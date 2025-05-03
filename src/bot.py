# src/bot.py

import asyncio
import logging
import sys
from contextlib import suppress
import aiohttp # <<< Добавлен импорт aiohttp

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiogram.types import Update
from aiogram.exceptions import TelegramNetworkError

from src import config
from src.db.database import initialize_database
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

# Импортируем роутеры
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.modules.alert_backup import handlers as alert_backup_handlers # <<< ДОБАВЛЕНО
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

async def on_startup(bot: Bot):
    logger.info("Executing on_startup actions...")
    if not config.RUN_WITH_WEBHOOK:
        logger.info("Running in polling mode, deleting potential webhook...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted.")
        except TelegramNetworkError as e:
            logger.error(f"Error deleting webhook: {e}")


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

    # Настройка сессии с таймаутом
    # Используем ClientTimeout из aiohttp
    session = AiohttpSession()
    try:
        bot = Bot(token=config.BOT_TOKEN, default=default_props, session=session)
        logger.info("Aiogram Bot initialized with custom session.")
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
    dp.include_router(alert_backup_handlers.router) # <<< ДОБАВЛЕНО
    dp.include_router(common_handlers.router) # Общий лучше регистрировать последним
    logger.info("All routers registered.")

    # --- Call on_startup ---
    await on_startup(bot)

    # --- Start Logic ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # --- Webhook Mode ---
            logger.warning("Starting bot in WEBHOOK mode...")
            app = web.Application()
            app["bot"] = bot
            app["dp"] = dp
            logger.info("aiohttp Application created for webhook.")
            webhook_requests_handler = SimpleRequestHandler(dispatcher=dp, bot=bot, secret_token=config.BOT_TOKEN[:10]) # Используем часть токена как секрет
            if config.WEBHOOK_PATH:
                webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
                logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            else:
                logger.error("WEBHOOK_PATH not set! Cannot register webhook handler.")
            setup_application(app, dp, bot=bot)
            logger.info("aiohttp Application setup complete.")
            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info("Web server started successfully.")
            logger.info("Starting infinite wait loop for web server...")
            await asyncio.Event().wait() # Бесконечное ожидание для веб-сервера
            logger.warning("Infinite wait loop finished (UNEXPECTED!).")
        else:
            # --- Polling Mode ---
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            max_retries = 5 # Макс попыток рестарта поллинга
            retry_delay = 2 # Начальная задержка в секундах

            for attempt in range(max_retries):
                try:
                    # Убрали явное добавление таймаута в start_polling, так как он настроен в сессии
                    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
                    break # Если start_polling завершился штатно (например, по KeyboardInterrupt), выходим
                except TelegramNetworkError as e:
                    logger.error(f"TelegramNetworkError during polling (attempt {attempt + 1}/{max_retries}): {e}")
                    if attempt < max_retries - 1:
                        logger.info(f"Waiting {retry_delay} seconds before retrying polling...")
                        await asyncio.sleep(retry_delay)
                        retry_delay *= 2 # Увеличиваем задержку экспоненциально
                    else:
                        logger.critical("All polling retries failed. Stopping bot.")
                        # Можно добавить отправку уведомления администратору здесь
                except Exception as e:
                     logger.exception(f"Unhandled exception during polling: {e}", exc_info=True)
                     # Можно добавить отправку уведомления администратору
                     # Решаем, нужно ли пытаться перезапустить после неизвестной ошибки
                     if attempt < max_retries - 1:
                          logger.info(f"Waiting {retry_delay} seconds before retrying polling...")
                          await asyncio.sleep(retry_delay)
                          retry_delay *= 2
                     else:
                          logger.critical("Stopping bot after unhandled exception in polling.")
    finally:
        logger.warning("Closing bot session (in finally block)...")
        await bot.session.close()
        logger.warning("Bot session closed.")
        await on_shutdown(bot)
        logger.info("Exiting main() function finally block.")