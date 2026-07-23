from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.telegram_catalog import app as catalog_app
from backend.telegram_catalog.database import connect, init_db

ADMIN_TOKEN = "test-token"


def call_app(
    path: str,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    token: str | None = None,
    bearer: str | None = None,
) -> tuple[str, dict[str, Any]]:
    payload = json.dumps(body or {}).encode("utf-8") if body is not None else b""
    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(payload)),
        "wsgi.input": io.BytesIO(payload),
    }
    if token:
        environ["HTTP_X_TELEGRAM_ADMIN_TOKEN"] = token
    if bearer:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {bearer}"
    status_holder: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status

    chunks = catalog_app.application(environ, start_response)
    response_body = b"".join(chunks if isinstance(chunks, Iterable) else [chunks])
    return status_holder["status"], json.loads(response_body.decode("utf-8"))


def setup_temp_db() -> tempfile.TemporaryDirectory[str]:
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["TELEGRAM_APP_DATABASE_URL"] = f"sqlite:///{Path(temp_dir.name) / 'telegram_app.db'}"
    os.environ["TELEGRAM_ADMIN_API_TOKEN"] = ADMIN_TOKEN
    os.environ.pop("TELEGRAM_AUTO_INIT_DB", None)
    init_db()
    return temp_dir


def create_partner(title: str = "Demo", **payload: Any) -> dict[str, Any]:
    status, created = call_app(
        "/api/tg/admin/partners",
        "POST",
        {"title": title, **payload},
        token=ADMIN_TOKEN,
    )
    assert status.startswith("201")
    return created


def test_admin_auth_accepts_configured_headers_and_blocks_missing_or_wrong_token() -> None:
    with setup_temp_db():
        status, payload = call_app("/api/tg/admin/partners")
        assert status.startswith("401")
        assert payload == {"detail": "admin_api_token_required"}

        status, payload = call_app("/api/tg/admin/partners", token="bad-token")
        assert status.startswith("403")
        assert payload == {"detail": "admin_api_token_invalid"}

        status, payload = call_app("/api/tg/admin/partners", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert payload == {"items": []}

        status, payload = call_app("/api/tg/admin/partners", bearer=ADMIN_TOKEN)
        assert status.startswith("200")
        assert payload == {"items": []}


def test_admin_writes_require_configured_token() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["TELEGRAM_APP_DATABASE_URL"] = f"sqlite:///{Path(temp_dir) / 'telegram_app.db'}"
        os.environ.pop("TELEGRAM_ADMIN_API_TOKEN", None)
        init_db()

        status, payload = call_app("/api/tg/admin/partners", "POST", {"title": "blocked"})
        assert status.startswith("501")
        assert payload == {"detail": "admin_api_token_not_configured"}


def test_partners_crud_and_public_catalog_filters_inactive_partners() -> None:
    with setup_temp_db():
        active = create_partner("  Demo  ", display_name="  Demo Name  ", city=" ")
        assert active["title"] == "Demo"
        assert active["display_name"] == "Demo Name"
        assert active["city"] is None
        assert active["sort_order"] == 100
        inactive = create_partner("Inactive", is_active=False)

        status, admin_partners = call_app("/api/tg/admin/partners", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert {item["id"] for item in admin_partners["items"]} == {active["id"], inactive["id"]}

        status, public_partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert [item["id"] for item in public_partners["items"]] == [active["id"]]

        status, patched = call_app(
            f"/api/tg/admin/partners/{active['id']}",
            "PATCH",
            {"category": " Cafe ", "sort_order": 3},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("200")
        assert patched["category"] == "Cafe"
        assert patched["sort_order"] == 3

        status, deleted = call_app(f"/api/tg/admin/partners/{active['id']}", "DELETE", token=ADMIN_TOKEN)
        assert status.startswith("204")
        assert deleted == {}

        status, public_partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert public_partners == {"items": []}

        status, admin_partners = call_app("/api/tg/admin/partners", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert [item["id"] for item in admin_partners["items"]] == [inactive["id"]]

        status, payload = call_app(f"/api/tg/admin/partners/{active['id']}", "DELETE", token=ADMIN_TOKEN)
        assert status.startswith("404")
        assert payload["detail"] == "partner_not_found"


def test_admin_partner_delete_removes_related_photos_offers_and_codes() -> None:
    with setup_temp_db():
        connection = connect()
        partner = create_partner("Cascade")
        partner_id = partner["id"]
        call_app(f"/api/tg/admin/partners/{partner_id}/photos", "POST", {"image_url": "https://cdn.test/p.jpg"}, token=ADMIN_TOKEN)
        status, offer = call_app(f"/api/tg/admin/partners/{partner_id}/offers", "POST", {"title": "Offer"}, token=ADMIN_TOKEN)
        assert status.startswith("201")
        connection.execute(
            "INSERT INTO telegram_privilege_codes (partner_id, offer_id, code) VALUES (?, ?, ?)",
            (partner_id, offer["id"], "CODE-1"),
        )
        connection.commit()

        status, payload = call_app(f"/api/tg/admin/partners/{partner_id}", "DELETE", token=ADMIN_TOKEN)
        assert status.startswith("204")
        assert payload == {}
        assert connection.execute("SELECT COUNT(*) AS count FROM telegram_partners WHERE id = ?", (partner_id,)).fetchone()["count"] == 0
        assert connection.execute("SELECT COUNT(*) AS count FROM telegram_partner_photos WHERE partner_id = ?", (partner_id,)).fetchone()["count"] == 0
        assert connection.execute("SELECT COUNT(*) AS count FROM telegram_partner_offers WHERE partner_id = ?", (partner_id,)).fetchone()["count"] == 0
        assert connection.execute("SELECT COUNT(*) AS count FROM telegram_privilege_codes WHERE partner_id = ?", (partner_id,)).fetchone()["count"] == 0
        connection.close()


def test_partner_validation_rejects_missing_title_and_object_string_fields() -> None:
    with setup_temp_db():
        status, payload = call_app("/api/tg/admin/partners", "POST", {"title": "   "}, token=ADMIN_TOKEN)
        assert status.startswith("400")
        assert payload == {"detail": "title_required"}

        status, payload = call_app(
            "/api/tg/admin/partners", "POST", {"title": "Demo", "city": {"bad": True}}, token=ADMIN_TOKEN
        )
        assert status.startswith("400")
        assert payload == {"detail": "city_must_be_string"}


def test_photos_crud_cover_logic_and_public_cover_selection() -> None:
    with setup_temp_db():
        partner = create_partner()
        partner_id = partner["id"]

        status, first = call_app(
            f"/api/tg/admin/partners/{partner_id}/photos",
            "POST",
            {"image_url": "https://example.com/b.jpg", "sort_order": 20},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")

        status, second = call_app(
            f"/api/tg/admin/partners/{partner_id}/photos",
            "POST",
            {"image_url": "https://example.com/a.jpg", "sort_order": 10},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")

        status, public_partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert public_partners["items"][0]["cover"] == "https://example.com/a.jpg"

        status, cover = call_app(
            f"/api/tg/admin/photos/{first['id']}",
            "PATCH",
            {"is_cover": True, "image_url": "https://bad.invalid/image.jpg"},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("200")
        assert cover["is_cover"] is True

        status, photos = call_app(f"/api/tg/admin/partners/{partner_id}/photos", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert photos["items"][0]["id"] == first["id"]
        assert [photo["is_cover"] for photo in photos["items"]] == [True, False]

        status, public_partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert public_partners["items"][0]["cover"] == "https://bad.invalid/image.jpg"

        status, payload = call_app(f"/api/tg/admin/photos/{second['id']}", "DELETE", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert payload == {"detail": "photo_deleted", "id": second["id"]}

        status, photos = call_app(f"/api/tg/admin/partners/{partner_id}/photos", token=ADMIN_TOKEN)
        assert [photo["id"] for photo in photos["items"]] == [first["id"]]


def test_photo_validation_requires_non_empty_image_url_string() -> None:
    with setup_temp_db():
        partner = create_partner()
        status, payload = call_app(
            f"/api/tg/admin/partners/{partner['id']}/photos",
            "POST",
            {"image_url": ""},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("400")
        assert payload == {"detail": "image_url_required"}

        status, payload = call_app(
            f"/api/tg/admin/partners/{partner['id']}/photos",
            "POST",
            {"image_url": ["bad"]},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("400")
        assert payload == {"detail": "image_url_must_be_string"}


def test_offers_crud_admin_includes_inactive_and_public_filters_inactive() -> None:
    with setup_temp_db():
        partner = create_partner()
        partner_id = partner["id"]

        status, offer = call_app(
            f"/api/tg/admin/partners/{partner_id}/offers",
            "POST",
            {
                "title": " Classic ",
                "description": " Service ",
                "conditions": " Terms ",
                "base_price": 2550.239,
                "member_price": 2250,
                "discount_percent": "",
            },
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")
        assert offer["title"] == "Classic"
        assert offer["description"] == "Service"
        assert offer["base_price"] == 2550.24
        assert offer["member_price"] == 2250.0
        assert offer["discount_percent"] is None

        status, inactive = call_app(
            f"/api/tg/admin/partners/{partner_id}/offers",
            "POST",
            {"title": "Inactive", "is_active": False},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")

        status, admin_offers = call_app(f"/api/tg/admin/partners/{partner_id}/offers", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert {item["id"] for item in admin_offers["items"]} == {offer["id"], inactive["id"]}

        status, public_offers = call_app(f"/api/tg/partners/{partner_id}/offers")
        assert status.startswith("200")
        assert [item["id"] for item in public_offers["items"]] == [offer["id"]]

        status, patched = call_app(
            f"/api/tg/admin/offers/{offer['id']}",
            "PATCH",
            {"conditions": "Updated", "discount_percent": 15},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("200")
        assert patched["conditions"] == "Updated"
        assert patched["discount_percent"] == 15.0

        status, deleted = call_app(f"/api/tg/admin/offers/{offer['id']}", "DELETE", token=ADMIN_TOKEN)
        assert status.startswith("200")
        assert deleted["is_active"] is False

        status, public_offers = call_app(f"/api/tg/partners/{partner_id}/offers")
        assert status.startswith("200")
        assert public_offers == {"items": []}


def test_offer_money_validation_rejects_objects_arrays_and_zero_member_price() -> None:
    with setup_temp_db():
        partner = create_partner()
        for body, detail in [
            ({"title": "Bad", "base_price": {"bad": True}}, "base_price_must_be_number_or_null"),
            ({"title": "Bad", "member_price": [1]}, "member_price_must_be_number_or_null"),
            ({"title": "Bad", "discount_percent": [1]}, "discount_percent_must_be_number_or_null"),
            ({"title": "Bad", "member_price": 0}, "member_price_must_be_positive"),
        ]:
            status, payload = call_app(
                f"/api/tg/admin/partners/{partner['id']}/offers", "POST", body, token=ADMIN_TOKEN
            )
            assert status.startswith("400")
            assert payload == {"detail": detail}


def test_verify_and_me_endpoints_are_controlled_until_access_context_exists() -> None:
    with setup_temp_db():
        status, payload = call_app("/api/tg/partners/1/offers/1/verify", "POST")
        assert status.startswith("501")
        assert payload == {"detail": "access_check_not_configured"}

        status, payload = call_app("/api/tg/me/verifications")
        assert status.startswith("501")
        assert payload == {"detail": "user_context_not_configured"}

        status, payload = call_app("/api/tg/me/savings")
        assert status.startswith("501")
        assert payload == {"detail": "user_context_not_configured"}



def test_status_endpoint_success_counts_and_runtime_hints() -> None:
    with setup_temp_db():
        active = create_partner("Active")
        inactive = create_partner("Inactive", is_active=False)
        status, offer = call_app(
            f"/api/tg/admin/partners/{active['id']}/offers",
            "POST",
            {"title": "Active offer", "is_active": True},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")
        status, inactive_offer = call_app(
            f"/api/tg/admin/partners/{inactive['id']}/offers",
            "POST",
            {"title": "Inactive offer", "is_active": False},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")

        os.environ["TELEGRAM_AUTO_INIT_DB"] = "true"
        status, payload = call_app("/api/tg/status")

        assert status.startswith("200")
        assert payload == {
            "status": "ok",
            "service": "telegram-local-catalog",
            "database": "ok",
            "partners_count": 2,
            "active_partners_count": 1,
            "offers_count": 2,
            "active_offers_count": 1,
            "auto_init_enabled": True,
            "local_catalog_enabled_hint": "frontend_env_only",
        }


def test_status_endpoint_db_failure_returns_503_without_secrets() -> None:
    os.environ["TELEGRAM_APP_DATABASE_URL"] = "invalid://user:secret@example.com/default_db"
    os.environ["TELEGRAM_ADMIN_API_TOKEN"] = "secret-admin-token"
    os.environ["TELEGRAM_AUTO_INIT_DB"] = "true"

    status, payload = call_app("/api/tg/status")

    assert status.startswith("503")
    assert payload == {
        "status": "error",
        "service": "telegram-local-catalog",
        "database": "error",
        "detail": "database_unavailable",
    }
    serialized = json.dumps(payload)
    assert "secret" not in serialized
    assert "invalid://" not in serialized

def test_health_endpoints_return_controlled_payloads() -> None:
    with setup_temp_db():
        status, payload = call_app("/api/tg/health")
        assert status.startswith("200")
        assert payload == {"status": "ok", "service": "telegram-local-catalog"}

        status, payload = call_app("/api/tg/health/db")
        assert status.startswith("200")
        assert payload == {"status": "ok", "database": "ok"}


def test_health_db_returns_503_without_secret_details() -> None:
    os.environ["TELEGRAM_APP_DATABASE_URL"] = "invalid://user:secret@example.com/default_db"

    status, payload = call_app("/api/tg/health/db")
    assert status.startswith("503")
    assert payload == {
        "status": "error",
        "database": "error",
        "detail": "database_unavailable",
    }
    assert "secret" not in json.dumps(payload)


def test_startup_auto_init_requires_explicit_true_and_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        db_path = Path(temp_dir) / "telegram_app.db"
        os.environ["TELEGRAM_APP_DATABASE_URL"] = f"sqlite:///{db_path}"
        os.environ.pop("TELEGRAM_AUTO_INIT_DB", None)
        catalog_app._startup_init_completed = False

        catalog_app.run_startup_init_if_enabled()
        assert not db_path.exists()

        os.environ["TELEGRAM_AUTO_INIT_DB"] = "true"
        catalog_app.run_startup_init_if_enabled()
        assert db_path.exists()

        catalog_app.run_startup_init_if_enabled()
        status, partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert partners == {"items": []}


def encode_multipart_file(filename: str, content_type: str, content: bytes, field_name: str = "file") -> tuple[bytes, str]:
    boundary = "----bloom-test-boundary"
    body = b"\r\n".join(
        [
            f"--{boundary}".encode("utf-8"),
            f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"'.encode("utf-8"),
            f"Content-Type: {content_type}".encode("utf-8"),
            b"",
            content,
            f"--{boundary}--".encode("utf-8"),
            b"",
        ]
    )
    return body, f"multipart/form-data; boundary={boundary}"


def call_upload_app(
    body: bytes,
    content_type: str,
    token: str | None = None,
    bearer: str | None = None,
) -> tuple[str, dict[str, Any]]:
    environ: dict[str, Any] = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": "/api/content/uploads",
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": io.BytesIO(body),
    }
    if token:
        environ["HTTP_X_TELEGRAM_ADMIN_TOKEN"] = token
    if bearer:
        environ["HTTP_AUTHORIZATION"] = f"Bearer {bearer}"
    status_holder: dict[str, str] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status

    chunks = catalog_app.application(environ, start_response)
    response_body = b"".join(chunks if isinstance(chunks, Iterable) else [chunks])
    return status_holder["status"], json.loads(response_body.decode("utf-8"))


def setup_upload_dir(temp_dir: str) -> Path:
    upload_dir = Path(temp_dir) / "uploads" / "content"
    catalog_app.CONTENT_UPLOAD_DIR = upload_dir
    return upload_dir


def test_content_upload_requires_admin_token() -> None:
    with setup_temp_db(), tempfile.TemporaryDirectory() as temp_dir:
        setup_upload_dir(temp_dir)
        body, content_type = encode_multipart_file("image.png", "image/png", b"png-content")

        status, payload = call_upload_app(body, content_type)

        assert status.startswith("401")
        assert payload == {"detail": "admin_api_token_required"}


def test_content_upload_rejects_unsupported_format() -> None:
    with setup_temp_db(), tempfile.TemporaryDirectory() as temp_dir:
        setup_upload_dir(temp_dir)
        body, content_type = encode_multipart_file("script.exe", "application/octet-stream", b"MZ")

        status, payload = call_upload_app(body, content_type, token=ADMIN_TOKEN)

        assert status.startswith("400")
        assert payload == {"detail": "unsupported_file_extension"}


def test_content_upload_rejects_large_file() -> None:
    with setup_temp_db(), tempfile.TemporaryDirectory() as temp_dir:
        setup_upload_dir(temp_dir)
        body, content_type = encode_multipart_file("image.png", "image/png", b"x" * (catalog_app.UPLOAD_MAX_BYTES + 1))

        status, payload = call_upload_app(body, content_type, token=ADMIN_TOKEN)

        assert status.startswith("400")
        assert payload == {"detail": "file_too_large"}


def test_content_upload_accepts_valid_image_formats_and_creates_files() -> None:
    cases = [
        ("image.png", "image/png", b"png-content", ".png"),
        ("photo.jpg", "image/jpeg", b"jpg-content", ".jpg"),
        ("photo.jpeg", "image/jpeg", b"jpeg-content", ".jpeg"),
        ("image.webp", "image/webp", b"webp-content", ".webp"),
    ]
    with setup_temp_db(), tempfile.TemporaryDirectory() as temp_dir:
        upload_dir = setup_upload_dir(temp_dir)
        for original_filename, mime_type, content, extension in cases:
            body, content_type = encode_multipart_file(original_filename, mime_type, content)

            status, payload = call_upload_app(body, content_type, token=ADMIN_TOKEN)

            assert status.startswith("200")
            assert payload["url"] == f"https://bloomclub.ru{payload['path']}"
            assert payload["path"] == f"/uploads/content/{payload['filename']}"
            assert payload["filename"].endswith(extension)
            assert payload["content_type"] == mime_type
            assert payload["size"] == len(content)
            assert (upload_dir / payload["filename"]).read_bytes() == content

def test_admin_published_partner_reaches_public_api_with_media_without_manual_sync() -> None:
    with setup_temp_db():
        status, created = call_app(
            "/api/tg/admin/partners",
            "POST",
            {"external_content_id": 501, "title": "Тест2", "is_active": True},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")
        status, photo = call_app(
            f"/api/tg/admin/partners/{created['id']}/photos",
            "POST",
            {"external_content_id": 701, "url": "https://cdn.test/test2.jpg", "is_main": True},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")
        assert photo["image_url"] == "https://cdn.test/test2.jpg"

        status, public_partners = call_app("/api/tg/partners")
        assert status.startswith("200")
        assert public_partners["items"][0]["title"] == "Тест2"
        assert public_partners["items"][0]["cover"] == "https://cdn.test/test2.jpg"

        status, duplicate = call_app(
            "/api/tg/admin/partners",
            "POST",
            {"external_content_id": 501, "title": "Тест2 updated", "is_active": True},
            token=ADMIN_TOKEN,
        )
        assert status.startswith("201")
        assert duplicate["id"] == created["id"]
        status, public_partners = call_app("/api/tg/partners")
        assert len(public_partners["items"]) == 1
        assert public_partners["items"][0]["title"] == "Тест2 updated"
