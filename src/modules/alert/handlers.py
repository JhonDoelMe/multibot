# src/modules/alert/handlers.py

import logging
from typing import Union
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup # Добавили InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

# Убираем импорты show_main_menu_message и CALLBACK_ALERT_BACK
# from src.handlers.common import show_main_menu_message
from .service import get_active_alerts, format_alerts_message
# Убрали CALLBACK_ALERT_BACK из импорта клавиатур
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

async def _show_alerts(target: Union[Message, CallbackQuery]):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    try:
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("⏳ Отримую актуальний статус тривог...")
             await target.answer()
        else:
             status_message = await message_to_edit_or_answer.answer("⏳ Отримую актуальний статус тривог...")
    except Exception as e:
         logger.error(f"Error sending/editing status message for alerts: {e}")
         status_message = message_to_edit_or_answer

    alerts_data = await get_active_alerts()
    message_text = format_alerts_message(alerts_data)
    reply_markup = get_alert_keyboard() # <<< Клавиатура только с кнопкой Обновить
    try:
        # Редактируем сообщение, показывая статус и кнопку Обновить
        await status_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent alert status to user {user_id}.")
    except Exception as e: # ... (обработка ошибок редактирования) ...
         logger.error(f"Error editing message for alert status: {e}")
         try: await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
         except Exception as e2: logger.error(f"Error sending new message for alert status: {e2}")


async def alert_entry_point(target: Union[Message, CallbackQuery]):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status.")
    await _show_alerts(target)


@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} requested alert status refresh.")
    await _show_alerts(callback)

# УДАЛЯЕМ обработчик handle_alert_back
# @router.callback_query(F.data == CALLBACK_ALERT_BACK) ...