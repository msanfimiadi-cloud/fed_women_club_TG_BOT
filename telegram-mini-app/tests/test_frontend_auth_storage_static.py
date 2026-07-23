from pathlib import Path

CLIENT = Path(__file__).resolve().parents[1] / "src" / "api" / "client.ts"


def test_auth_token_not_persisted_to_local_storage_by_default() -> None:
    source = CLIENT.read_text()

    assert 'const AUTH_SESSION_STORAGE_KEY = "bloom_club_tma_auth_session"' in source
    assert 'window.sessionStorage.setItem(\n    AUTH_SESSION_STORAGE_KEY' in source
    assert 'window.localStorage.setItem(AUTH_STORAGE_KEY, token)' not in source
    assert 'window.localStorage.removeItem(AUTH_STORAGE_KEY)' in source


def test_auth_session_has_short_ttl_and_legacy_flag_gate() -> None:
    source = CLIENT.read_text()

    assert 'const AUTH_SESSION_TTL_MS = 30 * 60 * 1000' in source
    assert 'const AUTH_SESSION_MAX_TTL_MS = 60 * 60 * 1000' in source
    assert 'VITE_AUTH_STORAGE_MODE === "legacy_local_storage"' in source
    assert 'AUTH_LEGACY_LOCAL_STORAGE_ENABLED && typeof window !== "undefined"' in source
