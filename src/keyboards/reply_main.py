# src/keyboards/reply_main.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Обновленные тексты кнопок
BTN_WEATHER = "🌦️ Погода"
BTN_CURRENCY = "💰 Курс валют"
BTN_ALERTS = "🚨 Повітряна тривога"
BTN_LOCATION = "📍 Погода по геолокації"
BTN_SETTINGS = "⚙️ Налаштування"

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """ Создает клавиатуру с основными командами + кнопка геолокации + настройки. """
    keyboard = [
        [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_ALERTS)],
        [KeyboardButton(text=BTN_CURRENCY), KeyboardButton(text=BTN_SETTINGS)],
        [KeyboardButton(text=BTN_LOCATION, request_location=True)]
    ]
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Оберіть опцію або відправте локацію..."
        )
    return markup