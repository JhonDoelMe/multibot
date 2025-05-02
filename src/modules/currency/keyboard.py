# src/modules/currency/keyboard.py

from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

CURRENCY_PREFIX = "currency"
CALLBACK_CURRENCY_CASH = f"{CURRENCY_PREFIX}:cash"
CALLBACK_CURRENCY_NONCASH = f"{CURRENCY_PREFIX}:noncash"
# Убираем старый CALLBACK_CURRENCY_BACK, он больше не нужен в инлайн
# CALLBACK_CURRENCY_BACK = f"{CURRENCY_PREFIX}:back_to_main"

def get_currency_type_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура для выбора типа курса: Наличный / Безналичный """
    # Кнопку "Назад" убираем, т.к. есть ReplyKeyboard
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💵 Готівковий", callback_data=CALLBACK_CURRENCY_CASH),
        InlineKeyboardButton(text="💳 Безготівковий", callback_data=CALLBACK_CURRENCY_NONCASH)
    )
    # builder.row(
    #     InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_CURRENCY_BACK)
    # )
    return builder.as_markup()

# Эта клавиатура теперь не нужна, можно удалить функцию или возвращать None
def get_currency_back_keyboard() -> Optional[InlineKeyboardMarkup]:
    """ Клавиатура после показа курса (пустая). """
    return None
    # builder = InlineKeyboardBuilder()
    # builder.row(
    #     InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_CURRENCY_BACK)
    # )
    # return builder.as_markup()