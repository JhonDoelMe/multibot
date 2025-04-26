from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_currency_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    usd_btn = KeyboardButton("USD to UAH")
    back_btn = KeyboardButton("Назад")
    menu.add(usd_btn, back_btn)
    return menu