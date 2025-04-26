# src/modules/currency/handlers.py

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession # На случай, если понадобится сессия

# Импортируем функции и объекты из других модулей
from src.keyboards.inline_main import CALLBACK_CURRENCY # Колбэк из главного меню
from src.handlers.common import show_main_menu # Функция возврата в меню
from .service import get_pb_exchange_rates, format_rates_message # Сервис валют
from .keyboard import ( # Клавиатуры валют
    get_currency_type_keyboard, get_currency_back_keyboard,
    CALLBACK_CURRENCY_CASH, CALLBACK_CURRENCY_NONCASH, CALLBACK_CURRENCY_BACK
)

logger = logging.getLogger(__name__)

# Создаем роутер для модуля валют
router = Router(name="currency-module")

# --- Обработчики ---

@router.callback_query(F.data == CALLBACK_CURRENCY)
async def handle_currency_entry(callback: CallbackQuery):
    """ Точка входа в модуль валют. Предлагает выбрать тип курса. """
    logger.info(f"User {callback.from_user.id} requested currency rates.")
    text = "🏦 Оберіть тип курсу:"
    reply_markup = get_currency_type_keyboard()
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await callback.answer()


async def _show_rates(callback: CallbackQuery, cash: bool):
    """ Вспомогательная функция для запроса и отображения курсов. """
    rate_type_name = "Готівковий курс ПриватБанку" if cash else "Безготівковий курс ПриватБанку"
    user_id = callback.from_user.id

    # Показываем "загрузку"
    await callback.message.edit_text(f"⏳ Отримую {rate_type_name.lower()}...")
    await callback.answer() # Отвечаем на колбэк сразу

    rates = await get_pb_exchange_rates(cash=cash)

    if rates:
        message_text = format_rates_message(rates, rate_type_name)
        reply_markup = get_currency_back_keyboard()
        await callback.message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"Sent {rate_type_name} rates to user {user_id}.")
    else:
        error_text = f"😔 Не вдалося отримати {rate_type_name.lower()}. Спробуйте пізніше."
        reply_markup = get_currency_back_keyboard()
        await callback.message.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"Failed to get {rate_type_name} rates for user {user_id}.")


@router.callback_query(F.data == CALLBACK_CURRENCY_CASH)
async def handle_cash_rates_request(callback: CallbackQuery):
    """ Обрабатывает запрос наличного курса. """
    await _show_rates(callback, cash=True)


@router.callback_query(F.data == CALLBACK_CURRENCY_NONCASH)
async def handle_noncash_rates_request(callback: CallbackQuery):
    """ Обрабатывает запрос безналичного курса. """
    await _show_rates(callback, cash=False)


@router.callback_query(F.data == CALLBACK_CURRENCY_BACK)
async def handle_currency_back(callback: CallbackQuery):
    """ Обрабатывает кнопку 'Назад в меню' из модуля валют. """
    logger.info(f"User {callback.from_user.id} requested back to main menu from currency.")
    await show_main_menu(callback) # Используем общую функцию для возврата

# --- Конец обработчиков ---