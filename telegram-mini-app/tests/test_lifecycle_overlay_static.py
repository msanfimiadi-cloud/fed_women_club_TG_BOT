from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
OVERLAY = (ROOT / "src/components/DiagnosticOverlay.tsx").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "src/diagnostics/lifecycleTrace.ts").read_text(encoding="utf-8")


def test_diagnostic_overlay_exists_with_required_actions() -> None:
    assert "diagnostic-overlay" in OVERLAY
    assert "Скопировать диагностику" in OVERLAY
    assert "Перезагрузить" in OVERLAY
    assert "createLifecycleDiagnosticSnapshot" in OVERLAY


def test_react_lifecycle_markers_exist() -> None:
    for marker in [
        "entry_start",
        "entry_finish",
        "react_createRoot_start",
        "react_createRoot_ok",
        "react_createRoot_fail",
        "react_render_start",
        "react_render_ok",
        "react_render_fail",
        "app_render",
    ]:
        assert marker in (MAIN + APP)


def test_app_mount_unmount_and_effect_markers_exist() -> None:
    for marker in [
        "app_mount",
        "app_unmount",
        "app_effect_page_start",
        "app_effect_page_cleanup",
        "app_effect_watchdogs_start",
        "app_effect_watchdogs_cleanup",
        "page_transition",
    ]:
        assert marker in APP


def test_boundary_import_markers_exist_without_app_dynamic_import_timeout() -> None:
    for marker in [
        "boundary_import_start",
        "boundary_import_ok",
        "boundary_import_fail",
        "import_boundary_start",
        "import_boundary_ok",
        "import_boundary_fail",
    ]:
        assert marker in MAIN
    assert "app_module_timeout" not in MAIN


def test_sensitive_fields_are_redacted() -> None:
    assert "[redacted]" in LIFECYCLE
    for sensitive in [
        "authorization",
        "initdata",
        "init_data",
        "launch_payload",
        "jwt",
        "cookie",
        "secret",
        "password",
        "telegram_admin_api_token",
    ]:
        assert sensitive in LIFECYCLE.lower()
