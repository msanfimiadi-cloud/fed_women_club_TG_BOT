from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
import tempfile
import csv
import io
from pathlib import Path
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware, Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, Message, ReplyKeyboardMarkup, TelegramObject
from aiogram.client.default import DefaultBotProperties

from .config import Settings, load_settings
from .keyboards import (
    banner_actions_keyboard,
    banner_delete_confirm_keyboard,
    banner_photo_keyboard,
    block_actions_keyboard,
    block_edit_keyboard,
    blocks_keyboard,
    banner_edit_keyboard,
    banners_keyboard,
    banners_menu_keyboard,
    after_partner_keyboard,
    giveaway_actions_keyboard,
    giveaway_edit_keyboard,
    giveaway_delete_confirm_keyboard,
    giveaway_photo_keyboard,
    giveaway_item_actions_keyboard,
    giveaway_item_edit_keyboard,
    giveaway_item_delete_confirm_keyboard,
    giveaway_items_keyboard,
    giveaway_items_menu_keyboard,
    giveaways_keyboard,
    home_menu_keyboard,
    references_menu_keyboard,
    reference_section_keyboard,
    references_keyboard,
    search_empty_keyboard,
    reference_actions_keyboard,
    reference_delete_confirm_keyboard,
    reference_edit_keyboard,
    main_menu,
    offer_actions_keyboard,
    offer_delete_confirm_keyboard,
    offer_edit_keyboard,
    offer_photo_keyboard,
    offers_keyboard,
    photo_sort_keyboard,
    sort_order_keyboard,
    partner_actions_keyboard,
    partner_delete_confirm_keyboard,
    partner_edit_keyboard,
    partner_photos_keyboard,
    partners_keyboard,
    privilege_code_actions_keyboard,
    privilege_code_delete_confirm_keyboard,
    privilege_codes_clear_confirm_keyboard,
    privilege_codes_keyboard,
    partner_reference_keyboard,
    skip_photo_keyboard,
)
from .states import (
    BannerCreate,
    BannerEdit,
    BannerPhotoAdd,
    BlockCreate,
    BlockEdit,
    CityCreate,
    CityEdit,
    CategoryCreate,
    CategoryEdit,
    GiveawayCreate,
    GiveawayEdit,
    GiveawayItemCreate,
    GiveawayItemEdit,
    GiveawayItemPhotoAdd,
    GiveawayPhotoAdd,
    OfferCreate,
    OfferEdit,
    OfferPhotoAdd,
    PartnerCreate,
    PartnerEdit,
    PartnerPhotoAdd,
    PrivilegeCodeBulkImport,
    PrivilegeCodeCreate,
    PrivilegeCodeEdit,
    SortOrderManual,
    AdminSearch,
)
from .login_code import LoginCodeClient, LoginCodeError, LoginCodeIdentity
from .web_api import ContentAdminApiClient, WebApiError

logger = logging.getLogger(__name__)
router = Router()
_content_api: ContentAdminApiClient | None = None
_login_code: LoginCodeClient | None = None
_browser_app_public_url = "https://app.bloomclub.ru"


PUBLIC_APP_BUTTON_TEXT = "🌐 Открыть приложение"


def public_onboarding_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=PUBLIC_APP_BUTTON_TEXT)]],
        resize_keyboard=True,
    )


def is_admin_user(user: Any, admin_ids: set[int] | frozenset[int]) -> bool:
    return user is not None and user.id in set(admin_ids)


def is_public_onboarding_event(event: TelegramObject) -> bool:
    if not isinstance(event, Message):
        return False
    text = (event.text or "").strip()
    return text in {"/start", PUBLIC_APP_BUTTON_TEXT}


class AdminOnlyMiddleware(BaseMiddleware):
    def __init__(self, admin_ids: set[int] | frozenset[int]) -> None:
        self._admin_ids = set(admin_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if is_public_onboarding_event(event):
            return await handler(event, data)
        if not is_admin_user(user, self._admin_ids):
            if isinstance(event, Message):
                await event.answer("Нет доступа.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Нет доступа.", show_alert=True)
            return None
        return await handler(event, data)


def get_api(message_or_callback: Message | CallbackQuery) -> ContentAdminApiClient:
    if _content_api is None:
        raise RuntimeError("Content API client is not initialized")
    return _content_api



def get_login_code_client() -> LoginCodeClient:
    if _login_code is None:
        raise RuntimeError("Login code client is not initialized")
    return _login_code


def telegram_display_name(user: Any) -> str | None:
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    display_name = " ".join(str(part).strip() for part in parts if part).strip()
    return display_name or getattr(user, "full_name", None) or None

def is_not_found_error(exc: WebApiError) -> bool:
    return "404:" in str(exc)


def is_conflict_error(exc: WebApiError) -> bool:
    return "409:" in str(exc)


def is_unavailable_error(exc: WebApiError) -> bool:
    lowered = str(exc).lower()
    return any(marker in lowered for marker in ("недоступ", "timeout", "timed out", "network"))


def friendly_api_error(
    exc: WebApiError,
    *,
    not_found: str = "Запись уже удалена или не найдена.",
    conflict: str = "Конфликт данных.",
) -> str:
    if is_unavailable_error(exc):
        return "Сервер временно недоступен. Попробуйте позже."
    if is_not_found_error(exc):
        return not_found
    if is_conflict_error(exc):
        return conflict
    if "405:" in str(exc):
        return "Действие сейчас недоступно. Попробуйте позже."
    return "Не удалось выполнить действие. Попробуйте ещё раз."


def user_error(exc: WebApiError) -> str:
    return friendly_api_error(exc)


def banner_user_error(exc: WebApiError) -> str:
    return friendly_api_error(exc, not_found="Баннер уже отсутствует.")


def privilege_code_user_error(exc: WebApiError) -> str:
    return friendly_api_error(exc, not_found="Код уже отсутствует.", conflict="Код уже существует.")


@router.message(Command("start", "admin"))
async def start(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    if is_admin_user(message.from_user, settings.telegram_admin_ids):
        await message.answer("Админ-бот Bloom Club. Выберите действие.", reply_markup=main_menu())
        return
    await message.answer(
        "Добро пожаловать в Bloom Club. Нажмите кнопку ниже, чтобы открыть приложение и получить код входа.",
        reply_markup=public_onboarding_keyboard(),
    )


@router.message(Command("cancel"))
@router.message(F.text == "❌ Отмена")
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=main_menu())


@router.callback_query(F.data == "finish")
async def finish(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Готово.", reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "back:menu")
async def back_menu(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.answer("Главное меню.", reply_markup=main_menu())
    await callback.answer()


@router.message(F.text == PUBLIC_APP_BUTTON_TEXT)
async def open_browser_app(message: Message) -> None:
    user = message.from_user
    if user is None:
        await message.answer("Не удалось определить пользователя Telegram. Попробуйте позже.")
        return
    identity = LoginCodeIdentity(
        provider="telegram",
        provider_user_id=str(user.id),
        first_name=getattr(user, "first_name", None),
        last_name=getattr(user, "last_name", None),
        username=user.username,
        source="telegram_bot",
    )
    logger.info("Requesting browser app login code for telegram_user_id=%s", user.id)
    try:
        result = await get_login_code_client().create_login_code(identity)
    except LoginCodeError as exc:
        logger.warning("Login Code generation failed for telegram_user_id=%s: %s", user.id, exc)
        await message.answer(str(exc))
        return
    logger.info(
        "Login Code generation success for telegram_user_id=%s expires_in=%s",
        user.id,
        result.expires_in,
    )
    await message.answer("🔐 Ваш код входа:")
    await message.answer(result.login_code)
    await message.answer(
        "Код действует 5 минут.\n"
        "Нажмите кнопку ниже, чтобы открыть приложение.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🌐 Открыть приложение", url=_browser_app_public_url)]]
        ),
    )


@router.message(F.text.in_({"🏠 Управление главной", "🏠 Главная"}))
@router.callback_query(F.data == "home:menu")
async def home_menu(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    await message.answer("🏠 Главная", reply_markup=home_menu_keyboard())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(F.text == "🖼 Баннеры")
@router.callback_query(F.data == "banners:menu")
async def banners_menu(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    await message.answer("Управление баннерами.", reply_markup=banners_menu_keyboard())
    if isinstance(event, CallbackQuery):
        await event.answer()




@router.message(F.text == "📚 Справочники")
@router.callback_query(F.data == "refs:menu")
async def references_menu(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    await message.answer("📚 Справочники Content CMS", reply_markup=references_menu_keyboard())
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.in_({"refs:cities", "refs:categories"}))
async def reference_section(event: CallbackQuery) -> None:
    kind = "cities" if event.data == "refs:cities" else "categories"
    await event.message.answer("🏙 Города" if kind == "cities" else "🏷 Категории", reply_markup=reference_section_keyboard(kind))
    await event.answer()


def reference_name(item: dict[str, Any]) -> str:
    return str(item.get("title") or item.get("name") or f"#{item.get('id', '')}").strip()


def reference_active(item: dict[str, Any]) -> bool:
    return bool(item.get("is_active", item.get("active", True)))


def format_reference(item: dict[str, Any], label: str) -> str:
    lines = [
        f"{label}: {reference_name(item)}",
        f"Статус: {'🟢 Активен' if reference_active(item) else '🔴 Скрыт'}",
    ]
    for key, name in (("slug", "Slug"), ("sort_order", "Порядок отображения"), ("partners_count", "Партнёров"), ("partner_count", "Партнёров"), ("partners_total", "Партнёров")):
        if item.get(key) is not None:
            lines.append(f"{name}: {item.get(key)}")
    return "\n".join(lines)


def reference_payload(data: dict[str, Any], is_category: bool) -> dict[str, Any]:
    title = data.get("title") or data.get("name")
    payload: dict[str, Any] = {"title" if is_category else "name": title, "is_active": data.get("is_active", True), "active": data.get("is_active", True)}
    if is_category:
        payload["name"] = title
    if data.get("slug"):
        payload["slug"] = data.get("slug")
    if data.get("sort_order") is not None:
        payload["sort_order"] = data.get("sort_order")
    return payload


async def show_reference_card(message: Message, prefix: str, item_id: int | str | None, item: dict[str, Any] | None = None) -> None:
    if item_id is None:
        await message.answer("Запись сохранена, но API не вернул ID.", reply_markup=references_menu_keyboard())
        return
    try:
        item = item or (await get_api(message).get_city(item_id) if prefix == "city" else await get_api(message).get_category(item_id))
    except WebApiError as exc:
        await message.answer(f"Не удалось открыть карточку: {user_error(exc)}", reply_markup=references_menu_keyboard())
        return
    label = "Город" if prefix == "city" else "Категория"
    await message.answer(format_reference(item, label), reply_markup=reference_actions_keyboard(prefix, item_id, reference_active(item)))


def reference_delete_error(prefix: str, exc: WebApiError) -> str:
    if "409:" in str(exc):
        return "Нельзя удалить город, пока он используется." if prefix == "city" else "Нельзя удалить категорию, пока она используется."
    return user_error(exc)


SEARCH_FIELDS: dict[str, tuple[str, ...]] = {
    "partners": ("name", "title", "display_name", "description", "address", "phone"),
    "offers": ("title", "name", "description"),
    "banners": ("title", "subtitle"),
    "giveaways": ("title", "name", "description"),
    "giveaway_items": ("title", "name", "description"),
    "city": ("name", "title"),
    "category": ("title", "name"),
    "privilege_codes": ("code", "recipient", "recipient_name", "user", "user_name", "assigned_to", "claimed_by"),
}


def search_matches(item: dict[str, Any], query: str, fields: tuple[str, ...]) -> bool:
    needle = query.casefold().strip()
    if not needle:
        return True
    for field in fields:
        value = item.get(field)
        if value is None:
            continue
        if needle in str(value).casefold():
            return True
    return False


def filter_search_results(items: list[dict[str, Any]], query: str, section: str) -> list[dict[str, Any]]:
    fields = SEARCH_FIELDS[section]
    return [item for item in items if search_matches(item, query, fields)]


def search_back_callback(section: str, data: dict[str, Any] | None = None) -> str:
    data = data or {}
    if section == "offers":
        return f"partner:offers:{data.get('partner_id')}"
    if section == "giveaway_items":
        return f"giveaway:items:list:{data.get('giveaway_id')}"
    if section == "privilege_codes":
        return f"pc:list:{data.get('partner_id')}:{data.get('offer_id')}"
    return {"partners": "partners:list", "banners": "banners:list", "giveaways": "giveaways:list", "city": "city:list", "category": "category:list"}.get(section, "back:menu")


async def load_search_items(event: Message | CallbackQuery, section: str, data: dict[str, Any]) -> list[dict[str, Any]]:
    api = get_api(event)
    if section == "partners":
        return await api.list_partners()
    if section == "offers":
        return await api.list_offers(data["partner_id"])
    if section == "banners":
        return await api.list_banners()
    if section == "giveaways":
        return await api.list_giveaways()
    if section == "giveaway_items":
        return await api.list_giveaway_items(data["giveaway_id"])
    if section == "city":
        return await api.list_cities()
    if section == "category":
        return await api.list_categories()
    if section == "privilege_codes":
        return await api.list_privilege_codes(data["offer_id"])
    return []


async def send_search_results(message: Message, section: str, items: list[dict[str, Any]], data: dict[str, Any], query: str | None = None) -> None:
    prefix = f"Результаты поиска: {query}\n" if query is not None else ""
    if not items:
        await message.answer("❌ Ничего не найдено", reply_markup=search_empty_keyboard(search_back_callback(section, data)))
    elif section == "partners":
        await message.answer(prefix + "Партнёры:", reply_markup=partners_keyboard(items[:50]))
    elif section == "offers":
        await message.answer(prefix + "Услуги партнёра:", reply_markup=offers_keyboard(data["partner_id"], items[:50]))
    elif section == "banners":
        await message.answer(prefix + "Баннеры:", reply_markup=banners_keyboard(items[:50]))
    elif section == "giveaways":
        await message.answer(prefix + "Розыгрыши:", reply_markup=giveaways_keyboard(items[:50]))
    elif section == "giveaway_items":
        await message.answer(prefix + "Призы розыгрыша:", reply_markup=giveaway_items_keyboard(data["giveaway_id"], items[:50]))
    elif section in {"city", "category"}:
        await message.answer(prefix + ("Города:" if section == "city" else "Категории:"), reply_markup=references_keyboard("cities" if section == "city" else "categories", items[:50]))
    elif section == "privilege_codes":
        await message.answer(prefix + "Коды привилегий:", reply_markup=privilege_codes_keyboard(data["partner_id"], data["offer_id"], items[:50]))


@router.callback_query(F.data.startswith("search:start:"))
async def search_start(callback: CallbackQuery, state: FSMContext) -> None:
    parts = callback.data.split(":")
    section = parts[2]
    data: dict[str, Any] = {"section": section}
    if section == "offers":
        data["partner_id"] = parts[3]
    elif section == "giveaway_items":
        data["giveaway_id"] = parts[3]
    elif section == "privilege_codes":
        data.update({"partner_id": parts[3], "offer_id": parts[4]})
    await state.clear()
    await state.update_data(**data)
    await state.set_state(AdminSearch.query)
    await callback.message.answer("Введите запрос")
    await callback.answer()


@router.message(AdminSearch.query)
async def search_query(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    section = data.get("section")
    query = (message.text or "").strip()
    try:
        items = await load_search_items(message, section, data)
        results = filter_search_results(items, query, section)
    except WebApiError as exc:
        await message.answer(f"Не удалось выполнить поиск: {user_error(exc)}", reply_markup=main_menu())
    else:
        await send_search_results(message, section, results, data, query)
    await state.clear()


@router.callback_query(F.data.startswith("search:reset:"))
async def search_reset(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    parts = callback.data.split(":")
    section = parts[2]
    if section == "partners":
        await list_partners(callback)
    elif section == "offers":
        await show_partner_offers(callback.message, parts[3]); await callback.answer()
    elif section == "banners":
        await list_banners(callback)
    elif section == "giveaways":
        await list_giveaways(callback)
    elif section == "giveaway_items":
        await send_giveaway_items_list(callback.message, parts[3]); await callback.answer()
    elif section in {"city", "category"}:
        items = await (get_api(callback).list_cities() if section == "city" else get_api(callback).list_categories())
        await send_search_results(callback.message, section, items, {}, None)
        await callback.answer()
    elif section == "privilege_codes":
        await show_privilege_codes(callback.message, parts[3], parts[4]); await callback.answer()


@router.callback_query(F.data.in_({"city:list", "category:list", "city:sort:list", "category:sort:list"}))
async def reference_list(event: CallbackQuery) -> None:
    is_city = event.data.startswith("city")
    try:
        items = await (get_api(event).list_cities() if is_city else get_api(event).list_categories())
    except WebApiError as exc:
        await event.message.answer(f"Не удалось получить список: {user_error(exc)}", reply_markup=references_menu_keyboard())
    else:
        if not items:
            await event.message.answer("Городов пока нет. Создайте первый город." if is_city else "Категорий пока нет. Создайте первую категорию.", reply_markup=references_keyboard("cities" if is_city else "categories", []))
        else:
            title = "Города:" if is_city else "Категории:"
            lines = [title] + [f"• {reference_name(i)} — {'🟢 Активен' if reference_active(i) else '🔴 Скрыт'} — порядок: {i.get('sort_order', 0)}" for i in items[:50]]
            await event.message.answer("\n".join(lines), reply_markup=references_keyboard("cities" if is_city else "categories", items[:50]))
    await event.answer()


@router.callback_query(F.data.in_({"city:add", "category:add"}))
async def reference_create_start(event: CallbackQuery, state: FSMContext) -> None:
    is_city = event.data.startswith("city")
    await state.clear(); await state.update_data(is_category=not is_city)
    await state.set_state(CityCreate.name if is_city else CategoryCreate.title)
    await event.message.answer("Введите название города:" if is_city else "Введите название категории:")
    await event.answer()


@router.message(CityCreate.name)
@router.message(CategoryCreate.title)
async def reference_create_name(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); is_category = bool(data.get("is_category"))
    value = (message.text or "").strip()
    if not value:
        await message.answer("Название не должно быть пустым."); return
    payload = reference_payload({"title": value, "name": value, "is_active": True}, is_category)
    try:
        item = await (get_api(message).create_category(payload) if is_category else get_api(message).create_city(payload))
    except WebApiError as exc:
        await message.answer(f"Не удалось создать справочник: {user_error(exc)}", reply_markup=references_menu_keyboard())
        await state.clear()
        return
    await state.clear()
    await show_reference_card(message, "category" if is_category else "city", item.get("id"), item)


@router.message(CityCreate.slug)
@router.message(CategoryCreate.slug)
async def reference_create_slug(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); is_category = bool(data.get("is_category"))
    await state.update_data(slug=normalize_optional_text(message.text))
    await state.set_state(CategoryCreate.sort_order if is_category else CityCreate.sort_order)
    await message.answer("Введите порядок сортировки числом или «-», если не нужен:")


@router.message(CityCreate.sort_order)
@router.message(CategoryCreate.sort_order)
async def reference_create_sort(message: Message, state: FSMContext) -> None:
    value = parse_optional_int(message.text)
    if value is None and normalize_optional_text(message.text) is not None:
        await message.answer("Введите целое число или «-»."); return
    data = await state.get_data(); is_category = bool(data.get("is_category"))
    await state.update_data(sort_order=value)
    await state.set_state(CategoryCreate.is_active if is_category else CityCreate.is_active)
    await message.answer("Опубликовать сразу? Введите да/нет:")


@router.message(CityCreate.is_active)
@router.message(CategoryCreate.is_active)
async def reference_create_active(message: Message, state: FSMContext) -> None:
    active = parse_bool_text(message.text)
    if active is None:
        await message.answer("Введите да или нет."); return
    data = await state.get_data(); is_category = bool(data.get("is_category")); data["is_active"] = active
    try:
        item = await (get_api(message).create_category(reference_payload(data, True)) if is_category else get_api(message).create_city(reference_payload(data, False)))
    except WebApiError as exc:
        await message.answer(f"Не удалось создать справочник: {user_error(exc)}", reply_markup=references_menu_keyboard()); await state.clear(); return
    await state.clear()
    item_id = item.get("id")
    prefix = "category" if is_category else "city"
    await message.answer("Категория создана." if is_category else "Город создан.", reply_markup=reference_actions_keyboard(prefix, item_id, reference_active(item)))


@router.callback_query(F.data.startswith("city:view:") | F.data.startswith("category:view:"))
async def reference_view(event: CallbackQuery) -> None:
    prefix, _, item_id = event.data.split(":", 2)
    item = await (get_api(event).get_city(item_id) if prefix == "city" else get_api(event).get_category(item_id))
    if not item:
        await event.message.answer("Запись не найдена.", reply_markup=references_menu_keyboard())
    else:
        await event.message.answer(format_reference(item, "Город" if prefix == "city" else "Категория"), reply_markup=reference_actions_keyboard(prefix, item_id, reference_active(item)))
    await event.answer()


@router.callback_query(F.data.startswith("city:edit:") | F.data.startswith("category:edit:"))
async def reference_edit(event: CallbackQuery) -> None:
    prefix, _, item_id = event.data.split(":", 2)
    await event.message.answer("Что изменить?", reply_markup=reference_edit_keyboard(prefix, item_id)); await event.answer()


@router.callback_query(F.data.startswith("city:edit_field:") | F.data.startswith("category:edit_field:"))
async def reference_edit_field(event: CallbackQuery, state: FSMContext) -> None:
    prefix, _, _, item_id, field = event.data.split(":", 4)
    await state.clear(); await state.update_data(prefix=prefix, item_id=item_id, field=field)
    states = {("city", "name"): CityEdit.name, ("city", "sort_order"): CityEdit.sort_order, ("city", "is_active"): CityEdit.sort_order, ("category", "title"): CategoryEdit.title, ("category", "sort_order"): CategoryEdit.sort_order, ("category", "is_active"): CategoryEdit.sort_order}
    await state.set_state(states[(prefix, field)])
    await event.message.answer("Введите новое значение или «-», чтобы очистить:" if field != "name" and field != "title" else "Введите новое название:")
    await event.answer()


@router.message(CityEdit.name)
@router.message(CityEdit.slug)
@router.message(CityEdit.sort_order)
@router.message(CategoryEdit.title)
@router.message(CategoryEdit.slug)
@router.message(CategoryEdit.sort_order)
async def reference_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); field = data["field"]; prefix = data["prefix"]
    if field == "sort_order":
        value = parse_optional_int(message.text)
        if value is None:
            await message.answer("Введите целое число."); return
    elif field == "is_active":
        value = parse_bool_text(message.text)
        if value is None:
            await message.answer("Введите да/нет, показать/скрыть или 1/0."); return
    elif field in {"name", "title"}:
        value = (message.text or "").strip()
        if not value:
            await message.answer("Название не должно быть пустым."); return
    else:
        value = normalize_optional_text(message.text)
    payload = {field: value}
    if prefix == "category" and field == "title":
        payload["name"] = value
    try:
        item = await (get_api(message).update_city(data["item_id"], payload) if prefix == "city" else get_api(message).update_category(data["item_id"], payload))
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить запись: {user_error(exc)}", reply_markup=references_menu_keyboard())
        await state.clear()
    else:
        await state.clear()
        await show_reference_card(message, prefix, data["item_id"], item)


@router.callback_query(F.data.startswith("city:hide:") | F.data.startswith("city:publish:") | F.data.startswith("category:hide:") | F.data.startswith("category:publish:"))
async def reference_toggle(event: CallbackQuery) -> None:
    prefix, action, item_id = event.data.split(":", 2)
    publish = action == "publish"
    try:
        item = await (get_api(event).publish_city(item_id) if prefix == "city" and publish else get_api(event).hide_city(item_id) if prefix == "city" else get_api(event).publish_category(item_id) if publish else get_api(event).hide_category(item_id))
    except WebApiError as exc:
        await event.message.answer(f"Не удалось изменить статус: {user_error(exc)}")
    else:
        await show_reference_card(event.message, prefix, item_id, item)
    await event.answer()


@router.callback_query(F.data.startswith("city:sort:menu:") | F.data.startswith("category:sort:menu:"))
async def reference_sort_menu(callback: CallbackQuery) -> None:
    prefix, _, _, item_id = callback.data.split(":", 3)
    try:
        item = await (get_api(callback).get_city(item_id) if prefix == "city" else get_api(callback).get_category(item_id))
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить запись: {user_error(exc)}")
    else:
        current = item_sort_order(item)
        await callback.message.answer(f"Текущий порядок:\n\n{current}", reply_markup=sort_order_keyboard(prefix, item_id, current, f"{prefix}:view:{item_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("city:sort:move:") | F.data.startswith("category:sort:move:"))
async def reference_sort_move(callback: CallbackQuery) -> None:
    prefix, _, _, item_id, delta_raw = callback.data.split(":", 4)
    try:
        item = await (get_api(callback).get_city(item_id) if prefix == "city" else get_api(callback).get_category(item_id))
        payload = {"sort_order": item_sort_order(item) + int(delta_raw)}
        item = await (get_api(callback).update_city(item_id, payload) if prefix == "city" else get_api(callback).update_category(item_id, payload))
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить порядок: {user_error(exc)}")
    else:
        await show_reference_card(callback.message, prefix, item_id, item)
    await callback.answer()


@router.callback_query(F.data.startswith("city:sort:manual:") | F.data.startswith("category:sort:manual:"))
async def reference_sort_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    prefix = callback.data.split(":", 1)[0]
    item_id = callback.data.split(":", 3)[3]
    await state.clear(); await state.update_data(kind=prefix, item_id=item_id); await state.set_state(SortOrderManual.value)
    await callback.message.answer("Введите порядок отображения числом:")
    await callback.answer()


@router.callback_query(F.data.startswith("city:delete:confirm:") | F.data.startswith("category:delete:confirm:"))
async def reference_delete_confirm(callback: CallbackQuery) -> None:
    prefix = callback.data.split(":", 1)[0]
    item_id = callback.data.split(":", 3)[3]
    await callback.message.answer("Удалить город?" if prefix == "city" else "Удалить категорию?", reply_markup=reference_delete_confirm_keyboard(prefix, item_id))
    await callback.answer()


@router.callback_query(F.data.startswith("city:delete:yes:") | F.data.startswith("category:delete:yes:"))
async def reference_delete_yes(callback: CallbackQuery) -> None:
    prefix = callback.data.split(":", 1)[0]
    item_id = callback.data.split(":", 3)[3]
    try:
        await (get_api(callback).delete_city(item_id) if prefix == "city" else get_api(callback).delete_category(item_id))
    except WebApiError as exc:
        await callback.message.answer(reference_delete_error(prefix, exc), reply_markup=references_menu_keyboard())
    else:
        await callback.message.answer("Запись удалена." if prefix == "city" else "Категория удалена.")
        await reference_list(callback)
        return
    await callback.answer()

@router.message(F.text == "🎁 Создать розыгрыш")
@router.callback_query(F.data == "giveaway:add")
async def create_giveaway_start(event: Message | CallbackQuery, state: FSMContext) -> None:
    message = event if isinstance(event, Message) else event.message
    await state.clear()
    await state.set_state(GiveawayCreate.title)
    await message.answer("Введите название розыгрыша:")
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.message(GiveawayCreate.title)
async def giveaway_create_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(GiveawayCreate.description)
    await message.answer("Введите описание розыгрыша:")


@router.message(GiveawayCreate.description)
async def giveaway_create_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(GiveawayCreate.terms)
    await message.answer("Введите условия участия:")


@router.message(GiveawayCreate.terms)
async def giveaway_create_terms(message: Message, state: FSMContext) -> None:
    await state.update_data(terms=(message.text or "").strip())
    await state.set_state(GiveawayCreate.starts_at)
    await message.answer("Введите дату начала в формате ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ:")


@router.message(GiveawayCreate.starts_at)
async def giveaway_create_starts_at(message: Message, state: FSMContext) -> None:
    value = parse_admin_date(message.text)
    if value is None:
        await message.answer(INVALID_DATE_MESSAGE)
        return
    await state.update_data(starts_at=value)
    await state.set_state(GiveawayCreate.ends_at)
    await message.answer("Введите дату окончания в формате ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ:")


@router.message(GiveawayCreate.ends_at)
async def giveaway_create_ends_at(message: Message, state: FSMContext) -> None:
    value = parse_admin_date(message.text)
    if value is None:
        await message.answer(INVALID_DATE_MESSAGE)
        return
    await state.update_data(ends_at=value)
    await state.set_state(GiveawayCreate.photo)
    await message.answer("Отправьте фото розыгрыша или нажмите «Пропустить».", reply_markup=skip_photo_keyboard())


@router.callback_query(GiveawayCreate.photo, F.data == "skip_photo")
async def giveaway_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_giveaway(callback.message, state, None)
    await callback.answer()


@router.message(GiveawayCreate.photo)
async def giveaway_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    await finalize_giveaway(message, state, url)


async def finalize_giveaway(message: Message, state: FSMContext, photo_url: str | None) -> None:
    api = get_api(message)
    data = await state.get_data()
    payload = giveaway_payload(data, photo_url)
    try:
        giveaway = await api.create_giveaway(payload)
        giveaway_id = giveaway.get("id")
        if giveaway_id is None:
            raise WebApiError("WEB API не вернул id созданного розыгрыша.")
        if photo_url:
            try:
                await api.add_giveaway_photo(giveaway_id, photo_url)
            except WebApiError:
                logger.info("Giveaway photo endpoint is unavailable; photo URL stayed in giveaway payload.")
    except WebApiError as exc:
        await state.clear()
        await message.answer(f"Не удалось создать розыгрыш: {user_error(exc)}", reply_markup=main_menu())
        return
    await state.clear()
    await send_giveaway_card(message, giveaway_id)


@router.message(F.text == "📋 Список розыгрышей")
@router.callback_query(F.data == "giveaways:list")
async def list_giveaways(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    try:
        giveaways = await get_api(event).list_giveaways()
    except WebApiError as exc:
        await message.answer(f"Не удалось получить список розыгрышей: {user_error(exc)}", reply_markup=main_menu())
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    if not giveaways:
        await message.answer("Розыгрышей пока нет.", reply_markup=giveaways_keyboard([]))
    else:
        lines = ["Розыгрыши:"]
        for giveaway in giveaways[:50]:
            title = giveaway_title(giveaway)
            status = giveaway_status(giveaway)
            period = giveaway_period(giveaway)
            prizes = giveaway_prize_count(giveaway)
            order = giveaway.get("sort_order")
            lines.append(f"• {title} — {status}{period} — призов: {prizes}" + (f" — порядок: {order}" if order is not None else ""))
        await message.answer("\n".join(lines), reply_markup=giveaways_keyboard(giveaways[:50]))
    if isinstance(event, CallbackQuery):
        await event.answer()


@router.callback_query(F.data.startswith("giveaway:view:"))
async def giveaway_view(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 2)[2]
    try:
        giveaway = await get_api(callback).get_giveaway(giveaway_id)
    except WebApiError:
        giveaways = await get_api(callback).list_giveaways()
        giveaway = next((item for item in giveaways if str(item.get("id")) == str(giveaway_id)), {})
    if not giveaway:
        await callback.message.answer("Розыгрыш не найден.", reply_markup=main_menu())
    else:
        await callback.message.answer(format_giveaway(giveaway), reply_markup=giveaway_actions_keyboard(giveaway_id, giveaway_active(giveaway)))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:items:menu:"))
async def giveaway_items_menu(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    await callback.message.answer("Управление призами розыгрыша.", reply_markup=giveaway_items_menu_keyboard(giveaway_id))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:items:list:"))
async def giveaway_items_list(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    try:
        items = await get_api(callback).list_giveaway_items(giveaway_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить призы: {user_error(exc)}", reply_markup=giveaway_items_menu_keyboard(giveaway_id))
        await callback.answer()
        return
    if not items:
        await callback.message.answer("У этого розыгрыша пока нет призов. Добавьте первый приз.", reply_markup=giveaway_items_keyboard(giveaway_id, []))
    else:
        lines = ["Призы розыгрыша:"]
        for item in items[:50]:
            title = giveaway_item_title(item)
            active = "активен" if giveaway_item_active(item) else "скрыт"
            order = item.get("sort_order")
            lines.append(f"• {title} — {active}" + (f" — порядок {order}" if order is not None else ""))
        await callback.message.answer("\n".join(lines), reply_markup=giveaway_items_keyboard(giveaway_id, items[:50]))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:item:view:"))
async def giveaway_item_view(callback: CallbackQuery) -> None:
    _, _, _, giveaway_id, item_id = callback.data.split(":", 4)
    try:
        item = await get_api(callback).get_giveaway_item(item_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось открыть приз: {user_error(exc)}", reply_markup=giveaway_items_keyboard(giveaway_id, []))
        await callback.answer()
        return
    await callback.message.answer(format_giveaway_item(item), reply_markup=giveaway_item_actions_keyboard(giveaway_id, item_id, giveaway_item_active(item)))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:item:add:"))
async def giveaway_item_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    await state.clear()
    await state.update_data(giveaway_id=giveaway_id)
    await state.set_state(GiveawayItemCreate.title)
    await callback.message.answer("Введите название приза:")
    await callback.answer()


@router.message(GiveawayItemCreate.title)
async def giveaway_item_create_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(GiveawayItemCreate.description)
    await message.answer("Введите описание приза:")


@router.message(GiveawayItemCreate.description)
async def giveaway_item_create_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(GiveawayItemCreate.sort_order)
    await message.answer("Введите порядок сортировки числом или «-», если не нужен:")


@router.message(GiveawayItemCreate.sort_order)
async def giveaway_item_create_sort_order(message: Message, state: FSMContext) -> None:
    sort_order = parse_optional_int(message.text)
    if sort_order is None and normalize_optional_text(message.text) is not None:
        await message.answer("Введите целое число или «-».")
        return
    await state.update_data(sort_order=sort_order)
    await state.set_state(GiveawayItemCreate.photo)
    await message.answer("Отправьте фото приза или нажмите «Пропустить».", reply_markup=skip_photo_keyboard())


@router.callback_query(GiveawayItemCreate.photo, F.data == "skip_photo")
async def giveaway_item_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_giveaway_item(callback.message, state, None)
    await callback.answer()


@router.message(GiveawayItemCreate.photo)
async def giveaway_item_create_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    await finalize_giveaway_item(message, state, url)


async def finalize_giveaway_item(message: Message, state: FSMContext, photo_url: str | None) -> None:
    data = await state.get_data()
    giveaway_id = data.get("giveaway_id")
    payload = giveaway_item_payload(data, photo_url)
    try:
        item = await get_api(message).create_giveaway_item(giveaway_id, payload)
        item_id = item.get("id")
        if item_id is None:
            raise WebApiError("WEB API не вернул id созданного приза.")
    except WebApiError as exc:
        await state.clear()
        await message.answer(f"Не удалось создать приз: {user_error(exc)}", reply_markup=giveaway_items_menu_keyboard(giveaway_id))
        return
    await state.clear()
    await send_giveaway_items_list(message, giveaway_id)


@router.callback_query(F.data.startswith("giveaway:item:edit:"))
async def giveaway_item_edit(callback: CallbackQuery) -> None:
    _, _, _, giveaway_id, item_id = callback.data.split(":", 4)
    await callback.message.answer("Что изменить?", reply_markup=giveaway_item_edit_keyboard(giveaway_id, item_id))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:item:edit_field:"))
async def giveaway_item_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, giveaway_id, item_id, field = callback.data.split(":", 5)
    states = {"title": GiveawayItemEdit.title, "description": GiveawayItemEdit.description, "sort_order": GiveawayItemEdit.sort_order, "is_active": GiveawayItemEdit.title}
    prompts = {"title": "Введите новое название приза:", "description": "Введите новое описание приза:", "sort_order": "Введите новый порядок сортировки числом или «-», чтобы очистить:", "is_active": "Введите статус: 1/да/активен или 0/нет/скрыт:"}
    await state.clear()
    await state.update_data(giveaway_id=giveaway_id, item_id=item_id, field=field)
    await state.set_state(states[field])
    await callback.message.answer(prompts[field])
    await callback.answer()


@router.message(GiveawayItemEdit.title)
@router.message(GiveawayItemEdit.description)
@router.message(GiveawayItemEdit.sort_order)
async def giveaway_item_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    if field == "sort_order":
        value = parse_optional_int(message.text)
        if value is None and normalize_optional_text(message.text) is not None:
            await message.answer("Введите целое число или «-».")
            return
    elif field == "is_active":
        value = parse_bool_text(message.text)
        if value is None:
            await message.answer("Введите 1/да/активен или 0/нет/скрыт.")
            return
    else:
        value = (message.text or "").strip()
    try:
        item = await get_api(message).update_giveaway_item(data["item_id"], {field: value})
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить приз: {user_error(exc)}", reply_markup=giveaway_items_menu_keyboard(data["giveaway_id"]))
    else:
        await callback_safe_item_card_message(message, data["giveaway_id"], data["item_id"], item)
    await state.clear()


@router.callback_query(F.data.startswith("giveaway:item:toggle:"))
async def giveaway_item_toggle(callback: CallbackQuery) -> None:
    _, _, _, giveaway_id, item_id, active_raw = callback.data.split(":", 5)
    active = bool(int(active_raw))
    try:
        if active:
            await get_api(callback).publish_giveaway_item(item_id)
        else:
            await get_api(callback).hide_giveaway_item(item_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус приза: {user_error(exc)}")
    else:
        await callback.message.answer("Приз опубликован." if active else "Приз скрыт.", reply_markup=giveaway_item_actions_keyboard(giveaway_id, item_id, active))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:item:photo:"))
async def giveaway_item_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, giveaway_id, item_id = callback.data.split(":", 4)
    await state.clear()
    await state.update_data(giveaway_id=giveaway_id, item_id=item_id)
    await state.set_state(GiveawayItemPhotoAdd.photo)
    await callback.message.answer("Отправьте фото приза jpg/png/webp до 10 MB.")
    await callback.answer()


@router.message(GiveawayItemPhotoAdd.photo)
async def giveaway_item_photo_save(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    data = await state.get_data()
    try:
        item = await get_api(message).update_giveaway_item(data["item_id"], {"image_url": url})
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить фото приза: {user_error(exc)}", reply_markup=giveaway_items_menu_keyboard(data["giveaway_id"]))
    else:
        await message.answer("Фото приза обновлено.", reply_markup=giveaway_item_actions_keyboard(data["giveaway_id"], data["item_id"], giveaway_item_active(item)))
    await state.clear()


@router.callback_query(F.data.startswith("giveaway:edit:"))
async def giveaway_edit(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 2)[2]
    await callback.message.answer("Что изменить?", reply_markup=giveaway_edit_keyboard(giveaway_id))
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:edit_field:"))
async def giveaway_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, giveaway_id, field = callback.data.split(":", 3)
    states = {
        "title": GiveawayEdit.title,
        "description": GiveawayEdit.description,
        "terms": GiveawayEdit.terms,
        "starts_at": GiveawayEdit.starts_at,
        "ends_at": GiveawayEdit.ends_at,
        "is_active": GiveawayEdit.title,
        "sort_order": GiveawayEdit.title,
    }
    prompts = {
        "title": "Введите новое название:",
        "description": "Введите новое описание:",
        "terms": "Введите новые условия:",
        "starts_at": "Введите новую дату начала или «-», чтобы очистить:",
        "ends_at": "Введите новую дату окончания в формате ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ:",
        "is_active": "Введите статус: 1/да/активен или 0/нет/скрыт:",
        "sort_order": "Введите sort_order числом или «-», чтобы очистить:",
    }
    await state.clear()
    await state.update_data(giveaway_id=giveaway_id, field=field)
    await state.set_state(states[field])
    await callback.message.answer(prompts[field])
    await callback.answer()


@router.message(GiveawayEdit.title)
@router.message(GiveawayEdit.description)
@router.message(GiveawayEdit.terms)
@router.message(GiveawayEdit.starts_at)
@router.message(GiveawayEdit.ends_at)
async def giveaway_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data["field"]
    value = (message.text or "").strip()
    if field in {"starts_at", "ends_at"}:
        value = parse_admin_date(value)
        if value is None:
            await message.answer(INVALID_DATE_MESSAGE)
            return
    elif field == "sort_order":
        value = parse_optional_int(value)
        if value is None and normalize_optional_text(message.text) is not None:
            await message.answer("Введите целое число или «-».")
            return
    elif field == "is_active":
        value = parse_bool_text(value)
        if value is None:
            await message.answer("Введите 1/да/активен или 0/нет/скрыт.")
            return
    payload = giveaway_update_payload(field, value)
    try:
        await get_api(message).update_giveaway(data["giveaway_id"], payload)
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить розыгрыш: {user_error(exc)}", reply_markup=main_menu())
    else:
        await send_giveaway_card(message, data["giveaway_id"])
    await state.clear()


@router.callback_query(F.data.startswith("giveaway:toggle:"))
async def giveaway_toggle(callback: CallbackQuery) -> None:
    _, _, giveaway_id, active_raw = callback.data.split(":", 3)
    active = bool(int(active_raw))
    try:
        if active:
            await get_api(callback).publish_giveaway(giveaway_id)
        else:
            await get_api(callback).hide_giveaway(giveaway_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус розыгрыша: {user_error(exc)}")
    else:
        await send_giveaway_card(callback.message, giveaway_id)
    await callback.answer()


@router.callback_query(F.data.startswith("giveaway:photo:menu:"))
async def giveaway_photo_menu(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    try:
        giveaway = await get_api(callback).get_giveaway(giveaway_id)
        photos = []
        try:
            photos = await get_api(callback).list_giveaway_photos(giveaway_id)
        except WebApiError:
            photos = []
        has_photo = bool(photos or giveaway.get("photo_url") or giveaway.get("image_url"))
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось открыть фото: {user_error(exc)}")
    else:
        await callback.message.answer("Фото отсутствует." if not has_photo else "Фото розыгрыша.", reply_markup=giveaway_photo_keyboard(giveaway_id, has_photo))
    await callback.answer()

@router.callback_query(F.data.startswith("giveaway:photo:delete:"))
async def giveaway_photo_delete(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    try:
        photos = []
        try:
            photos = await get_api(callback).list_giveaway_photos(giveaway_id)
        except WebApiError:
            photos = []
        if photos:
            for photo in photos:
                photo_id = photo.get("id")
                if photo_id is not None:
                    await get_api(callback).delete_giveaway_photo(photo_id)
        else:
            await get_api(callback).update_giveaway(giveaway_id, {"photo_url": None, "image_url": None, "url": None})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить фото: {user_error(exc)}")
    else:
        await send_giveaway_card(callback.message, giveaway_id)
    await callback.answer()

@router.callback_query(F.data.startswith("giveaway:delete:confirm:"))
async def giveaway_delete_confirm(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    await callback.message.answer("Удалить розыгрыш?", reply_markup=giveaway_delete_confirm_keyboard(giveaway_id))
    await callback.answer()

@router.callback_query(F.data.startswith("giveaway:delete:yes:"))
async def giveaway_delete_yes(callback: CallbackQuery) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    try:
        await get_api(callback).delete_giveaway(giveaway_id)
    except WebApiError as exc:
        if "404:" not in str(exc):
            await callback.message.answer(f"Не удалось удалить розыгрыш: {user_error(exc)}")
            await callback.answer(); return
    await list_giveaways(callback)

@router.callback_query(F.data.startswith("giveaway:item:delete:confirm:"))
async def giveaway_item_delete_confirm(callback: CallbackQuery) -> None:
    _, _, _, _, giveaway_id, item_id = callback.data.split(":", 5)
    await callback.message.answer("Удалить приз?", reply_markup=giveaway_item_delete_confirm_keyboard(giveaway_id, item_id))
    await callback.answer()

@router.callback_query(F.data.startswith("giveaway:item:delete:yes:"))
async def giveaway_item_delete_yes(callback: CallbackQuery) -> None:
    _, _, _, _, giveaway_id, item_id = callback.data.split(":", 5)
    try:
        await get_api(callback).delete_giveaway_item(item_id)
    except WebApiError as exc:
        if "404:" not in str(exc):
            await callback.message.answer(f"Не удалось удалить приз: {user_error(exc)}")
            await callback.answer(); return
    await send_giveaway_items_list(callback.message, giveaway_id)
    await callback.answer()

@router.callback_query(F.data.startswith("giveaway:photo:add:"))
async def giveaway_photo_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    giveaway_id = callback.data.split(":", 3)[3]
    await state.clear()
    await state.update_data(giveaway_id=giveaway_id)
    await state.set_state(GiveawayPhotoAdd.photo)
    await callback.message.answer("Отправьте фото розыгрыша.")
    await callback.answer()


@router.message(GiveawayPhotoAdd.photo)
async def giveaway_photo_add(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    giveaway_id = (await state.get_data()).get("giveaway_id")
    try:
        try:
            await get_api(message).add_giveaway_photo(giveaway_id, url)
        except WebApiError:
            await get_api(message).update_giveaway(giveaway_id, giveaway_photo_payload(url))
    except WebApiError as exc:
        await message.answer(f"Не удалось добавить фото розыгрыша: {user_error(exc)}", reply_markup=main_menu())
    else:
        await send_giveaway_card(message, giveaway_id)
    await state.clear()


@router.message(F.text == "➕ Создать партнёра")
async def create_partner_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PartnerCreate.name)
    await message.answer("Введите название партнёра:")


@router.message(PartnerCreate.name)
async def partner_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await state.set_state(PartnerCreate.description)
    await message.answer("Введите описание партнёра:")


@router.message(PartnerCreate.description)
async def partner_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(PartnerCreate.city)
    await send_partner_city_choices(message)


async def send_partner_city_choices(message: Message) -> None:
    try:
        cities = await get_api(message).list_cities()
    except WebApiError as exc:
        await message.answer(f"Не удалось загрузить города: {user_error(exc)}", reply_markup=main_menu())
        return
    if not cities:
        await message.answer("В справочнике нет городов. Сначала добавьте город в разделе «Справочники».", reply_markup=main_menu())
        return
    await message.answer("Выберите город:", reply_markup=partner_reference_keyboard("cities", cities))


@router.callback_query(PartnerCreate.city, F.data.startswith("partner_city:select:"))
async def partner_city_selected(callback: CallbackQuery, state: FSMContext) -> None:
    city_id = callback.data.split(":", 2)[2]
    try:
        city = await get_api(callback).get_city(city_id)
    except WebApiError as exc:
        await state.clear()
        await callback.message.answer(f"Не удалось загрузить город: {user_error(exc)}", reply_markup=main_menu())
        await callback.answer()
        return
    await state.update_data(city_id=city_id, city=city.get("name") or city.get("title"))
    await state.set_state(PartnerCreate.category)
    await send_partner_category_choices(callback.message)
    await callback.answer()


@router.message(PartnerCreate.city)
async def partner_city(message: Message) -> None:
    await message.answer("Пожалуйста, выберите город кнопкой из справочника.")


async def send_partner_category_choices(message: Message) -> None:
    try:
        categories = await get_api(message).list_categories()
    except WebApiError as exc:
        await message.answer(f"Не удалось загрузить категории: {user_error(exc)}", reply_markup=main_menu())
        return
    if not categories:
        await message.answer("В справочнике нет категорий. Сначала добавьте категорию в разделе «Справочники».", reply_markup=main_menu())
        return
    await message.answer("Выберите категорию:", reply_markup=partner_reference_keyboard("categories", categories))


@router.callback_query(PartnerCreate.category, F.data.startswith("partner_category:select:"))
async def partner_category_selected(callback: CallbackQuery, state: FSMContext) -> None:
    category_id = callback.data.split(":", 2)[2]
    try:
        category = await get_api(callback).get_category(category_id)
    except WebApiError as exc:
        await state.clear()
        await callback.message.answer(f"Не удалось загрузить категорию: {user_error(exc)}", reply_markup=main_menu())
        await callback.answer()
        return
    await state.update_data(category_id=category_id, category=category.get("title") or category.get("name"))
    await state.set_state(PartnerCreate.address)
    await callback.message.answer("Введите адрес:")
    await callback.answer()


@router.message(PartnerCreate.category)
async def partner_category(message: Message) -> None:
    await message.answer("Пожалуйста, выберите категорию кнопкой из справочника.")


@router.message(PartnerCreate.address)
async def partner_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=(message.text or "").strip())
    await state.set_state(PartnerCreate.phone)
    await message.answer("Введите телефон:")


@router.message(PartnerCreate.phone)
async def partner_phone(message: Message, state: FSMContext) -> None:
    await state.update_data(phone=(message.text or "").strip())
    await state.set_state(PartnerCreate.photo)
    await message.answer("Отправьте фото партнёра или нажмите «Пропустить».", reply_markup=skip_photo_keyboard())


@router.callback_query(PartnerCreate.photo, F.data == "skip_photo")
async def partner_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_partner(callback.message, state, None)
    await callback.answer()


@router.message(PartnerCreate.photo)
async def partner_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    await finalize_partner(message, state, url)


async def finalize_partner(message: Message, state: FSMContext, photo_url: str | None) -> None:
    api = get_api(message)
    data = await state.get_data()
    payload = {
        "name": data.get("name"),
        "title": data.get("name"),
        "description": data.get("description"),
        "city_id": data.get("city_id"),
        "category_id": data.get("category_id"),
        "address": data.get("address"),
        "phone": data.get("phone"),
        "is_active": True,
    }
    try:
        partner = await api.create_partner(payload)
        partner_id = partner.get("id")
        if partner_id is None:
            raise WebApiError("WEB API не вернул id созданного партнёра.")
        if photo_url:
            await api.add_partner_photo(partner_id, photo_url)
    except WebApiError as exc:
        await state.clear()
        await message.answer(f"Не удалось создать партнёра: {user_error(exc)}", reply_markup=main_menu())
        return
    await state.clear()
    await message.answer("Партнёр создан. Хотите добавить услугу?", reply_markup=after_partner_keyboard(partner_id))


@router.callback_query(F.data.startswith("offer:add:"))
async def add_offer_start(callback: CallbackQuery, state: FSMContext) -> None:
    partner_id = callback.data.split(":", 2)[2]
    await state.clear()
    await state.update_data(partner_id=partner_id)
    await state.set_state(OfferCreate.title)
    await callback.message.answer("Введите название услуги:")
    await callback.answer()


@router.message(OfferCreate.title)
async def offer_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(OfferCreate.description)
    await message.answer("Введите описание услуги:")


@router.message(OfferCreate.description)
async def offer_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=(message.text or "").strip())
    await state.set_state(OfferCreate.terms)
    await message.answer("Введите условия получения услуги:")


@router.message(OfferCreate.terms)
async def offer_terms(message: Message, state: FSMContext) -> None:
    await state.update_data(terms=(message.text or "").strip())
    await state.set_state(OfferCreate.regular_price)
    await message.answer("Введите цену числом:")


@router.message(OfferCreate.regular_price)
async def offer_regular_price(message: Message, state: FSMContext) -> None:
    price = parse_price(message.text)
    if price is None:
        await message.answer("Введите цену числом, например 2500.")
        return
    await state.update_data(regular_price=price)
    await state.set_state(OfferCreate.club_price)
    await message.answer("Введите старую цену числом или «-», чтобы пропустить:")


@router.message(OfferCreate.club_price)
async def offer_club_price(message: Message, state: FSMContext) -> None:
    if normalize_optional_text(message.text) is None:
        await state.update_data(club_price=None)
        await state.set_state(OfferCreate.savings)
        await message.answer("Введите размер скидки числом:")
        return
    price = parse_price(message.text)
    if price is None:
        await message.answer("Введите старую цену числом или «-», чтобы пропустить.")
        return
    await state.update_data(club_price=price)
    await state.set_state(OfferCreate.savings)
    await message.answer("Введите размер скидки числом:")


@router.message(OfferCreate.savings)
async def offer_savings(message: Message, state: FSMContext) -> None:
    savings = parse_price(message.text)
    if savings is None:
        await message.answer("Введите размер скидки числом, например 500.")
        return
    await state.update_data(savings=savings)
    await state.set_state(OfferCreate.photo)
    await message.answer("Отправьте фото услуги или нажмите «Пропустить».", reply_markup=skip_photo_keyboard())


@router.callback_query(OfferCreate.photo, F.data == "skip_photo")
async def offer_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_offer(callback.message, state, None)
    await callback.answer()


@router.message(OfferCreate.photo)
async def offer_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    await finalize_offer(message, state, url)


async def finalize_offer(message: Message, state: FSMContext, photo_url: str | None) -> None:
    api = get_api(message)
    data = await state.get_data()
    partner_id = data.get("partner_id")
    payload = {
        "title": data.get("title"),
        "name": data.get("title"),
        "description": data.get("description"),
        "regular_price": data.get("regular_price"),
        "club_price": data.get("club_price"),
        "discount_price": data.get("club_price"),
        "savings": data.get("savings"),
        "terms": data.get("terms"),
        "is_active": True,
    }
    try:
        offer = await api.create_offer(partner_id, payload)
        offer_id = offer.get("id")
        if offer_id is None:
            raise WebApiError("WEB API не вернул id созданной услуги.")
        if photo_url:
            await api.add_offer_photo(offer_id, photo_url)
    except WebApiError as exc:
        await state.clear()
        await message.answer(f"Не удалось добавить услугу: {user_error(exc)}", reply_markup=main_menu())
        return
    await state.clear()
    await message.answer("Услуга добавлена.")
    await show_partner_offers(message, partner_id)


def partner_display_name(partner: dict[str, Any]) -> str:
    return str(partner.get("name") or partner.get("title") or "Без названия").strip() or "Без названия"


async def find_partner_by_id(api: ContentAdminApiClient, partner_id: int | str) -> dict[str, Any] | None:
    partners = await api.list_partners()
    return next((p for p in partners if str(p.get("id")) == str(partner_id)), None)

@router.message(F.text == "📋 Список партнёров")
@router.callback_query(F.data == "partners:list")
async def list_partners(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    api = get_api(event)
    try:
        partners = await api.list_partners()
    except WebApiError as exc:
        await message.answer(f"Не удалось получить список партнёров: {user_error(exc)}", reply_markup=main_menu())
        if isinstance(event, CallbackQuery):
            await event.answer()
        return
    if not partners:
        await message.answer("Партнёров пока нет.", reply_markup=main_menu())
    else:
        lines = ["Партнёры:"]
        for partner in partners[:50]:
            name = partner_display_name(partner)
            city = partner.get("city") or "город не указан"
            active = "активен" if bool(partner.get("is_active", partner.get("active", True))) else "скрыт"
            lines.append(f"• {name} — {city} — {active}")
        await message.answer("\n".join(lines), reply_markup=partners_keyboard(partners[:50]))
    if isinstance(event, CallbackQuery):
        await event.answer()



def item_sort_order(item: dict[str, Any] | None) -> int:
    if not item:
        return 0
    try:
        return int(item.get("sort_order") or 0)
    except (TypeError, ValueError):
        return 0


async def find_offer_by_id(api: ContentAdminApiClient, partner_id: int | str, offer_id: int | str) -> dict[str, Any] | None:
    offers = await api.list_offers(partner_id)
    return next((offer for offer in offers if str(offer.get("id")) == str(offer_id)), None)

@router.callback_query(F.data.startswith("partner:view:"))
async def partner_view(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 2)[2]
    partner = await find_partner_by_id(get_api(callback), partner_id)
    if partner is None:
        await callback.message.answer("Партнёр не найден.", reply_markup=main_menu())
    else:
        name = partner_display_name(partner)
        city = partner.get("city") or "город не указан"
        active = bool(partner.get("is_active", partner.get("active", True)))
        await callback.message.answer(
            f"{name}\nГород: {city}\nСтатус: {'активен' if active else 'скрыт'}",
            reply_markup=partner_actions_keyboard(partner_id, active),
        )
    await callback.answer()



@router.callback_query(F.data.startswith("partner:sort:menu:"))
async def partner_sort_menu(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 3)[3]
    partner = await find_partner_by_id(get_api(callback), partner_id)
    current = item_sort_order(partner)
    await callback.message.answer(f"Текущий порядок:\n\n{current}", reply_markup=sort_order_keyboard("partner", partner_id, current, f"partner:view:{partner_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("partner:sort:move:"))
async def partner_sort_move(callback: CallbackQuery) -> None:
    _, _, _, partner_id, delta_raw = callback.data.split(":", 4)
    partner = await find_partner_by_id(get_api(callback), partner_id)
    await get_api(callback).update_partner(partner_id, {"sort_order": item_sort_order(partner) + int(delta_raw)})
    await list_partners(callback)


@router.callback_query(F.data.startswith("partner:sort:manual:"))
async def partner_sort_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    partner_id = callback.data.split(":", 3)[3]
    await state.clear(); await state.update_data(kind="partner", partner_id=partner_id); await state.set_state(SortOrderManual.value)
    await callback.message.answer("Введите порядок отображения числом:")
    await callback.answer()

@router.callback_query(F.data.startswith("partner:delete:confirm:"))
async def partner_delete_confirm(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 3)[3]
    try:
        partner = await find_partner_by_id(get_api(callback), partner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить партнёра: {user_error(exc)}")
    else:
        name = partner_display_name(partner or {"id": partner_id})
        await callback.message.answer(
            f'Вы уверены, что хотите удалить партнёра "{name}"?',
            reply_markup=partner_delete_confirm_keyboard(partner_id),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("partner:delete:yes:"))
async def partner_delete_execute(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 3)[3]
    try:
        await get_api(callback).delete_partner(partner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить партнёра: {user_error(exc)}")
        await callback.answer()
        return
    await callback.message.answer("✅ Партнёр успешно удалён.")
    await list_partners(callback)


@router.callback_query(F.data.startswith("partner:edit:"))
async def partner_edit_menu(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 2)[2]
    await callback.message.answer("Что изменить?", reply_markup=partner_edit_keyboard(partner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("partner:edit_field:"))
async def partner_edit_field_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, partner_id, field = callback.data.split(":", 4)
    await state.clear()
    await state.update_data(partner_id=partner_id, field=field)
    await state.set_state(PartnerEdit.value)
    prompts = {
        "name": "Введите новое название:",
        "description": "Введите новое описание:",
        "address": "Введите новый адрес:",
        "phone": "Введите новый телефон:",
        "is_active": "Введите да/показать или нет/скрыть:",
    }
    await callback.message.answer(prompts.get(field, "Введите новое значение:"))
    await callback.answer()


@router.message(PartnerEdit.value)
async def partner_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    text = message.text or ""
    if field == "is_active":
        lowered = text.strip().lower()
        active = lowered in {"1", "да", "yes", "true", "показать", "активен", "активна"}
        if not active and lowered not in {"0", "нет", "no", "false", "скрыть", "скрыт", "скрыта"}:
            await message.answer("Введите да/показать или нет/скрыть.")
            return
        payload = {"is_active": active}
    else:
        value = text.strip()
        if not value:
            await message.answer("Значение не должно быть пустым.")
            return
        payload = {str(field): value}
        if field == "name":
            payload["title"] = value
    try:
        await get_api(message).update_partner(data.get("partner_id"), payload)
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить партнёра: {user_error(exc)}", reply_markup=main_menu())
    else:
        await message.answer("Партнёр обновлён.")
        partners = await get_api(message).list_partners()
        partner = next((p for p in partners if str(p.get("id")) == str(data.get("partner_id"))), None)
        if partner:
            active = bool(partner.get("is_active", partner.get("active", True)))
            await message.answer(
                f"{partner_display_name(partner)}\nГород: {partner.get('city') or 'город не указан'}\nСтатус: {'активен' if active else 'скрыт'}",
                reply_markup=partner_actions_keyboard(data.get("partner_id"), active),
            )
        else:
            await list_partners(message)
    await state.clear()


@router.callback_query(F.data.startswith("partner:toggle:"))
async def partner_toggle(callback: CallbackQuery) -> None:
    _, _, partner_id, active_raw = callback.data.split(":", 3)
    active = bool(int(active_raw))
    try:
        await get_api(callback).update_partner(partner_id, {"is_active": active})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус партнёра: {user_error(exc)}")
    else:
        await send_partner_card(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("partner:photos:"))
async def partner_photos(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 2)[2]
    try:
        photos = await get_api(callback).list_partner_photos(partner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить фото партнёра: {user_error(exc)}")
        photos = []
    lines = ["Фото партнёра:"] + [f"• #{p.get('id', '?')} {p.get('url') or p.get('image_url') or ''}" for p in photos]
    await callback.message.answer("\n".join(lines), reply_markup=partner_photos_keyboard(partner_id, photos))
    await callback.answer()



@router.callback_query(F.data.startswith("partner:photo:sort_menu:"))
async def partner_photo_sort_menu(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 3)[3]
    photos = await get_api(callback).list_partner_photos(partner_id)
    text = "Порядок фото партнёра:\n" + "\n".join(f"• #{p.get('id')} — {item_sort_order(p)}" for p in photos)
    await callback.message.answer(text, reply_markup=photo_sort_keyboard("partner", partner_id, photos, f"partner:photos:{partner_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("partner:photo:sort:"))
async def partner_photo_sort_move(callback: CallbackQuery) -> None:
    _, _, _, partner_id, photo_id, delta_raw = callback.data.split(":", 5)
    photos = await get_api(callback).list_partner_photos(partner_id)
    photo = next((p for p in photos if str(p.get("id")) == str(photo_id)), None)
    await get_api(callback).update_partner_photo(photo_id, {"sort_order": item_sort_order(photo) + int(delta_raw)})
    photos = await get_api(callback).list_partner_photos(partner_id)
    lines = ["Фото партнёра:"] + [f"• #{p.get('id', '?')} {p.get('url') or p.get('image_url') or ''}" for p in photos]
    await callback.message.answer("\n".join(lines), reply_markup=partner_photos_keyboard(partner_id, photos))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:photo:sort_menu:"))
async def offer_photo_sort_menu(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    photos = await get_api(callback).list_offer_photos(offer_id)
    text = "Порядок фото услуги:\n" + "\n".join(f"• #{p.get('id')} — {item_sort_order(p)}" for p in photos)
    await callback.message.answer(text, reply_markup=photo_sort_keyboard("offer", f"{partner_id}:{offer_id}", photos, f"offer:photo:menu:{partner_id}:{offer_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:photo:sort:"))
async def offer_photo_sort_move(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id, photo_id, delta_raw = callback.data.split(":", 6)
    photos = await get_api(callback).list_offer_photos(offer_id)
    photo = next((p for p in photos if str(p.get("id")) == str(photo_id)), None)
    await get_api(callback).update_offer_photo(photo_id, {"sort_order": item_sort_order(photo) + int(delta_raw)})
    photos = await get_api(callback).list_offer_photos(offer_id)
    text = "Фото услуги:\n" + ("\n".join(f"• {p.get('url') or p.get('image_url') or p.get('photo_url')}" for p in photos) if photos else "Фото отсутствует.")
    await callback.message.answer(text, reply_markup=offer_photo_keyboard(partner_id, offer_id, photos))
    await callback.answer()

@router.callback_query(F.data.startswith("partner:photo:add:"))
async def partner_photo_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    partner_id = callback.data.split(":", 3)[3]
    await state.clear()
    await state.update_data(partner_id=partner_id)
    await state.set_state(PartnerPhotoAdd.photo)
    await callback.message.answer("Отправьте фото партнёра.")
    await callback.answer()


@router.message(PartnerPhotoAdd.photo)
async def partner_photo_add(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    partner_id = (await state.get_data()).get("partner_id")
    try:
        await get_api(message).add_partner_photo(partner_id, url)
    except WebApiError as exc:
        await message.answer(f"Не удалось добавить фото партнёра: {user_error(exc)}", reply_markup=main_menu())
    else:
        await message.answer("Фото партнёра добавлено.", reply_markup=main_menu())
    await state.clear()


@router.callback_query(F.data.startswith("partner:photo:main:"))
async def partner_photo_main(callback: CallbackQuery) -> None:
    _, _, _, partner_id, photo_id = callback.data.split(":", 4)
    try:
        await get_api(callback).update_partner_photo(photo_id, {"is_main": True})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось сделать фото главным: {user_error(exc)}")
    else:
        await callback.message.answer("Фото отмечено главным.", reply_markup=partner_photos_keyboard(partner_id, []))
    await callback.answer()


def offer_title_text(offer: dict[str, Any]) -> str:
    return str(offer.get("title") or offer.get("name") or f"Услуга {offer.get('id', '')}".strip() or "Без названия")


def offer_active(offer: dict[str, Any]) -> bool:
    return bool(offer.get("is_active", offer.get("active", True)))


def offer_price(offer: dict[str, Any]) -> Any:
    return offer.get("regular_price", offer.get("price"))


def offer_old_price(offer: dict[str, Any]) -> Any:
    return offer.get("club_price", offer.get("old_price"))


def offer_discount(offer: dict[str, Any]) -> Any:
    return offer.get("savings", offer.get("discount", offer.get("discount_amount")))


def offer_photo_url(offer: dict[str, Any], photos: list[dict[str, Any]] | None = None) -> str | None:
    for key in ("image_url", "photo_url", "url"):
        if offer.get(key):
            return str(offer[key])
    for photo in photos or []:
        for key in ("image_url", "url", "photo_url"):
            if photo.get(key):
                return str(photo[key])
    return None


def format_offer_card(offer: dict[str, Any], photos: list[dict[str, Any]] | None = None) -> str:
    photo = offer_photo_url(offer, photos)
    lines = [
        f"Название: {offer_title_text(offer)}",
        f"Описание: {offer.get('description') or '—'}",
        f"Условия: {offer.get('terms') or offer.get('conditions') or '—'}",
        f"Цена: {offer_price(offer) if offer_price(offer) is not None else '—'}",
        f"Старая цена: {offer_old_price(offer) if offer_old_price(offer) is not None else '—'}",
        f"Размер скидки: {offer_discount(offer) if offer_discount(offer) is not None else '—'}",
        f"Фото: {photo or 'Фото отсутствует.'}",
        f"Статус: {'🟢 Активна' if offer_active(offer) else '🔴 Скрыта'}",
    ]
    return "\n".join(lines)


async def show_partner_offers(message: Message, partner_id: int | str) -> None:
    try:
        offers = await get_api(message).list_offers(partner_id)
    except WebApiError as exc:
        await message.answer(f"Не удалось получить услуги: {user_error(exc)}")
        offers = []
    lines = ["Услуги партнёра:"]
    for offer in offers:
        status = "🟢 Активна" if offer_active(offer) else "🔴 Скрыта"
        discount = offer_discount(offer)
        discount_text = f" — скидка {discount}" if discount is not None else ""
        lines.append(f"• {offer_title_text(offer)} — {status} — цена {offer_price(offer) if offer_price(offer) is not None else '—'}{discount_text}")
    if len(lines) == 1:
        lines.append("Услуг пока нет.")
    await message.answer("\n".join(lines), reply_markup=offers_keyboard(partner_id, offers))


@router.callback_query(F.data.startswith("partner:offers:"))
async def partner_offers(callback: CallbackQuery) -> None:
    partner_id = callback.data.split(":", 2)[2]
    await show_partner_offers(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("offer:view:"))
async def offer_view(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id = callback.data.split(":", 3)
    api = get_api(callback)
    offers = await api.list_offers(partner_id)
    offer = next((item for item in offers if str(item.get("id")) == str(offer_id)), None)
    if offer is None:
        await callback.message.answer("Услуга не найдена.")
    else:
        try:
            photos = await api.list_offer_photos(offer_id)
        except WebApiError:
            photos = []
        await callback.message.answer(format_offer_card(offer, photos), reply_markup=offer_actions_keyboard(partner_id, offer_id, offer_active(offer)))
    await callback.answer()



@router.callback_query(F.data.startswith("offer:sort:menu:"))
async def offer_sort_menu(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    offer = await find_offer_by_id(get_api(callback), partner_id, offer_id)
    current = item_sort_order(offer)
    await callback.message.answer(f"Текущий порядок:\n\n{current}", reply_markup=sort_order_keyboard("offer", f"{partner_id}:{offer_id}", current, f"offer:view:{partner_id}:{offer_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:sort:move:"))
async def offer_sort_move(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id, delta_raw = callback.data.split(":", 5)
    offer = await find_offer_by_id(get_api(callback), partner_id, offer_id)
    await get_api(callback).update_offer(offer_id, {"sort_order": item_sort_order(offer) + int(delta_raw)})
    await show_partner_offers(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("offer:sort:manual:"))
async def offer_sort_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    await state.clear(); await state.update_data(kind="offer", partner_id=partner_id, offer_id=offer_id); await state.set_state(SortOrderManual.value)
    await callback.message.answer("Введите порядок отображения числом:")
    await callback.answer()

@router.callback_query(F.data.startswith("offer:toggle:"))
async def offer_toggle(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id, active_raw = callback.data.split(":", 4)
    active = bool(int(active_raw))
    try:
        await get_api(callback).update_offer(offer_id, {"is_active": active})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус услуги: {user_error(exc)}")
    else:
        await callback.message.answer("Услуга показана." if active else "Услуга скрыта.")
        await show_partner_offers(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("offer:edit:"))
async def offer_edit_menu(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id = callback.data.split(":", 3)
    await callback.message.answer("Что изменить?", reply_markup=offer_edit_keyboard(partner_id, offer_id))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:edit_field:"))
async def offer_edit_field_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, partner_id, offer_id, field = callback.data.split(":", 5)
    await state.clear()
    await state.update_data(partner_id=partner_id, offer_id=offer_id, field=field)
    await state.set_state(OfferEdit.value)
    prompts = {
        "title": "Введите новое название:",
        "description": "Введите новое описание:",
        "terms": "Введите новые условия:",
        "regular_price": "Введите новую цену числом:",
        "club_price": "Введите старую цену числом или «-»:",
        "savings": "Введите размер скидки числом:",
        "is_active": "Введите 1/да/показать или 0/нет/скрыть:",
    }
    await callback.message.answer(prompts.get(field, "Введите новое значение:"))
    await callback.answer()


@router.message(OfferEdit.value)
async def offer_edit_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    field = data.get("field")
    text = message.text or ""
    if field in {"regular_price", "club_price", "savings"}:
        value = None if field == "club_price" and normalize_optional_text(text) is None else parse_price(text)
        if value is None and not (field == "club_price" and normalize_optional_text(text) is None):
            await message.answer("Введите число.")
            return
        payload = {field: value}
        if field == "club_price":
            payload["discount_price"] = value
    elif field == "title":
        value = (text or "").strip()
        payload = {"title": value, "name": value}
    elif field == "terms":
        value = (text or "").strip()
        payload = {"terms": value, "conditions": value}
    elif field == "is_active":
        lowered = text.strip().lower()
        active = lowered in {"1", "да", "yes", "true", "показать", "активна"}
        if not active and lowered not in {"0", "нет", "no", "false", "скрыть", "скрыта"}:
            await message.answer("Введите 1/да/показать или 0/нет/скрыть.")
            return
        payload = {"is_active": active}
    else:
        payload = {str(field): (text or "").strip()}
    try:
        await get_api(message).update_offer(data.get("offer_id"), payload)
    except WebApiError as exc:
        await message.answer(f"Не удалось изменить услугу: {user_error(exc)}")
    else:
        await message.answer("Услуга обновлена.")
        await show_partner_offers(message, data.get("partner_id"))
    await state.clear()



@router.message(SortOrderManual.value)
async def sort_order_manual_value(message: Message, state: FSMContext) -> None:
    value = parse_optional_int(message.text)
    if value is None:
        await message.answer("Введите целое число.")
        return
    data = await state.get_data()
    if data.get("kind") == "partner":
        await get_api(message).update_partner(data.get("partner_id"), {"sort_order": value})
        await state.clear()
        await list_partners(message)
    elif data.get("kind") == "banner":
        await get_api(message).update_banner(data.get("banner_id"), {"sort_order": value})
        await state.clear()
        await show_banner_card(message, data.get("banner_id"))
    elif data.get("kind") in {"city", "category"}:
        prefix = data.get("kind")
        item_id = data.get("item_id")
        item = await (get_api(message).update_city(item_id, {"sort_order": value}) if prefix == "city" else get_api(message).update_category(item_id, {"sort_order": value}))
        await state.clear()
        await show_reference_card(message, prefix, item_id, item)
    else:
        await get_api(message).update_offer(data.get("offer_id"), {"sort_order": value})
        await state.clear()
        await show_partner_offers(message, data.get("partner_id"))

@router.callback_query(F.data.startswith("offer:photo:menu:"))
async def offer_photo_menu(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    try:
        photos = await get_api(callback).list_offer_photos(offer_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить фото услуги: {user_error(exc)}")
        photos = []
    text = "Фото услуги:\n" + ("\n".join(f"• {p.get('url') or p.get('image_url') or p.get('photo_url')}" for p in photos) if photos else "Фото отсутствует.")
    await callback.message.answer(text, reply_markup=offer_photo_keyboard(partner_id, offer_id, photos))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:photo:add:"))
async def offer_photo_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    await state.clear()
    await state.update_data(partner_id=partner_id, offer_id=offer_id)
    await state.set_state(OfferPhotoAdd.photo)
    await callback.message.answer("Отправьте фото услуги.")
    await callback.answer()


@router.message(OfferPhotoAdd.photo)
async def offer_photo_add(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    data = await state.get_data()
    try:
        await get_api(message).delete_offer_photos(data.get("offer_id"))
        await get_api(message).add_offer_photo(data.get("offer_id"), url)
    except WebApiError as exc:
        await message.answer(f"Не удалось добавить фото услуги: {user_error(exc)}", reply_markup=main_menu())
    else:
        await message.answer("Фото услуги добавлено.")
        await show_partner_offers(message, data.get("partner_id"))
    await state.clear()


@router.callback_query(F.data.startswith("offer:photo:delete:"))
async def offer_photo_delete(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    try:
        await get_api(callback).delete_offer_photos(offer_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить фото услуги: {user_error(exc)}")
    else:
        await callback.message.answer("Фото услуги удалено.")
        await show_partner_offers(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("offer:delete:confirm:"))
async def offer_delete_confirm(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    name = f"#{offer_id}"
    try:
        offers = await get_api(callback).list_offers(partner_id)
        offer = next((item for item in offers if str(item.get("id")) == str(offer_id)), None)
        if offer:
            name = offer_title_text(offer)
    except WebApiError:
        pass
    await callback.message.answer(f'⚠️\n\nВы действительно хотите удалить услугу\n"{name}"?', reply_markup=offer_delete_confirm_keyboard(partner_id, offer_id))
    await callback.answer()


@router.callback_query(F.data.startswith("offer:delete:yes:"))
async def offer_delete_execute(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    try:
        await get_api(callback).delete_offer(offer_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить услугу: {user_error(exc)}")
    else:
        await callback.message.answer("Услуга удалена.")
        await show_partner_offers(callback.message, partner_id)
    await callback.answer()


@router.callback_query(F.data == "block:add")
async def block_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BlockCreate.key)
    await callback.message.answer("Введите key блока (например hero):")
    await callback.answer()


@router.message(BlockCreate.key)
async def block_create_key(message: Message, state: FSMContext) -> None:
    await state.update_data(key=(message.text or "").strip())
    await state.set_state(BlockCreate.placement)
    await message.answer("Введите placement (например home):")


@router.message(BlockCreate.placement)
async def block_create_placement(message: Message, state: FSMContext) -> None:
    await state.update_data(placement=(message.text or "").strip())
    await state.set_state(BlockCreate.locale)
    await message.answer("Введите locale (например ru) или «-»:")


@router.message(BlockCreate.locale)
async def block_create_locale(message: Message, state: FSMContext) -> None:
    await state.update_data(locale=normalize_optional_text(message.text))
    await state.set_state(BlockCreate.title)
    await message.answer("Введите title или «-»:")


@router.message(BlockCreate.title)
async def block_create_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=normalize_optional_text(message.text))
    await state.set_state(BlockCreate.body)
    await message.answer("Введите body или «-»:")


@router.message(BlockCreate.body)
async def block_create_body(message: Message, state: FSMContext) -> None:
    await state.update_data(body=normalize_optional_text(message.text))
    await state.set_state(BlockCreate.metadata_json)
    await message.answer('Введите metadata_json как JSON или «-». Например: {"type":"hero"}')


@router.message(BlockCreate.metadata_json)
async def block_create_metadata(message: Message, state: FSMContext) -> None:
    metadata = validate_metadata_text(message.text)
    if metadata is False:
        await message.answer("metadata_json должен быть валидным JSON или «-». Исправьте и отправьте снова.")
        return
    await state.update_data(metadata_json=metadata)
    await state.set_state(BlockCreate.is_active)
    await message.answer("Опубликовать блок сразу? Ответьте да/нет:")


@router.message(BlockCreate.is_active)
async def block_create_active(message: Message, state: FSMContext) -> None:
    active = parse_bool_text(message.text)
    if active is None:
        await message.answer("Ответьте да или нет.")
        return
    data = await state.get_data()
    payload = block_payload(data, active)
    try:
        block = await get_api(message).create_block(payload)
        block_id = block.get("id") or block.get("key")
        if block_id is None:
            raise WebApiError("WEB API не вернул id/key созданного блока.")
    except WebApiError as exc:
        await message.answer(f"Не удалось создать блок: {user_error(exc)}", reply_markup=home_menu_keyboard())
    else:
        await message.answer("Блок создан.", reply_markup=block_actions_keyboard(block_id, block_active(block)))
    await state.clear()


@router.callback_query(F.data == "blocks:list")
async def list_blocks(callback: CallbackQuery) -> None:
    try:
        blocks = await get_api(callback).list_blocks()
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить список блоков: {user_error(exc)}", reply_markup=home_menu_keyboard())
    else:
        if not blocks:
            await callback.message.answer("Контентных блоков пока нет.", reply_markup=blocks_keyboard([]))
        else:
            lines = ["Контентные блоки:"]
            for block in blocks[:50]:
                lines.append(f"• {block.get('key', '-')} · {block.get('placement', '-')} — {'активен' if block_active(block) else 'скрыт'}")
            await callback.message.answer("\n".join(lines), reply_markup=blocks_keyboard(blocks[:50]))
    await callback.answer()


@router.callback_query(F.data.startswith("block:view:"))
async def block_view(callback: CallbackQuery) -> None:
    block_id = callback.data.split(":", 2)[2]
    block = await get_api(callback).get_block(block_id)
    if not block:
        await callback.message.answer("Блок не найден.", reply_markup=blocks_keyboard([]))
    else:
        await callback.message.answer(format_block(block), reply_markup=block_actions_keyboard(block_id, block_active(block)))
    await callback.answer()


@router.callback_query(F.data.startswith("block:edit:"))
async def block_edit(callback: CallbackQuery) -> None:
    block_id = callback.data.split(":", 2)[2]
    await callback.message.answer("Что изменить?", reply_markup=block_edit_keyboard(block_id))
    await callback.answer()


@router.callback_query(F.data.startswith("block:edit_field:"))
async def block_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, block_id, field = callback.data.split(":", 4)
    states = {"title": BlockEdit.title, "body": BlockEdit.body, "metadata_json": BlockEdit.metadata_json, "placement": BlockEdit.placement, "locale": BlockEdit.locale}
    prompts = {"title": "Введите новый title или «-»:", "body": "Введите новый body или «-»:", "metadata_json": "Введите новый валидный metadata_json или «-»:", "placement": "Введите новый placement:", "locale": "Введите новый locale или «-»:"}
    await state.clear(); await state.update_data(block_id=block_id, field=field); await state.set_state(states[field])
    await callback.message.answer(prompts[field]); await callback.answer()


@router.message(BlockEdit.title)
@router.message(BlockEdit.body)
@router.message(BlockEdit.metadata_json)
@router.message(BlockEdit.placement)
@router.message(BlockEdit.locale)
async def block_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); field = data["field"]
    value: Any = validate_metadata_text(message.text) if field == "metadata_json" else normalize_optional_text(message.text)
    if value is False:
        await message.answer("metadata_json должен быть валидным JSON или «-». PATCH не отправлен.")
        return
    try:
        block = await get_api(message).update_block(data["block_id"], {field: value})
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить блок: {user_error(exc)}", reply_markup=home_menu_keyboard())
    else:
        await message.answer("Блок обновлён.", reply_markup=block_actions_keyboard(data["block_id"], block_active(block)))
        await state.clear()


@router.callback_query(F.data.startswith("block:toggle:"))
async def block_toggle(callback: CallbackQuery) -> None:
    _, _, block_id, active_raw = callback.data.split(":", 3)
    active = bool(int(active_raw))
    try:
        block = await (get_api(callback).publish_block(block_id) if active else get_api(callback).hide_block(block_id))
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус блока: {user_error(exc)}")
    else:
        await callback.message.answer("Блок опубликован." if active else "Блок скрыт.", reply_markup=block_actions_keyboard(block_id, block_active(block) if block else active))
    await callback.answer()


@router.callback_query(F.data == "banner:add")
async def banner_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BannerCreate.title)
    await callback.message.answer("Введите заголовок баннера:")
    await callback.answer()


@router.message(BannerCreate.title)
async def banner_create_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=(message.text or "").strip())
    await state.set_state(BannerCreate.subtitle)
    await message.answer("Введите подзаголовок или «-», если не нужен:")


@router.message(BannerCreate.subtitle)
async def banner_create_subtitle(message: Message, state: FSMContext) -> None:
    await state.update_data(subtitle=normalize_optional_text(message.text))
    await state.set_state(BannerCreate.description)
    await message.answer("Введите описание или «-», если не нужно:")


@router.message(BannerCreate.description)
async def banner_create_description(message: Message, state: FSMContext) -> None:
    await state.update_data(description=normalize_optional_text(message.text))
    await state.set_state(BannerCreate.cta_text)
    await message.answer("Введите текст CTA-кнопки или «-», если не нужен:")


@router.message(BannerCreate.cta_text)
async def banner_create_cta(message: Message, state: FSMContext) -> None:
    await state.update_data(cta_text=normalize_optional_text(message.text))
    await state.set_state(BannerCreate.link_url)
    await message.answer("Введите ссылку или «-», если не нужна:")


@router.message(BannerCreate.link_url)
async def banner_create_link(message: Message, state: FSMContext) -> None:
    await state.update_data(link_url=normalize_optional_text(message.text))
    await state.set_state(BannerCreate.placement)
    await message.answer("Введите placement (например home) или «-», если не нужен:")


@router.message(BannerCreate.placement)
async def banner_create_placement(message: Message, state: FSMContext) -> None:
    await state.update_data(placement=normalize_optional_text(message.text))
    await state.set_state(BannerCreate.photo)
    await message.answer("Отправьте фото баннера jpg/png/webp до 10 MB или нажмите «Пропустить».", reply_markup=skip_photo_keyboard())


@router.callback_query(BannerCreate.photo, F.data == "skip_photo")
async def banner_create_skip_photo(callback: CallbackQuery, state: FSMContext) -> None:
    await finalize_banner(callback.message, state, None)
    await callback.answer()


@router.message(BannerCreate.photo)
async def banner_create_photo(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is not None:
        await finalize_banner(message, state, url)


async def finalize_banner(message: Message, state: FSMContext, photo_url: str | None) -> None:
    data = await state.get_data()
    payload = banner_payload(data, photo_url)
    try:
        banner = await get_api(message).create_banner(payload)
        banner_id = banner.get("id")
        if banner_id is None:
            raise WebApiError("WEB API не вернул id созданного баннера.")
    except WebApiError as exc:
        await state.clear()
        await message.answer(f"Не удалось создать баннер: {banner_user_error(exc)}", reply_markup=banners_menu_keyboard())
        return
    await state.clear()
    await message.answer("Баннер создан.")
    await show_banner_card(message, banner_id)


@router.message(F.text == "📋 Список баннеров")
@router.callback_query(F.data == "banners:list")
async def list_banners(event: Message | CallbackQuery) -> None:
    message = event if isinstance(event, Message) else event.message
    try:
        banners = await get_api(event).list_banners()
    except WebApiError as exc:
        await message.answer(f"Не удалось получить список баннеров: {banner_user_error(exc)}", reply_markup=banners_menu_keyboard())
    else:
        if not banners:
            await message.answer("Баннеров пока нет. Создайте первый баннер.", reply_markup=banners_keyboard([]))
        else:
            lines = ["Баннеры:"]
            for banner in banners[:50]:
                lines.append(format_banner_list_item(banner))
            await message.answer("\n\n".join(lines), reply_markup=banners_keyboard(banners[:50]))
    if isinstance(event, CallbackQuery):
        await event.answer()


async def show_banner_card(message: Message, banner_id: int | str) -> None:
    try:
        banner = await get_api(message).get_banner(banner_id)
    except WebApiError as exc:
        await message.answer(f"Не удалось получить баннер: {banner_user_error(exc)}", reply_markup=banners_keyboard([]))
        return
    if not banner:
        await message.answer("Баннер уже отсутствует.", reply_markup=banners_keyboard([]))
    else:
        await message.answer(format_banner(banner), reply_markup=banner_actions_keyboard(banner_id, banner_active(banner)))


@router.callback_query(F.data.startswith("banner:view:"))
async def banner_view(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 2)[2]
    await show_banner_card(callback.message, banner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("banner:edit:"))
async def banner_edit(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 2)[2]
    await callback.message.answer("Что изменить?", reply_markup=banner_edit_keyboard(banner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("banner:edit_field:"))
async def banner_edit_field(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, _, banner_id, field = callback.data.split(":", 4)
    states = {"title": BannerEdit.title, "subtitle": BannerEdit.subtitle, "description": BannerEdit.description, "link_url": BannerEdit.link_url, "cta_text": BannerEdit.cta_text, "placement": BannerEdit.placement, "sort_order": BannerEdit.sort_order, "is_active": BannerEdit.is_active}
    prompts = {"title": "Введите новый заголовок:", "subtitle": "Введите новый подзаголовок или «-», чтобы очистить:", "description": "Введите новое описание или «-», чтобы очистить:", "link_url": "Введите новую ссылку или «-», чтобы очистить:", "cta_text": "Введите новый CTA или «-», чтобы очистить:", "placement": "Введите новый placement или «-», чтобы очистить:", "sort_order": "Введите новый порядок числом или «-», чтобы очистить:", "is_active": "Введите 1/да/показать или 0/нет/скрыть:"}
    await state.clear(); await state.update_data(banner_id=banner_id, field=field); await state.set_state(states[field])
    await callback.message.answer(prompts[field]); await callback.answer()


@router.message(BannerEdit.title)
@router.message(BannerEdit.subtitle)
@router.message(BannerEdit.description)
@router.message(BannerEdit.link_url)
@router.message(BannerEdit.cta_text)
@router.message(BannerEdit.placement)
@router.message(BannerEdit.sort_order)
@router.message(BannerEdit.is_active)
async def banner_edit_save(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); field = data["field"]
    if field == "sort_order":
        value = parse_optional_int(message.text)
        if value is None and normalize_optional_text(message.text) is not None:
            await message.answer("Введите целое число или «-»."); return
    elif field == "is_active":
        active = parse_bool_text(message.text)
        if active is None:
            await message.answer("Введите 1/да/показать или 0/нет/скрыть."); return
        value = active
    elif field == "title":
        value = (message.text or "").strip()
    else:
        value = normalize_optional_text(message.text)
    try:
        banner = await get_api(message).update_banner(data["banner_id"], {field: value})
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить баннер: {banner_user_error(exc)}", reply_markup=banners_menu_keyboard())
    else:
        await message.answer("Баннер обновлён.")
        await show_banner_card(message, data["banner_id"])
    await state.clear()




@router.callback_query(F.data == "banners:sort")
async def banners_sort_info(callback: CallbackQuery) -> None:
    await callback.message.answer("Откройте карточку баннера и используйте «↕️ Порядок» для изменения позиции.", reply_markup=banners_keyboard([]))
    await callback.answer()


@router.callback_query(F.data.startswith("banner:sort:menu:"))
async def banner_sort_menu(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 3)[3]
    try:
        banner = await get_api(callback).get_banner(banner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить баннер: {banner_user_error(exc)}")
    else:
        current = item_sort_order(banner)
        await callback.message.answer(f"Текущий порядок:\n\n{current}", reply_markup=sort_order_keyboard("banner", banner_id, current, f"banner:view:{banner_id}"))
    await callback.answer()


@router.callback_query(F.data.startswith("banner:sort:move:"))
async def banner_sort_move(callback: CallbackQuery) -> None:
    _, _, _, banner_id, delta_raw = callback.data.split(":", 4)
    try:
        banner = await get_api(callback).get_banner(banner_id)
        await get_api(callback).update_banner(banner_id, {"sort_order": item_sort_order(banner) + int(delta_raw)})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить порядок баннера: {banner_user_error(exc)}")
    else:
        await show_banner_card(callback.message, banner_id)
    await callback.answer()


@router.callback_query(F.data.startswith("banner:sort:manual:"))
async def banner_sort_manual_start(callback: CallbackQuery, state: FSMContext) -> None:
    banner_id = callback.data.split(":", 3)[3]
    await state.clear(); await state.update_data(kind="banner", banner_id=banner_id); await state.set_state(SortOrderManual.value)
    await callback.message.answer("Введите порядок отображения числом:")
    await callback.answer()

@router.callback_query(F.data.startswith("banner:toggle:"))
async def banner_toggle(callback: CallbackQuery) -> None:
    _, _, banner_id, active_raw = callback.data.split(":", 3)
    active = bool(int(active_raw))
    try:
        banner = await (get_api(callback).publish_banner(banner_id) if active else get_api(callback).hide_banner(banner_id))
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус баннера: {banner_user_error(exc)}")
    else:
        await callback.message.answer("Баннер показан." if active else "Баннер скрыт.")
        await show_banner_card(callback.message, banner_id)
    await callback.answer()




@router.callback_query(F.data.startswith("banner:photo:menu:"))
async def banner_photo_menu(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 3)[3]
    try:
        banner = await get_api(callback).get_banner(banner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось получить фото баннера: {banner_user_error(exc)}")
        await callback.answer(); return
    image_url = banner.get("image_url")
    text = "Фото баннера:\n" + (str(image_url) if image_url else "Фото отсутствует")
    await callback.message.answer(text, reply_markup=banner_photo_keyboard(banner_id, bool(image_url)))
    await callback.answer()


@router.callback_query(F.data.startswith("banner:photo:delete:"))
async def banner_photo_delete(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 3)[3]
    try:
        await get_api(callback).update_banner(banner_id, {"image_url": None})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить фото баннера: {banner_user_error(exc)}")
    else:
        await callback.message.answer("Фото баннера удалено.")
        await show_banner_card(callback.message, banner_id)
    await callback.answer()

@router.callback_query(F.data.startswith("banner:photo:add:"))
async def banner_photo_start(callback: CallbackQuery, state: FSMContext) -> None:
    banner_id = callback.data.split(":", 3)[3]
    await state.clear(); await state.update_data(banner_id=banner_id); await state.set_state(BannerPhotoAdd.photo)
    await callback.message.answer("Отправьте фото баннера jpg/png/webp до 10 MB."); await callback.answer()


@router.message(BannerPhotoAdd.photo)
async def banner_photo_save(message: Message, state: FSMContext, settings: Settings) -> None:
    url = await receive_and_upload_photo(message, settings)
    if url is None:
        return
    banner_id = (await state.get_data()).get("banner_id")
    try:
        banner = await get_api(message).update_banner(banner_id, {"image_url": url})
    except WebApiError as exc:
        await message.answer(f"Не удалось обновить фото баннера: {banner_user_error(exc)}", reply_markup=banners_menu_keyboard())
    else:
        await message.answer("Фото баннера обновлено.")
        await show_banner_card(message, banner_id)
    await state.clear()



@router.callback_query(F.data.startswith("banner:delete:confirm:"))
async def banner_delete_confirm(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 3)[3]
    await callback.message.answer("Удалить баннер?", reply_markup=banner_delete_confirm_keyboard(banner_id))
    await callback.answer()


@router.callback_query(F.data.startswith("banner:delete:yes:"))
async def banner_delete_execute(callback: CallbackQuery) -> None:
    banner_id = callback.data.split(":", 3)[3]
    try:
        await get_api(callback).delete_banner(banner_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить баннер: {banner_user_error(exc)}")
        await callback.answer(); return
    await callback.message.answer("Баннер удалён.")
    await list_banners(callback)


def validate_metadata_text(value: str | None) -> str | None | bool:
    text = normalize_optional_text(value)
    if text is None:
        return None
    try:
        json.loads(text)
    except json.JSONDecodeError:
        return False
    return text


def block_payload(data: dict[str, Any], active: bool) -> dict[str, Any]:
    return {"key": data.get("key"), "placement": data.get("placement"), "locale": data.get("locale"), "title": data.get("title"), "body": data.get("body"), "metadata_json": data.get("metadata_json"), "is_active": active, "active": active}


def block_active(block: dict[str, Any]) -> bool:
    return bool(block.get("is_active", block.get("active", True)))


def format_block(block: dict[str, Any]) -> str:
    lines = [f"Key: {block.get('key', '-')}", f"Placement: {block.get('placement', '-')}", f"Locale: {block.get('locale', '-')}", f"Title: {block.get('title', '-')}", f"Body: {block.get('body', '-')}", f"Статус: {'активен' if block_active(block) else 'скрыт'}"]
    if block.get("metadata_json") is not None:
        lines.append(f"metadata_json: {block.get('metadata_json')}")
    return "\n".join(lines)


def banner_payload(data: dict[str, Any], photo_url: str | None = None) -> dict[str, Any]:
    payload = {
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
        "description": data.get("description"),
        "link_url": data.get("link_url"),
        "cta_text": data.get("cta_text"),
        "placement": data.get("placement"),
        "is_active": True,
        "active": True,
    }
    if data.get("sort_order") is not None:
        payload["sort_order"] = data.get("sort_order")
    if photo_url:
        payload["image_url"] = photo_url
    return payload


def banner_title(banner: dict[str, Any]) -> str:
    return str(banner.get("title") or f"Баннер {banner.get('id', '')}".strip())


def banner_active(banner: dict[str, Any]) -> bool:
    return bool(banner.get("is_active", banner.get("active", True)))


def format_banner_list_item(banner: dict[str, Any]) -> str:
    status = "🟢 Активен" if banner_active(banner) else "🔴 Скрыт"
    photo = banner.get("image_url") or "Фото отсутствует"
    return "\n".join([
        f"• {banner_title(banner)}",
        f"Фото: {photo}",
        f"Подзаголовок: {banner.get('subtitle') or '-'}",
        f"Место размещения: {banner.get('placement') or '-'}",
        f"Порядок отображения: {banner.get('sort_order', '-')}",
        f"Статус: {status}",
    ])


def format_banner(banner: dict[str, Any]) -> str:
    status = "🟢 Активен" if banner_active(banner) else "🔴 Скрыт"
    lines = [
        f"Название: {banner_title(banner)}",
        f"Подзаголовок: {banner.get('subtitle') or '-'}",
        f"Описание: {banner.get('description') or '-'}",
        f"CTA текст: {banner.get('cta_text') or '-'}",
        f"Ссылка: {banner.get('link_url') or '-'}",
        f"Placement: {banner.get('placement') or '-'}",
        f"Sort Order: {banner.get('sort_order', '-')}",
        f"Статус: {status}",
        f"Фото: {banner.get('image_url') or 'Фото отсутствует'}",
    ]
    return "\n".join(lines)


INVALID_DATE_MESSAGE = "Введите дату в формате ДД.ММ.ГГГГ или ДД.ММ.ГГГГ ЧЧ:ММ."

def parse_admin_date(value: str | None) -> str | None:
    text = (value or "").strip()
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y"):
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="minutes")
        except ValueError:
            continue
    return None

async def send_giveaway_card(message: Message, giveaway_id: int | str) -> None:
    giveaway = await get_api(message).get_giveaway(giveaway_id)
    await message.answer(format_giveaway(giveaway), reply_markup=giveaway_actions_keyboard(giveaway_id, giveaway_active(giveaway)))

async def send_giveaway_items_list(message: Message, giveaway_id: int | str) -> None:
    items = await get_api(message).list_giveaway_items(giveaway_id)
    if not items:
        await message.answer("У этого розыгрыша пока нет призов. Добавьте первый приз.", reply_markup=giveaway_items_keyboard(giveaway_id, []))
        return
    lines = ["Призы розыгрыша:"]
    for item in items[:50]:
        lines.append(format_giveaway_item_summary(item))
    await message.answer("\n".join(lines), reply_markup=giveaway_items_keyboard(giveaway_id, items[:50]))

def normalize_optional_text(value: str | None) -> str | None:
    text = (value or "").strip()
    if text in {"", "-", "—", "нет", "Нет"}:
        return None
    return text


def giveaway_payload(data: dict[str, Any], photo_url: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": data.get("title"),
        "name": data.get("title"),
        "description": data.get("description"),
        "terms": data.get("terms"),
        "conditions": data.get("terms"),
        "is_active": True,
        "active": True,
    }
    for source, targets in {
        "starts_at": ("starts_at", "start_date", "date_start"),
        "ends_at": ("ends_at", "end_date", "draw_date", "date"),
    }.items():
        value = data.get(source)
        if value:
            for target in targets:
                payload[target] = value
    if photo_url:
        payload.update(giveaway_photo_payload(photo_url))
    return payload


def giveaway_update_payload(field: str, value: str | None) -> dict[str, Any]:
    if field == "title":
        return {"title": value, "name": value}
    if field == "terms":
        return {"terms": value, "conditions": value}
    if field == "starts_at":
        return {"starts_at": value, "start_date": value, "date_start": value}
    if field == "ends_at":
        return {"ends_at": value, "end_date": value, "draw_date": value, "date": value}
    return {field: value}


def giveaway_photo_payload(url: str) -> dict[str, str]:
    return {"photo_url": url, "image_url": url, "url": url}


def giveaway_title(giveaway: dict[str, Any]) -> str:
    return str(giveaway.get("title") or giveaway.get("name") or f"Розыгрыш {giveaway.get('id', '')}".strip())


def giveaway_active(giveaway: dict[str, Any]) -> bool:
    return bool(giveaway.get("is_active", giveaway.get("active", True)))

def giveaway_status(giveaway: dict[str, Any]) -> str:
    if not giveaway_active(giveaway):
        return "🔴 Скрыт"
    now = datetime.now()
    start = parse_known_date(giveaway.get("starts_at") or giveaway.get("start_date") or giveaway.get("date_start"))
    end = parse_known_date(giveaway.get("ends_at") or giveaway.get("end_date") or giveaway.get("draw_date") or giveaway.get("date"))
    if start and start > now:
        return "⏳ Запланирован"
    if end and end < now:
        return "✅ Завершён"
    return "🟢 Активен"

def parse_known_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        pass
    for fmt in ("%d.%m.%Y %H:%M", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None

def giveaway_prize_count(giveaway: dict[str, Any]) -> int | str:
    for key in ("prizes_count", "items_count", "prize_count", "items"):
        value = giveaway.get(key)
        if isinstance(value, list):
            return len(value)
        if value is not None:
            return value
    return "-"


def giveaway_period(giveaway: dict[str, Any]) -> str:
    start = giveaway.get("starts_at") or giveaway.get("start_date") or giveaway.get("date_start")
    end = giveaway.get("ends_at") or giveaway.get("end_date") or giveaway.get("draw_date") or giveaway.get("date")
    if start and end:
        return f" — {start}–{end}"
    if end:
        return f" — до {end}"
    if start:
        return f" — с {start}"
    return ""


def format_giveaway(giveaway: dict[str, Any]) -> str:
    start = giveaway.get("starts_at") or giveaway.get("start_date") or giveaway.get("date_start") or "-"
    end = giveaway.get("ends_at") or giveaway.get("end_date") or giveaway.get("draw_date") or giveaway.get("date") or "-"
    lines = [
        f"Название: {giveaway_title(giveaway)}",
        f"Описание: {giveaway.get('description') or '-'}",
        f"Условия участия: {giveaway.get('terms') or giveaway.get('conditions') or '-'}",
        f"Дата начала: {start}",
        f"Дата окончания: {end}",
        f"Статус: {giveaway_status(giveaway)}",
        f"Фото: {giveaway.get('photo_url') or giveaway.get('image_url') or 'Фото отсутствует.'}",
        f"Количество призов: {giveaway_prize_count(giveaway)}",
    ]
    if giveaway.get("sort_order") is not None:
        lines.append(f"Порядок отображения: {giveaway['sort_order']}")
    return "\n".join(lines)


def giveaway_item_payload(data: dict[str, Any], photo_url: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "title": data.get("title"),
        "description": data.get("description"),
        "is_active": True,
    }
    if data.get("sort_order") is not None:
        payload["sort_order"] = data.get("sort_order")
    if photo_url:
        payload["image_url"] = photo_url
    return payload


def giveaway_item_title(item: dict[str, Any]) -> str:
    return str(item.get("title") or f"Приз {item.get('id', '')}".strip())


def giveaway_item_active(item: dict[str, Any]) -> bool:
    return bool(item.get("is_active", True))


def format_giveaway_item_summary(item: dict[str, Any]) -> str:
    photo = "есть фото" if (item.get("image_url") or item.get("photo_url")) else "нет фото"
    return f"• {giveaway_item_title(item)} — {item.get('description') or '-'} — {'🟢 Активен' if giveaway_item_active(item) else '🔴 Скрыт'} — порядок: {item.get('sort_order', '-')} — {photo}"

def format_giveaway_item(item: dict[str, Any]) -> str:
    return "\n".join([
        f"Название: {giveaway_item_title(item)}",
        f"Описание: {item.get('description') or '-'}",
        f"Статус: {'🟢 Активен' if giveaway_item_active(item) else '🔴 Скрыт'}",
        f"Порядок отображения: {item.get('sort_order', '-')}",
        f"Фото: {item.get('image_url') or item.get('photo_url') or 'Фото отсутствует.'}",
    ])


def parse_bool_text(value: str | None) -> bool | None:
    text = (value or "").strip().lower()
    if text in {"1", "+", "да", "д", "yes", "y", "true", "активен", "показать"}:
        return True
    if text in {"0", "-", "нет", "н", "no", "n", "false", "скрыт", "скрыть"}:
        return False
    return None

async def callback_safe_item_card_message(message: Message, giveaway_id: int | str, item_id: int | str, item: dict[str, Any] | None = None) -> None:
    item = item or await get_api(message).get_giveaway_item(item_id)
    await message.answer(format_giveaway_item(item), reply_markup=giveaway_item_actions_keyboard(giveaway_id, item_id, giveaway_item_active(item)))

def parse_optional_int(value: str | None) -> int | None:
    text = normalize_optional_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


async def receive_and_upload_photo(message: Message, settings: Settings) -> str | None:
    file_id: str | None = None
    filename = "telegram_photo.jpg"
    mime_type = "image/jpeg"
    size = 0
    if message.photo:
        photo = message.photo[-1]
        file_id = photo.file_id
        size = photo.file_size or 0
    elif message.document and message.document.mime_type in {"image/jpeg", "image/png", "image/webp"}:
        file_id = message.document.file_id
        filename = message.document.file_name or "telegram_document_image"
        mime_type = message.document.mime_type or mime_type
        size = message.document.file_size or 0
    else:
        await message.answer("Отправьте фото или документ jpg/png/webp до 10 MB.")
        return None

    if size > settings.max_upload_size_mb * 1024 * 1024:
        await message.answer(f"Файл слишком большой. Максимум {settings.max_upload_size_mb} MB.")
        return None

    api = get_api(message)
    tmp_path: Path | None = None
    try:
        file = await message.bot.get_file(file_id)
        suffix = Path(filename).suffix or ".jpg"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp_path = Path(tmp.name)
        await message.bot.download_file(file.file_path, destination=tmp_path)
        return await api.upload_file(tmp_path, mime_type)
    except WebApiError as exc:
        await message.answer(f"Не удалось загрузить файл: {user_error(exc)}")
    except Exception:
        logger.exception("Telegram file upload failed")
        await message.answer("Не удалось обработать файл. Попробуйте другое изображение.")
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return None


def parse_price(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace(" ", "").replace(",", "."))
    except ValueError:
        return None


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    global _content_api, _login_code, _browser_app_public_url
    settings = load_settings()
    bot = Bot(settings.telegram_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    _content_api = ContentAdminApiClient(settings.web_content_api_base_url, settings.telegram_admin_api_token, settings.telegram_catalog_api_base_url)
    _login_code = LoginCodeClient(settings.web_api_base_url, settings.bot_service_token)
    _browser_app_public_url = settings.browser_app_public_url
    dp = Dispatcher(storage=MemoryStorage(), settings=settings)
    router.message.middleware(AdminOnlyMiddleware(settings.telegram_admin_ids))
    router.callback_query.middleware(AdminOnlyMiddleware(settings.telegram_admin_ids))
    dp.include_router(router)
    try:
        await dp.start_polling(bot)
    finally:
        if _content_api is not None:
            await _content_api.close()
        if _login_code is not None:
            await _login_code.close()
        await bot.session.close()


def run() -> None:
    asyncio.run(main())


def privilege_code_status(code: dict[str, Any]) -> str:
    if code.get("is_active", code.get("active", True)) is False or str(code.get("status", "")).lower() in {"inactive", "disabled", "deactivated"}:
        return "❌ Неактивен"
    if code.get("issued_to") or code.get("telegram_user_id") or code.get("user_id") or code.get("used_at") or str(code.get("status", "")).lower() in {"issued", "used", "redeemed"}:
        return "🎁 Выдан"
    return "✅ Свободен"


def format_privilege_code_line(code: dict[str, Any]) -> str:
    return f"• {code.get('code') or '—'} — {privilege_code_status(code)} — создан: {code.get('created_at') or '—'}"


def format_privilege_code_card(code: dict[str, Any]) -> str:
    issued_to = code.get("issued_to") or code.get("telegram_user_id") or code.get("user_id") or "—"
    issued_at = code.get("issued_at") or code.get("used_at") or "—"
    return "\n".join([
        f"Код: {code.get('code') or '—'}",
        f"Статус: {privilege_code_status(code)}",
        f"Кому выдан: {issued_to}",
        f"Дата выдачи: {issued_at}",
        f"Дата создания: {code.get('created_at') or '—'}",
    ])


def split_privilege_codes_payload(text: str) -> list[str]:
    rows: list[str] = []
    for row in csv.reader(io.StringIO(text)):
        value = (row[0] if row else "").strip()
        if value:
            rows.append(value)
    return rows


async def show_privilege_codes(message: Message, partner_id: int | str, offer_id: int | str) -> None:
    try:
        codes = await get_api(message).list_privilege_codes(offer_id)
    except WebApiError as exc:
        await message.answer(f"Не удалось получить коды: {privilege_code_user_error(exc)}")
        codes = []
    lines = ["🎟 Коды привилегий", f"Количество кодов: {len(codes)}"]
    lines.extend(format_privilege_code_line(c) for c in codes[:50])
    if len(lines) == 2:
        lines.append("Кодов пока нет.")
    await message.answer("\n".join(lines), reply_markup=privilege_codes_keyboard(partner_id, offer_id, codes))


@router.callback_query(F.data.startswith("pc:list:"))
async def privilege_codes_list(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id = callback.data.split(":", 3)
    await show_privilege_codes(callback.message, partner_id, offer_id)
    await callback.answer()


@router.callback_query(F.data.startswith("pc:view:"))
async def privilege_code_view(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id, code_id = callback.data.split(":", 4)
    codes = await get_api(callback).list_privilege_codes(offer_id)
    code = next((c for c in codes if str(c.get("id")) == str(code_id)), None)
    if not code:
        await callback.message.answer("Код уже отсутствует.")
    else:
        active = code.get("is_active", code.get("active", True)) is not False
        await callback.message.answer(format_privilege_code_card(code), reply_markup=privilege_code_actions_keyboard(partner_id, offer_id, code_id, active))
    await callback.answer()


@router.callback_query(F.data.startswith("pc:add:"))
async def privilege_code_create_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, partner_id, offer_id = callback.data.split(":", 3)
    await state.clear(); await state.update_data(partner_id=partner_id, offer_id=offer_id); await state.set_state(PrivilegeCodeCreate.code)
    await callback.message.answer("Введите код:")
    await callback.answer()


@router.message(PrivilegeCodeCreate.code)
async def privilege_code_create(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); code = (message.text or "").strip()
    if not code:
        await message.answer("Введите непустой код."); return
    try:
        await get_api(message).create_privilege_code(data.get("offer_id"), code)
    except WebApiError as exc:
        await message.answer("Код уже существует." if is_conflict_error(exc) else f"Не удалось создать код: {privilege_code_user_error(exc)}")
    else:
        await message.answer("Код создан.")
    await state.clear(); await show_privilege_codes(message, data.get("partner_id"), data.get("offer_id"))


@router.callback_query(F.data.startswith("pc:bulk:"))
async def privilege_code_bulk_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, partner_id, offer_id = callback.data.split(":", 3)
    await state.clear(); await state.update_data(partner_id=partner_id, offer_id=offer_id); await state.set_state(PrivilegeCodeBulkImport.payload)
    await callback.message.answer("Отправьте список кодов сообщением или CSV/TXT файлом. Каждая строка = отдельный код.")
    await callback.answer()


@router.message(PrivilegeCodeBulkImport.payload)
async def privilege_code_bulk_import(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data(); text = message.text or ""
    if message.document:
        file = await bot.get_file(message.document.file_id)
        bio = io.BytesIO(); await bot.download_file(file.file_path, bio); text = bio.getvalue().decode("utf-8-sig", errors="ignore")
    added = dup = errors = 0
    for code in split_privilege_codes_payload(text):
        try:
            await get_api(message).create_privilege_code(data.get("offer_id"), code)
            added += 1
        except WebApiError as exc:
            if is_conflict_error(exc): dup += 1
            else: errors += 1
    await message.answer(f"Добавлено: {added}\nПропущено дублей: {dup}\nОшибок: {errors}")
    await state.clear(); await show_privilege_codes(message, data.get("partner_id"), data.get("offer_id"))


@router.callback_query(F.data.startswith("pc:edit:"))
async def privilege_code_edit_start(callback: CallbackQuery, state: FSMContext) -> None:
    _, _, partner_id, offer_id, code_id = callback.data.split(":", 4)
    await state.clear(); await state.update_data(partner_id=partner_id, offer_id=offer_id, code_id=code_id); await state.set_state(PrivilegeCodeEdit.code)
    await callback.message.answer("Введите новый код:")
    await callback.answer()


@router.message(PrivilegeCodeEdit.code)
async def privilege_code_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data(); code = (message.text or "").strip()
    if not code:
        await message.answer("Введите непустой код."); return
    try:
        await get_api(message).update_privilege_code(data.get("code_id"), {"code": code})
    except WebApiError as exc:
        await message.answer("Код уже существует." if is_conflict_error(exc) else f"Не удалось изменить код: {privilege_code_user_error(exc)}")
    else:
        await message.answer("Код обновлён.")
    await state.clear(); await show_privilege_codes(message, data.get("partner_id"), data.get("offer_id"))


@router.callback_query(F.data.startswith("pc:toggle:"))
async def privilege_code_toggle(callback: CallbackQuery) -> None:
    _, _, partner_id, offer_id, code_id, active_raw = callback.data.split(":", 5)
    active = bool(int(active_raw))
    try:
        await get_api(callback).update_privilege_code(code_id, {"is_active": active, "active": active})
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось изменить статус кода: {privilege_code_user_error(exc)}")
    else:
        await callback.message.answer("Код активирован." if active else "Код деактивирован.")
        await show_privilege_codes(callback.message, partner_id, offer_id)
    await callback.answer()


@router.callback_query(F.data.startswith("pc:delete:confirm:"))
async def privilege_code_delete_confirm(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id, code_id = callback.data.split(":", 5)
    await callback.message.answer("Удалить код?", reply_markup=privilege_code_delete_confirm_keyboard(partner_id, offer_id, code_id))
    await callback.answer()


@router.callback_query(F.data.startswith("pc:delete:yes:"))
async def privilege_code_delete(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id, code_id = callback.data.split(":", 5)
    try:
        await get_api(callback).delete_privilege_code(code_id)
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось удалить код: {privilege_code_user_error(exc)}")
    else:
        await callback.message.answer("Код удалён.")
        await show_privilege_codes(callback.message, partner_id, offer_id)
    await callback.answer()


@router.callback_query(F.data.startswith("pc:clear:confirm:"))
async def privilege_codes_clear_confirm(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    await callback.message.answer("Удалить все неиспользованные и невыданные коды?", reply_markup=privilege_codes_clear_confirm_keyboard(partner_id, offer_id))
    await callback.answer()


@router.callback_query(F.data.startswith("pc:clear:yes:"))
async def privilege_codes_clear(callback: CallbackQuery) -> None:
    _, _, _, partner_id, offer_id = callback.data.split(":", 4)
    deleted = 0
    try:
        codes = await get_api(callback).list_privilege_codes(offer_id)
        for code in codes:
            if privilege_code_status(code) == "✅ Свободен" and code.get("id") is not None:
                await get_api(callback).delete_privilege_code(code.get("id")); deleted += 1
    except WebApiError as exc:
        await callback.message.answer(f"Не удалось очистить коды: {privilege_code_user_error(exc)}")
    else:
        await callback.message.answer(f"Удалено: {deleted}")
        await show_privilege_codes(callback.message, partner_id, offer_id)
    await callback.answer()
