# src/db/database.py (без print)

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
    logger.info("Attempting database initialization...") # Оставили лог

    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Database features disabled.")
        return False, None

    logger.info(f"Initializing database connection for: {DATABASE_URL.split('@')[-1]}") # Оставили лог

    temp_engine = None
    temp_session_factory = None
    try:
        logger.info("Creating async engine...") # Оставили лог
        temp_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        logger.info("Database engine created.") # Оставили лог

        logger.info("Creating session factory...") # Оставили лог
        temp_session_factory = async_sessionmaker(temp_engine, expire_on_commit=False)
        logger.info("Database session factory created.") # Оставили лог

        async with temp_engine.begin() as conn:
            logger.info("Creating/checking database tables...") # Оставили лог
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database tables checked/created successfully.") # Оставили лог

        logger.info("Database initialization successful.") # Оставили лог
        return True, temp_session_factory

    except Exception as e:
        logger.exception(f"Failed to initialize database or connect: {e}", exc_info=True) # Оставили лог ошибки
        return False, None

# Удалили get_db_session