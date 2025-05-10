# src/modules/currency/handlers.py (Исправлена IndentationError)

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession # Пока не используется здесь

# Импорты сервиса и клавиатур
from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard,
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH
    # Убрали импорт get_currency_back_keyboard и CALLBACK_CURRENCY_BACK
)
# Импорт для кнопки "Назад"
from src.handlers.utils import show_main_menu_message # Используем utils

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

# --- Точка входа (Исправлены отступы в try/except/else) ---
async def currency_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    """ Точка входа в модуль валют. Предлагает выбрать тип курса. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested currency rates.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard() # Клавиатура выбора типа
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target

    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при отправке/редактировании сообщения
    if isinstance(target, CallbackQuery):
        try: await target.answer() # Отвечаем на колбэк
        except Exception as e: logger.warning(f"Could not answer callback in currency_entry_point: {e}")
        # Пытаемся отредактировать сообщение
        try:
            await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            # Если редактирование не удалось, пробуем отправить новое
            logger.error(f"Error editing message in currency_entry_point: {e}")
            try:
                await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
            except Exception as e2:
                 logger.error(f"Could not send new message either in currency_entry_point: {e2}")
    else:
        # Если это было не CallbackQuery (а Message), просто отправляем новое сообщение
        try: await target.answer(text, reply_markup=reply_markup)
        except Exception as e: logger.error(f"Error sending message in currency_entry_point: {e}")


async def _show_rates(bot: Bot, callback: CallbackQuery, cash: bool):
    """ Вспомогательная функция для запроса и отображения курсов. """
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id
    # Отвечаем на колбэк сразу
    try: await callback.answer()
    except Exception as e: logger.warning(f"Could not answer callback in _show_rates: {e}")


    # Редактируем сообщение на "Загрузка..." БЕЗ клавиатуры
    status_message = None
    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при редактировании статусного сообщения
    try:
        status_message = await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    except Exception as e:
        logger.warning(f"Could not edit message before showing rates: {e}")
        status_message = callback.message # Fallback

    rates = await get_pb_exchange_rates(bot, cash=cash) # Передаем bot
    reply_markup = None # Клавиатура после показа курса не нужна

    if rates is not None: # Проверяем, что не None (т.е. не было критической ошибки API)
        message_text = format_rates_message(rates, rate_type_name)
        if "Не вдалося отримати" not in message_text: # Дополнительная проверка на ошибку внутри форматировщика
             logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
        else:
             logger.warning(f"Formatted message indicated error for {rate_type_name} rates for user {user_id}.")
    else:
        message_text = f"😥 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."
        logger.warning(f"Failed to get {rate_type_name} rates for user {user_id} (API service returned None).")

    # Редактируем сообщение, показывая курсы БЕЗ инлайн клавиатуры
    # ИСПРАВЛЕНИЕ: Исправлен синтаксис обработки ошибок при редактировании финального сообщения
    final_target_message = status_message if status_message else callback.message # Ensure final_target_message is set
    try:
         await final_target_message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e:
         logger.error(f"Failed to edit message with rates: {e}")
         try: # Fallback to answer if edit fails
             await callback.message.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Failed even to send new message with rates: {e2}")


@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery, bot: Bot):
    await _show_rates(bot, callback, cash=True)

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery, bot: Bot):
    await _show_rates(bot, callback, cash=False)

# Обработчик кнопки Назад здесь не нужен, так как ее нет в инлайн клавиатурах этого модуля