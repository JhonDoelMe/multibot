# src/modules/weather_backup/handlers.py

import logging
import re 
from typing import Union, Optional, Dict, Any

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User 
from .service import (
    get_current_weather_weatherapi,
    format_weather_backup_message,
    get_forecast_weatherapi,
    format_forecast_backup_message,
    format_tomorrow_forecast_backup_message
)
from .keyboard import (
    get_current_weather_backup_keyboard,
    get_forecast_weather_backup_keyboard,
    CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT,
    CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_3D, 
    CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST,
    CALLBACK_WEATHER_BACKUP_SHOW_CURRENT_W,
    CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_TOMORROW
)
from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard, WEATHER_PREFIX as MAIN_WEATHER_PREFIX
from src.modules.weather.keyboard import get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO
from src.handlers.utils import show_main_menu_message


logger = logging.getLogger(__name__)
router = Router(name="weather-backup-module")

class WeatherBackupStates(StatesGroup):
    waiting_for_location = State()
    showing_current = State()
    showing_forecast_3d = State() 
    showing_forecast_tomorrow = State() 
    waiting_for_save_decision = State()


async def _fetch_and_show_backup_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    location_input: str, 
    show_forecast_days: Optional[int] = None,
    is_coords_request: bool = False
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False

    action_text = "⏳ Отримую резервні дані..."
    if show_forecast_days == 1:
        action_text = "⏳ Отримую резервний прогноз на завтра..."
    elif show_forecast_days and show_forecast_days > 1:
        action_text = f"⏳ Отримую резервний прогноз на {show_forecast_days} дні..."

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _fetch_and_show_backup_weather for user {user_id}: {e}")
    
    try:
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
        else:
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for backup weather, user {user_id}: {e}")

    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_response_data: Dict[str, Any]
    formatted_message_text: str
    reply_markup: Optional[InlineKeyboardMarkup] = None
    
    api_days_to_request = 3 
    if show_forecast_days == 1:
        api_days_to_request = 3 

    if show_forecast_days is not None:
        api_response_data = await get_forecast_weatherapi(bot, location=location_input, days=api_days_to_request)
        if show_forecast_days == 1:
            formatted_message_text = format_tomorrow_forecast_backup_message(api_response_data, requested_location=location_input)
        else:
            formatted_message_text = format_forecast_backup_message(api_response_data, requested_location=location_input)
    else:
        api_response_data = await get_current_weather_weatherapi(bot, location=location_input)
        formatted_message_text = format_weather_backup_message(api_response_data, requested_location=location_input)

    is_api_error = "error" in api_response_data and isinstance(api_response_data.get("error"), dict)

    if is_api_error:
        reply_markup = get_weather_enter_city_back_keyboard()
        await state.set_state(WeatherBackupStates.waiting_for_location)
        logger.warning(f"User {user_id}: API error for backup weather/forecast. State set to waiting_for_location. Response: {api_response_data}")
    else:
        api_city_name = api_response_data.get("location", {}).get("name")
        city_to_save_confirmed_backup = api_city_name if api_city_name else None

        await state.update_data(
            current_backup_location=location_input,
            current_backup_api_city_name=api_city_name,
            is_backup_coords=is_coords_request,
            city_to_save_confirmed_backup=city_to_save_confirmed_backup
        )
        logger.debug(f"User {user_id}: Backup weather/forecast FSM data updated. API city: {api_city_name}, Input: {location_input}")

        if show_forecast_days == 1:
            await state.set_state(WeatherBackupStates.showing_forecast_tomorrow)
            reply_markup = get_forecast_weather_backup_keyboard(is_tomorrow_forecast=True)
        elif show_forecast_days and show_forecast_days > 1:
            await state.set_state(WeatherBackupStates.showing_forecast_3d)
            reply_markup = get_forecast_weather_backup_keyboard(is_tomorrow_forecast=False)
        else:
            await state.set_state(WeatherBackupStates.showing_current)
            reply_markup = get_current_weather_backup_keyboard()

        db_user = await session.get(User, user_id)
        # Додамо перевірку, чи db_user не None, перед доступом до preferred_city
        preferred_city_from_db = None
        if db_user:
            preferred_city_from_db = db_user.preferred_city
        else:
            logger.error(f"User {user_id} not found in DB in _fetch_and_show_backup_weather. Cannot check preferred city.")
        
        ask_to_save = False

        if city_to_save_confirmed_backup and \
           (not preferred_city_from_db or preferred_city_from_db.lower() != city_to_save_confirmed_backup.lower()):
            ask_to_save = True
        
        if ask_to_save:
            prompt_city_name = city_to_save_confirmed_backup.capitalize()
            formatted_message_text += f"\n\n💾 Зберегти <b>{prompt_city_name}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await state.set_state(WeatherBackupStates.waiting_for_save_decision)
            logger.info(f"User {user_id}: Asking to save '{prompt_city_name}' (from backup module). FSM to waiting_for_save_decision.")

    try:
        if status_message:
            await final_target_message.edit_text(formatted_message_text, reply_markup=reply_markup)
        else:
            await message_to_edit_or_answer.answer(formatted_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent/edited backup weather/forecast for location_input='{location_input}'.")
    except Exception as e:
        logger.error(f"Error sending/editing final message for backup weather: {e}")
        if is_api_error and not status_message :
            try: await message_to_edit_or_answer.answer("Не вдалося відобразити резервну погоду. Спробуйте пізніше.")
            except: pass

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
        await state.set_data({})

    location_to_use: Optional[str] = None
    db_user = await session.get(User, user_id)
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
        await _fetch_and_show_backup_weather(bot, target, state, session, location_input=location_to_use)
    else:
        logger.info(f"User {user_id}: No preferred city for backup weather. Asking for location input.")
        # Тимчасово прибираємо вимогу української мови з підказки
        text = "Будь ласка, введіть назву міста (або 'lat,lon') для резервного сервісу погоди, або надішліть геолокацію."
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            if isinstance(target, CallbackQuery):
                 await target_message.edit_text(text, reply_markup=reply_markup)
            else:
                 await target_message.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message to ask for backup location: {e}")
            if isinstance(target, CallbackQuery):
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
    
    is_coords_input = False
    if ',' in location_input:
        parts = location_input.split(',')
        if len(parts) == 2:
            try: float(parts[0].strip()); float(parts[1].strip()); is_coords_input = True
            except ValueError: pass 

    # --- ТИМЧАСОВО ВИМКНЕНО ПЕРЕВІРКУ НА УКРАЇНСЬКУ МОВУ ВВЕДЕННЯ ---
    # if not is_coords_input and not re.match(r"^[А-Яа-яЁёІіЇїЄєҐґ\s\-\']+$", location_input):
    #     try:
    #         await message.answer(
    #             "😔 Будь ласка, введіть назву міста українською мовою, або точні координати (lat,lon).",
    #             reply_markup=get_weather_enter_city_back_keyboard()
    #         )
    #     except Exception as e: logger.error(f"Error sending 'use Ukrainian input for backup' message: {e}")
    #     return
    # --- КІНЕЦЬ ТИМЧАСОВО ВИМКНЕНОЇ ПЕРЕВІРКИ ---
        
    # Загальна перевірка на довжину (можна залишити)
    if len(location_input) > 100:
        try: await message.answer("😔 Назва міста або координати занадто довгі (максимум 100 символів).", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending location too long message: {e}")
        return
    # Загальна перевірка на символи (можна залишити, вона дозволяє латиницю)
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄєҐґ\s\-\.\,'\d]+$", location_input): # Додано кому для координат
        try: await message.answer("😔 Назва міста або координати містять неприпустимі символи.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending invalid location chars message: {e}")
        return

    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input, is_coords_request=is_coords_input)


@router.message(WeatherBackupStates.waiting_for_location, F.location)
async def handle_backup_geolocation_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} sent geolocation for backup weather: lat={lat}, lon={lon}")
    location_input_str = f"{lat},{lon}"
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, is_coords_request=True)

async def weather_backup_geolocation_entry_point(
    message: Message, state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = message.from_user.id
    lat = message.location.latitude
    lon = message.location.longitude
    logger.info(f"User {user_id} initiated backup weather by geolocation directly: lat={lat}, lon={lon}")
    location_input_str = f"{lat},{lon}"
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input_str, is_coords_request=True)


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT, WeatherBackupStates.showing_current)
async def handle_refresh_current_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing current backup weather for location: '{location}', is_coords={is_coords}.")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, is_coords_request=is_coords)
    else:
        logger.warning(f"User {user_id}: No location found in state for refreshing current backup weather.")
        answered = False
        try:
            await callback.answer("Помилка: дані для оновлення не знайдено.", show_alert=True)
            answered = True
        except Exception as e: logger.warning(f"Could not answer callback (refresh error): {e}")
        
        # Тимчасово прибираємо вимогу української мови з підказки
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


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_3D, WeatherBackupStates.showing_current)
async def handle_show_forecast_3d_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting backup 3-day forecast for location: '{location}', is_coords={is_coords}.")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast_days=3, is_coords_request=is_coords)
    else:
        # ... (аналогічна обробка помилки, як вище)
        logger.warning(f"User {user_id}: No location found in state for backup 3d forecast.")
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:"
        # ...
        await state.set_state(WeatherBackupStates.waiting_for_location)


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST_TOMORROW, WeatherBackupStates.showing_current)
async def handle_show_forecast_tomorrow_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting backup tomorrow's forecast for location: '{location}', is_coords={is_coords}.")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast_days=1, is_coords_request=is_coords)
    else:
        # ... (аналогічна обробка помилки) ...
        logger.warning(f"User {user_id}: No location found in state for backup tomorrow's forecast.")
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу на завтра:"
        # ...
        await state.set_state(WeatherBackupStates.waiting_for_location)


@router.callback_query(
    F.data == CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST, 
    WeatherBackupStates.showing_forecast_3d, 
    WeatherBackupStates.showing_forecast_tomorrow
)
async def handle_refresh_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    current_fsm_state_str = await state.get_state() 
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} refreshing backup forecast (state: {current_fsm_state_str}) for location: '{location}', is_coords={is_coords}.")

    days_to_refresh = 3 
    if current_fsm_state_str == WeatherBackupStates.showing_forecast_tomorrow.state:
        days_to_refresh = 1

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast_days=days_to_refresh, is_coords_request=is_coords)
    else:
        # ... (аналогічна обробка помилки) ...
        logger.warning(f"User {user_id}: No location found in state for refreshing backup forecast.")
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервного прогнозу:"
        # ...
        await state.set_state(WeatherBackupStates.waiting_for_location)


@router.callback_query(
    F.data == CALLBACK_WEATHER_BACKUP_SHOW_CURRENT_W, 
    WeatherBackupStates.showing_forecast_3d, 
    WeatherBackupStates.showing_forecast_tomorrow
)
async def handle_show_current_from_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    is_coords = user_fsm_data.get("is_backup_coords", False)
    logger.info(f"User {user_id} requesting to show current backup weather (from forecast view) for: '{location}', is_coords={is_coords}.")

    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, is_coords_request=is_coords)
    else:
        # ... (аналогічна обробка помилки) ...
        logger.warning(f"User {user_id}: No location found in state for showing current backup weather from forecast.")
        text = "Будь ласка, введіть місто (або надішліть геолокацію) для резервної погоди:"
        # ...
        await state.set_state(WeatherBackupStates.waiting_for_location)


@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_YES, WeatherBackupStates.waiting_for_save_decision)
async def handle_backup_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city (from backup module). FSM data: {user_fsm_data}")

    city_to_save = user_fsm_data.get("city_to_save_confirmed_backup")
    display_city_name = user_fsm_data.get("current_backup_api_city_name", city_to_save)

    answered_callback = False
    try:
        await callback.answer("Зберігаю місто як основне...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_backup_save_city_yes: {e}")

    final_text = ""
    final_markup = get_current_weather_backup_keyboard() 

    if not city_to_save:
        logger.error(f"User {user_id}: 'city_to_save_confirmed_backup' is missing in FSM. Cannot save.")
        final_text = "Помилка: не вдалося визначити місто для збереження."
    else:
        db_user = await session.get(User, user_id)
        if db_user:
            try:
                old_preferred_city = db_user.preferred_city
                db_user.preferred_city = city_to_save 
                session.add(db_user)
                logger.info(f"User {user_id}: Preferred city (main) set to '{city_to_save}' (was '{old_preferred_city}') via backup module.")
                final_text = f"✅ Місто <b>{display_city_name or city_to_save}</b> збережено як ваше основне."
            except Exception as e_db:
                logger.exception(f"User {user_id}: DB error while saving preferred_city '{city_to_save}': {e_db}", exc_info=True)
                await session.rollback()
                final_text = "😥 Виникла помилка під час збереження міста."
        else:
            logger.error(f"User {user_id} not found in DB during save city (backup module).")
            final_text = "Помилка: не вдалося знайти ваші дані."
    
    await state.set_state(WeatherBackupStates.showing_current) 
    try:
        original_weather_text_parts = callback.message.text.split("\n\n💾 Зберегти", 1)
        weather_part = original_weather_text_parts[0] if original_weather_text_parts else "Резервна погода"
        
        await callback.message.edit_text(f"{weather_part}\n\n{final_text}", reply_markup=final_markup)

    except Exception as e_edit:
        logger.error(f"Failed to edit message after save city (YES) decision in backup: {e_edit}")
        try: await callback.message.answer(final_text, reply_markup=final_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after save city (YES) decision in backup: {e_ans}")

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_NO, WeatherBackupStates.waiting_for_save_decision)
async def handle_backup_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city (from backup module). FSM data: {user_fsm_data}")
    
    city_display_name_from_prompt = user_fsm_data.get("current_backup_api_city_name", "поточне місто")
    
    original_message_text = callback.message.text
    text_after_no_save = original_message_text.split("\n\n💾 Зберегти", 1)[0] 
    text_after_no_save += f"\n\n(Місто <b>{city_display_name_from_prompt}</b> не було збережено як основне)"

    answered_callback = False
    try:
        await callback.answer("Місто не збережено.")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_backup_save_city_no: {e}")

    reply_markup = get_current_weather_backup_keyboard() 
    await state.set_state(WeatherBackupStates.showing_current)
    try:
        await callback.message.edit_text(text_after_no_save, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Failed to edit message after user chose NOT to save city (backup): {e_edit}")
        try: await callback.message.answer(text_after_no_save, reply_markup=reply_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after user chose NOT to save city (backup): {e_ans}")

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == f"{MAIN_WEATHER_PREFIX}:back_main", WeatherBackupStates.waiting_for_location)
async def handle_backup_weather_back_to_main_from_input(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} pressed 'Back to Main' from backup weather location input. Setting state to None.")
    await state.set_state(None)
    await show_main_menu_message(callback)