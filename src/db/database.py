# src/db/database.py

import logging
import sys
from typing import AsyncGenerator, Tuple, Optional # Добавляем Tuple, Optional

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncAttrs
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.exc import SQLAlchemyError

from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Убираем глобальные переменные engine/factory отсюда
# async_engine = None
# async_session_factory = None

class Base(AsyncAttrs, DeclarativeBase):
    pass

# Возвращаемый тип: кортеж из bool (успех?) и опциональной фабрики сессий
async def initialize_database() -> Tuple[bool, Optional[async_sessionmaker[AsyncSession]]]:
    # global async_engine, async_session_factory # Убираем global

    logger.info("Attempting database initialization...")

    if not DATABASE_URL:
        logger.error("DATABASE_URL not set. Database features disabled.")
        return False, None # Возвращаем неуспех и None для фабрики

    logger.info(f"Initializing database connection for: {DATABASE_URL.split('@')[-1]}")

    temp_engine = None
    temp_session_factory = None
    try:
        logger.info("Creating async engine...")
        temp_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        logger.info("Database engine created.")

        logger.info("Creating session factory...")
        # Создаем фабрику во временную переменную
        temp_session_factory = async_sessionmaker(temp_engine, expire_on_commit=False)
        logger.info("Database session factory created.")

        async with temp_engine.begin() as conn:
            logger.info("Creating/checking database tables...")
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.")

        logger.info("Database initialization successful.")
        # Возвращаем успех и СОЗДАННУЮ ФАБРИКУ
        return True, temp_session_factory

    except Exception as e:
        logger.exception(f"Failed to initialize database or connect: {e}", exc_info=True)
        # Движок и фабрика не были успешно созданы или присвоены
        return False, None # Возвращаем неуспех и None


# !!! Важно: get_db_session теперь не может работать, так как фабрика не глобальна
# !!! Мы должны передавать фабрику в Middleware при регистрации
# async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
#     # Этот код больше не будет работать правильно
#     pass # Нужно удалить или переделать, если понадобится вне middleware