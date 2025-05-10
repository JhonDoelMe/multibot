# src/modules/settings/keyboard.py

from typing import Optional # <<< ИСПРАВЛЕНИЕ: Добавлен импорт Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Импортируем ServiceChoice для использования в данных колбэка
from src.db.models import ServiceChoice 

SETTINGS_PREFIX = "settings"

# Колбэки для главного меню настроек
CB_SETTINGS_WEATHER = f"{SETTINGS_PREFIX}:select_weather"
CB_SETTINGS_ALERTS = f"{SETTINGS_PREFIX}:select_alerts"
CB_SETTINGS_BACK_TO_MAIN_MENU = f"{SETTINGS_PREFIX}:back_main_menu" # Для возврата в главное меню бота

# Колбэки для выбора сервиса погоды
# Формат: settings:set_weather:[service_code]
CB_SET_WEATHER_SERVICE_PREFIX = f"{SETTINGS_PREFIX}:set_weather" 
CB_SET_WEATHER_OWM = f"{CB_SET_WEATHER_SERVICE_PREFIX}:{ServiceChoice.OPENWEATHERMAP}"
CB_SET_WEATHER_WAPI = f"{CB_SET_WEATHER_SERVICE_PREFIX}:{ServiceChoice.WEATHERAPI}"

# Колбэки для выбора сервиса тревог
# Формат: settings:set_alerts:[service_code]
CB_SET_ALERTS_SERVICE_PREFIX = f"{SETTINGS_PREFIX}:set_alerts"
CB_SET_ALERTS_UALARM = f"{CB_SET_ALERTS_SERVICE_PREFIX}:{ServiceChoice.UKRAINEALARM}"
CB_SET_ALERTS_AINUA = f"{CB_SET_ALERTS_SERVICE_PREFIX}:{ServiceChoice.ALERTSINUA}"

# Колбэк для возврата из меню выбора сервиса в главное меню настроек
CB_BACK_TO_SETTINGS_MENU = f"{SETTINGS_PREFIX}:back_to_settings"


def get_main_settings_keyboard(current_weather_service: Optional[str], current_alert_service: Optional[str]) -> InlineKeyboardMarkup:
    """
    Генерирует главную клавиатуру настроек.
    Показывает текущие выбранные сервисы.
    """
    builder = InlineKeyboardBuilder()

    weather_service_name = "Не обрано"
    if current_weather_service == ServiceChoice.OPENWEATHERMAP:
        weather_service_name = "OpenWeatherMap (осн.)"
    elif current_weather_service == ServiceChoice.WEATHERAPI:
        weather_service_name = "WeatherAPI.com (резерв.)"
    
    alert_service_name = "Не обрано"
    if current_alert_service == ServiceChoice.UKRAINEALARM:
        alert_service_name = "UkraineAlarm (осн.)"
    elif current_alert_service == ServiceChoice.ALERTSINUA:
        alert_service_name = "Alerts.in.ua (резерв.)"

    builder.button(
        text=f"🌦️ Сервіс погоди ({weather_service_name})", 
        callback_data=CB_SETTINGS_WEATHER
    )
    builder.button(
        text=f"🚨 Сервіс тривог ({alert_service_name})",
        callback_data=CB_SETTINGS_ALERTS
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад в головне меню", callback_data=CB_SETTINGS_BACK_TO_MAIN_MENU))
    builder.adjust(1) # Каждая кнопка выбора сервиса на новой строке
    return builder.as_markup()


def get_weather_service_selection_keyboard(selected_service: Optional[str]) -> InlineKeyboardMarkup:
    """ Клавиатура для выбора сервиса погоды. """
    builder = InlineKeyboardBuilder()
    
    owm_text = "OpenWeatherMap (осн.)"
    wapi_text = "WeatherAPI.com (резерв.)"

    if selected_service == ServiceChoice.OPENWEATHERMAP:
        owm_text = f"✅ {owm_text}"
    elif selected_service == ServiceChoice.WEATHERAPI:
        wapi_text = f"✅ {wapi_text}"

    builder.button(text=owm_text, callback_data=CB_SET_WEATHER_OWM)
    builder.button(text=wapi_text, callback_data=CB_SET_WEATHER_WAPI)
    builder.row(InlineKeyboardButton(text="⬅️ Назад до налаштувань", callback_data=CB_BACK_TO_SETTINGS_MENU))
    builder.adjust(1)
    return builder.as_markup()


def get_alert_service_selection_keyboard(selected_service: Optional[str]) -> InlineKeyboardMarkup:
    """ Клавиатура для выбора сервиса оповещений о тревогах. """
    builder = InlineKeyboardBuilder()

    ualarm_text = "UkraineAlarm (осн.)"
    ainua_text = "Alerts.in.ua (резерв.)"

    if selected_service == ServiceChoice.UKRAINEALARM:
        ualarm_text = f"✅ {ualarm_text}"
    elif selected_service == ServiceChoice.ALERTSINUA:
        ainua_text = f"✅ {ainua_text}"

    builder.button(text=ualarm_text, callback_data=CB_SET_ALERTS_UALARM)
    builder.button(text=ainua_text, callback_data=CB_SET_ALERTS_AINUA)
    builder.row(InlineKeyboardButton(text="⬅️ Назад до налаштувань", callback_data=CB_BACK_TO_SETTINGS_MENU))
    builder.adjust(1)
    return builder.as_markup()