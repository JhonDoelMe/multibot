# src/main.py

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiocache import caches

from src import config
from src.handlers import router  # Предполагается, что роутеры определены в handlers

logger = logging.getLogger(__name__)

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Настройка aiocache
    caches.set_config({
        "default": {
            "cache": "aiocache.SimpleMemoryCache" if config.CACHE_BACKEND == "memory" else "aiocache.RedisCache",
            "endpoint": config.CACHE_REDIS_URL.split("://")[1].split(":")[0] if config.CACHE_BACKEND == "redis" else None,
            "port": int(config.CACHE_REDIS_URL.split(":")[-1].split("/")[0]) if config.CACHE_BACKEND == "redis" else None,
            "db": int(config.CACHE_REDIS_URL.split("/")[-1]) if config.CACHE_BACKEND == "redis" else None,
        }
    })

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    if config.RUN_WITH_WEBHOOK:
        await bot.set_webhook(f"{config.WEBHOOK_PATH}")
        logger.info(f"Webhook set to {config.WEBHOOK_PATH}")
        # Здесь предполагается запуск веб-сервера, например, с aiohttp
    else:
        await bot.delete_webhook()
        logger.info("Starting polling...")
        await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())