from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE = (ROOT / "src/diagnostics/startupTrace.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
ERROR_STATE = (ROOT / "src/components/ErrorState.tsx").read_text(encoding="utf-8")
STYLES = (ROOT / "src/styles.css").read_text(encoding="utf-8")


def test_startup_trace_helper_exists() -> None:
    for marker in ["traceStart", "traceOk", "traceFail", "traceMark", "getStartupTrace", "__BLOOM_STARTUP_TRACE__", "bloom_startup_trace"]:
        assert marker in TRACE


def test_startup_trace_redacts_secret_fields() -> None:
    assert "SENSITIVE_KEY_PATTERN" in TRACE
    for secret in ["authorization", "initdata", "init_data", "token", "telegram_admin_api_token"]:
        assert secret in TRACE.lower()
    assert ".filter(([key]) => !SENSITIVE_KEY_PATTERN.test(key))" in TRACE


def test_main_has_required_trace_markers() -> None:
    for marker in [
        "app_entry_loaded",
        "pre_react_handlers_installed",
        "root_container_ready",
        "boundary_import_start",
        "boundary_import_ok",
        "boundary_import_fail",
        "import_boundary_start",
        "import_boundary_ok",
        "import_boundary_fail",
        "entry_loading_fallback_rendered",
        "create_root_start",
        "render_call_start",
        "render_call_ok",
    ]:
        assert marker in MAIN


def test_app_has_required_bootstrap_markers() -> None:
    for marker in [
        "app_component_mount",
        "app_initial_state",
        "loadAppData_start",
        "telegram_prepare_start",
        "telegram_runtime_check_start",
        "launch_payload_read_start",
        "stored_token_check_start",
        "telegram_login_start",
        "fresh_profile_start",
        "stale_state_cleanup_start",
        "partner_flow_reset_start",
        "app_data_set_start",
        "secondary_requests_start",
        "verifications_start",
        "savings_start",
        "cities_start",
        "linking_status_start",
        "secondary_requests_done",
        "bootstrap_done",
        "render_page_start",
        "render_page_ok",
        "catalog_bootstrap_available",
        "catalog_bootstrap_consumed",
        "catalog_bootstrap_missing",
        "catalog_load_start",
        "catalog_load_ok",
        "catalog_load_fail",
        "partner_open_start",
        "offers_load_start",
        "offers_load_ok",
        "offers_load_fail",
    ]:
        assert marker in APP


def test_post_auth_is_active_guard_diagnostics_are_present() -> None:
    guard_section = APP[
        APP.index("const postAuthMounted = mountedRef.current;") :
        APP.index('traceStart("stale_state_cleanup_start"')
    ]

    assert 'const postAuthMounted = mountedRef.current;' in guard_section
    assert 'const postAuthBootstrapSequence = bootstrapSequenceRef.current;' in guard_section
    assert 'const postAuthIsActive = isActive();' in guard_section
    assert 'traceStartup("loadAppData_before_post_auth_isActive_guard"' in guard_section
    for payload_key in [
        "sequenceId",
        "mounted: postAuthMounted",
        "bootstrapSequence: postAuthBootstrapSequence",
        "isActive: postAuthIsActive",
    ]:
        assert payload_key in guard_section
    assert 'if (!isActive()) {' in guard_section
    assert 'traceStartup("loadAppData_post_auth_isActive_guard_return"' in guard_section
    assert "reason: !postAuthMounted" in guard_section
    assert '"mountedRef_false"' in guard_section
    assert '"sequence_mismatch"' in guard_section
    assert '"unknown"' in guard_section
    assert guard_section.index('traceStartup("loadAppData_before_post_auth_isActive_guard"') < guard_section.index('if (!isActive()) {')
    assert guard_section.index('traceStartup("loadAppData_post_auth_isActive_guard_return"') < guard_section.index("return;")


def test_post_optional_is_active_guard_diagnostics_are_present() -> None:
    guard_section = APP[
        APP.index('traceStartup("loadAppData_before_post_optional_isActive_guard"') :
        APP.index('lifecycleTrace("secondary_requests_ok"')
    ]

    assert 'traceStartup("loadAppData_before_post_optional_isActive_guard"' in guard_section
    for payload_key in [
        "sequenceId",
        "mounted: mountedRef.current",
        "bootstrapSequence: bootstrapSequenceRef.current",
        "isActive: isActive()",
    ]:
        assert payload_key in guard_section
    assert 'if (!isActive()) {' in guard_section
    assert 'traceStartup("loadAppData_post_optional_isActive_guard_return"' in guard_section
    assert "reason: !mountedRef.current" in guard_section
    assert '"mountedRef_false"' in guard_section
    assert '"sequence_mismatch"' in guard_section
    assert '"unknown"' in guard_section
    assert guard_section.index('traceStartup("loadAppData_before_post_optional_isActive_guard"') < guard_section.index('if (!isActive()) {')
    assert guard_section.index('traceStartup("loadAppData_post_optional_isActive_guard_return"') < guard_section.index("return;")


def test_is_active_guard_business_flow_is_preserved() -> None:
    post_auth_section = APP[
        APP.index('traceStartup("loadAppData_before_post_auth_isActive_guard"') :
        APP.index('traceStartup("loadAppData_optional_requests_started"')
    ]

    assert post_auth_section.index('if (!isActive()) {') < post_auth_section.index('traceStart("stale_state_cleanup_start"')
    assert post_auth_section.index('traceStart("app_data_set_start"') < post_auth_section.index('void loadPartners(true);')
    assert 'void loadPartners(true);' in post_auth_section


def test_visible_diagnostic_overlay_watchdog_exists() -> None:
    assert "startup_watchdog_5s" in APP
    assert "startup_watchdog_8s" in APP
    assert "isStartupDebugUiEnabledValue" in APP
    assert "Открыть debug диагностику" in APP
    assert "startup-diagnostic-panel" in APP
    assert ".startup-diagnostic-panel" in STYLES


def test_error_state_includes_startup_trace_details() -> None:
    assert "startupTrace" in ERROR_STATE
    assert "lastEvents" in ERROR_STATE
    assert "currentPage" in ERROR_STATE
    assert "bootstrapStatus" in ERROR_STATE
    assert "catalogStatus" in ERROR_STATE
    assert "offersStatus" in ERROR_STATE


def test_index_entry_uses_static_app_import_and_visible_fallback() -> None:
    assert 'import App from "./App";' in MAIN
    assert "import('./App')" not in MAIN
    assert 'import("./App")' not in MAIN
    assert "Bloom Club загружается" in MAIN
    assert "startup-entry-diagnostics" in MAIN
    assert "startup-entry-fallback" in STYLES


def test_app_dynamic_import_timeout_removed_but_failure_panel_remains() -> None:
    assert "MODULE_IMPORT_TIMEOUT_MS" not in MAIN
    assert "Promise.race" not in MAIN
    assert "app_module_timeout" not in MAIN
    assert "renderEarlyErrorDiagnostic(error, 'app_module_import')" in MAIN
    assert "Не удалось загрузить модуль приложения" in MAIN
    assert "Перезагрузить" in MAIN
    assert "lastEvents: getStartupTrace().slice(-20)" in MAIN
    assert "startup-entry-error-panel" in STYLES


def test_no_blank_root_possible_after_index_chunk_load() -> None:
    assert 'wrapper.id = "bloom-entry-fallback-overlay"' in MAIN
    assert "document.body.appendChild(wrapper)" in MAIN
    assert "document.documentElement.appendChild(wrapper)" in MAIN
    assert "rootElement.replaceChildren(panel)" in MAIN
    assert "renderStartupLoadingFallback();" in MAIN
