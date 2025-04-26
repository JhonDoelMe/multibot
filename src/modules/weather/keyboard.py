# src/modules/weather/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Callback data префиксы для модуля погоды
WEATHER_PREFIX = "weather"
CALLBACK_WEATHER_BACK = f"{WEATHER_PREFIX}:back"
CALLBACK_WEATHER_REFRESH = f"{WEATHER_PREFIX}:refresh" # Пока не используется, но можно добавить

def get_weather_back_keyboard() -> InlineKeyboardMarkup:
    """Возвращает инлайн-клавиатуру с кнопкой 'Назад в меню'."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK)
        # Можно добавить кнопку Refresh сюда же
        # InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_WEATHER_REFRESH)
    )
    return builder.as_markup()