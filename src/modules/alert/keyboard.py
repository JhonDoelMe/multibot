# src/modules/alert/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Callback data префиксы и константы
ALERT_PREFIX = "alert"
CALLBACK_ALERT_REFRESH = f"{ALERT_PREFIX}:refresh"
CALLBACK_ALERT_BACK = f"{ALERT_PREFIX}:back_to_main" # Уникальный callback

def get_alert_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура для статуса тревог: Обновить / Назад """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_ALERT_REFRESH)
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_ALERT_BACK)
    )
    return builder.as_markup()