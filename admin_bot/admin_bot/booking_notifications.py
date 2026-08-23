from __future__ import annotations

import re
from typing import Any

import httpx


BOOKING_LINK_PATTERN = re.compile(r"^/start(?:@[A-Za-z0-9_]+)?\s+bloomonline_([a-f0-9]{48})$")


class BookingNotificationError(RuntimeError):
    pass


def booking_link_token(text: str | None) -> str | None:
    match = BOOKING_LINK_PATTERN.fullmatch((text or "").strip())
    return match.group(1) if match else None


async def connect_booking_notifications(
    *,
    public_url: str,
    bot_token: str,
    link_token: str,
    chat_id: int,
    telegram_user_id: int,
    username: str | None,
    display_name: str | None,
) -> str:
    if not public_url.startswith("https://"):
        raise BookingNotificationError("Адрес Bloom Online настроен некорректно.")
    if chat_id <= 0 or chat_id != telegram_user_id:
        raise BookingNotificationError("Подключение доступно только в личном диалоге с ботом.")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{public_url.rstrip('/')}/api/telegram/link",
                headers={"Authorization": f"Bearer {bot_token}"},
                json={
                    "token": link_token,
                    "chatId": str(chat_id),
                    "telegramUserId": str(telegram_user_id),
                    "username": username,
                    "displayName": display_name,
                },
            )
    except httpx.HTTPError as exc:
        raise BookingNotificationError("Bloom Online временно недоступен. Попробуйте ещё раз.") from exc

    try:
        data: dict[str, Any] = response.json()
    except ValueError as exc:
        raise BookingNotificationError("Bloom Online вернул некорректный ответ.") from exc

    if response.status_code >= 400 or not data.get("success"):
        raise BookingNotificationError(str(data.get("error") or "Не удалось подключить уведомления."))
    return str(data.get("organizationName") or "вашего партнёра")
