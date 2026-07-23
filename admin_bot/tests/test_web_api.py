import asyncio
import json
from pathlib import Path

import httpx
import pytest

from admin_bot.web_api import ContentAdminApiClient, WebApiError, _as_dict, _as_list


def test_as_list_accepts_giveaways_key():
    assert _as_list({"giveaways": [{"id": 1}, "bad", {"id": 2}]}) == [{"id": 1}, {"id": 2}]


def test_as_list_accepts_giveaway_items_key():
    assert _as_list({"giveaway_items": [{"id": 1}, "bad", {"id": 2}]}) == [{"id": 1}, {"id": 2}]


def test_as_dict_unwraps_data():
    assert _as_dict({"data": {"id": 10, "title": "Test"}}) == {"id": 10, "title": "Test"}


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ([{"id": 1}], [{"id": 1}]),
        ({"items": [{"id": 2}]}, [{"id": 2}]),
        ({"giveaway_items": [{"id": 3}]}, [{"id": 3}]),
        ({"results": [{"id": 4}]}, [{"id": 4}]),
    ],
)
def test_list_giveaway_items_normalizes_response_variants(body, expected):
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/content/admin/giveaways/10/items"
            return httpx.Response(200, json=body)

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_giveaway_items(10) == expected
        finally:
            await client.close()

    asyncio.run(run())


def test_create_update_hide_giveaway_item_methods():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "POST":
                return httpx.Response(200, json={"id": 7, **payload})
            return httpx.Response(200, json={"data": {"id": 7, **payload}})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_giveaway_item(10, {"title": "Prize"}) == {"id": 7, "title": "Prize"}
            assert await client.update_giveaway_item(7, {"sort_order": 2}) == {"id": 7, "sort_order": 2}
            assert await client.hide_giveaway_item(7) == {"id": 7, "is_active": False}
        finally:
            await client.close()

        assert calls == [
            ("POST", "/api/content/admin/giveaways/10/items", {"title": "Prize"}),
            ("PATCH", "/api/content/admin/giveaway-items/7", {"sort_order": 2}),
            ("PATCH", "/api/content/admin/giveaway-items/7", {"is_active": False}),
        ]

    asyncio.run(run())


def test_upload_then_patch_giveaway_item_image_url(tmp_path: Path):
    async def run():
        image = tmp_path / "prize.jpg"
        image.write_bytes(b"fake-image")
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path == "/api/content/uploads":
                return httpx.Response(200, json={"url": "https://cdn.test/prize.jpg"})
            assert json.loads(request.content.decode()) == {"image_url": "https://cdn.test/prize.jpg"}
            return httpx.Response(200, json={"id": 7, "image_url": "https://cdn.test/prize.jpg"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            url = await client.upload_file(image, "image/jpeg")
            assert await client.update_giveaway_item(7, {"image_url": url}) == {"id": 7, "image_url": "https://cdn.test/prize.jpg"}
        finally:
            await client.close()

        assert calls == [("POST", "/api/content/uploads"), ("PATCH", "/api/content/admin/giveaway-items/7")]

    asyncio.run(run())


def test_list_banners_normalizes_response_variants():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/content/admin/banners"
            return httpx.Response(200, json={"banners": [{"id": 1, "active": False, "url": "https://cdn/banner.jpg", "link": "https://site"}]})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_banners() == [{"id": 1, "active": False, "url": "https://cdn/banner.jpg", "link": "https://site", "image_url": "https://cdn/banner.jpg", "link_url": "https://site", "is_active": False}]
        finally:
            await client.close()

    asyncio.run(run())


def test_create_update_hide_banner_methods():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            return httpx.Response(200, json={"data": {"id": 5, **(payload or {})}})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_banner({"title": "Hero", "active": True}) == {"id": 5, "title": "Hero", "active": True, "is_active": True}
            assert await client.update_banner(5, {"sort_order": 3}) == {"id": 5, "sort_order": 3}
            assert await client.hide_banner(5) == {"id": 5, "is_active": False, "active": False}
        finally:
            await client.close()

        assert calls == [
            ("POST", "/api/content/admin/banners", {"title": "Hero", "active": True, "is_active": True}),
            ("PATCH", "/api/content/admin/banners/5", {"sort_order": 3}),
            ("PATCH", "/api/content/admin/banners/5", {"is_active": False, "active": False}),
        ]

    asyncio.run(run())


def test_upload_then_patch_banner_image_url(tmp_path: Path):
    async def run():
        image = tmp_path / "banner.webp"
        image.write_bytes(b"fake-image")
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path == "/api/content/uploads":
                return httpx.Response(200, json={"url": "https://cdn.test/banner.webp"})
            assert json.loads(request.content.decode()) == {"image_url": "https://cdn.test/banner.webp"}
            return httpx.Response(200, json={"id": 5, "image_url": "https://cdn.test/banner.webp"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            url = await client.upload_file(image, "image/webp")
            assert await client.update_banner(5, {"image_url": url}) == {"id": 5, "image_url": "https://cdn.test/banner.webp"}
        finally:
            await client.close()

        assert calls == [("POST", "/api/content/uploads"), ("PATCH", "/api/content/admin/banners/5")]

    asyncio.run(run())


def test_list_blocks_normalizes_response_variants():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == "/api/content/admin/blocks"
            return httpx.Response(200, json={"blocks": [{"id": 1, "key": "hero", "placement": "home", "active": False, "metadata": {"type": "hero"}}]})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_blocks() == [{"id": 1, "key": "hero", "placement": "home", "active": False, "metadata": {"type": "hero"}, "metadata_json": {"type": "hero"}, "is_active": False}]
        finally:
            await client.close()

    asyncio.run(run())


@pytest.mark.parametrize("key", ["results", "items", "list"])
def test_list_blocks_accepts_collection_keys(key):
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={key: [{"id": 2, "key": "banner"}]})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_blocks() == [{"id": 2, "key": "banner"}]
        finally:
            await client.close()

    asyncio.run(run())


def test_create_update_hide_publish_block_methods():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            return httpx.Response(200, json={"data": {"id": 9, **(payload or {})}})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_block({"key": "hero", "active": True}) == {"id": 9, "key": "hero", "active": True, "is_active": True}
            assert await client.update_block(9, {"title": "New"}) == {"id": 9, "title": "New"}
            assert await client.hide_block(9) == {"id": 9, "is_active": False, "active": False}
            assert await client.publish_block(9) == {"id": 9, "is_active": True, "active": True}
        finally:
            await client.close()

        assert calls == [
            ("POST", "/api/content/admin/blocks", {"key": "hero", "active": True, "is_active": True}),
            ("PATCH", "/api/content/admin/blocks/9", {"title": "New"}),
            ("PATCH", "/api/content/admin/blocks/9", {"is_active": False, "active": False}),
            ("PATCH", "/api/content/admin/blocks/9", {"is_active": True, "active": True}),
        ]

    asyncio.run(run())


def test_metadata_validation():
    from admin_bot.bot import validate_metadata_text

    assert validate_metadata_text('{"type":"hero"}') == '{"type":"hero"}'
    assert validate_metadata_text("-") is None
    assert validate_metadata_text('{"type":') is False

@pytest.mark.parametrize(
    ("method_name", "response_key", "path"),
    [
        ("list_cities", "cities", "/api/content/admin/cities"),
        ("list_categories", "categories", "/api/content/admin/categories"),
    ],
)
def test_reference_lists_normalize_named_response_keys(method_name, response_key, path):
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "GET"
            assert request.url.path == path
            return httpx.Response(200, json={response_key: [{"id": 1, "title": "NSK", "active": False}]})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await getattr(client, method_name)() == [{"id": 1, "title": "NSK", "active": False, "name": "NSK", "is_active": False}]
        finally:
            await client.close()

    asyncio.run(run())


@pytest.mark.parametrize("key", ["items", "results", "list", "data"])
def test_reference_lists_normalize_generic_response_keys(key):
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={key: [{"id": 2, "name": "Beauty", "is_active": True}]})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_categories() == [{"id": 2, "name": "Beauty", "is_active": True, "title": "Beauty", "active": True}]
        finally:
            await client.close()

    asyncio.run(run())


def test_city_crud_visibility_methods():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            return httpx.Response(200, json={"data": {"id": 3, **(payload or {})}})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_city({"name": "Новосибирск", "active": True}) == {"id": 3, "name": "Новосибирск", "active": True, "is_active": True, "title": "Новосибирск"}
            assert await client.update_city(3, {"sort_order": 10}) == {"id": 3, "sort_order": 10}
            assert await client.hide_city(3) == {"id": 3, "is_active": False, "active": False}
            assert await client.publish_city(3) == {"id": 3, "is_active": True, "active": True}
        finally:
            await client.close()

        assert calls == [
            ("POST", "/api/content/admin/cities", {"name": "Новосибирск", "active": True, "is_active": True}),
            ("PATCH", "/api/content/admin/cities/3", {"sort_order": 10}),
            ("PATCH", "/api/content/admin/cities/3", {"is_active": False, "active": False}),
            ("PATCH", "/api/content/admin/cities/3", {"is_active": True, "active": True}),
        ]

    asyncio.run(run())


def test_category_crud_visibility_methods():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode()) if request.content else None
            calls.append((request.method, request.url.path, payload))
            return httpx.Response(200, json={"id": 4, **(payload or {})})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.create_category({"title": "Красота", "is_active": True}) == {"id": 4, "title": "Красота", "is_active": True, "active": True, "name": "Красота"}
            assert await client.update_category(4, {"slug": "beauty"}) == {"id": 4, "slug": "beauty"}
            assert await client.hide_category(4) == {"id": 4, "is_active": False, "active": False}
            assert await client.publish_category(4) == {"id": 4, "is_active": True, "active": True}
        finally:
            await client.close()

        assert calls == [
            ("POST", "/api/content/admin/categories", {"title": "Красота", "is_active": True, "active": True}),
            ("PATCH", "/api/content/admin/categories/4", {"slug": "beauty"}),
            ("PATCH", "/api/content/admin/categories/4", {"is_active": False, "active": False}),
            ("PATCH", "/api/content/admin/categories/4", {"is_active": True, "active": True}),
        ]

    asyncio.run(run())


def test_partner_reference_keyboard_uses_ids_and_hides_inactive_items():
    from admin_bot.keyboards import partner_reference_keyboard

    markup = partner_reference_keyboard(
        "cities",
        [
            {"id": 1, "name": "Новосибирск", "is_active": True},
            {"id": 2, "name": "Скрытый", "is_active": False},
        ],
    )

    buttons = [button for row in markup.inline_keyboard for button in row]
    assert [(button.text, button.callback_data) for button in buttons] == [
        ("Новосибирск", "partner_city:select:1"),
        ("Отмена", "back:menu"),
    ]


def test_finalize_partner_sends_reference_ids_without_legacy_city_category(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module

        class FakeApi:
            def __init__(self):
                self.created_payload = None
                self.photos = []

            async def create_partner(self, payload):
                self.created_payload = payload
                return {"id": 42}

            async def add_partner_photo(self, partner_id, url):
                self.photos.append((partner_id, url))
                return {"id": 5}

        class FakeState:
            def __init__(self):
                self.cleared = False

            async def get_data(self):
                return {
                    "name": "Bloom Spa",
                    "description": "Описание",
                    "city": "Новосибирск",
                    "city_id": "10",
                    "category": "Красота",
                    "category_id": "20",
                    "address": "Красный проспект",
                    "phone": "+79990000000",
                }

            async def clear(self):
                self.cleared = True

        class FakeMessage:
            def __init__(self):
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        api = FakeApi()
        state = FakeState()
        message = FakeMessage()
        monkeypatch.setattr(bot_module, "_content_api", api)

        await bot_module.finalize_partner(message, state, "https://cdn.test/partner.jpg")

        assert api.created_payload == {
            "name": "Bloom Spa",
            "title": "Bloom Spa",
            "description": "Описание",
            "city_id": "10",
            "category_id": "20",
            "address": "Красный проспект",
            "phone": "+79990000000",
            "is_active": True,
        }
        assert "city" not in api.created_payload
        assert "category" not in api.created_payload
        assert api.photos == [(42, "https://cdn.test/partner.jpg")]
        assert state.cleared is True
        assert message.answers[0][0] == "Партнёр создан. Хотите добавить услугу?"

    asyncio.run(run())

def test_partner_creation_mirrors_to_telegram_catalog_without_manual_sync():
    async def run():
        import httpx
        from admin_bot.web_api import ContentAdminApiClient

        requests = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content.decode() or "{}") if request.content else {}
            requests.append((request.method, str(request.url), body))
            if str(request.url).endswith("/api/tg/admin/partners"):
                return httpx.Response(201, json={"id": 9, "external_content_id": body["external_content_id"], "title": body["title"], "is_active": True})
            if str(request.url).endswith("/admin/partners"):
                return httpx.Response(201, json={"id": 77, "title": body["title"], "is_active": True})
            if str(request.url).endswith("/admin/partners/77/photos"):
                return httpx.Response(201, json={"id": 88, "image_url": body["image_url"]})
            if str(request.url).endswith("/api/tg/admin/partners/9/photos"):
                return httpx.Response(201, json={"id": 10, "image_url": body["image_url"]})
            return httpx.Response(404, json={"detail": "unexpected"})

        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient
        try:
            httpx.AsyncClient = lambda *args, **kwargs: original(*args, transport=transport, **kwargs)
            client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
            assert await client.create_partner({"title": "Тест2", "is_active": True}) == {"id": 77, "title": "Тест2", "is_active": True}
            assert await client.add_partner_photo(77, "https://cdn.test/test2.jpg") == {"id": 88, "image_url": "https://cdn.test/test2.jpg"}
            await client.close()
        finally:
            httpx.AsyncClient = original

        assert ("POST", "https://tg.test/api/tg/admin/partners", {"external_content_id": 77, "title": "Тест2", "display_name": None, "description": None, "city": None, "category": None, "address": None, "phone": None, "is_active": True}) in requests
        assert ("POST", "https://tg.test/api/tg/admin/partners/9/photos", {"external_content_id": 88, "image_url": "https://cdn.test/test2.jpg", "url": "https://cdn.test/test2.jpg", "is_cover": True}) in requests

    asyncio.run(run())


def test_delete_partner_removes_related_web_content_and_catalog_record_idempotently():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, str(request.url)))
            path = request.url.path
            if path == "/api/content/admin/partners/77/offers":
                return httpx.Response(200, json={"items": [{"id": 5}, {"id": 6}]})
            if path == "/api/content/admin/offers/5/photos":
                return httpx.Response(200, json={"items": [{"id": 50}]})
            if path == "/api/content/admin/offers/6/photos":
                return httpx.Response(404, json={"detail": "not_found"})
            if path == "/api/content/admin/partners/77/photos":
                return httpx.Response(200, json={"items": [{"id": 70}]})
            if path in {
                "/api/content/admin/offer-photos/50",
                "/api/content/admin/offers/5",
                "/api/content/admin/offers/6",
                "/api/content/admin/partner-photos/70",
                "/api/content/admin/partners/77",
                "/api/tg/admin/partners/9",
            }:
                return httpx.Response(200, json={"detail": "deleted"})
            if path == "/api/tg/admin/partners":
                return httpx.Response(200, json={"items": [{"id": 9, "external_content_id": 77}]})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        try:
            assert await client.delete_partner(77) is None
        finally:
            await client.close()

        assert ("DELETE", "https://web.test/api/content/admin/partners/77") in calls
        assert not any("/api/content/admin/offers/" in url for _, url in calls)
        assert not any("/api/content/admin/partner-photos/" in url for _, url in calls)
        assert ("GET", "https://tg.test/api/tg/admin/partners") in calls
        assert ("DELETE", "https://tg.test/api/tg/admin/partners/9") in calls

    asyncio.run(run())


def test_delete_partner_ignores_missing_partner_in_both_sources():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "GET" and request.url.path.endswith("/offers"):
                return httpx.Response(404, json={"detail": "missing"})
            if request.method == "GET" and request.url.path.endswith("/photos"):
                return httpx.Response(404, json={"detail": "missing"})
            if request.method == "DELETE":
                return httpx.Response(404, json={"detail": "missing"})
            if request.url.path == "/api/tg/admin/partners":
                return httpx.Response(200, json={"items": []})
            return httpx.Response(404, json={"detail": "missing"})

        client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        try:
            assert await client.delete_partner(404) is None
        finally:
            await client.close()

    asyncio.run(run())


def test_delete_partner_does_not_fall_back_to_web_soft_delete_when_delete_is_not_allowed():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode() or "{}") if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "DELETE" and request.url.path == "/api/content/admin/partners/77":
                return httpx.Response(405, json={"detail": "Method Not Allowed"})
            if request.method == "PATCH" and request.url.path == "/api/content/admin/partners/77":
                return httpx.Response(200, json={"id": 77, "is_active": False})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        try:
            with pytest.raises(WebApiError) as exc_info:
                await client.delete_partner(77)
        finally:
            await client.close()

        assert "WEB API вернул ошибку 405" in str(exc_info.value)
        assert ("DELETE", "/api/content/admin/partners/77", None) in calls
        assert ("PATCH", "/api/content/admin/partners/77", {"is_active": False}) not in calls

    asyncio.run(run())


def test_delete_partner_treats_missing_web_and_catalog_partner_as_success():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode() or "{}") if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "DELETE" and request.url.path == "/api/content/admin/partners/77":
                return httpx.Response(404, json={"detail": "missing"})
            if request.url.path == "/api/tg/admin/partners":
                return httpx.Response(200, json={"items": [{"id": 9, "external_content_id": 77, "is_active": True}]})
            if request.method == "DELETE" and request.url.path == "/api/tg/admin/partners/9":
                return httpx.Response(404, json={"detail": "missing"})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        try:
            assert await client.delete_partner(77) is None
        finally:
            await client.close()

        assert ("DELETE", "/api/content/admin/partners/77", None) in calls
        assert ("GET", "/api/tg/admin/partners", None) in calls
        assert ("DELETE", "/api/tg/admin/partners/9", None) in calls
        assert not any(call[0] == "PATCH" and call[1] == "/api/content/admin/partners/77" for call in calls)

    asyncio.run(run())


def test_delete_partner_does_not_delete_catalog_by_random_content_id_when_external_mapping_missing():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path, json.loads(request.content.decode() or "{}") if request.content else None))
            if request.method == "DELETE" and request.url.path == "/api/content/admin/partners/77":
                return httpx.Response(204)
            if request.method == "GET" and request.url.path == "/api/tg/admin/partners":
                return httpx.Response(200, json={"items": [{"id": 77, "external_content_id": 88}]})
            raise AssertionError(f"unexpected request {request.method} {request.url}")

        client = ContentAdminApiClient("https://web.test/api/content", "token", catalog_base_url="https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        try:
            assert await client.delete_partner(77) is None
        finally:
            await client.close()

        assert ("DELETE", "/api/content/admin/partners/77", None) in calls
        assert ("GET", "/api/tg/admin/partners", None) in calls
        assert not any(call[0] == "DELETE" and call[1].startswith("/api/tg/admin/partners/") for call in calls)

    asyncio.run(run())


def test_partner_delete_callback_shows_success_and_refreshes_list(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module

        class FakeApi:
            def __init__(self):
                self.deleted = []

            async def delete_partner(self, partner_id):
                self.deleted.append(partner_id)

        class FakeMessage:
            def __init__(self):
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        class FakeCallback:
            data = "partner:delete:yes:77"

            def __init__(self):
                self.message = FakeMessage()
                self.answered = False

            async def answer(self, *args, **kwargs):
                self.answered = True

        refreshed = []
        api = FakeApi()
        callback = FakeCallback()
        monkeypatch.setattr(bot_module, "_content_api", api)

        async def fake_list_partners(event):
            refreshed.append(event)
            await event.message.answer("Партнёры:\n• Другой — город не указан — активен")

        monkeypatch.setattr(bot_module, "list_partners", fake_list_partners)

        await bot_module.partner_delete_execute(callback)

        assert api.deleted == ["77"]
        assert callback.message.answers[0][0] == "✅ Партнёр успешно удалён."
        assert "405" not in callback.message.answers[0][0]
        assert refreshed == [callback]
        assert callback.message.answers[-1][0] == "Партнёры:\n• Другой — город не указан — активен"

    asyncio.run(run())


def test_partner_delete_callback_shows_technical_error_on_delete_405():
    async def run():
        from admin_bot import bot as bot_module

        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode() or "{}") if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "DELETE" and request.url.path == "/api/content/admin/partners/77":
                return httpx.Response(405, json={"detail": "Method Not Allowed"})
            return httpx.Response(404, json={"detail": "unexpected"})

        class FakeMessage:
            def __init__(self):
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        class FakeCallback:
            data = "partner:delete:yes:77"

            def __init__(self):
                self.message = FakeMessage()
                self.answered = False

            async def answer(self, *args, **kwargs):
                self.answered = True

        client = ContentAdminApiClient("https://web.test/api/content", "token", "https://tg.test")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://web.test")
        callback = FakeCallback()
        refreshed = []
        original_api = bot_module._content_api
        original_list_partners = bot_module.list_partners
        bot_module._content_api = client

        async def fake_list_partners(event):
            refreshed.append(event)

        try:
            bot_module.list_partners = fake_list_partners
            await bot_module.partner_delete_execute(callback)
        finally:
            bot_module._content_api = original_api
            bot_module.list_partners = original_list_partners
            await client.close()

        assert callback.message.answers[0][0].startswith("Не удалось удалить партнёра")
        assert "405" not in callback.message.answers[0][0]
        assert "Действие сейчас недоступно" in callback.message.answers[0][0]
        assert refreshed == []
        assert ("DELETE", "/api/content/admin/partners/77", None) in calls
        assert not any(call[0] == "PATCH" for call in calls)

    asyncio.run(run())


def test_partner_offer_crud_photo_and_list_endpoints():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode() or "{}") if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "GET" and request.url.path == "/api/content/admin/partners/77/offers":
                return httpx.Response(200, json={"items": [{"id": 5, "title": "SPA", "is_active": True}]})
            if request.method == "POST" and request.url.path == "/api/content/admin/partners/77/offers":
                return httpx.Response(201, json={"id": 5, **payload})
            if request.method == "PATCH" and request.url.path == "/api/content/admin/offers/5":
                return httpx.Response(200, json={"id": 5, **payload})
            if request.method == "GET" and request.url.path == "/api/content/admin/offers/5/photos":
                return httpx.Response(200, json={"items": []})
            if request.method == "POST" and request.url.path == "/api/content/admin/offers/5/photos":
                return httpx.Response(201, json={"id": 9, **payload})
            if request.method == "DELETE" and request.url.path in {"/api/content/admin/offers/5/privilege-codes", "/api/content/admin/offers/5"}:
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_offers(77) == [{"id": 5, "title": "SPA", "is_active": True}]
            assert await client.create_offer(77, {"title": "SPA"}) == {"id": 5, "title": "SPA"}
            assert await client.update_offer(5, {"title": "Massage"}) == {"id": 5, "title": "Massage"}
            assert await client.update_offer(5, {"is_active": False}) == {"id": 5, "is_active": False}
            assert await client.add_offer_photo(5, "https://cdn.test/offer.jpg") == {"id": 9, "url": "https://cdn.test/offer.jpg", "image_url": "https://cdn.test/offer.jpg"}
            assert await client.delete_offer(5) is None
        finally:
            await client.close()

        assert ("GET", "/api/content/admin/partners/77/offers", None) in calls
        assert ("POST", "/api/content/admin/partners/77/offers", {"title": "SPA"}) in calls
        assert ("PATCH", "/api/content/admin/offers/5", {"title": "Massage"}) in calls
        assert ("PATCH", "/api/content/admin/offers/5", {"is_active": False}) in calls
        assert ("POST", "/api/content/admin/offers/5/photos", {"url": "https://cdn.test/offer.jpg", "image_url": "https://cdn.test/offer.jpg"}) in calls
        assert ("DELETE", "/api/content/admin/offers/5/privilege-codes", None) in calls
        assert ("DELETE", "/api/content/admin/offers/5", None) in calls

    asyncio.run(run())


def test_delete_offer_removes_photos_and_treats_404_as_idempotent():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "GET" and request.url.path == "/api/content/admin/offers/5/photos":
                return httpx.Response(200, json={"items": [{"id": 9}]})
            if request.method == "DELETE" and request.url.path == "/api/content/admin/offer-photos/9":
                return httpx.Response(404, json={"detail": "already deleted"})
            if request.method == "DELETE" and request.url.path == "/api/content/admin/offers/5/privilege-codes":
                return httpx.Response(404, json={"detail": "already deleted"})
            if request.method == "DELETE" and request.url.path == "/api/content/admin/offers/5":
                return httpx.Response(404, json={"detail": "already deleted"})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.delete_offer(5) is None
        finally:
            await client.close()

        assert calls == [
            ("GET", "/api/content/admin/offers/5/photos"),
            ("DELETE", "/api/content/admin/offer-photos/9"),
            ("DELETE", "/api/content/admin/offers/5/privilege-codes"),
            ("DELETE", "/api/content/admin/offers/5"),
        ]

    asyncio.run(run())


def test_delete_offer_photos_refreshes_current_photo_list():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.method == "GET" and request.url.path == "/api/content/admin/offers/8/photos":
                return httpx.Response(200, json={"items": [{"id": 10}, {"id": 11}]})
            if request.method == "DELETE" and request.url.path in {"/api/content/admin/offer-photos/10", "/api/content/admin/offer-photos/11"}:
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(404, json={"detail": "unexpected"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.delete_offer_photos(8) is None
        finally:
            await client.close()

        assert calls == [
            ("GET", "/api/content/admin/offers/8/photos"),
            ("DELETE", "/api/content/admin/offer-photos/10"),
            ("DELETE", "/api/content/admin/offer-photos/11"),
        ]

    asyncio.run(run())


def test_partner_sort_order_change_refreshes_partner_list(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module

        class FakeApi:
            async def list_partners(self):
                return [{"id": 77, "name": "A", "sort_order": 5, "is_active": True}]
            async def update_partner(self, partner_id, payload):
                self.updated = (partner_id, payload)
                return {"id": partner_id, **payload}
        class Msg:
            def __init__(self): self.answers=[]
            async def answer(self, text, reply_markup=None): self.answers.append((text, reply_markup))
        class Cb:
            data="partner:sort:move:77:-1"
            def __init__(self): self.message=Msg(); self.answered=False
            async def answer(self,*a,**k): self.answered=True
        api=FakeApi(); cb=Cb(); monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.partner_sort_move(cb)
        assert api.updated == ("77", {"sort_order": 4})
        assert cb.message.answers[-1][0].startswith("Партнёры:")
    asyncio.run(run())


def test_offer_sort_order_change_refreshes_offer_list(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module
        class FakeApi:
            async def list_offers(self, partner_id): return [{"id": 5, "title": "SPA", "sort_order": 2, "is_active": True}]
            async def update_offer(self, offer_id, payload): self.updated=(offer_id,payload); return {"id": offer_id, **payload}
        class Msg:
            def __init__(self): self.answers=[]
            async def answer(self, text, reply_markup=None): self.answers.append((text, reply_markup))
        class Cb:
            data="offer:sort:move:77:5:1"
            def __init__(self): self.message=Msg(); self.answered=False
            async def answer(self,*a,**k): self.answered=True
        api=FakeApi(); cb=Cb(); monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.offer_sort_move(cb)
        assert api.updated == ("5", {"sort_order": 3})
        assert cb.message.answers[-1][0].startswith("Услуги партнёра:")
    asyncio.run(run())


def test_partner_photo_sort_order_change_refreshes_photos(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module
        class FakeApi:
            async def list_partner_photos(self, partner_id): return [{"id": 9, "url": "u", "sort_order": 10}, {"id": 10, "url": "v", "sort_order": 20}]
            async def update_partner_photo(self, photo_id, payload): self.updated=(photo_id,payload); return {"id": photo_id, **payload}
        class Msg:
            def __init__(self): self.answers=[]
            async def answer(self, text, reply_markup=None): self.answers.append((text, reply_markup))
        class Cb:
            data="partner:photo:sort:77:9:-1"
            def __init__(self): self.message=Msg(); self.answered=False
            async def answer(self,*a,**k): self.answered=True
        api=FakeApi(); cb=Cb(); monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.partner_photo_sort_move(cb)
        assert api.updated == ("9", {"sort_order": 9})
        assert cb.message.answers[-1][0].startswith("Фото партнёра:")
    asyncio.run(run())


def test_offer_photo_sort_order_change_refreshes_photos(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module
        class FakeApi:
            async def list_offer_photos(self, offer_id): return [{"id": 8, "url": "u", "sort_order": 1}, {"id": 9, "url": "v", "sort_order": 2}]
            async def update_offer_photo(self, photo_id, payload): self.updated=(photo_id,payload); return {"id": photo_id, **payload}
        class Msg:
            def __init__(self): self.answers=[]
            async def answer(self, text, reply_markup=None): self.answers.append((text, reply_markup))
        class Cb:
            data="offer:photo:sort:77:5:8:1"
            def __init__(self): self.message=Msg(); self.answered=False
            async def answer(self,*a,**k): self.answered=True
        api=FakeApi(); cb=Cb(); monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.offer_photo_sort_move(cb)
        assert api.updated == ("8", {"sort_order": 2})
        assert cb.message.answers[-1][0].startswith("Фото услуги:")
    asyncio.run(run())


def test_manual_sort_order_input_updates_partner_and_refreshes_list(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module
        class FakeApi:
            async def update_partner(self, partner_id, payload): self.updated=(partner_id,payload); return {"id": partner_id, **payload}
            async def list_partners(self): return [{"id": 77, "name": "A", "sort_order": 42, "is_active": True}]
        class State:
            async def get_data(self): return {"kind": "partner", "partner_id": "77"}
            async def clear(self): self.cleared=True
        class Msg:
            text="42"
            def __init__(self): self.answers=[]; self.message=self
            async def answer(self, text, reply_markup=None): self.answers.append((text, reply_markup))
        api=FakeApi(); msg=Msg(); state=State(); monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.sort_order_manual_value(msg, state)
        assert api.updated == ("77", {"sort_order": 42})
        assert msg.answers[-1][0].startswith("Партнёры:")
    asyncio.run(run())


def test_partner_edit_updates_name_and_returns_to_card(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module

        class FakeApi:
            def __init__(self):
                self.updated = None

            async def update_partner(self, partner_id, payload):
                self.updated = (partner_id, payload)
                return {"id": partner_id, **payload}

            async def list_partners(self):
                return [{"id": 77, "name": "New Bloom", "city": "NSK", "is_active": True}]

        class State:
            async def get_data(self):
                return {"partner_id": "77", "field": "name"}

            async def clear(self):
                self.cleared = True

        class Msg:
            text = "New Bloom"

            def __init__(self):
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        api = FakeApi()
        state = State()
        msg = Msg()
        monkeypatch.setattr(bot_module, "_content_api", api)
        await bot_module.partner_edit_value(msg, state)

        assert api.updated == ("77", {"name": "New Bloom", "title": "New Bloom"})
        assert state.cleared is True
        assert msg.answers[0][0] == "Партнёр обновлён."
        assert msg.answers[-1][0] == "New Bloom\nГород: NSK\nСтатус: активен"

    asyncio.run(run())


def test_partner_edit_api_error_is_friendly_and_clears_state(monkeypatch):
    async def run():
        from admin_bot import bot as bot_module

        class FakeApi:
            async def update_partner(self, partner_id, payload):
                raise WebApiError("WEB API вернул ошибку 404: raw detail")

        class State:
            async def get_data(self):
                return {"partner_id": "77", "field": "phone"}

            async def clear(self):
                self.cleared = True

        class Msg:
            text = "+7999"

            def __init__(self):
                self.answers = []

            async def answer(self, text, reply_markup=None):
                self.answers.append((text, reply_markup))

        state = State()
        msg = Msg()
        monkeypatch.setattr(bot_module, "_content_api", FakeApi())
        await bot_module.partner_edit_value(msg, state)

        assert state.cleared is True
        assert msg.answers[0][0] == "Не удалось обновить партнёра: Запись уже удалена или не найдена."
        assert "raw detail" not in msg.answers[0][0]

    asyncio.run(run())


def test_partner_and_offer_callback_data_are_unique_and_short():
    from admin_bot.keyboards import (
        offer_actions_keyboard,
        offer_delete_confirm_keyboard,
        offer_edit_keyboard,
        offer_photo_keyboard,
        offers_keyboard,
        partner_actions_keyboard,
        partner_delete_confirm_keyboard,
        partner_edit_keyboard,
        partner_photos_keyboard,
        partners_keyboard,
        sort_order_keyboard,
    )

    markups = [
        partners_keyboard([{"id": 77, "name": "Partner"}]),
        partner_actions_keyboard(77, True),
        partner_delete_confirm_keyboard(77),
        partner_edit_keyboard(77),
        partner_photos_keyboard(77, [{"id": 1}, {"id": 2}]),
        offers_keyboard(77, [{"id": 5, "title": "SPA"}]),
        offer_actions_keyboard(77, 5, True),
        offer_delete_confirm_keyboard(77, 5),
        offer_edit_keyboard(77, 5),
        offer_photo_keyboard(77, 5, [{"id": 8}, {"id": 9}]),
        sort_order_keyboard("partner", 77, 1, "partner:view:77"),
        sort_order_keyboard("offer", "77:5", 1, "offer:view:77:5"),
    ]
    callbacks = [button.callback_data for markup in markups for row in markup.inline_keyboard for button in row]

    assert all(callback and len(callback.encode("utf-8")) <= 64 for callback in callbacks)
    for markup in markups:
        markup_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert len(markup_callbacks) == len(set(markup_callbacks))


def test_privilege_code_api_methods_and_repeat_delete_success():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content.decode() or "{}") if request.content else None
            calls.append((request.method, request.url.path, payload))
            if request.method == "GET":
                return httpx.Response(200, json={"privilege_codes": [{"id": 1, "code": "CODE001"}]})
            if request.method == "POST":
                return httpx.Response(200, json={"id": 2, **payload})
            if request.method == "PATCH":
                return httpx.Response(200, json={"data": {"id": 2, **payload}})
            return httpx.Response(404, json={"detail": "missing"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.list_privilege_codes(5) == [{"id": 1, "code": "CODE001"}]
            assert await client.create_privilege_code(5, "CODE002") == {"id": 2, "code": "CODE002"}
            assert await client.update_privilege_code(2, {"is_active": False}) == {"id": 2, "is_active": False}
            await client.delete_privilege_code(2)
        finally:
            await client.close()
        assert calls == [
            ("GET", "/api/content/admin/offers/5/privilege-codes", None),
            ("POST", "/api/content/admin/offers/5/privilege-codes", {"code": "CODE002"}),
            ("PATCH", "/api/content/admin/privilege-codes/2", {"is_active": False}),
            ("DELETE", "/api/content/admin/privilege-codes/2", None),
        ]

    asyncio.run(run())


def test_privilege_code_csv_txt_parsing_status_and_cleanup_filter():
    from admin_bot.bot import privilege_code_status, split_privilege_codes_payload

    assert split_privilege_codes_payload("CODE001\nCODE002\n") == ["CODE001", "CODE002"]
    assert split_privilege_codes_payload('CODE003,ignored\n"CODE004"\n') == ["CODE003", "CODE004"]
    assert privilege_code_status({"code": "A"}) == "✅ Свободен"
    assert privilege_code_status({"code": "B", "telegram_user_id": 7}) == "🎁 Выдан"
    assert privilege_code_status({"code": "C", "is_active": False}) == "❌ Неактивен"


def test_privilege_code_callback_limits_and_uniqueness():
    from admin_bot.keyboards import (
        offer_actions_keyboard,
        privilege_code_actions_keyboard,
        privilege_code_delete_confirm_keyboard,
        privilege_codes_clear_confirm_keyboard,
        privilege_codes_keyboard,
    )

    markups = [
        offer_actions_keyboard(77, 5, True),
        privilege_codes_keyboard(77, 5, [{"id": 1, "code": "CODE001"}, {"id": 2, "code": "CODE002"}]),
        privilege_code_actions_keyboard(77, 5, 1, True),
        privilege_code_delete_confirm_keyboard(77, 5, 1),
        privilege_codes_clear_confirm_keyboard(77, 5),
    ]
    callbacks = [button.callback_data for markup in markups for row in markup.inline_keyboard for button in row]
    assert all(callback and len(callback.encode("utf-8")) <= 64 for callback in callbacks)
    for markup in markups:
        markup_callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
        assert len(markup_callbacks) == len(set(markup_callbacks))


def test_privilege_code_user_errors_are_friendly():
    from admin_bot.bot import privilege_code_user_error

    assert privilege_code_user_error(WebApiError("WEB API вернул ошибку 404: missing")) == "Код уже отсутствует."
    assert privilege_code_user_error(WebApiError("WEB API вернул ошибку 409: duplicate")) == "Код уже существует."
    assert privilege_code_user_error(WebApiError("timeout")) == "Сервер временно недоступен. Попробуйте позже."


def test_privilege_code_fsm_states_and_cleanup_hooks_exist():
    import inspect
    from admin_bot import bot as bot_module
    from admin_bot.states import PrivilegeCodeBulkImport, PrivilegeCodeCreate, PrivilegeCodeEdit

    assert PrivilegeCodeCreate.code.state.endswith(":code")
    assert PrivilegeCodeEdit.code.state.endswith(":code")
    assert PrivilegeCodeBulkImport.payload.state.endswith(":payload")
    for handler in (bot_module.privilege_code_create, bot_module.privilege_code_bulk_import, bot_module.privilege_code_edit):
        source = inspect.getsource(handler)
        assert "await state.clear()" in source
        assert "await show_privilege_codes" in source


def test_banner_formatting_has_production_fields_and_empty_photo_message():
    from admin_bot.bot import format_banner, format_banner_list_item

    banner = {"id": 5, "title": "Hero", "subtitle": "Sub", "description": "Body", "cta_text": "Go", "link_url": "https://x", "placement": "home", "sort_order": 7, "is_active": False}

    card = format_banner(banner)
    list_item = format_banner_list_item(banner)

    assert "Название: Hero" in card
    assert "Фото: Фото отсутствует" in card
    assert "Статус: 🔴 Скрыт" in card
    assert "Место размещения: home" in list_item
    assert "Порядок отображения: 7" in list_item


def test_banner_delete_treats_404_as_success():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            assert request.method == "DELETE"
            assert request.url.path == "/api/content/admin/banners/5"
            return httpx.Response(404, json={"detail": "missing"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.delete_banner(5) is None
        finally:
            await client.close()

    asyncio.run(run())


def test_banner_callbacks_are_unique_and_short():
    from admin_bot.keyboards import banner_actions_keyboard, banner_edit_keyboard, banner_photo_keyboard, banners_keyboard

    markups = [
        banners_keyboard([{"id": 1, "title": "Hero"}]),
        banner_actions_keyboard(1, True),
        banner_edit_keyboard(1),
        banner_photo_keyboard(1, True),
    ]
    for markup in markups:
        callbacks = [
            button.callback_data
            for row in markup.inline_keyboard
            for button in row
            if button.callback_data
        ]
        assert len(callbacks) == len(set(callbacks))
        assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)


def test_banner_friendly_errors():
    from admin_bot.bot import banner_user_error

    assert banner_user_error(WebApiError("WEB API вернул ошибку 404: raw")) == "Баннер уже отсутствует."
    assert banner_user_error(WebApiError("WEB API вернул ошибку 409: raw")) == "Конфликт данных."
    assert banner_user_error(WebApiError("Request timed out")) == "Сервер временно недоступен. Попробуйте позже."



def _keyboard_callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row if button.callback_data]


def test_reference_keyboard_production_callbacks_unique_and_short():
    from admin_bot.keyboards import references_keyboard, reference_actions_keyboard, reference_edit_keyboard, reference_delete_confirm_keyboard, sort_order_keyboard

    markups = [
        references_keyboard("cities", [{"id": 123, "name": "Новосибирск", "is_active": True, "sort_order": 7}]),
        references_keyboard("categories", [{"id": 456, "title": "Красота", "is_active": False, "sort_order": 8}]),
        reference_actions_keyboard("city", 123, True),
        reference_actions_keyboard("category", 456, False),
        reference_edit_keyboard("city", 123),
        reference_edit_keyboard("category", 456),
        reference_delete_confirm_keyboard("city", 123),
        reference_delete_confirm_keyboard("category", 456),
        sort_order_keyboard("city", 123, 7, "city:view:123"),
        sort_order_keyboard("category", 456, 8, "category:view:456"),
    ]
    callbacks = [callback for markup in markups for callback in _keyboard_callbacks(markup)]

    assert all(len(callback.encode("utf-8")) <= 64 for callback in callbacks)
    action_callbacks = [callback for callback in callbacks if not callback.startswith(("city:view:", "category:view:", "city:list", "category:list"))]
    assert len(action_callbacks) == len(set(action_callbacks))
    assert "city:sort:manual:123" in callbacks
    assert "category:delete:yes:456" in callbacks


def test_reference_delete_methods_treat_404_as_success_and_surface_409():
    async def run():
        calls = []

        async def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, request.url.path))
            if request.url.path.endswith("/missing"):
                return httpx.Response(404, json={"detail": "not found"})
            return httpx.Response(409, json={"detail": "used"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            assert await client.delete_city("missing") is None
            assert await client.delete_category("missing") is None
            with pytest.raises(WebApiError, match="409:"):
                await client.delete_city("used")
            with pytest.raises(WebApiError, match="409:"):
                await client.delete_category("used")
        finally:
            await client.close()

        assert calls == [
            ("DELETE", "/api/content/admin/cities/missing"),
            ("DELETE", "/api/content/admin/categories/missing"),
            ("DELETE", "/api/content/admin/cities/used"),
            ("DELETE", "/api/content/admin/categories/used"),
        ]

    asyncio.run(run())


def test_reference_format_and_friendly_delete_conflicts():
    from admin_bot.bot import format_reference, reference_delete_error

    city = format_reference({"name": "Омск", "slug": "omsk", "sort_order": 3, "is_active": False, "partners_count": 2}, "Город")
    assert "Город: Омск" in city
    assert "Статус: 🔴 Скрыт" in city
    assert "Slug: omsk" in city
    assert "Порядок отображения: 3" in city
    assert "Партнёров: 2" in city

    assert reference_delete_error("city", WebApiError("409: Конфликт данных.")) == "Нельзя удалить город, пока он используется."
    assert reference_delete_error("category", WebApiError("409: Конфликт данных.")) == "Нельзя удалить категорию, пока она используется."
    assert reference_delete_error("city", WebApiError("404: Запись уже отсутствует.")) == "Запись уже удалена или не найдена."


def test_admin_bot_does_not_send_raw_reference_or_upload_errors():
    import inspect
    from admin_bot import bot as bot_module

    checked = "\n".join(
        inspect.getsource(handler)
        for handler in (
            bot_module.reference_list,
            bot_module.reference_create_active,
            bot_module.receive_and_upload_photo,
        )
    )

    assert "{exc}" not in checked
    assert "user_error(exc)" in checked


def test_privilege_code_conflict_detection_accepts_normalized_errors():
    from admin_bot.bot import is_conflict_error, privilege_code_user_error

    normalized = WebApiError("409: Конфликт данных.")
    legacy = WebApiError("WEB API вернул ошибку 409: duplicate")

    assert is_conflict_error(normalized)
    assert is_conflict_error(legacy)
    assert privilege_code_user_error(normalized) == "Код уже существует."


def test_production_error_messages_hide_transport_details():
    from admin_bot.bot import user_error

    for raw in (
        "WEB API вернул ошибку 405: method not allowed",
        "HTTP 500 traceback",
        "network is unreachable",
    ):
        message = user_error(WebApiError(raw))
        assert "WEB API" not in message
        assert "HTTP" not in message
        assert "405" not in message
        assert "traceback" not in message.lower()


def test_visibility_keyboards_show_only_expected_transition():
    from admin_bot.keyboards import reference_actions_keyboard, privilege_code_actions_keyboard

    active_ref_callbacks = _keyboard_callbacks(reference_actions_keyboard("city", 1, True))
    inactive_ref_callbacks = _keyboard_callbacks(reference_actions_keyboard("city", 1, False))
    active_code_callbacks = _keyboard_callbacks(privilege_code_actions_keyboard(1, 2, 3, True))
    inactive_code_callbacks = _keyboard_callbacks(privilege_code_actions_keyboard(1, 2, 3, False))

    assert "city:hide:1" in active_ref_callbacks
    assert "city:publish:1" not in active_ref_callbacks
    assert "city:publish:1" in inactive_ref_callbacks
    assert "city:hide:1" not in inactive_ref_callbacks
    assert "pc:toggle:1:2:3:0" in active_code_callbacks
    assert "pc:toggle:1:2:3:1" not in active_code_callbacks
    assert "pc:toggle:1:2:3:1" in inactive_code_callbacks
    assert "pc:toggle:1:2:3:0" not in inactive_code_callbacks


def test_parse_bool_text_accepts_all_admin_prompt_aliases():
    from admin_bot.bot import parse_bool_text

    for value in ("1", "+", "да", "д", "yes", "y", "true", "активен", "показать"):
        assert parse_bool_text(value) is True
    for value in ("0", "-", "нет", "н", "no", "n", "false", "скрыт", "скрыть"):
        assert parse_bool_text(value) is False
    assert parse_bool_text("maybe") is None


def test_admin_clients_list_and_detail_expose_stable_id_and_referral_fields():
    async def run():
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/api/content/admin/clients":
                return httpx.Response(200, json={"items": [{"id": 42, "telegram_user_id": 777, "created_at": "2026-06-30T00:00:00Z", "subscription": {"status": "active"}, "trial_used": True, "referrals_count": 2, "earned_giveaway_entries_count": 10}]})
            if request.url.path == "/api/content/admin/clients/42":
                return httpx.Response(200, json={"data": {"id": 42, "telegram_user_id": 777, "subscription_status": "active", "trial_used": True, "referrals_count": 2, "earned_giveaway_entries_count": 10}})
            return httpx.Response(404, json={"detail": "not_found"})

        client = ContentAdminApiClient("https://example.test/api/content", "token")
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://example.test")
        try:
            clients = await client.list_clients()
            detail = await client.get_client(42)
        finally:
            await client.close()

        assert clients[0]["id"] == 42
        assert clients[0]["telegram_id"] == 777
        assert clients[0]["subscription_status"] == "active"
        assert clients[0]["trial_used"] is True
        assert clients[0]["referrals_count"] == 2
        assert clients[0]["earned_giveaway_entries_count"] == 10
        assert detail["id"] == 42

    asyncio.run(run())
