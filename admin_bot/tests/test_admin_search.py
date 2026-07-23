import asyncio

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from admin_bot.bot import filter_search_results, search_matches
from admin_bot.keyboards import banners_keyboard, partners_keyboard
from admin_bot.states import AdminSearch


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_search_is_case_insensitive():
    items = [{"name": "Bloom Spa"}, {"name": "Coffee"}]
    assert filter_search_results(items, "bLOOm", "partners") == [items[0]]


def test_search_matches_partial_string():
    item = {"title": "Летний баннер", "subtitle": "Главная"}
    assert search_matches(item, "бан", ("title", "subtitle"))


def test_search_no_results():
    assert filter_search_results([{"title": "A"}], "missing", "banners") == []


def test_search_reset_callbacks_present_and_safe():
    callbacks = _callbacks(partners_keyboard([{"id": 1, "name": "A"}]))
    assert "search:start:partners" in callbacks
    assert "search:reset:partners" in callbacks
    assert all(len(item.encode()) <= 64 for item in callbacks)


def test_search_callbacks_have_no_duplicates():
    callbacks = _callbacks(banners_keyboard([{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]))
    assert len(callbacks) == len(set(callbacks))


def test_search_fsm_state_can_be_cleared():
    async def run():
        storage = MemoryStorage()
        context = FSMContext(storage=storage, key=StorageKey(bot_id=1, chat_id=1, user_id=1))
        await context.set_state(AdminSearch.query)
        assert await context.get_state() == AdminSearch.query.state
        await context.clear()
        assert await context.get_state() is None
    asyncio.run(run())
