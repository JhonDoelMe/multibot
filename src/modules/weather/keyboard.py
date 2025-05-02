# src/modules/weather/keyboard.py

from typing import Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEATHER_PREFIX = "weather"
CALLBACK_WEATHER_OTHER_CITY = f"{WEATHER_PREFIX}:other"
CALLBACK_WEATHER_REFRESH = f"{WEATHER_PREFIX}:refresh"
CALLBACK_WEATHER_BACK_TO_MAIN = f"{WEATHER_PREFIX}:back_main"
CALLBACK_WEATHER_SAVE_CITY_YES = f"{WEATHER_PREFIX}:save_yes"
CALLBACK_WEATHER_SAVE_CITY_NO = f"{WEATHER_PREFIX}:save_no"
# --- Новые колбэки для прогноза ---
CALLBACK_WEATHER_FORECAST_5D = f"{WEATHER_PREFIX}:forecast5"
CALLBACK_WEATHER_SHOW_CURRENT = f"{WEATHER_PREFIX}:show_current"


def get_save_city_keyboard() -> InlineKeyboardMarkup:
    # ... (без изменений) ...
     builder = InlineKeyboardBuilder(); builder.row(InlineKeyboardButton(text="💾 Так, зберегти", callback_data=CALLBACK_WEATHER_SAVE_CITY_YES), InlineKeyboardButton(text="❌ Ні", callback_data=CALLBACK_WEATHER_SAVE_CITY_NO)); return builder.as_markup()

def get_weather_actions_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура с действиями ПОСЛЕ показа погоды: Другой город / Обновить / Прогноз 5д """
    builder = InlineKeyboardBuilder()
    # Добавляем кнопку прогноза в первый ряд
    builder.row(
        InlineKeyboardButton(text="🏙️ Інше місто", callback_data=CALLBACK_WEATHER_OTHER_CITY),
        InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_WEATHER_REFRESH)
    )
    # Кнопка прогноза во втором ряду
    builder.row(
         InlineKeyboardButton(text="📅 Прогноз на 5 днів", callback_data=CALLBACK_WEATHER_FORECAST_5D)
    )
    return builder.as_markup()

def get_weather_enter_city_back_keyboard() -> InlineKeyboardMarkup:
    # ... (без изменений) ...
     builder = InlineKeyboardBuilder(); builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN)); return builder.as_markup()

# --- Новая клавиатура для прогноза ---
def get_forecast_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура после показа прогноза: Назад к текущей погоде """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ До поточної погоди", callback_data=CALLBACK_WEATHER_SHOW_CURRENT)
    )
    # Можно добавить кнопку "Назад в меню", если нужно
    # builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN))
    return builder.as_markup()