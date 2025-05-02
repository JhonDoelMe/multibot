# src/modules/weather/keyboard.py

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Callback data префиксы и константы
WEATHER_PREFIX = "weather"
# Основные действия - переименовали для ясности
CALLBACK_WEATHER_OTHER_CITY = f"{WEATHER_PREFIX}:other" # Запросить другой город
CALLBACK_WEATHER_REFRESH = f"{WEATHER_PREFIX}:refresh" # Обновить погоду для ТЕКУЩЕГО (отображенного) города
CALLBACK_WEATHER_BACK_TO_MAIN = f"{WEATHER_PREFIX}:back_main" # Возврат именно из диалога ввода города

# Подтверждение сохранения города
CALLBACK_WEATHER_SAVE_CITY_YES = f"{WEATHER_PREFIX}:save_yes"
CALLBACK_WEATHER_SAVE_CITY_NO = f"{WEATHER_PREFIX}:save_no"

# Клавиатура БОЛЬШЕ НЕ НУЖНА, показываем погоду сразу
# def get_city_confirmation_keyboard() -> InlineKeyboardMarkup: ...

def get_save_city_keyboard() -> InlineKeyboardMarkup:
    """ Клавиатура с вопросом о сохранении города (без кнопки Назад). """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="💾 Так, зберегти", callback_data=CALLBACK_WEATHER_SAVE_CITY_YES),
        InlineKeyboardButton(text="❌ Ні", callback_data=CALLBACK_WEATHER_SAVE_CITY_NO)
    )
    # Убрали кнопку Назад
    return builder.as_markup()


def get_weather_actions_keyboard() -> InlineKeyboardMarkup:
    """
    Возвращает инлайн-клавиатуру с действиями ПОСЛЕ показа погоды.
    Кнопки: Другой город / Обновить
    """
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏙️ Інше місто", callback_data=CALLBACK_WEATHER_OTHER_CITY),
        InlineKeyboardButton(text="🔄 Оновити", callback_data=CALLBACK_WEATHER_REFRESH)
    )
    # Убрали кнопку Назад в меню
    return builder.as_markup()

def get_weather_enter_city_back_keyboard() -> InlineKeyboardMarkup:
     """ Клавиатура для экрана ввода города (только Назад) """
     builder = InlineKeyboardBuilder()
     builder.row(
         InlineKeyboardButton(text="⬅️ Назад в меню", callback_data=CALLBACK_WEATHER_BACK_TO_MAIN)
     )
     return builder.as_markup()