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
    BTN_ALERTS_BACKUP, BTN_WEATHER_BACKUP,
    BTN_LOCATION_MAIN, BTN_LOCATION_BACKUP
)
from src.modules.weather.handlers import weather_entry_point, handle_location as handle_main_weather_location
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.modules.alert_backup.handlers import alert_backup_entry_point
from src.modules.weather_backup.handlers import weather_backup_entry_point, weather_backup_geolocation_entry_point
from src.db.models import User
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")
location_router = Router(name="location-handlers")


@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    # ... (код без изменений) ...
    await state.clear()
    user_tg = message.from_user
    if not user_tg:
        logger.warning("Received /start from a user with no user info (message.from_user is None).")
        await message.answer("Не вдалося отримати інформацію про користувача. Спробуйте пізніше.")
        return

    user_id = user_tg.id
    first_name = user_tg.first_name if user_tg.first_name else "Користувач"
    last_name = user_tg.last_name
    username = user_tg.username

    db_user = None
    try:
        db_user = await session.get(User, user_id)
        if db_user:
             needs_update = False
             if db_user.first_name != first_name: db_user.first_name = first_name; needs_update = True
             if db_user.last_name != last_name: db_user.last_name = last_name; needs_update = True
             if db_user.username != username: db_user.username = username; needs_update = True
             if needs_update: logger.info(f"User {user_id} ('{username}') found. Updating info..."); session.add(db_user)
             else: logger.info(f"User {user_id} ('{username}') found. No info update needed.")
        else:
             logger.info(f"User {user_id} ('{username}') not found. Creating..."); new_user = User(user_id=user_id, first_name=first_name, last_name=last_name, username=username); session.add(new_user)
    except Exception as e:
        logger.exception(f"DB error during /start for user {user_id}: {e}", exc_info=True); await session.rollback()
        await message.answer("Виникла помилка під час роботи з базою даних. Будь ласка, спробуйте пізніше."); return

    user_name_display = first_name
    text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_entry_point(message, state, session, bot)

@router.message(F.text == BTN_WEATHER_BACKUP)
async def handle_weather_backup_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_backup_entry_point(message, state, session, bot)

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot):
     await currency_entry_point(message, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot):
     await alert_entry_point(message, bot)

@router.message(F.text == BTN_ALERTS_BACKUP)
async def handle_alert_backup_text_request(message: Message, bot: Bot):
     await alert_backup_entry_point(message, bot)


# Обработчики для кнопок геолокации
@location_router.message(F.location) # Сделаем один обработчик и будем смотреть на reply_to_message внутри
async def route_geolocation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent location. Checking for reply_to_message context...")
    
    # Проверяем, было ли это ответом на сообщение с текстом кнопки
    # Заранее убираем request_location=True из текста кнопки, т.к. его нет в reply_to_message
    # и эмодзи тоже может не быть. Лучше сравнивать по уникальной части текста.
    
    # Убираем эмодзи и "(осн.)"/"(резерв)" для более простого сравнения
    # BTN_LOCATION_MAIN = "📍 Погода по геолокації (осн.)"
    # BTN_LOCATION_BACKUP = "📍 Погода по геолокації (резерв)"
    # Уникальная часть "Погода по геолокації"
    
    # Более надежный способ - если бы кнопки отправляли команду или устанавливали состояние.
    # Но для reply кнопок с request_location=True, это сложно.

    # Проверяем, является ли сообщение ответом (reply) на предыдущее сообщение бота
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
        replied_text = message.reply_to_message.text
        logger.info(f"User {user_id} replied with location to bot message: '{replied_text}'")
        if BTN_LOCATION_MAIN in replied_text: # Проверяем наличие полного текста кнопки
            logger.info(f"User {user_id} used MAIN location button (based on replied text).")
            await handle_main_weather_location(message, state, session, bot)
            return
        elif BTN_LOCATION_BACKUP in replied_text: # Проверяем наличие полного текста кнопки
            logger.info(f"User {user_id} used BACKUP location button (based on replied text).")
            await weather_backup_geolocation_entry_point(message, state, session, bot)
            return
        else:
            logger.info(f"User {user_id} replied with location, but replied text ('{replied_text}') didn't match known location buttons.")
    else:
        logger.info(f"User {user_id} sent location not as a reply to a specific bot message, or reply_to_message is None.")

    # Если не удалось определить контекст по reply_to_message, или это не reply,
    # по умолчанию направляем на основной сервис погоды.
    logger.info(f"User {user_id}: Defaulting location to main weather service.")
    await handle_main_weather_location(message, state, session, bot)