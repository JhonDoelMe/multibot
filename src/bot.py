# src/bot.py

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

# Импортируем конфигурацию
from src import config
# --- Импорт для БД ---
from src.db.database import init_db, async_session_factory # <<< Импортируем фабрику сессий
# --- Импорт Middleware ---
from src.middlewares.db_session import DbSessionMiddleware # <<< Импортируем Middleware

# Импортируем роутеры
# (Порядок важен: сначала специфичные, потом общие)
from src.modules.weather import handlers as weather_handlers
# from src.modules.currency import handlers as currency_handlers
# from src.modules.alert import handlers as alert_handlers
from src.handlers import common as common_handlers


# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def main() -> None:
    """Главная асинхронная функция для настройки и запуска бота."""
    logger.info("Starting bot setup...")

    # --- Инициализация БД ---
    if config.DATABASE_URL:
        logger.info("Initializing database...")
        await init_db()
    else:
        logger.warning("DATABASE_URL is not set. Skipping database initialization.")
        # Если БД критична, возможно, стоит прекратить выполнение или работать в ограниченном режиме
        # exit("Database URL is required.") # Например

    # --- Инициализация Aiogram ---
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=config.BOT_TOKEN, default=default_props)
    dp = Dispatcher(storage=storage)

    # --- Регистрация Middleware ---
    # Middleware сессии БД будет срабатывать ДО роутеров для КАЖДОГО события
    if async_session_factory: # Убедимся, что фабрика сессий создана (DATABASE_URL был задан)
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("Database session middleware skipped (no session factory).")

    # --- Регистрация роутеров ---
    logger.info("Registering routers...")
    # СНАЧАЛА регистрируем роутеры модулей
    dp.include_router(weather_handlers.router)
    logger.info("Weather module router registered.")
    # dp.include_router(currency_handlers.router)
    # logger.info("Currency module router registered.")
    # dp.include_router(alert_handlers.router)
    # logger.info("Alert module router registered.")

    # В КОНЦЕ регистрируем общие обработчики
    dp.include_router(common_handlers.router)
    logger.info("Common handlers router registered.")

    # --- Запуск Polling ---
    try:
      await bot.delete_webhook(drop_pending_updates=True)
      logger.info("Webhook deleted (if existed).")
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")

    logger.info("Starting polling...")
    await dp.start_polling(bot)

# Точка входа остается в __main__.py