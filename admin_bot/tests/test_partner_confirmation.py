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
            {"name": "Анна", "subscription_active": True, "title": "Карта", "token": "a"*43, "used_today": 0},
            {"ok": True}])
        monkeypatch.setattr(mod, "api", api)
        s = state()
        message = event(text="SECRET123")
        await mod.login(message, s, None)
        message.delete.assert_awaited_once()
        await mod.start_confirmation(message, s)
        message.text = "000001"
        await mod.lookup(message, s, None)
        assert api.call_args.args[2] == "/coupon"
        assert api.call_args.args[3]["code"] == "000001"
        callback = SimpleNamespace(from_user=message.from_user, message=message, data="", answer=AsyncMock())
        message.edit_reply_markup = AsyncMock()
        assert await s.get_state() == mod.Flow.confirm.state
        callback.data = "pcab:confirm:" + "a"*43 + ":0"
        await mod.confirm(callback, s, None)
        assert await s.get_state() is None
        assert api.call_args.args[3]["allow_repeat"] is False
        assert api.call_args.args[2] == "/coupon/confirm"
    asyncio.run(run())


def test_final_button_name_and_callback_size():
    for repeat in (True, False):
        button = mod.final_buttons("a"*32, repeat).inline_keyboard[0][0]
        assert button.text == "Подтвердить привилегию"
        assert len(button.callback_data.encode()) <= 64


def test_variable_coupon_requires_staff_amount(monkeypatch):
    async def run():
        api = AsyncMock(return_value={'token': 'a'*32, 'name': 'Анна', 'title': 'Карта',
            'subscription_active': True, 'used_today': 0, 'requires_order_amount': True, 'amount_revision': 0})
        monkeypatch.setattr(mod, 'api', api)
        s = state()
        message = event(text='001234')
        await mod.lookup(message, s, None)
        assert await s.get_state() == mod.Flow.amount.state
        assert 'БЕЗ учёта скидки' in message.answer.call_args.args[0]
        message.text = '-1'
        await mod.submit_amount(message, s, None)
        assert api.await_count == 1
        api.return_value = {'token': 'a'*32, 'name': 'Анна', 'title': 'Карта', 'used_today': 0,
            'amount_revision': 1, 'amount_review_status': 'matched', 'base_price': '10000', 'final_price': '9000', 'saving_amount': '1000'}
        message.text = '10 000,00'
        await mod.submit_amount(message, s, None)
        assert api.call_args.args[2] == '/coupon/amount'
        assert api.call_args.args[3]['order_amount'] == '10000.00'
        buttons = message.answer.call_args.kwargs['reply_markup'].inline_keyboard
        assert buttons[0][0].callback_data.endswith(':0:1')
        assert await s.get_state() == mod.Flow.confirm.state
    asyncio.run(run())


def test_pending_amount_has_no_confirm_button():
    async def run():
        s = state()
        message = event()
        await mod.show_amount_result(message, s, {'token': 'a'*32, 'used_today': 0, 'amount_revision': 2,
            'amount_review_status': 'pending', 'base_price': '100000', 'partner_order_amount': '10000'})
        buttons = [b.text for row in message.answer.call_args.kwargs['reply_markup'].inline_keyboard for b in row]
        assert mod.CONFIRM not in buttons
        assert 'Сумма отличается' in message.answer.call_args.args[0]
        assert 'Исправить сумму' in buttons
    asyncio.run(run())


def test_waiter_notifies_employee_after_customer_accepts(monkeypatch):
    async def run():
        token = 'a'*32
        s = state()
        await s.update_data(token=token, amount_revision=2)
        await s.set_state(mod.Flow.confirm)
        message = event()
        monkeypatch.setattr(mod.asyncio, 'sleep', AsyncMock())
        monkeypatch.setattr(mod, 'api', AsyncMock(return_value={
            'token': token, 'amount_revision': 2, 'amount_review_status': 'accepted', 'used_today': 0,
            'name': 'Анна', 'title': 'Карта', 'base_price': '10000', 'final_price': '9000', 'saving_amount': '1000'}))
        await mod.wait_for_amount(message, s, None, token, 2)
        assert 'Сумма согласована' in message.answer.call_args.args[0]
        assert '9 000,00 ₽' in message.answer.call_args.args[0]
        assert message.answer.call_args.kwargs['reply_markup'].inline_keyboard[0][0].callback_data.endswith(':0:2')
    asyncio.run(run())


def test_coupon_summary_prices_and_customer_warning():
    summary = mod.coupon_summary({'name': 'Анна <тест>', 'title': 'Карта', 'code': '001234',
        'base_price': '10000.00', 'final_price': '8300.00', 'saving_amount': '1700.00',
        'requires_order_amount': True})
    assert '10 000,00 ₽' in summary
    assert '8 300,00 ₽' in summary
    assert '1 700,00 ₽' in summary
    assert '001234' in summary
    assert 'сумму заказа указывает клиент' in summary
    assert '&lt;тест&gt;' in summary
    assert mod.money('0') == '0,00 ₽'
    assert mod.money(None) == 'не указана'
    assert mod.money('NaN') == 'не указана'
    gift = mod.coupon_summary({'name': 'Анна', 'title': 'Подвеска', 'is_gift': True})
    assert 'подарок' in gift and '₽' not in gift


def test_cancel_confirmation_does_not_confirm_coupon(monkeypatch):
    async def run():
        api = AsyncMock()
        monkeypatch.setattr(mod, 'api', api)
        s = state()
        await s.set_state(mod.Flow.confirm)
        message = event()
        message.edit_reply_markup = AsyncMock()
        callback = SimpleNamespace(message=message, answer=AsyncMock())
        await mod.cancel_confirmation(callback, s)
        assert await s.get_state() is None
        api.assert_not_awaited()
    asyncio.run(run())


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


