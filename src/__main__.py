# src/__main__.py

import asyncio
import logging
import logging.handlers
import sys
import os

# --- Настройка логирования (остается как было) ---
LOG_FILENAME = "bot.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 5
log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
file_handler = logging.handlers.RotatingFileHandler(
    filename=LOG_FILENAME,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO)
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)
# --- Конец настройки логирования ---

logger = logging.getLogger(__name__)
logger.info("Logging configured!") # Логгер уже настроен

# --- Инициализация Sentry ---
try:
    # Импортируем Sentry и конфиг ПОСЛЕ настройки логгера
    import sentry_sdk
    from sentry_sdk.integrations.aiohttp import AioHttpIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    from src import config # Импортируем конфиг здесь

    if config.SENTRY_DSN:
        logger.info("Attempting to initialize Sentry SDK...")
        sentry_sdk.init(
            dsn=config.SENTRY_DSN,
            # Включаем интеграции для большего контекста
            integrations=[
                AioHttpIntegration(),
                SqlalchemyIntegration(),
            ],
            # Уровень выборки трассировок (для Performance Monitoring, можно начать с 0)
            traces_sample_rate=0.1,
            # Отправлять ли данные, которые могут быть личными (IP, User ID)?
            # Если да, Sentry может автоматически связывать ошибки с пользователями.
            # Оцените риски согласно вашей политике конфиденциальности.
            # send_default_pii=True,
        )
        logger.info("Sentry SDK initialized successfully.")
    else:
        logger.info("Sentry DSN not found, skipping Sentry initialization.")

except ImportError:
    logger.error("sentry-sdk not installed. Sentry integration skipped.")
except Exception as e:
    logger.exception(f"Failed to initialize Sentry SDK: {e}", exc_info=True)
# --- Конец инициализации Sentry ---

# --- Настройка aiocache ---
try:
    from aiocache import caches
    logger.info("Initializing aiocache...")
    caches.set_config({
        "default": {
            "cache": "aiocache.SimpleMemoryCache" if config.CACHE_BACKEND == "memory" else "aiocache.RedisCache",
            "endpoint": config.CACHE_REDIS_URL.split("://")[1].split(":")[0] if config.CACHE_BACKEND == "redis" else None,
            "port": int(config.CACHE_REDIS_URL.split(":")[-1].split("/")[0]) if config.CACHE_BACKEND == "redis" else None,
            "db": int(config.CACHE_REDIS_URL.split("/")[-1]) if config.CACHE_BACKEND == "redis" else None,
        }
    })
    logger.info("aiocache initialized successfully.")
except ImportError:
    logger.error("aiocache not installed. Caching will be disabled.", exc_info=True)
except Exception as e:
    logger.error(f"Failed to initialize aiocache: {e}", exc_info=True)
# --- Конец настройки aiocache ---

# --- Импорт и запуск бота ---
# Импортируем main ПОСЛЕ инициализации Sentry
try:
    from src.bot import main
except ImportError as e:
     logger.critical(f"Failed to import src.bot.main: {e}", exc_info=True)
     sys.exit("Critical: Failed to import core bot module.")
except Exception as e:
     logger.critical(f"An unexpected error occurred during initial imports: {e}", exc_info=True)
     sys.exit("Critical: Unexpected error during imports.")

if __name__ == "__main__":
    logger.info("Initializing application via __main__.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user or system exit.")
    except Exception as e:
        # Sentry должен автоматически перехватить это исключение, если он инициализирован
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown sequence initiated.")
        logging.shutdown()
        logger.info("Application shutdown complete.")