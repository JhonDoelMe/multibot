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
    BTN_ALERTS_BACKUP
)
# Импортируем точки входа модулей
from src.modules.weather.handlers import weather_entry_point
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.modules.alert_backup.handlers import alert_backup_entry_point
from src.db.models import User
from src.handlers.utils import show_main_menu_message # Оставляем для возможного использования

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear() # Очищаем состояние при старте
    user_tg = message.from_user
    if not user_tg: # Добавим проверку, что user не None
        logger.warning("Received /start from a user with no user info (message.from_user is None).")
        await message.answer("Не вдалося отримати інформацію про користувача. Спробуйте пізніше.")
        return

    user_id = user_tg.id
    # Используем безопасный вариант с проверкой на None и значением по умолчанию
    first_name = user_tg.first_name if user_tg.first_name else "Користувач"
    last_name = user_tg.last_name # Может быть None
    username = user_tg.username # Может быть None

    db_user = None
    try:
        db_user = await session.get(User, user_id)
        if db_user:
             # Обновляем данные, если они изменились
             needs_update = False
             if db_user.first_name != first_name:
                 db_user.first_name = first_name
                 needs_update = True
             if db_user.last_name != last_name: # Сравниваем, даже если оба None
                 db_user.last_name = last_name
                 needs_update = True
             if db_user.username != username: # Сравниваем, даже если оба None
                 db_user.username = username
                 needs_update = True
             
             if needs_update:
                  logger.info(f"User {user_id} ('{username}') found. Updating info...")
                  session.add(db_user) # Добавляем в сессию только если есть изменения
             else:
                  logger.info(f"User {user_id} ('{username}') found. No info update needed.")
        else:
             logger.info(f"User {user_id} ('{username}') not found. Creating...")
             new_user = User(
                 user_id=user_id,
                 first_name=first_name,
                 last_name=last_name,
                 username=username
             )
             session.add(new_user)
        # Коммит будет выполнен автоматически middleware DbSessionMiddleware
    except Exception as e:
        logger.exception(f"DB error during /start for user {user_id}: {e}", exc_info=True)
        # Важно откатить сессию, если middleware не справится или ошибка до middleware
        await session.rollback()
        await message.answer("Виникла помилка під час роботи з базою даних. Будь ласка, спробуйте пізніше.")
        return # Выходим, если была ошибка БД

    user_name_display = first_name # Используем first_name
    text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_entry_point(message, state, session, bot)

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot): # session здесь не нужен по текущей логике currency_entry_point
     await currency_entry_point(message, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot): # session здесь не нужен
     await alert_entry_point(message, bot)

@router.message(F.text == BTN_ALERTS_BACKUP)
async def handle_alert_backup_text_request(message: Message, bot: Bot): # session здесь не нужен
     await alert_backup_entry_point(message, bot)

# Пример обработчика для неопознанных текстовых сообщений (если нужно)
# @router.message(F.text)
# async def handle_unknown_text(message: Message):
#     await message.answer("Незрозуміла команда. Будь ласка, скористайтеся кнопками меню.")