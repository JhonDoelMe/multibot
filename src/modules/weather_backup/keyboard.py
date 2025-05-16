# src/modules/weather_backup/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Префікс для колбеків цього модуля, щоб відрізняти від основного модуля погоди
WEATHER_BACKUP_PREFIX = "weatherbk"

# Колбеки для поточної резервної погоди
CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT = f"{WEATHER_BACKUP_PREFIX}:refresh_current"
CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_3D = f"{WEATHER_BACKUP_PREFIX}:show_forecast_3d" # Змінено для ясності (3 дні)

# Нові колбеки для прогнозу на завтра (резерв)
CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_TOMORROW = f"{WEATHER_BACKUP_PREFIX}:show_forecast_tomorrow"

# Колбеки для дій після показу прогнозу (3-денного або на завтра)
CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST = f"{WEATHER_BACKUP_PREFIX}:refresh_forecast" # Оновлення поточного прогнозу (3д або завтра)
CALLBACK_WEATHER_BACKUP_SHOW_CURRENT_W = f"{WEATHER_BACKUP_PREFIX}:show_current_w" # Повернення до поточної резервної погоди


# Клавіатура після показу поточної резервної погоди
def get_current_weather_backup_keyboard() -> InlineKeyboardMarkup:
    """
    Клавіатура для поточної резервної погоди:
    - Оновити (резерв)
    - Прогноз на 3 дні (резерв) / Прогноз на завтра (резерв)
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Оновити (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT)
    )
    builder.row(
        InlineKeyboardButton(text="📅 Прогноз на 3 дні (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_3D),
        InlineKeyboardButton(text="☀️ Прогноз на завтра (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_TOMORROW)
    )
    # Кнопку "Назад в головне меню" тут зазвичай не додають, користувач може використати reply-клавіатуру
    return builder.as_markup()

# Клавіатура після показу резервного прогнозу (3-денного або на завтра)
def get_forecast_weather_backup_keyboard(is_tomorrow_forecast: bool = False) -> InlineKeyboardMarkup:
    """
    Клавіатура для резервного прогнозу:
    - Оновити поточний прогноз (3д або на завтра)
    - До поточної резервної погоди
    """
    builder = InlineKeyboardBuilder()
    
    # Текст кнопки оновлення залежить від того, який прогноз показано
    # Однак, колбек може бути один, а логіка оновлення в хендлері визначить, що саме оновлювати
    # на основі поточного стану FSM (showing_forecast_3d або showing_forecast_tomorrow).
    # Або можна мати різні колбеки для оновлення.
    # Для простоти, поки що один колбек на оновлення прогнозу.
    refresh_text = "🔄 Оновити прогноз (резерв)"
    # if is_tomorrow_forecast:
    #     refresh_text = "🔄 Оновити прогноз на завтра (резерв)"
    # else:
    #     refresh_text = "🔄 Оновити прогноз на 3 дні (резерв)"

    builder.row(
        InlineKeyboardButton(text=refresh_text, callback_data=CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST)
    )
    builder.row(
        InlineKeyboardButton(text="🌦️ До поточної (резерв)", callback_data=CALLBACK_WEATHER_BACKUP_SHOW_CURRENT_W)
    )
    return builder.as_markup()

# Ця клавіатура використовується, коли потрібно ввести місто для резервного сервісу
# Вона імпортується з основного модуля погоди, тому тут її можна не дублювати,
# або залишити, якщо вона має відрізнятися.
# from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard
# def get_weather_backup_enter_city_keyboard() -> InlineKeyboardMarkup:
#     """
#     Клавіатура для ситуації, коли потрібно ввести місто для резервного сервісу.
#     """
#     return get_weather_enter_city_back_keyboard() # Використовуємо ту саму, що й для основного
#     # або можна створити нову, якщо потрібно