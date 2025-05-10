# src/bot.py

import asyncio
import logging
import sys
import aiohttp
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage # <<< ДОДАНО ІМПОРТ

from src import config
from src.db.database import initialize_database
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

# Імпортуємо роутери
from src.handlers import common as common_handlers
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.modules.alert_backup import handlers as alert_backup_handlers
from src.modules.weather_backup import handlers as weather_backup_handlers
from src.modules.settings import handlers as settings_handlers

logger = logging.getLogger(__name__)

async def on_startup(bot: Bot, dispatcher: Dispatcher, base_url: Optional[str] = None):
    logger.info("Executing on_startup actions...")
    if config.RUN_WITH_WEBHOOK:
        if not base_url:
            logger.error("Base URL for webhook is not provided on startup! Cannot set webhook.")
            return
        webhook_url = f"{base_url.rstrip('/')}{config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook to: {webhook_url}")
        try:
            await bot.set_webhook(
                webhook_url,
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=True
            )
            logger.info("Webhook set successfully.")
        except TelegramRetryAfter as e:
            logger.error(f"Error setting webhook due to rate limits: {e}. Sleeping for {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.set_webhook(webhook_url, secret_token=config.WEBHOOK_SECRET, allowed_updates=dispatcher.resolve_used_update_types(), drop_pending_updates=True)
                logger.info("Webhook set successfully after retry.")
            except Exception as e_retry:
                logger.error(f"Retry setting webhook failed: {e_retry}")
        except TelegramAPIError as e:
            logger.error(f"Telegram API error setting webhook: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during webhook setup: {e}", exc_info=True)
    else:
        logger.info("Running in polling mode, attempting to delete any existing webhook...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully (or was not set).")
        except TelegramNetworkError as e:
            logger.error(f"Network error deleting webhook: {e}")
        except TelegramAPIError as e:
            if "Webhook was not set" in str(e).lower():
                logger.info("Webhook was not set, no deletion needed.")
            else:
                logger.error(f"API error deleting webhook: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during webhook deletion: {e}", exc_info=True)

async def on_shutdown(bot: Optional[Bot]):
    logger.warning("Executing on_shutdown actions...")
    # Основне закриття сесії бота відбувається в `finally` блоці `main`
    logger.warning("Bot shutdown actions complete.")

async def main() -> None:
    logger.info("Starting main() function of the bot.")
    bot_instance: Optional[Bot] = None
    dp: Optional[Dispatcher] = None

    try:
        logger.info("Attempting database initialization...")
        db_initialized, session_factory = await initialize_database()
        if not db_initialized and config.DATABASE_URL:
            logger.critical("Database initialization failed! Check DATABASE_URL and DB availability.")
            sys.exit("Critical: Database failed to initialize.")
        elif not config.DATABASE_URL:
            logger.warning("DATABASE_URL is not set. Database features will be disabled.")
        else:
            logger.info("Database initialization successful.")

        logger.info("Initializing Aiogram components...")
        storage = MemoryStorage() # Тепер MemoryStorage визначено
        
        aio_session = AiohttpSession() 
        logger.info("AiohttpSession initialized.")

        default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
        try:
            bot_instance = Bot(
                token=config.BOT_TOKEN,
                default=default_props,
                session=aio_session,
                request_timeout=config.API_REQUEST_TIMEOUT
            )
            logger.info(f"Aiogram Bot initialized. Default request_timeout for bot methods: {config.API_REQUEST_TIMEOUT}s.")
        except Exception as e:
            logger.exception("Critical: Failed to initialize Aiogram Bot object.", exc_info=True)
            sys.exit("Critical: Bot initialization failed.")

        dp = Dispatcher(storage=storage)
        logger.info("Aiogram Dispatcher initialized.")

        if db_initialized and session_factory:
            dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory))
            logger.info("Database session middleware registered.")
        else:
            logger.warning("Database session middleware skipped (DB not initialized or factory not created).")
        
        dp.update.outer_middleware(ThrottlingMiddleware(default_rate=config.THROTTLING_RATE_DEFAULT))
        logger.info(f"Throttling middleware registered with rate: {config.THROTTLING_RATE_DEFAULT}s.")

        logger.info("Registering routers...")
        dp.include_router(settings_handlers.router)
        dp.include_router(weather_handlers.router)
        dp.include_router(weather_backup_handlers.router)
        dp.include_router(currency_handlers.router)
        dp.include_router(alert_handlers.router)
        dp.include_router(alert_backup_handlers.router)
        dp.include_router(common_handlers.router)
        logger.info("All routers registered.")

        await on_startup(bot_instance, dp, base_url=config.WEBHOOK_BASE_URL if config.RUN_WITH_WEBHOOK else None)

        if config.RUN_WITH_WEBHOOK:
            logger.warning("Starting bot in WEBHOOK mode...")
            if not config.WEBHOOK_BASE_URL:
                logger.critical("WEBHOOK_BASE_URL is not set for webhook mode!")
                sys.exit("Critical: WEBHOOK_BASE_URL not configured.")

            app = web.Application()
            app["bot"] = bot_instance 
            
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot_instance,
                secret_token=config.WEBHOOK_SECRET
            )
            webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
            logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            
            logger.info("aiohttp Application setup for webhook complete.")
            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, host=config.WEBAPP_HOST, port=config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info(f"Web server started successfully on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}.")
            logger.info("Bot is up and running in webhook mode! Waiting for updates from Telegram...")
            
            await asyncio.Event().wait() 
            logger.warning("Infinite wait loop for web server finished (UNEXPECTED!). Performing cleanup...")
            await runner.cleanup()

        else: 
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            max_polling_retries = 5
            retry_delay_polling = 5
            
            for attempt_polling in range(max_polling_retries):
                try:
                    await dp.start_polling(
                        bot_instance,
                        allowed_updates=dp.resolve_used_update_types(),
                        polling_timeout=30 
                    )
                    logger.info("Polling stopped gracefully.")
                    break 
                except (TelegramNetworkError, aiohttp.ClientConnectorError, asyncio.TimeoutError, TelegramRetryAfter) as e:
                    if isinstance(e, TelegramRetryAfter):
                        logger.error(f"Polling attempt {attempt_polling + 1}/{max_polling_retries} failed due to rate limits: {e}. Sleeping for {e.retry_after}s.")
                        await asyncio.sleep(e.retry_after)
                    else:
                        logger.error(f"Polling attempt {attempt_polling + 1}/{max_polling_retries} failed due to network/timeout error: {e}")
                    
                    if attempt_polling < max_polling_retries - 1:
                        logger.info(f"Waiting {retry_delay_polling} seconds before retrying polling...")
                        await asyncio.sleep(retry_delay_polling)
                        retry_delay_polling = min(retry_delay_polling * 2, 60)
                    else:
                        logger.critical("All polling retries failed. Stopping bot.")
                except Exception as e:
                     logger.exception(f"Unhandled exception during polling (attempt {attempt_polling + 1}): {e}", exc_info=True)
                     if attempt_polling < max_polling_retries - 1:
                         logger.info(f"Waiting {retry_delay_polling} seconds before retrying polling after unhandled exception...")
                         await asyncio.sleep(retry_delay_polling)
                     else:
                         logger.critical("Stopping bot after unhandled exception in polling.")
    except Exception as e:
        logger.critical(f"Critical error in main function before bot run loop: {e}", exc_info=True)
    finally:
        logger.warning("Closing bot session (in main finally block)...")
        if bot_instance and hasattr(bot_instance, 'session') and bot_instance.session:
            if not bot_instance.session.closed:
                 await bot_instance.session.close()
                 logger.warning("Bot aiohttp session closed.")
            else:
                 logger.info("Bot aiohttp session was already closed.")
        
        await on_shutdown(bot_instance) 
        logger.info("Exiting main() function's finally block.")