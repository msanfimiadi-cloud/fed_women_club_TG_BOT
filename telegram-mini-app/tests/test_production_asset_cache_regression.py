import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "server/production-server.js").read_text(encoding="utf-8")
INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_source_index_has_static_app_import_and_no_js_entry_watchdog_backend_call() -> None:
    assert '<script type="module" src="/src/main.tsx"></script>' in INDEX
    assert "bloomHtmlEntryWatchdog" in INDEX
    watchdog = INDEX[INDEX.index("bloomHtmlEntryWatchdog") : INDEX.index("</script>", INDEX.index("bloomHtmlEntryWatchdog"))]
    assert "fetch(" not in watchdog
    assert "JS entry не выполнен" in watchdog


def test_server_cache_constants_apply_to_html_and_hashed_assets() -> None:
    assert "HTML_NO_STORE_CACHE_CONTROL = 'no-store, no-cache, max-age=0, must-revalidate'" in SERVER
    assert "ASSET_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'" in SERVER
    serve_frontend = SERVER[SERVER.index("async function serveFrontend") : SERVER.index("async function handleRequest")]
    assert "'cache-control': HTML_NO_STORE_CACHE_CONTROL" in serve_frontend
    assert "pragma: 'no-cache'" in serve_frontend
    assert "expires: '0'" in serve_frontend
    serve_asset = SERVER[SERVER.index("async function serveAsset") : SERVER.index("async function serveUpload")]
    assert "'cache-control': ASSET_IMMUTABLE_CACHE_CONTROL" in serve_asset
    assert "sendText(response, 404, 'Not found')" in serve_asset
    assert "serveFrontend" not in serve_asset


def test_built_production_html_references_only_existing_assets_after_build() -> None:
    dist_index = ROOT / "dist" / "index.html"
    assert dist_index.is_file(), "run npm run build before pytest so dist/index.html exists"
    html = dist_index.read_text(encoding="utf-8")
    asset_paths = set(re.findall(r'''(?:src|href)=["'](/assets/[^"']+)["']''', html))
    assert asset_paths, "production HTML must reference built /assets files"
    for asset_path in asset_paths:
        assert (ROOT / "dist" / asset_path.removeprefix("/")).is_file(), f"missing built asset {asset_path}"
