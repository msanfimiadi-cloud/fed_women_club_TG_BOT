from aiogram.fsm.state import State, StatesGroup


class PartnerCreate(StatesGroup):
    name = State()
    description = State()
    city = State()
    category = State()
    address = State()
    phone = State()
    photo = State()


class OfferCreate(StatesGroup):
    title = State()
    description = State()
    terms = State()
    regular_price = State()
    club_price = State()
    savings = State()
    photo = State()


class OfferEdit(StatesGroup):
    value = State()


class PartnerEdit(StatesGroup):
    value = State()


class PartnerPhotoAdd(StatesGroup):
    photo = State()


class OfferPhotoAdd(StatesGroup):
    photo = State()


class SortOrderManual(StatesGroup):
    value = State()


class GiveawayCreate(StatesGroup):
    title = State()
    description = State()
    terms = State()
    starts_at = State()
    ends_at = State()
    photo = State()


class GiveawayEdit(StatesGroup):
    title = State()
    description = State()
    terms = State()
    starts_at = State()
    ends_at = State()


class GiveawayPhotoAdd(StatesGroup):
    photo = State()


class GiveawayItemCreate(StatesGroup):
    title = State()
    description = State()
    sort_order = State()
    photo = State()


class GiveawayItemEdit(StatesGroup):
    title = State()
    description = State()
    sort_order = State()


class GiveawayItemPhotoAdd(StatesGroup):
    photo = State()


class BannerCreate(StatesGroup):
    title = State()
    subtitle = State()
    description = State()
    link_url = State()
    cta_text = State()
    placement = State()
    sort_order = State()
    photo = State()


class BannerEdit(StatesGroup):
    title = State()
    subtitle = State()
    description = State()
    link_url = State()
    cta_text = State()
    placement = State()
    is_active = State()
    sort_order = State()


class BannerPhotoAdd(StatesGroup):
    photo = State()


class BlockCreate(StatesGroup):
    key = State()
    placement = State()
    locale = State()
    title = State()
    body = State()
    metadata_json = State()
    is_active = State()


class BlockEdit(StatesGroup):
    title = State()
    body = State()
    metadata_json = State()
    placement = State()
    locale = State()


class CityCreate(StatesGroup):
    name = State()
    slug = State()
    sort_order = State()
    is_active = State()


class CityEdit(StatesGroup):
    name = State()
    slug = State()
    sort_order = State()


class CategoryCreate(StatesGroup):
    title = State()
    slug = State()
    sort_order = State()
    is_active = State()


class CategoryEdit(StatesGroup):
    title = State()
    slug = State()
    sort_order = State()


class PrivilegeCodeCreate(StatesGroup):
    code = State()


class PrivilegeCodeEdit(StatesGroup):
    code = State()


class PrivilegeCodeBulkImport(StatesGroup):
    payload = State()


class AdminSearch(StatesGroup):
    query = State()
