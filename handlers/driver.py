import asyncio
import html
from aiogram import Router, F, Bot, types
from aiogram.types import Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime, timedelta

from config import ADMIN_ID
from database.db import (
    check_driver_subscription, set_driver_online_status, update_order_status,
    assign_order_to_driver, get_order_details, get_driver, get_user, get_waiting_orders, change_user_mode, register_driver_complete, get_db_connection,
    auto_complete_order_after_timeout
)
from keyboards.inline import get_admin_sub_kb, get_driver_order_kb, get_client_decision_kb, get_broadcast_kb
from keyboards.reply import get_client_menu_kb

router = Router()


# --- ТАКСИСТІ ТІРКЕУ КҮЙЛЕРІ ---
class DriverRegistration(StatesGroup):
    waiting_for_name = State()
    waiting_for_phone = State()
    waiting_for_car = State()
    waiting_for_plate = State()


class PaymentState(StatesGroup):
    waiting_for_pdf = State()


# --- ТАКСИСТІ ТІРКЕУ ЛОГИКАСЫ ---
@router.message(F.text == "🚕 Мен таксистпін")
async def start_driver_registration(message: Message, state: FSMContext):
    await message.answer(
        "Тамаша! Таксист ретінде тіркелуді бастаймыз.\n\n"
        "Толық аты-жөніңізді жазыңыз (мысалы: Асан Төлеуов):"
    )
    await state.set_state(DriverRegistration.waiting_for_name)


@router.message(DriverRegistration.waiting_for_name)
async def process_driver_name(message: Message, state: FSMContext):
    await state.update_data(driver_name=message.text)
    await message.answer("Телефон нөміріңізді жазыңыз (мысалы: +77071234567):")
    await state.set_state(DriverRegistration.waiting_for_phone)


@router.message(DriverRegistration.waiting_for_phone)
async def process_driver_phone(message: Message, state: FSMContext):
    await state.update_data(driver_phone=message.text)
    await message.answer("Көлігіңіздің маркасы мен моделін жазыңыз (мысалы: Toyota Camry):")
    await state.set_state(DriverRegistration.waiting_for_car)


# ✨ ТҮЗЕТІЛДІ: Қайталанып тұрған екі функция біріктіріліп, тазартылды
@router.message(DriverRegistration.waiting_for_car)
async def process_driver_car(message: Message, state: FSMContext):
    await state.update_data(driver_car=message.text)
    await message.answer(
        "Керемет! Енді көліктің мемлекеттік нөмірін жазыңыз (мысалы: 123 ABC 06):"
    )
    await state.set_state(DriverRegistration.waiting_for_plate)


@router.message(DriverRegistration.waiting_for_plate)
async def process_driver_plate(message: Message, state: FSMContext):
    """Нөмірді алып, барлығын нағыз базаға сақтау және аяқтау"""
    driver_plate = message.text
    user_data = await state.get_data()

    driver_name = user_data.get('driver_name', message.from_user.full_name)
    driver_phone = user_data.get('driver_phone', 'Көрсетілмеген')
    driver_car = user_data.get('driver_car', 'Белгісіз көлік')
    driver_id = message.from_user.id

    reg_date = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 🔥 ТҮЗЕТІЛДІ: Базаға жазу кезінде қате шықса, бот үнсіз қалмай логқа жазады және чатқа ескертеді
    try:
        await register_driver_complete(
            telegram_id=driver_id,
            car_model=driver_car,
            car_number=driver_plate,
            full_name=driver_name,
            phone_number=driver_phone,
            reg_date=reg_date
        )
    except Exception as db_error:
        print(f"❌ Дерекқорға сақтау кезінде қате шықты: {db_error}")
        await message.answer(
            f"❌ <b>Тіркелу сәтсіз аяқталды! Жүйелік қате.</b>\n"
            f"Қате туралы мәлімет: <code>{db_error}</code>\n\n"
            f"Өтініш, Render логтарын тексеріңіз немесе db.py-дегі деректер типін қараңыз.",
            parse_mode="HTML"
        )
        return

    # Тек базаға сәтті сақталған жағдайда ғана төмендегі мәзір шығады:
    kb = [
        [KeyboardButton(text="🚕 Линияға шығу")],
        [KeyboardButton(text="👤 Клиент режиміне өту")]
    ]
    driver_menu_kb = ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

    safe_name = html.escape(str(driver_name))
    safe_phone = html.escape(str(driver_phone))
    safe_car = html.escape(str(driver_car))
    safe_plate = html.escape(str(driver_plate))

    await message.answer(
        f"🎉 Құттықтаймыз, {safe_name}!\n"
        f"💡 Сіз таксист ретінде жүйеге сәтті тіркелдіңіз.\n\n"
        f"📱 Тел: <b>{safe_phone}</b>\n"
        f"🚘 Көлік: <b>{safe_car}</b>\n"
        f"🔢 Нөмір: <b>{safe_plate}</b>\n\n"
        f"Енді жұмысты бастау үшін төмендегі «🚕 Линияға шығу» батырмасын басыңыз.",
        reply_markup=driver_menu_kb,
        parse_mode="HTML"
    )
    await state.clear()


@router.message(F.text == "🚕 Линияға шығу")
async def go_online(message: Message, state: FSMContext):
    """Таксист линияға шыққысы келгенде жазылымын тексереміз және бос заказдарды ұсынамыз"""
    has_sub = await check_driver_subscription(message.from_user.id)

    if has_sub:
        await set_driver_online_status(message.from_user.id, 1)

        online_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🔴 Линиядан шығу")]],
            resize_keyboard=True
        )

        await message.answer(
            "🟢 <b>Сіз линиядасыз! Жаңа заказдарды күтіңіз.</b>",
            reply_markup=online_kb,
            parse_mode="HTML"
        )

        waiting_orders = await get_waiting_orders()

        if waiting_orders:
            await message.answer(
                f"📦 Жүйеде сізді күтіп тұрған <b>{len(waiting_orders)} тапсырыс</b> бар.\n"
                f"Олар төменде көрсетілді 👇"
            )
            for order in waiting_orders:
                # 🌟 ҚАУІПСІЗ ТӘСІЛ: Мәліметтерді индекс арқылы ажыратамыз
                order_id = order[0]
                from_addr = order[1]
                to_addr = order[2]
                price = order[3]
                client_name = order[4]
                client_phone = order[5]
                order_type = order[6] if len(order) > 6 else "local"

                # Хабарламада бағытты анық көрсету үшін белгі қосамыз
                route_label = "🏙 ҚАЛА АРАЛЫҚ" if order_type == "intercity" else "🏘 АУЫЛ ІШІ"

                order_text = (
                    f"🚨 <b>БӨГЕЛГЕН ТАПСЫРЫС (№{order_id}) — {route_label}</b>\n\n"
                    f"📍 Қайдан: <b>{from_addr}</b>\n"
                    f"🏁 Қайда: <b>{to_addr}</b>\n"
                    f"💰 Бағасы: <b>{price} тг</b>\n\n"
                    f"👤 Клиент: <b>{client_name}</b>\n"
                    f"📱 Тел: <code>{client_phone}</code>\n\n"
                    f"👇 <i>Заказды алғыңыз келсе, батырманы басыңыз:</i>"
                )
                try:
                    await message.bot.send_message(
                        chat_id=message.from_user.id,
                        text=order_text,
                        reply_markup=get_broadcast_kb(order_id, price, order_type=order_type),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Хабарлама жіберуде қате: {e}")
    else:
        sub_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="1 күн - 500 тг", callback_data="buy_sub_day")],
            [InlineKeyboardButton(text="1 апта - 3000 тг", callback_data="buy_sub_week")]
        ])
        await message.answer(
            "⚠️ <b>Линияға шығу үшін доступ алу қажет.</b>\n"
            "Төмендегі тарифтердің бірін таңдаңыз:",
            reply_markup=sub_kb,
            parse_mode="HTML"
        )


@router.message(F.text == "🔴 Линиядан шығу")
async def go_offline(message: Message):
    """Таксист линиядан шыққысы келгенде"""
    await set_driver_online_status(message.from_user.id, 0)

    offline_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚕 Линияға шығу")]
        ],
        resize_keyboard=True
    )

    await message.answer(
        "🔴 <b>Сіз линиядан шықтыңыз. Демалысыңыз жақсы өтсін!</b>\n\n"
        "Қайтадан жұмысқа кірісу үшін төмендегі батырманы басыңыз.",
        reply_markup=offline_kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_(["buy_sub_day", "buy_sub_week"]))
async def process_sub_choice(call: CallbackQuery, state: FSMContext):
    if call.data == "buy_sub_day":
        period = "1 күн"
        price = "500"
    else:
        period = "1 апта"
        price = "3000"

    await state.update_data(sub_period=period)
    await state.set_state(PaymentState.waiting_for_pdf)

    await call.message.edit_text(
        f"Керемет! Сіз <b>{period}</b> доступ таңдадыңыз.\n"
        f"Төлем сомасы: <b>{price} тг.</b>\n\n"
        f"💳 Kaspi нөмірі: <code>+7 701 365 3276</code> (Эльмира Е.)\n\n"
        f"⚠️ <i>Каспиден скриншот жасалмайтындықтан, төлем жасаған соң Kaspi-ден жүктелген <b>PDF форматтағы чекті</b> осы чатқа файл ретінде жіберіңіз:</i>",
        parse_mode="HTML"
    )


@router.message(PaymentState.waiting_for_pdf)
async def handle_receipt_pdf(message: Message, state: FSMContext, bot: Bot):
    if message.document and message.document.mime_type == "application/pdf":
        user_data = await state.get_data()
        period = user_data.get('sub_period', 'Белгісіз мерзім')
        user_id = message.from_user.id

        user_info = await get_user(user_id)
        if user_info:
            driver_name = user_info[1]
            driver_phone = user_info[2]
        else:
            driver_name = message.from_user.full_name
            driver_phone = "Белгісіз"

        admin_msg = (
            f"🆕 <b>ЖАҢА ТӨЛЕМ (PDF ЧЕК)!</b>\n\n"
            f"👤 Жүргізуші: <b>{driver_name}</b>\n"
            f"📱 Тел: <code>{driver_phone}</code>\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"⏳ Сұратылған доступ: <b>{period}</b>\n\n"
            f"Төмендегі батырмалар арқылы растаңыз немесе бас тартыңыз:"
        )

        sub_type = "day" if period == "1 күн" else "week"
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Растау", callback_data=f"sub_approve:{sub_type}:{user_id}")],
            [InlineKeyboardButton(text="❌ Бас тарту", callback_data=f"sub_reject:{user_id}")]
        ])

        await bot.send_document(
            chat_id=ADMIN_ID,
            document=message.document.file_id,
            caption=admin_msg,
            reply_markup=admin_kb,
            parse_mode="HTML"
        )

        await message.answer("✅ PDF чек сәтті жіберілді! Админ растаған соң сізге хабарлама келеді.")
        await state.clear()
    else:
        await message.answer(
            "⚠️ Қате! Өтініш, чекті сурет емес, дәл Kaspi қосымшасынан жүктелген <b>PDF форматта</b> жіберіңіз."
        )


@router.callback_query(F.data.startswith("order_finish:"))
async def process_order_payment_pending(callback: CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    await update_order_status(order_id, "payment_pending")

    await callback.message.edit_text(
        "🏁 Сіз мекенжайға жеттіңіз.\n"
        "Клиент сізге Kaspi немесе қолма-қол ақша аударған соң, төмендегі батырманы басыңыз.\n"
        "⚠️ Назар аударыңыз! Төлемді растамайынша жаңа заказ ала алмайсыз!",
        reply_markup=get_driver_order_kb(order_id, "payment_pending")
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_paid:"))
async def process_order_paid(call: CallbackQuery, bot: Bot):
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])
    driver_id = call.from_user.id  # Жүргізушінің Telegram ID-сі

    order_info = await get_order_details(order_id)
    if not order_info:
        await call.answer("Тапсырыс табылдамады!", show_alert=True)
        return

    client_id = order_info[5]

    conn = await get_db_connection()
    try:
        row = await conn.fetchrow("SELECT created_at FROM orders WHERE order_id = $1", order_id)
        created_at_val = row[0] if row else None
    finally:
        await conn.close()

    if created_at_val:
        try:
            if isinstance(created_at_val, str):
                created_time = datetime.strptime(created_at_val[:19], "%Y-%m-%d %H:%M:%S")
            else:
                created_time = created_at_val

            now = datetime.now()
            seconds_passed = (now - created_time).total_seconds()

            if seconds_passed < 240:
                remaining_seconds = int(240 - seconds_passed)
                remaining_minutes = (remaining_seconds // 60) + 1

                await call.answer(
                    f"🛑 Сапарды аяқтауға әлі ерте!\n\n"
                    f"Жүйе қауіпсіздігі үшін сапар кемінде 4 минутқа созылуы керек. "
                    f"Тағы шамамен {remaining_minutes} минут күте тұрыңыз.",
                    show_alert=True
                )
                return

        except Exception as e:
            print(f"Уақытты есептеуде қате шықты: {e}")

    # 1. Заказды сәтті жабамыз
    await update_order_status(order_id, 'completed')

    # Базада жүргізушіні ресми түрде ЛИНЯҒА ҚАЙТА ҚОСАМЫЗ (Енді ол бос!)
    await set_driver_online_status(driver_id, 1)

    try:
        await call.answer("Төлем расталды! Тапсырыс жабылды.")
    except Exception:
        pass

    await call.message.edit_text(
        f"✅ <b>Тапсырыс №{order_id} толықтай аяқталды!</b>\n\n"
        f"Ақшаңызды алдыңыз. Сіз қайтадан линиядасыз (жаңа заказ қабылдауға дайынсыз). 🚕",
        parse_mode="HTML"
    )

    stars_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 ⭐️", callback_data=f"rate_driver:{order_id}:1"),
            InlineKeyboardButton(text="2 ⭐️", callback_data=f"rate_driver:{order_id}:2"),
            InlineKeyboardButton(text="3 ⭐️", callback_data=f"rate_driver:{order_id}:3")
        ],
        [
            InlineKeyboardButton(text="4 ⭐️", callback_data=f"rate_driver:{order_id}:4"),
            InlineKeyboardButton(text="5 ⭐️", callback_data=f"rate_driver:{order_id}:5")
        ]
    ])

    try:
        await bot.send_message(
            chat_id=client_id,
            text="✅ <b>Төлеміңіз расталды!</b>\n\n"
                 "Біздің қызметті пайдаланғаныңыз үшін рақмет. 👋\n"
                 "Сапарыңыз қалай өтті? Жүргізушіге қандай баға қоясыз? 👇",
            reply_markup=stars_kb,
            parse_mode="HTML"
        )

        waiting_orders = await get_waiting_orders()

        if waiting_orders:
            await bot.send_message(
                chat_id=driver_id,
                text="🔔 <b>Кезекте күтіп тұрған жаңа тапсырыстар бар:</b>",
                parse_mode="HTML"
            )
            for w_order in waiting_orders:
                # 🌟 ҚАУІПСІЗ ТӘСІЛ: Мәліметтерді индекс арқылы бөліп алу
                w_order_id = w_order[0]
                w_from = w_order[1]
                w_to = w_order[2]
                w_price = w_order[3]
                w_client_name = w_order[4]
                w_client_phone = w_order[5]
                w_type = w_order[6] if len(w_order) > 6 else "local"

                w_route_label = "🏙 ҚАЛА АРАЛЫҚ" if w_type == "intercity" else "🏘 АУЫЛ ІШІ"

                order_text = (
                    f"🚨 <b>БӨГЕЛГЕН ТАПСЫРЫС (№{w_order_id}) — {w_route_label}</b>\n\n"
                    f"📍 Қайдан: <b>{w_from}</b>\n"
                    f"🏁 Қайда: <b>{w_to}</b>\n"
                    f"💰 Бағасы: <b>{w_price} тг</b>\n\n"
                    f"👤 Клиент: <b>{w_client_name}</b>\n"
                    f"📱 Тел: <code>{w_client_phone}</code>\n\n"
                    f"👇 <i>Заказды алғыңыз келсе, батырманы басыңыз:</i>"
                )

                try:
                    await bot.send_message(
                        chat_id=driver_id,
                        text=order_text,
                        reply_markup=get_broadcast_kb(w_order_id, w_price, order_type=w_type),
                        parse_mode="HTML"
                    )
                except Exception as e:
                    print(f"Кезектегі хабарламаны жіберу қатесі: {e}")
        else:
            await bot.send_message(
                chat_id=driver_id,
                text="🚕 Қазіргі уақытта жаңа тапсырыстар жоқ. Линияда күте тұрыңыз."
            )

    except Exception as e:
        print(f"Клиентке хабарлама жіберуде қате шықты: {e}")


@router.callback_query(F.data.startswith("take_order:"))
async def accept_order_directly(callback: CallbackQuery, bot: Bot):
    _, order_id, price = callback.data.split(":")
    order_id, price = int(order_id), int(price)
    driver_id = callback.from_user.id

    # 🌟 1-ӨЗГЕРІС: success және res (сәтсіз болғандағы нақты себеп) айнымалыларын қабылдаймыз
    success, res = await assign_order_to_driver(order_id, driver_id, price)

    if success:
        # 🌟 2-ӨЗГЕРІС: Таксисті бірден офлайн қылып тастайтын жолды алып тастадық (немесе комментарий жасадық)
        # await set_driver_online_status(driver_id, 0)  <-- Енді бұл керек емес, таксист линияда қала береді

        order_info = await get_order_details(order_id)
        client_name, client_phone, client_id = order_info[3], order_info[4], order_info[5]

        order_type = order_info[6] if len(order_info) > 6 else "local"

        timeout_minutes = 60 if order_type == "intercity" else 10
        timeout_seconds = timeout_minutes * 60
        deadline_time = (datetime.now() + timedelta(minutes=timeout_minutes)).strftime("%H:%M")

        await callback.message.edit_text(
            f"✅ <b>Заказ қабылданды!</b>\n\n"
            f"⏱ <b>Аяқтау уақыты:</b> {deadline_time}-ге дейін.\n"
            f"⚠️ Сапарды макс. {timeout_minutes} минут ішінде аяқтауыңыз керек (кемі 4 минуттан кейін аяқтауға болады).\n\n"
            f"👤 Клиент: {client_name}\n"
            f"📱 Телефон: {client_phone}\n"
            f"📍 Қайдан: {order_info[0]}\n"
            f"🏁 Қайда: {order_info[1]}\n\n"
            f"Клиентке жеткен соң төмендегі батырманы басыңыз.",
            reply_markup=get_driver_order_kb(order_id, "accepted"),
            parse_mode="HTML"
        )

        driver_user_info = await get_user(driver_id)
        driver_name = driver_user_info[1] if driver_user_info else "Анықталмады"
        driver_phone = driver_user_info[2] if driver_user_info else "Анықталмады"

        driver_info = await get_driver(driver_id)
        car_model = driver_info[1] if driver_info else "Анықталмады"
        car_number = driver_info[2] if driver_info else "Анықталмады"

        await bot.send_message(
            chat_id=client_id,
            text=f"🚕 <b>Сізге такси келе жатыр!</b>\n\n"
                 f"⏱ <b>Жеткізу/Бару уақыты:</b> {deadline_time}-ге дейін.\n"
                 f"👤 Жүргізуші: <b>{driver_name}</b>\n"
                 f"📱 Телефон: <code>{driver_phone}</code>\n"
                 f"🚘 Көлік: <b>{car_model}</b>\n"
                 f"🔢 Мемлекеттік нөмірі: <code>{car_number}</code>\n"
                 f"💰 Баға: <b>{price} тг</b>",
            parse_mode="HTML"
        )

        asyncio.create_task(auto_complete_order_after_timeout(order_id, bot, timeout_seconds))

    else:
        # 🌟 3-ӨЗГЕРІС: Егер лимит толып қалса (3 заказ) немесе заказ басқа адамға кетсе,
        # `res` ішіндегі нақты қатені таксистке терезе (alert) етіп шығарамыз
        await callback.answer(text=res, show_alert=True)
        # Хабарлама мәтінін де қатеге сәйкес өзгертеміз
        await callback.message.edit_text(f"❌ {res}")


@router.callback_query(F.data.startswith("offer:"))
async def offer_new_price(callback: CallbackQuery, bot: Bot):
    _, order_id, new_price = callback.data.split(":")
    order_id, new_price = int(order_id), int(new_price)
    driver_id = callback.from_user.id

    driver_user_info = await get_user(driver_id)
    driver_name = driver_user_info[1] if driver_user_info else "Таксист"

    order_info = await get_order_details(order_id)
    if not order_info:
        await callback.answer("Заказ табылмады.", show_alert=True)
        return

    client_id = order_info[5]

    await bot.send_message(
        chat_id=client_id,
        text=f"🔔 <b>Таксист баға ұсынды!</b>\n\n"
             f"🚕 Жүргізуші: {driver_name}\n"
             f"💰 Ұсынған баға: <b>{new_price} тг</b>\n\n"
             f"Келісесіз бе?",
        reply_markup=get_client_decision_kb(order_id, driver_id, new_price),
        parse_mode="HTML"
    )

    await callback.message.edit_text(f"⏳ Клиентке {new_price} тг ұсынылды. Жауап күтілуде...")


@router.callback_query(F.data.startswith("order_arrived:"))
async def process_driver_arrived(call: CallbackQuery, bot: Bot):
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])
    driver_id = call.from_user.id

    order_info = await get_order_details(order_id)
    if not order_info:
        await call.answer("Тапсырыс базадан табылмады!", show_alert=True)
        return

    client_id = order_info[5]
    await call.answer("Клиентке хабарлама жітелді")

    await call.message.edit_text(
        f"🚖 <b>Тапсырыс №{order_id}</b>\n\n"
        f"📍 Сіз мекенжайға келдіңіз. Клиентке хабарланды, көлікке отыруын күтіңіз...",
        parse_mode="HTML"
    )

    client_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚖 Таксиге отырдым", callback_data=f"client_onboard:{order_id}:{driver_id}")]
    ])

    try:
        await bot.send_message(
            chat_id=client_id,
            text="🚕 <b>Таксист сіз айтқан мекенжайға келіп тұр!</b>\n"
                 "Сыртқа шығып көлікті іздесеңіз болады.\n\n"
                 "👇 <i>Көлікке отырғаннан кейін төмендегі батырманы басып, растаңыз:</i>",
            reply_markup=client_kb,
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("client_onboard:"))
async def process_client_onboard(call: CallbackQuery, bot: Bot):
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])
    driver_id = int(data_parts[2])

    await call.answer("Сапар басталды")

    await call.message.edit_text(
        "⚪ <b>Ақ жол! Сапарыңыз сәтті өтсін. 👍</b>",
        parse_mode="HTML"
    )

    driver_finish_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏁 Тапсырысты аяқтау", callback_data=f"complete_order:{order_id}")]
    ])

    try:
        await bot.send_message(
            chat_id=driver_id,
            text=f"🚖 <b>Тапсырыс №{order_id} басталды!</b>\n\n"
                 f"Клиент көлікке отырғанын растады.\n"
                 f"Баратын жерге жеткен соң төмендегі батырманы басып, тапсырысты жабыңыз.",
            reply_markup=driver_finish_kb,
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("complete_order:"))
async def process_order_finish(call: CallbackQuery, bot: Bot):
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])

    order_info = await get_order_details(order_id)
    if not order_info:
        await call.answer("Тапсырыс табылмады!", show_alert=True)
        return

    client_id = order_info[5]
    await call.answer("Клиенттен төлем күтілуде...")

    payment_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Төлемді растау (Ақша түсті)", callback_data=f"order_paid:{order_id}")]
    ])

    await call.message.edit_text(
        f"🏁 <b>Мекенжайға жеттіңіз!</b>\n\n"
        f"💳 Клиенттен жолақысын күтіңіз (Kaspi немесе қолма-қол).\n"
        f"Ақша түскенін растау үшін төмендегі батырманы басыңыз.",
        reply_markup=payment_kb,
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=client_id,
            text="📍 <b>Сіз мекенжайға жеттіңіз!</b>\n\n"
                 "🚕 Жүргізушіге жолақысын төлеуіңізді сұраймыз.\n"
                 "<i>(Төлем жасалған соң жүргізуші сапарды жүйеде жабады)</i>",
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.message(F.text == "👤 Клиент режиміне өту")
async def switch_to_client_mode(message: Message):
    user_id = message.from_user.id
    await change_user_mode(user_id, 'client')
    await message.answer(
        "👤 Сіз клиент режиміне өттіңіз! Жолға шығу үшін заказ бере аласыз.",
        reply_markup=get_client_menu_kb()
    )