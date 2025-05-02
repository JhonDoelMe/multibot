# src/modules/currency/handlers.py

import logging
from typing import Union, Optional
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

# Import moved inside handle_currency_back
# from src.handlers.common import show_main_menu_message
from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard, # No back keyboard needed here now
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH
)

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

async def currency_entry_point(target: Union[Message, CallbackQuery]):
    """ Entry point for currency module. Offers rate type selection. """
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested currency rates.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard()
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target

    if isinstance(target, CallbackQuery):
        await target.answer()
        try:
            await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Error editing message in currency_entry_point: {e}")
             # Send new if edit fails
             await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)


async def _show_rates(callback: CallbackQuery, cash: bool):
    """ Helper to get and show rates. """
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id
    await callback.answer() # Answer callback first

    # Edit message to show loading state WITHOUT inline keyboard
    try:
        await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    except Exception as e:
        logger.warning(f"Could not edit message before showing rates: {e}")

    rates = await get_pb_exchange_rates(cash=cash)
    # No inline keyboard needed after showing rates
    reply_markup = None

    if rates:
        message_text = format_rates_message(rates, rate_type_name)
        logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
    else:
        message_text = f"😔 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."
        logger.warning(f"Failed to get {rate_type_name} rates for user {user_id}.")

    # Edit message to show final result (rates or error) without keyboard
    try:
         await callback.message.edit_text(message_text, reply_markup=reply_markup)
    except Exception as e:
         logger.error(f"Failed to edit message with rates: {e}")
         # Attempt to send new message only if edit failed (less ideal UX)
         try:
             await callback.message.answer(message_text, reply_markup=reply_markup)
         except Exception as e2:
              logger.error(f"Failed even to send new message with rates: {e2}")


@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=True)

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery):
    await _show_rates(callback, cash=False)

# No back button handler needed here anymore