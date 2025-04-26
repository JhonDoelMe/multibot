# src/bot.py

import asyncio
import logging
import sys
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.bot import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
# --- Импорты для УПРОЩЕННОГО вебхука ---
# from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application # <- Закомментировано для теста
from aiohttp import web # <- Используем только базовый aiohttp
# from aiogram.types import Update # <- Не нужен для теста

from src import config
# --- Импорт для БД ---
from src.db.database import initialize_database, async_session_factory
# --- Импорт Middleware ---
from src.middlewares.db_session import DbSessionMiddleware

# Импортируем роутеры (они не будут использоваться в упрощенной версии вебхука, но пусть остаются)
from src.modules.weather import handlers as weather_handlers
from src.modules.currency import handlers as currency_handlers
from src.modules.alert import handlers as alert_handlers
from src.handlers import common as common_handlers

logger = logging.getLogger(__name__)

# --- Функции для запуска/остановки ---

async def on_startup(bot: Bot):
    """ Выполняется при старте бота: инициализация БД и удаление старого вебхука (для polling). """
    logger.info("Executing on_startup actions...")
    if not config.RUN_WITH_WEBHOOK:
         logger.info("Running in polling mode, deleting potential webhook...")
         await bot.delete_webhook(drop_pending_updates=True)
         logger.info("Webhook deleted.")

async def on_shutdown(bot: Bot):
    """ Выполняется при остановке бота. """
    logger.warning("Executing on_shutdown actions...")
    logger.warning("Bot shutdown complete.")


async def main() -> None:
    """ Главная функция: настраивает и запускает бота. """

    # --- Инициализация БД ---
    logger.info("Attempting database initialization...")
    db_initialized = await initialize_database()
    if not db_initialized and config.DATABASE_URL:
         logger.critical("Database initialization failed! Bot functionalities might be limited.")
    elif db_initialized:
         logger.info("Database initialization seems successful.")

    # --- Инициализация Aiogram (оставляем, т.к. Bot нужен) ---
    logger.info("Initializing Aiogram Bot component...")
    # storage = MemoryStorage() # Не используется в упрощенном тесте
    default_props = DefaultBotProperties(parse_mode=ParseMode.HTML)
    bot = Bot(token=config.BOT_TOKEN, default=default_props)
    # dp = Dispatcher(storage=storage) # Не используется в упрощенном тесте

    # --- Регистрация Middleware (пропускаем в упрощенном тесте) ---
    # if db_initialized and async_session_factory:
    #     dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
    #     logger.info("Database session middleware registered.")
    # else:
    #     logger.warning("Database session middleware skipped (DB not initialized or session factory missing).")

    # --- Регистрация роутеров (пропускаем в упрощенном тесте) ---
    # logger.info("Registering routers...")
    # dp.include_router(weather_handlers.router)
    # dp.include_router(currency_handlers.router)
    # dp.include_router(alert_handlers.router)
    # dp.include_router(common_handlers.router)
    # logger.info("All routers registered.")

    # --- Вызов on_startup (оставляем, т.к. он удаляет вебхук для polling) ---
    await on_startup(bot)

    # --- Логика запуска ---
    try:
        if config.RUN_WITH_WEBHOOK:
            # #############################################
            # ### НАЧАЛО УПРОЩЕННОГО КОДА ДЛЯ ТЕСТА ###
            # #############################################
            logger.warning("Starting bot in WEBHOOK mode (SIMPLIFIED TEST)...")

            # Простой обработчик запросов
            async def handle_simple_request(request):
                logger.info("Received request on simplified handler!")
                return web.Response(text="Hello from simplified bot!")

            # Создаем базовое приложение aiohttp
            app = web.Application()
            # Добавляем только один простой обработчик на корневой путь
            app.router.add_get('/', handle_simple_request)
            # Пробуем добавить и путь вебхука, если он есть, для базовой проверки
            if config.WEBHOOK_PATH:
                 app.router.add_post(config.WEBHOOK_PATH, handle_simple_request)
                 logger.info(f"Registered simplified handler at path: {config.WEBHOOK_PATH}")
            else:
                 logger.error("WEBHOOK_PATH is not set in config!")

            # Запускаем веб-сервер
            logger.info(f"Attempting to start simplified web server on {config.WEBAPP_HOST}:{config.WEBAPP_PORT}...")
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, config.WEBAPP_HOST, config.WEBAPP_PORT)
            await site.start()
            logger.info("Simplified web server started successfully.") # <- Должны увидеть в логах

            # Ожидаем вечно
            logger.info("Starting infinite wait loop (simplified)...") # <- Должны увидеть в логах
            await asyncio.Event().wait() # <- Блокируем здесь
            logger.warning("Infinite wait loop somehow finished (THIS IS UNEXPECTED!).")
            # #############################################
            # ### КОНЕЦ УПРОЩЕННОГО КОДА ДЛЯ ТЕСТА ###
            # #############################################
        else:
            # --- Режим Поллинга (остается без изменений) ---
            logger.warning("Starting bot in POLLING mode...")
            # Инициализация Dispatcher нужна только для поллинга
            logger.info("Initializing Aiogram Dispatcher for polling...")
            storage = MemoryStorage()
            dp = Dispatcher(storage=storage)
            # Регистрируем middleware и роутеры для поллинга
            if db_initialized and async_session_factory:
                 dp.update.outer_middleware(DbSessionMiddleware(session_pool=async_session_factory))
                 logger.info("DB Middleware registered for polling.")
            logger.info("Registering routers for polling...")
            dp.include_router(weather_handlers.router)
            dp.include_router(currency_handlers.router)
            dp.include_router(alert_handlers.router)
            dp.include_router(common_handlers.router)
            logger.info("Routers registered for polling.")

            logger.info("Starting polling...")
            await dp.start_polling(bot)

    finally:
        logger.warning("Closing bot session (in finally block)...")
        await bot.session.close()
        logger.warning("Bot session closed.")
        await on_shutdown(bot) # Выполняем действия при остановке

# Точка входа остается в __main__.py