# src/modules/currency/handlers.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F # <<< Добавили Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession # Пока не используется здесь

# from src.handlers.utils import show_main_menu_message # Импорт внутри handle_currency_back
from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard,
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH
)

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

# --- Точка входа (без изменений) ---
async def currency_entry_point(target: Union[Message, CallbackQuery]):
    user_id = target.from_user.id; logger.info(f"User {user_id} requested currency rates."); text = "🏦 Оберіть тип курсу:"; reply_markup = get_currency_type_keyboard(); message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    if isinstance(target, CallbackQuery): await target.answer(); try: await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
         except Exception as e: logger.error(f"Error editing msg: {e}"); await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
    else: await target.answer(text, reply_markup=reply_markup)

# --- ИЗМЕНЯЕМ ЭТУ ФУНКЦИЮ: Добавляем bot ---
async def _show_rates(bot: Bot, callback: CallbackQuery, cash: bool): # <<< Добавили bot
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id
    await callback.answer() # Отвечаем на колбэк сразу
    try: await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    except Exception as e: logger.warning(f"Could not edit message before showing rates: {e}")

    rates = await get_pb_exchange_rates(bot, cash=cash) # <<< Передаем bot
    reply_markup = None # Клавиатура не нужна

    if rates: message_text = format_rates_message(rates, rate_type_name); logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
    else: message_text = f"😔 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."; logger.warning(f"Failed to get {rate_type_name} rates for user {user_id}.")

    try: await callback.message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e: logger.error(f"Failed edit msg with rates: {e}"); try: await callback.message.answer(message_text, reply_markup=reply_markup)
         except Exception as e2: logger.error(f"Failed send new msg with rates: {e2}")

# --- ИЗМЕНЯЕМ ВЫЗОВЫ: Передаем bot ---
@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery, bot: Bot): # <<< Добавили bot
    await _show_rates(bot, callback, cash=True) # <<< Передаем bot

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery, bot: Bot): # <<< Добавили bot
    await _show_rates(bot, callback, cash=False) # <<< Передаем bot

# Обработчик Назад здесь не нужен, т.к. нет инлайн кнопки Назад