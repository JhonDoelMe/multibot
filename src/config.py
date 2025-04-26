# src/config.py

import os
from dotenv import load_dotenv
import logging

# Загружаем переменные окружения из файла .env
# Если переменная уже установлена в системе, load_dotenv ее не перезапишет
load_dotenv()

logger = logging.getLogger(__name__)

# --- Основные настройки ---
BOT_TOKEN = os.getenv("BOT_TOKEN")

# --- API Ключи и Токены ---
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY")
RATEXCHANGES_API_KEY = os.getenv("RATEXCHANGES_API_KEY")
UKRAINEALARM_API_TOKEN = os.getenv("UKRAINEALARM_API_TOKEN")

# --- Настройки Вебхука (для Fly.io) ---
# При развертывании на Fly.io, он обычно предоставляет свой URL
# Лучше устанавливать эти переменные через секреты Fly.io (`flyctl secrets set`)
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST") # Например, https://your-app-name.fly.dev
WEBHOOK_PATH = os.getenv("WEBHOOK_PATH", "/webhook/bot") # Секретный путь для вебхука

# Настройки веб-сервера для вебхука
WEBAPP_HOST = os.getenv("WEBAPP_HOST", "0.0.0.0") # Слушать на всех интерфейсах внутри контейнера
# Fly.io ожидает, что приложение будет слушать на порту 8080 по умолчанию
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT", "8080"))

# --- Настройки Базы Данных ---
DATABASE_URL = os.getenv("DATABASE_URL") # Например, sqlite+aiosqlite:///./src/db/local_database.db

# --- Проверка обязательных переменных ---
if not BOT_TOKEN:
    error_message = (
        "Critical error: BOT_TOKEN is not defined. "
        "Please set it in your .env file or environment variables."
    )
    logger.critical(error_message)
    raise ValueError(error_message)

# --- Логирование опциональных переменных (для отладки) ---
if not WEATHER_API_KEY:
    logger.warning("WEATHER_API_KEY is not set. Weather module may not work.")
if not RATEXCHANGES_API_KEY:
    logger.warning("RATEXCHANGES_API_KEY is not set. Currency module might have limitations (free tier?).")
if not UKRAINEALARM_API_TOKEN:
    logger.warning("UKRAINEALARM_API_TOKEN is not set. Alert module may not work.")
if not DATABASE_URL:
    logger.warning("DATABASE_URL is not set. Database features will be disabled.")
if not WEBHOOK_HOST and os.getenv('FLY_APP_NAME'): # Пробуем определить хост для Fly.io
     WEBHOOK_HOST = f"https://{os.getenv('FLY_APP_NAME')}.fly.dev"
     logger.info(f"Inferred WEBHOOK_HOST for Fly.io: {WEBHOOK_HOST}")
elif not WEBHOOK_HOST:
     logger.warning("WEBHOOK_HOST is not set. Webhook setup might fail.")


# Можно добавить другие настройки по мере необходимости
# Например, список администраторов бота
# ADMIN_IDS = [int(admin_id) for admin_id in os.getenv("ADMIN_IDS", "").split(",") if admin_id]