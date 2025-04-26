# src/bot.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage # <<< Добавили импорт MemoryStorage

# Импортируем конфигурацию
from src import config

# Импортируем роутеры
from src.handlers import common as common_handlers
# --- Подключаем модуль погоды ---
from src.modules.weather import handlers as weather_handlers # <<< Раскомментировали
# Заготовки для импорта роутеров модулей
# from src.modules.currency import handlers as currency_handlers
# from src.modules.alert import handlers as alert_handlers

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def main() -> None:
    """Главная асинхронная функция для настройки и запуска бота."""
    logger.info("Starting bot setup...")

    # --- Инициализация ---
    # Используем MemoryStorage для хранения состояний FSM
    storage = MemoryStorage() # <<< Создали экземпляр хранилища

    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=config.BOT_TOKEN, default=default_props)

    # Передаем хранилище в Диспетчер
    dp = Dispatcher(storage=storage) # <<< Передали storage

    # --- Регистрация роутеров ---
    logger.info("Registering routers...")
    # Сначала общие команды
    dp.include_router(common_handlers.router)
    # Затем роутеры модулей
    dp.include_router(weather_handlers.router) # <<< Раскомментировали
    logger.info("Weather module router registered.")
    # dp.include_router(currency_handlers.router)
    # logger.info("Currency module router registered.")
    # dp.include_router(alert_handlers.router)
    # logger.info("Alert module router registered.")

    # --- Запуск Polling ---
    try:
      await bot.delete_webhook(drop_pending_updates=True)
      logger.info("Webhook deleted (if existed).")
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")

    logger.info("Starting polling...")
    await dp.start_polling(bot)

# Точка входа остается в __main__.py