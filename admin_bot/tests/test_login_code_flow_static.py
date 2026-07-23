from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def test_bot_opens_browser_app_without_parameters():
    bot = read("admin_bot/bot.py")
    assert '_browser_app_public_url = "https://app.bloomclub.ru"' in bot
    assert "url=_browser_app_public_url" in bot
    assert "/login?t=" not in bot
    assert "login?" not in bot


def test_no_browser_login_token_generation_remains_in_telegram_bot():
    combined = "\n".join(path.read_text() for path in (ROOT / "admin_bot").glob("*.py"))
    assert "browser-login-token" not in combined
    assert "BrowserLoginClient" not in combined
    assert "create_token" not in combined


def test_public_onboarding_bypasses_admin_only_middleware():
    bot = read("admin_bot/bot.py")
    assert "def is_public_onboarding_event" in bot
    assert 'text in {"/start", PUBLIC_APP_BUTTON_TEXT}' in bot
    assert "if is_public_onboarding_event(event):\n            return await handler(event, data)" in bot
    assert "if not is_admin_user(user, self._admin_ids):" in bot


def test_non_admin_start_gets_public_welcome_not_admin_menu():
    bot = read("admin_bot/bot.py")
    assert "def public_onboarding_keyboard" in bot
    assert "Добро пожаловать в Bloom Club" in bot
    assert "reply_markup=public_onboarding_keyboard()" in bot
    assert "if is_admin_user(message.from_user, settings.telegram_admin_ids):" in bot
    assert "Админ-бот Bloom Club. Выберите действие." in bot
