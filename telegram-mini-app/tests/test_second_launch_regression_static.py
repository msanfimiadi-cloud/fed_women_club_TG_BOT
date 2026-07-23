from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
WEBAPP = (ROOT / "src/telegram/webapp.ts").read_text(encoding="utf-8")
SERVER = (ROOT / "server/production-server.js").read_text(encoding="utf-8")


def test_bootstrap_can_be_forced_after_bfcache_pageshow_without_global_one_shot_flag() -> None:
    assert 'window.addEventListener("pageshow", onPageShow)' in APP
    assert 'if (!event.persisted)' in APP
    assert 'if (bootstrapPromiseRef.current)' in APP
    assert 'traceStartup("pageshow_retry_skipped_active_bootstrap")' in APP
    assert 'traceStartup("pageshow_retry_started_after_idle")' in APP
    assert 'void loadAppData("retry", true);' in APP
    assert APP.index('if (bootstrapPromiseRef.current)') < APP.index('traceStartup("pageshow_retry_skipped_active_bootstrap")')
    assert APP.index('traceStartup("pageshow_retry_started_after_idle")') < APP.index('void loadAppData("retry", true);')
    assert "bootstrapSequenceRef" in APP
    assert "bootstrapPromiseRef.current = null" in APP
    assert "resetTelegramLoginInFlight();" in APP


def test_webview_resume_events_reprepare_viewport_idempotently() -> None:
    assert 'document.addEventListener("resume", onResume)' in APP
    assert 'document.addEventListener("visibilitychange", onVisibilityChange)' in APP
    assert 'document.visibilityState === "visible"' in APP
    assert 'lifecycleTrace("webview_resume_prepare_start"' in APP
    assert 'lifecycleTrace("webview_resume_prepare_ok"' in APP


def test_repeated_prepare_telegram_viewport_cleans_previous_listeners_first() -> None:
    prepare_index = WEBAPP.index("export function prepareTelegramViewport")
    cleanup_index = WEBAPP.index("cleanupTelegramViewportListeners?.();", prepare_index)
    ready_index = WEBAPP.index("webApp.ready?.();", prepare_index)
    on_event_index = WEBAPP.index("webApp.onEvent?.('viewportChanged'", prepare_index)
    assert cleanup_index < ready_index < on_event_index
    assert "cleanupTelegramViewportListeners = null;" in WEBAPP
    assert "__BLOOM_TG_VIEWPORT_PREPARE_COUNT__" in WEBAPP
    assert "__BLOOM_TG_VIEWPORT_CLEANUP_COUNT__" in WEBAPP


def test_fallback_removed_after_successful_mount_and_cannot_cover_ready_app() -> None:
    assert 'entryFallback?.remove();' in MAIN
    assert 'htmlFallback?.remove();' in MAIN
    assert 'window.__BLOOM_ENTRY_FALLBACK_OVERLAY_REMOVED__ = true;' in MAIN
    mount_index = APP.index('lifecycleTrace("app_mount"')
    remove_index = APP.index('removeEntryFallbackOverlay();')
    assert mount_index < remove_index


def test_startup_errors_are_visible_without_backend_endpoint() -> None:
    assert "function persistStartupError" in MAIN
    assert "window.__BLOOM_LAST_STARTUP_ERROR__" in MAIN
    assert '"session" + "Storage"' in MAIN
    assert '?.setItem("bloom_last_startup_error"' in MAIN
    assert 'console.error("bloom_startup_error"' in MAIN
    assert "fetch(" not in MAIN[MAIN.index("function persistStartupError") : MAIN.index("function renderModuleLoadErrorPanel")]


def test_production_html_is_no_store_and_assets_are_immutable() -> None:
    assert "const HTML_NO_STORE_CACHE_CONTROL = 'no-store, no-cache, max-age=0, must-revalidate'" in SERVER
    assert "'cache-control': HTML_NO_STORE_CACHE_CONTROL" in SERVER
    assert "pragma: 'no-cache'" in SERVER
    assert "expires: '0'" in SERVER
    assert "const ASSET_IMMUTABLE_CACHE_CONTROL = 'public, max-age=31536000, immutable'" in SERVER
    assert "'cache-control': ASSET_IMMUTABLE_CACHE_CONTROL" in SERVER


def test_production_static_serving_logs_safe_index_and_asset_events() -> None:
    assert "frontend_index_served" in SERVER
    assert "frontend_asset_served" in SERVER
    assert "frontend_asset_missing" in SERVER
    assert "cacheControlType" in SERVER
    assert "isTelegramUserAgent" in SERVER
    assert "contentLength" in SERVER
    assert "injectedCatalogBootstrap" in SERVER


def test_app_static_import_is_preserved() -> None:
    assert 'import App from "./App";' in MAIN
    assert 'import("./App")' not in MAIN
    assert "import('./App')" not in MAIN


def test_html_fallback_reports_js_entry_not_executed_without_backend_endpoint() -> None:
    index = (ROOT / "index.html").read_text(encoding="utf-8")
    assert "__BLOOM_ENTRY_SCRIPT_EXECUTED__ = false" in index
    assert "bloomHtmlEntryWatchdog" in index
    assert "JS entry не выполнен" in index
    assert "устаревшего HTML" in index
    assert "fetch(" not in index[index.index("bloomHtmlEntryWatchdog") : index.index("</script>", index.index("bloomHtmlEntryWatchdog"))]
    assert "__BLOOM_ENTRY_SCRIPT_EXECUTED__ = true" in MAIN


def test_missing_assets_are_not_spa_fallbacks() -> None:
    asset_section = SERVER[SERVER.index("async function serveAsset") : SERVER.index("async function serveUpload")]
    assert "sendText(response, 404, 'Not found')" in asset_section
    assert "serveFrontend" not in asset_section
    assert "frontend_asset_missing" in asset_section


def test_all_versioned_paths_use_current_index_handler_without_redirect() -> None:
    route_section = SERVER[SERVER.index("function isVersionedFrontendRoute") : SERVER.index("const REQUEST_LOG_WINDOW_MS")]
    assert "pathname.startsWith('/app-v')" in route_section
    request_section = SERVER[SERVER.index("if (isVersionedFrontendRoute(pathname))") : SERVER.index("sendText(response, 404, 'Not found');", SERVER.index("if (isVersionedFrontendRoute(pathname))"))]
    assert "serveFrontend" in request_section
    assert "writeHead(30" not in request_section


def test_pageshow_persisted_during_active_bootstrap_does_not_force_retry() -> None:
    on_pageshow = APP[APP.index('const onPageShow = (event: PageTransitionEvent) => {'):APP.index('const onResume =', APP.index('const onPageShow = (event: PageTransitionEvent) => {'))]
    assert 'refreshAfterWebViewResume(event);' in on_pageshow
    assert 'if (!event.persisted)' in on_pageshow
    assert 'if (bootstrapPromiseRef.current)' in on_pageshow
    assert 'traceStartup("pageshow_retry_skipped_active_bootstrap")' in on_pageshow
    assert 'void loadAppData("retry", true);' in on_pageshow
    assert on_pageshow.index('if (bootstrapPromiseRef.current)') < on_pageshow.index('traceStartup("pageshow_retry_skipped_active_bootstrap")') < on_pageshow.index('return;', on_pageshow.index('traceStartup("pageshow_retry_skipped_active_bootstrap")'))
    assert on_pageshow.index('traceStartup("pageshow_retry_started_after_idle")') < on_pageshow.index('void loadAppData("retry", true);')


def test_active_bootstrap_sequence_not_invalidated_by_pageshow_persisted() -> None:
    on_pageshow = APP[APP.index('const onPageShow = (event: PageTransitionEvent) => {'):APP.index('const onResume =', APP.index('const onPageShow = (event: PageTransitionEvent) => {'))]
    active_branch = on_pageshow[on_pageshow.index('if (bootstrapPromiseRef.current)'):on_pageshow.index('traceStartup("pageshow_retry_started_after_idle")')]
    assert 'loadAppData("retry", true)' not in active_branch
    assert 'bootstrapPromiseRef.current = null' not in active_branch
    assert 'resetTelegramLoginInFlight()' not in active_branch


def test_post_auth_guard_cannot_get_pageshow_sequence_mismatch_during_active_bootstrap() -> None:
    on_pageshow = APP[APP.index('const onPageShow = (event: PageTransitionEvent) => {'):APP.index('const onResume =', APP.index('const onPageShow = (event: PageTransitionEvent) => {'))]
    assert 'if (bootstrapPromiseRef.current)' in on_pageshow
    assert 'return;' in on_pageshow[on_pageshow.index('if (bootstrapPromiseRef.current)'):on_pageshow.index('traceStartup("pageshow_retry_started_after_idle")')]
    assert 'loadAppData_before_post_auth_isActive_guard' in APP
    assert 'sequence_mismatch' in APP


def test_load_partners_still_called_after_successful_profile_subscription() -> None:
    post_auth_section = APP[APP.index('traceStartup("loadAppData_before_post_auth_isActive_guard"'):APP.index('traceStartup("loadAppData_optional_requests_started"')]
    assert 'traceStartup("loadAppData_profile_success")' in APP
    assert 'traceStartup("loadAppData_subscription_success")' in APP
    assert 'void loadPartners(true);' in post_auth_section
    assert post_auth_section.index('setData(') < post_auth_section.index('void loadPartners(true);')


def test_pageshow_persisted_after_idle_bootstrap_can_trigger_safe_retry() -> None:
    on_pageshow = APP[APP.index('const onPageShow = (event: PageTransitionEvent) => {'):APP.index('const onResume =', APP.index('const onPageShow = (event: PageTransitionEvent) => {'))]
    assert 'traceStartup("pageshow_retry_started_after_idle")' in on_pageshow
    assert on_pageshow.index('if (bootstrapPromiseRef.current)') < on_pageshow.index('traceStartup("pageshow_retry_started_after_idle")') < on_pageshow.index('void loadAppData("retry", true);')


def test_visibilitychange_resume_focus_behavior_unchanged() -> None:
    assert 'const onResume = (event: Event) => refreshAfterWebViewResume(event);' in APP
    assert 'const onFocus = () => traceStartup("focus");' in APP
    assert 'const onBlur = () => traceStartup("blur");' in APP
    assert 'document.visibilityState === "visible"' in APP
    assert 'refreshAfterWebViewResume(event);' in APP[APP.index('const onVisibilityChange'):APP.index('window.addEventListener("pageshow", onPageShow)')]
