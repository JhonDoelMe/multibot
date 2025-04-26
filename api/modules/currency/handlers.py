from aiogram import Router, types
from aiogram.filters import Command, Text
from .api import get_currency_rate
from .keyboard import get_currency_menu
from keyboards.main_menu import get_main_menu

currency_router = Router()

@currency_router.message(Command("currency"))
@currency_router.message(Text("Курс валют"))
async def cmd_currency(message: types.Message):
    try:
        await message.reply(
            "Выбери валюту:",
            reply_markup=get_currency_menu()
        )
    except Exception as e:
        await message.reply("Ошибка в модуле валют")

@currency_router.message(Text("USD to UAH"))
async def currency_usd(message: types.Message):
    try:
        result = await get_currency_rate()
        await message.reply(result, reply_markup=get_currency_menu())
    except Exception as e:
        await message.reply("Ошибка при получении курса")

@currency_router.message(Text("Назад"))
async def back_to_main(message: types.Message):
    await message.reply(
        "Возвращаемся в главное меню:",
        reply_markup=get_main_menu()
    )