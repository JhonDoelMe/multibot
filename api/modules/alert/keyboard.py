from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

def get_alert_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    status_btn = KeyboardButton("Статус тревоги")
    back_btn = KeyboardButton("Назад")
    menu.add(status_btn, back_btn)
    return menu