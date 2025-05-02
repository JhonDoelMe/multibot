# src/modules/currency/handlers.py

import logging
from typing import Union, Optional # Добавили Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup # Добавили InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

# from src.handlers.common import show_main_menu_message # Убрали импорт
from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard, # Убрали get_currency_back_keyboard
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH # Убрали CALLBACK_CURRENCY_BACK
)

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

async def currency_entry_point(target: Union[Message, CallbackQuery]):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested currency rates.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard() # Клавиатура выбора типа
    if isinstance(target, CallbackQuery):
        await target.answer()
        # Редактируем сообщение, добавляя клавиатуру выбора
        await target.message.edit_text(text, reply_markup=reply_markup)
    else:
        # Отправляем новое сообщение с клавиатурой выбора
        await target.answer(text, reply_markup=reply_markup)


async def _show_rates(callback: CallbackQuery, cash: bool):
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id
    # Сразу отвечаем на колбэк выбора типа курса
    await callback.answer()
    # Редактируем сообщение на "Загрузка..." БЕЗ клавиатуры
    try:
        await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    except Exception as e:
        logger.warning(f"Could not edit message before showing rates: {e}")

    rates = await get_pb_exchange_rates(cash=cash)
    # reply_markup = get_currency_back_keyboard() # <<< УБИРАЕМ кнопку Назад
    reply_markup = None # <<< Устанавливаем None

    if rates:
        message_text = format_rates_message(rates, rate_type_name)
        logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
    else:
        message_text = f"😔 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."
        logger.warning(f"Failed to get {rate_type_name} rates for user {user_id}.")
    # Редактируем сообщение, показывая курсы БЕЗ инлайн клавиатуры
    try:
         await callback.message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e:
         logger.error(f"Failed to edit message with rates: {e}")
         # Если не вышло редактировать, новое тоже не шлем, т.к. показать нечего

@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=True)

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=False)

# УДАЛЯЕМ обработчик handle_currency_back
# @router.callback_query(F.data == CALLBACK_CURRENCY_BACK) ...