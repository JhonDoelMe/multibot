# src/bot.py

import asyncio
import logging
import sys
import aiohttp # Потрібен для web.Application та ClientTimeout
from typing import Optional, Union # Union потрібен для fsm_storage

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.webhook.aiohttp_server import SimpleRequestHandler
from aiohttp import web # Потрібен для web.Application
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError, TelegramRetryAfter

# Сховища FSM
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
# from aiogram.fsm.storage.redis import DefaultKeyBuilder as RedisKeyBuilder # Якщо потрібен кастомний префікс

from src import config as app_config # Використовуємо псевдонім
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

async def on_shutdown(bot: Optional[Bot], fsm_storage_instance: Optional[Union[MemoryStorage, RedisStorage]] = None):
    logger.warning("Executing on_shutdown actions...")
    # Закриття сесії бота відбувається в `finally` блоці `main`
    
    # Закриваємо з'єднання з Redis для FSM, якщо воно використовувалося
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

async def main() -> None:
    logger.info("Starting main() function of the bot.")
    bot_instance: Optional[Bot] = None
    dp: Optional[Dispatcher] = None
    aio_session: Optional[AiohttpSession] = None
    fsm_storage: Optional[Union[MemoryStorage, RedisStorage]] = None 

    try:
        logger.info("Attempting database initialization...")
        db_initialized, session_factory = await initialize_database()
        if not db_initialized and app_config.DATABASE_URL:
            logger.critical("Database initialization failed! Check DATABASE_URL and DB availability.")
            sys.exit("Critical: Database failed to initialize.")
        elif not app_config.DATABASE_URL:
            logger.warning("DATABASE_URL is not set. Database features will be disabled.")
        else:
            logger.info("Database initialization successful.")

        logger.info("Initializing Aiogram components...")
        
        # --- Налаштування сховища FSM ---
        if app_config.FSM_STORAGE_TYPE == "redis":
            if app_config.FSM_REDIS_URL:
                try:
                    # from redis.asyncio import Redis # Можна імпортувати, якщо потрібен сам клієнт
                    # redis_client = Redis.from_url(app_config.FSM_REDIS_URL)
                    # fsm_storage = RedisStorage(redis=redis_client)
                    # Або простіше через from_url самого RedisStorage:
                    fsm_storage = RedisStorage.from_url(app_config.FSM_REDIS_URL)
                    
                    # Спроба перевірити з'єднання (опціонально, але корисно для відладки)
                    # Це потребує, щоб `fsm_storage.redis` був доступний і мав метод `ping`
                    if hasattr(fsm_storage, 'redis') and fsm_storage.redis:
                        await fsm_storage.redis.ping() # Тестовий запит до Redis
                        logger.info(f"Successfully connected to Redis for FSM states (URL: {app_config.FSM_REDIS_URL}). Using RedisStorage.")
                    else: # Якщо ping неможливий, але сховище створено
                        logger.info(f"Using RedisStorage for FSM states (URL: {app_config.FSM_REDIS_URL}). Ping check skipped or 'redis' attribute not available on storage.")

                except ConnectionRefusedError as e_redis_conn:
                    logger.error(f"Redis connection refused for FSM storage (URL: {app_config.FSM_REDIS_URL}): {e_redis_conn}. Falling back to MemoryStorage.")
                    fsm_storage = MemoryStorage()
                except Exception as e_redis: # Будь-які інші помилки при ініціалізації RedisStorage
                    logger.exception(f"Failed to initialize RedisStorage (URL: {app_config.FSM_REDIS_URL}): {e_redis}. Falling back to MemoryStorage.", exc_info=True)
                    fsm_storage = MemoryStorage()
            else:
                logger.warning("FSM_STORAGE_TYPE is 'redis' but FSM_REDIS_URL is not set. Falling back to MemoryStorage.")
                fsm_storage = MemoryStorage()
        else: 
            fsm_storage = MemoryStorage()
            logger.info("Using MemoryStorage for FSM states.")
        
        aio_session = AiohttpSession() 
        logger.info("AiohttpSession initialized.")

        default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
        try:
            bot_instance = Bot(
                token=app_config.BOT_TOKEN,
                default=default_props,
                session=aio_session,
                request_timeout=app_config.API_REQUEST_TIMEOUT
            )
            logger.info(f"Aiogram Bot initialized. Default request_timeout for bot methods: {app_config.API_REQUEST_TIMEOUT}s.")
        except Exception as e:
            logger.exception("Critical: Failed to initialize Aiogram Bot object.", exc_info=True)
            if aio_session and hasattr(aio_session, 'closed') and not aio_session.closed: await aio_session.close()
            if isinstance(fsm_storage, RedisStorage) and hasattr(fsm_storage, 'redis') and fsm_storage.redis: await fsm_storage.close()
            sys.exit("Critical: Bot initialization failed.")

        dp = Dispatcher(storage=fsm_storage)
        logger.info(f"Aiogram Dispatcher initialized with storage: {type(fsm_storage).__name__}.")

        if db_initialized and session_factory:
            dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory))
            logger.info("Database session middleware registered.")
        else:
            logger.warning("Database session middleware skipped (DB not initialized or factory not created).")
        
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

        if not bot_instance or not dp:
            logger.critical("Bot instance or Dispatcher is not initialized before on_startup. Exiting.")
            if aio_session and hasattr(aio_session, 'closed') and not aio_session.closed: await aio_session.close()
            if isinstance(fsm_storage, RedisStorage) and hasattr(fsm_storage, 'redis') and fsm_storage.redis: await fsm_storage.close()
            sys.exit("Critical: Bot/Dispatcher not initialized.")

        await on_startup(bot_instance, dp, base_url=app_config.WEBHOOK_BASE_URL if app_config.RUN_WITH_WEBHOOK else None)

        if app_config.RUN_WITH_WEBHOOK:
            logger.warning("Starting bot in WEBHOOK mode...")
            if not app_config.WEBHOOK_BASE_URL:
                logger.critical("WEBHOOK_BASE_URL is not set for webhook mode!")
                if aio_session and hasattr(aio_session, 'closed') and not aio_session.closed: await aio_session.close()
                if isinstance(fsm_storage, RedisStorage) and hasattr(fsm_storage, 'redis') and fsm_storage.redis: await fsm_storage.close()
                sys.exit("Critical: WEBHOOK_BASE_URL not configured.")

            app = web.Application()
            app["bot"] = bot_instance 
            
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot_instance,
                secret_token=app_config.WEBHOOK_SECRET
            )
            webhook_requests_handler.register(app, path=app_config.WEBHOOK_PATH)
            logger.info(f"Registered webhook handler at path: {app_config.WEBHOOK_PATH}")
            
            logger.info("aiohttp Application setup for webhook complete.")
            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, host=app_config.WEBAPP_HOST, port=app_config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {app_config.WEBAPP_HOST}:{app_config.WEBAPP_PORT}...")
            await site.start()
            logger.info(f"Web server started successfully on {app_config.WEBAPP_HOST}:{app_config.WEBAPP_PORT}.")
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
                    if not bot_instance or not dp:
                         logger.critical("Bot instance or Dispatcher is not available for polling. Exiting.")
                         if aio_session and hasattr(aio_session, 'closed') and not aio_session.closed: await aio_session.close()
                         if isinstance(fsm_storage, RedisStorage) and hasattr(fsm_storage, 'redis') and fsm_storage.redis: await fsm_storage.close()
                         sys.exit("Critical: Bot/Dispatcher not available for polling.")

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
        logger.warning("Closing bot session and FSM storage (in main finally block)...")
        if aio_session:
            if hasattr(aio_session, 'closed') and not aio_session.closed:
                 try:
                     await aio_session.close()
                     logger.warning("Bot aiohttp session closed.")
                 except Exception as e_close:
                     logger.error(f"Error closing aiohttp session: {e_close}")
            elif not hasattr(aio_session, 'closed'):
                try:
                    await aio_session.close()
                    logger.warning("Bot aiohttp session closed (no .closed attribute check).")
                except Exception as e_close:
                    logger.error(f"Error closing aiohttp session (no .closed attr): {e_close}")
            else: 
                 logger.info("Bot aiohttp session was already closed.")
        
        # Передаємо fsm_storage в on_shutdown для коректного закриття
        await on_shutdown(bot_instance, fsm_storage_instance=fsm_storage) 
        logger.info("Exiting main() function's finally block.")