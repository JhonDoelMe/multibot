# src/modules/alert/handlers.py

import logging
from typing import Union # <<< Добавляем Union
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery # <<< Добавляем Message
from sqlalchemy.ext.asyncio import AsyncSession

# Убираем импорт CALLBACK_ALERT из inline_main
# from src.keyboards.inline_main import CALLBACK_ALERT
from src.handlers.common import show_main_menu_message # Импортируем новую функцию возврата
from .service import get_active_alerts, format_alerts_message
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH, CALLBACK_ALERT_BACK

logger = logging.getLogger(__name__)
router = Router(name="alert-module")

# --- Вспомогательная функция ---
async def _show_alerts(target: Union[Message, CallbackQuery]): # <<< Изменяем тип target
    """ Запрашивает и отображает статус тревог """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None

    # Показываем "загрузку"
    try:
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("⏳ Отримую актуальний статус тривог...")
             await target.answer() # Отвечаем на колбэк сразу
        else:
             status_message = await message_to_edit_or_answer.answer("⏳ Отримую актуальний статус тривог...")
    except Exception as e:
         logger.error(f"Error sending/editing status message for alerts: {e}")
         status_message = message_to_edit_or_answer # Fallback

    alerts_data = await get_active_alerts()
    message_text = format_alerts_message(alerts_data)
    reply_markup = get_alert_keyboard()

    try:
        await status_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent alert status to user {user_id}.")
    except Exception as e:
         logger.error(f"Error editing message for alert status: {e}")
         try:
             await message_to_edit_or_answer.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Error sending new message for alert status: {e2}")


# --- Точка входа в модуль Тревог ---
# @router.callback_query(F.data == CALLBACK_ALERT) # <<< Убираем декоратор
async def alert_entry_point(target: Union[Message, CallbackQuery]): # <<< Новое имя и тип
    """ Точка входа в модуль тревог. Сразу показывает статус. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested alert status.")
    await _show_alerts(target)

# Обработчики инлайн-кнопок внутри модуля остаются
@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery):
    """ Обрабатывает кнопку 'Обновить' """
    logger.info(f"User {callback.from_user.id} requested alert status refresh.")
    await _show_alerts(callback) # Передаем колбэк в _show_alerts

@router.callback_query(F.data == CALLBACK_ALERT_BACK)
async def handle_alert_back(callback: CallbackQuery):
    """ Обрабатывает кнопку 'Назад в меню' из модуля тревог. """
    logger.info(f"User {callback.from_user.id} requested back to main menu from alerts.")
    await show_main_menu_message(callback) # Используем новую функцию возврата