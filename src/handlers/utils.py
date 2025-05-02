# src/handlers/utils.py

import logging
from typing import Union
from aiogram.types import Message, CallbackQuery

logger = logging.getLogger(__name__)

async def show_main_menu_message(target: Union[Message, CallbackQuery]):
    """ Отправляет/редактирует сообщение, напоминая о главном меню. """
    text = "Головне меню доступне через кнопки нижче 👇" # Корректный текст
    target_message = target.message if isinstance(target, CallbackQuery) else target
    try:
        # Пытаемся отредактировать без инлайн клавиатуры
        await target_message.edit_text(text, reply_markup=None)
        logger.debug(f"Edited message {target_message.message_id} to show main menu text.")
    except Exception as edit_err:
         logger.warning(f"Could not edit message to show main menu text ({edit_err}), sending new one.")
         try:
             # Если не вышло, отправляем новое сообщение
             await target_message.answer(text, reply_markup=None)
             logger.debug(f"Sent new message with main menu text to chat {target_message.chat.id}.")
         except Exception as send_err:
              logger.error(f"Could not send main menu message either: {send_err}")
    finally:
        # Отвечаем на колбэк, если он был
        if isinstance(target, CallbackQuery):
            try:
                await target.answer()
            except Exception as answer_err:
                 logger.warning(f"Could not answer callback query for main menu message: {answer_err}")