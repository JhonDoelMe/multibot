# src/bot.py

import asyncio
import logging
import sys # Убрали ненужный импорт Router отсюда, если он не используется напрямую

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
# from aiogram.fsm.storage.memory import MemoryStorage # Если понадобится FSM

# Импортируем конфигурацию
# Используем абсолютный импорт от корня проекта,
# который будет работать при запуске через `python -m src`
from src import config

# Импортируем роутеры
from src.handlers import common as common_handlers
# Заготовки для импорта роутеров модулей
# from src.modules.weather import handlers as weather_handlers
# from src.modules.currency import handlers as currency_handlers
# from src.modules.alert import handlers as alert_handlers

# Получаем логгер для этого модуля
logger = logging.getLogger(__name__)

async def main() -> None:
    """Главная асинхронная функция для настройки и запуска бота."""
    logger.info("Starting bot setup...")

    # --- Инициализация ---
    # Указываем parse_mode по умолчанию для сообщений бота
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=config.BOT_TOKEN, default=default_props)

    # Диспетчер будет обрабатывать входящие обновления
    # storage=MemoryStorage() можно добавить, если планируется использование FSM
    dp = Dispatcher()

    # --- Регистрация роутеров ---
    logger.info("Registering routers...")
    # Подключаем роутер с общими командами (/start и колбэки главного меню)
    dp.include_router(common_handlers.router)

    # Здесь будем подключать роутеры модулей по мере их готовности
    # dp.include_router(weather_handlers.router)
    # logger.info("Weather module router registered.")
    # dp.include_router(currency_handlers.router)
    # logger.info("Currency module router registered.")
    # dp.include_router(alert_handlers.router)
    # logger.info("Alert module router registered.")

    # --- Запуск Polling ---
    # Удаляем вебхук перед запуском polling
    # Это важно для локальной разработки
    try:
      await bot.delete_webhook(drop_pending_updates=True)
      logger.info("Webhook deleted (if existed).")
    except Exception as e:
        # Логируем ошибку удаления вебхука, но не прерываем запуск
        logger.error(f"Error deleting webhook: {e}")


    logger.info("Starting polling...")
    # Запускаем polling - бот начинает получать обновления от Telegram
    # Важно передать и бот в start_polling
    # Блок try/except/finally для перехвата ошибок внутри polling
    # лучше оставить в точке входа (__main__.py) или обернуть dp.start_polling здесь.
    # Для простоты пока оставим без try/except здесь, он есть в __main__.py
    await dp.start_polling(bot)

# Блок if __name__ == "__main__": УДАЛЕН ОТСЮДА