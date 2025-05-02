# src/modules/alert/handlers.py

import logging
from typing import Union
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

# Import moved inside handle_alert_back
# from src.handlers.common import show_main_menu_message
from .service import get_active_alerts, format_alerts_message
# Only refresh callback is needed from keyboard
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

async def _show_alerts(target: Union[Message, CallbackQuery]):
    """ Gets and shows alert status. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    try:
        # Edit/send "loading" message
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("⏳ Отримую актуальний статус тривог...")
             await target.answer()
        else:
             status_message = await message_to_edit_or_answer.answer("⏳ Отримую актуальний статус тривог...")
    except Exception as e:
         logger.error(f"Error sending/editing status message for alerts: {e}")
         status_message = message_to_edit_or_answer # Fallback

    alerts_data = await get_active_alerts()
    message_text = format_alerts_message(alerts_data)
    # Get keyboard with only "Refresh" button
    reply_markup = get_alert_keyboard()

    # Edit the status message to show the result
    final_target_message = status_message if status_message else message_to_edit_or_answer
    try:
        await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent alert status to user {user_id}.")
    except Exception as e:
         logger.error(f"Error editing message for alert status: {e}")
         try:
             # If edit failed, try sending new message
             await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Error sending new message for alert status: {e2}")


async def alert_entry_point(target: Union[Message, CallbackQuery]):
    """ Entry point for alerts module. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status.")
    await _show_alerts(target)


@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery):
    """ Handles 'Refresh' button. """
    logger.info(f"User {callback.from_user.id} requested alert status refresh.")
    # Call _show_alerts again, passing the callback query
    await _show_alerts(callback)

# No back button handler needed here anymore