from aiogram import Router, types
from aiogram.filters import Command, Text
from .api import get_alert_status
from .keyboard import get_alert_menu
from keyboards.main_menu import get_main_menu

alert_router = Router()

@alert_router.message(Command("alert"))
@alert_router.message(Text("Воздушная тревога"))
async def cmd_alert(message: types.Message):
    try:
        await message.reply(
            "Выбери действие:",
            reply_markup=get_alert_menu()
        )
    except Exception as e:
        await message.reply("Ошибка в модуле тревоги")

@alert_router.message(Text("Статус тревоги"))
async def alert_status(message: types.Message):
    try:
        result = await get_alert_status()
        await message.reply(result, reply_markup=get_alert_menu())
    except Exception as e:
        await message.reply("Ошибка при получении статуса")

@alert_router.message(Text("Назад"))
async def back_to_main(message: types.Message):
    await message.reply(
        "Возвращаемся в главное меню:",
        reply_markup=get_main_menu()
    )