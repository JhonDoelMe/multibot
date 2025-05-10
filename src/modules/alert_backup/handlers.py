# src/modules/alert_backup/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery

# Импорты сервиса и клавиатур этого модуля
from .service import get_backup_alerts, format_backup_alerts_message
from .keyboard import get_alert_backup_keyboard, CALLBACK_ALERT_BACKUP_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-backup-module")

async def _show_backup_alerts(bot: Bot, target: Union[Message, CallbackQuery]):
    """ Запрашивает и отображает резервный статус тревог. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None

    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при отправке/редактировании статусного сообщения
    try: # Отправка статуса "Загрузка..."
        if isinstance(target, CallbackQuery):
            try: status_message = await message_to_edit_or_answer.edit_text("⏳ Отримую резервний статус тривог...")
            except Exception as e: logger.error(f"Error editing message for initial status in _show_backup_alerts (callback): {e}"); try: status_message = await target.message.answer("⏳ Отримую резервний статус тривог..."); except Exception as e2: logger.error(f"Error sending new message for initial status (callback fallback): {e2}"); status_message = message_to_edit_or_answer # Final fallback
            try: await target.answer()
            except Exception as e: logger.warning(f"Could not answer callback after status message: {e}")
        else: # Message
            try: status_message = await message_to_edit_or_answer.answer("⏳ Отримую резервний статус тривог...")
            except Exception as e: logger.error(f"Error sending message for initial status in _show_backup_alerts (message): {e}"); status_message = message_to_edit_or_answer # Fallback
    except Exception as e:
        logger.error(f"Unexpected error before sending/editing status message for backup alerts: {e}")
        status_message = message_to_edit_or_answer # Ensure status_message is set even on error


    # Запрашиваем данные из резервного сервиса
    alerts_data = await get_backup_alerts(bot)
    # Форматируем сообщение
    message_text = format_backup_alerts_message(alerts_data)
    # Получаем клавиатуру
    reply_markup = get_alert_backup_keyboard()

    # Определяем финальное сообщение для редактирования
    final_target_message = status_message if status_message else message_to_edit_or_answer

    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при редактировании/отправке финального сообщения
    try: # Редактирование финального сообщения
        await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent backup alert status to user {user_id}.")
    except Exception as e: # Обработка ошибок редактирования/отправки
         logger.error(f"Error editing message for backup alert status: {e}")
         try: # Пытаемся отправить новое сообщение, если редактирование не удалось
             await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Error sending new message for backup alert status: {e2}")

# --- Точка входа для резервного модуля ---
async def alert_backup_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    """ Точка входа в модуль резервных тревог. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested backup alert status.")
    await _show_backup_alerts(bot, target)

@router.callback_query(F.data == CALLBACK_ALERT_BACKUP_REFRESH)
async def handle_alert_backup_refresh(callback: CallbackQuery, bot: Bot):
    """ Обрабатывает кнопку 'Обновить (резерв)'. """
    logger.info(f"User {callback.from_user.id} requested backup alert status refresh.")
    await _show_backup_alerts(bot, callback)