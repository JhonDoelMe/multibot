# src/__main__.py

import asyncio
import logging
import logging.handlers # Для RotatingFileHandler
import sys
import os
from datetime import datetime

# --- Налаштування логування (має бути однією з перших операцій) ---
LOG_FILENAME = os.getenv("LOG_FILENAME", "bot.log")
LOG_LEVEL_CONSOLE_STR = os.getenv("LOG_LEVEL_CONSOLE", "INFO").upper()
LOG_LEVEL_FILE_STR = os.getenv("LOG_LEVEL_FILE", "INFO").upper()
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 10 * 1024 * 1024))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

LOG_LEVEL_CONSOLE = getattr(logging, LOG_LEVEL_CONSOLE_STR, logging.INFO)
LOG_LEVEL_FILE = getattr(logging, LOG_LEVEL_FILE_STR, logging.INFO)

log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s'
)

root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG) 

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(LOG_LEVEL_CONSOLE)
root_logger.addHandler(stream_handler)

try:
    log_dir = os.path.dirname(LOG_FILENAME)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
        print(f"Log directory created: {log_dir}", file=sys.stderr)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_FILENAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(LOG_LEVEL_FILE)
    root_logger.addHandler(file_handler)
except Exception as e:
    print(f"CRITICAL: Failed to initialize file logger for '{LOG_FILENAME}': {e}", file=sys.stderr)

logger = logging.getLogger(__name__)
logger.info("Logging configured!")
logger.debug(f"Console log level set to: {logging.getLevelName(LOG_LEVEL_CONSOLE)}")
logger.debug(f"File log level set to: {logging.getLevelName(LOG_LEVEL_FILE)}")
logger.debug(f"Log filename: {LOG_FILENAME}, Max bytes: {LOG_MAX_BYTES}, Backup count: {LOG_BACKUP_COUNT}")


# --- Імпорт конфігурації ---
try:
    from src import config as app_config 
    app_config.log_config_status() 
except ImportError:
    logger.critical("Failed to import src.config. Critical error, cannot continue.", exc_info=True)
    sys.exit("Critical: src.config import failed.")
except Exception as e:
    logger.critical(f"An unexpected error occurred during config import or its logging: {e}", exc_info=True)
    sys.exit("Critical: Unexpected error with config loading/logging.")


# --- Ініціалізація Sentry/GlitchTip ---
if app_config.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration as SentryLoggingIntegration
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        sentry_logging_integration = SentryLoggingIntegration(
            level=logging.INFO, 
            event_level=logging.ERROR 
        )

        sentry_sdk.init(
            dsn=app_config.SENTRY_DSN,
            integrations=[
                AioHttpIntegration(),
                SqlalchemyIntegration(),
                sentry_logging_integration,
                AsyncioIntegration(),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.2)),
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", 0.2)),
            environment=app_config.BOT_ENVIRONMENT, 
            release=app_config.BOT_VERSION,
        )
        logger.info(f"Sentry/GlitchTip SDK initialized successfully. Environment: {app_config.BOT_ENVIRONMENT}, Version: {app_config.BOT_VERSION}")
    except ImportError:
        logger.warning("sentry-sdk not installed. Sentry/GlitchTip integration skipped.")
    except Exception as e:
        logger.exception("Failed to initialize Sentry/GlitchTip SDK.", exc_info=True)
else:
    logger.info("SENTRY_DSN (or GLITCHTIP_DSN) not found in config. Sentry/GlitchTip integration skipped.")


# --- Налаштування aiocache ---
if app_config.CACHE_BACKEND in ["memory", "redis"]:
    try:
        from aiocache import caches
        
        cache_config_dict = {
            'default': {
                'cache': "aiocache.SimpleMemoryCache" if app_config.CACHE_BACKEND == "memory" else "aiocache.RedisCache",
                'serializer': {'class': 'aiocache.serializers.JsonSerializer'},
                'timeout': 60*5 
            }
        }
        if app_config.CACHE_BACKEND == "redis":
            if not app_config.CACHE_REDIS_URL:
                logger.error("CACHE_BACKEND is 'redis' but CACHE_REDIS_URL is not set. Redis cache will be unavailable.")
                cache_config_dict['default']['cache'] = "aiocache.SimpleMemoryCache"
                logger.warning("Falling back to memory cache due to missing CACHE_REDIS_URL.")
            else:
                from urllib.parse import urlparse
                redis_url_parsed = urlparse(app_config.CACHE_REDIS_URL)
                cache_config_dict['default'].update({
                    'endpoint': redis_url_parsed.hostname or 'localhost',
                    'port': redis_url_parsed.port or 6379,
                    'password': redis_url_parsed.password,
                    'db': int(redis_url_parsed.path.lstrip('/') or 0)
                })
        
        caches.set_config(cache_config_dict)
        logger.info(f"aiocache initialized with backend: {cache_config_dict['default']['cache']}.")
        
    except ImportError:
        logger.error("aiocache or its dependencies not installed. Caching will be disabled.", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to initialize aiocache: {e}", exc_info=True)
else:
    logger.info(f"Unsupported CACHE_BACKEND value: '{app_config.CACHE_BACKEND}'. Caching disabled.")

# --- Функція для запуску окремих завдань ---
async def main_task_runner(task_name: str):
    logger.info(f"Task Runner: Starting task '{task_name}'...")

    from src.db.database import initialize_database
    db_initialized, session_factory = await initialize_database()
    if not db_initialized or not session_factory:
        logger.critical(f"Task Runner '{task_name}': Database could not be initialized. Exiting task.")
        return

    # ВИПРАВЛЕНО: Імпорт DefaultBotProperties
    from aiogram import Bot
    from aiogram.client.bot import DefaultBotProperties # <--- ПРАВИЛЬНИЙ ІМПОРТ
    from aiogram.enums import ParseMode
    from aiogram.client.session.aiohttp import AiohttpSession
    
    bot_session = None
    bot_instance = None
    try:
        bot_session = AiohttpSession()
        # Переконуємося, що app_config доступний тут
        # Якщо main_task_runner викликається з __main__, app_config вже має бути завантажений
        bot_instance = Bot(
            token=app_config.BOT_TOKEN, # Використовуємо app_config
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            session=bot_session
        )
        logger.info(f"Task Runner '{task_name}': Bot instance initialized.")

        if task_name == "process_weather_reminders":
            from src.scheduler_tasks import send_weather_reminders_task
            await send_weather_reminders_task(session_factory, bot_instance)
        else:
            logger.error(f"Task Runner: Unknown task name '{task_name}'. Nothing to run.")

    except Exception as e_task:
        logger.exception(f"Task Runner '{task_name}': An error occurred during task execution.", exc_info=e_task)
    finally:
        if bot_instance and bot_instance.session: 
            if hasattr(bot_instance.session, 'closed') and not bot_instance.session.closed:
                await bot_instance.session.close()
                logger.info(f"Task Runner '{task_name}': Bot session closed.")
            elif not hasattr(bot_instance.session, 'closed'):
                await bot_instance.session.close()
                logger.info(f"Task Runner '{task_name}': Bot session closed (no .closed check).")
        logger.info(f"Task Runner: Task '{task_name}' finished.")


# --- Точка входу програми ---
if __name__ == "__main__":
    task_to_run = None
    if len(sys.argv) > 1:
        for arg in sys.argv[1:]:
            if arg.startswith('--task='):
                task_to_run = arg.split('=', 1)[1]
                break
    
    if task_to_run:
        logger.info(f"Received request to run specific task: {task_to_run}")
        asyncio.run(main_task_runner(task_to_run))
    else:
        logger.info(f"Initializing application (main bot) via __main__.py (PID: {os.getpid()}). Timestamp: {datetime.now()}")
        try:
            from src.bot import main as run_bot 
            asyncio.run(run_bot())
        except ImportError as e_bot_import:
            logger.critical("Failed to import src.bot.main for main bot run.", exc_info=e_bot_import)
            sys.exit("Critical: Failed to import core bot module for main run.")
        except Exception as e_bot_module: 
            logger.critical("An unexpected error occurred during 'src.bot' module import for main bot run.", exc_info=e_bot_module)
            sys.exit("Critical: Unexpected error during bot module import for main run.")
        except (KeyboardInterrupt, SystemExit) as e_interrupt:
            logger.warning(f"Main bot run stopped by {type(e_interrupt).__name__}.")
            if app_config.SENTRY_DSN and 'sentry_sdk' in sys.modules and hasattr(sentry_sdk, 'Hub') and sentry_sdk.Hub.current.client:
                logger.info("Flushing Sentry/GlitchTip events before exit (from main bot interrupt)...")
                sentry_sdk.flush(timeout=3.0)
                logger.info("Sentry/GlitchTip flush complete (from main bot interrupt).")
        except Exception as e_top_level:
            logger.critical("Unhandled exception at the top level of main bot asyncio.run.", exc_info=e_top_level)
            if app_config.SENTRY_DSN and 'sentry_sdk' in sys.modules and hasattr(sentry_sdk, 'Hub') and sentry_sdk.Hub.current.client:
                sentry_sdk.capture_exception(e_top_level)
                sentry_sdk.flush(timeout=5.0)
        finally:
            if not task_to_run:
                logger.info("Main bot application shutdown sequence initiated in __main__ finally block.")
    
    logging.shutdown()
    print(f"[{datetime.now()}] Application __main__.py finished.", file=sys.stderr)

