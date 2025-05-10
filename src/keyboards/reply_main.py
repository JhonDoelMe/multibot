# src/keyboards/reply_main.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Тексты кнопок
BTN_WEATHER = "🌦️ Погода (осн.)" # Уточним, что это основной сервис
BTN_CURRENCY = "💰 Курс валют"
BTN_ALERTS = "🚨 Повітряна тривога"
BTN_ALERTS_BACKUP = "🚨 Резерв (Тривоги)"
BTN_WEATHER_BACKUP = "🌦️ Погода (резерв)" # <<< НОВАЯ КНОПКА
BTN_LOCATION = "📍 Погода по геолокації (осн.)" # Уточним для геолокации

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """ Создает клавиатуру с основными командами + кнопка геолокации. """
    keyboard = [
        [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_WEATHER_BACKUP)], # Погода основная и резерв
        [KeyboardButton(text=BTN_ALERTS), KeyboardButton(text=BTN_ALERTS_BACKUP)],   # Тревоги основные и резерв
        [KeyboardButton(text=BTN_CURRENCY)],
        [KeyboardButton(text=BTN_LOCATION, request_location=True)]
    ]
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Оберіть опцію або відправте локацію..."
        )
    return markup