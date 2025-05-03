# src/handlers/common.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.reply_main import (
    get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS,
    BTN_ALERTS_BACKUP # <<< ДОБАВЛЕНО
)
# Импортируем точки входа модулей
from src.modules.weather.handlers import weather_entry_point
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.modules.alert_backup.handlers import alert_backup_entry_point # <<< ДОБАВЛЕНО
from src.db.models import User
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear()
    user = message.from_user
    if not user: # Добавим проверку, что user не None
        logger.warning("Received /start from a user with no user info.")
        return

    user_id = user.id
    first_name = user.first_name or "Користувач" # Добавим значение по умолчанию
    last_name = user.last_name
    username = user.username

    db_user = None
    try:
        db_user = await session.get(User, user_id)
        if db_user:
             # Обновляем данные, если они изменились
             needs_update = False
             if db_user.first_name != first_name:
                 db_user.first_name = first_name
                 needs_update = True
             if db_user.last_name != last_name:
                 db_user.last_name = last_name
                 needs_update = True
             if db_user.username != username:
                 db_user.username = username
                 needs_update = True
             if needs_update:
                  logger.info(f"User {user_id} ('{username}') found. Updating info...")
                  session.add(db_user)
             else:
                  logger.info(f"User {user_id} ('{username}') found. No info update needed.")

        else:
             logger.info(f"User {user_id} ('{username}') not found. Creating...")
             new_user = User(user_id=user_id, first_name=first_name, last_name=last_name, username=username)
             session.add(new_user)
        # Коммит будет выполнен автоматически middleware
    except Exception as e:
        logger.exception(f"DB error during /start for user {user_id}: {e}")
        await session.rollback() # Явный роллбэк при ошибке
        await message.answer("Виникла помилка бази даних. Спробуйте пізніше.")
        return # Выходим, если была ошибка БД

    user_name_display = first_name # Используем first_name, так как он обязателен
    text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_entry_point(message, state, session, bot)

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot):
     await currency_entry_point(message, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot):
     await alert_entry_point(message, bot)

# --- ОБРАБОТЧИК ДЛЯ РЕЗЕРВНОЙ КНОПКИ --- <<< ДОБАВЛЕНО
@router.message(F.text == BTN_ALERTS_BACKUP)
async def handle_alert_backup_text_request(message: Message, bot: Bot):
     await alert_backup_entry_point(message, bot)