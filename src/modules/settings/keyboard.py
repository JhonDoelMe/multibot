# src/modules/settings/keyboard.py

from typing import Optional
from datetime import time as dt_time # Для анотації типів часу

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Імпортуємо ServiceChoice для використання в даних колбека
from src.db.models import ServiceChoice 

SETTINGS_PREFIX = "settings"

# Колбеки для головного меню налаштувань
CB_SETTINGS_WEATHER = f"{SETTINGS_PREFIX}:select_weather"
CB_SETTINGS_ALERTS = f"{SETTINGS_PREFIX}:select_alerts"
CB_SETTINGS_BACK_TO_MAIN_MENU = f"{SETTINGS_PREFIX}:back_main_menu"

# Нові колбеки для налаштувань нагадувань про погоду
CB_SETTINGS_WEATHER_REMINDER = f"{SETTINGS_PREFIX}:weather_reminder_menu" # Перехід в меню нагадувань
CB_WEATHER_REMINDER_TOGGLE = f"{SETTINGS_PREFIX}:wr_toggle" # Увімкнути/вимкнути
CB_WEATHER_REMINDER_SET_TIME = f"{SETTINGS_PREFIX}:wr_set_time_menu" # Перехід в меню вибору часу
# Колбек-префікс для кнопок вибору конкретного часу
CB_WEATHER_REMINDER_TIME_SELECT_PREFIX = f"{SETTINGS_PREFIX}:wr_time_sel:" # наприклад, settings:wr_time_sel:07:00

# Колбеки для вибору сервісу погоди
CB_SET_WEATHER_SERVICE_PREFIX = f"{SETTINGS_PREFIX}:set_weather" 
CB_SET_WEATHER_OWM = f"{CB_SET_WEATHER_SERVICE_PREFIX}:{ServiceChoice.OPENWEATHERMAP}"
CB_SET_WEATHER_WAPI = f"{CB_SET_WEATHER_SERVICE_PREFIX}:{ServiceChoice.WEATHERAPI}"

# Колбеки для вибору сервісу тривог
CB_SET_ALERTS_SERVICE_PREFIX = f"{SETTINGS_PREFIX}:set_alerts"
CB_SET_ALERTS_UALARM = f"{CB_SET_ALERTS_SERVICE_PREFIX}:{ServiceChoice.UKRAINEALARM}"
CB_SET_ALERTS_AINUA = f"{CB_SET_ALERTS_SERVICE_PREFIX}:{ServiceChoice.ALERTSINUA}"

# Колбек для повернення з меню вибору сервісу/нагадувань в головне меню налаштувань
CB_BACK_TO_SETTINGS_MENU = f"{SETTINGS_PREFIX}:back_to_settings"


def get_main_settings_keyboard(
    current_weather_service: Optional[str],
    current_alert_service: Optional[str],
    weather_reminder_enabled: bool, # Новий параметр
    weather_reminder_time: Optional[dt_time] # Новий параметр (використовуємо dt_time з datetime)
) -> InlineKeyboardMarkup:
    """
    Генерирует главную клавиатуру настроек.
    Показывает текущие выбранные сервисы и статус нагадувань про погоду.
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

    # Формування тексту для кнопки нагадувань
    reminder_status_display = "Увімк." if weather_reminder_enabled else "Вимк."
    reminder_time_display = ""
    if weather_reminder_enabled:
        reminder_time_display = weather_reminder_time.strftime('%H:%M') if weather_reminder_time else "07:00 (за замовч.)"
    else:
        reminder_time_display = "не активне"
        
    builder.button(
        text=f"⏰ Нагадування ({reminder_status_display}, {reminder_time_display})", # Скорочено текст
        callback_data=CB_SETTINGS_WEATHER_REMINDER
    )
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад в головне меню", callback_data=CB_SETTINGS_BACK_TO_MAIN_MENU))
    builder.adjust(1) # Кожна кнопка налаштування на новому рядку
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

# --- Нові клавіатури для налаштувань нагадувань про погоду ---

def get_weather_reminder_settings_keyboard(
    reminder_enabled: bool,
    reminder_time: Optional[dt_time] # Використовуємо dt_time
) -> InlineKeyboardMarkup:
    """
    Клавіатура для налаштування нагадувань про погоду:
    - Увімкнути/Вимкнути
    - Встановити час
    - Назад
    """
    builder = InlineKeyboardBuilder()
    
    toggle_text = "🟢 Вимкнути нагадування" if reminder_enabled else "🔴 Увімкнути нагадування"
    builder.button(text=toggle_text, callback_data=CB_WEATHER_REMINDER_TOGGLE)

    current_time_display = "не встановлено"
    if reminder_enabled:
        current_time_display = reminder_time.strftime('%H:%M') if reminder_time else "07:00 (за замовч.)"
    
    set_time_button_text = f"🕒 Встановити час (зараз: {current_time_display})"
    if not reminder_enabled:
        set_time_button_text = "🕒 Встановити час (нагадування вимкнені)"

    builder.button(
        text=set_time_button_text, 
        callback_data=CB_WEATHER_REMINDER_SET_TIME
    )
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад до налаштувань", callback_data=CB_BACK_TO_SETTINGS_MENU))
    builder.adjust(1) # Кожна кнопка на новому рядку
    return builder.as_markup()

def get_weather_reminder_time_selection_keyboard(
    current_selected_time_obj: Optional[dt_time] # Приймає об'єкт time або None
) -> InlineKeyboardMarkup:
    """
    Клавіатура для вибору часу нагадування.
    Показує галочку біля поточного обраного часу.
    """
    builder = InlineKeyboardBuilder()
    # Пропоновані варіанти часу (можна винести в константи)
    suggested_times_str = ["06:00", "07:00", "08:00", "09:00", "12:00", "18:00", "20:00", "21:00"]
    
    current_selected_time_str = current_selected_time_obj.strftime('%H:%M') if current_selected_time_obj else None

    buttons_in_row = []
    for time_str_option in suggested_times_str:
        button_text = time_str_option
        if time_str_option == current_selected_time_str:
            button_text = f"✅ {time_str_option}"
        
        buttons_in_row.append(InlineKeyboardButton(
            text=button_text,
            callback_data=f"{CB_WEATHER_REMINDER_TIME_SELECT_PREFIX}{time_str_option}"
        ))
        
        if len(buttons_in_row) == 3: # Розміщуємо по 3 кнопки в ряд
            builder.row(*buttons_in_row)
            buttons_in_row = []
            
    if buttons_in_row: # Додаємо залишок кнопок, якщо вони є
        builder.row(*buttons_in_row)
        
    # Можна додати кнопку для ручного введення часу в майбутньому
    # builder.row(InlineKeyboardButton(text="📝 Ввести свій час", callback_data="wr_custom_time_input"))
    
    builder.row(InlineKeyboardButton(text="⬅️ Назад до налаштувань нагадувань", callback_data=CB_SETTINGS_WEATHER_REMINDER))
    return builder.as_markup()

