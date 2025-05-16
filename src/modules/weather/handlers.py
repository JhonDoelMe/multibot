# src/modules/weather/handlers.py

import logging
import re 
from typing import Union, Optional, Dict, Any

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User
from .keyboard import (
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO,
    CALLBACK_WEATHER_FORECAST_5D, CALLBACK_WEATHER_SHOW_CURRENT, get_forecast_keyboard,
    CALLBACK_WEATHER_FORECAST_TOMORROW
)
from .service import (
    get_weather_data, format_weather_message,
    get_5day_forecast, format_forecast_message,
    get_weather_data_by_coords,
    format_tomorrow_forecast_message
)
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()
    showing_weather = State() 
    showing_forecast = State()


async def _get_and_show_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    city_input: Optional[str] = None,
    coords: Optional[Dict[str, float]] = None
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False

    request_details_log = f"city '{city_input}'" if city_input else f"coords {coords}" if coords else "unknown request"
    logger.info(f"_get_and_show_weather: User {user_id}, request: {request_details_log}")

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _get_and_show_weather for user {user_id}: {e}")
    
    try:
        action_text = "🔍 Отримую дані про погоду..."
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
        else: 
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for weather, user {user_id}: {e}")

    weather_api_response: Dict[str, Any]
    is_coords_request_flag = False
    initial_display_location = city_input if city_input else ("ваші координати" if coords else "вказана локація")

    if coords:
        is_coords_request_flag = True
        weather_api_response = await get_weather_data_by_coords(bot, latitude=coords['lat'], longitude=coords['lon'])
    elif city_input:
        weather_api_response = await get_weather_data(bot, city_name=city_input)
    else:
        logger.error(f"No city_input or coords provided for user {user_id} in _get_and_show_weather.")
        error_text = "Помилка: Не вказано місто або координати для запиту погоди."
        target_msg_for_error = status_message if status_message else message_to_edit_or_answer
        try:
            if status_message: await target_msg_for_error.edit_text(error_text)
            else: await target_msg_for_error.answer(error_text)
        except Exception as e_send: logger.error(f"Failed to send 'no city/coords' error: {e_send}")
        await state.set_state(None)
        return

    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_city_name_raw = weather_api_response.get("name") if str(weather_api_response.get("cod")) == "200" else None
    city_display_name_for_message = api_city_name_raw or initial_display_location

    weather_message_text = format_weather_message(weather_api_response, city_display_name_for_message, is_coords_request_flag)

    if weather_api_response.get("status") == "error" or str(weather_api_response.get("cod")) != "200":
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            if status_message: await final_target_message.edit_text(weather_message_text, reply_markup=reply_markup)
            else: await message_to_edit_or_answer.answer(weather_message_text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit/send weather API error message: {e_edit}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.warning(f"API error/country restriction for weather request {request_details_log} for user {user_id}. Response: {weather_api_response}")
        return

    city_to_save_confirmed = api_city_name_raw
    logger.info(f"User {user_id}: API confirmed city='{api_city_name_raw}', to_save_confirmed='{city_to_save_confirmed}'")

    fsm_update_data = {
        "current_shown_city_api": api_city_name_raw if api_city_name_raw else (f"{coords['lat']},{coords['lon']}" if coords else city_input),
        "city_display_name_user": city_display_name_for_message,
        "city_to_save_confirmed": city_to_save_confirmed,
        "is_coords_request_fsm": is_coords_request_flag
    }
    await state.update_data(**fsm_update_data)
    logger.debug(f"User {user_id}: Updated FSM data: {fsm_update_data}")

    ask_to_save = False
    db_user = await session.get(User, user_id)
    if not db_user: # Перевірка, чи користувач існує, перед тим як намагатися зберегти місто
        logger.error(f"User {user_id} not found in DB before asking to save city. This should not happen if /start was processed.")
        # Можна просто не пропонувати зберегти або показати помилку
    else:
        preferred_city_from_db = db_user.preferred_city
        if city_to_save_confirmed and \
           (not preferred_city_from_db or preferred_city_from_db.lower() != city_to_save_confirmed.lower()):
            ask_to_save = True

    reply_markup = None
    if ask_to_save:
        save_prompt_city_name = city_to_save_confirmed.capitalize()
        weather_message_text_with_prompt = weather_message_text + \
            f"\n\n💾 Зберегти <b>{save_prompt_city_name}</b> як основне місто?"
        reply_markup = get_save_city_keyboard()
        await state.set_state(WeatherStates.waiting_for_save_decision)
        logger.info(f"User {user_id}: Asking to save '{save_prompt_city_name}'. Set FSM to waiting_for_save_decision.")
        message_to_send_final = weather_message_text_with_prompt
    else:
        reply_markup = get_weather_actions_keyboard()
        await state.set_state(WeatherStates.showing_weather)
        logger.info(f"User {user_id}: Weather shown for '{city_display_name_for_message}'. Set FSM to showing_weather.")
        message_to_send_final = weather_message_text

    try:
        if status_message: await final_target_message.edit_text(message_to_send_final, reply_markup=reply_markup)
        else: await message_to_edit_or_answer.answer(message_to_send_final, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Successfully sent/edited weather message for {request_details_log}.")
    except Exception as e_send_final:
        logger.error(f"Failed to send/edit final weather message for {request_details_log}: {e_send_final}")
    finally:
        if isinstance(target, CallbackQuery) and not answered_callback:
            try: await target.answer()
            except Exception: logger.warning(f"Final attempt to answer weather callback for user {user_id} failed.")


async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_entry_point.")
    
    current_fsm_state_name = await state.get_state()
    if current_fsm_state_name not in [None, WeatherStates.waiting_for_city.state, WeatherStates.showing_weather.state, WeatherStates.showing_forecast.state, WeatherStates.waiting_for_save_decision.state]:
        logger.info(f"User {user_id}: In an unrelated FSM state ({current_fsm_state_name}), clearing state before weather module.")
        await state.clear()
    elif current_fsm_state_name is None:
        await state.set_data({})

    answered_callback = False
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e: logger.warning(f"Could not answer callback in weather_entry_point: {e}")

    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)
    preferred_city = db_user.preferred_city if db_user else None
    
    if preferred_city:
        logger.info(f"weather_entry_point: User {user_id}, using preferred_city: '{preferred_city}'")
        await _get_and_show_weather(bot, target, state, session, city_input=preferred_city)
    else:
        logger.info(f"User {user_id} has no preferred city. Asking for input.")
        # Тимчасово прибираємо вимогу української мови з підказки
        text = "🌍 Будь ласка, введіть назву міста або надішліть геолокацію:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            if isinstance(target, CallbackQuery):
                await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
            else:
                await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message in weather_entry_point (ask for city): {e}")
            if isinstance(target, CallbackQuery):
                try: await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city.")
    
    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except: pass


@router.message(WeatherStates.waiting_for_city, F.location)
async def handle_location_when_waiting(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"Weather module: handle_location_when_waiting for user {user_id}: lat={lat}, lon={lon}")
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: handle_location_when_waiting called without message.location.")
        try: await message.reply("Не вдалося отримати вашу геолокацію. Спробуйте ще раз.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' message: {e}")

async def process_main_geolocation_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"Weather module: process_main_geolocation_button for user {user_id}: lat={lat}, lon={lon}")
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: process_main_geolocation_button called without message.location.")
        try: await message.reply("Не вдалося отримати вашу геолокацію для погоди.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' (from button): {e}")


@router.message(WeatherStates.waiting_for_city, F.text)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_city_input = message.text.strip() if message.text else ""
    user_id = message.from_user.id
    logger.info(f"handle_city_input: User {user_id} entered city '{user_city_input}'.")
    
    if not user_city_input:
        try: await message.answer("😔 Будь ласка, введіть назву міста.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending empty city input message: {e}")
        return

    # --- ТИМЧАСОВО ВИМКНЕНО ПЕРЕВІРКУ НА УКРАЇНСЬКУ МОВУ ВВЕДЕННЯ ---
    # if not re.match(r"^[А-Яа-яЁёІіЇїЄєҐґ\s\-\']+$", user_city_input):
    #     try:
    #         await message.answer(
    #             "😔 Будь ласка, введіть назву міста українською мовою, використовуючи лише українські літери, пробіл, дефіс або апостроф.",
    #             reply_markup=get_weather_enter_city_back_keyboard()
    #         )
    #     except Exception as e: logger.error(f"Error sending 'use Ukrainian input' message: {e}")
    #     return
    # --- КІНЕЦЬ ТИМЧАСОВО ВИМКНЕНОЇ ПЕРЕВІРКИ ---

    # Загальна перевірка на довжину та базові символи (можна залишити або спростити)
    if len(user_city_input) > 100:
        try: await message.answer("😔 Назва міста занадто довга (максимум 100 символів).", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending city name too long message: {e}")
        return
    # Цей re.match дозволяє латиницю, цифри тощо, що зараз нам підходить для тестування
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄєҐґ\s\-\.\'\d]+$", user_city_input):
        try: await message.answer("😔 Назва міста містить неприпустимі символи. Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending invalid city name chars message: {e}")
        return
        
    await _get_and_show_weather(bot, message, state, session, city_input=user_city_input)

@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY, WeatherStates.showing_weather)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested OTHER city from showing_weather state.")
    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_other_city: {e}")
    
    # Тимчасово прибираємо вимогу української мови з підказки
    text_prompt = "🌍 Введіть назву іншого міста:"
    try:
        await callback.message.edit_text(text_prompt, reply_markup=get_weather_enter_city_back_keyboard())
    except Exception as e_edit:
        logger.error(f"Failed to edit message for 'other city' input: {e_edit}")
        try: 
            await callback.message.answer(text_prompt, reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e_ans: logger.error(f"Failed to send new message for 'other city' input: {e_ans}")
    
    await state.set_state(WeatherStates.waiting_for_city)
    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH, WeatherStates.showing_weather)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested REFRESH. FSM data: {user_fsm_data}")
    
    api_request_location = user_fsm_data.get("current_shown_city_api")
    is_coords = user_fsm_data.get("is_coords_request_fsm", False)

    answered_callback = False
    try:
        await callback.answer("Оновлюю дані...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_refresh: {e}")

    if api_request_location:
        logger.info(f"User {user_id} refreshing weather for API location: '{api_request_location}', is_coords={is_coords}")
        coords_for_refresh = None
        city_for_refresh = None
        if is_coords and isinstance(api_request_location, str) and ',' in api_request_location:
            try:
                lat_str, lon_str = api_request_location.split(',')
                coords_for_refresh = {"lat": float(lat_str), "lon": float(lon_str)}
            except ValueError: api_request_location = None 
        elif not is_coords:
            city_for_refresh = api_request_location
        else: api_request_location = None 
            
        if coords_for_refresh:
            await _get_and_show_weather(bot, callback, state, session, coords=coords_for_refresh)
        elif city_for_refresh:
            await _get_and_show_weather(bot, callback, state, session, city_input=city_for_refresh)
        else: 
            api_request_location = None 
            
    if not api_request_location: 
        logger.warning(f"User {user_id}: No valid location found in FSM for refresh. Asking to input city.")
        # Тимчасово прибираємо вимогу української мови з підказки
        error_text = "😔 Не вдалося визначити дані для оновлення. Будь ласка, введіть місто:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after refresh failure: {e_edit}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message after refresh failure: {e_ans}")
        await state.set_state(WeatherStates.waiting_for_city)

    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_YES, WeatherStates.waiting_for_save_decision)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city. FSM data: {user_fsm_data}")

    city_to_actually_save_in_db = user_fsm_data.get("city_to_save_confirmed")
    city_name_user_saw_in_prompt = user_fsm_data.get("city_display_name_user", city_to_actually_save_in_db)

    answered_callback = False
    try:
        await callback.answer("Зберігаю місто...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_yes: {e}")

    final_text = ""
    final_markup = get_weather_actions_keyboard() 

    if not city_to_actually_save_in_db:
        logger.error(f"User {user_id}: 'city_to_save_confirmed' is missing in FSM data. Cannot save.")
        final_text = "Помилка: не вдалося визначити місто для збереження."
    else:
        db_user = await session.get(User, user_id)
        if db_user:
            try:
                old_preferred_city = db_user.preferred_city
                db_user.preferred_city = city_to_actually_save_in_db
                session.add(db_user)
                logger.info(f"User {user_id}: Preferred city set to '{city_to_actually_save_in_db}' (was '{old_preferred_city}').")
                final_text = f"✅ Місто <b>{city_name_user_saw_in_prompt or city_to_actually_save_in_db}</b> збережено як основне."
                await state.update_data(preferred_city_from_db_fsm=city_to_actually_save_in_db)
            except Exception as e_db:
                logger.exception(f"User {user_id}: DB error while saving preferred city '{city_to_actually_save_in_db}': {e_db}", exc_info=True)
                await session.rollback()
                final_text = "😥 Виникла помилка під час збереження міста."
        else: # Цей блок тепер досяжний, якщо _get_and_show_weather не знайшов користувача
            logger.error(f"User {user_id} not found in DB during save city operation (handle_save_city_yes).")
            final_text = "Помилка: не вдалося знайти ваші дані для збереження міста. Спробуйте /start."
    
    await state.set_state(WeatherStates.showing_weather)
    try:
        await callback.message.edit_text(final_text, reply_markup=final_markup)
    except Exception as e_edit:
        logger.error(f"Failed to edit message after save city (YES) decision: {e_edit}")
        try: await callback.message.answer(final_text, reply_markup=final_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after save city (YES) decision: {e_ans}")

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_NO, WeatherStates.waiting_for_save_decision)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city. FSM data: {user_fsm_data}")
    
    city_display_name_from_prompt = user_fsm_data.get("city_display_name_user", "поточне місто")
    original_message_text = callback.message.text
    text_after_no_save = original_message_text.split("\n\n💾 Зберегти", 1)[0]
    text_after_no_save += f"\n\n(Місто <b>{city_display_name_from_prompt}</b> не було збережено)"

    answered_callback = False
    try:
        await callback.answer("Місто не збережено.")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_no: {e}")

    reply_markup = get_weather_actions_keyboard()
    try:
        await callback.message.edit_text(text_after_no_save, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Failed to edit message after user chose NOT to save city: {e_edit}")
        try: await callback.message.answer(text_after_no_save, reply_markup=reply_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after user chose NOT to save city: {e_ans}")

    await state.set_state(WeatherStates.showing_weather)
    logger.info(f"User {user_id}: City not saved. Set FSM state to showing_weather.")
    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D, WeatherStates.showing_weather)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested 5-day FORECAST. FSM data: {user_fsm_data}")

    city_name_for_api_request = user_fsm_data.get("current_shown_city_api")
    display_name_for_forecast_header = user_fsm_data.get("city_display_name_user", city_name_for_api_request)
    
    answered_callback = False
    status_message = None

    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested 5d forecast, but 'current_shown_city_api' not found.")
        try:
            await callback.answer("Помилка: місто для прогнозу не визначено.", show_alert=True)
            answered_callback = True
        except Exception: pass
        return

    try:
        await callback.answer("Отримую прогноз на 5 днів...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_forecast_request: {e}")

    try:
        status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{display_name_for_forecast_header}</b>...")
    except Exception as e_edit_status:
        logger.warning(f"Failed to edit message for 5d forecast status: {e_edit_status}")

    final_target_message = status_message if status_message else callback.message
    full_forecast_api_response = await get_5day_forecast(bot, city_name=city_name_for_api_request) 
    
    message_text = format_forecast_message(full_forecast_api_response, display_name_for_forecast_header)
    reply_markup = get_forecast_keyboard()

    try:
        if status_message: await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        else: await callback.message.answer(message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent 5-day forecast for '{display_name_for_forecast_header}'.")
        await state.set_state(WeatherStates.showing_forecast)
    except Exception as e_edit_final:
        logger.error(f"Failed to edit/send final 5d forecast message: {e_edit_final}")

    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_TOMORROW, WeatherStates.showing_weather)
async def handle_tomorrow_forecast_request(callback: CallbackQuery, state: FSMContext, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested TOMORROW'S FORECAST. FSM data: {user_fsm_data}")

    city_name_for_api_request = user_fsm_data.get("current_shown_city_api")
    display_name_for_header = user_fsm_data.get("city_display_name_user", city_name_for_api_request)
    
    answered_callback = False
    status_message = None

    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested tomorrow's forecast, but 'current_shown_city_api' not found.")
        try:
            await callback.answer("Помилка: місто для прогнозу не визначено. Спробуйте оновити погоду.", show_alert=True)
            answered_callback = True
        except Exception: pass
        return

    try:
        await callback.answer("Отримую прогноз на завтра...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_tomorrow_forecast_request: {e}")

    try:
        status_message = await callback.message.edit_text(f"⏳ Отримую прогноз на завтра для: <b>{display_name_for_header}</b>...")
    except Exception as e_edit_status:
        logger.warning(f"Failed to edit message for tomorrow's forecast status: {e_edit_status}")

    final_target_message = status_message if status_message else callback.message
    full_forecast_api_response = await get_5day_forecast(bot, city_name=city_name_for_api_request) 
    
    message_text = format_tomorrow_forecast_message(full_forecast_api_response, display_name_for_header)
    reply_markup = get_forecast_keyboard()

    try:
        if status_message: await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        else: await callback.message.answer(message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent tomorrow's forecast for '{display_name_for_header}'.")
        await state.set_state(WeatherStates.showing_forecast) 
    except Exception as e_edit_final:
        logger.error(f"Failed to edit/send final tomorrow's forecast message: {e_edit_final}")

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT, WeatherStates.showing_forecast)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested to show CURRENT weather again (from forecast view). FSM data: {user_fsm_data}")

    api_request_location = user_fsm_data.get("current_shown_city_api")
    is_coords = user_fsm_data.get("is_coords_request_fsm", False)
    
    answered_callback = False
    try:
        await callback.answer("Показую поточну погоду...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_show_current_weather: {e}")

    if api_request_location:
        coords_to_show = None
        city_to_show = None
        if is_coords and isinstance(api_request_location, str) and ',' in api_request_location:
            try:
                lat_str, lon_str = api_request_location.split(',')
                coords_to_show = {"lat": float(lat_str), "lon": float(lon_str)}
            except ValueError: api_request_location = None
        elif not is_coords:
            city_to_show = api_request_location
        else: api_request_location = None 
            
        if coords_to_show:
            await _get_and_show_weather(bot, callback, state, session, coords=coords_to_show)
        elif city_to_show:
            await _get_and_show_weather(bot, callback, state, session, city_input=city_to_show)
        else: 
            api_request_location = None 
    
    if not api_request_location: 
        logger.warning(f"User {user_id}: No valid location in FSM to show current weather from forecast. Asking to input city.")
        # Тимчасово прибираємо вимогу української мови з підказки
        error_text = "🌍 Будь ласка, введіть назву міста:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after show current failure: {e_edit}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message after show current failure: {e_ans}")
        await state.set_state(WeatherStates.waiting_for_city)

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(
    F.data == CALLBACK_WEATHER_BACK_TO_MAIN, 
    WeatherStates.waiting_for_city, 
    WeatherStates.showing_weather, 
    WeatherStates.showing_forecast, 
    WeatherStates.waiting_for_save_decision
)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_fsm_state = await state.get_state()
    logger.info(f"User {user_id} requested back to main menu from weather module (state: {current_fsm_state}). Setting FSM state to None.")
    await state.set_state(None) # Або state.clear(), якщо потрібно очистити і дані FSM
    await show_main_menu_message(callback) # Ця функція має обробити callback.answer()