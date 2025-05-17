# src/bot.py

import asyncio
import logging
import sys
import aiohttp 
from typing import Optional, Union 

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web 
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramRetryAfter

from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
import redis 
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession 

from src import config as app_config 
from src.db.database import initialize_database 
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

from src.handlers import common as common_handlers
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.modules.alert_backup import handlers as alert_backup_handlers
from src.modules.weather_backup import handlers as weather_backup_handlers
from src.modules.settings import handlers as settings_handlers

logger = logging.getLogger(__name__)

async def on_bot_startup(bot: Bot, dispatcher: Dispatcher, base_url: Optional[str] = None):
    logger.info("Executing on_bot_startup actions...")
    if app_config.RUN_WITH_WEBHOOK:
        if not base_url:
            logger.error("Base URL for webhook is not provided on startup! Cannot set webhook.")
            return
        webhook_url = f"{base_url.rstrip('/')}{app_config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook to: {webhook_url}")
        try:
            await bot.set_webhook(
                webhook_url,
                secret_token=app_config.WEBHOOK_SECRET,
                allowed_updates=dispatcher.resolve_used_update_types(),
                drop_pending_updates=True
            )
            logger.info("Webhook set successfully.")
        except TelegramRetryAfter as e:
            logger.error(f"Error setting webhook due to rate limits: {e}. Sleeping for {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
            try:
                await bot.set_webhook(webhook_url, secret_token=app_config.WEBHOOK_SECRET, allowed_updates=dispatcher.resolve_used_update_types(), drop_pending_updates=True)
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

async def on_bot_shutdown(bot: Optional[Bot], fsm_storage_instance: Optional[Union[MemoryStorage, RedisStorage]] = None):
    logger.warning("Executing on_bot_shutdown actions...")
    if bot and bot.session: 
         if hasattr(bot.session, 'closed') and not bot.session.closed:
            try:
                await bot.session.close()
                logger.warning("Bot aiohttp session closed by on_bot_shutdown.")
            except Exception as e_close:
                logger.error(f"Error closing bot aiohttp session in on_bot_shutdown: {e_close}")
         elif not hasattr(bot.session, 'closed'): 
            try:
                await bot.session.close()
                logger.warning("Bot aiohttp session closed by on_bot_shutdown (no .closed check).")
            except Exception as e_close:
                logger.error(f"Error closing bot aiohttp session in on_bot_shutdown (no .closed attr): {e_close}")
    
    if isinstance(fsm_storage_instance, RedisStorage):
        if hasattr(fsm_storage_instance, 'redis') and fsm_storage_instance.redis:
            logger.info("Attempting to close Redis connection for FSM storage...")
            try:
                await fsm_storage_instance.close()
                logger.info("Redis connection for FSM storage closed successfully.")
            except Exception as e_redis_close:
                logger.error(f"Error closing Redis connection for FSM: {e_redis_close}")
        else:
            logger.info("RedisStorage instance found, but no active Redis connection to close (or 'redis' attribute missing).")
    logger.warning("Bot shutdown actions complete.")

async def create_bot_dispatcher_and_fsm_storage(session_factory_param: Optional[async_sessionmaker[AsyncSession]]) -> tuple[Optional[Bot], Optional[Dispatcher], Optional[Union[MemoryStorage, RedisStorage]], Optional[AiohttpSession]]:
    fsm_storage: Optional[Union[MemoryStorage, RedisStorage]] = None
    if app_config.FSM_STORAGE_TYPE == "redis":
        if app_config.FSM_REDIS_URL:
            try:
                temp_redis_storage = RedisStorage.from_url(app_config.FSM_REDIS_URL)
                if hasattr(temp_redis_storage, 'redis') and temp_redis_storage.redis:
                    await temp_redis_storage.redis.ping()
                fsm_storage = temp_redis_storage
                logger.info(f"Successfully connected to Redis for FSM states (URL: {app_config.FSM_REDIS_URL}). Using RedisStorage.")
            except redis.exceptions.ConnectionError as e_conn:
                logger.warning(f"Could not connect to Redis for FSM storage (URL: {app_config.FSM_REDIS_URL}): {e_conn}. Falling back to MemoryStorage.")
                fsm_storage = MemoryStorage()
            except Exception as e_redis_other:
                logger.error(f"Unexpected error during RedisStorage init: {e_redis_other}. Falling back to MemoryStorage.", exc_info=True)
                fsm_storage = MemoryStorage()
        else:
            logger.warning("FSM_STORAGE_TYPE is 'redis' but FSM_REDIS_URL is not set. Falling back to MemoryStorage.")
            fsm_storage = MemoryStorage()

    if fsm_storage is None:
        fsm_storage = MemoryStorage()
        logger.info("Using MemoryStorage for FSM states.")

    aio_session = AiohttpSession()
    logger.info("AiohttpSession initialized for bot.")

    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot_instance = Bot(
        token=app_config.BOT_TOKEN,
        default=default_props,
        session=aio_session,
        request_timeout=app_config.API_REQUEST_TIMEOUT
    )
    logger.info(f"Aiogram Bot object initialized. Default request_timeout: {app_config.API_REQUEST_TIMEOUT}s.")

    dp = Dispatcher(storage=fsm_storage)
    logger.info(f"Aiogram Dispatcher initialized with storage: {type(fsm_storage).__name__}.")

    if session_factory_param: 
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory_param))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("session_factory_param is None. Skipping DB middleware.")

    dp.update.outer_middleware(ThrottlingMiddleware(default_rate=app_config.THROTTLING_RATE_DEFAULT))
    logger.info(f"Throttling middleware registered with rate: {app_config.THROTTLING_RATE_DEFAULT}s.")

    logger.info("Registering routers...")
    dp.include_router(settings_handlers.router)
    dp.include_router(weather_handlers.router)
    dp.include_router(weather_backup_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(alert_backup_handlers.router)
    dp.include_router(common_handlers.router)
    logger.info("All routers registered.")

    return bot_instance, dp, fsm_storage, aio_session

async def get_aiohttp_app() -> web.Application:
    logger.info("get_aiohttp_app: Initializing database...")
    db_initialized, session_factory = await initialize_database()
    if not db_initialized and app_config.DATABASE_URL:
        logger.critical("Database initialization failed!")
        raise RuntimeError("Database init failed")

    bot, dp, fsm_storage, _ = await create_bot_dispatcher_and_fsm_storage(session_factory_param=session_factory)
    if not bot or not dp:
        logger.critical("Bot or Dispatcher init failed.")
        raise RuntimeError("Bot init failed")

    async def startup_callback():
        await on_bot_startup(bot, dp, base_url=app_config.WEBHOOK_BASE_URL)

    async def shutdown_callback():
        await on_bot_shutdown(bot, fsm_storage_instance=fsm_storage)

    dp.startup.register(startup_callback)
    dp.shutdown.register(shutdown_callback)

    app = web.Application()
    app['bot_instance'] = bot
    app['dispatcher'] = dp
    app['fsm_storage'] = fsm_storage

    setup_application(app, dp, bot=bot)
    logger.info(f"Webhook handler registered at: {app_config.WEBHOOK_PATH}")
    return app

async def main_polling():
    logger.info("main_polling: Initializing database...")
    db_initialized, session_factory = await initialize_database()
    if not db_initialized and app_config.DATABASE_URL:
        logger.critical("Polling mode: database init failed")
        return

    bot, dp, fsm_storage, aio_session = await create_bot_dispatcher_and_fsm_storage(session_factory_param=session_factory)

    if not bot or not dp:
        logger.critical("Polling mode: Bot or Dispatcher init failed")
        return

    try:
        await on_bot_startup(bot, dp)
        logger.warning("Starting bot in POLLING mode...")
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            polling_timeout=30
        )
    except Exception as e:
        logger.critical(f"Critical error in polling: {e}", exc_info=True)
    finally:
        logger.warning("Polling: shutting down...")
        await on_bot_shutdown(bot, fsm_storage_instance=fsm_storage)
        if aio_session and hasattr(aio_session, 'closed') and not aio_session.closed:
            await aio_session.close()

async def main():
    if app_config.RUN_WITH_WEBHOOK:
        logger.warning("main(): running in WEBHOOK mode")
        app = await get_aiohttp_app()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, host=app_config.WEBAPP_HOST, port=app_config.WEBAPP_PORT)
        try:
            await site.start()
            logger.info(f"aiohttp server started at {app_config.WEBAPP_HOST}:{app_config.WEBAPP_PORT}")
            await asyncio.Event().wait()
        except Exception as e:
            logger.critical(f"aiohttp server error: {e}", exc_info=True)
        finally:
            await runner.cleanup()
    else:
        await main_polling()
