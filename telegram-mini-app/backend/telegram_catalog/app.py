"""WSGI app for the local Telegram catalog API.

This scaffold intentionally uses the Python standard library so adding it to the
frontend repository does not change the existing Vite deployment path.
"""
from __future__ import annotations

import json
import logging
import math
import re
import uuid
from collections.abc import Callable, Iterable
from email import policy
from email.parser import BytesParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import get_settings
from .database import connect, init_db, safe_database_url_summary
from .repository import (
    get_active_partner,
    list_active_offers,
    list_active_partners,
    list_admin_offers,
    list_admin_partners,
    list_partner_photos,
    row_to_dict,
)

StartResponse = Callable[[str, list[tuple[str, str]]], None]

logger = logging.getLogger(__name__)
_startup_init_completed = False
PARTNER_STRING_FIELDS = ("title", "display_name", "description", "city", "category", "address", "phone")
OFFER_STRING_FIELDS = ("title", "description", "conditions")
MONEY_FIELDS = ("base_price", "member_price", "discount_percent")
UPLOAD_MAX_BYTES = 10 * 1024 * 1024
UPLOAD_REQUEST_MAX_BYTES = UPLOAD_MAX_BYTES + 1024 * 1024
CONTENT_UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "content"
CONTENT_PUBLIC_BASE_URL = "https://bloomclub.ru"
WEB_CONTENT_GIVEAWAYS_URL = "https://bloomclub.ru/api/content/giveaways"
CONTENT_API_TIMEOUT_SECONDS = 20
ALLOWED_UPLOAD_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def table_exists(connection: Any, table_name: str) -> bool:
    if connection.__class__.__name__ == "PostgresConnection":
        row = connection.execute(
            "SELECT 1 AS table_exists FROM information_schema.tables WHERE table_schema = 'public' AND table_name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
        return row is not None
    row = connection.execute("SELECT 1 AS table_exists FROM sqlite_master WHERE type = 'table' AND name = ?", (table_name,)).fetchone()
    return row is not None


def json_response(
    start_response: StartResponse, status: str, payload: dict[str, Any]
) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def parse_json_body(environ: dict[str, Any]) -> dict[str, Any]:
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size <= 0:
        return {}
    raw = environ["wsgi.input"].read(size)
    if not raw:
        return {}
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("json_body_must_be_object")
    return decoded


def admin_is_authorized(environ: dict[str, Any]) -> tuple[bool, str | None]:
    token = get_settings().telegram_admin_api_token
    if not token:
        return False, "admin_api_token_not_configured"
    header_token = environ.get("HTTP_X_TELEGRAM_ADMIN_TOKEN")
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    bearer_token = auth_header.removeprefix("Bearer ") if auth_header.startswith("Bearer ") else None
    if not header_token and not bearer_token:
        return False, "admin_api_token_required"
    if header_token == token or bearer_token == token:
        return True, None
    return False, "admin_api_token_invalid"


def require_admin(environ: dict[str, Any], start_response: StartResponse) -> list[bytes] | None:
    authorized, reason = admin_is_authorized(environ)
    if authorized:
        return None
    if reason == "admin_api_token_not_configured":
        return json_response(start_response, "501 Not Implemented", {"detail": reason})
    if reason == "admin_api_token_required":
        return json_response(start_response, "401 Unauthorized", {"detail": reason})
    return json_response(start_response, "403 Forbidden", {"detail": reason})


def parse_multipart_upload(environ: dict[str, Any]) -> tuple[str, str, bytes]:
    content_type = (environ.get("CONTENT_TYPE") or "").strip()
    if not content_type.lower().startswith("multipart/form-data") or "boundary=" not in content_type.lower():
        raise ValueError("multipart_form_data_required")
    try:
        size = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        size = 0
    if size <= 0:
        raise ValueError("file_required")
    if size > UPLOAD_REQUEST_MAX_BYTES:
        raise ValueError("file_too_large")

    raw_body = environ["wsgi.input"].read(size)
    message_body = (
        b"Content-Type: "
        + content_type.encode("utf-8")
        + b"\r\nMIME-Version: 1.0\r\n\r\n"
        + raw_body
    )
    message = BytesParser(policy=policy.default).parsebytes(message_body)
    for part in message.iter_parts():
        if (
            part.get_content_disposition() != "form-data"
            or part.get_param("name", header="content-disposition") != "file"
        ):
            continue
        original_filename = part.get_filename()
        if not original_filename:
            raise ValueError("filename_required")
        extension = Path(original_filename).suffix.lower()
        expected_content_type = ALLOWED_UPLOAD_CONTENT_TYPES.get(extension)
        if expected_content_type is None:
            raise ValueError("unsupported_file_extension")
        file_content_type = (part.get_content_type() or "").lower()
        if file_content_type != expected_content_type:
            raise ValueError("unsupported_content_type")
        payload = part.get_payload(decode=True) or b""
        if not payload:
            raise ValueError("file_required")
        if len(payload) > UPLOAD_MAX_BYTES:
            raise ValueError("file_too_large")
        return extension, file_content_type, payload
    raise ValueError("file_required")


def upload_content_response(environ: dict[str, Any], start_response: StartResponse) -> list[bytes]:
    admin_error = require_admin(environ, start_response)
    if admin_error is not None:
        return admin_error
    if environ.get("REQUEST_METHOD", "GET").upper() != "POST":
        return json_response(start_response, "405 Method Not Allowed", {"detail": "method_not_allowed"})

    extension, content_type, payload = parse_multipart_upload(environ)
    CONTENT_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{extension}"
    target_path = CONTENT_UPLOAD_DIR / filename
    target_path.write_bytes(payload)
    public_path = f"/uploads/content/{filename}"
    return json_response(
        start_response,
        "200 OK",
        {
            "url": f"{CONTENT_PUBLIC_BASE_URL}{public_path}",
            "path": public_path,
            "filename": filename,
            "content_type": content_type,
            "size": len(payload),
        },
    )


def _as_list(data: Any, keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in keys:
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _normalize_giveaway_item(item: dict[str, Any]) -> dict[str, Any]:
    data = dict(item)
    image_url = data.get("image_url") or data.get("photo_url") or data.get("url") or data.get("image") or data.get("picture") or ""
    data["image_url"] = image_url
    data["photo_url"] = data.get("photo_url") or image_url
    if "is_active" not in data:
        data["is_active"] = bool(data.get("active", True))
    return data


def _normalize_giveaway(giveaway: dict[str, Any]) -> dict[str, Any]:
    data = dict(giveaway)
    photo_url = data.get("photo_url") or data.get("image_url") or data.get("url") or data.get("image") or data.get("picture") or ""
    data["photo_url"] = photo_url
    data["image_url"] = data.get("image_url") or photo_url
    if "is_active" not in data:
        data["is_active"] = bool(data.get("active", True))
    data["items"] = [
        _normalize_giveaway_item(item)
        for item in _as_list(data.get("items") or data.get("giveaway_items") or [], ("items", "giveaway_items"))
    ]
    data["photos"] = _as_list(data.get("photos") or data.get("giveaway_photos") or [], ("photos", "giveaway_photos"))
    return data


def giveaways_response(start_response: StartResponse) -> list[bytes]:
    request = Request(WEB_CONTENT_GIVEAWAYS_URL, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(request, timeout=CONTENT_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8") or "null")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        logger.exception("Failed to load public giveaways from WEB Content API")
        return json_response(start_response, "502 Bad Gateway", {"detail": "content_api_unavailable"})

    items = [_normalize_giveaway(item) for item in _as_list(payload, ("giveaways", "items", "data", "results"))]
    active_items = [item for item in items if item.get("is_active") is not False]
    active_items.sort(key=lambda item: float(item.get("sort_order") or item.get("order") or 0))
    return json_response(start_response, "200 OK", {"items": active_items})


def run_startup_init_if_enabled() -> None:
    """Run idempotent schema initialization when TELEGRAM_AUTO_INIT_DB=true."""
    global _startup_init_completed
    settings = get_settings()
    if _startup_init_completed or not settings.telegram_auto_init_db:
        return

    database_summary = safe_database_url_summary(settings.telegram_app_database_url)
    logger.info("TELEGRAM_AUTO_INIT_DB=true; initializing Telegram catalog DB: %s", database_summary)
    try:
        init_db(settings.telegram_app_database_url)
    except Exception as error:
        logger.error(
            "Telegram catalog DB auto init failed for %s; error_type=%s",
            database_summary,
            type(error).__name__,
        )
        raise RuntimeError(
            "Telegram catalog DB auto init failed. "
            f"Check TELEGRAM_APP_DATABASE_URL target ({database_summary}) and dependencies."
        ) from None
    _startup_init_completed = True
    logger.info("Telegram catalog DB auto init completed: %s", database_summary)



def count_rows(connection: Any, query: str) -> int:
    row = connection.execute(query).fetchone()
    return int(row["count"] if row else 0)


def status_response(start_response: StartResponse) -> list[bytes]:
    settings = get_settings()
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
            counts = {
                "partners_count": count_rows(connection, "SELECT COUNT(*) AS count FROM telegram_partners"),
                "active_partners_count": count_rows(
                    connection, "SELECT COUNT(*) AS count FROM telegram_partners WHERE is_active = 1"
                ),
                "offers_count": count_rows(connection, "SELECT COUNT(*) AS count FROM telegram_partner_offers"),
                "active_offers_count": count_rows(
                    connection, "SELECT COUNT(*) AS count FROM telegram_partner_offers WHERE is_active = 1"
                ),
            }
    except Exception:
        return json_response(
            start_response,
            "503 Service Unavailable",
            {
                "status": "error",
                "service": "telegram-local-catalog",
                "database": "error",
                "detail": "database_unavailable",
            },
        )

    return json_response(
        start_response,
        "200 OK",
        {
            "status": "ok",
            "service": "telegram-local-catalog",
            "database": "ok",
            **counts,
            "auto_init_enabled": settings.telegram_auto_init_db,
            "local_catalog_enabled_hint": "frontend_env_only",
        },
    )

def health_db_response(start_response: StartResponse) -> list[bytes]:
    try:
        with connect() as connection:
            connection.execute("SELECT 1")
    except Exception:
        return json_response(
            start_response,
            "503 Service Unavailable",
            {"status": "error", "database": "error", "detail": "database_unavailable"},
        )
    return json_response(start_response, "200 OK", {"status": "ok", "database": "ok"})


def require_object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field}_must_be_object")
    return value


def optional_string(payload: dict[str, Any], field: str, *, required: bool = False) -> str | None:
    if field not in payload:
        if required:
            raise ValueError(f"{field}_required")
        return None
    value = payload[field]
    if value is None:
        if required:
            raise ValueError(f"{field}_required")
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field}_must_be_string")
    trimmed = value.strip()
    if not trimmed:
        if required:
            raise ValueError(f"{field}_required")
        return None
    return trimmed


def optional_bool(payload: dict[str, Any], field: str, default: bool | None = None) -> bool | None:
    if field not in payload:
        return default
    if not isinstance(payload[field], bool):
        raise ValueError(f"{field}_must_be_boolean")
    return payload[field]


def optional_int(payload: dict[str, Any], field: str, default: int | None = None) -> int | None:
    if field not in payload:
        return default
    value = payload[field]
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field}_must_be_number")
    return int(value)


def optional_money(payload: dict[str, Any], field: str) -> float | None:
    if field not in payload or payload[field] is None:
        return None
    value = payload[field]
    if value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{field}_must_be_number_or_null")
    normalized = round(float(value), 2)
    if field == "member_price" and normalized <= 0:
        raise ValueError("member_price_must_be_positive")
    if normalized < 0:
        raise ValueError(f"{field}_must_be_non_negative")
    return normalized


def validate_partner_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    require_object(payload, "payload")
    validated: dict[str, Any] = {}
    for field in PARTNER_STRING_FIELDS:
        if field in payload or (field == "title" and not partial):
            validated[field] = optional_string(payload, field, required=(field == "title"))
    if "is_active" in payload or not partial:
        validated["is_active"] = optional_bool(payload, "is_active", True)
    if "sort_order" in payload or not partial:
        validated["sort_order"] = optional_int(payload, "sort_order", 100)
    if "external_content_id" in payload:
        validated["external_content_id"] = optional_int(payload, "external_content_id", None)
    return validated


def validate_photo_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    require_object(payload, "payload")
    validated: dict[str, Any] = {}
    image_payload = dict(payload)
    if "image_url" not in image_payload and "url" in image_payload:
        image_payload["image_url"] = image_payload.get("url")
    if "is_cover" not in image_payload and "is_main" in image_payload:
        image_payload["is_cover"] = image_payload.get("is_main")
    if "image_url" in image_payload or not partial:
        validated["image_url"] = optional_string(image_payload, "image_url", required=not partial)
    if "file_path" in image_payload:
        validated["file_path"] = optional_string(image_payload, "file_path")
    if "sort_order" in image_payload or not partial:
        validated["sort_order"] = optional_int(image_payload, "sort_order", 100)
    if "is_cover" in image_payload or not partial:
        validated["is_cover"] = optional_bool(image_payload, "is_cover", False)
    if "external_content_id" in image_payload:
        validated["external_content_id"] = optional_int(image_payload, "external_content_id", None)
    return validated


def validate_offer_payload(payload: dict[str, Any], *, partial: bool = False) -> dict[str, Any]:
    require_object(payload, "payload")
    validated: dict[str, Any] = {}
    for field in OFFER_STRING_FIELDS:
        if field in payload or (field == "title" and not partial):
            validated[field] = optional_string(payload, field, required=(field == "title"))
    for field in MONEY_FIELDS:
        if field in payload:
            validated[field] = optional_money(payload, field)
    if "is_active" in payload or not partial:
        validated["is_active"] = optional_bool(payload, "is_active", True)
    if "sort_order" in payload or not partial:
        validated["sort_order"] = optional_int(payload, "sort_order", 100)
    return validated


def get_partner_any(connection: Any, partner_id: int) -> dict[str, Any] | None:
    return row_to_dict(connection.execute("SELECT * FROM telegram_partners WHERE id = ?", (partner_id,)).fetchone())


def get_photo(connection: Any, photo_id: int) -> dict[str, Any] | None:
    return row_to_dict(connection.execute("SELECT * FROM telegram_partner_photos WHERE id = ?", (photo_id,)).fetchone())


def get_offer(connection: Any, offer_id: int) -> dict[str, Any] | None:
    return row_to_dict(connection.execute("SELECT * FROM telegram_partner_offers WHERE id = ?", (offer_id,)).fetchone())


def create_partner(connection: Any, payload: dict[str, Any]) -> dict[str, Any]:
    data = validate_partner_payload(payload)
    if data.get("external_content_id") is not None:
        existing = row_to_dict(connection.execute("SELECT * FROM telegram_partners WHERE external_content_id = ?", (data["external_content_id"],)).fetchone())
        if existing:
            patch_partner(connection, int(existing["id"]), data)
            return get_partner_any(connection, int(existing["id"])) or {}
    cursor = connection.execute(
        """
        INSERT INTO telegram_partners
            (external_content_id, title, display_name, description, city, category, address, phone, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            data.get("external_content_id"),
            data["title"],
            data.get("display_name"),
            data.get("description"),
            data.get("city"),
            data.get("category"),
            data.get("address"),
            data.get("phone"),
            1 if data.get("is_active", True) else 0,
            data.get("sort_order", 100),
        ),
    )
    partner_id = int(cursor.fetchone()["id"])
    connection.commit()
    return get_partner_any(connection, partner_id) or {}


def patch_partner(connection: Any, partner_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not get_partner_any(connection, partner_id):
        return None
    data = validate_partner_payload(payload, partial=True)
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in data.items():
        assignments.append(f"{key} = ?")
        values.append(1 if key == "is_active" and value else 0 if key == "is_active" else value)
    if assignments:
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        connection.execute(f"UPDATE telegram_partners SET {', '.join(assignments)} WHERE id = ?", (*values, partner_id))
        connection.commit()
    return get_partner_any(connection, partner_id)


def hard_delete_partner(connection: Any, partner_id: int) -> bool:
    if not get_partner_any(connection, partner_id):
        return False
    offer_rows = connection.execute("SELECT id FROM telegram_partner_offers WHERE partner_id = ?", (partner_id,)).fetchall()
    offer_ids = [int(row["id"]) for row in offer_rows]
    if offer_ids:
        placeholders = ",".join("?" for _ in offer_ids)
        if table_exists(connection, "telegram_offer_photos"):
            connection.execute(f"DELETE FROM telegram_offer_photos WHERE offer_id IN ({placeholders})", tuple(offer_ids))
        connection.execute(f"DELETE FROM telegram_privilege_codes WHERE offer_id IN ({placeholders})", tuple(offer_ids))
    connection.execute("DELETE FROM telegram_privilege_codes WHERE partner_id = ?", (partner_id,))
    connection.execute("DELETE FROM telegram_partner_photos WHERE partner_id = ?", (partner_id,))
    connection.execute("DELETE FROM telegram_partner_offers WHERE partner_id = ?", (partner_id,))
    connection.execute("DELETE FROM telegram_partners WHERE id = ?", (partner_id,))
    connection.commit()
    return True


def clear_other_covers(connection: Any, partner_id: int, photo_id: int | None = None) -> None:
    if photo_id is None:
        connection.execute("UPDATE telegram_partner_photos SET is_cover = 0 WHERE partner_id = ?", (partner_id,))
        return
    connection.execute(
        "UPDATE telegram_partner_photos SET is_cover = 0 WHERE partner_id = ? AND id <> ?",
        (partner_id, photo_id),
    )


def create_photo(connection: Any, partner_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not get_partner_any(connection, partner_id):
        return None
    data = validate_photo_payload(payload)
    if data.get("external_content_id") is not None:
        existing = row_to_dict(connection.execute("SELECT * FROM telegram_partner_photos WHERE external_content_id = ?", (data["external_content_id"],)).fetchone())
        if existing:
            patch_photo(connection, int(existing["id"]), data)
            return get_photo(connection, int(existing["id"])) or {}
    if data.get("is_cover"):
        clear_other_covers(connection, partner_id)
    cursor = connection.execute(
        """
        INSERT INTO telegram_partner_photos (partner_id, external_content_id, image_url, file_path, sort_order, is_cover)
        VALUES (?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            partner_id,
            data.get("external_content_id"),
            data.get("image_url"),
            data.get("file_path"),
            data.get("sort_order", 100),
            1 if data.get("is_cover", False) else 0,
        ),
    )
    photo_id = int(cursor.fetchone()["id"])
    connection.commit()
    return get_photo(connection, photo_id) or {}


def patch_photo(connection: Any, photo_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    current = get_photo(connection, photo_id)
    if not current:
        return None
    data = validate_photo_payload(payload, partial=True)
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in data.items():
        assignments.append(f"{key} = ?")
        values.append(1 if key == "is_cover" and value else 0 if key == "is_cover" else value)
    if assignments:
        if data.get("is_cover"):
            clear_other_covers(connection, int(current["partner_id"]), photo_id)
        connection.execute(f"UPDATE telegram_partner_photos SET {', '.join(assignments)} WHERE id = ?", (*values, photo_id))
        connection.commit()
    return get_photo(connection, photo_id)


def delete_photo(connection: Any, photo_id: int) -> dict[str, Any] | None:
    photo = get_photo(connection, photo_id)
    if not photo:
        return None
    connection.execute("DELETE FROM telegram_partner_photos WHERE id = ?", (photo_id,))
    connection.commit()
    return photo


def create_offer(connection: Any, partner_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not get_partner_any(connection, partner_id):
        return None
    data = validate_offer_payload(payload)
    cursor = connection.execute(
        """
        INSERT INTO telegram_partner_offers
            (partner_id, title, description, conditions, base_price, member_price,
             discount_percent, is_active, sort_order)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING id
        """,
        (
            partner_id,
            data["title"],
            data.get("description"),
            data.get("conditions"),
            data.get("base_price"),
            data.get("member_price"),
            data.get("discount_percent"),
            1 if data.get("is_active", True) else 0,
            data.get("sort_order", 100),
        ),
    )
    offer_id = int(cursor.fetchone()["id"])
    connection.commit()
    return get_offer(connection, offer_id) or {}


def patch_offer(connection: Any, offer_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
    if not get_offer(connection, offer_id):
        return None
    data = validate_offer_payload(payload, partial=True)
    assignments: list[str] = []
    values: list[Any] = []
    for key, value in data.items():
        assignments.append(f"{key} = ?")
        values.append(1 if key == "is_active" and value else 0 if key == "is_active" else value)
    if assignments:
        assignments.append("updated_at = CURRENT_TIMESTAMP")
        connection.execute(
            f"UPDATE telegram_partner_offers SET {', '.join(assignments)} WHERE id = ?",
            (*values, offer_id),
        )
        connection.commit()
    return get_offer(connection, offer_id)


def soft_delete_offer(connection: Any, offer_id: int) -> dict[str, Any] | None:
    if not get_offer(connection, offer_id):
        return None
    connection.execute(
        "UPDATE telegram_partner_offers SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (offer_id,),
    )
    connection.commit()
    return get_offer(connection, offer_id)


def application(environ: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "") or "/"

    if method == "GET" and path == "/api/tg/health":
        return json_response(start_response, "200 OK", {"status": "ok", "service": "telegram-local-catalog"})
    if method == "GET" and path == "/api/tg/health/db":
        return health_db_response(start_response)
    if path == "/api/content/uploads":
        try:
            return upload_content_response(environ, start_response)
        except ValueError as error:
            return json_response(start_response, "400 Bad Request", {"detail": str(error)})

    if method == "GET" and path == "/api/tg/status":
        return status_response(start_response)

    if method == "GET" and path == "/api/tg/giveaways":
        return giveaways_response(start_response)

    try:
        with connect() as connection:
            if method == "GET" and path == "/api/tg/partners":
                return json_response(start_response, "200 OK", {"items": list_active_partners(connection)})

            partner_match = re.fullmatch(r"/api/tg/partners/(\d+)", path)
            if method == "GET" and partner_match:
                partner = get_active_partner(connection, int(partner_match.group(1)))
                if not partner:
                    return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                return json_response(start_response, "200 OK", partner)

            offers_match = re.fullmatch(r"/api/tg/partners/(\d+)/offers", path)
            if method == "GET" and offers_match:
                partner_id = int(offers_match.group(1))
                if not get_active_partner(connection, partner_id):
                    return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                return json_response(start_response, "200 OK", {"items": list_active_offers(connection, partner_id)})

            verify_match = re.fullmatch(r"/api/tg/partners/(\d+)/offers/(\d+)/verify", path)
            if method == "POST" and verify_match:
                return json_response(start_response, "501 Not Implemented", {"detail": "access_check_not_configured"})

            if method == "GET" and path in ("/api/tg/me/verifications", "/api/tg/me/savings"):
                return json_response(start_response, "501 Not Implemented", {"detail": "user_context_not_configured"})

            if path.startswith("/api/tg/admin"):
                admin_error = require_admin(environ, start_response)
                if admin_error is not None:
                    return admin_error
                payload = parse_json_body(environ) if method in {"POST", "PATCH"} else {}

                if method == "GET" and path == "/api/tg/admin/partners":
                    return json_response(start_response, "200 OK", {"items": list_admin_partners(connection)})
                if method == "POST" and path == "/api/tg/admin/partners":
                    return json_response(start_response, "201 Created", create_partner(connection, payload))

                admin_partner_match = re.fullmatch(r"/api/tg/admin/partners/(\d+)", path)
                if admin_partner_match:
                    partner_id = int(admin_partner_match.group(1))
                    if method == "PATCH":
                        partner = patch_partner(connection, partner_id, payload)
                        if not partner:
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "200 OK", partner)
                    if method == "DELETE":
                        if not hard_delete_partner(connection, partner_id):
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "204 No Content", {})

                admin_photo_match = re.fullmatch(r"/api/tg/admin/partners/(\d+)/photos", path)
                if admin_photo_match:
                    partner_id = int(admin_photo_match.group(1))
                    if method == "GET":
                        if not get_partner_any(connection, partner_id):
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "200 OK", {"items": list_partner_photos(connection, partner_id)})
                    if method == "POST":
                        photo = create_photo(connection, partner_id, payload)
                        if not photo:
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "201 Created", photo)

                admin_patch_photo_match = re.fullmatch(r"/api/tg/admin/photos/(\d+)", path)
                if admin_patch_photo_match:
                    photo_id = int(admin_patch_photo_match.group(1))
                    if method == "PATCH":
                        photo = patch_photo(connection, photo_id, payload)
                        if not photo:
                            return json_response(start_response, "404 Not Found", {"detail": "photo_not_found"})
                        return json_response(start_response, "200 OK", photo)
                    if method == "DELETE":
                        photo = delete_photo(connection, photo_id)
                        if not photo:
                            return json_response(start_response, "404 Not Found", {"detail": "photo_not_found"})
                        return json_response(start_response, "200 OK", {"detail": "photo_deleted", "id": photo_id})

                admin_offers_match = re.fullmatch(r"/api/tg/admin/partners/(\d+)/offers", path)
                if admin_offers_match:
                    partner_id = int(admin_offers_match.group(1))
                    if method == "GET":
                        if not get_partner_any(connection, partner_id):
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "200 OK", {"items": list_admin_offers(connection, partner_id)})
                    if method == "POST":
                        offer = create_offer(connection, partner_id, payload)
                        if not offer:
                            return json_response(start_response, "404 Not Found", {"detail": "partner_not_found"})
                        return json_response(start_response, "201 Created", offer)

                admin_patch_offer_match = re.fullmatch(r"/api/tg/admin/offers/(\d+)", path)
                if admin_patch_offer_match:
                    offer_id = int(admin_patch_offer_match.group(1))
                    if method == "PATCH":
                        offer = patch_offer(connection, offer_id, payload)
                        if not offer:
                            return json_response(start_response, "404 Not Found", {"detail": "offer_not_found"})
                        return json_response(start_response, "200 OK", offer)
                    if method == "DELETE":
                        offer = soft_delete_offer(connection, offer_id)
                        if not offer:
                            return json_response(start_response, "404 Not Found", {"detail": "offer_not_found"})
                        return json_response(start_response, "200 OK", offer)

            return json_response(start_response, "404 Not Found", {"detail": "not_found"})
    except json.JSONDecodeError:
        return json_response(start_response, "400 Bad Request", {"detail": "invalid_json"})
    except ValueError as error:
        return json_response(start_response, "400 Bad Request", {"detail": str(error)})


run_startup_init_if_enabled()


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("0.0.0.0", 8000, application) as server:
        print("Telegram catalog API listening on http://0.0.0.0:8000")
        server.serve_forever()
