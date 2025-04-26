# src/modules/alert/handlers.py

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession # Пока не используется, но может пригодиться

# Импортируем функции и объекты из других модулей
from src.keyboards.inline_main import CALLBACK_ALERT # Колбэк из главного меню
from src.handlers.common import show_main_menu # Функция возврата в меню
from .service import get_active_alerts, format_alerts_message # Сервис тревог
from .keyboard import get_alert_keyboard, CALLBACK_ALERT_REFRESH, CALLBACK_ALERT_BACK # Клавиатуры тревог

logger = logging.getLogger(__name__)

# Создаем роутер для модуля тревог
router = Router(name="alert-module")

# --- Вспомогательная функция ---
async def _show_alerts(callback: CallbackQuery):
    """ Запрашивает и отображает статус тревог """
    user_id = callback.from_user.id
    # Показываем "загрузку" и отвечаем на колбэк
    await callback.message.edit_text("⏳ Отримую актуальний статус тривог...")
    await callback.answer()

    alerts_data = await get_active_alerts()
    message_text = format_alerts_message(alerts_data)
    reply_markup = get_alert_keyboard()

    try:
        await callback.message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent alert status to user {user_id}.")
    except Exception as e:
         # Может возникнуть ошибка, если сообщение не изменилось (редко)
         logger.error(f"Error editing message for alert status: {e}")
         # Попробуем отправить новое сообщение, если редактирование не удалось
         try:
             await callback.message.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Error sending new message for alert status: {e2}")


# --- Обработчики ---

@router.callback_query(F.data == CALLBACK_ALERT)
async def handle_alert_entry(callback: CallbackQuery):
    """ Точка входа в модуль тревог. Сразу показывает статус. """
    logger.info(f"User {callback.from_user.id} requested alert status.")
    await _show_alerts(callback)


@router.callback_query(F.data == CALLBACK_ALERT_REFRESH)
async def handle_alert_refresh(callback: CallbackQuery):
    """ Обрабатывает кнопку 'Обновить' """
    logger.info(f"User {callback.from_user.id} requested alert status refresh.")
    await _show_alerts(callback)


@router.callback_query(F.data == CALLBACK_ALERT_BACK)
async def handle_alert_back(callback: CallbackQuery):
    """ Обрабатывает кнопку 'Назад в меню' из модуля тревог. """
    logger.info(f"User {callback.from_user.id} requested back to main menu from alerts.")
    await show_main_menu(callback) # Используем общую функцию для возврата

# --- Конец обработчиков ---