from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_sub_kb(driver_id: int):
    """Бастыққа таксистің PDF чегін растау батырмалары"""
    kb = [
        [
            InlineKeyboardButton(text="✅ Растау (7 күн)", callback_data=f"sub_approve:{driver_id}"),
            InlineKeyboardButton(text="❌ Бас тарту", callback_data=f"sub_reject:{driver_id}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def get_driver_order_kb(order_id: int, current_stage: str):
    """Таксистке заказдың әр қадамына арналған батырмалар"""
    kb = []
    if current_stage == "accepted":
        kb.append([InlineKeyboardButton(text="📍 Мекенжайға келдім", callback_data=f"order_arrived:{order_id}")])
    elif current_stage == "arrived":
        kb.append([InlineKeyboardButton(text="🚀 Кеттік (Адрес 2-ге)", callback_data=f"order_start:{order_id}")])
    elif current_stage == "started":
        kb.append([InlineKeyboardButton(text="🏁 Мекенжайға жеттік", callback_data=f"order_finish:{order_id}")])
    elif current_stage == "payment_pending":
        # Сұраныс бойынша ең маңызды батырма: Төлем расталмай, келесі қадамға өтпейді
        kb.append([InlineKeyboardButton(text="💰 Төлемді растау (Ақша түсті)", callback_data=f"order_paid:{order_id}")])

    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_broadcast_kb(order_id: int, current_price: int):
    """Таксистке заказ келгенде шығатын батырмалар"""
    kb = [
        [InlineKeyboardButton(text="✅ Осы бағаға қабылдау", callback_data=f"take_order:{order_id}:{current_price}")],
        [
            InlineKeyboardButton(text="+50 тг", callback_data=f"offer:{order_id}:{current_price + 50}"),
            InlineKeyboardButton(text="+100 тг", callback_data=f"offer:{order_id}:{current_price + 100}"),
            InlineKeyboardButton(text="+150 тг", callback_data=f"offer:{order_id}:{current_price + 150}")
        ]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_client_decision_kb(order_id: int, driver_id: int, offered_price: int):
    """Клиентке таксисттің жаңа бағасын растау немесе бас тарту батырмасы"""
    kb = [
        [InlineKeyboardButton(text=f"✅ Келісемін ({offered_price} тг)", callback_data=f"accept_offer:{order_id}:{driver_id}:{offered_price}")],
        [InlineKeyboardButton(text="❌ Бас тарту", callback_data=f"reject_offer:{order_id}:{driver_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)