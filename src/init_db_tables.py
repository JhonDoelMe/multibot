# init_db_tables.py
import asyncio
import logging
import os
import sys

# Додаємо шлях до src, щоб можна було імпортувати модулі звідти,
# якщо скрипт запускається з кореневої директорії проекту.
# Це потрібно, якщо ви запускаєте `python init_db_tables.py` з кореня.
# Якщо ви запускаєте як модуль `python -m init_db_tables` (і він у src), то це не потрібно.
# Для простоти, припустимо, що він в корені, і src поруч.
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = current_dir # Якщо скрипт в корені
# Якщо скрипт в піддиректорії scripts:
# project_root = os.path.dirname(current_dir) 
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Тепер можна імпортувати з src
from src import config as app_config # Завантажуємо конфігурацію
from src.db.database import engine, Base # Імпортуємо engine та Base
from src.db.models import User # Імпортуємо ваші моделі, щоб вони були зареєстровані в Base.metadata

# Налаштування базового логування для цього скрипта
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

async def create_tables():
    """
    Асинхронна функція для створення всіх таблиць, визначених у Base.metadata.
    """
    if not app_config.DATABASE_URL:
        logger.error("DATABASE_URL is not set in the environment/config. Cannot create tables.")
        return

    logger.info(f"Attempting to connect to database: {app_config.DATABASE_URL.split('@')[-1] if '@' in app_config.DATABASE_URL else app_config.DATABASE_URL}") # Показуємо частину URL без пароля
    
    # Переконуємося, що всі моделі імпортовані до виклику create_all,
    # щоб SQLAlchemy знав про них. Імпорт User вище це забезпечує.
    # Якщо у вас є інші моделі, їх також потрібно імпортувати.

    try:
        async with engine.begin() as conn:
            logger.info("Dropping all existing tables (if any)...") # Опціонально: для чистого створення
            # УВАГА: Наступні два рядки ВИДАЛЯТЬ ВСІ ІСНУЮЧІ ТАБЛИЦІ перед створенням нових.
            # Закоментуйте їх, якщо ви не хочете видаляти дані, а лише створити відсутні таблиці.
            # await conn.run_sync(Base.metadata.drop_all)
            # logger.info("Existing tables dropped.")

            logger.info("Creating database tables based on models...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully!")
            
            # Додаткова перевірка (опціонально)
            # Можна спробувати зробити простий запит, щоб переконатися, що таблиця users існує
            # from sqlalchemy import text
            # result = await conn.execute(text("SELECT COUNT(*) FROM users"))
            # logger.info(f"Test query: Found {result.scalar_one_or_none()} rows in users table (should be 0 if just created).")

    except ConnectionRefusedError:
        logger.error(f"Database connection refused. Ensure the database server is running and accessible at {app_config.DATABASE_URL}.")
    except Exception as e:
        logger.exception("An error occurred during table creation:", exc_info=e)
    finally:
        # Закриваємо з'єднання двигуна, якщо воно було відкрито
        await engine.dispose()
        logger.info("Database engine disposed.")

if __name__ == "__main__":
    logger.info("Starting database table creation script...")
    # Завантажуємо конфігурацію (це вже зроблено на рівні модуля, але для ясності)
    if not app_config.BOT_TOKEN: # Проста перевірка, що конфіг завантажився
        logger.warning("App config might not be loaded correctly (BOT_TOKEN is missing).")
    
    asyncio.run(create_tables())
    logger.info("Database table creation script finished.")

# Додаткові коментарі:
# Цей скрипт створює таблиці бази даних на основі моделей SQLAlchemy.
# Перед запуском переконайтеся, що DATABASE_URL налаштовано правильно.