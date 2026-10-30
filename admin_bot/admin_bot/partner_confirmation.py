"""Private-chat-only confirmation flow, separate from admin content forms."""
from html import escape
import httpx
from aiogram import Router, F, BaseMiddleware
from aiogram.filters import StateFilter
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

CREATE = "Создать кабинет для подтверждения привилегий партнёров"
ENTER = "Режим подтверждения привилегий для ПАРТНЁРОВ"
CONFIRM = "Подтвердить привилегию"
EXIT = "Выход из партнёрского доступа"
router = Router(name="partner_confirmation")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class Flow(StatesGroup):
    admin_code = State()
    login = State()
    member = State()
    select_offer = State()
    confirm = State()


class ApiError(Exception):
    pass


async def api(settings, method, path, payload=None, *, admin=False):
    token = settings.telegram_admin_api_token if admin else settings.bot_service_token
    url = settings.web_api_base_url.rstrip("/") + "/partner-confirmation" + path
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.request(method, url, json=payload,
                headers={"Authorization": f"Bearer {token}"})
    except httpx.HTTPError:
        raise ApiError("Сервер временно недоступен. Повторите действие позже.") from None
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise ApiError(detail if isinstance(detail, str) else "Не удалось выполнить действие. Попробуйте заново.")
    try:
        return response.json()
    except ValueError:
        raise ApiError("Сервер вернул некорректный ответ. Попробуйте позже.") from None


class Errors(BaseMiddleware):
    async def __call__(self, handler, event, data):
        try:
            return await handler(event, data)
        except ApiError as exc:
            message = event.message if isinstance(event, CallbackQuery) else event
            await message.answer(escape(str(exc)))
            if isinstance(event, CallbackQuery):
                await event.answer()


class PublicNavigation(BaseMiddleware):
    async def __call__(self, handler, event, data):
        text = event.text or ""
        if text in {"🔐 Получить код для входа", "🌐 Открыть приложение", "📊 Моя статистика"} or text.split(" ", 1)[0] in {"/start", "/stats"}:
            state = data.get("state")
            if state is not None:
                await state.clear()
                data["raw_state"] = None
        return await handler(event, data)


router.message.outer_middleware(PublicNavigation())
router.message.middleware(Errors())
router.callback_query.middleware(Errors())


def menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text=CONFIRM)], [KeyboardButton(text=EXIT)]], resize_keyboard=True)


def identity(event):
    return {"telegram_id": str(event.from_user.id)}


def admin_allowed(event, settings):
    return event.from_user.id in settings.telegram_admin_ids


async def page(message, settings, number):
    result = await api(settings, "GET", f"/partners?page={number}", admin=True)
    builder = InlineKeyboardBuilder()
    for item in result["items"]:
        builder.button(text=item["name"][:55], callback_data=f"pcab:choose:{item['id']}")
    if number > 0:
        builder.button(text="← Назад", callback_data=f"pcab:page:{number-1}")
    if (number + 1) * 10 < result["total"]:
        builder.button(text="Далее →", callback_data=f"pcab:page:{number+1}")
    builder.adjust(1)
    await message.answer(f"Выберите партнёра. Страница {number+1}.", reply_markup=builder.as_markup())


@router.message(F.text == CREATE)
async def create(message: Message, state: FSMContext, settings):
    if not admin_allowed(message, settings):
        await message.answer("Нет доступа.")
        return
    await state.clear()
    await page(message, settings, 0)


@router.callback_query(F.data.startswith("pcab:page:"))
async def paginate(callback: CallbackQuery, settings):
    if not admin_allowed(callback, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    await page(callback.message, settings, int(callback.data.rsplit(":", 1)[1]))


@router.callback_query(F.data.startswith("pcab:choose:"))
async def choose(callback: CallbackQuery, state: FSMContext, settings):
    if not admin_allowed(callback, settings):
        await callback.answer("Нет доступа.", show_alert=True)
        return
    await callback.answer()
    await state.clear()
    await state.update_data(partner_id=int(callback.data.rsplit(":", 1)[1]))
    await state.set_state(Flow.admin_code)
    await callback.message.answer("Введите уникальный код для сотрудников: от 8 до 64 символов. "
        "Если кабинет уже есть, код будет заменён, а старые входы отозваны. /cancel — отмена.")


@router.message(Flow.admin_code, F.text, ~F.text.startswith("/"), ~F.text.in_({EXIT, ENTER, CREATE, CONFIRM}))
async def save_code(message: Message, state: FSMContext, settings):
    if not admin_allowed(message, settings):
        await state.clear()
        return
    data = await state.get_data()
    code = message.text.strip()
    if not 8 <= len(code) <= 64:
        await message.answer("Нужно от 8 до 64 символов.")
        return
    await api(settings, "PUT", f"/partners/{data['partner_id']}", {"code": code}, admin=True)
    try:
        await message.delete()
    except Exception:
        pass
    await state.clear()
    await message.answer("Код сохранён. Передайте его сотрудникам лично. Старые входы отозваны.")


@router.message(F.text == ENTER)
async def enter(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Flow.login)
    await message.answer("Введите код партнёрского доступа. /cancel — отмена.")


@router.message(F.text == EXIT)
async def leave(message: Message, state: FSMContext, settings):
    await api(settings, "POST", "/logout", identity(message))
    await state.clear()
    from .bot import public_onboarding_keyboard
    await message.answer("Вы вышли из партнёрского доступа.", reply_markup=public_onboarding_keyboard())


@router.message(StateFilter(Flow.login, Flow.member, Flow.select_offer, Flow.confirm, Flow.admin_code), F.text == "/cancel")
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    from .bot import public_onboarding_keyboard
    await message.answer("Действие отменено.", reply_markup=public_onboarding_keyboard())


@router.message(Flow.login, F.text, ~F.text.startswith("/"), F.text != CONFIRM)
async def login(message: Message, state: FSMContext, settings):
    code = message.text.strip()
    if len(code) > 64:
        await message.answer("Неверный код доступа.")
        return
    try:
        result = await api(settings, "POST", "/login", {**identity(message),
            "code": code, "display_name": message.from_user.full_name[:255]})
    finally:
        try:
            await message.delete()
        except Exception:
            pass
    await state.clear()
    await message.answer(f"Партнёрский доступ: {escape(result['partner_name'])}.", reply_markup=menu())


@router.message(F.text == CONFIRM)
async def start_confirmation(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Flow.member)
    await message.answer("Введите шестизначный код купона, который показывает клиент. Это код привилегии, а не номер участницы. /cancel — отмена.",
        reply_markup=menu())


@router.message(Flow.member, F.text, ~F.text.startswith("/"))
async def lookup(message: Message, state: FSMContext, settings):
    number = message.text.strip()
    if len(number) != 6 or not number.isascii() or not number.isdigit():
        await message.answer("Введите ровно 6 цифр, например 000049.")
        return
    result = await api(settings, "POST", "/coupon", {**identity(message), "code": number})
    if not result["subscription_active"]:
        await message.answer("Подписка неактивна — подтверждение недоступно.")
        return
    await state.update_data(token=result["token"], repeat=bool(result["used_today"]))
    await state.set_state(Flow.confirm)
    warning = ("\n\nСегодня уже было подтверждение. Подтверждайте только ДРУГУЮ покупку."
        if result["used_today"] else "")
    await message.answer(f"Участница: {escape(result['name'])}\n"
        f"Привилегия: {escape(result['title'])}\nПодписка активна."
        f"{warning}\n\nУслуга оформлена на условиях привилегии?",
        reply_markup=final_buttons(result["token"], bool(result["used_today"])))


def final_buttons(token, repeat=False):
    builder = InlineKeyboardBuilder()
    builder.button(text=CONFIRM, callback_data=f"pcab:confirm:{token}:{int(repeat)}")
    return builder.as_markup()


@router.callback_query(Flow.confirm, F.data.startswith("pcab:confirm:"))
async def confirm(callback: CallbackQuery, state: FSMContext, settings):
    data = await state.get_data()
    parts = callback.data.split(":")
    if parts[2] != data.get("token") or (parts[3] == "1" and not data.get("repeat")):
        await callback.answer("Откройте новое подтверждение.", show_alert=True)
        return
    result = await api(settings, "POST", "/coupon/confirm", {**identity(callback),
        "token": data["token"], "allow_repeat": parts[3] == "1"})
    await callback.answer()
    if result.get("repeat_confirmation_required"):
        await state.update_data(repeat=True)
        await callback.message.answer("Сегодня уже было подтверждение. Это другая покупка?",
            reply_markup=final_buttons(data["token"], True))
        return
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Привилегия подтверждена. Запись сохранена в статистике Bloom Club.",
        reply_markup=menu())


@router.callback_query(F.data.startswith("pcab:"))
async def stale(callback: CallbackQuery):
    await callback.answer("Эта кнопка устарела. Начните подтверждение заново.", show_alert=True)

