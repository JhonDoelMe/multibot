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
    logger.info("Attempting database initialization...") # Оставили INFO

    if not DATABASE_URL:
        logger.error("DATABASE_URL is not set. Database features disabled.")
        return False, None

    logger.debug(f"Initializing database connection for: {DATABASE_URL.split('@')[-1]}") # Изменено на DEBUG

    temp_engine = None
    temp_session_factory = None
    try:
        logger.debug("Creating async engine...") # Изменено на DEBUG
        temp_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        logger.debug("Database engine created.") # Изменено на DEBUG

        logger.debug("Creating session factory...") # Изменено на DEBUG
        temp_session_factory = async_sessionmaker(temp_engine, expire_on_commit=False)
        logger.debug("Database session factory created.") # Изменено на DEBUG

        async with temp_engine.begin() as conn:
            logger.debug("Creating/checking database tables...") # Изменено на DEBUG
            await conn.run_sync(Base.metadata.create_all)
            logger.debug("Database tables checked/created successfully.") # Изменено на DEBUG

        logger.info("Database initialization successful.") # Оставили INFO
        return True, temp_session_factory

    except Exception as e:
        logger.exception(f"Failed to initialize database or connect: {e}", exc_info=True) # Оставили ERROR
        return False, None

# Удалили get_db_session