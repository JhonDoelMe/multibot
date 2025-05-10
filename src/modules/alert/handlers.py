# src/modules/alert/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession # Пока не используется

# from src.handlers.utils import show_main_menu_message # Импорт внутри handle_alert_back
from .service import get_active_alerts, format_alerts_message
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

# --- ИЗМЕНЯЕМ ЭТУ ФУНКЦИЮ: Добавляем bot ---
async def _show_alerts(bot: Bot, target: Union[Message, CallbackQuery]): # <<< Добавили bot
    """ Запрашивает и отображает статус тревог, используя сессию бота. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None

    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при отправке/редактировании статусного сообщения
    try: # Отправка статуса
        if isinstance(target, CallbackQuery):
            try: status_message = await message_to_edit_or_answer.edit_text("⏳ Отримую актуальний статус тривог...")
            except Exception as e: logger.error(f"Error editing message for initial status in _show_alerts (callback): {e}"); try: status_message = await target.message.answer("⏳ Отримую актуальний статус тривог..."); except Exception as e2: logger.error(f"Error sending new message for initial status (callback fallback): {e2}"); status_message = message_to_edit_or_answer # Final fallback
            try: await target.answer()
            except Exception as e: logger.warning(f"Could not answer callback after status message: {e}")
        else: # Message
            try: status_message = await message_to_edit_or_answer.answer("⏳ Отримую актуальний статус тривог...")
            except Exception as e: logger.error(f"Error sending message for initial status in _show_alerts (message): {e}"); status_message = message_to_edit_or_answer # Fallback
    except Exception as e:
         logger.error(f"Unexpected error before sending/editing status message for alerts: {e}")
         status_message = message_to_edit_or_answer # Ensure status_message is set even on error


    alerts_data = await get_active_alerts(bot) # <<< Передаем bot
    message_text = format_alerts_message(alerts_data)
    reply_markup = get_alert_keyboard()

    # Определяем финальное сообщение для редактирования
    final_target_message = status_message if status_message else message_to_edit_or_answer

    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при редактировании/отправке финального сообщения
    try: # Редактирование финального сообщения
        await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent alert status to user {user_id}.")
    except Exception as e: # Обработка ошибок редактирования/отправки
         logger.error(f"Error editing message for alert status: {e}")
         try:
             await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Error sending new message for alert status: {e2}")

# --- ИЗМЕНЯЕМ ВЫЗОВЫ: Передаем bot ---
async def alert_entry_point(target: Union[Message, CallbackQuery], bot: Bot): # <<< Добавили bot
    """ Точка входа в модуль тревог. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status.")
    await _show_alerts(bot, target) # <<< Передаем bot

@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery, bot: Bot): # <<< Добавили bot
    """ Обрабатывает кнопку 'Обновить'. """
    logger.info(f"User {callback.from_user.id} requested alert status refresh.")
    await _show_alerts(bot, callback) # <<< Передаем bot

# Обработчик Назад здесь не нужен