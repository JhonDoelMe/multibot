# src/__main__.py

import asyncio
import logging
import logging.handlers # <<< Добавляем handlers
import sys
import os # <<< Добавляем os для пути к логу

# --- Настройка логирования ---
# Определяем путь к лог-файлу (в корне проекта)
LOG_FILENAME = "bot.log"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT = 5 # Хранить 5 старых лог-файлов

# Создаем форматтер
log_formatter = logging.Formatter(
    '%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)

# --- Файловый обработчик с ротацией ---
file_handler = logging.handlers.RotatingFileHandler(
    filename=LOG_FILENAME,
    maxBytes=LOG_MAX_BYTES,
    backupCount=LOG_BACKUP_COUNT,
    encoding='utf-8'
)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.INFO) # Пишем в файл INFO и выше

# --- Консольный обработчик ---
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(log_formatter)
stream_handler.setLevel(logging.INFO) # В консоль тоже INFO и выше (можно DEBUG для отладки)

# --- Настройка корневого логгера ---
root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO) # Минимальный уровень для обработки (INFO)
root_logger.addHandler(file_handler)
root_logger.addHandler(stream_handler)

# --- Завершение базовой настройки логирования ---

# Сообщение о старте логгера
logger = logging.getLogger(__name__) # Получаем логгер для этого файла
logger.info("Logging configured!")

# Импортируем main ТОЛЬКО ПОСЛЕ настройки логирования
try:
    from src.bot import main
except ImportError as e:
     logger.critical(f"Failed to import src.bot.main: {e}", exc_info=True)
     sys.exit("Critical: Failed to import core bot module.")
except Exception as e:
     logger.critical(f"An unexpected error occurred during initial imports: {e}", exc_info=True)
     sys.exit("Critical: Unexpected error during imports.")


# --- Запуск приложения ---
if __name__ == "__main__":
    logger.info("Initializing application via __main__.py...")
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user or system exit.")
    except Exception as e:
        # Ловим любые другие исключения на верхнем уровне
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)
    finally:
        logger.info("Application shutdown sequence initiated.")
        # Здесь можно добавить код для корректного освобождения ресурсов, если нужно
        logging.shutdown() # Корректно закрываем обработчики логов
        logger.info("Application shutdown complete.")