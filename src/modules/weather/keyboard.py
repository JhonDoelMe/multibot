# src/modules/weather/keyboard.py

from typing import Optional # Optional тут не використовується, але може знадобитися в майбутньому
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

WEATHER_PREFIX = "weather"
CALLBACK_WEATHER_OTHER_CITY = f"{WEATHER_PREFIX}:other"
CALLBACK_WEATHER_REFRESH = f"{WEATHER_PREFIX}:refresh"
CALLBACK_WEATHER_BACK_TO_MAIN = f"{WEATHER_PREFIX}:back_main"
CALLBACK_WEATHER_SAVE_CITY_YES = f"{WEATHER_PREFIX}:save_yes"
CALLBACK_WEATHER_SAVE_CITY_NO = f"{WEATHER_PREFIX}:save_no"

# Колбеки для прогнозу
CALLBACK_WEATHER_FORECAST_5D = f"{WEATHER_PREFIX}:forecast5"
CALLBACK_WEATHER_SHOW_CURRENT = f"{WEATHER_PREFIX}:show_current" # Повернення до поточної погоди з прогнозу
CALLBACK_WEATHER_FORECAST_TOMORROW = f"{WEATHER_PREFIX}:forecast_tomorrow" # Новий колбек для прогнозу на завтра


def get_save_city_keyboard() -> InlineKeyboardMarkup:
    """
    Клавіатура для підтвердження збереження міста.
    "Так, зберегти" / "Ні".
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💾 Так, зберегти", callback_data=CALLBACK_WEATHER_SAVE_CITY_YES),
        InlineKeyboardButton(text="❌ Ні", callback_data=CALLBACK_WEATHER_SAVE_CITY_NO)
    )
    # Можна додати кнопку "Назад до погоди" або "Скасувати", якщо потрібно
    return builder.as_markup()

def get_weather_actions_keyboard() -> InlineKeyboardMarkup:
    """ 
    Клавіатура з діями ПІСЛЯ показу поточної погоди:
    - Інше місто / Оновити
    - Прогноз на 5 днів / Прогноз на завтра
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏙️ Інше місто", callback_data=CALLBACK_WEATHER_OTHER_CITY),
        InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_WEATHER_REFRESH)
    )
    builder.row( 
        InlineKeyboardButton(text="📅 Прогноз на 5 днів", callback_data=CALLBACK_WEATHER_FORECAST_5D),
        InlineKeyboardButton(text="☀️ Прогноз на завтра", callback_data=CALLBACK_WEATHER_FORECAST_TOMORROW) # Нова кнопка
    )
    # Кнопку "Назад в головне меню" тут можна не додавати, 
    # оскільки користувач може використовувати reply-клавіатуру або команду /start.
    # Або, якщо це доцільно, додати її окремим рядком:
    # builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN))
    return builder.as_markup()

def get_weather_enter_city_back_keyboard() -> InlineKeyboardMarkup:
    """
    Клавіатура для стану введення міста:
    - Назад в меню (головне меню бота)
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN)
    )
    return builder.as_markup()

def get_forecast_keyboard() -> InlineKeyboardMarkup:
    """ 
    Клавіатура після показу прогнозу (5-денного або на завтра):
    - Назад до поточної погоди
    - (Опціонально) Назад в головне меню
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🌦️ До поточної погоди", callback_data=CALLBACK_WEATHER_SHOW_CURRENT)
    )
    # Якщо потрібно, можна додати кнопку повернення в головне меню налаштувань або бота
    # builder.row(InlineKeyboardButton(text="⚙️ До налаштувань", callback_data="settings:main")) # Приклад
    # builder.row(InlineKeyboardButton(text="⬅️ Головне меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN)) # Якщо з прогнозу можна вийти в головне меню
    return builder.as_markup()
