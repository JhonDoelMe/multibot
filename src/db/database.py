# src/db/database.py

import logging
import sys
from typing import AsyncGenerator, Tuple, Optional

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

# Убрали engine/factory отсюда

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def initialize_database() -> Tuple[bool, Optional[async_sessionmaker[AsyncSession]]]:
    logger.info("Attempting database initialization...")

    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Database features disabled.")
        return False, None

    logger.info(f"Initializing database connection for: {DATABASE_URL.split('@')[-1]}") # ИСПРАВЛЕНИЕ: Уровень INFO
    # Логирование полного URL в DEBUG может быть полезно для отладки
    logger.debug(f"Full DATABASE_URL: {DATABASE_URL}")

    temp_engine = None
    temp_session_factory = None
    try:
        logger.info("Creating async engine...") # ИСПРАВЛЕНИЕ: Уровень INFO
        temp_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        logger.info("Database engine created.") # ИСПРАВЛЕНИЕ: Уровень INFO

        logger.info("Creating session factory...") # ИСПРАВЛЕНИЕ: Уровень INFO
        temp_session_factory = async_sessionmaker(temp_engine, expire_on_commit=False)
        logger.info("Database session factory created.") # ИСПРАВЛЕНИЕ: Уровень INFO

        async with temp_engine.begin() as conn:
            logger.info("Creating/checking database tables...") # ИСПРАВЛЕНИЕ: Уровень INFO
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.") # ИСПРАВЛЕНИЕ: Уровень INFO

        logger.info("Database initialization successful.")
        return True, temp_session_factory

    except Exception as e:
        logger.exception(f"Failed to initialize database or connect: {e}", exc_info=True)
        return False, None

# Удалили get_db_session