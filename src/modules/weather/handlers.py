# src/modules/weather/handlers.py

import logging
import re
from typing import Union, Optional, Dict, Any
from aiogram import Bot, Router, F # MagicFilter удален, если не используется
from aiogram.filters import StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

# Импорты
from src.db.models import User
from .keyboard import (
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO,
    CALLBACK_WEATHER_FORECAST_5D, CALLBACK_WEATHER_SHOW_CURRENT, get_forecast_keyboard
)
from .service import (
    get_weather_data, format_weather_message,
    get_5day_forecast, format_forecast_message,
    get_weather_data_by_coords
)
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()

async def _get_and_show_weather(
    bot: Bot, target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession,
    city_input: Optional[str] = None, coords: Optional[Dict[str, float]] = None
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    is_preferred = False
    request_details = ""
    is_coords_request_flag = False

    logger.info(f"_get_and_show_weather: Called for user {user_id}. city_input='{city_input}', coords={coords}")

    try:
        action_text = "🔍 Отримую дані про погоду..."
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке/редактировании статусного сообщения
        if isinstance(target, CallbackQuery):
            try:
                status_message = await message_to_edit_or_answer.edit_text(action_text)
                await target.answer()
            except Exception as e:
                 logger.error(f"Error editing message for initial status in _get_and_show_weather (callback): {e}")
                 # Fallback to sending a new message if editing fails
                 try: status_message = await target.message.answer(action_text); await target.answer()
                 except Exception as e2: logger.error(f"Error sending new message for initial status (callback fallback): {e2}"); status_message = message_to_edit_or_answer # Final fallback
        elif hasattr(target, 'location') and target.location:
             try: status_message = await target.answer(action_text)
             except Exception as e: logger.error(f"Error sending message for initial status in _get_and_show_weather (location): {e}"); status_message = target # Fallback
        else:
            try: status_message = await target.answer(action_text)
            except Exception as e: logger.error(f"Error sending message for initial status in _get_and_show_weather (message): {e}"); status_message = target # Fallback

    except Exception as e:
        # This outer except might catch errors before sending any message, less likely now
        logger.error(f"Unexpected error before sending/editing status message for weather: {e}")
        status_message = message_to_edit_or_answer # Ensure status_message is set even on error


    weather_data = None
    preferred_city_from_db = None
    city_to_save_in_db = None

    if coords:
        is_coords_request_flag = True
        request_details = f"coords ({coords['lat']:.4f}, {coords['lon']:.4f})"
        logger.info(f"User {user_id} requesting weather by {request_details}")
        weather_data = await get_weather_data_by_coords(bot, coords['lat'], coords['lon'])
        logger.debug(f"_get_and_show_weather: For coords, weather_data from service: {str(weather_data)[:300]}")
        is_preferred = False
        db_user_for_coords = await session.get(User, user_id)
        if db_user_for_coords:
            preferred_city_from_db = db_user_for_coords.preferred_city
    elif city_input:
        is_coords_request_flag = False
        request_details = f"city '{city_input}'"
        logger.info(f"User {user_id} requesting weather by {request_details}")
        weather_data = await get_weather_data(bot, city_input)
        logger.debug(f"_get_and_show_weather: For city_input='{city_input}', weather_data from service: {str(weather_data)[:300]}")
        
        db_user = await session.get(User, user_id)
        if db_user:
            preferred_city_from_db = db_user.preferred_city

        if weather_data and str(weather_data.get("cod")) == "200":
            api_city_name = weather_data.get("name")
            logger.info(f"_get_and_show_weather: For city_input='{city_input}', API returned name='{api_city_name}'")
            city_to_save_in_db = api_city_name

            if preferred_city_from_db and api_city_name:
                if preferred_city_from_db.lower() == api_city_name.lower():
                    is_preferred = True
            if preferred_city_from_db and not is_preferred:
                 if preferred_city_from_db.lower() == city_input.strip().lower():
                      is_preferred = True
            logger.info(f"_get_and_show_weather: For city_input='{city_input}', preferred_city_from_db='{preferred_city_from_db}', api_city_name='{api_city_name}', is_preferred={is_preferred}")
    else:
        logger.error(f"No city_input or coords provided for user {user_id} in _get_and_show_weather.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке финального повідомлення про помилку
        error_text = "Помилка: Не вказано місто або координати."
        try: await final_target_message.edit_text(error_text)
        except Exception as e: logger.error(f"Failed to edit message with 'no city/coords' error: {e}"); try: await message_to_edit_or_answer.answer(error_text); except Exception as e2: logger.error(f"Failed to send 'no city/coords' error message either: {e2}")
        await state.set_state(None) # Use set_state(None) instead of clear() here as well for consistency
        return

    final_target_message = status_message if status_message else message_to_edit_or_answer

    if weather_data and str(weather_data.get("cod")) == "200":
        actual_city_name_from_api = weather_data.get("name")
        logger.info(f"_get_and_show_weather: actual_city_name_from_api='{actual_city_name_from_api}' for request_details='{request_details}'")

        city_display_name_for_user_message: str
        if coords and actual_city_name_from_api:
            city_display_name_for_user_message = actual_city_name_from_api
        elif coords:
            city_display_name_for_user_message = "ваші координати"
        elif actual_city_name_from_api:
             city_display_name_for_user_message = actual_city_name_from_api.capitalize()
        elif city_input:
            city_display_name_for_user_message = city_input.capitalize()
        else:
            city_display_name_for_user_message = "Невідоме місце"
        
        logger.info(f"_get_and_show_weather: city_display_name_for_user_message (to format_weather_message)='{city_display_name_for_user_message}', is_coords_request_flag={is_coords_request_flag}")
        weather_message_text = format_weather_message(weather_data, city_display_name_for_user_message, is_coords_request_flag)
        current_shown_city_for_refresh_fsm = actual_city_name_from_api if actual_city_name_from_api else city_input if city_input else None
        logger.info(f"_get_and_show_weather: current_shown_city_for_refresh_fsm='{current_shown_city_for_refresh_fsm}'")

        state_data_to_update = {
            "city_to_save": city_to_save_in_db,
            "city_display_name": city_display_name_for_user_message,
            "current_shown_city": current_shown_city_for_refresh_fsm,
            "current_coords": coords,
            "preferred_city_from_db": preferred_city_from_db,
            "is_coords_request": is_coords_request_flag
        }
        logger.debug(f"User {user_id}: PREPARING to update FSM state in _get_and_show_weather with: {state_data_to_update}")
        await state.update_data(**state_data_to_update)
        current_fsm_data_after_update = await state.get_data()
        logger.debug(f"User {user_id}: FSM data AFTER update in _get_and_show_weather: {current_fsm_data_after_update}")
        ask_to_save = city_input is not None and not is_preferred and city_to_save_in_db is not None
        text_to_send = weather_message_text
        reply_markup = None
        if ask_to_save:
            save_prompt_city_name = city_to_save_in_db.capitalize() if city_to_save_in_db else city_input.capitalize()
            text_to_send += f"\n\n💾 Зберегти <b>{save_prompt_city_name}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await state.set_state(WeatherStates.waiting_for_save_decision)
            logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_save_decision. Asking to save '{save_prompt_city_name}'.")
        else:
            reply_markup = get_weather_actions_keyboard()
            current_fsm_state_name = await state.get_state()
            # ИСПРАВЛЕНИЕ: Используем set_state(None) чтобы выйти из текущего состояния, если это не состояние сохранения
            # Проверяем, находится ли пользователь в состоянии waiting_for_city
            if current_fsm_state_name == WeatherStates.waiting_for_city.state:
                 logger.info(f"User {user_id}: Weather shown (city '{city_input}' is preferred or from geo). Setting FSM state to None from waiting_for_city.")
                 await state.set_state(None)
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке финального сообщения
        try:
            await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit final weather message: {e}")
            try: await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new final weather message either: {e2}")

    elif weather_data and (str(weather_data.get("cod")) == "404"):
        city_error_name = city_input if city_input else "вказана локація"
        error_text = f"😔 На жаль, місто/локація '<b>{city_error_name}</b>' не знайдено."
        reply_markup = get_weather_enter_city_back_keyboard()
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке финального сообщения
        try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit 404 error message: {e}")
            try: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new 404 error message either: {e2}")
        logger.warning(f"Location '{request_details}' not found for user {user_id} (404). Setting FSM state to None.")
        await state.set_state(None) # Use set_state(None) instead of clear()

    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details} (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке финального сообщения
        try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit other error message: {e}")
            try: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new other error message either: {e2}")
        logger.error(f"Failed to get weather for {request_details} for user {user_id}. API Response: {weather_data}. Setting FSM state to None.")
        await state.set_state(None) # Use set_state(None) instead of clear()


async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    # Логика очистки состояния, если пользователь не в состоянии погоды
    current_fsm_state_name = await state.get_state()
    # Логіка перевірки та очищення стану при вході в модуль погоди.
    # Залишаємо state.clear() при вході ззовні для повного скидання стану,
    # якщо це не продовження поточного стану погоди.
    if current_fsm_state_name is not None and current_fsm_state_name.startswith("WeatherStates"):
         logger.info(f"User {user_id}: Already in a WeatherStates ({current_fsm_state_name}) at weather_entry_point.")
         # Не очищаємо стан, якщо вже в стані погоди
    elif current_fsm_state_name is not None:
        # В іншому стані FSM, очищаємо його
        logger.info(f"User {user_id}: In another FSM state ({current_fsm_state_name}), clearing before main weather.")
        await state.clear() # Очищаем весь FSM state, так как входим в новый модуль
    else: # current_fsm_state_name is None
        logger.info(f"User {user_id}: State was None, clearing data at weather_entry_point.")
        await state.clear() # Очищаем данные, если состояние None

    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)
    # ИСПРАВЛЕНИЕ: Обработка случая, если target - CallbackQuery и answer() вызывает ошибку
    if isinstance(target, CallbackQuery):
        try: await target.answer()
        except Exception as e: logger.warning(f"Could not answer callback in weather_entry_point: {e}")

    preferred_city = db_user.preferred_city if db_user else None
    logger.info(f"weather_entry_point: User {user_id}, preferred_city from DB: '{preferred_city}'")
    if preferred_city:
        # Встановлюємо стан ПЕРЕД викликом _get_and_show_weather, якщо погода буде показана одразу
        # Це важливо, щоб _get_and_show_weather знала, в якому стані завершити
        await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
        await _get_and_show_weather(bot, target, state, session, city_input=preferred_city)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (new user or DB error)") + " has no preferred city."
        logger.info(log_msg)
        text = "🌍 Будь ласка, введіть назву міста або надішліть геолокацію:"
        reply_markup = get_weather_enter_city_back_keyboard()
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try:
            if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
            else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message in weather_entry_point (ask for city): {e}")
            if isinstance(target, CallbackQuery):
                try: await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city.")


@router.message(WeatherStates.waiting_for_city, F.location)
async def handle_location_when_waiting(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: handle_location_when_waiting for user {user_id}: lat={lat}, lon={lon}")
        # Устанавливаем состояние перед показом
        await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: handle_location_when_waiting (main weather) called without message.location.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.reply("Не вдалося отримати вашу геолокацію.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' message: {e}")

async def process_main_geolocation_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    # Эта функция вызывается из common_handlers.handle_any_geolocation
    # common_handlers уже установил state в None при необходимости
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: process_main_geolocation_button for user {user_id}: lat={lat}, lon={lon}")
        # Устанавливаем состояние перед показом
        await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
        # Передаем обработку в основную функцию показа погоды
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: process_main_geolocation_button called without message.location.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.reply("Не вдалося отримати вашу геолокацію.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' message (from button): {e}")


@router.message(WeatherStates.waiting_for_city, F.text)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_city_input = message.text.strip() if message.text else ""
    logger.info(f"handle_city_input: User {message.from_user.id} entered city '{user_city_input}'. Current FSM state: {await state.get_state()}")
    if not user_city_input:
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.answer("😔 Будь ласка, введіть назву міста (текст не може бути порожнім).", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending empty city input message: {e}")
        return
    if len(user_city_input) > 100:
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.answer("😔 Назва міста занадто довга (максимум 100 символів). Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending city name too long message: {e}")
        return
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄє\s\-\.\']+$", user_city_input):
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при отправке сообщения
        try: await message.answer("😔 Назва міста може містити лише літери, пробіли, дефіси, апострофи та крапки. Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending invalid city name chars message: {e}")
        return
    # Устанавливаем состояние перед показом
    await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
    await _get_and_show_weather(bot, message, state, session, city_input=user_city_input)

@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested OTHER city. Current FSM state before setting waiting_for_city: {await state.get_state()}, data: {await state.get_data()}")
    # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
    try: await callback.message.edit_text("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    except Exception as e:
        logger.error(f"Failed to edit message for 'other city' input: {e}")
        try: await callback.message.answer("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e2: logger.error(f"Failed to send message for 'other city' input either: {e2}")
    await state.set_state(WeatherStates.waiting_for_city)
    logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city (from Other City callback).")
    try: await callback.answer() # Отвечаем на колбэк
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_other_city: {e}")


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    current_fsm_state_name_on_refresh = await state.get_state()
    logger.info(f"User {user_id} requested REFRESH (main weather). Current FSM state: {current_fsm_state_name_on_refresh}, FSM data: {user_data}")
    coords = user_data.get("current_coords")
    city_name_to_refresh = user_data.get("current_shown_city")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Оновлюю дані...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_refresh: {e}")

    if coords:
        logger.info(f"User {user_id} refreshing main weather by coords: {coords}")
        # Устанавливаем состояние перед показом
        await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
        await _get_and_show_weather(bot, callback, state, session, coords=coords)
    elif city_name_to_refresh:
        logger.info(f"User {user_id} refreshing main weather for city: '{city_name_to_refresh}'")
        # Устанавливаем состояние перед показом
        await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
        await _get_and_show_weather(bot, callback, state, session, city_input=city_name_to_refresh)
    else:
        logger.warning(f"User {user_id} requested REFRESH (main), but no city_name_to_refresh or coords found in FSM state. Attempting preferred city from DB.")
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: No specific city in state for main refresh, using preferred city '{preferred_city_from_db}' from DB.")
            # Устанавливаем состояние перед показом
            await state.set_state(WeatherStates.waiting_for_save_decision) # Початковий стан після показу погоди
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city in DB for main refresh. Asking to input city.")
            # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
            error_text = "😔 Не вдалося визначити місто для оновлення. Будь ласка, введіть місто:"
            reply_markup = get_weather_enter_city_back_keyboard()
            try: await callback.message.edit_text(error_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message after refresh failure: {e}")
                try: await callback.message.answer(error_text, reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Failed to send message after refresh failure either: {e2}")
            await state.set_state(WeatherStates.waiting_for_city)
            # callback.answer() уже сделан выше

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city. FSM state: {await state.get_state()}, FSM data BEFORE save: {user_data}")
    city_to_actually_save_in_db = user_data.get("city_to_save")
    city_name_user_saw_in_prompt = user_data.get("city_display_name", city_to_actually_save_in_db)
    # Отвечаем на колбэк сразу
    try: await callback.answer("Зберігаю місто...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_yes: {e}")

    if not city_to_actually_save_in_db:
        logger.error(f"User {user_id}: 'city_to_save' is missing in FSM data. Cannot save. Data: {user_data}")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Помилка: не вдалося визначити місто для збереження."
        reply_markup = get_weather_actions_keyboard()
        try: await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after save failure (no city_to_save): {e}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send message after save failure either: {e2}")
        await state.set_state(None)
        # callback.answer() уже сделан выше
        return
    db_user = await session.get(User, user_id)
    if db_user:
        try:
            old_preferred_city = db_user.preferred_city
            db_user.preferred_city = city_to_actually_save_in_db
            session.add(db_user)
            # Коммит будет выполнен DbSessionMiddleware
            logger.info(f"User {user_id}: Preferred city changed from '{old_preferred_city}' to '{city_to_actually_save_in_db}' for DB commit. User saw prompt for '{city_name_user_saw_in_prompt}'.")
            text_after_save = f"✅ Місто <b>{city_name_user_saw_in_prompt}</b> збережено як основне."
            await state.update_data(preferred_city_from_db=city_to_actually_save_in_db)
            logger.debug(f"User {user_id}: Updated 'preferred_city_from_db' in FSM state to '{city_to_actually_save_in_db}' after saving.")
            fsm_data_after_save_logic = await state.get_data()
            logger.debug(f"User {user_id}: FSM data AFTER save logic and state update, BEFORE setting state to None: {fsm_data_after_save_logic}")
            # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
            reply_markup = get_weather_actions_keyboard()
            try: await callback.message.edit_text(text_after_save, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message after successful save: {e}")
                try: await callback.message.answer(text_after_save, reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Failed to send message after successful save either: {e2}")

        except Exception as e:
            logger.exception(f"User {user_id}: DB error while saving preferred city '{city_to_actually_save_in_db}': {e}", exc_info=True)
            await session.rollback() # Rollback explicitly on error
            # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
            error_text = "😥 Виникла помилка під час збереження міста."
            reply_markup = get_weather_actions_keyboard()
            try: await callback.message.edit_text(error_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message after DB save error: {e}")
                try: await callback.message.answer(error_text, reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Failed to send message after DB save error either: {e2}")
    else:
        logger.error(f"User {user_id} not found in DB during save city.")
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
        error_text = "Помилка: не вдалося знайти ваші дані."
        reply_markup = get_weather_actions_keyboard()
        try: await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after DB user not found error: {e}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send message after DB user not found error either: {e2}")
            
    await state.set_state(None) # Use set_state(None) instead of clear()
    logger.info(f"User {user_id}: Set FSM state to None (was WeatherStates.waiting_for_save_decision) after saving city. Data should persist for user.")
    # callback.answer() уже сделан выше


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city. FSM state: {await state.get_state()}, FSM data: {user_data}")
    city_display_name_from_prompt = user_data.get("city_display_name", "поточне місто")
    original_weather_message_parts = callback.message.text.split('\n\n💾 Зберегти', 1)
    weather_part = original_weather_message_parts[0] if original_weather_message_parts else "Дані про погоду"
    text_after_no_save = f"{weather_part}\n\n(Місто <b>{city_display_name_from_prompt}</b> не було збережено як основне)"
    # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
    reply_markup = get_weather_actions_keyboard()
    try: await callback.message.edit_text(text_after_no_save, reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Failed to edit message after user chose NOT to save city: {e}")
        try: await callback.message.answer(text_after_no_save, reply_markup=reply_markup)
        except Exception as e2: logger.error(f"Failed to send message after user chose NOT to save city either: {e2}")

    await state.set_state(None) # Use set_state(None) instead of clear()
    logger.info(f"User {user_id}: Set FSM state to None (was WeatherStates.waiting_for_save_decision) after NOT saving city. Data should persist.")
    try: await callback.answer("Місто не збережено.") # Отвечаем на колбэк
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_no: {e}")


@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} requested 5-day FORECAST (main). Current FSM state: {await state.get_state()}, FSM data: {user_data}")
    city_name_for_api_request = user_data.get("current_shown_city")
    display_name_for_forecast_header = user_data.get("city_display_name", city_name_for_api_request)
    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested forecast (main), but 'current_shown_city' not found. Data: {user_data}")
        try: await callback.answer("Спочатку отримайте погоду для міста.", show_alert=True) # Отвечаем на колбэк с alert
        except Exception as e: logger.warning(f"Could not answer callback (no city for forecast): {e}")
        return
    # Отвечаем на колбэк сразу
    try: await callback.answer("Отримую прогноз на 5 днів...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_forecast_request: {e}")

    # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения о статусе
    status_message = None
    try: status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{display_name_for_forecast_header}</b>...")
    except Exception as e:
        logger.error(f"Failed to edit message for forecast status: {e}")
        try: status_message = await callback.message.answer(f"⏳ Отримую прогноз для: <b>{display_name_for_forecast_header}</b>...")
        except Exception as e2: logger.error(f"Failed to send forecast status message either: {e2}"); status_message = callback.message # Fallback

    forecast_api_data = await get_5day_forecast(bot, city_name_for_api_request)
    final_target_message = status_message if status_message else callback.message # Ensure final_target_message is set

    if forecast_api_data and str(forecast_api_data.get("cod")) == "200":
        message_text = format_forecast_message(forecast_api_data, display_name_for_forecast_header)
        reply_markup = get_forecast_keyboard()
        # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке финального сообщения
        try: await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit final forecast message: {e}")
            try: await callback.message.answer(message_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new final forecast message either: {e2}")
        logger.info(f"User {user_id}: Sent 5-day forecast (main) for API city '{city_name_for_api_request}' (display: '{display_name_for_forecast_header}').")
        # Можно установить состояние WeatherStates.showing_forecast здесь, если нужно
        # await state.set_state(WeatherStates.showing_forecast)
    else:
        error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'
        error_api_message = forecast_api_data.get('message', 'Невідома помилка API') if forecast_api_data else 'Не вдалося з\'єднатися з API'
        error_text = f"😥 Не вдалося отримати прогноз для <b>{display_name_for_forecast_header}</b>.\n<i>Помилка: {error_api_message} (Код: {error_code})</i>"
        reply_markup = get_weather_actions_keyboard()
        # ИСПРАВЛЕНИЕ: Улучшенная обробка помилок при редактировании/отправці фінального повідомлення
        try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after forecast failure: {e}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send message after forecast failure either: {e2}")
        logger.error(f"User {user_id}: Failed to get 5-day forecast (main) for API city '{city_name_for_api_request}'. API Response: {forecast_api_data}")


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} requested to show CURRENT weather again (main, from forecast view). FSM data: {user_data}")
    city_to_show_current = user_data.get("current_shown_city")
    coords_to_show_current = user_data.get("current_coords")
    # Отвечаем на колбэк сразу
    try: await callback.answer("Показую поточну погоду...")
    except Exception as e: logger.warning(f"Could not answer callback in handle_show_current_weather: {e}")

    if coords_to_show_current:
        logger.info(f"User {user_id}: Showing current weather (main) by COORDS again: {coords_to_show_current}")
        await _get_and_show_weather(bot, callback, state, session, coords=coords_to_show_current)
    elif city_to_show_current:
        logger.info(f"User {user_id}: Showing current weather (main) for CITY again: '{city_to_show_current}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_to_show_current)
    else:
        logger.warning(f"User {user_id}: Requested show current weather (main), but no city or coords in FSM state. Trying preferred.")
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: Showing weather (main) for preferred city '{preferred_city_from_db}' as fallback.")
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city (main). Redirecting to city input.")
            # ИСПРАВЛЕНИЕ: Улучшенная обработка ошибок при редактировании/отправке сообщения
            error_text = "🌍 Будь ласка, введіть назву міста:"
            reply_markup = get_weather_enter_city_back_keyboard()
            try: await callback.message.edit_text(error_text, reply_markup=reply_markup)
            except Exception as e:
                logger.error(f"Failed to edit message after show current failure: {e}")
                try: await callback.message.answer(error_text, reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Failed to send message after show current failure either: {e2}")
            await state.set_state(WeatherStates.waiting_for_city)
            # callback.answer() уже сделан выше


@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_fsm_state = await state.get_state()
    logger.info(f"User {user_id} requested back to main menu from weather module. Current FSM state: {current_fsm_state}. Setting weather FSM state to None.")
    await state.set_state(None) # Use set_state(None) instead of clear()
    await show_main_menu_message(callback)
    # show_main_menu_message уже делает callback.answer()
    # try: await callback.answer() # Отвечаем на колбэк
    # except Exception as e: logger.warning(f"Could not answer callback in handle_weather_back_to_main: {e}")