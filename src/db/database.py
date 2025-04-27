# src/db/database.py (убираем print)

import logging
import sys
from typing import AsyncGenerator

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

async_engine = None
async_session_factory = None

class Base(AsyncAttrs, DeclarativeBase):
    pass

async def initialize_database() -> bool:
    global async_engine, async_session_factory
    # print("--- DB: Attempting initialization...", flush=True)

    if not DATABASE_URL:
        # print("--- DB: ERROR - DATABASE_URL not set.", flush=True)
        logger.error("DATABASE_URL is not set. Database features disabled.")
        return False

    # print(f"--- DB: Database URL found (host part): {DATABASE_URL.split('@')[-1]}", flush=True)

    temp_engine = None
    try:
        # print("--- DB: Creating async engine...", flush=True)
        temp_engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
        # print("--- DB: Testing connection with engine...", flush=True)
        # async with temp_engine.connect() as connection: # Уберем тест соединения на время
        #     pass
        # print("--- DB: Engine connection test successful.", flush=True)
        async_engine = temp_engine
        # print("--- DB: Async engine created and assigned.", flush=True)
        logger.info("Database engine created.") # Оставляем лог

    except Exception as e:
        # print(f"--- DB: !!! EXCEPTION during engine creation or connection test: {e!r}", flush=True)
        # print(f"--- DB: !!! Exception Type: {type(e)}", flush=True)
        logger.exception(f"Failed to create database engine or connect: {e}", exc_info=True)
        async_engine = None
        return False

    if not async_engine:
         logger.error("Engine is None after creation block.") # Логируем ошибку
         return False

    try:
        # print("--- DB: Creating session factory...", flush=True)
        async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
        # print("--- DB: Session factory created.", flush=True)
        logger.info("Database session factory created.") # Оставляем лог

        async with async_engine.begin() as conn:
            # print("--- DB: Connecting and creating tables...", flush=True)
            await conn.run_sync(Base.metadata.create_all)
            # print("--- DB: Tables checked/created.", flush=True)
        logger.info("Database tables checked/created successfully.") # Оставляем лог
        # print("--- DB: Initialization successful.", flush=True)
        return True

    except Exception as e:
        # print(f"--- DB: !!! EXCEPTION during session factory/table creation: {e!r}", flush=True)
        logger.exception(f"Failed to initialize session factory or tables: {e}", exc_info=True)
        async_engine = None
        async_session_factory = None
        return False


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    if not async_session_factory:
        logger.error("Session factory is not initialized. Cannot get DB session.")
        yield None
        return
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            # print("--- DB: !!! EXCEPTION IN SESSION, ROLLING BACK !!!", flush=True)
            logger.exception("Exception in DB session, rolling back.")
            await session.rollback()
            raise