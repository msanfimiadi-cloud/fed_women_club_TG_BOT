from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
LIFECYCLE = (ROOT / "src/diagnostics/lifecycleTrace.ts").read_text(encoding="utf-8")


def test_main_uses_static_app_import_without_dynamic_app_import() -> None:
    assert 'import App from "./App";' in MAIN
    assert 'import("./App")' not in MAIN
    assert "import('./App')" not in MAIN
    assert "Bloom Club загружается" in MAIN
    assert "Если экран не меняется больше 10 секунд, нажмите перезагрузить" in MAIN


def test_app_module_timeout_path_is_removed() -> None:
    assert "app_module_timeout" not in MAIN
    assert "Dynamic import timeout after 15000ms" not in MAIN
    assert "MODULE_IMPORT_TIMEOUT_MS" not in MAIN


def test_static_import_startup_markers_exist() -> None:
    assert "__BLOOM_APP_STATIC_IMPORT_ENABLED__" in MAIN
    assert "window.__BLOOM_APP_STATIC_IMPORT_ENABLED__ = true;" in MAIN
    assert "__BLOOM_APP_RENDER_ATTEMPTED__" in MAIN
    assert "window.__BLOOM_APP_RENDER_ATTEMPTED__ = true;" in MAIN


def test_entry_fallback_contains_reload_and_diagnostics_buttons() -> None:
    assert 'createButton("Перезагрузить"' in MAIN
    assert 'createButton("Диагностика"' in MAIN


def test_entry_watchdog_status_updates_exist_without_app_timeout() -> None:
    assert "startEntryWatchdog" in MAIN
    assert "3_000" in MAIN
    assert "8_000" in MAIN
    assert "Загрузка модулей приложения" in MAIN
    assert "Приложение не завершило запуск" in MAIN
    assert "Открыть заново" in MAIN


def test_no_telegram_or_storage_access_before_static_fallback() -> None:
    before_fallback = MAIN[: MAIN.index("renderStartupLoadingFallback();")]
    forbidden_access = ["window.Telegram", ".Telegram", "localStorage", "sessionStorage", "JSON.parse"]
    for token in forbidden_access:
        assert token not in before_fallback
    assert "await " not in before_fallback


def test_lifecycle_trace_listener_setup_is_fail_safe() -> None:
    assert "try {\n  installLifecycleTraceListeners();" in LIFECYCLE
    assert "listener setup must not break entry startup" in LIFECYCLE
    assert "function sanitizeValue" in LIFECYCLE
    assert "return \"[unserializable]\"" in LIFECYCLE


def test_entry_static_imports_are_limited_to_startup_dependencies() -> None:
    assert 'import React from "react";' in MAIN
    assert 'import * as ReactDOM from "react-dom/client";' in MAIN
    assert 'import App from "./App";' in MAIN
    assert 'import "./styles.css";' in MAIN


def test_entry_fallback_insertion_precedes_boundary_import() -> None:
    fallback_index = MAIN.index("renderStartupLoadingFallback();")
    assert fallback_index < MAIN.index('import("./components/RuntimeErrorBoundary")')


def test_entry_fallback_has_inline_fixed_fullscreen_max_z_index() -> None:
    style_index = MAIN.index('"style"')
    assert "position: fixed" in MAIN[style_index:]
    assert "inset: 0" in MAIN[style_index:]
    assert "z-index: 2147483647" in MAIN[style_index:]
    assert "display: flex" in MAIN[style_index:]
    assert "align-items: center" in MAIN[style_index:]
    assert "justify-content: center" in MAIN[style_index:]
    assert "background: #fff7fa" in MAIN[style_index:]
    assert "color: #2b1b22" in MAIN[style_index:]
    assert "font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif" in MAIN[style_index:]


def test_entry_fallback_body_overlay_markers_exist() -> None:
    assert "__BLOOM_ENTRY_FALLBACK_INSERTED__" in MAIN
    assert "__BLOOM_ENTRY_FALLBACK_INSERTED_AT__" in MAIN
    assert "__BLOOM_ENTRY_FALLBACK_OVERLAY_INSERTED__" in MAIN
    assert "__BLOOM_ENTRY_FALLBACK_OVERLAY_PARENT__" in MAIN
    assert "__BLOOM_ENTRY_FALLBACK_OVERLAY_REMOVED__" in MAIN


def test_entry_fallback_overlay_uses_body_or_document_element_not_root() -> None:
    assert 'wrapper.id = "bloom-entry-fallback-overlay"' in MAIN
    assert "document.body.appendChild(wrapper)" in MAIN
    assert "document.documentElement.appendChild(wrapper)" in MAIN
    assert 'wrapper.id = "bloom-entry-fallback"' not in MAIN
    assert "rootElement.replaceChildren(wrapper)" not in MAIN
    assert "root.innerHTML" not in MAIN


def test_remove_entry_fallback_overlay_is_exported_but_not_called_after_render() -> None:
    assert "export function removeEntryFallbackOverlay()" in MAIN
    render_block = MAIN[MAIN.index("root.render(") : MAIN.index("console.info(\"app_after_render_call\")")]
    assert "removeEntryFallbackOverlay();" not in render_block


def test_app_removes_entry_fallback_overlay_after_mount() -> None:
    assert 'import { removeEntryFallbackOverlay } from "./main";' in APP
    mount_index = APP.index('lifecycleTrace("app_mount"')
    remove_index = APP.index("removeEntryFallbackOverlay();")
    assert mount_index < remove_index


def test_app_is_static_but_fallback_removal_still_waits_for_app_mount() -> None:
    static_app_index = MAIN.index('import App from "./App";')
    remove_export_index = MAIN.index("export function removeEntryFallbackOverlay()")
    app_calls_remove = APP.index("removeEntryFallbackOverlay();")
    assert static_app_index < remove_export_index
    assert app_calls_remove > 0
    assert "App.tsx removes the body overlay after the real App component mounts" in MAIN

INDEX = (ROOT / "index.html").read_text(encoding="utf-8")


def test_index_contains_html_startup_fallback_overlay() -> None:
    assert 'id="bloom-html-fallback-overlay"' in INDEX
    assert "Bloom Club загружается" in INDEX
    assert "Если экран не меняется больше 10 секунд, закройте и откройте приложение заново" in INDEX
    assert 'onclick="location.reload()"' in INDEX
    assert "Диагностика появится после запуска приложения" in INDEX


def test_html_fallback_precedes_entry_script() -> None:
    fallback_index = INDEX.index('id="bloom-html-fallback-overlay"')
    entry_script_index = INDEX.index('type="module" src="/src/main.tsx"')
    root_index = INDEX.index('id="root"')
    assert fallback_index < root_index < entry_script_index


def test_html_fallback_visible_without_js() -> None:
    fallback_index = INDEX.index('id="bloom-html-fallback-overlay"')
    fallback_block = INDEX[fallback_index : INDEX.index('</section>', fallback_index)]
    for token in [
        "position: fixed",
        "inset: 0",
        "z-index: 2147483646",
        "display: flex",
        "align-items: center",
        "justify-content: center",
        "background: #fff7fa",
        "color: #2b1b22",
        "font-family: -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
    ]:
        assert token in fallback_block
    assert "hidden" not in fallback_block
    assert "display: none" not in fallback_block


def test_remove_entry_fallback_overlay_removes_html_fallback() -> None:
    remove_block = MAIN[MAIN.index("export function removeEntryFallbackOverlay()") : MAIN.index("async function startApp()")]
    assert 'document.getElementById("bloom-entry-fallback-overlay")' in remove_block
    assert 'document.getElementById("bloom-html-fallback-overlay")' in remove_block
    assert "entryFallback?.remove();" in remove_block
    assert "htmlFallback?.remove();" in remove_block


def test_html_fallback_window_markers_exist() -> None:
    assert "__BLOOM_HTML_FALLBACK_PRESENT__" in INDEX
    assert "__BLOOM_HTML_FALLBACK_REMOVED__" in INDEX
    assert "__BLOOM_HTML_FALLBACK_PRESENT__" in MAIN
    assert "__BLOOM_HTML_FALLBACK_REMOVED__" in MAIN


def test_app_still_removes_fallback_only_after_mount_ready() -> None:
    mount_index = APP.index('lifecycleTrace("app_mount"')
    remove_index = APP.index("removeEntryFallbackOverlay();")
    assert mount_index < remove_index
    before_mount = APP[:mount_index]
    assert "removeEntryFallbackOverlay();" not in before_mount
