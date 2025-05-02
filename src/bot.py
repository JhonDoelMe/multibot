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
from src.middlewares.rate_limit import ThrottlingMiddleware # <<< Добавили импорт Throttling

# Импортируем роутеры
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

# --- Функции для запуска/остановки ---

async def on_startup(bot: Bot):
    """ Выполняется при старте бота: инициализация БД и удаление старого вебхука (для polling). """
    logger.info("Executing on_startup actions...")
    if not config.RUN_WITH_WEBHOOK:
         logger.info("Running in polling mode, deleting potential webhook...")
         await bot.delete_webhook(drop_pending_updates=True)
         logger.info("Webhook deleted.")
    # Убрали установку вебхука отсюда

async def on_shutdown(bot: Bot):
    """ Выполняется при остановке бота. """
    logger.warning("Executing on_shutdown actions...")
    logger.warning("Bot shutdown complete.")


async def main() -> None:
    """ Главная функция: настраивает и запускает бота. """
    logger.info("Starting main() function.")

    # --- Инициализация БД ---
    logger.info("Attempting database initialization...")
    db_initialized, session_factory = await initialize_database()
    logger.info(f"initialize_database() returned: db_initialized={db_initialized}, session_factory is {'set' if session_factory else 'None'}")

    if not db_initialized and config.DATABASE_URL:
         logger.warning("Database initialization failed! Bot functionalities might be limited.")

    # --- Инициализация Aiogram ---
    logger.info("Initializing Aiogram components...")
    storage = MemoryStorage() # Можно заменить на RedisStorage, если Redis настроен
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    try:
        bot = Bot(token=config.BOT_TOKEN, default=default_props)
        logger.info("Aiogram Bot initialized.")
    except Exception as e:
        logger.exception("Failed to initialize Bot", exc_info=True)
        sys.exit("Critical: Bot initialization failed")

    dp = Dispatcher(storage=storage)
    logger.info("Aiogram Dispatcher initialized.")

    # --- Регистрация Middleware ---
    # Сначала сессия БД
    if db_initialized and session_factory:
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("Database session middleware skipped (DB not initialized or session factory missing).")

    # Затем Throttling (ограничение частоты)
    dp.update.outer_middleware(ThrottlingMiddleware(default_rate=0.5)) # Лимит 0.5 сек
    logger.info("Throttling middleware registered.")
    # ---------------------------------------------------

    # --- Регистрация роутеров (идет после middleware) ---
    logger.info("Registering routers...")
    dp.include_router(weather_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(common_handlers.router) # Общий роутер последним
    logger.info("All routers registered.")

    # --- Вызов on_startup ---
    await on_startup(bot) # Вызываем до старта

    # --- Логика запуска ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # --- Режим Вебхука ---
            logger.warning("Starting bot in WEBHOOK mode...")

            app = web.Application()
            app["bot"] = bot
            app["dp"] = dp
            logger.info("aiohttp Application created for webhook.")

            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=config.BOT_TOKEN[:10] # Секрет для проверки запросов
            )
            if config.WEBHOOK_PATH:
                webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
                logger.info(f"Registered aiogram webhook handler at path: {config.WEBHOOK_PATH}")
            else:
                 logger.error("WEBHOOK_PATH is not set! Cannot register webhook handler.")

            setup_application(app, dp, bot=bot) # Связываем aiogram с aiohttp
            logger.info("aiohttp Application setup with aiogram complete.")

            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info("Web server started successfully.")

            logger.info("Starting infinite wait loop for web server...")
            await asyncio.Event().wait() # Ожидаем вечно
            logger.warning("Infinite wait loop somehow finished (UNEXPECTED!).")

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
        logger.info("Exiting main() function finally block.")