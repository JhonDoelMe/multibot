# src/modules/alert/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

ALERT_PREFIX = "alert"
CALLBACK_ALERT_REFRESH = f"{ALERT_PREFIX}:refresh"
# Убираем старый CALLBACK_ALERT_BACK
# CALLBACK_ALERT_BACK = f"{ALERT_PREFIX}:back_to_main"

def get_alert_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура для статуса тревог: Только Обновить """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_ALERT_REFRESH)
    )
    # Убрали кнопку Назад
    # builder.row(
    #     InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_ALERT_BACK)
    # )
    return builder.as_markup()