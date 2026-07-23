"""Production WSGI entrypoint for Timeweb Telegram Mini App deployment.

This app serves the local Telegram catalog API and the built Vite SPA from a
single Python process so `/api/tg/*` never falls through to `dist/index.html`.
"""
from __future__ import annotations

import json
import mimetypes
import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Callable
from wsgiref.simple_server import make_server

from .app import application as telegram_catalog_application

StartResponse = Callable[[str, list[tuple[str, str]]], None]

REPO_ROOT = Path(__file__).resolve().parents[2]
DIST_DIR = REPO_ROOT / "dist"
ASSETS_DIR = DIST_DIR / "assets"
INDEX_FILE = DIST_DIR / "index.html"
UPLOADS_DIR = REPO_ROOT / "uploads"


def _json_response(start_response: StartResponse, status: str, payload: dict[str, Any]) -> list[bytes]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _text_response(start_response: StartResponse, status: str, payload: str) -> list[bytes]:
    body = payload.encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _content_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _send_file(start_response: StartResponse, path: Path, content_type: str | None = None) -> list[bytes]:
    body = path.read_bytes()
    start_response(
        "200 OK",
        [
            ("Content-Type", content_type or _content_type(path)),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _safe_asset_path(path: str) -> Path | None:
    relative = path.removeprefix("/assets/")
    if not relative or relative.startswith("/"):
        return None
    candidate = (ASSETS_DIR / relative).resolve()
    assets_root = ASSETS_DIR.resolve()
    if candidate == assets_root or assets_root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate



def _safe_upload_path(path: str) -> Path | None:
    relative = path.removeprefix("/uploads/")
    if not relative or relative.startswith("/"):
        return None
    candidate = (UPLOADS_DIR / relative).resolve()
    uploads_root = UPLOADS_DIR.resolve()
    if candidate == uploads_root or uploads_root not in candidate.parents:
        return None
    if not candidate.is_file():
        return None
    return candidate


def _frontend_index(start_response: StartResponse) -> list[bytes]:
    if not INDEX_FILE.is_file():
        return _text_response(
            start_response,
            "500 Internal Server Error",
            "Vite dist/index.html is missing. Run npm run build before starting production app.",
        )
    return _send_file(start_response, INDEX_FILE, "text/html; charset=utf-8")


def application(environ: dict[str, Any], start_response: StartResponse) -> Iterable[bytes]:
    """Route API requests to the WSGI backend and frontend routes to Vite dist."""
    path = environ.get("PATH_INFO", "") or "/"

    if (
        path == "/api/tg"
        or path.startswith("/api/tg/")
    ):
        return telegram_catalog_application(environ, start_response)

    if path.startswith("/api/") or path == "/api":
        return _json_response(start_response, "404 Not Found", {"detail": "not_found"})

    if path.startswith("/assets/"):
        asset_path = _safe_asset_path(path)
        if asset_path is None:
            return _text_response(start_response, "404 Not Found", "Not found")
        return _send_file(start_response, asset_path)

    if path.startswith("/uploads/"):
        upload_path = _safe_upload_path(path)
        if upload_path is None:
            return _text_response(start_response, "404 Not Found", "Not found")
        return _send_file(start_response, upload_path)

    if path == "/tg-admin":
        return _text_response(start_response, "404 Not Found", "Not found")

    if path == "/favicon.ico":
        favicon = DIST_DIR / "favicon.ico"
        if favicon.is_file():
            return _send_file(start_response, favicon)
        return _text_response(start_response, "404 Not Found", "Not found")

    return _frontend_index(start_response)


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    with make_server("0.0.0.0", port, application) as server:
        print(f"Telegram production app listening on http://0.0.0.0:{port}")
        server.serve_forever()


if __name__ == "__main__":
    main()
