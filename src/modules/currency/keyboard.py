# src/modules/currency/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Callback data префиксы и константы
CURRENCY_PREFIX = "currency"
CALLBACK_CURRENCY_CASH = f"{CURRENCY_PREFIX}:cash"
CALLBACK_CURRENCY_NONCASH = f"{CURRENCY_PREFIX}:noncash"
CALLBACK_CURRENCY_BACK = f"{CURRENCY_PREFIX}:back_to_main" # Уникальный callback для возврата

def get_currency_type_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура для выбора типа курса: Наличный / Безналичный / Назад """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💵 Готівковий", callback_data=CALLBACK_CURRENCY_CASH),
        InlineKeyboardButton(text="💳 Безготівковий", callback_data=CALLBACK_CURRENCY_NONCASH)
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_CURRENCY_BACK)
    )
    return builder.as_markup()

def get_currency_back_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура с одной кнопкой 'Назад' для возврата к выбору типа курса или в меню """
    # Пока сделаем универсальную "Назад в меню"
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_CURRENCY_BACK)
        # Если захотим возврат к выбору типа:
        # InlineKeyboardButton(text="⬅️ До вибору курсу", callback_data=CALLBACK_CURRENCY_BACK_TO_TYPE)
    )
    return builder.as_markup()