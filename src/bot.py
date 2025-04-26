# src/bot.py

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiogram.types import Update

from src import config
# --- Импорт для БД ---
from src.db.database import initialize_database, async_session_factory
# --- Импорт Middleware ---
from src.middlewares.db_session import DbSessionMiddleware

# Импортируем роутеры
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

# --- Функции для запуска/остановки ---

async def on_startup(bot: Bot):
    logger.info("Executing on_startup actions...")
    if not config.RUN_WITH_WEBHOOK:
         logger.info("Running in polling mode, deleting potential webhook...")
         await bot.delete_webhook(drop_pending_updates=True)
         logger.info("Webhook deleted.")

async def on_shutdown(bot: Bot):
    logger.warning("Executing on_shutdown actions...")
    logger.warning("Bot shutdown complete.")


async def main() -> None:
    """ Главная функция: настраивает и запускает бота. """

    # --- Инициализация БД ---
    logger.info("Attempting database initialization...")
    db_initialized = await initialize_database()
    if not db_initialized and config.DATABASE_URL:
         logger.critical("Database initialization failed! Bot functionalities might be limited.")
    elif db_initialized:
         logger.info("Database initialization seems successful.")

    # --- Инициализация Aiogram ---
    logger.info("Initializing Aiogram components...")
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=config.BOT_TOKEN, default=default_props)
    dp = Dispatcher(storage=storage)

    # --- Регистрация Middleware ---
    if db_initialized and async_session_factory:
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("Database session middleware skipped (DB not initialized or session factory missing).")

    # --- Регистрация роутеров ---
    logger.info("Registering routers...")
    dp.include_router(weather_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(common_handlers.router)
    logger.info("All routers registered.")

    # --- Вызов on_startup ---
    await on_startup(bot)

    # --- Логика запуска ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # --- Режим Вебхука ---
            logger.warning("Starting bot in WEBHOOK mode...")

            # Создаем приложение aiohttp
            app = web.Application()
            app["bot"] = bot
            app["dp"] = dp
            logger.info("aiohttp Application created.")

            # Регистрируем обработчик вебхуков
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=config.BOT_TOKEN[:10]
            )
            if config.WEBHOOK_PATH:
                webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
                logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            else:
                 logger.error("WEBHOOK_PATH is not set! Cannot register webhook handler.")

            # Связываем aiogram с aiohttp
            setup_application(app, dp, bot=bot)
            logger.info("aiohttp Application setup complete.")

            # Запускаем веб-сервер
            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            logger.info(f"Attempting to start web server on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info("Web server started successfully (site.start() completed).") # <<< Важный лог

            # Ожидаем вечно
            logger.info("Starting infinite wait loop (asyncio.Event().wait())...") # <<< Важный лог
            await asyncio.Event().wait()
            logger.warning("Infinite wait loop somehow finished (THIS IS UNEXPECTED!).") # <<< Не должно появиться

        else:
            # --- Режим Поллинга ---
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            await dp.start_polling(bot)

    finally:
        logger.warning("Closing bot session (in finally block)...")
        await bot.session.close()
        logger.warning("Bot session closed.")
        await on_shutdown(bot)