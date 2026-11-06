"""Private-chat-only confirmation flow, separate from admin content forms."""
from html import escape
from decimal import Decimal, InvalidOperation
import asyncio
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
    amount = State()


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
    await state.update_data(token=result["token"], repeat=bool(result["used_today"]), amount_revision=result.get("amount_revision", 0))
    if result.get("requires_order_amount"):
        await state.set_state(Flow.amount)
        await message.answer(f"Услуга: {escape(result['title'])}\nВведите фактическую стоимость покупки или услуги БЕЗ учёта скидки Bloom Club, в рублях. Скидку бот рассчитает автоматически. Например: 10000.")
        return
    await state.set_state(Flow.confirm)
    warning = ("\n\nСегодня уже было подтверждение. Подтверждайте только ДРУГУЮ покупку."
        if result["used_today"] else "")
    await message.answer(coupon_summary(result) + warning +
        "\n\nСверьте услугу и суммы с фактическим заказом. Если данные неверны, не подтверждайте: попросите клиента открыть новый купон с правильной суммой.\n\nУслуга оформлена на указанных условиях?",
        reply_markup=final_buttons(result["token"], bool(result["used_today"])))


def money(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0:
            return "не указана"
        return f"{amount:,.2f}".replace(",", " ").replace(".", ",") + " ₽"
    except (InvalidOperation, ValueError):
        return "не указана"


def coupon_summary(result):
    lines = [f"Участница: {escape(result['name'])}",
             f"Услуга: {escape(result['title'])}", "Подписка активна."]
    if result.get("code"):
        lines.append(f"Код купона: {escape(str(result['code']))}")
    if result.get("is_gift"):
        lines.append("Тип привилегии: подарок. Проверьте выполнение условий получения подарка.")
    else:
        lines.extend([f"Стоимость без скидки: {money(result.get('base_price'))}",
                      f"Скидка: {money(result.get('saving_amount'))}",
                      f"Стоимость со скидкой: {money(result.get('final_price'))}"])
        if result.get("requires_order_amount"):
            lines.append("⚠️ Для этой привилегии сумму заказа указывает клиент. Обязательно проверьте её перед подтверждением.")
    return "\n".join(lines)


def final_buttons(token, repeat=False, revision=None):
    builder = InlineKeyboardBuilder()
    suffix = f":{revision}" if revision is not None else ""
    builder.button(text=CONFIRM, callback_data=f"pcab:confirm:{token}:{int(repeat)}{suffix}")
    if revision is not None:
        builder.button(text="Исправить сумму", callback_data=f"pcab:amount:{token}")
    builder.button(text="Не подтверждать", callback_data="pcab:cancel")
    builder.adjust(1)
    return builder.as_markup()


def review_buttons(token):
    builder = InlineKeyboardBuilder()
    builder.button(text="Проверить согласование", callback_data=f"pcab:check:{token}")
    builder.button(text="Исправить сумму", callback_data=f"pcab:amount:{token}")
    builder.button(text="Не подтверждать", callback_data="pcab:cancel")
    builder.adjust(1)
    return builder.as_markup()


async def show_amount_result(message, state, result):
    revision = result['amount_revision']
    await state.update_data(amount_revision=revision, repeat=bool(result['used_today']))
    await state.set_state(Flow.confirm)
    if result['amount_review_status'] in ('matched', 'accepted'):
        await message.answer(coupon_summary(result) + "\n\nСумма согласована. Услуга оформлена на этих условиях?",
            reply_markup=final_buttons(result['token'], bool(result['used_today']), revision))
    elif result['amount_review_status'] == 'rejected':
        await message.answer("Клиент не согласен с суммой. Уточните стоимость БЕЗ скидки и нажмите «Исправить сумму».", reply_markup=review_buttons(result['token']))
    else:
        await message.answer("⚠️ Сумма отличается от указанной клиентом.\n"
            f"Клиент указал: {money(result.get('base_price'))}\n"
            f"Вы указали БЕЗ скидки: {money(result.get('partner_order_amount'))}\n"
            "Ожидаем согласования клиентом в приложении. Подтверждение пока недоступно.", reply_markup=review_buttons(result['token']))


_amount_waiters = set()


async def wait_for_amount(message, state, settings, token, revision):
    # Persistent agreement lives in the backend. The check button also works after a lost notification.
    for _ in range(300):
        await asyncio.sleep(3)
        data = await state.get_data()
        if data.get('token') != token or data.get('amount_revision') != revision or await state.get_state() != Flow.confirm.state:
            return
        try:
            result = await api(settings, 'POST', '/coupon/status', {**identity(message), 'token': token})
        except ApiError:
            return
        current = await state.get_data()
        if current.get('token') != token or current.get('amount_revision') != revision or await state.get_state() != Flow.confirm.state:
            return
        if result['amount_revision'] != revision:
            return
        if result['amount_review_status'] != 'pending':
            await show_amount_result(message, state, result)
            return


@router.message(Flow.amount, F.text, ~F.text.startswith('/'))
async def submit_amount(message: Message, state: FSMContext, settings):
    raw = message.text.strip().replace(' ', '').replace(',', '.')
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or amount <= 0 or amount > 1000000 or amount.as_tuple().exponent < -2:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer('Введите сумму БЕЗ скидки от 0,01 до 1 000 000 ₽, не более двух знаков после запятой.')
        return
    data = await state.get_data()
    result = await api(settings, 'POST', '/coupon/amount', {**identity(message), 'token': data['token'],
        'order_amount': str(amount), 'amount_revision': data['amount_revision']})
    await show_amount_result(message, state, result)
    if result['amount_review_status'] == 'pending':
        task = asyncio.create_task(wait_for_amount(message, state, settings, result['token'], result['amount_revision']))
        _amount_waiters.add(task)
        task.add_done_callback(_amount_waiters.discard)


@router.callback_query(Flow.confirm, F.data.startswith('pcab:amount:'))
@router.callback_query(Flow.confirm, F.data.startswith('pcab:check:'))
async def review_amount(callback: CallbackQuery, state: FSMContext, settings):
    data = await state.get_data()
    token = callback.data.split(':')[2]
    if token != data.get('token'):
        await callback.answer('Откройте купон заново.', show_alert=True)
        return
    result = await api(settings, 'POST', '/coupon/status', {**identity(callback), 'token': token})
    await callback.answer()
    if callback.data.startswith('pcab:amount:'):
        await state.update_data(amount_revision=result['amount_revision'])
        await state.set_state(Flow.amount)
        await callback.message.answer('Введите правильную стоимость БЕЗ учёта скидки Bloom Club, в рублях.')
    else:
        await show_amount_result(callback.message, state, result)


@router.callback_query(Flow.confirm, F.data == "pcab:cancel")
async def cancel_confirmation(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Подтверждение отменено. Если сумма неверна, попросите клиента открыть новый купон с правильной суммой.", reply_markup=menu())


@router.callback_query(Flow.confirm, F.data.startswith("pcab:confirm:"))
async def confirm(callback: CallbackQuery, state: FSMContext, settings):
    data = await state.get_data()
    parts = callback.data.split(":")
    if parts[2] != data.get("token") or (parts[3] == "1" and not data.get("repeat")):
        await callback.answer("Откройте новое подтверждение.", show_alert=True)
        return
    result = await api(settings, "POST", "/coupon/confirm", {**identity(callback),
        "token": data["token"], "allow_repeat": parts[3] == "1",
        "amount_revision": int(parts[4]) if len(parts) > 4 else None})
    await callback.answer()
    if result.get("repeat_confirmation_required"):
        await state.update_data(repeat=True)
        await callback.message.answer("Сегодня уже было подтверждение. Это другая покупка?",
            reply_markup=final_buttons(data["token"], True, int(parts[4]) if len(parts) > 4 else None))
        return
    await state.clear()
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer("Привилегия подтверждена. Запись сохранена в статистике Bloom Club.",
        reply_markup=menu())


@router.callback_query(F.data.startswith("pcab:"))
async def stale(callback: CallbackQuery):
    await callback.answer("Эта кнопка устарела. Начните подтверждение заново.", show_alert=True)

