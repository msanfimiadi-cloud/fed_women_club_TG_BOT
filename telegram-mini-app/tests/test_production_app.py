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

from backend.telegram_catalog import production_app
from backend.telegram_catalog import app as catalog_app
from backend.telegram_catalog.database import init_db


def call_production(
    path: str,
    method: str = "GET",
    body: bytes = b"",
    headers: dict[str, str] | None = None,
) -> tuple[str, dict[str, str], bytes]:
    environ: dict[str, Any] = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    for key, value in (headers or {}).items():
        environ_key = key.upper().replace("-", "_")
        if environ_key == "CONTENT_TYPE":
            environ["CONTENT_TYPE"] = value
        else:
            environ[f"HTTP_{environ_key}"] = value
    status_holder: dict[str, Any] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> None:
        status_holder["status"] = status
        status_holder["headers"] = dict(headers)

    chunks = production_app.application(environ, start_response)
    body = b"".join(chunks if isinstance(chunks, Iterable) else [chunks])
    return status_holder["status"], status_holder["headers"], body


def configure_dist(dist_dir: Path) -> None:
    production_app.DIST_DIR = dist_dir
    production_app.ASSETS_DIR = dist_dir / "assets"
    production_app.INDEX_FILE = dist_dir / "index.html"


def configure_uploads(uploads_dir: Path) -> None:
    production_app.UPLOADS_DIR = uploads_dir


def write_dist() -> tempfile.TemporaryDirectory[str]:
    temp_dir = tempfile.TemporaryDirectory()
    dist = Path(temp_dir.name)
    (dist / "assets").mkdir()
    (dist / "index.html").write_text('<!doctype html><div id="root">Bloom Club</div>', encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')", encoding="utf-8")
    configure_dist(dist)
    return temp_dir


def configure_temp_db() -> tempfile.TemporaryDirectory[str]:
    temp_dir = tempfile.TemporaryDirectory()
    os.environ["TELEGRAM_APP_DATABASE_URL"] = f"sqlite:///{Path(temp_dir.name) / 'telegram_app.db'}"
    os.environ.pop("TELEGRAM_AUTO_INIT_DB", None)
    init_db()
    return temp_dir


def assert_json_response(headers: dict[str, str], body: bytes) -> dict[str, Any]:
    assert headers["Content-Type"].startswith("application/json")
    assert not body.lstrip().startswith(b"<!doctype html")
    return json.loads(body.decode("utf-8"))


def test_health_through_production_app_returns_json_not_index_html() -> None:
    with write_dist():
        status, headers, body = call_production("/api/tg/health")

    assert status.startswith("200")
    assert assert_json_response(headers, body) == {"status": "ok", "service": "telegram-local-catalog"}


def test_status_through_production_app_returns_controlled_json_without_secrets() -> None:
    os.environ["TELEGRAM_APP_DATABASE_URL"] = "postgresql://gen_user:super-secret@192.168.0.4:5432/default_db"
    with write_dist():
        status, headers, body = call_production("/api/tg/status")

    assert status.startswith(("200", "503"))
    payload = assert_json_response(headers, body)
    assert payload["service"] == "telegram-local-catalog"
    decoded = body.decode("utf-8")
    assert "super-secret" not in decoded
    assert "TELEGRAM_APP_DATABASE_URL" not in decoded


def test_partners_through_production_app_returns_json_shape_not_index_html() -> None:
    with write_dist(), configure_temp_db():
        status, headers, body = call_production("/api/tg/partners")

    assert status.startswith("200")
    assert assert_json_response(headers, body) == {"items": []}


def test_giveaways_through_production_app_returns_public_content_contract_not_stub() -> None:
    class FakeContentResponse:
        def __enter__(self) -> "FakeContentResponse":
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "giveaways": [
                        {
                            "id": 7,
                            "title": "Лето",
                            "active": True,
                            "url": "https://cdn.test/g.jpg",
                            "items": [{"id": 3, "title": "Приз", "photo_url": "https://cdn.test/p.jpg"}],
                        },
                        {"id": 8, "title": "Скрыт", "is_active": False},
                    ]
                }
            ).encode("utf-8")

    original_urlopen = catalog_app.urlopen
    catalog_app.urlopen = lambda *_args, **_kwargs: FakeContentResponse()
    try:
        with write_dist():
            status, headers, body = call_production("/api/tg/giveaways")
    finally:
        catalog_app.urlopen = original_urlopen

    assert status.startswith("200")
    payload = assert_json_response(headers, body)
    assert [item["id"] for item in payload["items"]] == [7]
    assert payload["items"][0]["photo_url"] == "https://cdn.test/g.jpg"
    assert payload["items"][0]["items"][0]["image_url"] == "https://cdn.test/p.jpg"


def test_admin_partner_and_photo_routes_through_production_app_feed_public_catalog() -> None:
    previous_token = os.environ.get("TELEGRAM_ADMIN_API_TOKEN")
    os.environ["TELEGRAM_ADMIN_API_TOKEN"] = "test-token"
    try:
        with write_dist(), configure_temp_db():
            headers = {"Content-Type": "application/json", "X-Telegram-Admin-Token": "test-token"}
            partner_body = json.dumps(
                {
                    "external_content_id": 999999,
                    "title": "Route Test",
                    "display_name": "Route Test",
                    "description": "route test",
                    "city": "НСК",
                    "category": "Красота",
                    "address": "test",
                    "phone": "test",
                    "is_active": True,
                }
            ).encode("utf-8")

            status, response_headers, body = call_production(
                "/api/tg/admin/partners", "POST", partner_body, headers
            )
            assert status.startswith("201")
            created = assert_json_response(response_headers, body)

            updated_body = json.dumps(
                {"external_content_id": 999999, "title": "Route Test Updated", "is_active": True}
            ).encode("utf-8")
            status, response_headers, body = call_production(
                "/api/tg/admin/partners", "POST", updated_body, headers
            )
            assert status.startswith("201")
            updated = assert_json_response(response_headers, body)
            assert updated["id"] == created["id"]
            assert updated["title"] == "Route Test Updated"

            photo_body = json.dumps(
                {"external_content_id": 888888, "url": "https://cdn.test/route.jpg", "is_main": True}
            ).encode("utf-8")
            status, response_headers, body = call_production(
                f"/api/tg/admin/partners/{created['id']}/photos", "POST", photo_body, headers
            )
            assert status.startswith("201")
            photo = assert_json_response(response_headers, body)
            assert photo["image_url"] == "https://cdn.test/route.jpg"
            assert photo["is_cover"] is True

            status, response_headers, body = call_production("/api/tg/partners")
            assert status.startswith("200")
            public_payload = assert_json_response(response_headers, body)
            assert len(public_payload["items"]) == 1
            assert public_payload["items"][0]["id"] == created["id"]
            assert public_payload["items"][0]["cover"] == "https://cdn.test/route.jpg"
    finally:
        if previous_token is None:
            os.environ.pop("TELEGRAM_ADMIN_API_TOKEN", None)
        else:
            os.environ["TELEGRAM_ADMIN_API_TOKEN"] = previous_token


def test_node_production_server_registers_tg_admin_routes_before_api_404() -> None:
    source = (Path(__file__).resolve().parents[1] / "server" / "production-server.js").read_text(encoding="utf-8")

    assert "pathname === '/api/tg/admin/partners'" in source
    assert "^\\/api\\/tg\\/admin\\/partners\\/\\d+\\/photos$" in source
    assert source.index("handleAdminPartners(request, response, pathname)") < source.index("pathname.startsWith('/api/')")




def test_node_admin_partner_writes_do_not_require_external_content_unique_index() -> None:
    source = (Path(__file__).resolve().parents[1] / "server" / "production-server.js").read_text(encoding="utf-8")
    admin_start = source.index("async function handleAdminPartners")
    admin_end = source.index("async function handlePartners", admin_start)
    admin_source = source[admin_start:admin_end]

    assert "SELECT id FROM telegram_partners WHERE external_content_id = $1 LIMIT 1" in admin_source
    assert "UPDATE telegram_partners SET" in admin_source
    assert "CURRENT_TIMESTAMP::TEXT" in admin_source
    assert "ON CONFLICT (external_content_id)" not in admin_source
    assert "data.is_active ? 1 : 0" in admin_source


def test_node_admin_photo_writes_match_current_schema_without_unique_index() -> None:
    source = (Path(__file__).resolve().parents[1] / "server" / "production-server.js").read_text(encoding="utf-8")
    admin_start = source.index("async function handleAdminPartners")
    admin_end = source.index("async function handlePartners", admin_start)
    admin_source = source[admin_start:admin_end]

    assert "SELECT id FROM telegram_partner_photos WHERE external_content_id = $1 LIMIT 1" in admin_source
    assert "UPDATE telegram_partner_photos SET" in admin_source
    assert "UPDATE telegram_partner_photos SET is_cover = 0 WHERE partner_id = $1" in admin_source
    assert "updated_at" not in admin_source[admin_source.index("telegram_partner_photos") :]
    assert "const coverValue = data.is_cover ? 1 : 0" in admin_source
    assert "ON CONFLICT (external_content_id)" not in admin_source


def test_node_admin_db_errors_are_logged_without_changing_safe_response() -> None:
    source = (Path(__file__).resolve().parents[1] / "server" / "production-server.js").read_text(encoding="utf-8")

    assert "function logDatabaseError(routeName, operationName, error)" in source
    assert "message=${JSON.stringify(error?.message || '')}" in source
    assert "code=${JSON.stringify(error?.code || '')}" in source
    assert "detail=${JSON.stringify(error?.detail || '')}" in source
    assert "logDatabaseError('telegram_catalog_admin', operationName, error)" in source
    assert "detail: 'database_unavailable'" in source

def test_frontend_routes_return_html_index() -> None:
    with write_dist():
        for path in ("/", "/some/frontend/path"):
            status, headers, body = call_production(path)
            assert status.startswith("200")
            assert headers["Content-Type"].startswith("text/html")
            assert b"Bloom Club" in body


def test_unknown_api_routes_return_json_404_not_html() -> None:
    with write_dist(), configure_temp_db():
        for path in ("/api/tg/unknown", "/api/unknown"):
            status, headers, body = call_production(path)
            assert status.startswith("404")
            assert assert_json_response(headers, body) == {"detail": "not_found"}


def test_missing_dist_index_returns_controlled_500_for_frontend_route() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        configure_dist(Path(temp_dir))
        status, headers, body = call_production("/missing-client-route")

    assert status.startswith("500")
    assert headers["Content-Type"].startswith("text/plain")
    decoded = body.decode("utf-8")
    assert "dist/index.html is missing" in decoded
    assert "secret" not in decoded.lower()



def test_removed_admin_and_upload_routes_do_not_serve_frontend_or_proxy() -> None:
    with write_dist():
        for path in ("/tg-admin", "/api/content/admin", "/api/content/admin/blocks", "/api/content/uploads"):
            status, headers, body = call_production(path, "POST" if path == "/api/content/uploads" else "GET")
            assert status.startswith("404")
            assert not body.lstrip().startswith(b"<!doctype html")


def test_uploads_are_served_as_static_files() -> None:
    with write_dist(), tempfile.TemporaryDirectory() as temp_dir:
        uploads_dir = Path(temp_dir) / "uploads"
        (uploads_dir / "content").mkdir(parents=True)
        (uploads_dir / "content" / "image.png").write_bytes(b"png-content")
        configure_uploads(uploads_dir)

        status, headers, body = call_production("/uploads/content/image.png")

    assert status.startswith("200")
    assert headers["Content-Type"] == "image/png"
    assert body == b"png-content"


def test_production_entrypoint_does_not_wrap_app_in_strict_mode() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "main.tsx").read_text(encoding="utf-8")

    render_expression = source[source.index("root.render(") : source.index("console.info('app_after_render_call')")]

    assert "import.meta.env.DEV ? <React.StrictMode>" in render_expression
    assert ": app" in render_expression
    assert "<React.StrictMode>" not in render_expression.split(": app", 1)[1]


def test_early_error_fallback_exists_before_create_root() -> None:
    source = (Path(__file__).resolve().parents[1] / "src" / "main.tsx").read_text(encoding="utf-8")

    create_root_index = source.index("ReactDOM.createRoot")

    assert source.index("window.onerror") < create_root_index
    assert source.index("window.onunhandledrejection") < create_root_index
    assert source.index("renderEarlyErrorDiagnostic") < create_root_index
    assert "pre_react_startup_error" in source
    assert "replaceChildren" in source
    assert "initData" in source


def test_startup_diagnostic_markers_exist() -> None:
    main_source = (Path(__file__).resolve().parents[1] / "src" / "main.tsx").read_text(encoding="utf-8")
    app_source = (Path(__file__).resolve().parents[1] / "src" / "App.tsx").read_text(encoding="utf-8")

    assert "app_entry_loaded" in main_source
    assert "app_before_create_root" in main_source
    assert "app_after_render_call" in main_source
    assert "app_component_mount_start" in app_source


def test_node_production_server_versioned_spa_routes_keep_api_and_static_paths() -> None:
    import socket
    import subprocess
    import time
    import urllib.error
    import urllib.request

    repo_root = Path(__file__).resolve().parents[1]
    dist = repo_root / "dist"
    assets = dist / "assets"
    index_file = dist / "index.html"
    assets.mkdir(parents=True, exist_ok=True)
    if not index_file.is_file():
        index_file.write_text(
            '<!doctype html><html><head></head><body><div id="root">Bloom Club</div><script type="module" src="/assets/app.js"></script></body></html>',
            encoding="utf-8",
        )
    (assets / "pytest-static.js").write_text("console.log('static-ok')", encoding="utf-8")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    env = os.environ.copy()
    env.update(
        {
            "HOST": "127.0.0.1",
            "PORT": str(port),
            "TELEGRAM_APP_DATABASE_URL": "",
            "TELEGRAM_AUTO_INIT_DB": "false",
            "WEB_CONTENT_API_BASE_URL": "http://127.0.0.1:1/api/content-test",
            "CONTENT_PROXY_TIMEOUT_MS": "100",
            "NODE_ENV": "test",
        }
    )
    process = subprocess.Popen(
        ["node", "server/production-server.js"],
        cwd=repo_root,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    def request_with_headers(path: str) -> tuple[int, dict[str, str], bytes]:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def request(path: str) -> tuple[int, str, bytes]:
        status, headers, body = request_with_headers(path)
        return status, headers.get("content-type", ""), body

    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                status, _, _ = request("/ready")
                if status == 200:
                    break
            except OSError:
                pass
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                raise AssertionError(f"Node production server exited early:\n{output}")
            time.sleep(0.1)
        else:
            raise AssertionError("Node production server did not become ready")

        status, headers, body = request_with_headers("/app-v20260625-12")
        assert status == 200
        assert headers.get("content-type", "").startswith("text/html")
        assert headers.get("cache-control") == "no-store, no-cache, max-age=0, must-revalidate"
        assert headers.get("pragma") == "no-cache"
        assert headers.get("expires") == "0"
        assert b"__BLOOM_TG_CATALOG_BOOTSTRAP__" in body
        assert b' src="/assets/' in body or b" src='/assets/" in body

        status, headers, root_body = request_with_headers("/")
        assert status == 200
        assert headers.get("cache-control") == "no-store, no-cache, max-age=0, must-revalidate"
        assert root_body == body

        status, content_type, body = request("/api/tg/partners")
        assert status == 200
        assert content_type.startswith("application/json")
        assert json.loads(body.decode("utf-8")) == {"items": []}

        head_request = urllib.request.Request(f"http://127.0.0.1:{port}/api/tg/giveaways", method="HEAD")
        with urllib.request.urlopen(head_request, timeout=5) as response:
            status, headers, body = response.status, dict(response.headers), response.read()
        assert status == 200
        assert body == b""

        status, headers, body = request_with_headers("/assets/pytest-static.js")
        assert status == 200
        assert headers.get("content-type", "").startswith("text/javascript")
        assert headers.get("cache-control") == "public, max-age=31536000, immutable"
        assert body == b"console.log('static-ok')"

        status, headers, body = request_with_headers("/assets/missing-entry.js")
        assert status == 404
        assert headers.get("content-type", "").startswith("text/plain")
        assert headers.get("cache-control") == "no-store, no-cache, max-age=0, must-revalidate"
        assert b"<!doctype html" not in body.lower()

        status, content_type, body = request("/api/unknown")
        assert status == 404
        assert content_type.startswith("application/json")
        assert json.loads(body.decode("utf-8")) == {"detail": "not_found"}

        status, headers, body = request_with_headers("/ready")
        assert status == 200
        assert headers.get("content-type", "").startswith("text/plain")
        assert headers.get("x-content-type-options") == "nosniff"
        assert headers.get("referrer-policy") == "no-referrer"
        assert headers.get("permissions-policy") == "camera=(), microphone=(), geolocation=(), payment=()"
        assert "content-security-policy-report-only" in {key.lower(): value for key, value in headers.items()}
        assert "content-security-policy" not in {key.lower(): value for key, value in headers.items()}
        assert body == b"ok"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_client_api_trial_post_without_auth_returns_web_401_not_500() -> None:
    import http.server
    import socket
    import subprocess
    import threading
    import time
    import urllib.error
    import urllib.request

    seen: list[dict[str, Any]] = []

    class WebHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0") or "0")
            seen.append({"path": self.path, "auth": self.headers.get("authorization"), "body": self.rfile.read(length)})
            self.send_response(401)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"detail":"not_authenticated"}')

        def log_message(self, format: str, *args: Any) -> None:
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        web_port = sock.getsockname()[1]
    web_server = http.server.ThreadingHTTPServer(("127.0.0.1", web_port), WebHandler)
    thread = threading.Thread(target=web_server.serve_forever, daemon=True)
    thread.start()

    repo_root = Path(__file__).resolve().parents[1]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "TELEGRAM_APP_DATABASE_URL": "",
        "TELEGRAM_AUTO_INIT_DB": "false",
        "WEB_CLIENTS_API_BASE_URL": f"http://127.0.0.1:{web_port}/api/v1",
        "NODE_ENV": "test",
    })
    process = subprocess.Popen(["node", "server/production-server.js"], cwd=repo_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1).read()
                break
            except OSError:
                if process.poll() is not None:
                    raise AssertionError(process.stdout.read() if process.stdout else "server exited")
                time.sleep(0.1)
        else:
            raise AssertionError("Node production server did not become ready")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/clients/me/trial-subscription?source=tg",
            data=b'{"plan":"trial"}',
            method="POST",
            headers={"content-type": "application/json"},
        )
        try:
            urllib.request.urlopen(request, timeout=5)
            raise AssertionError("expected HTTPError")
        except urllib.error.HTTPError as error:
            body = error.read()
            assert error.code == 401
            assert body == b'{"detail":"not_authenticated"}'
        assert seen == [{"path": "/api/v1/clients/me/trial-subscription?source=tg", "auth": None, "body": b'{"plan":"trial"}'}]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        web_server.shutdown()
        web_server.server_close()


def test_client_api_trial_post_proxies_authorization_method_and_body() -> None:
    import http.server
    import socket
    import subprocess
    import threading
    import time
    import urllib.request

    seen: list[dict[str, Any]] = []

    class WebHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("content-length", "0") or "0")
            seen.append({"method": self.command, "path": self.path, "auth": self.headers.get("authorization"), "body": self.rfile.read(length)})
            self.send_response(201)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status":"trial_started"}')

        def log_message(self, format: str, *args: Any) -> None:
            return

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        web_port = sock.getsockname()[1]
    web_server = http.server.ThreadingHTTPServer(("127.0.0.1", web_port), WebHandler)
    thread = threading.Thread(target=web_server.serve_forever, daemon=True)
    thread.start()

    repo_root = Path(__file__).resolve().parents[1]
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = os.environ.copy()
    env.update({
        "HOST": "127.0.0.1",
        "PORT": str(port),
        "TELEGRAM_APP_DATABASE_URL": "",
        "TELEGRAM_AUTO_INIT_DB": "false",
        "WEB_CLIENTS_API_BASE_URL": f"http://127.0.0.1:{web_port}/api/v1/",
        "NODE_ENV": "test",
    })
    process = subprocess.Popen(["node", "server/production-server.js"], cwd=repo_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/ready", timeout=1).read()
                break
            except OSError:
                if process.poll() is not None:
                    raise AssertionError(process.stdout.read() if process.stdout else "server exited")
                time.sleep(0.1)
        else:
            raise AssertionError("Node production server did not become ready")

        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/v1/clients/me/trial-subscription",
            data=b'{"source":"tg"}',
            method="POST",
            headers={"authorization": "Bearer valid-token", "content-type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=5) as response:
            assert response.status == 201
            assert response.read() == b'{"status":"trial_started"}'
        assert seen == [{"method": "POST", "path": "/api/v1/clients/me/trial-subscription", "auth": "Bearer valid-token", "body": b'{"source":"tg"}'}]
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        web_server.shutdown()
        web_server.server_close()


def test_client_api_non_trial_post_to_clients_me_remains_disallowed_static() -> None:
    server = (Path(__file__).resolve().parents[1] / "server" / "production-server.js").read_text(encoding="utf-8")
    assert "request.method === 'POST' && pathname !== '/api/v1/clients/me/trial-subscription'" in server
    assert "sendMethodNotAllowed(response)" in server
