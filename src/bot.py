# src/bot.py

import asyncio
import logging
import sys
from contextlib import suppress
import aiohttp
from typing import Optional # <<< ИСПРАВЛЕНИЕ: Добавлен импорт Optional

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage # или другая реализация хранилища
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web # Для вебхука
from aiogram.types import Update # Не используется напрямую, но может быть полезно
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

from src import config
from src.db.database import initialize_database
from src.middlewares.db_session import DbSessionMiddleware
from src.middlewares.rate_limit import ThrottlingMiddleware

# Импортируем роутеры
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.modules.alert_backup import handlers as alert_backup_handlers
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

async def on_startup(bot: Bot, base_url: Optional[str] = None): # Добавлен base_url для вебхука
    logger.info("Executing on_startup actions...")
    if config.RUN_WITH_WEBHOOK:
        if not base_url:
            logger.error("Base URL for webhook is not provided on startup!")
            # Можно выбросить исключение или попытаться взять из конфига, если он там есть
            # Для Fly.io base_url обычно формируется из APP_NAME.fly.dev
            # base_url = f"https://{os.getenv('FLY_APP_NAME')}.fly.dev" # Пример для Fly.io
            # Этот URL должен быть доступен извне
            # Пока оставим как есть, предполагая что base_url передается правильно
        webhook_url = f"{base_url}{config.WEBHOOK_PATH}"
        logger.info(f"Setting webhook to: {webhook_url}")
        try:
            # Используем секретный токен из конфигурации
            await bot.set_webhook(
                webhook_url,
                secret_token=config.WEBHOOK_SECRET, # Используем новый секрет
                allowed_updates=dp.resolve_used_update_types(),
                drop_pending_updates=True # Рекомендуется удалять накопленные обновления
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
    # Здесь можно добавить логику для корректного завершения работы,
    # например, закрытие соединений, сохранение состояния и т.д.
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

    # --- DB Init ---
    logger.info("Attempting database initialization...")
    db_initialized, session_factory = await initialize_database()
    if not db_initialized and config.DATABASE_URL: # Если DATABASE_URL задан, но инициализация не удалась
        logger.critical("Database initialization failed despite DATABASE_URL being set! Bot cannot start without DB if it's configured.")
        # Можно решить, стоит ли боту работать без БД, если она ожидается.
        # Для примера, прекратим работу, если БД была сконфигурирована, но не запустилась.
        sys.exit("Critical: Database failed to initialize. Check DATABASE_URL and DB availability.")
    elif not config.DATABASE_URL:
        logger.warning("DATABASE_URL is not set. Database features will be disabled.")
    else: # db_initialized is True
        logger.info("Database initialization successful.")


    # --- Aiogram Init ---
    logger.info("Initializing Aiogram components...")
    # FSM Storage: MemoryStorage простой, но данные теряются при перезапуске.
    # Для продакшена лучше RedisStorage или другие персистентные хранилища, если FSM активно используется.
    storage = MemoryStorage()
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)

    # Настройка сессии aiohttp с таймаутами
    # Общий таймаут для всех операций в сессии
    # connect - таймаут на установку соединения
    # sock_read - таймаут на чтение данных из сокета
    # sock_connect - таймаут на соединение с сокетом (часть connect)
    timeout = aiohttp.ClientTimeout(
        total=config.API_SESSION_TOTAL_TIMEOUT,  # Общий таймаут на запрос-ответ сессии
        connect=config.API_SESSION_CONNECT_TIMEOUT # Таймаут на установку соединения
        # Можно добавить и другие: sock_connect, sock_read
    )
    session = AiohttpSession(timeout=timeout)

    try:
        bot = Bot(token=config.BOT_TOKEN, default=default_props, session=session)
        logger.info("Aiogram Bot initialized with custom session and timeouts.")
    except Exception as e:
        logger.exception("Critical: Failed to initialize Aiogram Bot object.", exc_info=True)
        sys.exit("Critical: Bot initialization failed.")

    # Объявляем dp глобально в main, чтобы on_startup мог его использовать для resolve_used_update_types
    global dp
    dp = Dispatcher(storage=storage)
    logger.info("Aiogram Dispatcher initialized.")


    # --- Register Middleware ---
    if db_initialized and session_factory: # Только если БД успешно инициализирована
        dp.update.outer_middleware(DbSessionMiddleware(session_pool=session_factory))
        logger.info("Database session middleware registered.")
    else:
        logger.warning("Database session middleware skipped (DB not initialized or factory not created).")

    # Throttling Middleware
    dp.update.outer_middleware(ThrottlingMiddleware(default_rate=config.THROTTLING_RATE_DEFAULT)) # Используем значение из конфига
    logger.info(f"Throttling middleware registered with rate: {config.THROTTLING_RATE_DEFAULT}s.")


    # --- Register Routers ---
    logger.info("Registering routers...")
    dp.include_router(common_handlers.router) # Общий лучше регистрировать первым или последним, зависит от логики
    dp.include_router(weather_handlers.router)
    dp.include_router(currency_handlers.router)
    dp.include_router(alert_handlers.router)
    dp.include_router(alert_backup_handlers.router)
    logger.info("All routers registered.")


    # --- Start Logic ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # --- Webhook Mode ---
            logger.warning("Starting bot in WEBHOOK mode...")
            # URL, на котором будет работать веб-сервер (для установки вебхука)
            # Обычно это внешний URL вашего сервера/сервиса.
            # Для Fly.io это https://your-app-name.fly.dev
            # Для локального теста с ngrok это будет URL от ngrok.
            # Важно: Этот URL должен быть доступен из интернета.
            base_webhook_url = config.WEBHOOK_BASE_URL # Должен быть задан в .env
            if not base_webhook_url:
                 logger.critical("WEBHOOK_BASE_URL is not set in config, cannot start in webhook mode.")
                 sys.exit("Critical: WEBHOOK_BASE_URL not configured.")

            await on_startup(bot, base_webhook_url) # Передаем URL для установки вебхука

            app = web.Application()
            # Передаем объект бота и диспетчера в приложение для обработчика
            app["bot"] = bot
            # app["dp"] = dp # SimpleRequestHandler сам берет dp из app["bot"].__dispatcher__ если есть, или из аргумента

            logger.info("aiohttp Application created for webhook.")
            # SimpleRequestHandler будет обрабатывать запросы от Telegram
            webhook_requests_handler = SimpleRequestHandler(
                dispatcher=dp,
                bot=bot,
                secret_token=config.WEBHOOK_SECRET # Используем новый секрет
            )
            # Регистрируем обработчик на указанный путь
            webhook_requests_handler.register(app, path=config.WEBHOOK_PATH)
            logger.info(f"Registered webhook handler at path: {config.WEBHOOK_PATH}")

            # Это альтернативный способ передать bot и dp, если SimpleRequestHandler их не находит автоматически
            # setup_application(app, dp, bot=bot)
            logger.info("aiohttp Application setup for webhook complete.")

            # Запуск веб-сервера aiohttp
            runner = web.AppRunner(app)
            await runner.setup()
            logger.info("aiohttp AppRunner setup complete.")
            site = web.TCPSite(runner, host=config.WEBAPP_HOST, port=config.WEBAPP_PORT)
            logger.info(f"Attempting to start aiohttp site on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            await site.start()
            logger.info(f"Web server started successfully on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}.")
            logger.info("Bot is up and running in webhook mode! Waiting for updates from Telegram...")
            await asyncio.Event().wait() # Бесконечное ожидание для веб-сервера
            logger.warning("Infinite wait loop for web server finished (UNEXPECTED!).")

        else:
            # --- Polling Mode ---
            await on_startup(bot) # Вызываем on_startup без base_url
            logger.warning("Starting bot in POLLING mode...")
            logger.info("Starting polling...")
            max_polling_retries = 5
            retry_delay_polling = 5 # секунд

            for attempt_polling in range(max_polling_retries):
                try:
                    await dp.start_polling(
                        bot,
                        allowed_updates=dp.resolve_used_update_types(),
                        # Таймаут для поллинга можно оставить по умолчанию или настроить
                        # timeout=30
                    )
                    # Если start_polling завершился без исключений (например, Ctrl+C), выходим из цикла
                    logger.info("Polling stopped gracefully.")
                    break
                except (TelegramNetworkError, aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                    logger.error(f"Polling attempt {attempt_polling + 1}/{max_polling_retries} failed due to network/timeout error: {e}")
                    if attempt_polling < max_polling_retries - 1:
                        logger.info(f"Waiting {retry_delay_polling} seconds before retrying polling...")
                        await asyncio.sleep(retry_delay_polling)
                        retry_delay_polling = min(retry_delay_polling * 2, 60) # Увеличиваем задержку, но не более минуты
                    else:
                        logger.critical("All polling retries failed. Stopping bot.")
                        # Можно добавить отправку уведомления администратору здесь
                except Exception as e:
                     logger.exception(f"Unhandled exception during polling (attempt {attempt_polling + 1}): {e}", exc_info=True)
                     if attempt_polling < max_polling_retries - 1:
                          logger.info(f"Waiting {retry_delay_polling} seconds before retrying polling after unhandled exception...")
                          await asyncio.sleep(retry_delay_polling)
                     else:
                          logger.critical("Stopping bot after unhandled exception in polling.")
    finally:
        logger.warning("Closing bot session (in main finally block)...")
        if 'bot' in locals() and bot.session: # Убедимся что bot был создан и сессия существует
            await bot.session.close()
            logger.warning("Bot session closed.")
        await on_shutdown(bot if 'bot' in locals() else None) # Передаем bot, если он был создан
        logger.info("Exiting main() function's finally block.")