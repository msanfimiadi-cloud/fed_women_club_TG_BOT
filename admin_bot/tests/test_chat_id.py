from types import SimpleNamespace

import pytest
from aiogram.enums import ChatType

from admin_bot.bot import channel_chat_id, format_chat_id_message


def test_format_chat_id_message_for_supergroup() -> None:
    result = format_chat_id_message(-1001234567890, "Bloom Club НСК", ChatType.SUPERGROUP)

    assert "<code>-1001234567890</code>" in result
    assert "Bloom Club НСК" in result
    assert "<code>supergroup</code>" in result
    assert "включая знак минус" in result


def test_format_chat_id_message_escapes_group_title() -> None:
    result = format_chat_id_message(-100123, "Bloom <Club>", ChatType.GROUP)

    assert "Bloom &lt;Club&gt;" in result


@pytest.mark.asyncio
async def test_channel_chat_id_is_sent_privately_to_configured_admins() -> None:
    sent: list[tuple[int, str]] = []

    class FakeBot:
        async def send_message(self, chat_id: int, text: str) -> None:
            sent.append((chat_id, text))

    message = SimpleNamespace(
        chat=SimpleNamespace(id=-1009876543210, title="Bloom Club НСК", type=ChatType.CHANNEL)
    )
    settings = SimpleNamespace(telegram_admin_ids=frozenset({123, 456}))

    await channel_chat_id(message, FakeBot(), settings)

    assert {chat_id for chat_id, _ in sent} == {123, 456}
    assert all("<code>-1009876543210</code>" in text for _, text in sent)
