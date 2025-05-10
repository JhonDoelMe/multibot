# src/modules/weather_backup/handlers.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup # <<< ИСПРАВЛЕНИЕ: Добавлен StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from .service import (
    get_current_weather_weatherapi,
    format_weather_backup_message,
    get_forecast_weatherapi,
    format_forecast_backup_message
)
from .keyboard import (
    get_current_weather_backup_keyboard,
    get_forecast_weather_backup_keyboard,
    CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT,
    CALLBACK_WEATHER_BACKUP_SHOW_FORECAST,
    CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST,
    CALLBACK_WEATHER_BACKUP_SHOW_CURRENT
)
from src.handlers.utils import show_main_menu_message
from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard
from src.modules.weather.keyboard import WEATHER_PREFIX as MAIN_WEATHER_PREFIX 


logger = logging.getLogger(__name__)
router = Router(name="weather-backup-module")

class WeatherBackupStates(StatesGroup): # Теперь StatesGroup определен
    waiting_for_location = State()
    showing_current = State()
    showing_forecast = State()

async def _fetch_and_show_backup_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    location_input: str,
    show_forecast: bool = False,
    is_coords_request: bool = False
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    action_text = "⏳ Отримую резервні дані..."
    if show_forecast:
        action_text = "⏳ Отримую резервний прогноз..."

    # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке/редактировании статусного сообщения
    try:
        if isinstance(target, CallbackQuery):
            try:
                status_message = await message_to_edit_or_answer.edit_text(action_text)
                await target.answer()
            except Exception as e:
                 logger.error(f"Error editing message for initial status in _fetch_and_show_backup_weather (callback): {e}")
                 try: status_message = await target.message.answer(action_text); await target.answer()
                 except Exception as e2: logger.error(f"Error sending new message for initial status (callback fallback): {e2}"); status_message = message_to_edit_or_answer # Final fallback
        else: # Message
            try: status_message = await target.answer(action_text)
            except Exception as e: logger.error(f"Error sending message for initial status in _fetch_and_show_backup_weather (message): {e}"); status_message = message_to_edit_or_answer # Fallback

    except Exception as e:
        logger.error(f"Unexpected error before sending/editing status message for backup weather: {e}")
        status_message = message_to_edit_or_answer # Ensure status_message is set even on error


    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_response_data = None
    formatted_message_text = ""
    reply_markup = None
    
    display_location_for_message = location_input

    if show_forecast:
        api_response_data = await get_forecast_weatherapi(bot, location=location_input, days=3)
        formatted_message_text = format_forecast_backup_message(api_response_data, requested_location=display_location_for_message)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_forecast_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_forecast)
        else:
            # ИСПРАВЛЕНИЕ: Используем set_state(None) при ошибке API
            await state.set_state(None)
    else:
        api_response_data = await get_current_weather_weatherapi(bot, location=location_input)
        formatted_message_text = format_weather_backup_message(api_response_data, requested_location=display_location_for_message)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_current_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_current)
        else:
            # ИСПРАВЛЕНИЕ: Используем set_state(None) при ошибке API
            await state.set_state(None)
    
    # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке финального сообщения
    try:
        await final_target_message.edit_text(formatted_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent backup weather/forecast for location_input='{location_input}'.")
        if api_response_data and "error" not in api_response_data:
            await state.update_data(current_backup_location=location_input, is_backup_coords=is_coords_request)
            logger.debug(f"User {user_id}: Updated FSM for backup: current_backup_location='{location_input}', is_backup_coords={is_coords_request}")
        else:
             await state.update_data(current_backup_location=None, is_backup_coords=None)
    except Exception as e:
        logger.error(f"Error editing final message for backup weather: {e}")
        try:
            await message_to_edit_or_answer.answer(formatted_message_text, reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending new final message for backup weather: {e2}")

async def weather_backup_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_backup_entry_point.")
    
    current_fsm_state = await state.get_state()
    # Логіка очищення стану, якщо користувач не в стані цього модуля
    # Залишаємо state.clear() при вході ззовні для повного скидання стану
    if current_fsm_state is not None and current_fsm_state.startswith("WeatherBackupStates"):
        logger.info(f"User {user_id}: Already in a WeatherBackupState ({current_fsm_state}), not clearing.")
    elif current_fsm_state is not None:
        logger.info(f"User {user_id}: In another FSM state ({current_fsm_state}), clearing before backup weather.")
        await state.clear() # Очищаем весь FSM state, так как входим в новый модуль
    else: # current_fsm_state is None
        logger.info(f"User {user_id}: State was None, clearing data at weather_backup_entry_point.")
        await state.clear() # Очищаем данные, если состояние None


    location_to_use: Optional[str] = None
    db_user = await session.get(User, user_id)
    if db_user and db_user.preferred_city:
        location_to_use = db_user.preferred_city
        logger.info(f"User {user_id}: Using preferred city '{location_to_use}' for backup weather.")
    
    # ИСПРАВЛЕНИЕ: Обработка случая, если target - CallbackQuery и answer() вызывает ошибку
    if isinstance(target, CallbackQuery):
        try: await target.answer()
        except Exception as e: logger.warning(f"Could not answer callback in weather_backup_entry_point: {e}")

    target_message = target.message if isinstance(target, CallbackQuery) else target

    if location_to_use:
        await state.set_state(WeatherBackupStates.showing_current)
        await _fetch_and_show_backup_weather(bot, target, state, session, location_input=location_to_use, show_forecast=False, is_coords_request=False)
    else:
        logger.info(f"User {user_id}: No preferred city for backup weather. Asking for location input or geolocation.")
        text = "Будь ласка, введіть назву міста (або 'lat,lon') для резервного сервісу погоди, або надішліть геолокацію."
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try:
            if isinstance(target, Message):
                 await target_message.answer(text, reply_markup=get_weather_enter_city_back_keyboard())
            elif isinstance(target, CallbackQuery):
                 await target_message.edit_text(text, reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e:
            logger.error(f"Error sending message to ask for backup location: {e}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        logger.info(f"User {user_id}: Set FSM state to WeatherBackupStates.waiting_for_location.")

@router.message(WeatherBackupStates.waiting_for_location, F.text)
async def handle_backup_location_text_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    location_input = message.text.strip() if message.text else ""
    logger.info(f"User {user_id} entered text location '{location_input}' for backup weather.")
    if not location_input:
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.answer("Назва міста або координати не можуть бути порожніми. Спробуйте ще раз.")
        except Exception as e: logger.error(f"Error sending empty backup location message: {e}")
        return
    is_coords = ',' in location_input and len(location_input.split(',')) == 2
    try:
        if is_coords:
            lat, lon = map(float, location_input.split(','))
            logger.info(f"User {user_id}: Parsed as coords: lat={lat}, lon={lon}")
    except ValueError:
        is_coords = False
        logger.info(f"User {user_id}: Input '{location_input}' not parsed as coords, treating as city name.")

    # Встановлюємо стан перед викликом _fetch_and_show_backup_weather
    # Якщо дані отримано успішно, _fetch_and_show_backup_weather встановить showing_current/forecast.
    # Якщо помилка, _fetch_and_show_backup_weather встановить None.
    # Тому явне встановлення стану перед викликом тут не потрібне, _fetch_and_show_backup_weather робить це сама.
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input, show_forecast=False, is_coords_request=is_coords)

@router.message(WeatherBackupStates.waiting_for_location, F.location)
async def handle_backup_geolocation_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} sent geolocation for backup weather: lat={lat}, lon={lon}")
    location_input_str = f"{lat},{lon}"
    # Встановлюємо стан перед викликом _fetch_and_show_backup_weather
    # Як і вище, _fetch_and_show_backup_weather сама встановить потрібний стан.
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)

async def weather_backup_geolocation_entry_point(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    # Эта функция вызывается из common_handlers.handle_any_geolocation
    # common_handlers уже установил state в None при необходимости
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} initiated backup weather by geolocation directly: lat={lat}, lon={lon}")
    # common_handlers уже очистил/установил state в None перед вызовом этой функции
    location_input_str = f"{lat},{lon}"
    await state.set_state(WeatherBackupStates.showing_current) # Встановлюємо стан перед показом
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT, WeatherBackupStates.showing_current)
async def handle_refresh_current_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing current backup weather for location: '{location}', is_coords={is_coords}.")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Оновлюю дані...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_refresh_current_backup: {e}")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for refreshing current backup weather.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Не вдалося знайти дані для оновлення."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Failed to edit message after backup refresh failure: {e}")
             try: await callback.message.answer("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=reply_markup)
             except Exception as e2: logger.error(f"Failed to send message after backup refresh failure either: {e2}")

        await state.set_state(WeatherBackupStates.waiting_for_location)
        # callback.answer() уже сделан выше с show_alert=True

@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST, WeatherBackupStates.showing_current)
async def handle_show_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting backup forecast for location: '{location}', is_coords={is_coords}.")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Отримую прогноз...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_show_forecast_backup: {e}")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for backup forecast.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Не вдалося знайти дані для прогнозу."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after backup forecast failure: {e}")
            try: await callback.message.answer("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send message after backup forecast failure either: {e2}")

        await state.set_state(WeatherBackupStates.waiting_for_location)
        # callback.answer() уже сделан выше с show_alert=True


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST, WeatherBackupStates.showing_forecast)
async def handle_refresh_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing backup forecast for location: '{location}', is_coords={is_coords}.")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Оновлюю прогноз...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_refresh_forecast_backup: {e}")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for refreshing backup forecast.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Не вдалося знайти дані для оновлення прогнозу."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Failed to edit message after backup forecast refresh failure: {e}")
             try: await callback.message.answer("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=reply_markup)
             except Exception as e2: logger.error(f"Failed to send message after backup forecast refresh failure either: {e2}")

        await state.set_state(WeatherBackupStates.waiting_for_location)
        # callback.answer() уже сделан выше с show_alert=True


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_CURRENT, WeatherBackupStates.showing_forecast)
async def handle_show_current_from_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting to show current backup weather (from forecast view) for: '{location}', is_coords={is_coords}.")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Показую поточну погоду...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_show_current_from_forecast_backup: {e}")


    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for showing current backup weather from forecast.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Не вдалося знайти дані."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after show current backup failure: {e}")
            try: await callback.message.answer("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send message after show current backup failure either: {e2}")

        await state.set_state(WeatherBackupStates.waiting_for_location)
        # callback.answer() уже сделан выше с show_alert=True


@router.callback_query(F.data == f"{MAIN_WEATHER_PREFIX}:back_main", WeatherBackupStates.waiting_for_location)
async def handle_backup_weather_back_to_main_from_input(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} pressed 'Back to Main' from backup weather location input. Setting WeatherBackupStates to None.")
    await state.set_state(None) # Use set_state(None) instead of clear()
    await show_main_menu_message(callback)
    # show_main_menu_message уже делает callback.answer()
    # try: await callback.answer()
    # except Exception as e: logger.warning(f"Could not answer callback in handle_backup_weather_back_to_main_from_input: {e}")