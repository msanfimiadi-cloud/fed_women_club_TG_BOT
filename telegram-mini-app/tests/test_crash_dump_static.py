from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRASH = (ROOT / "src/diagnostics/crashDump.ts").read_text(encoding="utf-8")
PROD = (ROOT / "src/diagnostics/productionDebug.ts").read_text(encoding="utf-8")
APP = (ROOT / "src/App.tsx").read_text(encoding="utf-8")
BOUNDARY = (ROOT / "src/components/RuntimeErrorBoundary.tsx").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.tsx").read_text(encoding="utf-8")
BUILD = (ROOT / "src/buildInfo.ts").read_text(encoding="utf-8")


def test_crash_dump_saves_to_local_storage() -> None:
    assert "BLOOM_LAST_CRASH_DUMP" in CRASH
    assert "setItem(BLOOM_LAST_CRASH_DUMP_KEY" in CRASH
    assert "saveCrashDump" in PROD
    assert "saveCrashDump" in MAIN
    assert "saveCrashDump" in BOUNDARY


def test_crash_dump_restores_without_auto_opening_overlay() -> None:
    assert "readCompatibleCrashDump" in APP
    assert "previousCrashDump" in APP
    assert "Обнаружена диагностика предыдущего неудачного запуска" in APP
    assert "Открыть диагностику" in APP
    assert "Очистить" in APP
    assert "useState<BloomCrashDump | null>(() => readCompatibleCrashDump())" in APP


def test_crash_dump_clears_after_successful_startup() -> None:
    assert "startup_completed_successfully" in APP
    assert "markStartupCompletedSuccessfully" in APP
    assert "removeItem(BLOOM_LAST_CRASH_DUMP_KEY)" in CRASH


def test_crash_dump_clears_after_build_hash_change() -> None:
    assert "buildHash" in BUILD
    assert "parsed?.buildHash !== currentBuildHash()" in CRASH
    assert "removeItem(BLOOM_LAST_CRASH_DUMP_KEY)" in CRASH


def test_crash_dump_redacts_secrets_but_keeps_build_hash() -> None:
    for marker in ["authorization", "initdata", "init_data", "access_token", "token", "cookie", "secret", "password"]:
        assert marker in CRASH.lower()
    assert "buildHash: currentBuildHash()" in CRASH
    assert "hasToken: false" in CRASH


def test_startup_completed_successfully_deletes_dump() -> None:
    assert "export function markStartupCompletedSuccessfully" in CRASH
    assert "clearCrashDump(\"startup_completed_successfully\")" in CRASH
    assert "traceOk(\"startup_completed_successfully\"" in APP
