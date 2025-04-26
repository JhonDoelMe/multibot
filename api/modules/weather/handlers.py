from aiogram import Router, types
from aiogram.filters import Command, Text
from .api import get_weather
from .keyboard import get_weather_menu
from keyboards.main_menu import get_main_menu

weather_router = Router()

@weather_router.message(Command("weather"))
@weather_router.message(Text("Погода"))
async def cmd_weather(message: types.Message):
    try:
        await message.reply(
            "Выбери действие:",
            reply_markup=get_weather_menu()
        )
    except Exception as e:
        await message.reply("Ошибка в модуле погоды")
        # Модуль изолирован, другие продолжают работать

@weather_router.message(Text("Прогноз на сегодня"))
async def weather_forecast(message: types.Message):
    try:
        result = await get_weather()
        await message.reply(result, reply_markup=get_weather_menu())
    except Exception as e:
        await message.reply("Ошибка при получении прогноза")

@weather_router.message(Text("Назад"))
async def back_to_main(message: types.Message):
    await message.reply(
        "Возвращаемся в главное меню:",
        reply_markup=get_main_menu()
    )