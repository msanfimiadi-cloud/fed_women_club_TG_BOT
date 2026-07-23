import asyncio
import json

import httpx
import pytest

from admin_bot.bot import (
    INVALID_DATE_MESSAGE,
    format_giveaway,
    format_giveaway_item,
    format_giveaway_item_summary,
    giveaway_payload,
    giveaway_update_payload,
    parse_admin_date,
)
from admin_bot.keyboards import giveaway_actions_keyboard, giveaway_item_actions_keyboard, giveaways_keyboard
from admin_bot.web_api import ContentAdminApiClient, WebApiError


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_giveaways_list_keyboard_unique_and_safe_callbacks():
    callbacks = _callbacks(giveaways_keyboard([{"id": 1, "title": "A"}, {"id": 2, "title": "B"}]))
    assert "giveaway:add" in callbacks
    assert len(callbacks) == len(set(callbacks))
    assert all(len(item.encode()) <= 64 for item in callbacks)


def test_giveaway_card_contains_production_fields():
    text = format_giveaway({"id": 1, "title": "Лето", "description": "desc", "terms": "terms", "starts_at": "2026-07-01T10:00", "ends_at": "2026-07-31T10:00", "is_active": True, "photo_url": "https://cdn/x.jpg", "items": [{"id": 1}], "sort_order": 3})
    assert "Название: Лето" in text
    assert "Условия участия: terms" in text
    assert "Количество призов: 1" in text
    assert "Порядок отображения: 3" in text


@pytest.mark.parametrize("value", ["28.06.2026", "28.06.2026 14:30"])
def test_create_giveaway_date_format(value):
    assert parse_admin_date(value).startswith("2026-06-28")


def test_invalid_date_format_message():
    assert parse_admin_date("2026-06-28") is None
    assert INVALID_DATE_MESSAGE == "Введите дату в формате ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ."


def test_create_and_edit_giveaway_payloads():
    payload = giveaway_payload({"title": "T", "description": "D", "terms": "U", "starts_at": "2026-06-28T10:00", "ends_at": "2026-06-29T10:00"}, "https://cdn/g.jpg")
    assert payload["title"] == payload["name"] == "T"
    assert payload["terms"] == payload["conditions"] == "U"
    assert payload["photo_url"] == payload["image_url"] == payload["url"]
    assert giveaway_update_payload("sort_order", 10) == {"sort_order": 10}
    assert giveaway_update_payload("is_active", False) == {"is_active": False}


def test_giveaway_photo_show_hide_delete_keyboard_callbacks():
    callbacks = _callbacks(giveaway_actions_keyboard(123, True))
    assert f"giveaway:photo:menu:123" in callbacks
    assert f"giveaway:toggle:123:0" in callbacks
    assert f"giveaway:delete:confirm:123" in callbacks
    assert len(callbacks) == len(set(callbacks))


def test_prize_card_and_summary_contains_required_fields():
    item = {"id": 7, "title": "Prize", "description": "Desc", "is_active": False, "sort_order": 2}
    text = format_giveaway_item(item)
    summary = format_giveaway_item_summary(item)
    assert "Название: Prize" in text
    assert "Фото: Фото отсутствует." in text
    assert "нет фото" in summary


def test_prize_actions_keyboard_callbacks_unique_and_safe():
    callbacks = _callbacks(giveaway_item_actions_keyboard(1, 2, False))
    assert "giveaway:item:toggle:1:2:1" in callbacks
    assert "giveaway:item:delete:confirm:1:2" in callbacks
    assert len(callbacks) == len(set(callbacks))
    assert all(len(item.encode()) <= 64 for item in callbacks)


def test_giveaway_api_create_update_photo_delete_and_friendly_errors():
    async def run():
        calls = []
        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.url.path.endswith("/missing"):
                return httpx.Response(404, json={"detail": "missing"})
            if request.url.path.endswith("/conflict"):
                return httpx.Response(409, json={"detail": "conflict"})
            return httpx.Response(200, json={"data": {"id": 1, **(payload or {})}})
        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_giveaway({"title": "G"}) == {"id": 1, "title": "G"}
            updated = await client.update_giveaway(1, {"sort_order": 5})
            assert updated["sort_order"] == 5
            assert await client.add_giveaway_photo(1, "https://cdn/g.jpg") == {"id": 1, "url": "https://cdn/g.jpg", "image_url": "https://cdn/g.jpg", "photo_url": "https://cdn/g.jpg"}
            await client.delete_giveaway_photo("missing")
            with pytest.raises(WebApiError, match="409: Конфликт данных"):
                await client.update_giveaway("conflict", {"title": "X"})
        finally:
            await client.close()
        assert ("DELETE", "/api/content/admin/giveaway-photos/missing", None) in calls
    asyncio.run(run())


def test_delete_giveaway_deletes_children_and_treats_404_as_success():
    async def run():
        calls = []
        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path.endswith("/photos"):
                return httpx.Response(200, json={"photos": [{"id": 8}]})
            if request.url.path.endswith("/items"):
                return httpx.Response(200, json={"items": [{"id": 9}]})
            return httpx.Response(404, json={"detail": "gone"})
        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            await client.delete_giveaway(1)
        finally:
            await client.close()
        assert ("DELETE", "/api/content/admin/giveaways/1") in calls
        assert ("DELETE", "/api/content/admin/giveaway-items/9") in calls
    asyncio.run(run())
