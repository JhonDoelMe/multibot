# src/config.py

import os
from dotenv import load_dotenv
import logging

load_dotenv() # Загружаем .env, если он есть (переменные из cPanel будут иметь приоритет)

logger = logging.getLogger(__name__)

# --- Основные настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- API Ключи и Токены ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
UKRAINEALARM_API_TOKEN = os.getenv("UKRAINEALARM_API_TOKEN")
ALERTS_IN_UA_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN") # <<< ДОБАВЛЕНО

# --- Настройки Вебхука ---
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

# --- Флаг режима работы ---
RUN_WITH_WEBHOOK = bool(WEBHOOK_PATH)

# --- Настройки Базы Данных ---
DATABASE_URL = os.getenv("DATABASE_URL")

# Параметры ретраев для API-запросов
MAX_RETRIES = 3  # Максимальное количество попыток при ошибках API
INITIAL_DELAY = 1  # Начальная задержка для ретраев в секундах
API_REQUEST_TIMEOUT = 15  # Таймаут для HTTP-запросов к API в секундах

# Настройки кэширования (aiocache)
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")  # "memory" или "redis"
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0")
CACHE_TTL_ALERTS = 30  # TTL для кэша тревог (1 минута) - UkraineAlarm
CACHE_TTL_ALERTS_BACKUP = 30 # TTL для резервного кэша тревог (1.5 минуты) <<< ДОБАВЛЕНО
CACHE_TTL_WEATHER = 600  # TTL для кэша погоды (10 минут)
CACHE_TTL_CURRENCY = 3600  # TTL для кэша валют (1 час)

# --- Sentry DSN ---
SENTRY_DSN = os.getenv("SENTRY_DSN") # <<< ДОБАВЛЕНО

# --- Проверка обязательных переменных ---
if not BOT_TOKEN:
    error_message = "Critical error: BOT_TOKEN is not defined."
    logger.critical(error_message)
    raise ValueError(error_message)

# --- Логирование режима работы и Sentry ---
if RUN_WITH_WEBHOOK:
    logger.info(f"Running in WEBHOOK mode. Path: {WEBHOOK_PATH}, Port: {WEBAPP_PORT}")
    if not WEBHOOK_PATH:
         logger.error("WEBHOOK_PATH is not set, but running in webhook mode inferred.")
else:
    logger.info("Running in POLLING mode.")

if SENTRY_DSN:
    logger.info("Sentry DSN found and loaded.")
else:
    logger.warning("SENTRY_DSN is not set. Sentry integration disabled.")

# --- Логирование статуса API ключей и токенов ---
if WEATHER_API_KEY:
    logger.info("WEATHER_API_KEY loaded.")
else:
    logger.warning("WEATHER_API_KEY not set.")
if UKRAINEALARM_API_TOKEN:
    logger.info("UKRAINEALARM_API_TOKEN loaded.")
else:
    logger.warning("UKRAINEALARM_API_TOKEN not set (Primary alerts may fail).")
if ALERTS_IN_UA_TOKEN: # <<< ДОБАВЛЕНО
    logger.info("ALERTS_IN_UA_TOKEN loaded.") # <<< ДОБАВЛЕНО
else: # <<< ДОБАВЛЕНО
    logger.warning("ALERTS_IN_UA_TOKEN not set (Backup alerts will fail).") # <<< ДОБАВЛЕНО
if DATABASE_URL:
    # Логируем только часть URL без пароля, если он есть
    db_log_url = DATABASE_URL.split('@')[-1] if '@' in DATABASE_URL else DATABASE_URL
    logger.info(f"DATABASE_URL loaded (connecting to: ...@{db_log_url}).")
else:
    logger.warning("DATABASE_URL not set. Database features disabled.")
logger.info(f"Cache backend: {CACHE_BACKEND}, Redis URL: {CACHE_REDIS_URL if CACHE_BACKEND == 'redis' else 'N/A'}")