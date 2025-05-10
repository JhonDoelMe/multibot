# src/handlers/common.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.filters import CommandStart, StateFilter # StateFilter может понадобиться для геолокации
from aiogram.fsm.context import FSMContext
from aiogram.types import Message # <<< ДОДАНО ІМПОРТ
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, ServiceChoice # Импортируем ServiceChoice
from src.keyboards.reply_main import (
    get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS,
    BTN_LOCATION, BTN_SETTINGS # Обновленный список кнопок
)

# Импортируем entry_points для всех сервисов
from src.modules.weather.handlers import weather_entry_point as main_weather_ep
from src.modules.weather.handlers import process_main_geolocation_button # Эта функция обрабатывает геолокацию для основного сервиса

from src.modules.weather_backup.handlers import weather_backup_entry_point as backup_weather_ep
from src.modules.weather_backup.handlers import weather_backup_geolocation_entry_point # Эта функция для резервной геолокации

from src.modules.alert.handlers import alert_entry_point as main_alert_ep
from src.modules.alert_backup.handlers import alert_backup_entry_point as backup_alert_ep

from src.modules.currency.handlers import currency_entry_point
from src.modules.settings.handlers import settings_entry_point # <<< НОВАЯ ТОЧКА ВХОДА ДЛЯ НАСТРОЕК

from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")
# location_router больше не нужен в том виде, как был,
# так как у нас будет одна кнопка геолокации, и ее обработчик будет в этом же роутере.


# Вспомогательная функция для получения настроек пользователя (можно вынести в utils, если используется много где)
async def _get_user_or_default_settings(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user: # Если пользователь не найден (например, еще не нажимал /start после добавления полей)
        logger.warning(f"User {user_id} not found in DB. Using default service settings.")
        # Возвращаем "виртуального" пользователя с настройками по умолчанию
        # Это не сохраняется в БД здесь, просто для логики выбора сервиса.
        # /start должен создать пользователя.
        return User(
            user_id=user_id, # Нужно для логов, но в БД его нет
            first_name = "Temp User", # Заглушка
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM
        )
    # Убедимся, что у существующего пользователя есть значения по умолчанию, если поля были NULL
    if user.preferred_weather_service is None:
        user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
    if user.preferred_alert_service is None:
        user.preferred_alert_service = ServiceChoice.UKRAINEALARM
    return user


@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    await state.clear() # Очищаем любое предыдущее состояние (для команды /start это обычно желательно)
    user_tg = message.from_user
    if not user_tg:
        logger.warning("Received /start from a user with no user info.")
        await message.answer("Не вдалося отримати інформацію про користувача.")
        return

    user_id = user_tg.id
    first_name = user_tg.first_name if user_tg.first_name else "Користувач"
    last_name = user_tg.last_name
    username = user_tg.username

    db_user = await session.get(User, user_id)
    if db_user:
        needs_update = False
        if db_user.first_name != first_name: db_user.first_name = first_name; needs_update = True
        if db_user.last_name != last_name: db_user.last_name = last_name; needs_update = True
        if db_user.username != username: db_user.username = username; needs_update = True
        # Устанавливаем значения по умолчанию для новых полей, если их нет (для старых юзеров)
        if db_user.preferred_weather_service is None:
            db_user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
            needs_update = True
        if db_user.preferred_alert_service is None:
            db_user.preferred_alert_service = ServiceChoice.UKRAINEALARM
            needs_update = True
        if needs_update:
            logger.info(f"User {user_id} ('{username}') found. Updating info/default settings...")
            session.add(db_user)
        else:
            logger.info(f"User {user_id} ('{username}') found. No info update needed.")
    else:
        logger.info(f"User {user_id} ('{username}') not found. Creating with default service settings...")
        new_user = User(
            user_id=user_id, first_name=first_name, last_name=last_name, username=username,
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP, # Значения по умолчанию
            preferred_alert_service=ServiceChoice.UKRAINEALARM
        )
        session.add(new_user)
    # Коммит будет выполнен DbSessionMiddleware

    text = f"Привіт, {first_name}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

# --- Обработчики для кнопок меню с учетом настроек ---

@router.message(F.text == BTN_WEATHER)
async def handle_weather_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_settings = await _get_user_or_default_settings(session, message.from_user.id)
    logger.info(f"User {message.from_user.id} pressed Weather button. Preferred service: {user_settings.preferred_weather_service}")
    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        await backup_weather_ep(message, state, session, bot)
    else: # По умолчанию или если выбран OWM
        await main_weather_ep(message, state, session, bot)

@router.message(F.text == BTN_ALERTS)
async def handle_alerts_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # Добавил state, session для консистентности
    user_settings = await _get_user_or_default_settings(session, message.from_user.id)
    logger.info(f"User {message.from_user.id} pressed Alerts button. Preferred service: {user_settings.preferred_alert_service}")
    if user_settings.preferred_alert_service == ServiceChoice.ALERTSINUA:
        await backup_alert_ep(message, bot) # backup_alert_ep может не требовать state, session
    else: # По умолчанию или если выбран UkraineAlarm
        await main_alert_ep(message, bot)   # main_alert_ep может не требовать state, session

# Единый обработчик для кнопки геолокации
@router.message(F.text == BTN_LOCATION) # Этот фильтр не сработает, т.к. кнопка с request_location
async def handle_location_text_button(message: Message): # Этот хендлер не должен вызываться для кнопки локации
     logger.warning(f"Received text message '{BTN_LOCATION}' instead of location. User: {message.from_user.id}")
     await message.reply("Будь ласка, надішліть вашу геолокацію, використовуючи кнопку на клавіатурі.")

@router.message(F.location) # Общий обработчик для любой присланной геолокации
async def handle_any_geolocation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    user_settings = await _get_user_or_default_settings(session, user_id)
    logger.info(f"User {user_id} sent geolocation. Preferred weather service: {user_settings.preferred_weather_service}")

    # Выходим из текущего состояния FSM gracefully, сохраняя данные
    current_fsm_state = await state.get_state()
    if current_fsm_state is not None:
        logger.info(f"Exiting FSM state '{current_fsm_state}' before processing geolocation.")
        # ИСПРАВЛЕНИЕ: Используем set_state(None) вместо clear()
        await state.set_state(None)
        logger.debug(f"User {user_id}: Set FSM state to None (from {current_fsm_state}) after receiving geolocation.")

    # Теперь передаем обработку соответствующему модулю погоды
    if user_settings.preferred_weather_service == ServiceChoice.WEATHERAPI:
        # Вызываем функцию обработки геолокации из резервного модуля
        await weather_backup_geolocation_entry_point(message, state, session, bot)
    else: # По умолчанию или если выбран OWM
        # Вызываем функцию обработки геолокации из основного модуля
        await process_main_geolocation_button(message, state, session, bot)


@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot):
     await currency_entry_point(message, bot)

@router.message(F.text == BTN_SETTINGS)
async def handle_settings_button(message: Message, session: AsyncSession, bot: Bot): # state здесь не нужен
    await settings_entry_point(message, session, bot)