# src/modules/weather/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Callback data префиксы и константы для модуля погоды
WEATHER_PREFIX = "weather"
# Основные действия
CALLBACK_WEATHER_BACK = f"{WEATHER_PREFIX}:back"
CALLBACK_WEATHER_REFRESH = f"{WEATHER_PREFIX}:refresh" # Пока не используется
# Подтверждение использования сохраненного города
CALLBACK_WEATHER_USE_SAVED = f"{WEATHER_PREFIX}:use_saved"
CALLBACK_WEATHER_OTHER_CITY = f"{WEATHER_PREFIX}:other_city"
# Подтверждение сохранения города
CALLBACK_WEATHER_SAVE_CITY_YES = f"{WEATHER_PREFIX}:save_yes"
CALLBACK_WEATHER_SAVE_CITY_NO = f"{WEATHER_PREFIX}:save_no"


def get_city_confirmation_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура для подтверждения использования сохраненного города.
    Кнопки: Да / Друге місто
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Так", callback_data=CALLBACK_WEATHER_USE_SAVED),
        InlineKeyboardButton(text="✍️ Інше місто", callback_data=CALLBACK_WEATHER_OTHER_CITY)
    )
    return builder.as_markup()

def get_save_city_keyboard() -> InlineKeyboardMarkup:
    """
    Клавиатура с вопросом о сохранении города.
    Кнопки: Так / Ні
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💾 Так, зберегти", callback_data=CALLBACK_WEATHER_SAVE_CITY_YES),
        InlineKeyboardButton(text="❌ Ні", callback_data=CALLBACK_WEATHER_SAVE_CITY_NO)
    )
    # Добавляем кнопку "Назад" на всякий случай
    builder.row(
         InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK)
    )
    return builder.as_markup()


def get_weather_back_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает инлайн-клавиатуру с кнопкой 'Назад в меню'.
    (Остается без изменений, но можно добавить сюда кнопку "Оновити" если нужно)
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK)
        # InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_WEATHER_REFRESH)
    )
    return builder.as_markup()