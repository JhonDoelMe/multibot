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

# (Логирование для ключей API и DB остается без изменений)