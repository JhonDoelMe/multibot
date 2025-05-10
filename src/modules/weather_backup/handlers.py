# src/modules/weather_backup/handlers.py

import logging
from typing import Union, Optional # Optional тут потрібен
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
# get_weather_backup_enter_city_keyboard не використовується, але його можна залишити
# from src.handlers.utils import show_main_menu_message # Не використовується напряму в цьому файлі
# Для кнопки "Назад" використовується клавіатура з основного модуля погоди
from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard 
from src.modules.weather.keyboard import WEATHER_PREFIX as MAIN_WEATHER_PREFIX
from src.handlers.utils import show_main_menu_message # Для кнопки Назад в головне меню


logger = logging.getLogger(__name__)
router = Router(name="weather-backup-module")

class WeatherBackupStates(StatesGroup):
    waiting_for_location = State()
    showing_current = State()
    showing_forecast = State()

async def _fetch_and_show_backup_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession, # session може бути не потрібний, якщо не взаємодіємо з User моделлю тут
    location_input: str,
    show_forecast: bool = False,
    is_coords_request: bool = False # Прапорець, чи був запит за координатами
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False

    action_text = "⏳ Отримую резервні дані..."
    if show_forecast:
        action_text = "⏳ Отримую резервний прогноз..."

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _fetch_and_show_backup_weather for user {user_id}: {e}")
    
    try:
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
        else: # Message
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for backup weather, user {user_id}: {e}")

    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_response_data: Dict[str, Any]
    formatted_message_text: str
    reply_markup: Optional[InlineKeyboardMarkup] = None # Явно вказуємо тип

    if show_forecast:
        api_response_data = await get_forecast_weatherapi(bot, location=location_input, days=3)
        # format_forecast_backup_message вже обробляє структуру помилки
        formatted_message_text = format_forecast_backup_message(api_response_data, requested_location=location_input)
        
        # Перевіряємо, чи відповідь не містить помилки (ключ "error" всередині відповіді WeatherAPI,
        # або наша обгортка з "error_source")
        if not ("error" in api_response_data and isinstance(api_response_data["error"], dict)):
            reply_markup = get_forecast_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_forecast)
            await state.update_data(current_backup_location=location_input, is_backup_coords=is_coords_request)
            logger.debug(f"User {user_id}: Backup forecast shown. FSM to showing_forecast. Location: {location_input}")
        else:
            # Якщо була помилка, кнопки дій не потрібні, або потрібні кнопки для повторного введення
            # Залишаємо reply_markup=None, стан скидаємо
            await state.set_state(None) # Скидаємо стан при помилці API
            logger.warning(f"User {user_id}: Error fetching backup forecast. State set to None. Response: {api_response_data}")
            # Можна додати клавіатуру для повторного введення міста, якщо потрібно
            # reply_markup = get_weather_enter_city_back_keyboard() 

    else: # Поточна погода
        api_response_data = await get_current_weather_weatherapi(bot, location=location_input)
        formatted_message_text = format_weather_backup_message(api_response_data, requested_location=location_input)
        
        if not ("error" in api_response_data and isinstance(api_response_data["error"], dict)):
            reply_markup = get_current_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_current)
            await state.update_data(current_backup_location=location_input, is_backup_coords=is_coords_request)
            logger.debug(f"User {user_id}: Backup current weather shown. FSM to showing_current. Location: {location_input}")
        else:
            await state.set_state(None)
            logger.warning(f"User {user_id}: Error fetching backup current weather. State set to None. Response: {api_response_data}")
            # reply_markup = get_weather_enter_city_back_keyboard()

    try:
        if status_message:
            await final_target_message.edit_text(formatted_message_text, reply_markup=reply_markup)
        else:
            await message_to_edit_or_answer.answer(formatted_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent/edited backup weather/forecast for location_input='{location_input}'.")
    except Exception as e:
        logger.error(f"Error sending/editing final message for backup weather: {e}")
        # Якщо відправка/редагування не вдалася, спробувати відповісти простим повідомленням, якщо це помилка
        if "error" in api_response_data and not status_message :
            try: await message_to_edit_or_answer.answer("Не вдалося відобразити резервну погоду. Спробуйте пізніше.")
            except: pass # Остання спроба

    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except Exception: logger.warning(f"Final attempt to answer backup weather callback for user {user_id} failed.")


async def weather_backup_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_backup_entry_point.")

    current_fsm_state = await state.get_state()
    if current_fsm_state is not None and not current_fsm_state.startswith("WeatherBackupStates"):
        logger.info(f"User {user_id}: In another FSM state ({current_fsm_state}), clearing state before backup weather.")
        await state.clear() 
    elif current_fsm_state is None:
        await state.set_data({}) # Очищаємо дані, якщо стан None

    location_to_use: Optional[str] = None
    db_user = await session.get(User, user_id) # Отримуємо користувача для переваг
    if db_user and db_user.preferred_city:
        location_to_use = db_user.preferred_city
        logger.info(f"User {user_id}: Using preferred city '{location_to_use}' for backup weather.")

    answered_callback = False
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e: logger.warning(f"Could not answer callback in weather_backup_entry_point: {e}")

    target_message = target.message if isinstance(target, CallbackQuery) else target

    if location_to_use:
        # Не встановлюємо стан тут, _fetch_and_show_backup_weather зробить це
        await _fetch_and_show_backup_weather(bot, target, state, session, location_input=location_to_use, show_forecast=False, is_coords_request=False)
    else:
        logger.info(f"User {user_id}: No preferred city for backup weather. Asking for location input.")
        text = "Будь ласка, введіть назву міста (або 'lat,lon') для резервного сервісу погоди, або надішліть геолокацію."
        reply_markup = get_weather_enter_city_back_keyboard() # Клавіатура "Назад в меню"
        try:
            if isinstance(target, CallbackQuery):
                 await target_message.edit_text(text, reply_markup=reply_markup)
            else: # Message
                 await target_message.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message to ask for backup location: {e}")
            if isinstance(target, CallbackQuery): # Fallback
                try: await target.message.answer(text, reply_markup=reply_markup)
                except: pass
        await state.set_state(WeatherBackupStates.waiting_for_location)
        logger.info(f"User {user_id}: Set FSM state to WeatherBackupStates.waiting_for_location.")
    
    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except: pass


@router.message(WeatherBackupStates.waiting_for_location, F.text)
async def handle_backup_location_text_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    location_input = message.text.strip() if message.text else ""
    logger.info(f"User {user_id} entered text location '{location_input}' for backup weather.")
    
    if not location_input:
        try: await message.answer("Назва міста або координати не можуть бути порожніми. Спробуйте ще раз.")
        except Exception as e: logger.error(f"Error sending empty backup location message: {e}")
        return
        
    is_coords = False
    if ',' in location_input:
        parts = location_input.split(',')
        if len(parts) == 2:
            try:
                float(parts[0].strip())
                float(parts[1].strip())
                is_coords = True
                logger.info(f"User {user_id}: Parsed input '{location_input}' as coords for backup weather.")
            except ValueError:
                logger.info(f"User {user_id}: Input '{location_input}' looked like coords but failed to parse floats.")
                is_coords = False # Залишаємо як назву міста
    
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input, show_forecast=False, is_coords_request=is_coords)


@router.message(WeatherBackupStates.waiting_for_location, F.location)
async def handle_backup_geolocation_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} sent geolocation for backup weather: lat={lat}, lon={lon}")
    location_input_str = f"{lat},{lon}"
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)


async def weather_backup_geolocation_entry_point(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    # Ця функція викликається з common_handlers.handle_any_geolocation
    # common_handlers вже мав встановити state в None (або очистити), якщо потрібно.
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} initiated backup weather by geolocation directly: lat={lat}, lon={lon}")
    location_input_str = f"{lat},{lon}"
    # Стан буде встановлено всередині _fetch_and_show_backup_weather
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, show_forecast=False, is_coords_request=True)


# Обробники для кнопок оновлення, показу прогнозу тощо.
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
        logger.warning(f"User {user_id}: No location found in state for refreshing current backup weather.")
        answered = False
        try:
            await callback.answer("Помилка: дані для оновлення не знайдено.", show_alert=True)
            answered = True
        except Exception as e: logger.warning(f"Could not answer callback (refresh error): {e}")
        
        # Якщо немає локації, пропонуємо ввести знову
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after backup refresh failure: {e_edit}")
            try: await callback.message.answer(text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message for backup refresh failure: {e_ans}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        if not answered:
            try: await callback.answer()
            except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST, WeatherBackupStates.showing_current)
async def handle_show_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting backup forecast for location: '{location}', is_coords={is_coords}.")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for backup forecast.")
        answered = False
        try:
            await callback.answer("Помилка: дані для прогнозу не знайдено.", show_alert=True)
            answered = True
        except Exception as e: logger.warning(f"Could not answer callback (forecast error): {e}")

        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after backup forecast failure: {e_edit}")
            try: await callback.message.answer(text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message for backup forecast failure: {e_ans}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        if not answered:
            try: await callback.answer()
            except: pass


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
        logger.warning(f"User {user_id}: No location found in state for refreshing backup forecast.")
        answered = False
        try:
            await callback.answer("Помилка: дані для оновлення прогнозу не знайдено.", show_alert=True)
            answered = True
        except Exception as e: logger.warning(f"Could not answer callback (refresh forecast error): {e}")
        
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after backup forecast refresh failure: {e_edit}")
            try: await callback.message.answer(text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message for backup forecast refresh failure: {e_ans}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        if not answered:
            try: await callback.answer()
            except: pass


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
        logger.warning(f"User {user_id}: No location found in state for showing current backup weather from forecast.")
        answered = False
        try:
            await callback.answer("Помилка: дані для показу поточної погоди не знайдено.", show_alert=True)
            answered = True
        except Exception as e: logger.warning(f"Could not answer callback (show current from forecast error): {e}")

        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after show current backup failure: {e_edit}")
            try: await callback.message.answer(text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message for show current backup failure: {e_ans}")
        await state.set_state(WeatherBackupStates.waiting_for_location)
        if not answered:
            try: await callback.answer()
            except: pass


# Кнопка "Назад в меню" з клавіатури вводу міста для резервного сервісу
@router.callback_query(F.data == f"{MAIN_WEATHER_PREFIX}:back_main", WeatherBackupStates.waiting_for_location)
async def handle_backup_weather_back_to_main_from_input(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} pressed 'Back to Main' from backup weather location input. Current state: {await state.get_state()}. Setting state to None.")
    await state.set_state(None) # Скидаємо стан цього модуля
    # show_main_menu_message вже робить callback.answer()
    await show_main_menu_message(callback)