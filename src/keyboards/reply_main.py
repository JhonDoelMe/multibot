# src/keyboards/reply_main.py

from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

# Тексты кнопок
BTN_WEATHER = "🌦️ Погода"
BTN_CURRENCY = "💰 Курс валют"
BTN_ALERTS = "🚨 Повітряна тривога"
BTN_LOCATION = "📍 Погода по геолокації" # <<< Новая кнопка

def get_main_reply_keyboard() -> ReplyKeyboardMarkup:
    """ Создает клавиатуру с основными командами + кнопка геолокации. """
    keyboard = [
        # Первый ряд оставляем как есть
        [KeyboardButton(text=BTN_WEATHER), KeyboardButton(text=BTN_CURRENCY)],
        # Второй ряд
        [KeyboardButton(text=BTN_ALERTS)],
        # Третий ряд - кнопка геолокации
        [KeyboardButton(text=BTN_LOCATION, request_location=True)] # <<< Добавляем request_location=True
    ]
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Оберіть опцію або відправте локацію..." # Обновили подсказку
        )
    return markup