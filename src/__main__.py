# src/__main__.py

import asyncio
import logging
import logging.handlers # Для RotatingFileHandler
import sys
import os # Для переменных окружения, если понадобятся здесь

# --- Настройка логирования (должна быть одной из первых операций) ---
LOG_FILENAME = os.getenv("LOG_FILENAME", "bot.log") # Имя файла логов из переменной или по умолчанию
LOG_LEVEL_CONSOLE = os.getenv("LOG_LEVEL_CONSOLE", "INFO").upper()
LOG_LEVEL_FILE = os.getenv("LOG_LEVEL_FILE", "INFO").upper()
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", 5 * 1024 * 1024)) # 5 MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", 5))

# Форматтер можно определить один раз
log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s' # Добавлен модуль и номер строки
)

# Корневой логгер
root_logger = logging.getLogger()
root_logger.setLevel(logging.DEBUG) # Устанавливаем самый низкий уровень для корневого, фильтрация на уровне хендлеров

# Обработчик для вывода в консоль (StreamHandler)
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
try:
    stream_handler.setLevel(getattr(logging, LOG_LEVEL_CONSOLE))
except AttributeError:
    stream_handler.setLevel(logging.INFO) # Уровень по умолчанию, если в переменной ошибка
root_logger.addHandler(stream_handler)

# Обработчик для записи в файл (RotatingFileHandler)
try:
    file_handler = logging.handlers.RotatingFileHandler(
        filename=LOG_FILENAME,
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding='utf-8'
    )
    file_handler.setFormatter(log_formatter)
    try:
        file_handler.setLevel(getattr(logging, LOG_LEVEL_FILE))
    except AttributeError:
        file_handler.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
except Exception as e:
    # Если не удалось настроить файловый логгер, сообщаем в консоль
    root_logger.error(f"Failed to initialize file logger: {e}", exc_info=True)


# Логируем факт успешной настройки (или проблем)
logger = logging.getLogger(__name__) # Получаем логгер для текущего модуля
logger.info("Logging configured successfully!")
logger.debug(f"Console log level: {LOG_LEVEL_CONSOLE}, File log level: {LOG_LEVEL_FILE}")
logger.debug(f"Log filename: {LOG_FILENAME}, Max bytes: {LOG_MAX_BYTES}, Backup count: {LOG_BACKUP_COUNT}")


# --- Импорт конфигурации ---
# Импортируем config ПОСЛЕ настройки логгера, чтобы config мог использовать logger
try:
    from src import config as app_config # Даем псевдоним, чтобы не конфликтовать с модулем config из других библиотек
    app_config.log_config_status() # Вызываем функцию логирования статуса конфигурации
except ImportError:
    logger.critical("Failed to import src.config. Critical error, cannot continue.", exc_info=True)
    sys.exit("Critical: src.config import failed.")
except Exception as e:
    logger.critical(f"An unexpected error occurred during config import or logging: {e}", exc_info=True)
    sys.exit("Critical: Unexpected error with config.")


# --- Инициализация Sentry (если DSN указан в конфиге) ---
if app_config.SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.aiohttp import AioHttpIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration # Для лучшей интеграции с логами
        from sentry_sdk.integrations.asyncio import AsyncioIntegration

        sentry_logging = LoggingIntegration(
            level=logging.INFO,        # Захватывать логи уровня INFO и выше
            event_level=logging.ERROR  # Отправлять логи уровня ERROR и выше как события Sentry
        )

        sentry_sdk.init(
            dsn=app_config.SENTRY_DSN,
            integrations=[
                AioHttpIntegration(),
                SqlalchemyIntegration(),
                sentry_logging, # Интеграция с логированием
                AsyncioIntegration(),
            ],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", 0.1)), # Частота выборки трассировок
            profiles_sample_rate=float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", 0.1)), # Частота выборки профилирования
            environment=os.getenv("SENTRY_ENVIRONMENT", "development"), # Окружение (dev, prod, staging)
            # send_default_pii=True, # Отправлять ли PII (Personal Identifiable Information)
        )
        logger.info("Sentry SDK initialized successfully.")
        sentry_sdk.capture_message("Sentry test message from bot startup", level="info") # Тестовое сообщение
    except ImportError:
        logger.error("sentry-sdk not installed. Sentry integration skipped.")
    except Exception as e:
        logger.exception(f"Failed to initialize Sentry SDK: {e}", exc_info=True)
else:
    logger.info("SENTRY_DSN not found in config. Sentry integration skipped.")


# --- Настройка aiocache (если используется) ---
# Убедимся, что CACHE_BACKEND валидный перед попыткой настройки
if app_config.CACHE_BACKEND in ["memory", "redis"]:
    try:
        from aiocache import caches, Cache
        from aiocache.serializers import JsonSerializer # Рекомендуется для сложных объектов

        cache_config = {
            'default': {
                'cache': "aiocache.SimpleMemoryCache" if app_config.CACHE_BACKEND == "memory" else "aiocache.RedisCache",
                'serializer': {'class': 'aiocache.serializers.JsonSerializer'} # Используем JsonSerializer
            }
        }
        if app_config.CACHE_BACKEND == "redis":
            if not app_config.CACHE_REDIS_URL:
                logger.error("CACHE_BACKEND is 'redis' but CACHE_REDIS_URL is not set. Caching will be disabled.")
            else:
                # aiocache.RedisCache может принимать endpoint и port или redis_url
                # Простой способ - передать все как часть URL, если библиотека поддерживает (проверить документацию aiocache)
                # Или парсить URL:
                from urllib.parse import urlparse
                redis_url_parsed = urlparse(app_config.CACHE_REDIS_URL)
                cache_config['default'].update({
                    'endpoint': redis_url_parsed.hostname,
                    'port': redis_url_parsed.port,
                    # 'password': redis_url_parsed.password, # Если есть пароль в URL
                    'db': int(redis_url_parsed.path.lstrip('/') or 0) # Redis DB номер
                })
        
        caches.set_config(cache_config)
        logger.info(f"aiocache initialized successfully with backend: {app_config.CACHE_BACKEND}.")
        
        # Проверка кэша
        # async def test_cache():
        #     cache = caches.get('default')
        #     await cache.set("my_key", "my_value", ttl=10)
        #     value = await cache.get("my_key")
        #     logger.info(f"Cache test: my_key = {value}")
        # asyncio.run(test_cache()) # Закомментировано, чтобы не выполнять при каждом запуске

    except ImportError:
        logger.error("aiocache not installed. Caching will be disabled.", exc_info=True)
    except Exception as e:
        logger.error(f"Failed to initialize aiocache: {e}", exc_info=True)
else:
    logger.info(f"Unsupported CACHE_BACKEND value: '{app_config.CACHE_BACKEND}'. Caching disabled.")


# --- Импорт и запуск бота ---
# Импортируем main из src.bot ПОСЛЕ всех инициализаций
try:
    from src.bot import main as run_bot
except ImportError as e:
     logger.critical(f"Failed to import src.bot.main: {e}", exc_info=True)
     sys.exit("Critical: Failed to import core bot module.")
except Exception as e: # Другие возможные ошибки при импорте
     logger.critical(f"An unexpected error occurred during 'src.bot' import: {e}", exc_info=True)
     sys.exit("Critical: Unexpected error during bot module import.")


if __name__ == "__main__":
    logger.info(f"Initializing application via __main__.py (PID: {os.getpid()})...")
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user (KeyboardInterrupt) or system exit.")
        # Sentry может не успеть отправить событие, если это KeyboardInterrupt
        # Можно добавить явный flush для Sentry здесь, если это критично
        if app_config.SENTRY_DSN and sentry_sdk.Hub.current.client:
            sentry_sdk.flush(timeout=2) # Даем Sentry 2 секунды на отправку
    except Exception as e:
        # Это исключение будет перехвачено Sentry, если он инициализирован
        logger.critical(f"Unhandled exception at the top level of asyncio.run: {e}", exc_info=True)
        if app_config.SENTRY_DSN and sentry_sdk.Hub.current.client:
            sentry_sdk.capture_exception(e)
            sentry_sdk.flush(timeout=5)
    finally:
        logger.info("Application shutdown sequence initiated in __main__ finally block.")
        # Закрытие логгеров (особенно файловых)
        logging.shutdown()
        # Здесь не нужно выводить в лог после logging.shutdown()
        print(f"{datetime.now()} - Application shutdown complete from __main__.py.", file=sys.stderr)