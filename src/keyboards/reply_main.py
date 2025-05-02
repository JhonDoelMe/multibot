# src/keyboards/reply_main.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Тексты кнопок (выносим в константы для удобства)
BTN_WEATHER = "🌦️ Погода"
BTN_CURRENCY = "💰 Курс валют"
BTN_ALERTS = "🚨 Повітряна тривога"
# BTN_SETTINGS = "⚙️ Налаштування" # Можно добавить позже

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """
    Создает и возвращает клавиатуру с основными командами под полем ввода.
    """
    # Создаем ряды кнопок
    keyboard = [
        [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_CURRENCY)],
        [KeyboardButton(text=BTN_ALERTS)],
        # [KeyboardButton(text=BTN_SETTINGS)], # Ряд для настроек
    ]

    # Создаем объект клавиатуры
    # resize_keyboard=True - делает кнопки компактнее
    # input_field_placeholder - подсказка в поле ввода (опционально)
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Оберіть опцію..."
        )
    return markup