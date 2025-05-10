# src/modules/weather_backup/handlers.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
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
# Используем клавиатуру с кнопкой "Назад в меню" из основного модуля погоды, если нужно запросить ввод
from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard
# Импортируем префикс для колбэка "Назад", чтобы правильно его обработать, если понадобится
from src.modules.weather.keyboard import WEATHER_PREFIX as MAIN_WEATHER_PREFIX 
                                        # или создать свой CALLBACK_WEATHER_BACKUP_BACK_TO_MAIN


logger = logging.getLogger(__name__)
router = Router(name="weather-backup-module")

class WeatherBackupStates(StatesGroup):
    waiting_for_location = State() # Ожидание ввода города/координат или отправки геолокации
    showing_current = State()
    showing_forecast = State()


async def _fetch_and_show_backup_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession, # session может быть не нужен здесь, если не работаем с User DB
    location_input: str, # Город или "lat,lon"
    show_forecast: bool = False,
    is_coords_request: bool = False # Флаг, что location_input - это координаты
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    action_text = "⏳ Отримую резервні дані..."
    if show_forecast:
        action_text = "⏳ Отримую резервний прогноз..."

    try:
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
            await target.answer()
        else:
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.error(f"Error sending/editing status message for backup weather: {e}")
        status_message = message_to_edit_or_answer

    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_response_data = None
    formatted_message_text = ""
    reply_markup = None
    
    # Определяем, что передать в format_message как requested_location
    # Если это координаты, то API само вернет имя, если сможет.
    # Если это текст, то это и есть requested_location.
    # format_message уже учитывает это.
    display_location_for_message = location_input
    if is_coords_request:
        # Для координат в format_message передаем строку "ваші координати" или результат API
        # location_input уже "lat,lon". format_weather_backup_message ожидает текст.
        # Можно передать "ваші координати", а format_message сам разберется, если API вернет имя.
        # Однако, API weatherapi.com вернет имя города в location.name даже для координат.
        # Поэтому requested_location оставляем как location_input ("lat,lon"), 
        # а format_weather_backup_message использует location.name из ответа.
        pass


    if show_forecast:
        api_response_data = await get_forecast_weatherapi(bot, location=location_input, days=3)
        formatted_message_text = format_forecast_backup_message(api_response_data, requested_location=display_location_for_message)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_forecast_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_forecast)
        else: # Ошибка или нет данных
            await state.set_state(None) # Сбрасываем состояние, если была ошибка
    else: 
        api_response_data = await get_current_weather_weatherapi(bot, location=location_input)
        formatted_message_text = format_weather_backup_message(api_response_data, requested_location=display_location_for_message)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_current_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_current)
        else: # Ошибка или нет данных
            await state.set_state(None) # Сбрасываем состояние, если была ошибка
    
    try:
        await final_target_message.edit_text(formatted_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent backup weather/forecast for location_input='{location_input}'.")
        if api_response_data and "error" not in api_response_data:
             # Сохраняем использованный location_input (город или "lat,lon") для кнопки "Обновить"
            await state.update_data(current_backup_location=location_input, is_backup_coords=is_coords_request)
            logger.debug(f"User {user_id}: Updated FSM for backup: current_backup_location='{location_input}', is_backup_coords={is_coords_request}")
        else: # Если была ошибка, очищаем данные о последней локации
             await state.update_data(current_backup_location=None, is_backup_coords=None)

    except Exception as e:
        logger.error(f"Error editing final message for backup weather: {e}")
        try:
            await message_to_edit_or_answer.answer(formatted_message_text, reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending new final message for backup weather: {e2}")


# Точка входа для резервной погоды (вызывается кнопкой "Резерв (Погода)")
async def weather_backup_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_backup_entry_point.")
    
    current_fsm_state = await state.get_state()
    if current_fsm_state is not None and current_fsm_state.startswith("WeatherBackupStates"):
        logger.info(f"User {user_id}: Already in a WeatherBackupState ({current_fsm_state}), not clearing.")
    elif current_fsm_state is not None: # Если в каком-то другом состоянии, очищаем
        logger.info(f"User {user_id}: In another FSM state ({current_fsm_state}), clearing before backup weather.")
        await state.clear()
    else: # Состояние None, можно очистить данные
        await state.clear()


    location_to_use: Optional[str] = None
    db_user = await session.get(User, user_id)
    if db_user and db_user.preferred_city:
        location_to_use = db_user.preferred_city
        logger.info(f"User {user_id}: Using preferred city '{location_to_use}' for backup weather.")
    
    if isinstance(target, CallbackQuery): await target.answer()
    target_message = target.message if isinstance(target, CallbackQuery) else target

    if location_to_use:
        # Устанавливаем состояние *до* вызова _fetch_and_show, чтобы колбэки работали
        await state.set_state(WeatherBackupStates.showing_current)
        await _fetch_and_show_backup_weather(bot, target, state, session, location_input=location_to_use, show_forecast=False, is_coords_request=False)
    else:
        logger.info(f"User {user_id}: No preferred city for backup weather. Asking for location input or geolocation.")
        text = "Будь ласка, введіть назву міста (або 'lat,lon') для резервного сервісу погоди, або надішліть геолокацію."
        # Используем клавиатуру из основного модуля, чтобы была кнопка "Назад в меню"
        # Важно, чтобы колбэк этой кнопки был обработан (например, в common.py или здесь)
        # или создать свою клавиатуру для этого модуля
        try:
            if isinstance(target, Message):
                 await target_message.answer(text, reply_markup=get_weather_enter_city_back_keyboard()) # Эта клавиатура имеет CALLBACK_WEATHER_BACK_TO_MAIN
            elif isinstance(target, CallbackQuery): # Если это коллбэк, например, от кнопки "Резерв (Погода)"
                 await target_message.edit_text(text, reply_markup=get_weather_enter_city_back_keyboard())

        except Exception as e:
            logger.error(f"Error sending message to ask for backup location: {e}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        logger.info(f"User {user_id}: Set FSM state to WeatherBackupStates.waiting_for_location.")

# Обработчик для текстового ввода города/координат для резервного сервиса
@router.message(WeatherBackupStates.waiting_for_location, F.text)
async def handle_backup_location_text_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    location_input = message.text.strip() if message.text else ""
    logger.info(f"User {user_id} entered text location '{location_input}' for backup weather.")

    if not location_input:
        await message.answer("Назва міста або координати не можуть бути порожніми. Спробуйте ще раз.")
        return

    # Простая проверка, похоже ли это на "lat,lon"
    is_coords = ',' in location_input and len(location_input.split(',')) == 2
    try:
        if is_coords:
            lat, lon = map(float, location_input.split(',')) # Проверка, что это числа
            logger.info(f"User {user_id}: Parsed as coords: lat={lat}, lon={lon}")
    except ValueError:
        is_coords = False # Не удалось распарсить как float, считаем, что это название города
        logger.info(f"User {user_id}: Input '{location_input}' not parsed as coords, treating as city name.")
    
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input, show_forecast=False, is_coords_request=is_coords)

# <<< НОВЫЙ ОБРАБОТЧИК для геолокации в состоянии waiting_for_location >>>
@router.message(WeatherBackupStates.waiting_for_location, F.location)
async def handle_backup_geolocation_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} sent geolocation for backup weather: lat={lat}, lon={lon}")
    
    location_input_str = f"{lat},{lon}" # Формат "lat,lon" для weatherapi.com
    
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)

# Обработчик для кнопки "Резерв (Геолокація)" из главной клавиатуры
# Этот обработчик будет в common.py, но здесь продумаем логику вызова
async def weather_backup_geolocation_entry_point(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} initiated backup weather by geolocation directly: lat={lat}, lon={lon}")
    
    current_fsm_state = await state.get_state()
    if current_fsm_state is not None: # Очищаем любое предыдущее состояние
        logger.info(f"User {user_id}: Clearing FSM state ({current_fsm_state}) before backup weather by geolocation.")
        await state.clear()
        
    location_input_str = f"{lat},{lon}"
    # Устанавливаем состояние *до* вызова _fetch_and_show, чтобы колбэки работали
    await state.set_state(WeatherBackupStates.showing_current)
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT, WeatherBackupStates.showing_current)
async def handle_refresh_current_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing current backup weather for location: '{location}', is_coords={is_coords}.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False, is_coords_request=is_coords)
    else:
        # ... (обработка ошибки как раньше)
        logger.warning(f"User {user_id}: No location found in state for refreshing current backup weather.")
        await callback.answer("Не вдалося знайти дані для оновлення.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location) 
        await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=get_weather_enter_city_back_keyboard())


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST, WeatherBackupStates.showing_current)
async def handle_show_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False) # Важно для правильного display_location_for_message
    logger.info(f"User {user_id} requesting backup forecast for location: '{location}', is_coords={is_coords}.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True, is_coords_request=is_coords)
    else:
        # ... (обработка ошибки)
        logger.warning(f"User {user_id}: No location found in state for backup forecast.")
        await callback.answer("Не вдалося знайти дані для прогнозу.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=get_weather_enter_city_back_keyboard())


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST, WeatherBackupStates.showing_forecast)
async def handle_refresh_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing backup forecast for location: '{location}', is_coords={is_coords}.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True, is_coords_request=is_coords)
    else:
        # ... (обработка ошибки)
        logger.warning(f"User {user_id}: No location found in state for refreshing backup forecast.")
        await callback.answer("Не вдалося знайти дані для оновлення прогнозу.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:", reply_markup=get_weather_enter_city_back_keyboard())


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_CURRENT, WeatherBackupStates.showing_forecast)
async def handle_show_current_from_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting to show current backup weather (from forecast view) for: '{location}', is_coords={is_coords}.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False, is_coords_request=is_coords)
    else:
        # ... (обработка ошибки)
        logger.warning(f"User {user_id}: No location found in state for showing current backup weather from forecast.")
        await callback.answer("Не вдалося знайти дані.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:", reply_markup=get_weather_enter_city_back_keyboard())

# Обработчик для кнопки "Назад в меню" с клавиатуры get_weather_enter_city_back_keyboard
# Это коллбэк из основного модуля погоды, но его можно обрабатывать и здесь, если мы в состоянии WeatherBackupStates
@router.callback_query(F.data == f"{MAIN_WEATHER_PREFIX}:back_main", WeatherBackupStates.waiting_for_location)
async def handle_backup_weather_back_to_main_from_input(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} pressed 'Back to Main' from backup weather location input. Clearing WeatherBackupStates.")
    await state.clear() # Очищаем состояние этого модуля
    await show_main_menu_message(callback) # Показываем главное меню
    await callback.answer()