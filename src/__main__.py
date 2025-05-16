# src/__main__.py

import asyncio
import logging
import logging.handlers
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
    from src import config as app_config # Даємо псевдонім
    app_config.log_config_status() 
except ImportError:
    logger.critical("Failed to import src.config. Critical error, cannot continue.", exc_info=True)
    sys.exit("Critical: src.config import failed.")
except Exception as e:
    logger.critical(f"An unexpected error occurred during config import or its logging: {e}", exc_info=True)
    sys.exit("Critical: Unexpected error with config loading/logging.")


# --- Ініціалізація Sentry/GlitchTip ---
if app_config.SENTRY_DSN: # SENTRY_DSN тепер може містити значення з GLITCHTIP_DSN
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
            # ВИКОРИСТОВУЄМО НОВІ ЗМІННІ З КОНФІГУРАЦІЇ
            environment=app_config.BOT_ENVIRONMENT, 
            release=app_config.BOT_VERSION,
            # send_default_pii=False, # За замовчуванням False
        )
        logger.info(f"Sentry/GlitchTip SDK initialized successfully. Environment: {app_config.BOT_ENVIRONMENT}, Version: {app_config.BOT_VERSION}")
    except ImportError:
        logger.warning("sentry-sdk not installed. Sentry/GlitchTip integration skipped.")
    except Exception as e:
        logger.exception("Failed to initialize Sentry/GlitchTip SDK.", exc_info=True)
else:
    logger.info("SENTRY_DSN (or GLITCHTIP_DSN) not found in config. Sentry/GlitchTip integration skipped.")


# --- Налаштування aiocache ---
# ... (код aiocache залишається без змін, оскільки нові змінні його не стосуються) ...
if app_config.CACHE_BACKEND in ["memory", "redis"]:
    try:
        from aiocache import caches, Cache
        from aiocache.serializers import JsonSerializer

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
    logger.info(f"Unsupported CACHE_BACKEND value: '{app_config.CACHE_BACKEND}'. Caching will be disabled.")

# --- Імпорт та запуск бота ---
try:
    from src.bot import main as run_bot
except ImportError as e_bot_import:
     logger.critical("Failed to import src.bot.main.", exc_info=e_bot_import)
     sys.exit("Critical: Failed to import core bot module.")
except Exception as e_bot_module: 
     logger.critical("An unexpected error occurred during 'src.bot' module import.", exc_info=e_bot_module)
     sys.exit("Critical: Unexpected error during bot module import.")


if __name__ == "__main__":
    logger.info(f"Initializing application via __main__.py (PID: {os.getpid()}). Timestamp: {datetime.now()}")
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit) as e:
        logger.warning(f"Bot stopped by {type(e).__name__}.")
        if app_config.SENTRY_DSN and 'sentry_sdk' in sys.modules and hasattr(sentry_sdk, 'Hub') and sentry_sdk.Hub.current.client:
            logger.info("Flushing Sentry/GlitchTip events before exit...")
            sentry_sdk.flush(timeout=3.0)
            logger.info("Sentry/GlitchTip flush complete.")
    except Exception as e_top_level:
        logger.critical("Unhandled exception at the top level of asyncio.run.", exc_info=e_top_level)
        if app_config.SENTRY_DSN and 'sentry_sdk' in sys.modules and hasattr(sentry_sdk, 'Hub') and sentry_sdk.Hub.current.client:
            sentry_sdk.capture_exception(e_top_level)
            sentry_sdk.flush(timeout=5.0)
    finally:
        logger.info("Application shutdown sequence initiated in __main__ finally block.")
        logging.shutdown()
        print(f"[{datetime.now()}] Application shutdown complete from __main__.py.", file=sys.stderr)