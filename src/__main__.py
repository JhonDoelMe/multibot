# src/__main__.py

import asyncio
import logging
import sys

# Импортируем главный конфигуратор и запускатор бота из соседнего модуля bot
from src.bot import main

# Настраиваем корневой логгер при запуске модуля как основного
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    stream=sys.stdout,
)

logger = logging.getLogger(__name__)


# Проверяем, что скрипт запущен напрямую (или через python -m src)
if __name__ == "__main__":
    logger.info("Initializing application via __main__.py...")
    try:
        # Запускаем асинхронную функцию main из bot.py в цикле событий asyncio
        # Эта функция теперь включает и инициализацию БД
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        # Ловим прерывание с клавиатуры (Ctrl+C) или сигнал завершения SystemExit
        logger.info("Bot stopped by user (KeyboardInterrupt) or system exit.")
    except Exception as e:
        # Ловим любые другие непредвиденные исключения на самом верхнем уровне
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
    finally:
        # Этот блок выполнится в любом случае при выходе из try/except
        logger.info("Application shutdown.")