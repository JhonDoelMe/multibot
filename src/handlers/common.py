# src/handlers/common.py

import logging
from typing import Union
from aiogram import Bot, Router, F # <<< Добавили Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.reply_main import get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS
# Импортируем точки входа модулей
from src.modules.weather.handlers import weather_entry_point
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.db.models import User
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")

# --- ИЗМЕНЯЕМ ВЫЗОВЫ: Передаем bot ---
@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext): # bot здесь доступен через message.bot
    await state.clear()
    user = message.from_user; user_id = user.id; first_name = user.first_name; last_name = user.last_name; username = user.username
    db_user = await session.get(User, user_id)
    try: # ... (код регистрации/обновления пользователя) ...
         if db_user: db_user.first_name = first_name; db_user.last_name = last_name; db_user.username = username; session.add(db_user)
         else: logger.info(f"User {user_id} ('{username}') not found. Creating..."); new_user = User(user_id=user_id, first_name=first_name, last_name=last_name, username=username); session.add(new_user)
    except Exception as e: logger.exception(f"DB error during /start: {e}"); await session.rollback(); await message.answer("Помилка БД."); return
    user_name_display = first_name
    text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
     await weather_entry_point(message, state, session, bot) # <<< Передаем bot

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot): # <<< Добавили bot
     await currency_entry_point(message, bot) # <<< Передаем bot

@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot): # <<< Добавили bot
     await alert_entry_point(message, bot) # <<< Передаем bot

# show_main_menu_message остается в utils.py