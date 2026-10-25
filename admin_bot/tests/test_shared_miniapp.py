from admin_bot import bot


def test_miniapp_uses_same_url_as_website(monkeypatch):
    monkeypatch.setattr(bot, "_browser_app_public_url", "https://app.bloomclub.ru")
    keyboard = bot.public_onboarding_keyboard()
    launch = keyboard.keyboard[0][0]
    assert launch.text == "🌸 Открыть в Telegram"
    assert launch.web_app.url == "https://app.bloomclub.ru"
    assert keyboard.keyboard[1][0].text == bot.PUBLIC_APP_BUTTON_TEXT
    assert keyboard.keyboard[1][0].web_app is None


def test_advertiser_retains_stats_with_miniapp_entry():
    keyboard = bot.public_onboarding_keyboard(advertiser=True)
    assert keyboard.keyboard[0][0].web_app is not None
    assert keyboard.keyboard[-1][0].text == bot.ADVERTISER_STATS_BUTTON_TEXT
