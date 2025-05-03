# src/bot.py (Очищенная версия)

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
from src.db.database import initialize_database # <<< ИСПРАВЛЕНО ЗДЕСЬ
# --- Импорт Middleware ---
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

# Импортируем роутеры
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

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
    logger.info("Starting main() function.")

    # --- DB Init ---
    logger.info("Attempting database initialization...")
    db_initialized, session_factory = await initialize_database()
    logger.info(f"initialize_database() returned: db_initialized={db_initialized}, session_factory is {'set' if session_factory else 'None'}")
    if not db_initialized and config.DATABASE_URL:
         logger.warning("Database initialization failed! Bot functionalities might be limited.")

    # --- Aiogram Init ---
    logger.info("Initializing Aiogram components...")
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    try:
        bot = Bot(token=config.BOT_TOKEN, default=default_props)
        logger.info("Aiogram Bot initialized.")
    except Exception as e:
        logger.exception("Failed to initialize Bot", exc_info=True)
        sys.exit("Critical: Bot initialization failed")
    dp = Dispatcher(storage=storage)
    logger.info("Aiogram Dispatcher initialized.")

    # --- Register Middleware ---
    if db_initialized and session_factory:
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("Database session middleware skipped.")
    dp.update.outer_middleware(ThrottlingMiddleware(default_rate=0.5))
    logger.info("Throttling middleware registered.")

    # --- Register Routers ---
    logger.info("Registering routers...")
    dp.include_router(weather_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(common_handlers.router)
    logger.info("All routers registered.")

    # --- Call on_startup ---
    await on_startup(bot)

    # --- Start Logic ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # --- Webhook Mode ---
            logger.warning("Starting bot in WEBHOOK mode...")
            app = web.Application(); app["bot"] = bot; app["dp"] = dp
            logger.info("aiohttp Application created for webhook.")
            webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.BOT_TOKEN[:10])
            if config.WEBHOOK_PATH: webhook_requests_handler.register(app, path=config.WEBHOOK_PATH); logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            else: logger.error("WEBHOOK_PATH not set! Cannot register webhook handler.")
            setup_application(app, dp, bot=bot)
            logger.info("aiohttp Application setup complete.")
            runner = web.AppRunner(app); await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info("Web server started successfully.")
            logger.info("Starting infinite wait loop for web server...")
            await asyncio.Event().wait()
            logger.warning("Infinite wait loop finished (UNEXPECTED!).")
        else:
            # --- Polling Mode ---
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            await dp.start_polling(bot)
    finally:
        logger.warning("Closing bot session (in finally block)...")
        await bot.session.close()
        logger.warning("Bot session closed.")
        await on_shutdown(bot)
        logger.info("Exiting main() function finally block.")