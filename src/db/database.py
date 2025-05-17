# src/db/database.py

import logging
from typing import Tuple, Optional

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

# Імпортуємо конфігурацію для доступу до DATABASE_URL
from src import config as app_config # <--- ПОВЕРНУЛИ до 'from src import config'

logger = logging.getLogger(__name__)

# --- Визначення Base для моделей ---
class Base(DeclarativeBase):
    """Базовий клас для всіх моделей SQLAlchemy з автоматичним ім'ям таблиці."""
    pass

# --- Створення асинхронного двигуна SQLAlchemy (engine) НА РІВНІ МОДУЛЯ ---
if not hasattr(app_config, 'DATABASE_URL') or not app_config.DATABASE_URL: 
    logger.error("DATABASE_URL is not set. Database engine cannot be created.")
    engine = None 
else:
    try:
        engine = create_async_engine(
            app_config.DATABASE_URL,
            echo=False, 
        )
        db_url_display = app_config.DATABASE_URL
        if '@' in db_url_display:
            db_url_display = db_url_display.split('@', 1)[-1]
        logger.info(f"Async SQLAlchemy engine created for URL (hidden credentials): {db_url_display}")
    except Exception as e:
        logger.exception("Failed to create SQLAlchemy engine at module level.", exc_info=e)
        engine = None 

async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None

async def initialize_database() -> Tuple[bool, Optional[async_sessionmaker[AsyncSession]]]:
    global async_session_factory 

    if not engine: 
        logger.error("Database engine is not available. Cannot initialize database.")
        return False, None

    logger.info("Attempting database initialization (tables and session factory)...")
    
    try:
        async with engine.begin() as conn:
            # Імпорт моделей потрібен тут, щоб Base.metadata знав про них
            from src.db import models 
            logger.info("Creating/checking database tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.")

        async_session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False 
        )
        logger.info("Database session factory created.")
        return True, async_session_factory
    except ConnectionRefusedError:
        db_url_display = app_config.DATABASE_URL
        if '@' in db_url_display:
            db_url_display = db_url_display.split('@', 1)[-1]
        logger.error(f"Database connection refused during initialization. URL: {db_url_display}")
        return False, None
    except Exception as e:
        logger.exception("An error occurred during database initialization:", exc_info=e)
        return False, None

async def get_db_session() -> AsyncSession: 
    if not async_session_factory:
        logger.error("async_session_factory is not initialized. Call initialize_database() first.")
        raise RuntimeError("Database session factory not initialized.")
    
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def get_db_session_context() -> async_sessionmaker[AsyncSession]: 
    if not async_session_factory:
        raise RuntimeError("Database session factory not initialized for context.")
    return async_session_factory