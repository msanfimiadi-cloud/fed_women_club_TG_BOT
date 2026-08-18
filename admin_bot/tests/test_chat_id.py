from aiogram.enums import ChatType

from admin_bot.bot import format_chat_id_message


def test_format_chat_id_message_for_supergroup() -> None:
    result = format_chat_id_message(-1001234567890, "Bloom Club НСК", ChatType.SUPERGROUP)

    assert "<code>-1001234567890</code>" in result
    assert "Bloom Club НСК" in result
    assert "<code>supergroup</code>" in result
    assert "включая знак минус" in result


def test_format_chat_id_message_escapes_group_title() -> None:
    result = format_chat_id_message(-100123, "Bloom <Club>", ChatType.GROUP)

    assert "Bloom &lt;Club&gt;" in result
