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

# Импортируем URL базы данных из конфигурации
from src.config import DATABASE_URL

logger = logging.getLogger(__name__)

# Проверяем, задан ли URL базы данных
if not DATABASE_URL:
    logger.error("DATABASE_URL is not set in the environment variables or .env file.")
    # В реальном приложении здесь можно либо выйти, либо работать без БД,
    # установив engine и session_factory в None и проверяя их перед использованием.
    # Пока просто создадим None, чтобы код ниже не падал при импорте.
    async_engine = None
    async_session_factory = None
else:
    logger.info(f"Connecting to database: {DATABASE_URL}")
    # Создаем асинхронный "движок" SQLAlchemy
    # echo=True - выводит все SQL-запросы в лог (полезно для отладки)
    # echo=False - отключает вывод запросов (для production)
    async_engine = create_async_engine(DATABASE_URL, echo=False)

    # Создаем фабрику асинхронных сессий
    # expire_on_commit=False рекомендуется для asyncio, чтобы объекты были доступны после коммита
    async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

# Базовый класс для декларативных моделей SQLAlchemy
# AsyncAttrs позволяет использовать await для загрузки связанных данных (lazy loading)
class Base(AsyncAttrs, DeclarativeBase):
    pass

# Функция для инициализации БД (создания таблиц)
async def init_db():
    """Инициализирует базу данных, создавая все таблицы."""
    if not async_engine:
        logger.error("Database engine is not initialized. Cannot init DB.")
        return
    async with async_engine.begin() as conn:
        logger.info("Dropping and creating tables...") # Опционально: удалить старые таблицы
        # await conn.run_sync(Base.metadata.drop_all) # Раскомментируйте для удаления таблиц перед созданием
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Tables created successfully.")

# Функция-генератор для получения сессии БД (для использования с Depends или middleware)
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Генератор для получения сессии базы данных."""
    if not async_session_factory:
        logger.error("Session factory is not initialized. Cannot get DB session.")
        yield None # Возвращаем None, если фабрика не создана
        return

    async with async_session_factory() as session:
        try:
            yield session
            await session.commit() # Коммитим изменения, если все прошло успешно
        except Exception as e:
            logger.exception(f"Database session rollback due to exception: {e}")
            await session.rollback() # Откатываем изменения при ошибке
            raise # Пробрасываем исключение дальше
        finally:
            # Сессия автоматически закрывается при выходе из `async with`
            pass