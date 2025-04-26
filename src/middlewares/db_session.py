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

            # Вызываем следующий middleware или сам хэндлер, передавая событие и обновленные данные
            result = await handler(event, data)

            # Коммит или роллбэк сессии происходит автоматически при выходе из `async with`
            # благодаря async_sessionmaker и контекстному менеджеру сессии.
            # Явный commit/rollback не требуется здесь, если не нужна особая логика.

            # logger.debug("Database session committed and closed.") # Для отладки

            return result