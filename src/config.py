# src/config.py

import os
from dotenv import load_dotenv
import logging

load_dotenv()

logger = logging.getLogger(__name__)

# --- Основные настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- API Ключи и Токены ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
UKRAINEALARM_API_TOKEN = os.getenv("UKRAINEALARM_API_TOKEN")

# --- Настройки Вебхука (для GCP Cloud Run) ---
# Секретный путь для вебхука (из Secret Manager)
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH")

# Настройки веб-сервера aiohttp
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080")) # Cloud Run передает PORT, но пусть будет и тут

# --- Флаг режима работы ---
# Определяем режим по наличию WEBHOOK_PATH (предполагаем, что он задан только при деплое)
RUN_WITH_WEBHOOK = bool(WEBHOOK_PATH)

# --- Настройки Базы Данных ---
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Проверка обязательных переменных ---
if not BOT_TOKEN:
    error_message = "Critical error: BOT_TOKEN is not defined."
    logger.critical(error_message)
    raise ValueError(error_message)

# --- Логирование режима работы ---
if RUN_WITH_WEBHOOK:
    logger.info(f"Running in WEBHOOK mode. Path: {WEBHOOK_PATH}, Port: {WEBAPP_PORT}")
    if not WEBHOOK_PATH:
         logger.error("WEBHOOK_PATH is not set, but running in webhook mode inferred. Webhook handler might not register.")
else:
    logger.info("Running in POLLING mode.")

# (Логирование для ключей API и DB остается без изменений)