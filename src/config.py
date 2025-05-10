# src/config.py

import os
from dotenv import load_dotenv
import logging

# Загружаем .env в первую очередь, чтобы переменные из него были доступны сразу
load_dotenv()

logger = logging.getLogger(__name__) # Логгер будет настроен в __main__.py

# --- Основные настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- API Ключи и Токены ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
UKRAINEALARM_API_TOKEN = os.getenv("UKRAINEALARM_API_TOKEN")
ALERTS_IN_UA_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN")

# --- Настройки Вебхука ---
# WEBHOOK_HOST - больше не нужен, используем WEBHOOK_BASE_URL
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL") # Например, https://your-app-name.fly.dev или URL от ngrok
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", f"/webhook/{BOT_TOKEN[:10]}") # Путь для вебхука, по умолчанию используем часть токена
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET") # Секретный токен для вебхука, ДОЛЖЕН БЫТЬ ЗАДАН

WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0") # Хост, на котором слушает веб-приложение (внутри контейнера)
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080")) # Порт, на котором слушает веб-приложение

# --- Флаг режима работы ---
# Определяем режим по наличию WEBHOOK_BASE_URL и WEBHOOK_SECRET
RUN_WITH_WEBHOOK = bool(WEBHOOK_BASE_URL and WEBHOOK_SECRET)

# --- Настройки Базы Данных ---
DATABASE_URL = os.getenv("DATABASE_URL") # Например, "postgresql+asyncpg://user:pass@host:port/db"

# --- Параметры ретраев и таймаутов для API-запросов ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
INITIAL_DELAY = int(os.getenv("INITIAL_DELAY", 1)) # секунды
API_REQUEST_TIMEOUT = int(os.getenv("API_REQUEST_TIMEOUT", 15)) # Таймаут для одного HTTP-запроса к внешнему API

# Таймауты для сессии aiohttp самого бота (для запросов к Telegram API)
# и для ClientSession при запросах к внешним API из сервисов
API_SESSION_TOTAL_TIMEOUT = int(os.getenv("API_SESSION_TOTAL_TIMEOUT", 30)) # Общий таймаут на запрос-ответ сессии
API_SESSION_CONNECT_TIMEOUT = int(os.getenv("API_SESSION_CONNECT_TIMEOUT", 10)) # Таймаут на установку соединения сессии


# --- Настройки кэширования (aiocache) ---
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")  # "memory" или "redis"
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0") # Если CACHE_BACKEND == "redis"

# TTL в секундах
CACHE_TTL_ALERTS = int(os.getenv("CACHE_TTL_ALERTS", 60)) # Основные тревоги (UkraineAlarm)
CACHE_TTL_ALERTS_BACKUP = int(os.getenv("CACHE_TTL_ALERTS_BACKUP", 90)) # Резервные тревоги
CACHE_TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", 600)) # 10 минут
CACHE_TTL_CURRENCY = int(os.getenv("CACHE_TTL_CURRENCY", 3600)) # 1 час
CACHE_TTL_REGIONS = int(os.getenv("CACHE_TTL_REGIONS", 86400)) # Список регионов (раз в сутки)

# --- Sentry DSN ---
SENTRY_DSN = os.getenv("SENTRY_DSN")

# --- Throttling ---
THROTTLING_RATE_DEFAULT = float(os.getenv("THROTTLING_RATE_DEFAULT", 0.7)) # секунд между запросами от одного юзера

# --- Проверка обязательных переменных ---
if not BOT_TOKEN:
    # Логирование здесь может не сработать, если __main__ еще не настроил логгер
    # Поэтому лучше использовать print для критических ошибок на старте конфига
    # и/или выбрасывать исключение, которое остановит запуск.
    critical_error_msg = "CRITICAL ERROR: BOT_TOKEN is not defined in environment variables. Bot cannot start."
    logger.critical(critical_error_msg) # Попытка логирования
    raise ValueError(critical_error_msg)

if RUN_WITH_WEBHOOK:
    if not WEBHOOK_SECRET:
        critical_error_msg = "CRITICAL ERROR: Running in WEBHOOK mode, but WEBHOOK_SECRET is not defined. Bot cannot start securely."
        logger.critical(critical_error_msg)
        raise ValueError(critical_error_msg)
    if not WEBHOOK_BASE_URL: # Уже проверено выше, но для ясности
        critical_error_msg = "CRITICAL ERROR: Running in WEBHOOK mode, but WEBHOOK_BASE_URL is not defined."
        logger.critical(critical_error_msg)
        raise ValueError(critical_error_msg)


# --- Логирование статуса конфигурации (вызывается после настройки логгера в __main__.py) ---
def log_config_status():
    logger.info(f"--- Configuration Status ---")
    logger.info(f"BOT_TOKEN: {'Loaded' if BOT_TOKEN else 'NOT SET'}")

    if RUN_WITH_WEBHOOK:
        logger.info(f"Running in WEBHOOK mode.")
        logger.info(f"  WEBHOOK_BASE_URL: {WEBHOOK_BASE_URL}")
        logger.info(f"  WEBHOOK_PATH: {WEBHOOK_PATH}")
        logger.info(f"  WEBHOOK_SECRET: {'Loaded' if WEBHOOK_SECRET else 'NOT SET - CRITICAL'}")
        logger.info(f"  WEBAPP_HOST: {WEBAPP_HOST}")
        logger.info(f"  WEBAPP_PORT: {WEBAPP_PORT}")
    else:
        logger.info("Running in POLLING mode.")

    logger.info(f"DATABASE_URL: {'Loaded (details in DB init logs)' if DATABASE_URL else 'NOT SET - DB features disabled'}")
    logger.info(f"WEATHER_API_KEY: {'Loaded' if WEATHER_API_KEY else 'NOT SET - Weather module may fail'}")
    logger.info(f"UKRAINEALARM_API_TOKEN: {'Loaded' if UKRAINEALARM_API_TOKEN else 'NOT SET - Primary alerts module may fail'}")
    logger.info(f"ALERTS_IN_UA_TOKEN: {'Loaded' if ALERTS_IN_UA_TOKEN else 'NOT SET - Backup alerts module may fail'}")

    logger.info(f"MAX_RETRIES: {MAX_RETRIES}, INITIAL_DELAY: {INITIAL_DELAY}s, API_REQUEST_TIMEOUT: {API_REQUEST_TIMEOUT}s")
    logger.info(f"API_SESSION_TOTAL_TIMEOUT: {API_SESSION_TOTAL_TIMEOUT}s, API_SESSION_CONNECT_TIMEOUT: {API_SESSION_CONNECT_TIMEOUT}s")

    logger.info(f"CACHE_BACKEND: {CACHE_BACKEND}")
    if CACHE_BACKEND == 'redis':
        logger.info(f"  CACHE_REDIS_URL: {CACHE_REDIS_URL}")
    logger.info(f"  CACHE_TTL_ALERTS: {CACHE_TTL_ALERTS}s, CACHE_TTL_ALERTS_BACKUP: {CACHE_TTL_ALERTS_BACKUP}s")
    logger.info(f"  CACHE_TTL_WEATHER: {CACHE_TTL_WEATHER}s, CACHE_TTL_CURRENCY: {CACHE_TTL_CURRENCY}s, CACHE_TTL_REGIONS: {CACHE_TTL_REGIONS}s")

    logger.info(f"SENTRY_DSN: {'Loaded - Sentry enabled' if SENTRY_DSN else 'NOT SET - Sentry disabled'}")
    logger.info(f"THROTTLING_RATE_DEFAULT: {THROTTLING_RATE_DEFAULT}s")
    logger.info(f"--- End Configuration Status ---")

# Важно: log_config_status() должна быть вызвана из __main__.py ПОСЛЕ настройки root_logger.