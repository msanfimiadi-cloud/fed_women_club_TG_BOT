import asyncio
from types import SimpleNamespace

import httpx

from admin_bot.booking_notifications import (
    BookingNotificationError,
    booking_link_token,
    connect_booking_notifications,
    connect_customer_booking_notifications,
    customer_booking_link_token,
)


def test_booking_link_token_accepts_only_signed_start_payload() -> None:
    token = "a" * 48
    assert booking_link_token(f"/start bloomonline_{token}") == token
    assert booking_link_token(f"/start@BloomBot bloomonline_{token}") == token
    assert booking_link_token("/start") is None
    assert booking_link_token("/start bloomonline_invalid") is None
    assert customer_booking_link_token(f"/start bloombooking_{token}") == token
    assert customer_booking_link_token(f"/start@BloomBot bloombooking_{token}") == token
    assert customer_booking_link_token(f"/start bloomonline_{token}") is None


def test_booking_link_rejects_group_or_mismatched_telegram_identity() -> None:
    async def run() -> None:
        try:
            await connect_booking_notifications(
                public_url="https://online.example.ru",
                bot_token="secret",
                link_token="a" * 48,
                chat_id=-100123,
                telegram_user_id=123,
                username=None,
                display_name=None,
            )
        except BookingNotificationError as exc:
            assert "личном диалоге" in str(exc)
        else:
            raise AssertionError("Group chat must be rejected")

    asyncio.run(run())


def test_booking_link_posts_personal_chat_to_authenticated_api(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url: str, *, headers: dict, json: dict):
            calls.append(SimpleNamespace(url=url, headers=headers, json=json))
            return httpx.Response(200, json={"success": True, "organizationName": "Luna Studio"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(
        connect_booking_notifications(
            public_url="https://online.example.ru",
            bot_token="bot-secret",
            link_token="a" * 48,
            chat_id=123456,
            telegram_user_id=123456,
            username="partner",
            display_name="Anna",
        )
    )

    assert result == "Luna Studio"
    assert calls[0].url == "https://online.example.ru/api/telegram/link"
    assert calls[0].headers["Authorization"] == "Bearer bot-secret"
    assert calls[0].json["chatId"] == "123456"


def test_customer_booking_link_posts_to_customer_endpoint(monkeypatch) -> None:
    calls = []

    class FakeClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        async def post(self, url: str, *, headers: dict, json: dict):
            calls.append(SimpleNamespace(url=url, headers=headers, json=json))
            return httpx.Response(200, json={"success": True, "appointment": {"organizationName": "Luna", "serviceName": "Маникюр"}})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(connect_customer_booking_notifications(public_url="https://online.example.ru", bot_token="bot-secret", link_token="b" * 48, chat_id=123456, telegram_user_id=123456))
    assert result["organizationName"] == "Luna"
    assert calls[0].url == "https://online.example.ru/api/telegram/customer-link"
    assert calls[0].headers["Authorization"] == "Bearer bot-secret"
    assert calls[0].json == {"token": "b" * 48, "chatId": "123456"}
