# src/keyboards/inline_main.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Определим callback_data для кнопок
# Префикс 'main' для главного меню, затем действие
CALLBACK_WEATHER = "main:weather"
CALLBACK_CURRENCY = "main:currency"
CALLBACK_ALERT = "main:alert"

def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Возвращает инлайн-клавиатуру главного меню."""
    builder = InlineKeyboardBuilder()

    builder.row(
        InlineKeyboardButton(text="🌦️ Погода", callback_data=CALLBACK_WEATHER)
    )
    builder.row(
        InlineKeyboardButton(text="💰 Курс валют", callback_data=CALLBACK_CURRENCY)
    )
    builder.row(
         # Используйте подходящую эмодзи для тревоги
        InlineKeyboardButton(text="🚨 Повітряна тривога", callback_data=CALLBACK_ALERT)
    )
    # Можно добавить кнопку "Назад" или другие опции сюда, если нужно

    return builder.as_markup()