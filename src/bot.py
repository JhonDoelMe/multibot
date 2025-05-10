# src/bot.py

import asyncio
import logging
import sys
from contextlib import suppress
import aiohttp
from typing import Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web
from aiogram.types import Update # Оставим, может пригодиться для типизации в будущем
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

from src import config
from src.db.database import initialize_database
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

# Импортируем роутеры
from src.handlers import common as common_handlers # Общий роутер для команд и кнопок меню
from src.handlers.common import location_router # <<< ИМПОРТИРУЕМ location_router ИЗ common.py
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.modules.alert_backup import handlers as alert_backup_handlers
from src.modules.weather_backup import handlers as weather_backup_handlers

logger = logging.getLogger(__name__)

async def on_startup(bot: Bot, base_url: Optional[str] = None):
    logger.info("Executing on_startup actions...")
    if config.RUN_WITH_WEBHOOK:
        if not base_url:
            logger.error("Base URL for webhook is not provided on startup!")
            # В реальном приложении здесь может быть более сложная логика получения URL
        webhook_url = f"{base_url}{config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook to: {webhook_url}")
        try:
            await bot.set_webhook(
                webhook_url,
                secret_token=config.WEBHOOK_SECRET,
                allowed_updates=dp.resolve_used_update_types(), # dp должен быть определен глобально или передан
                drop_pending_updates=True
            )
            logger.info("Webhook set successfully.")
        except TelegramAPIError as e:
            logger.error(f"Error setting webhook: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during webhook setup: {e}", exc_info=True)
    else:
        logger.info("Running in polling mode, deleting potential webhook...")
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook deleted successfully.")
        except TelegramNetworkError as e:
            logger.error(f"Network error deleting webhook: {e}")
        except TelegramAPIError as e:
            logger.error(f"API error deleting webhook: {e}")
        except Exception as e:
            logger.exception(f"An unexpected error occurred during webhook deletion: {e}", exc_info=True)


async def on_shutdown(bot: Bot):
    logger.warning("Executing on_shutdown actions...")
    if config.RUN_WITH_WEBHOOK:
        logger.info("Attempting to delete webhook on shutdown...")
        try:
            await bot.delete_webhook()
            logger.info("Webhook deleted on shutdown.")
        except Exception as e:
            logger.error(f"Error deleting webhook on shutdown: {e}")
    logger.warning("Bot shutdown complete.")


async def main() -> None:
    logger.info("Starting main() function of the bot.")

    logger.info("Attempting database initialization...")
    db_initialized, session_factory = await initialize_database()
    if not db_initialized and config.DATABASE_URL:
        logger.critical("Database initialization failed despite DATABASE_URL being set! Bot cannot start without DB if it's configured.")
        sys.exit("Critical: Database failed to initialize. Check DATABASE_URL and DB availability.")
    elif not config.DATABASE_URL:
        logger.warning("DATABASE_URL is not set. Database features will be disabled.")
    else:
        logger.info("Database initialization successful.")

    logger.info("Initializing Aiogram components...")
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    
    # Инициализируем AiohttpSession без явного ClientTimeout объекта,
    # чтобы избежать TypeError при вычислении таймаута поллинга в aiogram.
    aio_session = AiohttpSession() # Переименовал, чтобы не конфликтовать с session из SQLAlchemy
    logger.info("AiohttpSession initialized without explicit ClientTimeout object.")

    try:
        # Устанавливаем request_timeout (int) для объекта Bot.
        # Этот таймаут будет использоваться для обычных API-запросов.
        bot = Bot(
            token=config.BOT_TOKEN,
            default=default_props,
            session=aio_session, # Используем созданную сессию
            request_timeout=config.API_SESSION_TOTAL_TIMEOUT
        )
        logger.info(f"Aiogram Bot initialized. Default request_timeout for bot methods: {config.API_SESSION_TOTAL_TIMEOUT}s.")
    except Exception as e:
        logger.exception("Critical: Failed to initialize Aiogram Bot object.", exc_info=True)
        sys.exit("Critical: Bot initialization failed.")

    # dp должен быть доступен в on_startup для resolve_used_update_types, если вебхук устанавливается там.
    # Сделаем dp глобальной переменной в контексте main(), чтобы on_startup мог её видеть.
    # Либо передавать dp в on_startup.
    global dp 
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
    # Сначала роутеры для конкретных модулей и состояний FSM
    dp.include_router(weather_handlers.router)
    dp.include_router(weather_backup_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(alert_backup_handlers.router)
    
    # Затем роутер для обработки геолокации (если он не конфликтует с FSM состоянием waiting_for_location)
    # Важно: location_router из common.py должен быть спроектирован так, чтобы его фильтры
    # не перехватывали сообщения F.location, предназначенные для FSM (например, WeatherBackupStates.waiting_for_location).
    # Это достигается тем, что FSM-хендлеры для F.location обычно имеют более высокий приоритет из-за фильтра по состоянию.
    dp.include_router(location_router) 

    # Общий роутер для команд (/start) и текстовых кнопок главного меню регистрируем в конце
    dp.include_router(common_handlers.router)
    logger.info("All routers registered.")

    try:
        if config.RUN_WITH_WEBHOOK:
            logger.warning("Starting bot in WEBHOOK mode...")
            base_webhook_url = config.WEBHOOK_BASE_URL
            if not base_webhook_url:
                 logger.critical("WEBHOOK_BASE_URL is not set in config, cannot start in webhook mode.")
                 sys.exit("Critical: WEBHOOK_BASE_URL not configured.")
            
            # Передаем dp в on_startup, если он там нужен для resolve_used_update_types
            # await on_startup(bot, base_webhook_url, dp) 
            # Или убедимся, что dp доступен глобально, как сейчас сделано
            await on_startup(bot, base_webhook_url)

            app = web.Application()
            app["bot"] = bot # SimpleRequestHandler может получить dp через bot, если dp был установлен в bot
            # Если dp не был установлен в bot.__dispatcher__, то передаем его явно:
            # app["dp"] = dp 

            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp, # Передаем dp явно
                bot=bot,
                secret_token=config.WEBHOOK_SECRET
            )
            webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
            logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")
            
            # setup_application(app, dp, bot=bot) # Это нужно, если SimpleRequestHandler не используется или для доп. настройки
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
            logger.warning("Infinite wait loop for web server finished (UNEXPECTED!).")
        else: # POLLING mode
            await on_startup(bot) # dp не нужен для delete_webhook
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            max_polling_retries = 5
            retry_delay_polling = 5
            for attempt_polling in range(max_polling_retries):
                try:
                    await dp.start_polling(
                        bot,
                        allowed_updates=dp.resolve_used_update_types(),
                        request_timeout=config.API_SESSION_TOTAL_TIMEOUT # Таймаут для long polling запроса
                    )
                    logger.info("Polling stopped gracefully.")
                    break 
                except (TelegramNetworkError, aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
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
    finally:
        logger.warning("Closing bot session (in main finally block)...")
        # Проверяем, что bot и его сессия существуют перед закрытием
        if 'bot' in locals() and hasattr(bot, 'session') and bot.session:
            await bot.session.close()
            logger.warning("Bot session closed.")
        
        # Передаем bot в on_shutdown, если он был создан
        await on_shutdown(bot if 'bot' in locals() else None) 
        logger.info("Exiting main() function's finally block.")