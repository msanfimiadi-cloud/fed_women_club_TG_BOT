from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_diagnostics_enable_without_query_params_and_hidden_gesture():
    diag = read("src/diagnostics/productionDebug.ts")
    app = read("src/App.tsx")
    shell = read("src/components/AppShell.tsx")
    assert 'localStorage.getItem("BLOOM_DEBUG")' in diag
    assert 'sessionStorage.getItem("BLOOM_DEBUG")' in diag
    assert 'window.BLOOM_DEBUG' in diag
    assert 'debugTapCountRef.current >= 7' in app
    assert 'onHiddenDiagnosticsGesture' in shell


def test_copy_snapshot_contains_required_json_sections():
    overlay = read("src/components/DiagnosticOverlay.tsx")
    diag = read("src/diagnostics/productionDebug.ts")
    assert 'Скопировать диагностику' in overlay
    assert 'createProductionDiagnosticSnapshot' in overlay
    for key in [
        'startupSessionId', 'buildHash', 'buildDate', 'startupTrace',
        'catalogTrace', 'networkTrace', 'errors', 'flags', 'telegram', 'browser'
    ]:
        assert key in diag


def test_startup_session_id_is_created_and_added_to_fetch():
    main = read("src/main.tsx")
    diag = read("src/diagnostics/productionDebug.ts")
    assert 'installProductionDiagnostics();' in main
    assert '__BLOOM_STARTUP_SESSION_ID__' in diag
    assert 'startup_session_created' in diag
    assert 'headers.set("X-Startup-Session", getStartupSessionId())' in diag


def test_fetch_wrapper_logs_full_lifecycle_and_sanitizes_secrets():
    diag = read("src/diagnostics/productionDebug.ts")
    for event in [
        'request created', 'request started', 'headers prepared', 'signal attached',
        'timeout attached', 'response received', 'request failed', 'request aborted'
    ]:
        assert event in diag
    assert 'authorization|initdata|init_data|telegram_payload|access_token|token' in diag.lower()
    assert '[redacted]' in diag


def test_abort_and_runtime_errors_are_logged():
    diag = read("src/diagnostics/productionDebug.ts")
    boundary = read("src/components/RuntimeErrorBoundary.tsx")
    assert 'AbortController created' in diag
    assert 'signal aborted' in diag
    assert 'abort called' in diag
    assert 'window.addEventListener("error"' in diag
    assert 'window.addEventListener("unhandledrejection"' in diag
    assert 'RuntimeErrorBoundary_error' in boundary


def test_diagnostics_are_diagnostic_only_no_fallback_contract_change():
    diag = read("src/diagnostics/productionDebug.ts")
    assert 'return r;' in diag
    assert 'throw e;' in diag
    assert '[]' not in diag.split('catch(e)')[1].split('throw e;')[0]
