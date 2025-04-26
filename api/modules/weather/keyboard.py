from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_weather_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    forecast_btn = KeyboardButton("Прогноз на сегодня")
    back_btn = KeyboardButton("Назад")
    menu.add(forecast_btn, back_btn)
    return menu