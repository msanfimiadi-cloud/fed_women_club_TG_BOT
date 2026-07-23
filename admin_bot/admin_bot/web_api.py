from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class WebApiError(RuntimeError):
    pass


class ContentAdminApiClient:
    def __init__(self, base_url: str, api_token: str, catalog_base_url: str | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._catalog_base_url = catalog_base_url.rstrip("/") if catalog_base_url else None
        self._catalog_id_by_content_id: dict[str, str] = {}
        self._client = httpx.AsyncClient(
            timeout=30,
            headers={
                "Authorization": f"Bearer {api_token}",
                "X-Telegram-Admin-Token": api_token,
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = f"{self._base_url}{path}"
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            raise WebApiError("Сервер временно недоступен.") from exc
        except httpx.HTTPError as exc:
            raise WebApiError("WEB API недоступен. Попробуйте позже.") from exc
        return self._parse_response(response, "WEB API")

    def _parse_response(self, response: httpx.Response, api_name: str) -> Any:
        if response.status_code >= 400:
            friendly = {404: "Запись уже отсутствует.", 409: "Конфликт данных."}.get(response.status_code)
            if friendly:
                raise WebApiError(f"{response.status_code}: {friendly}")
            detail = self._extract_error(response)
            raise WebApiError(f"{api_name} вернул ошибку {response.status_code}: {detail}")
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise WebApiError(f"{api_name} вернул некорректный JSON.") from exc

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text[:300] or "без описания"
        if isinstance(data, dict):
            for key in ("detail", "message", "error"):
                if data.get(key):
                    return str(data[key])[:300]
        return str(data)[:300]

    async def upload_file(self, file_path: Path, content_type: str | None = None) -> str:
        with file_path.open("rb") as file_obj:
            files = {"file": (file_path.name, file_obj, content_type or "application/octet-stream")}
            data = await self._request("POST", "/uploads", files=files)
        url = self._extract_url(data)
        if not url:
            raise WebApiError("Upload endpoint не вернул URL файла.")
        return url

    @staticmethod
    def _extract_url(data: Any) -> str | None:
        if isinstance(data, str):
            return data
        if isinstance(data, dict):
            for key in ("url", "file_url", "fileUrl", "src", "location", "path"):
                value = data.get(key)
                if isinstance(value, str) and value:
                    return value
            nested = data.get("data")
            if nested is not data:
                return ContentAdminApiClient._extract_url(nested)
        return None

    async def list_clients(self) -> list[dict[str, Any]]:
        return [_normalize_client(item) for item in _as_list(await self._request("GET", "/admin/clients"))]

    async def get_client(self, client_id: int | str) -> dict[str, Any]:
        return _normalize_client(_as_dict(await self._request("GET", f"/admin/clients/{client_id}")))

    async def list_partners(self) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", "/admin/partners"))

    async def create_partner(self, payload: dict[str, Any]) -> dict[str, Any]:
        partner = _as_dict(await self._request("POST", "/admin/partners", json=payload))
        await self._mirror_partner_to_catalog(partner, payload)
        return partner

    async def update_partner(self, partner_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/partners/{partner_id}", json=payload))

    async def delete_partner(self, partner_id: int | str) -> None:
        await self._delete_web_partner_optional(partner_id)
        await self._delete_catalog_partner_optional(partner_id)

    async def _optional_list(self, func: Any, *args: Any) -> list[dict[str, Any]]:
        try:
            return await func(*args)
        except WebApiError as exc:
            if "404:" in str(exc):
                return []
            raise

    async def _delete_web_optional(
        self,
        path: str,
        *,
        entity_type: str,
        entity_id: int | str,
        fallback_payloads: tuple[dict[str, Any], ...] = (),
    ) -> None:
        try:
            await self._request("DELETE", path)
            return
        except WebApiError as exc:
            message = str(exc)
            if "404:" in message:
                return
            if "405:" not in message:
                raise

        fallback_result = "skipped_no_patch_endpoint"
        for payload in fallback_payloads:
            try:
                await self._request("PATCH", path, json=payload)
                fallback_result = f"patched:{','.join(payload.keys())}"
                break
            except WebApiError as exc:
                message = str(exc)
                if "404:" in message:
                    fallback_result = "patch_404_skipped"
                    break
                if "405:" in message:
                    fallback_result = "patch_405_try_next"
                    continue
                raise
        else:
            if fallback_payloads and fallback_result == "patch_405_try_next":
                fallback_result = "patch_405_skipped"

        logger.warning(
            "Handled child delete after WEB API DELETE returned 405",
            extra={
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "status_code": 405,
                "fallback_result": fallback_result,
            },
        )

    async def _delete_web_partner_optional(self, partner_id: int | str) -> None:
        path = f"/admin/partners/{partner_id}"
        try:
            await self._request("DELETE", path)
        except WebApiError as exc:
            message = str(exc)
            if "404:" in message:
                return
            raise

    async def list_partner_photos(self, partner_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/partners/{partner_id}/photos"))

    async def add_partner_photo(self, partner_id: int | str, url: str) -> dict[str, Any]:
        photo = _as_dict(await self._request("POST", f"/admin/partners/{partner_id}/photos", json={"url": url, "image_url": url}))
        await self._mirror_partner_photo_to_catalog(partner_id, url, photo)
        return photo

    async def update_partner_photo(self, photo_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/partner-photos/{photo_id}", json=payload))


    async def _catalog_request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self._catalog_base_url:
            return None
        url = f"{self._catalog_base_url}{path}"
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            raise WebApiError("Telegram catalog API недоступен. Попробуйте позже.") from exc
        return self._parse_response(response, "Telegram catalog API")

    async def _delete_catalog_partner_optional(self, content_partner_id: int | str) -> None:
        if not self._catalog_base_url:
            return
        catalog_partner_id = self._catalog_id_by_content_id.get(str(content_partner_id))
        if catalog_partner_id is None:
            try:
                partners = _as_list(await self._catalog_request("GET", "/api/tg/admin/partners"))
            except WebApiError as exc:
                if "404:" in str(exc):
                    return
                raise
            match = next((p for p in partners if str(p.get("external_content_id")) == str(content_partner_id)), None)
            if not match or match.get("id") is None:
                return
            catalog_partner_id = str(match["id"])
        path = f"/api/tg/admin/partners/{catalog_partner_id}"
        try:
            await self._catalog_request("DELETE", path)
        except WebApiError as exc:
            message = str(exc)
            if "404:" in message:
                return
            raise

    async def _mirror_partner_to_catalog(self, partner: dict[str, Any], original_payload: dict[str, Any]) -> None:
        if not self._catalog_base_url:
            return
        content_id = partner.get("id")
        payload = {
            "external_content_id": content_id,
            "title": partner.get("title") or partner.get("name") or original_payload.get("title") or original_payload.get("name"),
            "display_name": partner.get("display_name") or partner.get("name") or original_payload.get("name"),
            "description": partner.get("description") or original_payload.get("description"),
            "city": partner.get("city") or original_payload.get("city"),
            "category": partner.get("category") or original_payload.get("category"),
            "address": partner.get("address") or original_payload.get("address"),
            "phone": partner.get("phone") or original_payload.get("phone"),
            "is_active": bool(partner.get("is_active", partner.get("active", original_payload.get("is_active", True)))),
        }
        mirrored = _as_dict(await self._catalog_request("POST", "/api/tg/admin/partners", json=payload))
        if content_id is not None and mirrored.get("id") is not None:
            self._catalog_id_by_content_id[str(content_id)] = str(mirrored["id"])

    async def _mirror_partner_photo_to_catalog(self, partner_id: int | str, url: str, photo: dict[str, Any]) -> None:
        if not self._catalog_base_url:
            return
        catalog_partner_id = self._catalog_id_by_content_id.get(str(partner_id), str(partner_id))
        payload = {"external_content_id": photo.get("id"), "image_url": url, "url": url, "is_cover": True}
        await self._catalog_request("POST", f"/api/tg/admin/partners/{catalog_partner_id}/photos", json=payload)

    async def list_offers(self, partner_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/partners/{partner_id}/offers"))

    async def create_offer(self, partner_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("POST", f"/admin/partners/{partner_id}/offers", json=payload))

    async def update_offer(self, offer_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/offers/{offer_id}", json=payload))

    async def delete_offer(self, offer_id: int | str) -> None:
        await self.delete_offer_photos(offer_id)
        await self._delete_web_optional(f"/admin/offers/{offer_id}/privilege-codes", entity_type="offer_privilege_codes", entity_id=offer_id)
        await self._delete_web_optional(f"/admin/offers/{offer_id}", entity_type="offer", entity_id=offer_id)


    async def list_privilege_codes(self, offer_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/offers/{offer_id}/privilege-codes"))

    async def create_privilege_code(self, offer_id: int | str, code: str) -> dict[str, Any]:
        return _as_dict(await self._request("POST", f"/admin/offers/{offer_id}/privilege-codes", json={"code": code}))

    async def update_privilege_code(self, code_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/privilege-codes/{code_id}", json=payload))

    async def delete_privilege_code(self, code_id: int | str) -> None:
        try:
            await self._request("DELETE", f"/admin/privilege-codes/{code_id}")
        except WebApiError as exc:
            if "404:" in str(exc):
                return
            raise

    async def list_offer_photos(self, offer_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/offers/{offer_id}/photos"))

    async def add_offer_photo(self, offer_id: int | str, url: str) -> dict[str, Any]:
        return _as_dict(await self._request("POST", f"/admin/offers/{offer_id}/photos", json={"url": url, "image_url": url}))

    async def update_offer_photo(self, photo_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/offer-photos/{photo_id}", json=payload))

    async def delete_offer_photo(self, photo_id: int | str) -> None:
        await self._delete_web_optional(f"/admin/offer-photos/{photo_id}", entity_type="offer_photo", entity_id=photo_id)

    async def delete_offer_photos(self, offer_id: int | str) -> None:
        photos = await self._optional_list(self.list_offer_photos, offer_id)
        for photo in photos:
            photo_id = photo.get("id")
            if photo_id is not None:
                await self.delete_offer_photo(photo_id)

    async def list_blocks(self) -> list[dict[str, Any]]:
        return [_normalize_block(item) for item in _as_list(await self._request("GET", "/admin/blocks"))]

    async def get_block(self, block_id: int | str) -> dict[str, Any]:
        try:
            data = _as_dict(await self._request("GET", f"/admin/blocks/{block_id}"))
        except WebApiError:
            blocks = await self.list_blocks()
            data = next((item for item in blocks if str(item.get("id")) == str(block_id) or str(item.get("key")) == str(block_id)), {})
        return _normalize_block(data)

    async def create_block(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_block(_as_dict(await self._request("POST", "/admin/blocks", json=_block_payload(payload))))

    async def update_block(self, block_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_block(_as_dict(await self._request("PATCH", f"/admin/blocks/{block_id}", json=_block_payload(payload))))

    async def hide_block(self, block_id: int | str) -> dict[str, Any]:
        return await self.update_block(block_id, _active_payload(False))

    async def publish_block(self, block_id: int | str) -> dict[str, Any]:
        return await self.update_block(block_id, _active_payload(True))

    async def list_banners(self) -> list[dict[str, Any]]:
        return [_normalize_banner(item) for item in _as_list(await self._request("GET", "/admin/banners"))]

    async def get_banner(self, banner_id: int | str) -> dict[str, Any]:
        try:
            data = _as_dict(await self._request("GET", f"/admin/banners/{banner_id}"))
        except WebApiError:
            banners = await self.list_banners()
            data = next((item for item in banners if str(item.get("id")) == str(banner_id)), {})
        return _normalize_banner(data)

    async def create_banner(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_banner(_as_dict(await self._request("POST", "/admin/banners", json=_banner_payload(payload))))

    async def update_banner(self, banner_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_banner(_as_dict(await self._request("PATCH", f"/admin/banners/{banner_id}", json=_banner_payload(payload))))

    async def hide_banner(self, banner_id: int | str) -> dict[str, Any]:
        return await self.update_banner(banner_id, _active_payload(False))

    async def publish_banner(self, banner_id: int | str) -> dict[str, Any]:
        return await self.update_banner(banner_id, _active_payload(True))

    async def delete_banner(self, banner_id: int | str) -> None:
        try:
            await self._request("DELETE", f"/admin/banners/{banner_id}")
        except WebApiError as exc:
            if "404:" in str(exc):
                return
            raise

    async def list_cities(self) -> list[dict[str, Any]]:
        return [_normalize_reference(item) for item in _as_list(await self._request("GET", "/admin/cities"))]

    async def get_city(self, city_id: int | str) -> dict[str, Any]:
        try:
            data = _as_dict(await self._request("GET", f"/admin/cities/{city_id}"))
        except WebApiError:
            cities = await self.list_cities()
            data = next((item for item in cities if str(item.get("id")) == str(city_id)), {})
        return _normalize_reference(data)

    async def create_city(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_reference(_as_dict(await self._request("POST", "/admin/cities", json=_reference_payload(payload))))

    async def update_city(self, city_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_reference(_as_dict(await self._request("PATCH", f"/admin/cities/{city_id}", json=_reference_payload(payload))))

    async def hide_city(self, city_id: int | str) -> dict[str, Any]:
        return await self.update_city(city_id, _active_payload(False))

    async def publish_city(self, city_id: int | str) -> dict[str, Any]:
        return await self.update_city(city_id, _active_payload(True))

    async def delete_city(self, city_id: int | str) -> None:
        try:
            await self._request("DELETE", f"/admin/cities/{city_id}")
        except WebApiError as exc:
            if "404:" in str(exc):
                return
            raise

    async def list_categories(self) -> list[dict[str, Any]]:
        return [_normalize_reference(item) for item in _as_list(await self._request("GET", "/admin/categories"))]

    async def get_category(self, category_id: int | str) -> dict[str, Any]:
        try:
            data = _as_dict(await self._request("GET", f"/admin/categories/{category_id}"))
        except WebApiError:
            categories = await self.list_categories()
            data = next((item for item in categories if str(item.get("id")) == str(category_id)), {})
        return _normalize_reference(data)

    async def create_category(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_reference(_as_dict(await self._request("POST", "/admin/categories", json=_reference_payload(payload))))

    async def update_category(self, category_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_reference(_as_dict(await self._request("PATCH", f"/admin/categories/{category_id}", json=_reference_payload(payload))))

    async def hide_category(self, category_id: int | str) -> dict[str, Any]:
        return await self.update_category(category_id, _active_payload(False))

    async def publish_category(self, category_id: int | str) -> dict[str, Any]:
        return await self.update_category(category_id, _active_payload(True))

    async def delete_category(self, category_id: int | str) -> None:
        try:
            await self._request("DELETE", f"/admin/categories/{category_id}")
        except WebApiError as exc:
            if "404:" in str(exc):
                return
            raise

    async def list_giveaways(self) -> list[dict[str, Any]]:
        return [_normalize_giveaway(item) for item in _as_list(await self._request("GET", "/admin/giveaways"))]

    async def get_giveaway(self, giveaway_id: int | str) -> dict[str, Any]:
        return _normalize_giveaway(_as_dict(await self._request("GET", f"/admin/giveaways/{giveaway_id}")))

    async def create_giveaway(self, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_giveaway(_as_dict(await self._request("POST", "/admin/giveaways", json=payload)))

    async def update_giveaway(self, giveaway_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_giveaway(_as_dict(await self._request("PATCH", f"/admin/giveaways/{giveaway_id}", json=payload)))

    async def delete_giveaway(self, giveaway_id: int | str) -> None:
        for photo in await self._optional_list(self.list_giveaway_photos, giveaway_id):
            photo_id = photo.get("id")
            if photo_id is not None:
                await self.delete_giveaway_photo(photo_id)
        for item in await self._optional_list(self.list_giveaway_items, giveaway_id):
            item_id = item.get("id")
            if item_id is not None:
                await self.delete_giveaway_item(item_id)
        await self._delete_web_optional(f"/admin/giveaways/{giveaway_id}", entity_type="giveaway", entity_id=giveaway_id)

    async def hide_giveaway(self, giveaway_id: int | str) -> dict[str, Any]:
        return await self.update_giveaway(giveaway_id, _active_payload(False))

    async def publish_giveaway(self, giveaway_id: int | str) -> dict[str, Any]:
        return await self.update_giveaway(giveaway_id, _active_payload(True))

    async def list_giveaway_photos(self, giveaway_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/giveaways/{giveaway_id}/photos"))

    async def add_giveaway_photo(self, giveaway_id: int | str, url: str) -> dict[str, Any]:
        return _as_dict(await self._request("POST", f"/admin/giveaways/{giveaway_id}/photos", json={"url": url, "image_url": url, "photo_url": url}))

    async def update_giveaway_photo(self, photo_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("PATCH", f"/admin/giveaway-photos/{photo_id}", json=payload))

    async def delete_giveaway_photo(self, photo_id: int | str) -> None:
        await self._delete_web_optional(f"/admin/giveaway-photos/{photo_id}", entity_type="giveaway_photo", entity_id=photo_id)

    async def list_giveaway_items(self, giveaway_id: int | str) -> list[dict[str, Any]]:
        return _as_list(await self._request("GET", f"/admin/giveaways/{giveaway_id}/items"))

    async def get_giveaway_item(self, item_id: int | str) -> dict[str, Any]:
        return _normalize_giveaway_item(_as_dict(await self._request("GET", f"/admin/giveaway-items/{item_id}")))

    async def create_giveaway_item(self, giveaway_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _as_dict(await self._request("POST", f"/admin/giveaways/{giveaway_id}/items", json=payload))

    async def update_giveaway_item(self, item_id: int | str, payload: dict[str, Any]) -> dict[str, Any]:
        return _normalize_giveaway_item(_as_dict(await self._request("PATCH", f"/admin/giveaway-items/{item_id}", json=payload)))

    async def delete_giveaway_item(self, item_id: int | str) -> None:
        await self._delete_web_optional(f"/admin/giveaway-items/{item_id}", entity_type="giveaway_item", entity_id=item_id)

    async def hide_giveaway_item(self, item_id: int | str) -> dict[str, Any]:
        return await self.update_giveaway_item(item_id, {"is_active": False})

    async def publish_giveaway_item(self, item_id: int | str) -> dict[str, Any]:
        return await self.update_giveaway_item(item_id, {"is_active": True})


def _as_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("cities", "categories", "blocks", "results", "items", "list", "giveaway_items", "data", "partners", "offers", "giveaways", "banners", "photos", "codes", "privilege_codes"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _as_dict(data: Any) -> dict[str, Any]:
    if isinstance(data, dict):
        nested = data.get("data")
        if isinstance(nested, dict):
            return nested
        return data
    return {}


def _active_payload(active: bool) -> dict[str, bool]:
    return {"is_active": active, "active": active}


def _reference_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if "active" in data and "is_active" not in data:
        data["is_active"] = data["active"]
    if "is_active" in data and "active" not in data:
        data["active"] = data["is_active"]
    return data


def _normalize_reference(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}
    data = dict(item)
    if "name" not in data and data.get("title"):
        data["name"] = data["title"]
    if "title" not in data and data.get("name"):
        data["title"] = data["name"]
    if "is_active" not in data and "active" in data:
        data["is_active"] = data["active"]
    if "active" not in data and "is_active" in data:
        data["active"] = data["is_active"]
    return data


def _block_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if "active" in data and "is_active" not in data:
        data["is_active"] = data["active"]
    if "is_active" in data and "active" not in data:
        data["active"] = data["is_active"]
    return data


def _normalize_block(block: dict[str, Any]) -> dict[str, Any]:
    if not block:
        return {}
    data = dict(block)
    if "metadata_json" not in data:
        for key in ("metadata", "metadataJson", "meta", "settings"):
            if key in data:
                data["metadata_json"] = data[key]
                break
    if "is_active" not in data and "active" in data:
        data["is_active"] = data["active"]
    if "active" not in data and "is_active" in data:
        data["active"] = data["is_active"]
    return data


def _banner_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    if "active" in data and "is_active" not in data:
        data["is_active"] = data["active"]
    if "is_active" in data and "active" not in data:
        data["active"] = data["is_active"]
    return data


def _normalize_banner(banner: dict[str, Any]) -> dict[str, Any]:
    if not banner:
        return {}
    data = dict(banner)
    if "image_url" not in data:
        for key in ("photo_url", "url", "image", "picture"):
            if data.get(key):
                data["image_url"] = data[key]
                break
    if "link_url" not in data:
        for key in ("link", "url", "target_url", "href"):
            if data.get(key):
                data["link_url"] = data[key]
                break
    if "cta_text" not in data:
        for key in ("button_text", "button", "cta"):
            if data.get(key):
                data["cta_text"] = data[key]
                break
    if "is_active" not in data and "active" in data:
        data["is_active"] = data["active"]
    if "active" not in data and "is_active" in data:
        data["active"] = data["is_active"]
    return data


def _normalize_giveaway(giveaway: dict[str, Any]) -> dict[str, Any]:
    if not giveaway:
        return {}
    data = dict(giveaway)
    if "photo_url" not in data:
        for key in ("image_url", "url", "image", "picture"):
            if data.get(key):
                data["photo_url"] = data[key]
                break
    if "is_active" not in data and "active" in data:
        data["is_active"] = data["active"]
    if "active" not in data and "is_active" in data:
        data["active"] = data["is_active"]
    return data


def _normalize_giveaway_item(item: dict[str, Any]) -> dict[str, Any]:
    if not item:
        return {}
    data = dict(item)
    if "image_url" not in data:
        for key in ("photo_url", "url", "image", "picture"):
            if data.get(key):
                data["image_url"] = data[key]
                break
    if "is_active" not in data and "active" in data:
        data["is_active"] = data["active"]
    return data


def _normalize_client(client: dict[str, Any]) -> dict[str, Any]:
    if not client:
        return {}
    data = dict(client)
    subscription = data.get("subscription") if isinstance(data.get("subscription"), dict) else {}
    referrals_count = data.get("referrals_count", data.get("referral_count", data.get("invited_count", 0)))
    entries_count = data.get("earned_giveaway_entries_count", data.get("earned_entries_count", data.get("referral_entries_count", 0)))
    data["id"] = data.get("id") or data.get("client_id")
    data["telegram_id"] = data.get("telegram_id") or data.get("telegram_user_id")
    data["username"] = data.get("username") or data.get("telegram_username")
    data["registered_at"] = data.get("registered_at") or data.get("created_at")
    data["subscription_status"] = data.get("subscription_status") or subscription.get("status")
    data["trial_used"] = bool(data.get("trial_used", subscription.get("trial_used", False)))
    data["referrals_count"] = int(referrals_count or 0)
    data["earned_giveaway_entries_count"] = int(entries_count or 0)
    return data
