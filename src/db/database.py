# src/db/database.py

import logging
from typing import Tuple, Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Імпортуємо конфігурацію для доступу до DATABASE_URL
from src import config as app_config # Даємо псевдонім, щоб уникнути конфлікту з модулем config

logger = logging.getLogger(__name__)

# --- Визначення Base для моделей ---
class Base(DeclarativeBase):
    """Базовий клас для всіх моделей SQLAlchemy з автоматичним ім'ям таблиці."""
    pass
    # Можна додати загальні поля або методи сюди, якщо потрібно

# --- Створення асинхронного двигуна SQLAlchemy (engine) НА РІВНІ МОДУЛЯ ---
# `engine` тепер буде доступний для імпорту з цього модуля.
# Переконуємося, що DATABASE_URL завантажено.
if not app_config.DATABASE_URL:
    logger.error("DATABASE_URL is not set. Database engine cannot be created.")
    # Можна викликати sys.exit() або підняти виняток, якщо БД критично важлива
    # Для скрипта init_db_tables.py це буде оброблено окремо.
    engine = None 
else:
    try:
        engine = create_async_engine(
            app_config.DATABASE_URL,
            echo=False,  # Встановіть в True для логування SQL-запитів (корисно для відладки)
            # pool_size=10, # Опціонально: налаштування пулу з'єднань
            # max_overflow=20 # Опціонально
        )
        logger.info(f"Async SQLAlchemy engine created for URL (hidden credentials): {app_config.DATABASE_URL.split('@')[-1] if '@' in app_config.DATABASE_URL else app_config.DATABASE_URL}")
    except Exception as e:
        logger.exception("Failed to create SQLAlchemy engine at module level.", exc_info=e)
        engine = None # Встановлюємо в None, щоб подальші перевірки могли це обробити

# --- Фабрика асинхронних сесій (буде ініціалізована в initialize_database) ---
# Залишаємо async_session_factory як Optional, оскільки вона залежить від успішного створення engine
async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

async def initialize_database() -> Tuple[bool, Optional[async_sessionmaker[AsyncSession]]]:
    """
    Ініціалізує базу даних: створює таблиці (якщо їх немає) та фабрику сесій.
    Повертає кортеж (успіх_ініціалізації_бд, фабрика_сесій_або_None).
    """
    global async_session_factory # Оголошуємо, що будемо змінювати глобальну змінну модуля

    if not engine: # Якщо двигун не вдалося створити на рівні модуля
        logger.error("Database engine is not available. Cannot initialize database.")
        return False, None

    logger.info("Attempting database initialization (tables and session factory)...")
    
    try:
        # Створення таблиць (тільки якщо вони ще не існують)
        # Base.metadata.create_all(bind=engine) - це для синхронного коду
        # Для асинхронного:
        async with engine.begin() as conn:
            # Імпортуємо моделі тут, щоб переконатися, що вони зареєстровані в Base.metadata
            # ДО того, як викликається create_all.
            # Це краще робити на рівні модуля, де визначається Base, або в __init__.py пакету models.
            # Але для простоти, якщо моделі в src.db.models, вони вже мають бути завантажені.
            # from src.db import models # Переконайтеся, що цей імпорт завантажує всі ваші моделі
            
            logger.info("Creating/checking database tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.")

        # Створення фабрики сесій
        async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False # Рекомендується для асинхронних сесій
        )
        logger.info("Database session factory created.")
        return True, async_session_factory
    except ConnectionRefusedError:
        logger.error(f"Database connection refused during initialization. URL: {app_config.DATABASE_URL}")
        return False, None
    except Exception as e:
        logger.exception("An error occurred during database initialization:", exc_info=e)
        return False, None

async def get_db_session() -> AsyncSession:
    """
    Залежність (dependency) для отримання сесії бази даних.
    Використовується в мідлварі або напряму в обробниках.
    """
    if not async_session_factory:
        logger.error("async_session_factory is not initialized. Call initialize_database() first.")
        # У реальному додатку це має бути критичною помилкою або оброблятися інакше.
        # Наприклад, можна спробувати ініціалізувати тут, але це не найкраща практика.
        raise RuntimeError("Database session factory not initialized.")
    
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

# Для використання в DbSessionMiddleware, який може не використовувати async generator
def get_db_session_context() -> async_sessionmaker[AsyncSession]:
    if not async_session_factory:
        raise RuntimeError("Database session factory not initialized for context.")
    return async_session_factory

# --- Закриття двигуна (engine) ---