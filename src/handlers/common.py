# src/handlers/common.py (убираем commit)

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.keyboards.inline_main import (
    get_main_menu_keyboard,
    CALLBACK_WEATHER,
    CALLBACK_CURRENCY,
    CALLBACK_ALERT
)
from src.db.models import User

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession):
    user = message.from_user
    user_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    username = user.username

    db_user = await session.get(User, user_id)

    try:
        if db_user:
            logger.info(f"User {user_id} ('{username}') found in DB. Updating info.")
            db_user.first_name = first_name
            db_user.last_name = last_name
            db_user.username = username
            # Неявное добавление в сессию при изменении
            # await session.commit() # <<< УБРАНО - Middleware должен сделать коммит
        else:
            logger.info(f"User {user_id} ('{username}') not found. Creating new user.")
            new_user = User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(new_user)
            # await session.commit() # <<< УБРАНО - Middleware должен сделать коммит
            # logger.info(f"Explicit commit after adding new user {user_id}.") # Убрано

    except Exception as e:
        logger.exception(f"Database error during /start for user {user_id}: {e}")
        await message.answer("Виникла помилка при роботі з базою даних.")
        return

    user_name_display = first_name
    text = f"Привіт, {user_name_display}! 👋\n\nЯ твій помічник. Оберіть опцію нижче:"
    reply_markup = get_main_menu_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

# --- Остальные обработчики без изменений ---
@router.callback_query(F.data == CALLBACK_CURRENCY)
async def handle_currency_callback(callback: CallbackQuery):
    await callback.message.edit_text("Ви обрали розділ 'Курс валют'. Функціонал в розробці.")
    await callback.answer()

@router.callback_query(F.data == CALLBACK_ALERT)
async def handle_alert_callback(callback: CallbackQuery):
    await callback.message.edit_text("Ви обрали розділ 'Повітряна тривога'. Функціонал в розробці.")
    await callback.answer()

@router.callback_query(F.data.startswith("main:"))
async def handle_unknown_main_callback(callback: CallbackQuery):
    await callback.answer("Невідома опція!", show_alert=True)

async def show_main_menu(message: Message | CallbackQuery, text: str = "Головне меню. Оберіть опцію:"):
    reply_markup = get_main_menu_keyboard()
    target_message = message.message if isinstance(message, CallbackQuery) else message
    try:
        await target_message.edit_text(text, reply_markup=reply_markup)
    except Exception:
         await target_message.answer(text, reply_markup=reply_markup)
    if isinstance(message, CallbackQuery):
        await message.answer()