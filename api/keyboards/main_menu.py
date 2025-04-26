from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_main_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    weather_btn = KeyboardButton("Погода")
    currency_btn = KeyboardButton("Курс валют")
    alert_btn = KeyboardButton("Воздушная тревога")
    menu.add(weather_btn, currency_btn)
    menu.add(alert_btn)
    return menu