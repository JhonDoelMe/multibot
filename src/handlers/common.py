# src/handlers/common.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext # Потрібен для передачі в settings_entry_point
from aiogram.types import Message, User as AiogramUser
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.filters import CommandStart

from src.db.models import User, ServiceChoice # Наша модель User
from src.keyboards.reply_main import (
    get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS,
    BTN_LOCATION, BTN_SETTINGS
)

# Імпортуємо entry_points для всіх сервісів
from src.modules.weather.handlers import weather_entry_point as main_weather_ep
from src.modules.weather.handlers import process_main_geolocation_button

from src.modules.weather_backup.handlers import weather_backup_entry_point as backup_weather_ep
from src.modules.weather_backup.handlers import weather_backup_geolocation_entry_point

from src.modules.alert.handlers import alert_entry_point as main_alert_ep
from src.modules.alert_backup.handlers import alert_backup_entry_point as backup_alert_ep

from src.modules.currency.handlers import currency_entry_point
from src.modules.settings.handlers import settings_entry_point # Ця функція тепер приймає state

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")


async def _get_user_or_default_settings(session: AsyncSession, user_id: int, user_tg_obj: Optional[AiogramUser] = None) -> User:
    db_user = await session.get(User, user_id)
    if db_user:
        if db_user.preferred_weather_service is None:
            db_user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if db_user.preferred_alert_service is None:
            db_user.preferred_alert_service = ServiceChoice.UKRAINEALARM
        # Перевірка нових полів для існуючих користувачів
        if not hasattr(db_user, 'weather_reminder_enabled') or db_user.weather_reminder_enabled is None:
            db_user.weather_reminder_enabled = False
        # weather_reminder_time може бути None за замовчуванням
        return db_user
    else:
        logger.warning(f"User {user_id} not found in DB by _get_user_or_default_settings. Returning User object with defaults for logic.")
        first_name_default = "Користувач"
        if user_tg_obj and user_tg_obj.first_name:
            first_name_default = user_tg_obj.first_name
        
        return User(
            user_id=user_id,
            first_name=first_name_default,
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, # Значення за замовчуванням
            weather_reminder_time=None      # Значення за замовчуванням
        )


@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
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

    db_user = await session.get(User, user_id)
    needs_commit = False

    if db_user:
        logger.info(f"User {user_id} ('{username or 'N/A'}') found in DB.")
        if db_user.first_name != first_name:
            db_user.first_name = first_name
            needs_commit = True
        if db_user.last_name != last_name: 
            db_user.last_name = last_name
            needs_commit = True
        if db_user.username != username:
            db_user.username = username
            needs_commit = True
        
        if db_user.preferred_weather_service is None:
            db_user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
            needs_commit = True
            logger.info(f"User {user_id}: Setting default preferred_weather_service to OWM.")
        if db_user.preferred_alert_service is None:
            db_user.preferred_alert_service = ServiceChoice.UKRAINEALARM
            needs_commit = True
            logger.info(f"User {user_id}: Setting default preferred_alert_service to UkraineAlarm.")
        # Ініціалізація нових полів для існуючих користувачів, якщо їх немає
        if not hasattr(db_user, 'weather_reminder_enabled') or db_user.weather_reminder_enabled is None:
            db_user.weather_reminder_enabled = False
            needs_commit = True
            logger.info(f"User {user_id}: Initializing weather_reminder_enabled to False.")
        # weather_reminder_time може бути None, це нормально, якщо нагадування вимкнені
        
        if needs_commit:
            logger.info(f"User {user_id}: Updating user info/default settings in DB.")
            session.add(db_user)
    else:
        logger.info(f"User {user_id} ('{username or 'N/A'}') not found. Creating new user with default service settings...")
        new_user = User(
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, # Значення за замовчуванням
            weather_reminder_time=None      # Значення за замовчуванням
        )
        session.add(new_user)
    
    text = f"Привіт, {first_name}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    try:
        await message.answer(text=text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to send start message to user {user_id}: {e}")


@router.message(F.text == BTN_WEATHER)
async def handle_weather_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    logger.info(f"User {message.from_user.id} pressed Weather button. Preferred service: {user_settings.preferred_weather_service}")
    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        await backup_weather_ep(message, state, session, bot)
    else:
        await main_weather_ep(message, state, session, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alerts_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # Додано state, session для можливої передачі
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    logger.info(f"User {message.from_user.id} pressed Alerts button. Preferred service: {user_settings.preferred_alert_service}")
    if user_settings.preferred_alert_service == ServiceChoice.ALERTSINUA:
        # backup_alert_ep може вимагати state, session, якщо його логіка зміниться
        await backup_alert_ep(message, bot) # Поки що передаємо тільки message, bot
    else: 
        await main_alert_ep(message, bot) # Аналогічно

@router.message(F.location)
async def handle_any_geolocation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    if not message.location:
        logger.warning(f"User {user_id} triggered F.location handler but message.location is None.")
        await message.reply("Не вдалося обробити геолокацію. Спробуйте ще раз.")
        return

    lat = message.location.latitude
    lon = message.location.longitude
    user_settings = await _get_user_or_default_settings(session, user_id, message.from_user)
    logger.info(f"User {user_id} sent geolocation ({lat}, {lon}). Preferred weather service: {user_settings.preferred_weather_service}")

    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        logger.info(f"User {user_id}: In FSM state '{current_fsm_state}' before processing geolocation. Setting state to None.")
        await state.set_state(None) 
        logger.debug(f"User {user_id}: FSM state set to None after receiving geolocation.")

    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        await weather_backup_geolocation_entry_point(message, state, session, bot)
    else:
        await process_main_geolocation_button(message, state, session, bot)


@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # Додано state, session
     # currency_entry_point може не вимагати state, session, але для уніфікації можна додати
     await currency_entry_point(message, bot) # Поки що передаємо тільки message, bot

# ВИПРАВЛЕНО: Додано state: FSMContext до сигнатури та передано у виклик
@router.message(F.text == BTN_SETTINGS)
async def handle_settings_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await settings_entry_point(message, session, bot, state)
    # state передається для можливого використання в settings_entry_point