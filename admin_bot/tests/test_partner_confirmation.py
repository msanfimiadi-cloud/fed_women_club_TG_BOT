import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.base import StorageKey
from admin_bot import partner_confirmation as mod


def event(user=1, text=""):
    return SimpleNamespace(from_user=SimpleNamespace(id=user, full_name="Employee"),
        text=text, answer=AsyncMock(), delete=AsyncMock())


def state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(bot_id=1, chat_id=1, user_id=1))


def test_partner_pages_have_ten_items_and_navigation(monkeypatch):
    async def run():
        api = AsyncMock(return_value={"items": [{"id": i, "name": "Partner"} for i in range(10)], "total": 21})
        monkeypatch.setattr(mod, "api", api)
        message = event()
        await mod.page(message, None, 1)
        buttons = [b for row in message.answer.call_args.kwargs["reply_markup"].inline_keyboard for b in row]
        assert len([b for b in buttons if b.callback_data.startswith("pcab:choose:")]) == 10
        assert {b.callback_data for b in buttons} >= {"pcab:page:0", "pcab:page:2"}
    asyncio.run(run())


def test_non_admin_cannot_create_cabinet(monkeypatch):
    async def run():
        api = AsyncMock()
        monkeypatch.setattr(mod, "api", api)
        await mod.create(event(2), state(), SimpleNamespace(telegram_admin_ids={1}))
        api.assert_not_awaited()
    asyncio.run(run())


def test_login_member_and_confirmation(monkeypatch):
    async def run():
        api = AsyncMock(side_effect=[
            {"partner_name": "XFIT"},
            {"name": "Анна", "subscription_active": True, "offers": [{"id": 5, "title": "Карта"}], "used_today": 0},
            {"name": "Анна", "title": "Карта", "token": "a"*32, "used_today": 0},
            {"ok": True}])
        monkeypatch.setattr(mod, "api", api)
        s = state()
        message = event(text="SECRET123")
        await mod.login(message, s, None)
        message.delete.assert_awaited_once()
        await mod.start_confirmation(message, s)
        message.text = "000001"
        await mod.lookup(message, s, None)
        assert await s.get_state() == mod.Flow.select_offer.state
        callback = SimpleNamespace(from_user=message.from_user, message=message, data="pcab:offer:5", answer=AsyncMock())
        message.edit_reply_markup = AsyncMock()
        await mod.prepare(callback, s, None)
        assert await s.get_state() == mod.Flow.confirm.state
        callback.data = "pcab:confirm:" + "a"*32 + ":0"
        await mod.confirm(callback, s, None)
        assert await s.get_state() is None
        assert api.call_args.args[3]["allow_repeat"] is False
    asyncio.run(run())


def test_final_button_name_and_callback_size():
    for repeat in (True, False):
        button = mod.final_buttons("a"*32, repeat).inline_keyboard[0][0]
        assert button.text == "Подтвердить привилегию"
        assert len(button.callback_data.encode()) <= 64


def test_real_router_accepts_employee_in_private_chat(monkeypatch):
    from datetime import datetime, timezone
    from aiogram.types import Message, User, Chat
    async def run():
        answers = AsyncMock()
        monkeypatch.setattr(Message, "answer", answers)
        s = state()
        message = Message(message_id=1, date=datetime.now(timezone.utc),
            chat=Chat(id=1, type="private"), from_user=User(id=1, is_bot=False, first_name="Staff"),
            text=mod.ENTER)
        await mod.router.propagate_event(update_type="message", event=message,
            state=s, raw_state=None, settings=SimpleNamespace(telegram_admin_ids={99}))
        assert await s.get_state() == mod.Flow.login.state
        answers.assert_awaited_once()
    asyncio.run(run())


def test_real_router_does_not_request_codes_in_group(monkeypatch):
    from datetime import datetime, timezone
    from aiogram.types import Message, User, Chat
    async def run():
        answers = AsyncMock()
        monkeypatch.setattr(Message, "answer", answers)
        s = state()
        message = Message(message_id=1, date=datetime.now(timezone.utc),
            chat=Chat(id=-1, type="group"), from_user=User(id=1, is_bot=False, first_name="Staff"),
            text=mod.ENTER)
        await mod.router.propagate_event(update_type="message", event=message,
            state=s, raw_state=None, settings=SimpleNamespace(telegram_admin_ids={99}))
        assert await s.get_state() is None
        answers.assert_not_awaited()
    asyncio.run(run())


