from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
import asyncio
import aiosqlite
from database.db import DB_PATH
from config import ADMIN_ID
from database.db import (
    update_driver_subscription, get_general_statistics, get_recent_orders,
    get_all_drivers_admin, get_all_clients_admin, get_all_orders_admin
)
from keyboards.reply import get_admin_menu_kb

router = Router()


class AdminBroadcast(StatesGroup):
    waiting_for_target = State()  # ЖАҢА: Кімге жіберетінін күту
    waiting_for_message = State()


# --- АДМИН ПАНЕЛІНЕ КІРУ ---

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Тек бастық қана кіре алатын мәзір"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Бұл бөлімге кіруге құқығыңыз жоқ.")
        return

    await message.answer(
        "👋 Қош келдіңіз, Бастық!\nБасқару панелі қосылды. Төмендегі батырмаларды қолданыңыз:",
        reply_markup=get_admin_menu_kb()
    )


# --- ЖАЛПЫ СТАТИСТИКА ---

@router.message(F.text == "📊 Статистика")
async def show_statistics(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    clients, drivers, orders_today = await get_general_statistics()

    text = (
        f"📈 <b>ЖАЛПЫ СТАТИСТИКА</b>\n\n"
        f"👥 Тіркелген клиенттер: <b>{clients}</b>\n"
        f"🚕 Тіркелген таксистер: <b>{drivers}</b>\n"
        f"🎯 Бүгінгі заказдар саны: <b>{orders_today}</b>"
    )
    await message.answer(text, parse_mode="HTML")


# --- ТАКСИСТЕРДІҢ ТОЛЫҚ ДЕРЕГІ ---

@router.message(F.text == "🚕 Тексеру: Таксистер")
async def show_all_drivers_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    drivers = await get_all_drivers_admin()
    if not drivers:
        await message.answer("Жүйеде ешқандай таксист тіркелмеген.")
        return

    text = "🗂 <b>БАРЛЫҚ ТІРКЕЛГЕН ТАКСИСТЕР ТІЗІМІ:</b>\n\n"
    for dr in drivers:
        name, phone, car, plate, reg_date, sub_start, sub_end, orders_count, is_online = dr
        status_text = "🟢 Онлайн" if is_online == 1 else "🔴 Оффлайн"

        text += (
            f"👤 <b>{name}</b>\n"
            f"📱 Тел: <code>{phone}</code>\n"
            f"🚘 Авто: {car} | 🔢 Мем. нөмір: <b>{plate}</b>\n"
            f"📅 Тіркелген күні: {reg_date}\n"
            f"⏳ Доступ: {sub_start} — {sub_end}\n"
            f"✅ Жасалған заказдар: <b>{orders_count}</b>\n"
            f"🔋 Белсенділігі: <b>{status_text}</b>\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        )

    # 4096 символдан асып кетсе, хабарламаны бөліп жібереміз
    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x + 4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# --- КЛИЕНТТЕРДІҢ ТОЛЫҚ ДЕРЕГІ ---

@router.message(F.text == "👥 Тексеру: Клиенттер")
async def show_all_clients_list(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    clients = await get_all_clients_admin()
    if not clients:
        await message.answer("Жүйеде ешқандай клиент тіркелмеген.")
        return

    text = "🗂 <b>БАРЛЫҚ ТІРКЕЛГЕН КЛИЕНТТЕР ТІЗІМІ:</b>\n\n"
    for cl in clients:
        name, phone, reg_date, orders_count = cl
        text += (
            f"👤 <b>{name}</b>\n"
            f"📱 Тел: <code>{phone}</code>\n"
            f"📅 Тіркелген күні: {reg_date}\n"
            f"📦 Жасалған заказдар: <b>{orders_count}</b>\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        )

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x + 4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# --- ЗАКАЗДАР БАЗАСЫ ---
@router.message(F.text == "📝 Соңғы заказдар")
async def show_recent_orders_detailed(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    orders = await get_all_orders_admin()
    if not orders:
        await message.answer("Әзірге базада ешқандай заказ жоқ.")
        return

    text = "📋 <b>ТАПСЫРЫСТАР БАЗАСЫ (Соңғылары жоғарыда):</b>\n\n"
    for order in orders:
        o_id, c_name, d_name, f_addr, t_addr, price, status, rating, review = order

        status_kaz = {
            "waiting": "⏳ Күтілуде",
            "accepted": "🚖 Қабылданды",
            "payment_pending": "💳 Төлем күтуде",
            "completed": "✅ Аяқталды",
            "cancelled": "❌ Жойылды"
        }
        current_status = status_kaz.get(status, status)
        driver_display = d_name if d_name else "<i>Ешкім алмады</i>"

        stars = '⭐️' * int(rating) if rating and int(rating) > 0 else 'Қойылмаған'
        review_text = review if review else 'Жоқ'

        text += (
            f"🔹 <b>Заказ №{o_id}</b> | Бағасы: <b>{price} тг</b>\n"
            f"🧍‍♂️ Кім берді: {c_name}\n"
            f"🚕 Кім қабылдады: {driver_display}\n"
            f"📍 Қайдан: {f_addr}\n"
            f"🏁 Қайда: {t_addr}\n"
            f"📊 Статус: {current_status}\n"
            f"⭐ <b>Баға:</b> {stars}\n"
            f"💬 <b>Пікір:</b> {review_text}\n"
            f"〰️〰️〰️〰️〰️〰️〰️〰️〰️\n"
        )

    if len(text) > 4000:
        for x in range(0, len(text), 4000):
            await message.answer(text[x:x + 4000], parse_mode="HTML")
    else:
        await message.answer(text, parse_mode="HTML")


# --- 📢 ЖАҢАРТЫЛҒАН ХАБАРЛАМА ТАРАТУ ЛОГИКАСЫ ---

@router.message(F.text == "📢 Хабарлама тарату")
async def start_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    # Сегменттеуге арналған Inline батырмалар
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚕 Таксистерге", callback_data="broadcast_driver")],
        [InlineKeyboardButton(text="👥 Клиенттерге", callback_data="broadcast_client")],
        [InlineKeyboardButton(text="🌍 Барлығына бірдей", callback_data="broadcast_all")]
    ])

    await message.answer("Кімдерге хабарлама таратамыз? Төмендегі батырмалардың бірін таңдаңыз:", reply_markup=keyboard)
    await state.set_state(AdminBroadcast.waiting_for_target)


@router.callback_query(F.data.startswith("broadcast_"), AdminBroadcast.waiting_for_target)
async def choose_target(call: CallbackQuery, state: FSMContext):
    target = call.data.split("_")[1]
    await state.update_data(target=target)

    target_text = {
        "driver": "🚕 Таксистер",
        "client": "👥 Клиенттер",
        "all": "🌍 Барлық пайдаланушылар"
    }

    await call.message.edit_text(
        f"✅ Таңдалған аудитория: <b>{target_text[target]}</b>\n\n"
        f"Енді жіберетін хабарламаңызды (мәтін немесе сурет) осында жіберіңіз:",
        parse_mode="HTML"
    )
    await state.set_state(AdminBroadcast.waiting_for_message)


@router.message(AdminBroadcast.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    target = data.get("target", "all")

    await message.answer("⏳ Хабарлама тарату басталды, күте тұрыңыз...")

    success_count = 0
    error_count = 0

    # Дерекқордан таңдалған аудиторияға қарай ID-лерді алу
    async with aiosqlite.connect(DB_PATH) as db:
        if target == "all":
            query = "SELECT telegram_id FROM users"
        elif target == "driver":
            query = "SELECT telegram_id FROM users WHERE role = 'driver'"
        elif target == "client":
            query = "SELECT telegram_id FROM users WHERE role = 'client'"

        async with db.execute(query) as cursor:
            users = await cursor.fetchall()

    if not users:
        await message.answer("❌ Бұл санатта ешқандай пайдаланушы табылмады.")
        await state.clear()
        return

    # Тарату циклі
    for row in users:
        user_id = row[0]
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id
            )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            error_count += 1

    target_names = {
        "driver": "Таксистер",
        "client": "Клиенттер",
        "all": "Барлығы"
    }

    await message.answer(
        f"✅ <b>Хабарлама сәтті таралды!</b>\n\n"
        f"🎯 Аудитория: <b>{target_names.get(target)}</b>\n"
        f"📨 Жеткізілді: <b>{success_count}</b> адамға\n"
        f"❌ Бұғаттағандар (қате): <b>{error_count}</b> адам",
        parse_mode="HTML"
    )

    await state.clear()

# --- ЧЕКТЕРДІ РАСТАУ ЛОГИКАСЫ ---

@router.callback_query(F.data.startswith("sub_approve:"))
async def approve_subscription(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    sub_type = parts[1]
    driver_id = int(parts[2])

    days = 1 if sub_type == "day" else 7
    period_text = "1 күн" if sub_type == "day" else "1 апта"

    # Базаны жаңарту
    await update_driver_subscription(driver_id, days=days)

    # PDF құжаттың астындағы жазуды жаңарту
    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n✅ <b>РАСТАЛДЫ ({period_text})</b>",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=driver_id,
            text=f"🎉 <b>Құттықтаймыз!</b> Төлеміңіз расталды.\n"
                 f"Сізге <b>{period_text}</b> доступ берілді.\n"
                 f"Енді «🚕 Линияға шығу» батырмасын басып жұмысты бастай аласыз!",
            parse_mode="HTML"
        )
    except Exception:
        pass

@router.callback_query(F.data.startswith("sub_reject:"))
async def reject_subscription(callback: CallbackQuery, bot: Bot):
    parts = callback.data.split(":")
    driver_id = int(parts[1])

    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n❌ <b>БАС ТАРТЫЛДЫ</b>",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=driver_id,
            text="❌ <b>Кешіріңіз, админ сіздің төлеміңізді растамады.</b>\n"
                 "Чекті дұрыстап қайта жіберіп көріңіз немесе админмен байланысыңыз.",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("sub_reject:"))
async def reject_subscription(callback: CallbackQuery, bot: Bot):
    driver_id = int(callback.data.split(":")[1])
    await callback.message.edit_caption(caption="❌ Төлем қабылданбады.")

    try:
        await bot.send_message(
            chat_id=driver_id,
            text="❌ Сіз жіберген чек жарамсыз немесе төлем расталмады. Қайтадан дұрыс PDF чек жіберіңіз немесе бастыққа хабарласыңыз."
        )
    except Exception:
        pass
    await callback.answer()