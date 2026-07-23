import asyncio
import json

import httpx
import pytest

from admin_bot.login_code import LoginCodeClient, LoginCodeError, LoginCodeIdentity


def test_create_telegram_login_code_payload_and_response():
    async def run():
        seen = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["path"] = request.url.path
            seen["auth"] = request.headers.get("Authorization")
            seen["payload"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"login_code": "BC-7K4P9Q", "expires_in": 300})

        client = LoginCodeClient("https://api.test/api/v1", "service-token")
        client._client = httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://api.test/api/v1",
            headers={"Authorization": "Bearer service-token"},
        )
        try:
            result = await client.create_login_code(
                LoginCodeIdentity(
                    provider="telegram",
                    provider_user_id="123",
                    first_name="Ada",
                    last_name="Lovelace",
                    username="ada",
                    source="telegram_bot",
                )
            )
        finally:
            await client.close()

        assert seen == {
            "method": "POST",
            "path": "/api/v1/internal/login-code",
            "auth": "Bearer service-token",
            "payload": {
                "provider": "telegram",
                "provider_user_id": "123",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "username": "ada",
                "source": "telegram_bot",
            },
        }
        assert result.login_code == "BC-7K4P9Q"
        assert result.expires_in == 300

    asyncio.run(run())


def test_same_user_second_code_supersedes_first_on_backend_contract():
    async def run():
        active_codes = {}
        generated = iter(["BC-AAAAAA", "BC-BBBBBB"])

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode())
            key = (payload["provider"], payload["provider_user_id"])
            code = next(generated)
            active_codes[key] = code
            return httpx.Response(200, json={"login_code": code, "expires_in": 300})

        client = LoginCodeClient("https://api.test/api/v1", "service-token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test/api/v1")
        try:
            identity = LoginCodeIdentity(provider="telegram", provider_user_id="123", source="telegram_bot")
            first = await client.create_login_code(identity)
            second = await client.create_login_code(identity)
        finally:
            await client.close()

        assert first.login_code == "BC-AAAAAA"
        assert second.login_code == "BC-BBBBBB"
        assert active_codes[("telegram", "123")] == second.login_code
        assert active_codes[("telegram", "123")] != first.login_code

    asyncio.run(run())


def test_different_users_receive_different_codes():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode())
            return httpx.Response(200, json={"login_code": f"BC-USER{payload['provider_user_id']}", "expires_in": 300})

        client = LoginCodeClient("https://api.test/api/v1", "service-token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test/api/v1")
        try:
            first = await client.create_login_code(LoginCodeIdentity(provider="telegram", provider_user_id="1"))
            second = await client.create_login_code(LoginCodeIdentity(provider="telegram", provider_user_id="2"))
        finally:
            await client.close()

        assert first.login_code != second.login_code

    asyncio.run(run())


@pytest.mark.parametrize("status_code", [500, 503])
def test_backend_unavailable_raises_required_error(status_code):
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status_code, json={"detail": "do not leak auth response"})

        client = LoginCodeClient("https://api.test/api/v1", "service-token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://api.test/api/v1")
        try:
            with pytest.raises(LoginCodeError, match="Не удалось получить код входа"):
                await client.create_login_code(LoginCodeIdentity(provider="telegram", provider_user_id="123"))
        finally:
            await client.close()

    asyncio.run(run())


def test_public_app_button_sends_copyable_login_code_messages(monkeypatch):
    async def run():
        from types import SimpleNamespace

        from admin_bot import bot as bot_module
        from admin_bot.login_code import LoginCodeResult

        class FakeLoginCodeClient:
            async def create_login_code(self, identity):
                assert identity.provider == "telegram"
                assert identity.provider_user_id == "123"
                assert identity.source == "telegram_bot"
                return LoginCodeResult(login_code="BC-XXXXXX", expires_in=300)

        class FakeMessage:
            def __init__(self):
                self.from_user = SimpleNamespace(
                    id=123,
                    first_name="Public",
                    last_name="User",
                    username="public_user",
                )
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        monkeypatch.setattr(bot_module, "get_login_code_client", lambda: FakeLoginCodeClient())
        message = FakeMessage()

        await bot_module.open_browser_app(message)

        assert [text for text, _ in message.answers] == [
            "🔐 Ваш код входа:",
            "BC-XXXXXX",
            "Код действует 5 минут.\nНажмите кнопку ниже, чтобы открыть приложение.",
        ]
        raw_code_text, raw_code_markup = message.answers[1]
        assert raw_code_text == "BC-XXXXXX"
        assert raw_code_text.strip() == raw_code_text
        assert raw_code_markup is None

        app_message_text, app_message_markup = message.answers[2]
        assert "/login?t=" not in "\n".join(text for text, _ in message.answers)
        assert "login?" not in "\n".join(text for text, _ in message.answers)
        assert app_message_text.startswith("Код действует 5 минут.")
        button = app_message_markup.inline_keyboard[0][0]
        assert button.text == "🌐 Открыть приложение"
        assert str(button.url) == "https://app.bloomclub.ru"

    asyncio.run(run())
