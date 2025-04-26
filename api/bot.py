import os
import json
import logging
from http import HTTPStatus
from aiogram import Bot, Dispatcher, types
from aiogram.types import Update
from modules.weather.handlers import weather_router
from modules.currency.handlers import currency_router
from modules.alert.handlers import alert_router
from keyboards.main_menu import get_main_menu

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота
API_TOKEN = os.getenv('TELEGRAM_TOKEN')
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# Регистрация роутеров из модулей
dp.include_router(weather_router)
dp.include_router(currency_router)
dp.include_router(alert_router)

# Обработчик команды /start
@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply(
        "Привет! Выбери опцию:",
        reply_markup=get_main_menu()
    )

# Обработчик Vercel (серверлесс)
async def handler(request):
    try:
        if request.method == 'POST':
            update = types.Update(**json.loads(await request.text()))
            await dp.process_update(update)
            return {'statusCode': HTTPStatus.OK, 'body': 'OK'}
        return {'statusCode': HTTPStatus.METHOD_NOT_ALLOWED, 'body': 'Method not allowed'}
    except Exception as e:
        logger.error(f"Error processing request: {e}")
        return {'statusCode': HTTPStatus.INTERNAL_SERVER_ERROR, 'body': str(e)}