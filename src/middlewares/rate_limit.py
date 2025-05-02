# src/middlewares/rate_limit.py

import time
import logging
from typing import Callable, Dict, Any, Awaitable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from aiogram.dispatcher.flags import get_flag

logger = logging.getLogger(__name__)

class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, default_rate: float = 0.5):
        super().__init__()
        self.rate_limit = default_rate
        self.user_last_request: Dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        if not isinstance(event, (Message, CallbackQuery)):
            return await handler(event, data)

        user = event.from_user
        if not user:
            return await handler(event, data)

        user_id = user.id
        current_time = time.monotonic()

        if get_flag(data, "no_throttle"):
            logger.debug(f"Throttling skipped for user {user_id} due to 'no_throttle' flag.")
            return await handler(event, data)

        last_request_time = self.user_last_request.get(user_id)

        if last_request_time:
            elapsed = current_time - last_request_time
            if elapsed < self.rate_limit:
                logger.warning(f"User {user_id} throttled. Elapsed: {elapsed:.3f} < Limit: {self.rate_limit}")
                if isinstance(event, CallbackQuery):
                    await event.answer("Не так швидко! Будь ласка, зачекайте.", show_alert=False)
                return  # Прерываем выполнение без вызова обработчика

        self.user_last_request[user_id] = current_time
        return await handler(event, data)
