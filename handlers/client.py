from aiogram import Router, F, types
from aiogram.filters import CommandStart, StateFilter
from aiogram.types import Message, ReplyKeyboardRemove, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State, any_state
from aiogram import Bot
from database.db import create_order, get_online_drivers, get_available_drivers, get_user, assign_order_to_driver, \
    get_driver, \
    get_order_details, cancel_order_by_client, save_order_rating, save_order_review, change_user_mode
from handlers.driver import DriverRegistration
from keyboards.reply import get_client_menu_kb, get_address_kb, get_price_kb, get_driver_menu_kb
from keyboards.inline import get_broadcast_kb

from database.db import get_user, register_user
from keyboards.reply import get_start_kb, get_phone_kb
from aiogram.exceptions import TelegramBadRequest

router = Router()


# Клиенттің тіркелу қадамдары (FSM)
class ClientReg(StatesGroup):
    entering_name = State()
    entering_phone = State()

class ClientFeedback(StatesGroup):
    waiting_for_review = State()

# 🌟 ТҮЗЕТІЛДІ: StateFilter(any_state) қосылды
@router.message(CommandStart(), StateFilter(any_state))
async def cmd_start(message: Message, state: FSMContext):
    """/start командасы - Пайдаланушыны тексеру немесе тіркеуді бастау"""
    await state.clear()  # Кез келген ескі күйлерді (state) тазалау

    user = await get_user(message.from_user.id)

    if user:
        role = user[2]  # Базадағы 'role' бағаны
        if role == 'client':
            await message.answer(
                f"Қайта қош келдіңіз, {user[1]}! (Клиент мәзірі)\nЗаказ беру үшін төмендегі батырмаларды қолданыңыз.",
                reply_markup=get_client_menu_kb()
            )
        elif role == 'driver':
            await message.answer(
                f"Қайта қош келдіңіз, {user[1]}! (Таксист мәзірі)\nЛинияға шығу үшін басқару панелін қолданыңыз.",
                reply_markup=get_driver_menu_kb()
            )
    else:
        # Жаңа қолданушы болса, рөл таңдауды ұсынамыз
        await message.answer(
            "Ауыл такси ботына қош келдіңіз! 🚕\nЖалғастыру үшін рөліңізді таңдаңыз:",
            reply_markup=get_start_kb()
        )


@router.message(F.text == "🙋‍♂️ Мен клиентпін")
async def start_client_reg(message: Message, state: FSMContext):
    """Клиент ретінде тіркелуді бастау"""
    await message.answer("Тіркелу үшін Аты-жөніңізді енгізіңіз (Мысалы: Арман Ахметов):",
                         reply_markup=ReplyKeyboardRemove())
    await state.set_state(ClientReg.entering_name)


@router.message(ClientReg.entering_name)
async def process_client_name(message: Message, state: FSMContext):
    """Атын қабылдау және телефон сұрау"""
    await state.update_data(full_name=message.text)
    await message.answer(
        "Енді төмендегі батырманы басу арқылы телефон нөміріңізді жіберіңіз:",
        reply_markup=get_phone_kb()
    )
    await state.set_state(ClientReg.entering_phone)


@router.message(ClientReg.entering_phone, F.contact)
async def process_client_phone_contact(message: Message, state: FSMContext):
    """Телефон нөмірін батырма арқылы қабылдау және базаға сақтау"""
    data = await state.get_data()
    phone = message.contact.phone_number
    # Базаға сақтау
    await register_user(message.from_user.id, data['full_name'], phone, 'client')

    await message.answer(
        f"Тіркелу сәтті аяқталды! 🎉\n"
        f"Қош келдіңіз, {message.from_user.full_name}.\n"
        f"Енді төмендегі батырманы басып, таксиге заказ бере аласыз 👇",
        reply_markup=get_client_menu_kb()
    )
    await state.clear()


class OrderFSM(StatesGroup):
    route_type = State()
    intercity_dir = State()
    from_addr = State()
    to_addr = State()
    price = State()

def get_route_type_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏘 Ауыл ішінде")],
            [KeyboardButton(text="🏙 Атырау ↔ Алмалы")]
        ], resize_keyboard=True
    )

def get_intercity_dir_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🏙 Атырау ➡ 🏘 Алмалы")],
            [KeyboardButton(text="🏘 Алмалы ➡ 🏙 Атырау")]
        ], resize_keyboard=True
    )

def get_intercity_price_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="1500"), KeyboardButton(text="1700")],
            [KeyboardButton(text="2000"), KeyboardButton(text="2500")]
        ], resize_keyboard=True
    )


# 1. РЕЖИМ АУЫСТЫРУ ХЭНДЛЕРІ
@router.message(F.text == "🚖 Жүргізуші режиміне өту")
async def switch_to_driver_mode(message: Message, state: FSMContext):
    user_id = message.from_user.id
    user = await get_user(user_id)

    if not user:
        return await message.answer("Кешіріңіз, сіз базада жоқсыз. /start басыңыз.")

    # user = (id, full_name, phone, is_client, is_driver, current_mode, reg_date)
    is_driver = user[4]

    if is_driver == 1:
        # Егер ол бұрын таксист болып тіркелсе, жай ғана режимін ауыстырамыз
        await change_user_mode(user_id, 'driver')
        await message.answer(
            "🚖 Жүргізуші режиміне өттіңіз! Заказдар күтілуде...",
            reply_markup=get_driver_menu_kb()  # Таксист клавиатурасы
        )
    else:
        # ЕГЕР ТІРКЕЛМЕГЕН БОЛСА:
        # 1. Аты мен телефонын қайта сұрамас үшін базадан алып, State-ке сақтай саламыз
        await state.update_data(driver_name=user[1], driver_phone=user[2])

        # 2. Машина маркасын сұраймыз (мәзірді уақытша жасырамыз)
        await message.answer(
            "🚕 Сіз таксист ретінде тіркелмегенсіз.\n"
            "Тіркелу үшін көлігіңіздің маркасын жазыңыз (мысалы, Toyota Camry):",
            reply_markup=ReplyKeyboardRemove()
        )

        # 3. Көлік сұрайтын State-ке өткіземіз
        # (Өзіңізде бұл қадам қалай аталады, соны жазыңыз, мысалы waiting_for_car)
        await state.set_state(DriverRegistration.waiting_for_car)

@router.message(F.text == "🚕 Заказ беру")
async def start_order(message: Message, state: FSMContext):
    await message.answer("Қай бағытта жүресіз?", reply_markup=get_route_type_kb())
    await state.set_state(OrderFSM.route_type)


@router.message(OrderFSM.route_type)
async def process_route_type(message: Message, state: FSMContext):
    if message.text == "🏙 Атырау ↔ Алмалы":
        # Қала аралық болса, order_type сақтап, нақты бағытты сұраймыз
        await state.update_data(order_type="intercity")
        await message.answer("Бағытты таңдаңыз:", reply_markup=get_intercity_dir_kb())
        await state.set_state(OrderFSM.intercity_dir)
    else:
        # Ауыл ішінде болса, баяғыша алып кету орнын сұраймыз
        await state.update_data(order_type="local")
        await message.answer("Қай жерден алып кету керек?", reply_markup=get_address_kb())
        await state.set_state(OrderFSM.from_addr)


@router.message(OrderFSM.intercity_dir)
async def process_intercity_dir(message: Message, state: FSMContext):
    # Қала-Ауыл бағытын сақтап аламыз (мысалы: "Атырау -> Алмалы")
    await state.update_data(direction=message.text)
    await message.answer(
        f"Сіз <b>{message.text}</b> бағытын таңдадыңыз.\n"
        "Нақты қай жерден алып кету керек? (Мысалы: Авангард, Әсем кафесінің жаны):",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="HTML"
    )
    await state.set_state(OrderFSM.from_addr)


@router.message(OrderFSM.from_addr)
async def process_from_addr(message: Message, state: FSMContext):
    await state.update_data(from_addr=message.text)
    user_data = await state.get_data()

    # Егер қала аралық болса, басқаша мәтін шығарамыз
    if user_data.get("order_type") == "intercity":
        await message.answer("Нақты қай жерге барасыз? (Мысалы: Мектептің қасына):")
    else:
        await message.answer("Қай жерге барасыз?", reply_markup=get_address_kb())

    await state.set_state(OrderFSM.to_addr)


@router.message(OrderFSM.to_addr)
async def process_to_addr(message: Message, state: FSMContext):
    await state.update_data(to_addr=message.text)
    user_data = await state.get_data()

    if user_data.get("order_type") == "intercity":
        await message.answer(
            "Қала мен ауыл арасына базалық баға: <b>1500 тг</b>.\n"
            "Такси тез табылуы үшін бағаны таңдаңыз немесе өз бағаңызды жазыңыз:",
            reply_markup=get_intercity_price_kb(),
            parse_mode="HTML"
        )
    else:
        await message.answer("Қанша төлейсіз? Бағаңызды жазыңыз немесе таңдаңыз:", reply_markup=get_price_kb())

    await state.set_state(OrderFSM.price)


from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


@router.message(OrderFSM.price)
async def process_price(message: Message, state: FSMContext, bot: Bot):
    # Тек сандарды сүзіп алу
    price_text = ''.join(filter(str.isdigit, message.text))
    if not price_text:
        await message.answer("⚠️ Қате! Бағаны тек сандармен жазыңыз (мысалы: 500).")
        return

    price = int(price_text)
    data = await state.get_data()

    # 🌟 ЖАҢА: Бағыт түрін алу (егер табылмаса, әдепкі бойынша 'local' болады)
    order_type = data.get("order_type", "local")

    # 🌟 ЖАҢА: МИНИМАЛДЫ БАҒАНЫ БАҒЫТҚА ҚАРАЙ ТЕКСЕРУ
    min_price = 1500 if order_type == "intercity" else 300

    if price < min_price:
        route_name = "Атырау ↔ Алмалы бағыты" if order_type == "intercity" else "Ауыл іші"
        await message.answer(
            f"❌ <b>Тапсырыс қабылданбады!</b>\n\n"
            f"⚠️ {route_name} үшін ең төменгі тапсырыс бағасы — <b>{min_price} тг</b>.\n"
            f"Кемінде {min_price} тг немесе одан жоғары сома енгізіңіз 👇:",
            parse_mode="HTML"
        )
        return

    client_id = message.from_user.id

    # 1. Базадан клиенттің аты-жөні мен телефонын алдын ала аламыз
    user_info = await get_user(client_id)
    if not user_info:
        await message.answer("Қате! Пайдаланушы базадан табылмады. Қайта тіркеліңіз /start")
        return

    client_name = user_info[1]
    client_phone = user_info[2]

    available_drivers = await get_available_drivers()
    drivers_count = len(available_drivers)

    # 2. Заказды базаға тіркеу (🌟 order_type параметрі қосылды)
    order_id = await create_order(client_id, data['from_addr'], data['to_addr'], price, order_type)

    # Тапсырысты жою батырмасы
    client_cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Тапсырысты жою (Отмена)", callback_data=f"cancel_my_order:{order_id}")]
    ])

    if drivers_count > 0:
        client_msg = (
            f"✅ <b>Тапсырыс №{order_id} сәтті қабылданды!</b>\n\n"
            f"🚕 Қазір линияда <b>{drivers_count} бос жүргізуші</b> бар.\n"
            f"Оларға хабарлама жіберілді, жауап күтіңіз... ⏳"
        )
    else:
        client_msg = (
            f"⚠️ <b>Тапсырыс №{order_id} жүйеге енгізілді.</b>\n\n"
            f"🛑 Бірақ дәл қазір линияда <b>бос жүргізушілер жоқ</b>.\n"
            f"Жүргізушілер босаған бойда тапсырысыңызды көре алады."
        )

    await message.answer(client_msg, reply_markup=client_cancel_kb, parse_mode="HTML")
    await message.answer("Қосымша әрекеттер үшін төмендегі мәзірді қолданыңыз 👇", reply_markup=get_client_menu_kb())
    await state.clear()

    # 🌟 ЖАҢА: Таксистерге баратын хабарламада бағытты анық көрсету
    route_label = "🏙 ҚАЛА АРАЛЫҚ (Атырау ↔ Алмалы)" if order_type == "intercity" else "🏘 АУЫЛ ІШІНДЕДЕГІ ТАПСЫРЫС"

    # 3. Бос таксистерге жіберілетін толық хабарлама мәтіні
    order_text = (
        f"🚨 <b>ЖАҢА ТАПСЫРЫС (№{order_id})</b>\n"
        f"🛣 <b>Бағыт:</b> {route_label}\n\n"
        f"📍 Қайдан: <b>{data['from_addr']}</b>\n"
        f"🏁 Қайда: <b>{data['to_addr']}</b>\n"
        f"💰 Бағасы: <b>{price} тг</b>\n\n"
        f"👤 Клиент: <b>{client_name}</b>\n"
        f"📱 Тел: <code>{client_phone}</code>\n\n"
        f"👇 <i>Заказды алғыңыз келсе, батырманы басыңыз:</i>"
    )

    # 4. Тек БОС таксистерге тарату
    for driver_id in available_drivers:
        try:
            await bot.send_message(
                chat_id=driver_id,
                text=order_text,
                reply_markup=get_broadcast_kb(order_id, price),
                parse_mode="HTML"
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("accept_offer:"))
async def process_accept_offer(call: CallbackQuery, bot: Bot):
    """Клиент таксист ұсынған жаңа бағаны қабылдағанда"""
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])
    driver_id = int(data_parts[2])
    offered_price = int(data_parts[3])

    await call.answer()

    # 1. Базада тапсырысты жаңарту
    await assign_order_to_driver(order_id, driver_id, offered_price)

    # 2. Базадан тапсырыстың толық мәліметін (адрестері мен клиентті) аламыз
    order_info = await get_order_details(order_id)

    if order_info:
        from_addr = order_info[0]  # Қайдан (0-индекс)
        to_addr = order_info[1]  # Қайда (1-индекс)
        client_name = order_info[3]  # Клиенттің аты-жөні (3-индекс)
        client_phone = order_info[4]  # Клиенттің телефоны (4-индекс)
        client_id = order_info[5]  # Клиенттің Telegram ID-і (5-индекс)
    else:
        from_addr, to_addr, client_name, client_phone, client_id = "Белгісіз", "Белгісіз", "Белгісіз", "Белгісіз", None

    # 3. Таксисттің көлік мәліметтерін алу
    driver_info = await get_driver(driver_id)
    car_model = driver_info[1] if driver_info else "Анықталмады"
    car_number = driver_info[2] if driver_info else "Анықталмады"

    # 4. Таксистің жеке мәліметтерін (аты мен телефонын) алу
    driver_user_info = await get_user(driver_id)
    driver_name = driver_user_info[1] if driver_user_info else "Анықталмады"
    driver_phone = driver_user_info[2] if driver_user_info else "Анықталмады"

    # Клиент экранын жаңарту
    await call.message.edit_text(
        f"✅ Сіз <b>{offered_price} тг</b> бағасын қабылдадыңыз!\n\n"
        f"👤 Жүргізуші: <b>{driver_name}</b>\n"
        f"📱 Тел: <code>{driver_phone}</code>\n"
        f"🚕 Көлік: <b>{car_model}</b>\n"
        f"🔢 Нөмірі: <code>{car_number}</code>\n\n"
        f"Жүргізуші сізге қарай жолға шықты. Күтіңіз!",
        parse_mode="HTML"
    )

    # 5. Таксистке "Мекенжайға келдім" батырмасын жіберу
    # (Алдыңғы жөндегенімізбен сәйкес келуі үшін 'order_arrived' деп түзетілді)
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    driver_action_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📍 Мекенжайға келдім", callback_data=f"order_arrived:{order_id}")]
    ])

    # 🌟 ЖАҢАЛЫҚ: Таксистке баратын мәтін дұрыс форматқа келтірілді
    try:
        await bot.send_message(
            chat_id=driver_id,
            text=f"🎉 <b>Тапсырыс №{order_id} бекітілді!</b>\n\n"
                 f"Клиент сіз ұсынған <b>{offered_price} тг</b> бағаға келісті.\n\n"
                 f"👤 Клиент: <b>{client_name}</b>\n"
                 f"📱 Тел. нөмірі: <code>{client_phone}</code>\n"
                 f"📍 Қайдан: <b>{from_addr}</b>\n"
                 f"🏁 Қайда: <b>{to_addr}</b>\n\n"
                 f"🚀 <b>{from_addr}</b> мекенжайына қарай қозғала беріңіз.",
            reply_markup=driver_action_kb,
            parse_mode="HTML"
        )
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject_offer:"))
async def process_reject_offer(call: CallbackQuery, bot: Bot):
    """Клиент таксистің бағасынан бас тартқанда"""
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])
    driver_id = int(data_parts[2])

    await call.answer("Бағадан бас тартылды")

    # 1. Клиенттің экранындағы мәтінді жаңартамыз (әдемі көрінуі үшін HTML қостық)
    await call.message.edit_text(
        "❌ <b>Сіз таксистің бұл баға ұсынысынан бас тарттыңыз.</b>\n"
        "Басқа жүргізушілерден ұсыныс күтілуде... ⏳",
        parse_mode="HTML"
    )

    # 2. Базадан тапсырыстың БАСТАПҚЫ мәліметтерін (адрестері мен бағасын) аламыз
    order_info = await get_order_details(order_id)

    if order_info:
        from_addr = order_info[0]
        to_addr = order_info[1]
        original_price = order_info[2]  # Клиенттің ең басында қойған бағасы (мысалы: 500)
        client_name = order_info[3]

        # 3. Таксистке "Клиент көнбеді, бірақ бастапқы бағамен ала аласыз" деп хабарлама дайындаймыз
        driver_msg = (
            f"😔 <b>Тапсырыс №{order_id}:</b> Клиент сіз ұсынған бағаға келіспеді.\n\n"
            f"👇 Бірақ бұл тапсырыс әлі де ашық. Оны <b>бастапқы бағасымен</b> қабылдағыңыз келсе, төменді басыңыз:\n\n"
            f"📍 Қайдан: <b>{from_addr}</b>\n"
            f"🏁 Қайда: <b>{to_addr}</b>\n"
            f"💰 Бағасы: <b>{original_price} тг</b>\n\n"
            f"👤 Клиент: <b>{client_name}</b>"
        )

        # 4. Таксистке хабарлама мен батырмаларды қайта жібереміз
        try:
            await bot.send_message(
                chat_id=driver_id,
                text=driver_msg,
                reply_markup=get_broadcast_kb(order_id, original_price),  # Бастапқы бағамен батырмаларды қайтарамыз
                parse_mode="HTML"
            )
        except Exception:
            pass

@router.callback_query(F.data.startswith("cancel_my_order:"))
async def process_client_cancel_order(call: CallbackQuery):
    """Клиент өз тапсырысынан бас тартқанда"""
    data_parts = call.data.split(":")
    order_id = int(data_parts[1])

    # Базада тексеріп, жоюға тырысамыз
    success = await cancel_order_by_client(order_id)

    if success:
        await call.answer("Тапсырыс жойылды!", show_alert=True)
        await call.message.edit_text(
            f"❌ <b>Тапсырыс №{order_id} сіз тарапыңыздан жойылды (БАС ТАРТЫЛДЫ).</b>\n\n"
            f"Қайтадан такси шақыру үшін мәзірді қолданыңыз.",
            parse_mode="HTML"
        )
    else:
        # Егер статус 'waiting' болмаса (яғни таксист алып қойса)
        await call.answer(
            "⚠️ Тапсырысты жою мүмкін емес!\n"
            "Жүргізуші тапсырысыңызды қабылдап қойды немесе бұл тапсырыс ескірген.",
            show_alert=True
        )

@router.callback_query(F.data.startswith("rate_driver:"))
async def process_driver_rating(call: CallbackQuery, state: FSMContext):
    """Клиент жұлдызды басқан кезде"""
    _, order_id, rating = call.data.split(":")
    order_id = int(order_id)
    rating = int(rating)

    # 1. Жұлдызды базаға сақтаймыз
    await save_order_rating(order_id, rating)

    # 2. Пікір сұраймыз немесе өткізіп жіберу батырмасын береміз
    skip_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➡️ Өткізіп жіберу", callback_data=f"skip_review:{order_id}")]
    ])

    await call.message.edit_text(
        f"Сіз жүргізушіге <b>{rating} ⭐️</b> қойдыңыз. Рақмет!\n\n"
        f"Қаласаңыз, қысқаша пікір жазып жіберіңіз немесе «Өткізіп жіберу» батырмасын басыңыз:",
        reply_markup=skip_kb,
        parse_mode="HTML"
    )

    # Күйге өтеміз және order_id сақтаймыз
    await state.update_data(rating_order_id=order_id)
    await state.set_state(ClientFeedback.waiting_for_review)


@router.callback_query(F.data.startswith("skip_review:"))
async def process_skip_review(call: CallbackQuery, state: FSMContext):
    """Клиент пікір жазуды өткізіп жібергенде"""
    await call.message.edit_text("Пікір жазу өткізілді. Қызметімізді пайдаланғаныңыз үшін рақмет! 👋")
    await state.clear()


@router.message(ClientFeedback.waiting_for_review)
async def process_review_text(message: Message, state: FSMContext):
    """Клиент пікір (мәтін) жазып жібергенде"""
    data = await state.get_data()
    order_id = data.get("rating_order_id")

    if order_id:
        # 3. Пікірді базаға сақтаймыз
        await save_order_review(order_id, message.text)

    await message.answer("📝 Пікіріңіз сәтті қабылданды! Үлкен рақмет, келесі сапарларда кездескенше! 👋")
    await state.clear()