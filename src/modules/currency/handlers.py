# src/modules/currency/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery

from .service import get_pb_exchange_rates, format_rates_message
from .keyboard import (
    get_currency_type_keyboard,
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH
)

logger = logging.getLogger(__name__)
router = Router(name="currency-module")

async def currency_entry_point(target: Union[Message, CallbackQuery], bot: Bot):
    user_id = target.from_user.id
    logger.info(f"User {user_id} requested currency rates entry point.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard()
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target

    if isinstance(target, CallbackQuery):
        try: await target.answer()
        except Exception as e: logger.warning(f"Could not answer callback in currency_entry_point: {e}")
        try:
            await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message in currency_entry_point: {e}")
            try:
                await message_to_edit_or_answer.answer(text, reply_markup=reply_markup) # Fallback
            except Exception as e2:
                 logger.error(f"Could not send new message either in currency_entry_point: {e2}")
    else: # Message
        try:
            await target.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending message in currency_entry_point: {e}")


async def _show_rates(bot: Bot, callback: CallbackQuery, cash: bool):
    user_id = callback.from_user.id
    rate_type_name_log = "готівкового" if cash else "безготівкового"
    logger.info(f"User {user_id} requested {rate_type_name_log} currency rates.")
    
    answered_callback = False # Прапорець, щоб відстежити, чи відповіли ми на колбек
    status_message = None
    try:
        await callback.answer() 
        answered_callback = True
    except Exception as e:
        logger.warning(f"Could not answer callback immediately in _show_rates for user {user_id}: {e}")

    try:
        status_message = await callback.message.edit_text(f"⏳ Отримую {rate_type_name_log} курс...")
    except Exception as e:
        logger.warning(f"Could not edit message to 'loading' status for user {user_id}: {e}")

    api_response_wrapper = await get_pb_exchange_rates(bot, cash=cash)
    message_text = format_rates_message(api_response_wrapper, cash=cash)
    target_message_for_result = status_message if status_message else callback.message

    try:
        if status_message: 
            await target_message_for_result.edit_text(message_text, reply_markup=None)
        else: 
            await callback.message.answer(message_text, reply_markup=None)
        logger.info(f"Sent currency rates (type: {rate_type_name_log}) to user {user_id}.")
    except Exception as e:
        logger.error(f"Failed to send/edit final currency rates message to user {user_id}: {e}")
        try:
            if not status_message:
                 await callback.message.answer("😥 Вибачте, сталася помилка при відображенні курсів.", reply_markup=None)
        except Exception as e2:
            logger.error(f"Truly unable to communicate currency rates error to user {user_id}: {e2}")
    finally:
        # ВИПРАВЛЕНО: Просто намагаємося відповісти, якщо ще не відповіли.
        # Aiogram сам обробить, якщо відповідь вже була.
        if not answered_callback:
             try: 
                 await callback.answer()
             except Exception as e:
                 # Логуємо, якщо відповідь не вдалася навіть тут (малоймовірно, але можливо)
                 logger.warning(f"Final attempt to answer callback for user {user_id} also failed: {e}")


@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery, bot: Bot):
    await _show_rates(bot, callback, cash=True)

@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery, bot: Bot):
    await _show_rates(bot, callback, cash=False)