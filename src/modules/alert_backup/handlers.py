# src/modules/alert_backup/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery

# Імпорти сервісу та клавіатур цього модуля
from .service import get_backup_alerts, format_backup_alerts_message
from .keyboard import get_alert_backup_keyboard, CALLBACK_ALERT_BACKUP_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-backup-module")

async def _show_backup_alerts(bot: Bot, target: Union[Message, CallbackQuery]):
    """ Запитує та відображає резервний статус тривог. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _show_backup_alerts for user {user_id}: {e}")
    
    try:
        loading_text = "⏳ Отримую резервний статус тривог..."
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(loading_text)
        else: # Message
            status_message = await message_to_edit_or_answer.answer(loading_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for backup alerts, user {user_id}: {e}")

    # Запитуємо дані з резервного сервісу
    api_response = await get_backup_alerts(bot) # Тепер це словник
    # Форматуємо повідомлення
    message_text = format_backup_alerts_message(api_response)
    # Отримуємо клавіатуру
    reply_markup = get_alert_backup_keyboard()

    target_message_for_result = status_message if status_message else message_to_edit_or_answer

    try:
        if status_message:
            await target_message_for_result.edit_text(message_text, reply_markup=reply_markup)
        else:
            await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
        logger.info(f"Sent backup alert status to user {user_id}.")
    except Exception as e:
        logger.error(f"Failed to send/edit final backup alert status message to user {user_id}: {e}")
        try:
            if not status_message:
                await message_to_edit_or_answer.answer("😥 Вибачте, сталася помилка при відображенні резервного статусу тривог.", reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Truly unable to communicate backup alert status error to user {user_id}: {e2}")
    finally:
        if isinstance(target, CallbackQuery) and not answered_callback:
            try:
                await target.answer()
            except Exception as e:
                logger.warning(f"Final attempt to answer backup alert callback for user {user_id} also failed: {e}")


async def alert_backup_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    """ Точка входу в модуль резервних тривог. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested backup alert status.")
    await _show_backup_alerts(bot, target)

@router.callback_query(F.data == CALLBACK_ALERT_BACKUP_REFRESH)
async def handle_alert_backup_refresh(callback: CallbackQuery, bot: Bot):
    """ Обробляє кнопку 'Оновити (резерв)'. """
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested backup alert status refresh.")
    await _show_backup_alerts(bot, callback)