# src/db/database.py

import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncAttrs
)
from sqlalchemy.orm import DeclarativeBase

from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Определяем переменные на уровне модуля, но инициализируем как None
async_engine = None
async_session_factory = None

# Базовый класс для моделей остается здесь
class Base(AsyncAttrs, DeclarativeBase):
    pass

# --- Модели должны быть импортированы ПОСЛЕ определения Base ---
# (Если бы у нас были модели в других файлах, импортировали бы их тут)
# from src.db.models import User # Пример

async def initialize_database() -> bool:
    """
    Инициализирует асинхронный движок, фабрику сессий и создает таблицы.
    Вызывается один раз при старте приложения.

    Returns:
        True, если инициализация прошла успешно, иначе False.
    """
    global async_engine, async_session_factory # Объявляем, что будем менять глобальные переменные

    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Database features disabled.")
        return False

    logger.info(f"Initializing database connection for: {DATABASE_URL.split('@')[0]}...") # Лог без пароля

    try:
        # --- Создание движка и фабрики сессий ПЕРЕНЕСЕНО СЮДА ---
        async_engine = create_async_engine(DATABASE_URL, echo=False)
        async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        logger.info("Database engine and session factory created.")

        # Проверяем соединение и создаем таблицы
        async with async_engine.begin() as conn:
            logger.info("Creating/checking database tables...")
            # await conn.run_sync(Base.metadata.drop_all) # Раскомментируйте для удаления таблиц при каждом старте
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.")
        return True # Инициализация успешна

    except Exception as e:
        # Логируем полную ошибку, чтобы понять причину сбоя
        logger.exception(f"Failed to initialize database or connect: {e}", exc_info=True)
        # Сбрасываем engine и factory в None при ошибке
        async_engine = None
        async_session_factory = None
        return False # Инициализация не удалась


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """ Генератор для получения сессии базы данных (использует глобальную фабрику). """
    if not async_session_factory:
        # Эта ошибка не должна происходить, если initialize_database() был вызван успешно
        # и middleware зарегистрирован после этого.
        logger.error("Session factory is not initialized. Cannot get DB session.")
        yield None
        return

    async with async_session_factory() as session:
        try:
            yield session
            # Коммит/Роллбэк теперь полностью зависит от Middleware или вызывающего кода
        except Exception:
            logger.exception("Exception in DB session, rolling back.")
            await session.rollback()
            raise
        # finally: # Коммит здесь больше не нужен, Middleware его делает
        #     await session.commit() # УБРАНО