# src/middlewares/db_session.py

import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

logger = logging.getLogger(__name__)

class DbSessionMiddleware(BaseMiddleware):
    """
    Middleware для добавления сессии SQLAlchemy в каждый обработчик.
    """
    def __init__(self, session_pool: async_sessionmaker[AsyncSession]):
        super().__init__()
        # Сохраняем фабрику сессий (session pool)
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        """
        Выполняется для каждого входящего события.

        Открывает сессию БД, передает ее в data['session'] для хэндлера,
        и автоматически закрывает/коммитит/откатывает сессию после выполнения хэндлера.
        """
        # Открываем сессию из пула перед вызовом хэндлера
        async with self.session_pool() as session:
            # Добавляем объект сессии в словарь data,
            # который будет доступен в хэндлере по ключу 'session'
            data['session'] = session

            try:
                logger.debug("DbSessionMiddleware: Before handler")
                # Вызываем следующий middleware или сам хэндлер, передавая событие и обновленные данные
                result = await handler(event, data)
                logger.debug("DbSessionMiddleware: Handler executed successfully, attempting commit")

                # Коммит, если не было исключений
                await session.commit()
                logger.debug("DbSessionMiddleware: Database session committed.")

            except Exception as e:
                logger.warning(f"DbSessionMiddleware: Exception occurred: {e}, rolling back")
                # Откат при любой ошибке
                await session.rollback()
                logger.warning("DbSessionMiddleware: Database session rolled back.")
                raise e  # Пробрасываем исключение дальше, чтобы его обработали другие обработчики

            finally:
                logger.debug("DbSessionMiddleware: Closing session")
                # Закрываем сессию (теперь это делается автоматически при выходе из async with, но оставим для ясности)
                await session.close()
                logger.debug("DbSessionMiddleware: Database session closed.")

            return result