# src/keyboards/reply_main.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Тексты кнопок
BTN_WEATHER = "🌦️ Погода (осн.)"
BTN_CURRENCY = "💰 Курс валют"
BTN_ALERTS = "🚨 Повітряна тривога"
BTN_ALERTS_BACKUP = "🚨 Резерв (Тривоги)"
BTN_WEATHER_BACKUP = "🌦️ Погода (резерв)"
BTN_LOCATION_MAIN = "📍 Погода по геолокації (осн.)" # Переименована для ясности
BTN_LOCATION_BACKUP = "📍 Погода по геолокації (резерв)" # <<< НОВАЯ КНОПКА

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """ Создает клавиатуру с основными командами + кнопки геолокации. """
    keyboard = [
        [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_WEATHER_BACKUP)],
        [KeyboardButton(text=BTN_ALERTS), KeyboardButton(text=BTN_ALERTS_BACKUP)],
        [KeyboardButton(text=BTN_CURRENCY)],
        [KeyboardButton(text=BTN_LOCATION_MAIN, request_location=True), KeyboardButton(text=BTN_LOCATION_BACKUP, request_location=True)] # Две кнопки геолокации
    ]
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Оберіть опцію або відправте локацію..."
        )
    return markup