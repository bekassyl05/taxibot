from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_start_kb():
    """Клиент немесе Таксист екенін таңдау батырмалары"""
    kb = [
        [KeyboardButton(text="🙋‍♂️ Мен клиентпін")],
        [KeyboardButton(text="🚕 Мен таксистпін")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Рөліңізді таңдаңыз..."
    )

def get_phone_kb():
    """Телефон нөмірін сұрау батырмасы (Қолмен жаздырмай, контактіні сұраймыз)"""
    kb = [
        [KeyboardButton(text="📱 Нөмірімді жіберу", request_contact=True)]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True
    )

def get_client_menu_kb():
    """Клиентке арналған басты мәзір клавиатурасы"""
    kb = [
        [KeyboardButton(text="🚕 Заказ беру")],
        [KeyboardButton(text="🚖 Жүргізуші режиміне өту")] # 🌟 МІНЕ, ОСЫ БАТЫРМА ҚОСЫЛДЫ!
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_driver_menu_kb():
    """Таксистке арналған басты мәзір"""
    kb = [
        [KeyboardButton(text="🚕 Линияға шығу")],
        [KeyboardButton(text="👤 Клиент режиміне өту")] # 🌟 ОСЫ БАТЫРМА ҚОСЫЛДЫ
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_address_kb():
    """Ауылдағы дайын мекенжайлар (клиент өз бетінше де жаза алады)"""
    kb = [
        [KeyboardButton(text="Үйден"), KeyboardButton(text="Орталықтан (Центр)")],
        [KeyboardButton(text="Мектептен"), KeyboardButton(text="Балабақшадан (Садик)")],
        [KeyboardButton(text="Ауруханадан (Больница)")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=kb,
        resize_keyboard=True,
        input_field_placeholder="Төменнен таңдаңыз немесе өзіңіз жазыңыз..." # Клиентке анық нұсқау
    )

def get_price_kb():
    """Дайын бағалар"""
    kb = [
        [KeyboardButton(text="500"), KeyboardButton(text="600"), KeyboardButton(text="700")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="Сумманы жазыңыз (тг)...")

def get_admin_menu_kb():
    """Бастықтың (Админнің) басқару мәзірі"""
    kb = [
        # 1-қатар: Таксистер мен Клиенттер базасын тексеру (Жаңа батырмалар)
        [KeyboardButton(text="🚕 Тексеру: Таксистер"), KeyboardButton(text="👥 Тексеру: Клиенттер")],
        # 2-қатар: Статистика және Заказдар
        [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="📝 Соңғы заказдар")],
        # 3-қатар: Хабарлама тарату
        [KeyboardButton(text="📢 Хабарлама тарату")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, input_field_placeholder="Бастық мәзірі...")