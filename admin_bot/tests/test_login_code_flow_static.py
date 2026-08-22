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
    assert 'text == "/start" or text.startswith("/start ")' in bot
    assert "text in {PUBLIC_APP_BUTTON_TEXT, LEGACY_PUBLIC_APP_BUTTON_TEXT}" in bot
    assert "if is_public_onboarding_event(event):\n            return await handler(event, data)" in bot
    assert "if not is_admin_user(user, self._admin_ids):" in bot


def test_non_admin_start_gets_public_welcome_not_admin_menu():
    bot = read("admin_bot/bot.py")
    assert "def public_onboarding_keyboard" in bot
    assert "Добро пожаловать в Bloom Club" in bot
    assert "reply_markup=public_onboarding_keyboard()" in bot
    assert "if is_admin_user(message.from_user, settings.telegram_admin_ids):" in bot
    assert "Админ-бот Bloom Club. Выберите действие." in bot


def test_public_start_explains_trial_login_installation_and_social_channels():
    bot = read("admin_bot/bot.py")

    for marker in (
        "15 дней бесплатно",
        "Как войти в приложение",
        "код — он действует 5 минут",
        "привязан к этому Telegram-профилю",
        "Если вы выйдете из приложения",
        "Добавить на главный экран",
        "На экран “Домой”",
        "https://t.me/Wo_ClubNSK",
        "https://vk.ru/club238169934",
        "https://www.instagram.com/bloomclubnsk",
        "?igsi=M3lnaHp2d3J1YzJm&utm_source=qr",
    ):
        assert marker in bot

    assert "PUBLIC_SOCIAL_TEXT" in bot
    assert "public_social_keyboard()" in bot
    assert 'PUBLIC_APP_BUTTON_TEXT = "🔐 Получить код для входа"' in bot


def test_legacy_open_app_button_still_generates_login_code():
    bot = read("admin_bot/bot.py")

    assert 'LEGACY_PUBLIC_APP_BUTTON_TEXT = "🌐 Открыть приложение"' in bot
    assert "F.text.in_({PUBLIC_APP_BUTTON_TEXT, LEGACY_PUBLIC_APP_BUTTON_TEXT})" in bot


def test_public_onboarding_and_login_code_use_one_message_each():
    bot = read("admin_bot/bot.py")

    assert "PUBLIC_ONBOARDING_TEXT = (" in bot
    assert "f\"{PUBLIC_WELCOME_TEXT}\\n\\n\"" in bot
    assert "f\"{PUBLIC_LOGIN_GUIDE_TEXT}\\n\\n\"" in bot
    assert "await message.answer(PUBLIC_WELCOME_TEXT)" not in bot
    assert "await message.answer(result.login_code)" not in bot
    assert "f\"<code>{escape(result.login_code)}</code>\\n\\n\"" in bot


def test_public_messages_and_notifications_have_rate_limits_and_retries():
    bot = read("admin_bot/bot.py")
    client = read("admin_bot/login_code.py")

    assert "TelegramRetryAfter" in bot
    assert "TelegramNetworkError" in bot
    assert "messages_per_second=15" in bot
    assert "messages_per_second=10" in bot
    assert "send_at + 1.05" in bot
    assert "background=True" in bot
    assert "max_connections=20" in client
    assert "timeout=httpx.Timeout(15.0, connect=5.0)" in client
