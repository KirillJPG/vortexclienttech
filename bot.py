import asyncio
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.client.default import DefaultBotProperties
from aiohttp_socks import ProxyConnector 
from .config import (
    BOT_TOKEN,
    ADMIN_IDS,
    PROXY_URL,
    CUSTOM_BOT_API_URL,
    PRICES,
    CRYPTO_PAY_TOKEN,
)
from .database import (
    register_user,
    create_key,
    redeem_key,
    reset_hwid,
    ban_key,
    get_user_keys,
    get_key_details,
    get_statistics,
    get_all_keys_with_users,
    count_all_keys,
    record_purchase,
    is_invoice_processed,
)
from .crypto_pay import crypto_pay

# Настройка сессии для обхода блокировок с оптимизацией скорости
session = None
if PROXY_URL:
    session = AiohttpSession(proxy=PROXY_URL, limit=50)
elif CUSTOM_BOT_API_URL:
    api_server = TelegramAPIServer.from_base(CUSTOM_BOT_API_URL)
    session = AiohttpSession(api=api_server, limit=50)
bot = Bot(
    token=BOT_TOKEN,
    session=session,
    default=DefaultBotProperties(parse_mode="HTML")
)



dp = Dispatcher()
router = Router()
dp.include_router(router)


class Form(StatesGroup):
    waiting_for_redeem_key = State()
    waiting_for_reset_key = State()
    waiting_for_genkey = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def get_main_keyboard(user_id: int) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton(text="🛒 Купить ключ", callback_data="btn_buy"),
            InlineKeyboardButton(text="🔑 Активировать ключ", callback_data="btn_redeem")
        ],
        [
            InlineKeyboardButton(text="📋 Мои подписки", callback_data="btn_mykeys"),
            InlineKeyboardButton(text="🔄 Сбросить HWID", callback_data="btn_resethwid")
        ],
        [
            InlineKeyboardButton(text="ℹ️ Инструкция", callback_data="btn_help")
        ]
    ]
    if is_admin(user_id):
        buttons.append([InlineKeyboardButton(text="⚡ Панель администратора", callback_data="btn_admin")])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await register_user(message.from_user.id, message.from_user.username)

    welcome_text = (
        f"👋 Здравствуйте, <b>{message.from_user.first_name}</b>!\n\n"
        "Добро пожаловать в систему управления лицензиями лоадера.\n"
        "Здесь вы можете активировать ключ, управлять привязкой HWID и следить за сроком подписки.\n\n"
        "Выберите действие ниже:"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")


def get_buy_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=f"⚡ 1 день — {PRICES[1]} ₽", callback_data="buy_plan_1")],
        [InlineKeyboardButton(text=f"🚀 7 дней — {PRICES[7]} ₽", callback_data="buy_plan_7")],
        [InlineKeyboardButton(text=f"👑 30 дней — {PRICES[30]} ₽", callback_data="buy_plan_30")],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="btn_back_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_methods_keyboard(days: int) -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text="💎 Криптовалюта (CryptoBot)", callback_data=f"pay_crypto_{days}")],
        [InlineKeyboardButton(text="◀️ Назад к тарифам", callback_data="btn_buy")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.callback_query(F.data == "btn_buy")
async def cb_buy(call: CallbackQuery):
    await call.answer()
    text = (
        "🛒 <b>Магазин подписок Vortex Client:</b>\n\n"
        "Выберите подходящий тариф лицензии для лоадера:\n\n"
        f"• <b>⚡ 1 день</b> — <code>{PRICES[1]} ₽</code> <i>(Быстрый тест чита)</i>\n"
        f"• <b>🚀 7 дней</b> — <code>{PRICES[7]} ₽</code> <i>(Недельный доступ)</i>\n"
        f"• <b>👑 30 дней</b> — <code>{PRICES[30]} ₽</code> <i>(Месячный доступ, максимальная выгода)</i>\n\n"
        "💳 <b>Доступные способы оплаты:</b>\n"
        "• 💎 <b>CryptoBot:</b> USDT, TON, SOL, TRX, BTC, ETH, LTC, BNB, DOGE, USDC\n\n"
        "✅ После оплаты ключ генерируется моментально и сразу привязывается к вашему аккаунту."
    )
    await call.message.edit_text(text, reply_markup=get_buy_keyboard(), parse_mode="HTML")


@router.message(Command("buy"))
async def cmd_buy(message: Message):
    text = (
        "🛒 <b>Магазин подписок Vortex Client:</b>\n\n"
        "Выберите подходящий тариф лицензии для лоадера:\n\n"
        f"• <b>⚡ 1 день</b> — <code>{PRICES[1]} ₽</code> <i>(Быстрый тест чита)</i>\n"
        f"• <b>🚀 7 дней</b> — <code>{PRICES[7]} ₽</code> <i>(Недельный доступ)</i>\n"
        f"• <b>👑 30 дней</b> — <code>{PRICES[30]} ₽</code> <i>(Месячный доступ, максимальная выгода)</i>\n\n"
        "💳 <b>Доступные способы оплаты:</b>\n"
        "• 💎 <b>CryptoBot:</b> USDT, TON, SOL, TRX, BTC, ETH, LTC, BNB, DOGE, USDC\n\n"
        "✅ После оплаты ключ генерируется моментально и сразу привязывается к вашему аккаунту."
    )
    await message.answer(text, reply_markup=get_buy_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("buy_plan_"))
async def cb_buy_plan(call: CallbackQuery):
    await call.answer()
    days = int(call.data.replace("buy_plan_", ""))
    price = PRICES.get(days, 100)

    text = (
        "💳 <b>Оплата подписки:</b>\n\n"
        f"📦 <b>Выбранный тариф:</b> Лицензия на <b>{days} дн.</b>\n"
        f"💰 <b>Сумма к оплате:</b> <code>{price} ₽</code>\n\n"
        "Для оплаты нажмите кнопку ниже:"
    )
    await call.message.edit_text(text, reply_markup=get_payment_methods_keyboard(days), parse_mode="HTML")


@router.callback_query(F.data.startswith("pay_crypto_"))
async def cb_pay_crypto(call: CallbackQuery):
    await call.answer()
    days = int(call.data.replace("pay_crypto_", ""))
    price = PRICES.get(days, 100)
    user_id = call.from_user.id

    # Индикация загрузки
    await call.message.edit_text("⏳ <i>Создание счета в CryptoBot...</i>", parse_mode="HTML")

    # Создаем инвойс через Crypto Pay API
    invoice = await crypto_pay.create_invoice(amount=price, days=days, user_id=user_id)
    if not invoice:
        err_buttons = [
            [InlineKeyboardButton(text="🔄 Попробовать снова", callback_data=f"pay_crypto_{days}")],
            [InlineKeyboardButton(text="◀️ Назад к выбору оплаты", callback_data=f"buy_plan_{days}")]
        ]
        await call.message.edit_text(
            "❌ <b>Ошибка связи с платежным шлюзом CryptoBot.</b>\n"
            "Пожалуйста, попробуйте еще раз через минуту.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=err_buttons),
            parse_mode="HTML"
        )
        return

    invoice_id = invoice.get("invoice_id")
    pay_url = invoice.get("pay_url") or invoice.get("bot_invoice_url")

    text = (
        f"💎 <b>Оплата подписки через CryptoBot</b>\n\n"
        f"📦 <b>Тариф:</b> Лицензия лоадера на <b>{days} дн.</b>\n"
        f"💰 <b>Сумма к оплате:</b> <code>{price} ₽</code> <i>(в криптовалюте)</i>\n"
        f"🕒 <b>Срок действия счета:</b> 1 час\n\n"
        "🌐 <b>Поддерживаются любые криптовалюты:</b>\n"
        "<code>USDT, TON, SOL, TRX, BTC, ETH, LTC, BNB, DOGE, USDC</code>\n\n"
        "<b>Инструкция по оплате:</b>\n"
        "1. Нажмите кнопку <b>«💎 Оплатить в CryptoBot»</b> ниже.\n"
        "2. Выберите монету и подтвердите перевод в боте.\n"
        "3. После оплаты вернитесь сюда и нажмите <b>«🔄 Проверить оплату»</b>."
    )

    buttons = [
        [InlineKeyboardButton(text=f"💎 Оплатить в CryptoBot ({price} ₽)", url=pay_url)],
        [InlineKeyboardButton(text="🔄 Проверить оплату", callback_data=f"check_inv_{invoice_id}_{days}")],
        [InlineKeyboardButton(text="◀️ Назад к выбору оплаты", callback_data=f"buy_plan_{days}")]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("check_inv_"))
async def cb_check_invoice(call: CallbackQuery):
    parts = call.data.split("_")
    if len(parts) < 4:
        await call.answer("Некорректный запрос.", show_alert=True)
        return

    invoice_id = int(parts[2])
    days = int(parts[3])
    user_id = call.from_user.id
    username = call.from_user.username or "без username"

    # Защита от повторной обработки
    if await is_invoice_processed(invoice_id):
        await call.answer("✅ Этот счет уже оплачен и ключ был успешно выдан!", show_alert=True)
        return

    # Запрашиваем актуальный статус инвойса из CryptoBot
    invoice = await crypto_pay.get_invoice(invoice_id)
    if not invoice:
        await call.answer("Не удалось проверить статус счета. Попробуйте еще раз через несколько секунд.", show_alert=True)
        return

    status = invoice.get("status")

    if status == "paid":
        price = int(float(invoice.get("amount", PRICES.get(days, 100))))

        # Генерируем уникальный лицензионный ключ с привязкой к покупателю
        new_key = await create_key(duration_days=days, owner_id=user_id)
        await record_purchase(user_id=user_id, key=new_key, duration_days=days, price=price, invoice_id=invoice_id)

        await call.answer("🎉 Оплата успешно подтверждена!", show_alert=False)

        success_text = (
            "🎉 <b>Оплата через CryptoBot подтверждена!</b>\n\n"
            f"🔑 Ваш лицензионный ключ:\n"
            f"<code>{new_key}</code>\n\n"
            f"⏳ Срок действия: <b>{days} дн.</b>\n"
            f"💰 Оплачено: <b>{price} ₽</b> (Crypto Pay)\n\n"
            "✅ <b>Ключ уже привязан к вашему аккаунту</b> и сохранен в разделе «📋 Мои подписки».\n\n"
            "<b>Инструкция по запуску:</b>\n"
            "1. Запустите <code>loader.exe</code> на вашем ПК.\n"
            "2. Вставьте полученный ключ в поле «Лицензионный ключ».\n"
            "3. Нажмите кнопку «Войти в систему» и запустите нужный модуль!"
        )

        buttons = [
            [InlineKeyboardButton(text="📋 Мои подписки", callback_data="btn_mykeys")],
            [InlineKeyboardButton(text="◀️ В главное меню", callback_data="btn_back_main")]
        ]
        await call.message.edit_text(success_text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")

        # Оповещение администраторам
        admin_msg = (
            "🛒 <b>Успешная оплата через CryptoBot!</b>\n\n"
            f"👤 Покупатель: @{username} (ID: <code>{user_id}</code>)\n"
            f"📦 Тариф: <b>{days} дней</b>\n"
            f"💰 Сумма: <b>{price} ₽</b> (Счет #{invoice_id})\n"
            f"🔑 Выданный ключ: <code>{new_key}</code>"
        )
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(admin_id, admin_msg, parse_mode="HTML")
            except Exception:
                pass

    elif status == "active":
        await call.answer("⏳ Счет еще не оплачен. Оплатите счет в @CryptoBot и нажмите проверку снова.", show_alert=True)
    elif status == "expired":
        await call.answer("❌ Время действия счета истекло. Пожалуйста, создайте новый заказ.", show_alert=True)
        await call.message.edit_text(
            "❌ <b>Срок действия счета истек.</b>\nПожалуйста, выберите тариф заново:",
            reply_markup=get_buy_keyboard(),
            parse_mode="HTML"
        )
    else:
        await call.answer(f"Статус счета в CryptoBot: {status}. Ожидаем оплату...", show_alert=True)


@router.callback_query(F.data == "btn_help")
async def cb_help(call: CallbackQuery):
    await call.answer()
    help_text = (
        "📖 <b>Инструкция по использованию лоадера:</b>\n\n"
        "1. Получите лицензионный ключ у администратора.\n"
        "2. Нажмите <b>«🔑 Активировать ключ»</b> или отправьте <code>/redeem КЛЮЧ</code>.\n"
        "3. Запустите <code>loader.exe</code> на вашем компьютере.\n"
        "4. Введите ключ (при первом запуске ключ автоматически привяжется к вашему железу/HWID).\n"
        "5. Если вы сменили комплектующие или Windows, воспользуйтесь кнопкой <b>«🔄 Сбросить HWID»</b>."
    )
    await call.message.edit_text(help_text, reply_markup=get_main_keyboard(call.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "btn_redeem")
async def cb_redeem(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.set_state(Form.waiting_for_redeem_key)
    await call.message.edit_text(
        "🔑 <b>Введите ваш лицензионный ключ:</b>\n"
        "<i>(Пример: KEY-XXXX-XXXX-XXXX-XXXX)</i>",
        parse_mode="HTML"
    )


@router.message(Form.waiting_for_redeem_key)
async def process_redeem(message: Message, state: FSMContext):
    key_str = message.text.strip()
    success, msg = await redeem_key(key_str, message.from_user.id)
    await state.clear()

    if success:
        await message.answer(f"✅ <b>Успех!</b>\n{msg}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer(f"❌ <b>Ошибка:</b> {msg}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")


@router.message(Command("redeem"))
async def cmd_redeem(message: Message, command: CommandObject):
    if not command.args:
        await message.answer("Использование: <code>/redeem KEY-XXXX-XXXX-XXXX-XXXX</code>", parse_mode="HTML")
        return

    key_str = command.args.strip()
    success, msg = await redeem_key(key_str, message.from_user.id)
    if success:
        await message.answer(f"✅ <b>Успех!</b>\n{msg}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")
    else:
        await message.answer(f"❌ <b>Ошибка:</b> {msg}", reply_markup=get_main_keyboard(message.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "btn_mykeys")
async def cb_mykeys(call: CallbackQuery):
    await call.answer()
    keys = await get_user_keys(call.from_user.id)
    if not keys:
        text = "У вас пока нет привязанных ключей.\nИспользуйте «🔑 Активировать ключ»."
        kb = get_main_keyboard(call.from_user.id)
        await call.message.edit_text(text, reply_markup=kb)
        return

    text = "📋 <b>Ваши лицензии:</b>\n\n"
    buttons = []
    for k in keys:
        status_icon = "🟢" if not k["is_banned"] else "🔴 Заблокирован"
        hwid_status = "✅ Привязан" if k["hwid"] else "⚪ Не привязан"
        exp = k["expires_at"] or "Не активирован в лоадере"

        text += (
            f"🔑 <code>{k['key']}</code>\n"
            f"• Статус: {status_icon}\n"
            f"• Срок: {k['duration_days']} дн.\n"
            f"• Истекает: <code>{exp}</code>\n"
            f"• HWID: {hwid_status}\n\n"
        )
        if k["hwid"]:
            buttons.append([InlineKeyboardButton(text=f"🔄 Сбросить HWID для {k['key'][:12]}...", callback_data=f"reset_{k['key']}")])

    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="btn_back_main")])
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data == "btn_resethwid")
async def cb_resethwid_prompt(call: CallbackQuery, state: FSMContext):
    await call.answer()
    keys = await get_user_keys(call.from_user.id)
    active_hwid_keys = [k for k in keys if k["hwid"]]

    if not active_hwid_keys:
        await call.message.edit_text(
            "У вас нет ключей с активной привязкой HWID.",
            reply_markup=get_main_keyboard(call.from_user.id)
        )
        return

    buttons = []
    for k in active_hwid_keys:
        buttons.append([InlineKeyboardButton(text=f"Сбросить: {k['key']}", callback_data=f"reset_{k['key']}")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="btn_back_main")])

    await call.message.edit_text(
        "Выберите ключ для сброса привязки HWID:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("reset_"))
async def cb_do_reset(call: CallbackQuery):
    await call.answer()
    key = call.data.replace("reset_", "")
    success, msg = await reset_hwid(key, user_id=call.from_user.id, is_admin=is_admin(call.from_user.id))

    if success:
        await call.message.edit_text(f"✅ <b>{msg}</b>", reply_markup=get_main_keyboard(call.from_user.id), parse_mode="HTML")
    else:
        await call.message.edit_text(f"❌ <b>Ошибка:</b> {msg}", reply_markup=get_main_keyboard(call.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "btn_back_main")
async def cb_back_main(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    await call.message.edit_text("Главное меню:", reply_markup=get_main_keyboard(call.from_user.id))


# --- Административная панель ---

@router.callback_query(F.data == "btn_admin")
async def cb_admin(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещен!", show_alert=True)
        return

    await call.answer()
    stats = await get_statistics()
    text = (
        "⚡ <b>Панель администратора</b>\n\n"
        f"👥 Всего пользователей: <b>{stats['total_users']}</b>\n"
        f"🔑 Всего ключей: <b>{stats['total_keys']}</b>\n"
        f"🟢 Активных ключей: <b>{stats['active_keys']}</b>\n"
        f"📈 Успешных авторизаций: <b>{stats['successful_auths']}</b>\n"
        f"💰 Покупок: <b>{stats.get('total_purchases', 0)}</b> (Выручка: <b>{stats.get('total_revenue', 0)} ₽</b>)\n\n"
        "<b>Команды в чат:</b>\n"
        "• <code>/genkey &lt;дней&gt; [кол-во]</code> — Создать ключи\n"
        "• <code>/ban &lt;ключ&gt;</code> — Заблокировать ключ\n"
        "• <code>/unban &lt;ключ&gt;</code> — Разблокировать ключ\n"
        "• <code>/resethwid_admin &lt;ключ&gt;</code> — Принудительный сброс HWID\n"
        "• <code>/allkeys</code> — Список всех ключей и HWID\n"
        "• <code>/info &lt;ключ&gt;</code> — Детали по ключу"
    )
    buttons = [
        [
            InlineKeyboardButton(text="➕ Ключ (1 дн.)", callback_data="adm_gen_1"),
            InlineKeyboardButton(text="➕ Ключ (7 дн.)", callback_data="adm_gen_7"),
            InlineKeyboardButton(text="➕ Ключ (30 дн.)", callback_data="adm_gen_30")
        ],
        [
            InlineKeyboardButton(text="📋 Список всех ключей и HWID", callback_data="adm_keys_0")
        ],
        [InlineKeyboardButton(text="◀️ Назад в меню", callback_data="btn_back_main")]
    ]
    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")


@router.callback_query(F.data.startswith("adm_keys_"))
async def cb_adm_keys(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("Доступ запрещен!", show_alert=True)
        return

    page = int(call.data.replace("adm_keys_", ""))
    page_size = 4
    total_keys = await count_all_keys()
    total_pages = max(1, (total_keys + page_size - 1) // page_size)

    if page < 0:
        page = 0
    elif page >= total_pages:
        page = total_pages - 1

    keys = await get_all_keys_with_users(limit=page_size, offset=page * page_size)

    if not keys:
        text = "📋 <b>Список ключей:</b>\n\nБаза данных пуста. Создайте ключ через <code>/genkey &lt;дней&gt;</code>."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ В админ-панель", callback_data="btn_admin")]
        ])
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await call.answer()
        return

    text = f"📋 <b>Список всех ключей и HWID</b> (Стр. {page + 1}/{total_pages}):\n\n"
    buttons = []

    for k in keys:
        status_icon = "🟢 Активен" if not k["is_banned"] else "🔴 Заблокирован"
        hwid_str = f"<code>{k['hwid']}</code>" if k["hwid"] else "<i>Не привязан</i>"
        user_str = f"@{k['username']} (<code>{k['owner_id']}</code>)" if k["owner_id"] else "<i>Не привязан</i>"
        exp_str = k["expires_at"] if k["expires_at"] else "<i>Ожидает первого запуска</i>"

        text += (
            f"🔑 <code>{k['key']}</code>\n"
            f"• Статус: {status_icon} ({k['duration_days']} дн.)\n"
            f"• Пользователь: {user_str}\n"
            f"• HWID: {hwid_str}\n"
            f"• Истекает: <code>{exp_str}</code>\n\n"
        )
        if k["hwid"]:
            buttons.append([
                InlineKeyboardButton(
                    text=f"🔄 Сбросить HWID для {k['key'][:12]}...",
                    callback_data=f"adm_resethwid_{k['key']}_{page}"
                )
            ])

    # Навигационные кнопки
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Назад", callback_data=f"adm_keys_{page - 1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"• {page + 1}/{total_pages} •", callback_data="noop"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Вперед ▶️", callback_data=f"adm_keys_{page + 1}"))

    buttons.append(nav_buttons)
    buttons.append([InlineKeyboardButton(text="◀️ В админ-панель", callback_data="btn_admin")])

    await call.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("adm_resethwid_"))
async def cb_adm_resethwid(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    data = call.data.replace("adm_resethwid_", "")
    parts = data.rsplit("_", 1)
    key = parts[0]
    page = int(parts[1]) if len(parts) > 1 else 0

    success, msg = await reset_hwid(key, is_admin=True)
    await call.answer(f"HWID для {key[:12]}... сброшен!", show_alert=True)
    # Обновляем страницу списка
    call.data = f"adm_keys_{page}"
    await cb_adm_keys(call)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()



@router.callback_query(F.data.startswith("adm_gen_"))
async def cb_adm_gen(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return

    days = int(call.data.replace("adm_gen_", ""))
    new_key = await create_key(duration_days=days)

    await call.message.answer(
        f"✅ Сгенерирован новый ключ на <b>{days} дней</b>:\n\n"
        f"<code>{new_key}</code>",
        parse_mode="HTML"
    )
    await call.answer()


@router.message(Command("genkey"))
async def cmd_genkey(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return

    args = (command.args or "").split()
    if not args:
        await message.answer("Использование: <code>/genkey &lt;дней&gt; [кол-во]</code>\nПример: <code>/genkey 30 3</code>", parse_mode="HTML")
        return

    try:
        days = int(args[0])
        count = int(args[1]) if len(args) > 1 else 1
    except ValueError:
        await message.answer("Ошибка: количество дней и ключей должны быть числами.")
        return

    if count > 50:
        await message.answer("Максимум 50 ключей за один раз.")
        return

    generated = []
    for _ in range(count):
        k = await create_key(duration_days=days)
        generated.append(f"<code>{k}</code>")

    res_text = f"✅ Создано ключей: <b>{count}</b> на <b>{days} дней</b>:\n\n" + "\n".join(generated)
    await message.answer(res_text, parse_mode="HTML")


@router.message(Command("ban"))
async def cmd_ban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Использование: <code>/ban &lt;ключ&gt;</code>", parse_mode="HTML")
        return

    success, msg = await ban_key(command.args.strip(), ban_status=True)
    await message.answer(msg)


@router.message(Command("unban"))
async def cmd_unban(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Использование: <code>/unban &lt;ключ&gt;</code>", parse_mode="HTML")
        return

    success, msg = await ban_key(command.args.strip(), ban_status=False)
    await message.answer(msg)


@router.message(Command("resethwid_admin"))
async def cmd_resethwid_admin(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Использование: <code>/resethwid_admin &lt;ключ&gt;</code>", parse_mode="HTML")
        return

    success, msg = await reset_hwid(command.args.strip(), is_admin=True)
    await message.answer(msg)


@router.message(Command("info"))
async def cmd_info(message: Message, command: CommandObject):
    if not is_admin(message.from_user.id):
        return
    if not command.args:
        await message.answer("Использование: <code>/info &lt;ключ&gt;</code>", parse_mode="HTML")
        return

    info = await get_key_details(command.args.strip())
    if not info:
        await message.answer("Ключ не найден в базе данных.")
        return

    status = "🔴 Заблокирован" if info["is_banned"] else "🟢 Активен"
    text = (
        f"🔍 <b>Информация о ключе:</b>\n\n"
        f"• Ключ: <code>{info['key']}</code>\n"
        f"• Статус: {status}\n"
        f"• Дней: {info['duration_days']}\n"
        f"• Создан: <code>{info['created_at']}</code>\n"
        f"• Активирован: <code>{info['activated_at'] or 'Нет'}</code>\n"
        f"• Истекает: <code>{info['expires_at'] or 'Нет'}</code>\n"
        f"• HWID: <code>{info['hwid'] or 'Не привязан'}</code>\n"
        f"• Telegram Owner ID: <code>{info['owner_id'] or 'Не привязан'}</code>\n"
        f"• Посл. сброс HWID: <code>{info['last_hwid_reset'] or 'Нет'}</code>"
    )
    await message.answer(text, parse_mode="HTML")


@router.message(Command("allkeys"))
async def cmd_allkeys(message: Message):
    if not is_admin(message.from_user.id):
        return

    keys = await get_all_keys_with_users(limit=50, offset=0)
    if not keys:
        await message.answer("В базе данных нет ключей.")
        return

    text = f"📋 <b>Все ключи и HWID (Всего: {len(keys)}):</b>\n\n"
    for k in keys:
        status_icon = "🟢" if not k["is_banned"] else "🔴"
        hwid_str = f"<code>{k['hwid']}</code>" if k["hwid"] else "Не привязан"
        user_str = f"@{k['username']} (ID: {k['owner_id']})" if k["owner_id"] else "Не привязан"
        text += (
            f"{status_icon} <code>{k['key']}</code> ({k['duration_days']} дн.)\n"
            f"👤 {user_str}\n"
            f"💻 HWID: {hwid_str}\n"
            f"⏳ Истекает: <code>{k['expires_at'] or 'Ожидает входа'}</code>\n\n"
        )
    await message.answer(text, parse_mode="HTML")


