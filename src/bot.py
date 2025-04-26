# src/bot.py (Возвращаем нормальную логику)

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
# --- Возвращаем импорты для вебхука ---
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
    print("--- BOT: On_startup called.", flush=True)
    logger.info("Executing on_startup actions...")
    if not config.RUN_WITH_WEBHOOK:
         print("--- BOT: Deleting webhook for polling mode.", flush=True)
         logger.info("Running in polling mode, deleting potential webhook...")
         await bot.delete_webhook(drop_pending_updates=True)
         logger.info("Webhook deleted.")
    print("--- BOT: On_startup finished.", flush=True)

async def on_shutdown(bot: Bot):
    print("--- BOT: On_shutdown called.", flush=True)
    logger.warning("Executing on_shutdown actions...")
    logger.warning("Bot shutdown complete.")


async def main() -> None:
    """ Главная функция: настраивает и запускает бота. """
    print("--- MAIN: Starting main() function.", flush=True)

    # --- Инициализация БД ---
    print("--- MAIN: Calling initialize_database()...", flush=True)
    db_initialized = await initialize_database()
    print(f"--- MAIN: initialize_database() returned: {db_initialized}", flush=True)

    if not db_initialized and config.DATABASE_URL:
         print("--- MAIN: WARNING - DB init failed. Continuing without DB middleware.", flush=True)
         logger.warning("Database initialization failed! Bot functionalities might be limited.")
         # sys.exit(1) # Убираем принудительный выход

    # --- Инициализация Aiogram ---
    print("--- MAIN: Initializing Aiogram components...", flush=True)
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    try:
        bot = Bot(token=config.BOT_TOKEN, default=default_props)
        print("--- MAIN: Aiogram Bot initialized.", flush=True)
    except Exception as e:
        print(f"--- MAIN: !!! FAILED TO INIT BOT: {e!r}", flush=True)
        logger.exception("Failed to initialize Bot", exc_info=True)
        sys.exit("Critical: Bot initialization failed") # Выходим, если бот не создался

    dp = Dispatcher(storage=storage)
    print("--- MAIN: Aiogram Dispatcher initialized.", flush=True)


    # --- Регистрация Middleware ---
    if db_initialized and async_session_factory:
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
        print("--- MAIN: Database session middleware registered.", flush=True)
    else:
        print("--- MAIN: Database session middleware skipped.", flush=True)
        logger.warning("Database session middleware skipped (DB not initialized or session factory missing).")

    # --- Регистрация роутеров ---
    print("--- MAIN: Registering routers...", flush=True)
    dp.include_router(weather_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(common_handlers.router)
    print("--- MAIN: Routers registered.", flush=True)

    # --- Вызов on_startup ---
    print("--- MAIN: Calling on_startup...", flush=True)
    await on_startup(bot)
    print("--- MAIN: on_startup finished.", flush=True)

    # --- Логика запуска ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # ###################################################
            # ### ВОЗВРАЩАЕМ НОРМАЛЬНЫЙ КОД ДЛЯ WEBHOOK РЕЖИМА ###
            # ###################################################
            print("--- MAIN: Starting WEBHOOK mode...", flush=True)
            logger.warning("Starting bot in WEBHOOK mode...")

            # Создаем приложение aiohttp
            app = web.Application()
            app["bot"] = bot
            app["dp"] = dp
            print("--- WEB: aiohttp Application created.", flush=True)

            # Регистрируем обработчик вебхуков aiogram
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=config.BOT_TOKEN[:10] # Секрет для проверки запросов
            )
            if config.WEBHOOK_PATH:
                webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
                print(f"--- WEB: Registered webhook handler at path: {config.WEBHOOK_PATH}", flush=True)
                logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            else:
                 print("--- WEB: ERROR - WEBHOOK_PATH not set!", flush=True)
                 logger.error("WEBHOOK_PATH is not set! Cannot register webhook handler.")

            # Связываем aiogram с aiohttp
            setup_application(app, dp, bot=bot)
            print("--- WEB: aiohttp Application setup complete (setup_application).", flush=True)

            # Запускаем веб-сервер
            runner = web.AppRunner(app)
            await runner.setup()
            print("--- WEB: AppRunner setup complete.", flush=True)
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            print(f"--- WEB: Attempting site.start() on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...", flush=True)
            await site.start()
            print("--- WEB: site.start() completed.", flush=True)
            logger.info("Web server started successfully.")

            # Ожидаем вечно
            print("--- WEB: Starting infinite wait loop (asyncio.Event().wait())...", flush=True)
            await asyncio.Event().wait()
            print("--- WEB: !!! ERROR - Infinite wait loop somehow finished !!!", flush=True)
            logger.warning("Infinite wait loop somehow finished (THIS IS UNEXPECTED!).")
            # ###################################################
            # ### КОНЕЦ НОРМАЛЬНОГО КОДА ДЛЯ WEBHOOK РЕЖИМА ###
            # ###################################################
        else:
            # --- Режим Поллинга ---
            print("--- MAIN: Starting POLLING mode...", flush=True)
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            await dp.start_polling(bot)

    finally:
        print("--- MAIN: Entering finally block...", flush=True)
        logger.warning("Closing bot session (in finally block)...")
        await bot.session.close()
        logger.warning("Bot session closed.")
        await on_shutdown(bot)
        print("--- MAIN: Exiting finally block.", flush=True)