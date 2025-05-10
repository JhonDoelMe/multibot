# src/modules/weather_backup/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Префикс для колбэков этого модуля, чтобы отличать от основного модуля погоды
WEATHER_BACKUP_PREFIX = "weatherbk"

CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT = f"{WEATHER_BACKUP_PREFIX}:refresh_current"
CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST = f"{WEATHER_BACKUP_PREFIX}:refresh_forecast" # Если будем делать прогноз
CALLBACK_WEATHER_BACKUP_SHOW_FORECAST = f"{WEATHER_BACKUP_PREFIX}:show_forecast" # Кнопка для показа прогноза
CALLBACK_WEATHER_BACKUP_SHOW_CURRENT = f"{WEATHER_BACKUP_PREFIX}:show_current_w" # Кнопка для показа текущей (из прогноза)

# Клавиатура после показа текущей резервной погоды
def get_current_weather_backup_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для текущей резервной погоды: Обновить / Показать прогноз (3 дня).
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT)
    )
    # Можно добавить кнопку для запроса прогноза от резервного источника
    builder.row(
        InlineKeyboardButton(text="📅 Прогноз на 3 дні (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_SHOW_FORECAST)
    )
    return builder.as_markup()

# Клавиатура после показа резервного прогноза
def get_forecast_weather_backup_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для резервного прогноза: Обновить прогноз / Показать текущую.
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити прогноз (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST)
    )
    builder.row(
        InlineKeyboardButton(text="🌦️ До поточної (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_SHOW_CURRENT)
    )
    return builder.as_markup()

def get_weather_backup_enter_city_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для ситуации, когда нужно ввести город для резервного сервиса
    (например, если не удалось определить город или пользователь хочет другой).
    Пока не используется, но может пригодиться.
    """
    builder = InlineKeyboardBuilder()
    # Можно добавить кнопку "Назад в главное меню", если этот модуль будет иметь состояние FSM
    # builder.row(InlineKeyboardButton(text="⬅️ Назад в меню", callback_data="main_menu")) # Пример
    return builder.as_markup()