# src/handlers/common.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext 
from aiogram.types import Message, User as AiogramUser # Перейменовано User на AiogramUser для уникнення конфлікту
from sqlalchemy.ext.asyncio import AsyncSession
from aiogram.filters import CommandStart

# Використовуємо AiogramUser для підказки типу, щоб уникнути конфлікту з локальною моделлю User
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


async def _get_user_or_default_settings(session: AsyncSession, user_id: int, tg_user_obj: Optional[AiogramUser] = None) -> User:
    db_user = await session.get(User, user_id)
    if db_user:
        # Переконуємося, що стандартні налаштування сервісів встановлені, якщо вони None
        if db_user.preferred_weather_service is None:
            db_user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if db_user.preferred_alert_service is None:
            db_user.preferred_alert_service = ServiceChoice.UKRAINEALARM
        
        # Ініціалізуємо нові поля для існуючих користувачів, якщо їх немає або вони None
        if not hasattr(db_user, 'weather_reminder_enabled') or db_user.weather_reminder_enabled is None:
            db_user.weather_reminder_enabled = False
        if not hasattr(db_user, 'is_blocked') or db_user.is_blocked is None:
            db_user.is_blocked = False # Ініціалізуємо is_blocked для існуючих користувачів
        return db_user
    else:
        logger.warning(f"User {user_id} not found in DB by _get_user_or_default_settings. Creating new User object with defaults.")
        first_name_default = "Користувач"
        if tg_user_obj and tg_user_obj.first_name:
            first_name_default = tg_user_obj.first_name
        
        # Створюємо новий екземпляр User з усіма полями, включаючи is_blocked
        new_user_instance = User(
            user_id=user_id,
            first_name=first_name_default,
            last_name=tg_user_obj.last_name if tg_user_obj else None,
            username=tg_user_obj.username if tg_user_obj else None,
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, 
            weather_reminder_time=None,
            is_blocked=False # Явно встановлюємо is_blocked для нових користувачів
        )
        # Ця функція тепер просто повертає екземпляр; додавання до сесії та коміт - відповідальність викликаючого коду.
        # Якщо викликається з /start, new_user_instance буде додано до сесії там.
        return new_user_instance


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
    needs_commit = False # Middleware зробить коміт

    if db_user:
        logger.info(f"User {user_id} ('{username or 'N/A'}') found in DB.")
        # Оновлюємо інформацію про користувача, якщо вона змінилася
        if db_user.first_name != first_name:
            db_user.first_name = first_name
            # needs_commit = True # Не потрібно, якщо middleware робить коміт
        if db_user.last_name != last_name: 
            db_user.last_name = last_name
            # needs_commit = True
        if db_user.username != username:
            db_user.username = username
            # needs_commit = True
        
        # Переконуємося, що стандартні налаштування та нові поля встановлені для існуючих користувачів
        if db_user.preferred_weather_service is None:
            db_user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
            logger.info(f"User {user_id}: Setting default preferred_weather_service to OWM.")
        if db_user.preferred_alert_service is None:
            db_user.preferred_alert_service = ServiceChoice.UKRAINEALARM
            logger.info(f"User {user_id}: Setting default preferred_alert_service to UkraineAlarm.")
        
        if not hasattr(db_user, 'weather_reminder_enabled') or db_user.weather_reminder_enabled is None:
            db_user.weather_reminder_enabled = False
            logger.info(f"User {user_id}: Initializing weather_reminder_enabled to False.")
        
        if not hasattr(db_user, 'is_blocked') or db_user.is_blocked is None:
            db_user.is_blocked = False # Ініціалізуємо is_blocked
            logger.info(f"User {user_id}: Initializing is_blocked to False.")
        
        # if needs_commit: # Не потрібно, якщо middleware робить коміт
        #     logger.info(f"User {user_id}: Updating user info/default settings in DB.")
        #     session.add(db_user) 
            # Коміт буде зроблено middleware
    else:
        logger.info(f"User {user_id} ('{username or 'N/A'}') not found. Creating new user with default service settings...")
        new_user = User(
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, 
            weather_reminder_time=None,
            is_blocked=False # Переконуємося, що is_blocked встановлено для нових користувачів
        )
        session.add(new_user)
        # Коміт буде зроблено middleware
    
    text = f"Привіт, {first_name}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    try:
        await message.answer(text=text, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to send start message to user {user_id}: {e}")


@router.message(F.text == BTN_WEATHER)
async def handle_weather_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    if user_settings.is_blocked: 
        logger.info(f"User {message.from_user.id} is blocked. Ignoring weather request.")
        await message.answer("Ваш обліковий запис заблоковано.")
        return
    logger.info(f"User {message.from_user.id} pressed Weather button. Preferred service: {user_settings.preferred_weather_service}")
    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        await backup_weather_ep(message, state, session, bot)
    else:
        await main_weather_ep(message, state, session, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alerts_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): 
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    if user_settings.is_blocked: 
        logger.info(f"User {message.from_user.id} is blocked. Ignoring alerts request.")
        await message.answer("Ваш обліковий запис заблоковано.")
        return
    logger.info(f"User {message.from_user.id} pressed Alerts button. Preferred service: {user_settings.preferred_alert_service}")
    if user_settings.preferred_alert_service == ServiceChoice.ALERTSINUA:
        await backup_alert_ep(message, bot) 
    else: 
        await main_alert_ep(message, bot) 

@router.message(F.location)
async def handle_any_geolocation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    if not message.location:
        logger.warning(f"User {user_id} triggered F.location handler but message.location is None.")
        await message.reply("Не вдалося обробити геолокацію. Спробуйте ще раз.")
        return

    user_settings = await _get_user_or_default_settings(session, user_id, message.from_user)
    if user_settings.is_blocked: 
        logger.info(f"User {user_id} is blocked. Ignoring geolocation request.")
        await message.answer("Ваш обліковий запис заблоковано.")
        return

    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} sent geolocation ({lat}, {lon}). Preferred weather service: {user_settings.preferred_weather_service}")

    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        logger.info(f"User {user_id}: In FSM state '{current_fsm_state}' before processing geolocation. Clearing state.")
        await state.clear() 
        logger.debug(f"User {user_id}: FSM state cleared after receiving geolocation.")

    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        await weather_backup_geolocation_entry_point(message, state, session, bot)
    else:
        await process_main_geolocation_button(message, state, session, bot)


@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): 
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    if user_settings.is_blocked: 
        logger.info(f"User {message.from_user.id} is blocked. Ignoring currency request.")
        await message.answer("Ваш обліковий запис заблоковано.")
        return
    await currency_entry_point(message, bot)

@router.message(F.text == BTN_SETTINGS)
async def handle_settings_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_settings = await _get_user_or_default_settings(session, message.from_user.id, message.from_user)
    if user_settings.is_blocked: 
        logger.info(f"User {message.from_user.id} is blocked. Ignoring settings request.")
        await message.answer("Ваш обліковий запис заблоковано.")
        return
    await settings_entry_point(message, session, bot, state)

