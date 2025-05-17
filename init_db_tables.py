# init_db_tables.py
import asyncio
import logging
import os
import sys

# Налаштування шляхів для коректного імпорту з src,
# коли скрипт запускається з кореневої директорії проєкту.
current_script_path = os.path.dirname(os.path.abspath(__file__))
# Якщо init_db_tables.py знаходиться в корені проєкту, то project_root = current_script_path
# Якщо init_db_tables.py знаходиться в /src, то project_root = os.path.dirname(current_script_path)
# Припускаємо, що init_db_tables.py знаходиться в КОРЕНЕВІЙ директорії проєкту.
project_root = current_script_path 
src_dir_path = os.path.join(project_root, "src")

if src_dir_path not in sys.path:
    sys.path.insert(0, src_dir_path)
if project_root not in sys.path: # Якщо сам корінь ще не в sys.path
    sys.path.insert(0, project_root)


# Тепер можна імпортувати з src
from src import config as app_config # Завантажуємо конфігурацію
from src.db.database import engine, Base # Імпортуємо engine та Base
from src.db.models import User # Імпортуємо ваші моделі

# Налаштування базового логування для цього скрипта
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout) # Виводимо логи в stdout
    ]
)
logger = logging.getLogger(__name__)

async def create_tables():
    """
    Асинхронна функція для створення всіх таблиць, визначених у Base.metadata.
    Якщо розкоментовано drop_all, то існуючі таблиці будуть видалені перед створенням.
    """
    if not app_config.DATABASE_URL:
        logger.error("DATABASE_URL is not set in the environment/config. Cannot create tables.")
        return

    # Логуємо URL бази даних (без облікових даних, якщо вони є)
    db_url_display = app_config.DATABASE_URL
    if '@' in db_url_display:
        db_url_display = db_url_display.split('@', 1)[-1]
    logger.info(f"Attempting to connect to database: {db_url_display}")
    
    try:
        async with engine.begin() as conn:
            logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            logger.warning("!!! ATTENTION: DROPPING ALL EXISTING TABLES (if configured)!!!")
            logger.warning("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            
            # Розкоментуйте наступний рядок, щоб ВИДАЛИТИ всі існуючі таблиці перед створенням нових.
            # ЦЕ ПРИЗВЕДЕ ДО ВТРАТИ ВСІХ ДАНИХ В ЦИХ ТАБЛИЦЯХ!
            await conn.run_sync(Base.metadata.drop_all) # <--- РОЗКОМЕНТОВАНО ДЛЯ ВИДАЛЕННЯ
            logger.info("Existing tables dropped successfully.")

            logger.info("Creating database tables based on models...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables created successfully!")
            
    except ConnectionRefusedError:
        logger.error(f"Database connection refused. Ensure the database server is running and accessible at the configured DATABASE_URL.")
    except Exception as e:
        logger.exception("An error occurred during table creation:", exc_info=e)
    finally:
        if engine: # Перевірка, чи engine взагалі було створено
            await engine.dispose()
            logger.info("Database engine disposed.")

if __name__ == "__main__":
    logger.info("Starting database table (re)creation script...")
    
    # Перевірка завантаження конфігурації
    if not hasattr(app_config, 'BOT_TOKEN') or not app_config.BOT_TOKEN: 
        logger.warning("App config might not be loaded correctly (BOT_TOKEN is missing or None).")
    if not hasattr(app_config, 'DATABASE_URL') or not app_config.DATABASE_URL:
        logger.error("CRITICAL: DATABASE_URL is not configured. Cannot proceed with table creation.")
        sys.exit(1) # Виходимо, якщо немає DATABASE_URL
    
    asyncio.run(create_tables())
    logger.info("Database table (re)creation script finished.")

# Виводимо повідомлення про завершення