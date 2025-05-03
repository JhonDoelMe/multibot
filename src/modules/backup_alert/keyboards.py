# src/modules/alert_backup/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

ALERT_BACKUP_PREFIX = "alertbk" # Отличается от основного
CALLBACK_ALERT_BACKUP_REFRESH = f"{ALERT_BACKUP_PREFIX}:refresh"

def get_alert_backup_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура для резервного статуса тревог: Только Обновить """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити (резерв)", callback_data=CALLBACK_ALERT_BACKUP_REFRESH)
    )
    return builder.as_markup()