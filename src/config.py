# src/config.py

import os
from dotenv import load_dotenv
import logging
import sys

load_dotenv()

logger = logging.getLogger(__name__)

# --- Основні настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- API Ключі и Токени ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
UKRAINEALARM_API_TOKEN = os.getenv("UKRAINEALARM_API_TOKEN")
ALERTS_IN_UA_TOKEN = os.getenv("ALERTS_IN_UA_TOKEN")
WEATHERAPI_COM_KEY = os.getenv("WEATHERAPI_COM_KEY")
# RATEXCHANGES_API_KEY = os.getenv("RATEXCHANGES_API_KEY") # Якщо використовується, розкоментуйте

# --- Налаштування Вебхука ---
WEBHOOK_BASE_URL = os.getenv("WEBHOOK_BASE_URL")
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", f"/webhook/{BOT_TOKEN[:10] if BOT_TOKEN else 'default_bot_path'}")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

RUN_WITH_WEBHOOK = bool(WEBHOOK_BASE_URL and WEBHOOK_SECRET)

# --- Налаштування Бази Даних ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Параметри ретраїв та таймаутів для API-запитів ---
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
INITIAL_DELAY = int(os.getenv("INITIAL_DELAY", 1))
API_REQUEST_TIMEOUT = int(os.getenv("API_REQUEST_TIMEOUT", 15))
API_SESSION_TOTAL_TIMEOUT = int(os.getenv("API_SESSION_TOTAL_TIMEOUT", 30))
API_SESSION_CONNECT_TIMEOUT = int(os.getenv("API_SESSION_CONNECT_TIMEOUT", 10))

# --- Налаштування кешування (aiocache) ---
CACHE_BACKEND = os.getenv("CACHE_BACKEND", "memory")
CACHE_REDIS_URL = os.getenv("CACHE_REDIS_URL", "redis://localhost:6379/0")

CACHE_TTL_ALERTS = int(os.getenv("CACHE_TTL_ALERTS", 60))
CACHE_TTL_ALERTS_BACKUP = int(os.getenv("CACHE_TTL_ALERTS_BACKUP", 90))
CACHE_TTL_WEATHER = int(os.getenv("CACHE_TTL_WEATHER", 600))
CACHE_TTL_WEATHER_BACKUP = int(os.getenv("CACHE_TTL_WEATHER_BACKUP", 700))
CACHE_TTL_CURRENCY = int(os.getenv("CACHE_TTL_CURRENCY", 3600))
CACHE_TTL_REGIONS = int(os.getenv("CACHE_TTL_REGIONS", 86400))

# --- Sentry/GlitchTip Configuration ---
# Замість SENTRY_DSN тепер може бути GLITCHTIP_DSN або універсальна назва
# Залишимо SENTRY_DSN як основну, але врахуємо GLITCHTIP_DSN, якщо SENTRY_DSN відсутній
SENTRY_DSN = os.getenv("SENTRY_DSN") or os.getenv("GLITCHTIP_DSN")
BOT_ENVIRONMENT = os.getenv("BOT_ENVIRONMENT", "development") # 'development', 'production', 'staging'
BOT_VERSION = os.getenv("BOT_VERSION", "unknown") # Версія вашого бота

THROTTLING_RATE_DEFAULT = float(os.getenv("THROTTLING_RATE_DEFAULT", 0.7))

if not BOT_TOKEN:
    critical_error_msg = "CRITICAL ERROR: BOT_TOKEN is not defined in environment variables. Bot cannot start."
    print(critical_error_msg, file=sys.stderr)
    raise ValueError(critical_error_msg)

if RUN_WITH_WEBHOOK:
    if not WEBHOOK_SECRET:
        critical_error_msg = "CRITICAL ERROR: Running in WEBHOOK mode, but WEBHOOK_SECRET is not defined. Bot cannot start securely."
        print(critical_error_msg, file=sys.stderr)
        raise ValueError(critical_error_msg)
    if not WEBHOOK_BASE_URL:
        critical_error_msg = "CRITICAL ERROR: Running in WEBHOOK mode, but WEBHOOK_BASE_URL is not defined."
        print(critical_error_msg, file=sys.stderr)
        raise ValueError(critical_error_msg)

def log_config_status():
    logger.info("--- Configuration Status ---")
    logger.info(f"BOT_TOKEN: {'Loaded' if BOT_TOKEN else 'NOT SET - CRITICAL ERROR (should have exited)'}")

    if RUN_WITH_WEBHOOK:
        logger.info("Running in WEBHOOK mode.")
        logger.info(f"  WEBHOOK_BASE_URL: {WEBHOOK_BASE_URL}")
        logger.info(f"  WEBHOOK_PATH: {WEBHOOK_PATH}")
        logger.info(f"  WEBHOOK_SECRET: {'Loaded' if WEBHOOK_SECRET else 'NOT SET - CRITICAL ERROR (should have exited)'}")
        logger.info(f"  WEBAPP_HOST: {WEBAPP_HOST}")
        logger.info(f"  WEBAPP_PORT: {WEBAPP_PORT}")
    else:
        logger.info("Running in POLLING mode.")

    logger.info(f"DATABASE_URL: {'Loaded (details in DB init logs)' if DATABASE_URL else 'NOT SET - DB features will be disabled'}")

    service_keys_status = {
        "WEATHER_API_KEY (OpenWeatherMap)": WEATHER_API_KEY,
        "WEATHERAPI_COM_KEY (WeatherAPI.com)": WEATHERAPI_COM_KEY,
        "UKRAINEALARM_API_TOKEN": UKRAINEALARM_API_TOKEN,
        "ALERTS_IN_UA_TOKEN": ALERTS_IN_UA_TOKEN
        # "RATEXCHANGES_API_KEY": RATEXCHANGES_API_KEY # Якщо використовується
    }
    for name, key_value in service_keys_status.items():
        if key_value:
            logger.info(f"{name}: Loaded")
        else:
            logger.warning(f"{name}: NOT SET - Corresponding module may not function correctly or at all.")

    logger.info(f"MAX_RETRIES: {MAX_RETRIES}, INITIAL_DELAY: {INITIAL_DELAY}s, API_REQUEST_TIMEOUT: {API_REQUEST_TIMEOUT}s")
    logger.info(f"API_SESSION_TOTAL_TIMEOUT: {API_SESSION_TOTAL_TIMEOUT}s, API_SESSION_CONNECT_TIMEOUT: {API_SESSION_CONNECT_TIMEOUT}s")

    logger.info(f"CACHE_BACKEND: {CACHE_BACKEND}")
    if CACHE_BACKEND == 'redis':
        if CACHE_REDIS_URL:
            logger.info(f"  CACHE_REDIS_URL: {CACHE_REDIS_URL}")
        else:
            logger.warning("  CACHE_REDIS_URL: NOT SET - Redis cache will not work!")
    logger.info(f"  CACHE_TTL_ALERTS: {CACHE_TTL_ALERTS}s, CACHE_TTL_ALERTS_BACKUP: {CACHE_TTL_ALERTS_BACKUP}s")
    logger.info(f"  CACHE_TTL_WEATHER: {CACHE_TTL_WEATHER}s, CACHE_TTL_WEATHER_BACKUP: {CACHE_TTL_WEATHER_BACKUP}s")
    logger.info(f"  CACHE_TTL_CURRENCY: {CACHE_TTL_CURRENCY}s, CACHE_TTL_REGIONS: {CACHE_TTL_REGIONS}s")

    logger.info(f"SENTRY_DSN (or GLITCHTIP_DSN): {'Loaded - Sentry/GlitchTip enabled' if SENTRY_DSN else 'NOT SET - Sentry/GlitchTip disabled'}")
    logger.info(f"BOT_ENVIRONMENT: {BOT_ENVIRONMENT}")
    logger.info(f"BOT_VERSION: {BOT_VERSION}")

    logger.info(f"THROTTLING_RATE_DEFAULT: {THROTTLING_RATE_DEFAULT}s")
    logger.info("--- End Configuration Status ---")