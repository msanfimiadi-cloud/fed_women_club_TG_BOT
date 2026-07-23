from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🖼 Баннеры"), KeyboardButton(text="📚 Справочники")],
            [KeyboardButton(text="➕ Создать партнёра"), KeyboardButton(text="📋 Список партнёров")],
            [KeyboardButton(text="🎁 Создать розыгрыш"), KeyboardButton(text="📋 Список розыгрышей")],
            [KeyboardButton(text="🌐 Открыть приложение"), KeyboardButton(text="🏠 Управление главной")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
    )


def skip_photo_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Пропустить", callback_data="skip_photo")]])


def after_partner_keyboard(partner_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить услугу", callback_data=f"offer:add:{partner_id}")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data="finish")],
        ]
    )


def after_offer_keyboard(partner_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить ещё услугу", callback_data=f"offer:add:{partner_id}")],
            [InlineKeyboardButton(text="✅ Завершить", callback_data="finish")],
        ]
    )


def partner_reference_keyboard(kind: str, items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = "partner_city" if kind == "cities" else "partner_category"
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue
        if item.get("is_active", item.get("active", True)) is False:
            continue
        name = item.get("title") or item.get("name") or f"#{item_id}"
        builder.button(text=str(name)[:55], callback_data=f"{prefix}:select:{item_id}")
    builder.button(text="Отмена", callback_data="back:menu")
    builder.adjust(1)
    return builder.as_markup()


def search_empty_keyboard(back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Назад", callback_data=back_callback)]])

def _add_search_controls(builder: InlineKeyboardBuilder, section: str) -> None:
    builder.button(text="🔍 Поиск", callback_data=f"search:start:{section}")
    builder.button(text="❌ Сбросить поиск", callback_data=f"search:reset:{section}")

def partners_keyboard(partners: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    _add_search_controls(builder, "partners")
    for partner in partners:
        partner_id = partner.get("id")
        if partner_id is None:
            continue
        name = partner.get("name") or partner.get("title") or f"Партнёр {partner_id}"
        builder.button(text=str(name)[:60], callback_data=f"partner:view:{partner_id}")
    builder.button(text="Назад", callback_data="back:menu")
    builder.adjust(1)
    return builder.as_markup()


def partner_actions_keyboard(partner_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    visibility_text = "🚫 Скрыть" if is_active else "✅ Показать"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"partner:edit:{partner_id}")],
            [InlineKeyboardButton(text="📷 Фото", callback_data=f"partner:photos:{partner_id}")],
            [InlineKeyboardButton(text="🛍 Услуги", callback_data=f"partner:offers:{partner_id}")],
            [InlineKeyboardButton(text="↕️ Порядок отображения", callback_data=f"partner:sort:menu:{partner_id}")],
            [InlineKeyboardButton(text=visibility_text, callback_data=f"partner:toggle:{partner_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="🗑️ Удалить партнёра", callback_data=f"partner:delete:confirm:{partner_id}")],
            [InlineKeyboardButton(text="Назад", callback_data="partners:list")],
        ]
    )



def partner_edit_keyboard(partner_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Название", callback_data=f"partner:edit_field:{partner_id}:name")],
            [InlineKeyboardButton(text="Описание", callback_data=f"partner:edit_field:{partner_id}:description")],
            [InlineKeyboardButton(text="Адрес", callback_data=f"partner:edit_field:{partner_id}:address")],
            [InlineKeyboardButton(text="Телефон", callback_data=f"partner:edit_field:{partner_id}:phone")],
            [InlineKeyboardButton(text="Статус", callback_data=f"partner:edit_field:{partner_id}:is_active")],
            [InlineKeyboardButton(text="Назад", callback_data=f"partner:view:{partner_id}")],
        ]
    )

def partner_delete_confirm_keyboard(partner_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"partner:delete:yes:{partner_id}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"partner:view:{partner_id}")],
        ]
    )


def partner_photos_keyboard(partner_id: int | str, photos: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить фото", callback_data=f"partner:photo:add:{partner_id}")
    if len(photos) > 1:
        builder.button(text="↕️ Порядок фото", callback_data=f"partner:photo:sort_menu:{partner_id}")
    for photo in photos:
        photo_id = photo.get("id")
        if photo_id is not None:
            builder.button(text=f"Сделать главным #{photo_id}", callback_data=f"partner:photo:main:{partner_id}:{photo_id}")
    builder.button(text="Назад", callback_data=f"partner:view:{partner_id}")
    builder.adjust(1)
    return builder.as_markup()


def offers_keyboard(partner_id: int | str, offers: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать услугу", callback_data=f"offer:add:{partner_id}")
    _add_search_controls(builder, f"offers:{partner_id}")
    for offer in offers:
        offer_id = offer.get("id")
        if offer_id is None:
            continue
        title = offer.get("title") or offer.get("name") or f"Услуга {offer_id}"
        builder.button(text=str(title)[:50], callback_data=f"offer:view:{partner_id}:{offer_id}")
    builder.button(text="Назад", callback_data=f"partner:view:{partner_id}")
    builder.adjust(1)
    return builder.as_markup()


def offer_actions_keyboard(partner_id: int | str, offer_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"offer:edit:{partner_id}:{offer_id}")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"offer:photo:menu:{partner_id}:{offer_id}")],
            [InlineKeyboardButton(text="↕️ Порядок отображения", callback_data=f"offer:sort:menu:{partner_id}:{offer_id}")],
            [InlineKeyboardButton(text="🎟 Коды привилегий", callback_data=f"pc:list:{partner_id}:{offer_id}")],
            [InlineKeyboardButton(text=("👁 Скрыть" if is_active else "👁‍🗨 Показать"), callback_data=f"offer:toggle:{partner_id}:{offer_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"offer:delete:confirm:{partner_id}:{offer_id}")],
            [InlineKeyboardButton(text="Назад", callback_data=f"partner:offers:{partner_id}")],
        ]
    )


def offer_edit_keyboard(partner_id: int | str, offer_id: int | str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Название", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:title")],
        [InlineKeyboardButton(text="Описание", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:description")],
        [InlineKeyboardButton(text="Условия", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:terms")],
        [InlineKeyboardButton(text="Цена", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:regular_price")],
        [InlineKeyboardButton(text="Старая цена", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:club_price")],
        [InlineKeyboardButton(text="Размер скидки", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:savings")],
        [InlineKeyboardButton(text="Статус", callback_data=f"offer:edit_field:{partner_id}:{offer_id}:is_active")],
        [InlineKeyboardButton(text="Назад", callback_data=f"offer:view:{partner_id}:{offer_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def offer_photo_keyboard(partner_id: int | str, offer_id: int | str, photos_or_has_photo: list[dict] | bool) -> InlineKeyboardMarkup:
    photo_count = len(photos_or_has_photo) if isinstance(photos_or_has_photo, list) else int(photos_or_has_photo)
    has_photo = photo_count > 0
    rows = [[InlineKeyboardButton(text="📷 Загрузить" if not has_photo else "♻️ Заменить", callback_data=f"offer:photo:add:{partner_id}:{offer_id}")]]
    if has_photo:
        if photo_count > 1:
            rows.append([InlineKeyboardButton(text="↕️ Порядок фото", callback_data=f"offer:photo:sort_menu:{partner_id}:{offer_id}")])
        rows.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"offer:photo:delete:{partner_id}:{offer_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"offer:view:{partner_id}:{offer_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)



def sort_order_keyboard(kind: str, entity_id: int | str, current: int, back_callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬆️ Выше", callback_data=f"{kind}:sort:move:{entity_id}:-1")],
        [InlineKeyboardButton(text="⬇️ Ниже", callback_data=f"{kind}:sort:move:{entity_id}:1")],
        [InlineKeyboardButton(text="✏️ Ввести вручную", callback_data=f"{kind}:sort:manual:{entity_id}")],
        [InlineKeyboardButton(text="Назад", callback_data=back_callback)],
    ])

def photo_sort_keyboard(kind: str, owner_id: int | str, photos: list[dict], back_callback: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for photo in photos:
        photo_id = photo.get("id")
        if photo_id is None:
            continue
        builder.button(text=f"⬆️ Фото #{photo_id}", callback_data=f"{kind}:photo:sort:{owner_id}:{photo_id}:-1")
        builder.button(text=f"⬇️ Фото #{photo_id}", callback_data=f"{kind}:photo:sort:{owner_id}:{photo_id}:1")
    builder.button(text="Назад", callback_data=back_callback)
    builder.adjust(2, 1)
    return builder.as_markup()

def offer_delete_confirm_keyboard(partner_id: int | str, offer_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"offer:delete:yes:{partner_id}:{offer_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"offer:view:{partner_id}:{offer_id}")],
    ])


def giveaways_keyboard(giveaways: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать розыгрыш", callback_data="giveaway:add")
    _add_search_controls(builder, "giveaways")
    for giveaway in giveaways:
        giveaway_id = giveaway.get("id")
        if giveaway_id is None:
            continue
        title = giveaway.get("title") or giveaway.get("name") or f"Розыгрыш {giveaway_id}"
        builder.button(text=str(title)[:60], callback_data=f"giveaway:view:{giveaway_id}")
    builder.button(text="Назад", callback_data="back:menu")
    builder.adjust(1)
    return builder.as_markup()


def giveaway_actions_keyboard(giveaway_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"giveaway:edit:{giveaway_id}")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"giveaway:photo:menu:{giveaway_id}")],
            [InlineKeyboardButton(text="🎁 Призы", callback_data=f"giveaway:items:list:{giveaway_id}")],
            [InlineKeyboardButton(text=("👁 Скрыть" if is_active else "👁‍🗨 Показать"), callback_data=f"giveaway:toggle:{giveaway_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="↕️ Порядок", callback_data=f"giveaway:edit_field:{giveaway_id}:sort_order")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"giveaway:delete:confirm:{giveaway_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="giveaways:list")],
        ]
    )


def giveaway_edit_keyboard(giveaway_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Название", callback_data=f"giveaway:edit_field:{giveaway_id}:title")],
            [InlineKeyboardButton(text="Описание", callback_data=f"giveaway:edit_field:{giveaway_id}:description")],
            [InlineKeyboardButton(text="Условия", callback_data=f"giveaway:edit_field:{giveaway_id}:terms")],
            [InlineKeyboardButton(text="Дата начала", callback_data=f"giveaway:edit_field:{giveaway_id}:starts_at")],
            [InlineKeyboardButton(text="Дата окончания", callback_data=f"giveaway:edit_field:{giveaway_id}:ends_at")],
            [InlineKeyboardButton(text="Статус", callback_data=f"giveaway:edit_field:{giveaway_id}:is_active")],
            [InlineKeyboardButton(text="Порядок отображения", callback_data=f"giveaway:edit_field:{giveaway_id}:sort_order")],
            [InlineKeyboardButton(text="Назад", callback_data=f"giveaway:view:{giveaway_id}")],
        ]
    )

def giveaway_items_menu_keyboard(giveaway_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список призов", callback_data=f"giveaway:items:list:{giveaway_id}")],
            [InlineKeyboardButton(text="➕ Добавить приз", callback_data=f"giveaway:item:add:{giveaway_id}")],
            [InlineKeyboardButton(text="Назад к розыгрышу", callback_data=f"giveaway:view:{giveaway_id}")],
        ]
    )


def giveaway_items_keyboard(giveaway_id: int | str, items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить приз", callback_data=f"giveaway:item:add:{giveaway_id}")
    _add_search_controls(builder, f"giveaway_items:{giveaway_id}")
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue
        title = item.get("title") or f"Приз {item_id}"
        active = bool(item.get("is_active", True))
        prefix = "✅" if active else "🚫"
        builder.button(text=f"{prefix} {str(title)[:50]}", callback_data=f"giveaway:item:view:{giveaway_id}:{item_id}")
    builder.button(text="Назад к розыгрышу", callback_data=f"giveaway:view:{giveaway_id}")
    builder.adjust(1)
    return builder.as_markup()


def giveaway_item_actions_keyboard(giveaway_id: int | str, item_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"giveaway:item:edit:{giveaway_id}:{item_id}")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"giveaway:item:photo:{giveaway_id}:{item_id}")],
            [InlineKeyboardButton(text=("👁 Скрыть" if is_active else "👁‍🗨 Показать"), callback_data=f"giveaway:item:toggle:{giveaway_id}:{item_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="↕️ Порядок", callback_data=f"giveaway:item:edit_field:{giveaway_id}:{item_id}:sort_order")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"giveaway:item:delete:confirm:{giveaway_id}:{item_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"giveaway:items:list:{giveaway_id}")],
        ]
    )


def giveaway_item_edit_keyboard(giveaway_id: int | str, item_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Название", callback_data=f"giveaway:item:edit_field:{giveaway_id}:{item_id}:title")],
            [InlineKeyboardButton(text="Описание", callback_data=f"giveaway:item:edit_field:{giveaway_id}:{item_id}:description")],
            [InlineKeyboardButton(text="Статус", callback_data=f"giveaway:item:edit_field:{giveaway_id}:{item_id}:is_active")],
            [InlineKeyboardButton(text="Порядок", callback_data=f"giveaway:item:edit_field:{giveaway_id}:{item_id}:sort_order")],
            [InlineKeyboardButton(text="Назад к призу", callback_data=f"giveaway:item:view:{giveaway_id}:{item_id}")],
        ]
    )


def banners_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список баннеров", callback_data="banners:list")],
            [InlineKeyboardButton(text="➕ Создать баннер", callback_data="banner:add")],
            [InlineKeyboardButton(text="Назад", callback_data="back:menu")],
        ]
    )


def banners_keyboard(banners: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать баннер", callback_data="banner:add")
    builder.button(text="↕️ Сортировка", callback_data="banners:sort")
    _add_search_controls(builder, "banners")
    for banner in banners:
        banner_id = banner.get("id")
        if banner_id is None:
            continue
        title = banner.get("title") or f"Баннер {banner_id}"
        active = bool(banner.get("is_active", banner.get("active", True)))
        builder.button(text=("✅ " if active else "🚫 ") + str(title)[:55], callback_data=f"banner:view:{banner_id}")
    builder.button(text="⬅️ Назад", callback_data="banners:menu")
    builder.adjust(1)
    return builder.as_markup()


def banner_actions_keyboard(banner_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"banner:edit:{banner_id}")],
            [InlineKeyboardButton(text="🖼 Фото", callback_data=f"banner:photo:menu:{banner_id}")],
            [InlineKeyboardButton(text=("👁 Скрыть" if is_active else "👁‍🗨 Показать"), callback_data=f"banner:toggle:{banner_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="↕️ Порядок", callback_data=f"banner:sort:menu:{banner_id}")],
            [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"banner:delete:confirm:{banner_id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="banners:list")],
        ]
    )


def banner_edit_keyboard(banner_id: int | str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=text, callback_data=f"banner:edit_field:{banner_id}:{field}")]
            for text, field in (("Название", "title"), ("Подзаголовок", "subtitle"), ("Описание", "description"), ("CTA", "cta_text"), ("Ссылка", "link_url"), ("Placement", "placement"), ("Статус", "is_active"), ("Порядок отображения", "sort_order"))]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"banner:view:{banner_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def banner_photo_keyboard(banner_id: int | str, has_photo: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📷 Загрузить" if not has_photo else "♻️ Заменить", callback_data=f"banner:photo:add:{banner_id}")]]
    if has_photo:
        rows.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"banner:photo:delete:{banner_id}")])
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"banner:view:{banner_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def banner_delete_confirm_keyboard(banner_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"banner:delete:yes:{banner_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"banner:view:{banner_id}")],
    ])


def home_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Контентные блоки", callback_data="blocks:list")],
            [InlineKeyboardButton(text="➕ Создать блок", callback_data="block:add")],
            [InlineKeyboardButton(text="Назад", callback_data="back:menu")],
        ]
    )


def blocks_keyboard(blocks: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Создать блок", callback_data="block:add")
    for block in blocks:
        block_id = block.get("id") or block.get("key")
        if block_id is None:
            continue
        active = bool(block.get("is_active", block.get("active", True)))
        key = block.get("key") or f"Блок {block_id}"
        placement = block.get("placement") or "-"
        builder.button(text=("✅ " if active else "🚫 ") + f"{key} · {placement}"[:55], callback_data=f"block:view:{block_id}")
    builder.button(text="Назад", callback_data="home:menu")
    builder.adjust(1)
    return builder.as_markup()


def block_actions_keyboard(block_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"block:edit:{block_id}")],
            [InlineKeyboardButton(text="🚫 Скрыть" if is_active else "✅ Опубликовать", callback_data=f"block:toggle:{block_id}:{int(not is_active)}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="blocks:list")],
        ]
    )


def block_edit_keyboard(block_id: int | str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=text, callback_data=f"block:edit_field:{block_id}:{field}")]
            for text, field in (("Заголовок", "title"), ("Body", "body"), ("Metadata JSON", "metadata_json"), ("Placement", "placement"), ("Locale", "locale"))]
    rows.append([InlineKeyboardButton(text="Назад", callback_data=f"block:view:{block_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def references_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏙 Города", callback_data="refs:cities")],
        [InlineKeyboardButton(text="🏷 Категории", callback_data="refs:categories")],
        [InlineKeyboardButton(text="Назад", callback_data="back:menu")],
    ])


def reference_section_keyboard(kind: str) -> InlineKeyboardMarkup:
    title = "городов" if kind == "cities" else "категорий"
    add = "город" if kind == "cities" else "категорию"
    prefix = "city" if kind == "cities" else "category"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"📋 Список {title}", callback_data=f"{prefix}:list")],
        [InlineKeyboardButton(text=f"➕ Добавить {add}", callback_data=f"{prefix}:add")],
        [InlineKeyboardButton(text="Назад", callback_data="refs:menu")],
    ])


def references_keyboard(kind: str, items: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    prefix = "city" if kind == "cities" else "category"
    builder.button(text="➕ Создать город" if prefix == "city" else "➕ Создать категорию", callback_data=f"{prefix}:add")
    builder.button(text="↕️ Сортировка", callback_data=f"{prefix}:sort:list")
    _add_search_controls(builder, prefix)
    for item in items:
        item_id = item.get("id")
        if item_id is None:
            continue
        name = item.get("title") or item.get("name") or f"#{item_id}"
        active = bool(item.get("is_active", item.get("active", True)))
        status = "🟢" if active else "🔴"
        sort_order = item.get("sort_order", 0)
        builder.button(text=f"{status} {str(name)[:38]} · #{sort_order}", callback_data=f"{prefix}:view:{item_id}")
    builder.button(text="Назад", callback_data=f"refs:{kind}")
    builder.adjust(1)
    return builder.as_markup()


def reference_actions_keyboard(prefix: str, item_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    visibility_text = "👁 Скрыть" if is_active else "👁‍🗨 Показать"
    visibility_action = "hide" if is_active else "publish"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"{prefix}:edit:{item_id}")],
        [InlineKeyboardButton(text=visibility_text, callback_data=f"{prefix}:{visibility_action}:{item_id}")],
        [InlineKeyboardButton(text="↕️ Порядок", callback_data=f"{prefix}:sort:menu:{item_id}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"{prefix}:delete:confirm:{item_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"{prefix}:list")],
    ])


def reference_delete_confirm_keyboard(prefix: str, item_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"{prefix}:delete:yes:{item_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"{prefix}:view:{item_id}")],
    ])


def reference_edit_keyboard(prefix: str, item_id: int | str) -> InlineKeyboardMarkup:
    label = "Название" if prefix == "city" else "Название/Title"
    field = "name" if prefix == "city" else "title"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"{prefix}:edit_field:{item_id}:{field}")],
        [InlineKeyboardButton(text="Статус", callback_data=f"{prefix}:edit_field:{item_id}:is_active")],
        [InlineKeyboardButton(text="Порядок отображения", callback_data=f"{prefix}:edit_field:{item_id}:sort_order")],
        [InlineKeyboardButton(text="Назад", callback_data=f"{prefix}:view:{item_id}")],
    ])


def privilege_codes_keyboard(partner_id: int | str, offer_id: int | str, codes: list[dict]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить код", callback_data=f"pc:add:{partner_id}:{offer_id}")
    builder.button(text="🗑 Массовое добавление", callback_data=f"pc:bulk:{partner_id}:{offer_id}")
    builder.button(text="🧹 Очистить неиспользованные", callback_data=f"pc:clear:confirm:{partner_id}:{offer_id}")
    _add_search_controls(builder, f"privilege_codes:{partner_id}:{offer_id}")
    for code in codes[:45]:
        code_id = code.get("id")
        if code_id is not None:
            label = str(code.get("code") or f"Код {code_id}")[:45]
            builder.button(text=label, callback_data=f"pc:view:{partner_id}:{offer_id}:{code_id}")
    builder.button(text="⬅️ Назад", callback_data=f"offer:view:{partner_id}:{offer_id}")
    builder.adjust(1)
    return builder.as_markup()


def privilege_code_actions_keyboard(partner_id: int | str, offer_id: int | str, code_id: int | str, is_active: bool) -> InlineKeyboardMarkup:
    visibility_text = "🚫 Деактивировать" if is_active else "🔄 Активировать"
    visibility_value = 0 if is_active else 1
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить", callback_data=f"pc:edit:{partner_id}:{offer_id}:{code_id}")],
        [InlineKeyboardButton(text=visibility_text, callback_data=f"pc:toggle:{partner_id}:{offer_id}:{code_id}:{visibility_value}")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"pc:delete:confirm:{partner_id}:{offer_id}:{code_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"pc:list:{partner_id}:{offer_id}")],
    ])


def privilege_code_delete_confirm_keyboard(partner_id: int | str, offer_id: int | str, code_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"pc:delete:yes:{partner_id}:{offer_id}:{code_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"pc:view:{partner_id}:{offer_id}:{code_id}")],
    ])


def privilege_codes_clear_confirm_keyboard(partner_id: int | str, offer_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да", callback_data=f"pc:clear:yes:{partner_id}:{offer_id}")],
        [InlineKeyboardButton(text="❌ Нет", callback_data=f"pc:list:{partner_id}:{offer_id}")],
    ])


def giveaway_photo_keyboard(giveaway_id: int | str, has_photo: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="📷 Загрузить" if not has_photo else "♻️ Заменить", callback_data=f"giveaway:photo:add:{giveaway_id}")]]
    if has_photo:
        rows.append([InlineKeyboardButton(text="🗑 Удалить фото", callback_data=f"giveaway:photo:delete:{giveaway_id}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data=f"giveaway:view:{giveaway_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def giveaway_delete_confirm_keyboard(giveaway_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да", callback_data=f"giveaway:delete:yes:{giveaway_id}")], [InlineKeyboardButton(text="❌ Нет", callback_data=f"giveaway:view:{giveaway_id}")]])

def giveaway_item_delete_confirm_keyboard(giveaway_id: int | str, item_id: int | str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Да", callback_data=f"giveaway:item:delete:yes:{giveaway_id}:{item_id}")], [InlineKeyboardButton(text="❌ Нет", callback_data=f"giveaway:item:view:{giveaway_id}:{item_id}")]])
