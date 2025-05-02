# src/modules/currency/handlers.py

import logging
from typing import Union # <<< Добавляем Union
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery # <<< Добавляем Message
from sqlalchemy.ext.asyncio import AsyncSession

# Убираем импорт CALLBACK_CURRENCY из inline_main
# from src.keyboards.inline_main import CALLBACK_CURRENCY
from src.handlers.common import show_main_menu_message # Импортируем новую функцию возврата
from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard, get_currency_back_keyboard,
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH, CALLBACK_CURRENCY_BACK
)

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

# --- Точка входа в модуль Валют ---
# @router.callback_query(F.data == CALLBACK_CURRENCY) # <- Убираем декоратор
async def currency_entry_point(target: Union[Message, CallbackQuery]): # <<< Новое имя и тип
    """ Точка входа в модуль валют. Предлагает выбрать тип курса. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested currency rates.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard()

    if isinstance(target, CallbackQuery):
        # Отвечаем на колбэк и редактируем сообщение
        await target.answer()
        await target.message.edit_text(text, reply_markup=reply_markup)
    else:
        # Отправляем новое сообщение
        await target.answer(text, reply_markup=reply_markup)


async def _show_rates(callback: CallbackQuery, cash: bool):
    """ Вспомогательная функция для запроса и отображения курсов. """
    # (Логика без изменений)
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id
    await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    await callback.answer()
    rates = await get_pb_exchange_rates(cash=cash)
    if rates: # ... (форматирование и отправка) ...
        message_text = format_rates_message(rates, rate_type_name)
        reply_markup = get_currency_back_keyboard()
        await callback.message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
    else: # ... (обработка ошибки) ...
        error_text = f"😔 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."
        reply_markup = get_currency_back_keyboard()
        await callback.message.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"Failed to get {rate_type_name} rates for user {user_id}.")


# Обработчики инлайн-кнопок внутри модуля остаются как есть
@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=True)

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=False)

@router.callback_query(F.data == CALLBACK_CURRENCY_BACK)
async def handle_currency_back(callback: CallbackQuery):
    logger.info(f"User {callback.from_user.id} requested back to main menu from currency.")
    await show_main_menu_message(callback) # Используем новую функцию возврата