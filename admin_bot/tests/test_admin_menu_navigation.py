import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, Message, MessageEntity, User

from admin_bot import bot as bot_module
from admin_bot.states import PartnerAccessGrant, AdvertiserCreate


@pytest.mark.parametrize("initial_state", [PartnerAccessGrant.telegram_user_id, AdvertiserCreate.telegram_user_id, AdvertiserCreate.name])
@pytest.mark.parametrize("text,reply", [
    ("❌ Отмена", "Действие отменено."),
    ("/cancel", "Действие отменено."),
    ("🖼 Баннеры", "Управление баннерами."),
    ("📚 Справочники", "📚 Справочники Content CMS"),
])
def test_real_router_exits_form_for_navigation(initial_state, text, reply, monkeypatch):
    async def run():
        answers = AsyncMock()
        monkeypatch.setattr(Message, "answer", answers)
        storage = MemoryStorage()
        state = FSMContext(storage=storage, key=StorageKey(bot_id=123, chat_id=1, user_id=1))
        await state.set_state(initial_state)
        await state.update_data(draft="unfinished")
        bot = Bot("123:TEST")
        message = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=1, type="private"),
                          from_user=User(id=1, is_bot=False, first_name="Admin"), text=text,
                          entities=[MessageEntity(type="bot_command", offset=0, length=7)] if text == "/cancel" else None)
        try:
            await bot_module.router.propagate_event(
                update_type="message", event=message, state=state,
                raw_state=await state.get_state(), settings=SimpleNamespace(telegram_admin_ids={1}), bot=bot)
            answers.assert_awaited_once()
            assert answers.call_args.args[0] == reply
            assert await state.get_state() is None
            assert await state.get_data() == {}
        finally:
            await bot.session.close()
            await storage.close()
    asyncio.run(run())


@pytest.mark.parametrize("user_id,text", [(1, "123456"), (1, "ошибка"), (2, "❌ Отмена")])
def test_other_input_and_non_admin_state_are_untouched(user_id, text):
    async def run():
        state = AsyncMock()
        handler = AsyncMock()
        event = Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=user_id, type="private"),
                        from_user=User(id=user_id, is_bot=False, first_name="User"), text=text)
        data = {"state": state, "raw_state": "original", "settings": SimpleNamespace(telegram_admin_ids={1})}
        await bot_module.AdminMenuNavigationMiddleware()(handler, event, data)
        state.clear.assert_not_awaited()
        assert data["raw_state"] == "original"
        handler.assert_awaited_once_with(event, data)
    asyncio.run(run())
