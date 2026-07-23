from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACE = (ROOT / "src/diagnostics/startupTrace.ts").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
CLIENT = (ROOT / "src/api/client.ts").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
OVERLAY = (ROOT / "src/components/DiagnosticOverlay.tsx").read_text(encoding="utf-8")
BOUNDARY = (ROOT / "src/components/RuntimeErrorBoundary.tsx").read_text(encoding="utf-8")


def test_required_trace_events_present_across_startup_catalog_chain() -> None:
    required = [
        "entry_script_executed",
        "app_component_rendered",
        "app_component_mounted",
        "runtime_error_boundary_mounted",
        "loadAppData_called",
        "loadAppData_started",
        "loadAppData_login_started",
        "loadAppData_login_success",
        "loadAppData_profile_started",
        "loadAppData_profile_success",
        "loadAppData_subscription_started",
        "loadAppData_subscription_success",
        "loadAppData_core_catalog_requested",
        "loadAppData_optional_requests_started",
        "loadAppData_optional_requests_finished",
        "loadAppData_finished",
        "loadAppData_failed",
        "loadPartners_called",
        "loadPartners_entered",
        "loadPartners_before_getPartners",
        "getPartners_called",
        "getPartnersAttempt_called",
        "getPartners_target_created",
        "getPartners_abort_controller_created",
        "getPartners_before_fetch",
        "getPartners_fetch_started",
        "getPartners_fetch_response",
        "getPartners_fetch_json_started",
        "getPartners_fetch_json_success",
        "getPartners_success",
        "getPartners_error",
        "loadPartners_success",
        "loadPartners_error",
        "catalog_timeout_created",
        "catalog_timeout_fired",
        "catalog_abort_called",
        "catalog_signal_aborted_before_fetch",
        "catalog_signal_aborted_after_error",
        "visibilitychange",
        "pageshow",
        "focus",
        "blur",
        "telegram_viewport_prepare_called",
        "telegram_viewport_prepare_finished",
    ]
    combined = "\n".join([TRACE, APP, CLIENT, MAIN, OVERLAY, BOUNDARY])
    for event in required:
        assert event in combined


def test_trace_helper_redacts_sensitive_data_and_is_debug_or_dev_only() -> None:
    assert "SENSITIVE_KEY_PATTERN" in TRACE
    for sensitive in ["authorization", "initdata", "init_data", "access_token", "token"]:
        assert sensitive in TRACE.lower()
    assert "import.meta.env.DEV" in TRACE
    assert 'get("debug") === "1"' in TRACE
    assert "console.debug" in TRACE
    assert "console.info(\"bloom_startup_trace" not in TRACE


def test_core_catalog_request_is_before_optional_requests() -> None:
    assert APP.index("loadAppData_core_catalog_requested") < APP.index("loadAppData_optional_requests_started")


def test_catalog_fetch_sequence_and_timeout_order() -> None:
    assert APP.index("loadPartners_called") < APP.index("loadPartners_before_getPartners")
    get_partners_body = CLIENT[CLIENT.index("export async function getPartners"):]
    assert get_partners_body.index("getPartners_called") < get_partners_body.index("getPartnersAttempt(attempt)")
    assert CLIENT.index("getPartners_before_fetch") < CLIENT.index("getPartners_fetch_started")
    assert CLIENT.index("getPartners_before_fetch") < CLIENT.index("catalog_timeout_created")
    assert CLIENT.index("catalog_timeout_fired") < CLIENT.index("catalog_abort_called")


def test_diagnostics_overlay_debug_only_and_shows_catalog_trace_state() -> None:
    assert "isStartupDebugUiEnabledValue ?" in APP
    for marker in [
        "window.__BLOOM_STARTUP_TRACE__",
        "Last catalog error",
        "catalogLoadRequested",
        "fetchStarted",
        "timeoutStarted",
        "activePage",
        "currentPath",
        "hasToken",
        "hasProfile",
        "hasSubscription",
        "partnerCount",
        "catalogStatus",
    ]:
        assert marker in APP or marker in OVERLAY
