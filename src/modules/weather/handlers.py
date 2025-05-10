# src/modules/weather/handlers.py

import logging
import re
from typing import Union, Optional, Dict, Any
from aiogram import Bot, Router, F
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

    logger.info(f"_get_and_show_weather: Called for user {user_id}. city_input='{city_input}', coords={coords}")

    try:
        action_text = "🔍 Отримую дані про погоду..."
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
            await target.answer()
        elif hasattr(target, 'location') and target.location:
            status_message = await target.answer(action_text)
        else:
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.error(f"Error sending/editing status message for weather: {e}")
        status_message = message_to_edit_or_answer

    weather_data = None
    preferred_city_from_db = None
    city_to_save_in_db = None # Имя города от API, которое будет сохранено в БД

    if coords:
        request_details = f"coords ({coords['lat']:.4f}, {coords['lon']:.4f})"
        logger.info(f"User {user_id} requesting weather by {request_details}")
        weather_data = await get_weather_data_by_coords(bot, coords['lat'], coords['lon'])
        logger.debug(f"_get_and_show_weather: For coords, weather_data from service: {str(weather_data)[:300]}")
        is_preferred = False # По координатам не предлагаем сохранение как "предпочтительный"
        db_user_for_coords = await session.get(User, user_id)
        if db_user_for_coords:
            preferred_city_from_db = db_user_for_coords.preferred_city
    elif city_input:
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
            city_to_save_in_db = api_city_name # Это имя от API будем сохранять

            if preferred_city_from_db and api_city_name:
                if preferred_city_from_db.lower() == api_city_name.lower():
                    is_preferred = True
            if preferred_city_from_db and not is_preferred:
                 if preferred_city_from_db.lower() == city_input.strip().lower():
                      is_preferred = True
            logger.info(f"_get_and_show_weather: For city_input='{city_input}', preferred_city_from_db='{preferred_city_from_db}', api_city_name='{api_city_name}', is_preferred={is_preferred}")
    else:
        logger.error(f"No city_input or coords provided for user {user_id} in _get_and_show_weather.")
        await status_message.edit_text("Помилка: Не вказано місто або координати.")
        await state.clear()
        return

    final_target_message = status_message if status_message else message_to_edit_or_answer

    if weather_data and str(weather_data.get("cod")) == "200":
        actual_city_name_from_api = weather_data.get("name") # Имя города, которое вернуло API
        logger.info(f"_get_and_show_weather: actual_city_name_from_api='{actual_city_name_from_api}' for request_details='{request_details}'")

        # Определение имени для отображения пользователю
        city_display_name_for_user_message: str
        if coords and actual_city_name_from_api:
            city_display_name_for_user_message = f"Прогноз за вашими координатами, м. {actual_city_name_from_api}"
        elif coords: # API не вернуло имя для координат
            city_display_name_for_user_message = "за вашими координатами"
        elif actual_city_name_from_api: # Ввод города, API вернуло имя
             city_display_name_for_user_message = actual_city_name_from_api.capitalize()
        elif city_input: # Ввод города, API НЕ вернуло имя, используем ввод пользователя
            city_display_name_for_user_message = city_input.capitalize()
        else:
            city_display_name_for_user_message = "Невідоме місце"
        
        logger.info(f"_get_and_show_weather: city_display_name_for_user_message='{city_display_name_for_user_message}'")

        weather_message_text = format_weather_message(weather_data, city_display_name_for_user_message)
        
        # Город для кнопки "Обновить" - это то, что можно снова передать в API.
        # Если есть имя от API, используем его. Иначе - то, что ввел пользователь.
        current_shown_city_for_refresh_fsm = actual_city_name_from_api if actual_city_name_from_api else city_input if city_input else None
        logger.info(f"_get_and_show_weather: current_shown_city_for_refresh_fsm='{current_shown_city_for_refresh_fsm}'")

        state_data_to_update = {
            "city_to_save": city_to_save_in_db, # Имя от API для сохранения (если это не координаты)
            "city_display_name": city_display_name_for_user_message, # Что показываем юзеру
            "current_shown_city": current_shown_city_for_refresh_fsm, # Что использовать для "Обновить"
            "current_coords": coords,
            "preferred_city_from_db": preferred_city_from_db
        }
        logger.debug(f"User {user_id}: PREPARING to update FSM state in _get_and_show_weather with: {state_data_to_update}")
        await state.update_data(**state_data_to_update)
        
        current_fsm_data_after_update = await state.get_data()
        logger.debug(f"User {user_id}: FSM data AFTER update in _get_and_show_weather: {current_fsm_data_after_update}")

        # Предлагаем сохранить только если это был ввод города, город не является предпочтительным, и API вернуло имя для сохранения
        ask_to_save = city_input is not None and not is_preferred and city_to_save_in_db is not None
        
        text_to_send = weather_message_text
        reply_markup = None

        if ask_to_save:
            text_to_send += f"\n\n💾 Зберегти <b>{city_display_name_for_user_message}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await state.set_state(WeatherStates.waiting_for_save_decision)
            logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_save_decision. Asking to save '{city_display_name_for_user_message}'.")
        else:
            reply_markup = get_weather_actions_keyboard()
            # Если не спрашиваем о сохранении, и текущее состояние было waiting_for_city (т.е. пользователь ввел город, который уже предпочтительный)
            # то сбрасываем состояние waiting_for_city.
            current_fsm_state_name = await state.get_state()
            if current_fsm_state_name == WeatherStates.waiting_for_city.state:
                logger.info(f"User {user_id}: City '{city_input}' is already preferred or not saveable. Clearing FSM state from waiting_for_city.")
                await state.set_state(None)


        try:
            await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit final weather message: {e}")
            try:
                await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Failed to send new final weather message either: {e2}")

    elif weather_data and (str(weather_data.get("cod")) == "404"):
        city_error_name = city_input if city_input else "вказана локація"
        error_text = f"😔 На жаль, місто/локація '<b>{city_error_name}</b>' не знайдено."
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit 404 error message: {e}")
            try:
                await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Failed to send new 404 error message either: {e2}")
        logger.warning(f"Location '{request_details}' not found for user {user_id} (404). Clearing FSM state.")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details} (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit other error message: {e}")
            try:
                await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup) # Исправлено: error_text
            except Exception as e2:
                logger.error(f"Failed to send new other error message either: {e2}")
        logger.error(f"Failed to get weather for {request_details} for user {user_id}. API Response: {weather_data}. Clearing FSM state.")
        await state.clear()


async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    # Очищаем состояние FSM модуля погоды *только если это новый вход*, а не коллбэк внутри модуля
    if isinstance(target, Message) or \
       (isinstance(target, CallbackQuery) and not target.data.startswith(CALLBACK_WEATHER_REFRESH.split(':')[0])): # Проверяем, что это не коллбэк этого же модуля
        current_fsm_state_name = await state.get_state()
        if current_fsm_state_name is not None and current_fsm_state_name.startswith("WeatherStates"):
             logger.info(f"User {user_id}: Clearing previous weather FSM state ({current_fsm_state_name}) at weather_entry_point.")
             await state.clear()
        elif current_fsm_state_name is None and isinstance(target, Message): # Если это сообщение и состояние уже None, можно очистить данные на всякий случай
             await state.clear() # Очистит данные, если состояние None
             logger.info(f"User {user_id}: State was None, cleared data at weather_entry_point on Message.")


    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)
    if isinstance(target, CallbackQuery):
        await target.answer()

    preferred_city = db_user.preferred_city if db_user else None
    logger.info(f"weather_entry_point: User {user_id}, preferred_city from DB: '{preferred_city}'")

    if preferred_city:
        await _get_and_show_weather(bot, target, state, session, city_input=preferred_city)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (new user or DB error)") + " has no preferred city."
        logger.info(log_msg)
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
                try:
                    await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2:
                    logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city.")


@router.message(F.location)
async def handle_location(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"User {user_id}: Received location: lat={lat}, lon={lon}")
        current_fsm_state_name = await state.get_state()
        if current_fsm_state_name is not None:
            logger.info(f"User {user_id}: Clearing FSM state ({current_fsm_state_name}) before showing weather by location.")
            await state.clear()
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_city_input = message.text.strip() if message.text else ""
    logger.info(f"handle_city_input: User {message.from_user.id} entered city '{user_city_input}'. Current FSM state: {await state.get_state()}")
    
    if not user_city_input:
        await message.answer("😔 Будь ласка, введіть назву міста (текст не може бути порожнім).", reply_markup=get_weather_enter_city_back_keyboard())
        return
    if len(user_city_input) > 100:
        await message.answer("😔 Назва міста занадто довга (максимум 100 символів). Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        return
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄє\s\-\.\']+$", user_city_input):
        await message.answer("😔 Назва міста може містити лише літери, пробіли, дефіси, апострофи та крапки. Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        return
    
    # При вводе нового города, данные состояния (кроме самого состояния waiting_for_city)
    # будут перезаписаны в _get_and_show_weather.
    # await state.update_data(current_shown_city=None, current_coords=None) # Можно так предварительно почистить ключи
    await _get_and_show_weather(bot, message, state, session, city_input=user_city_input)


@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested OTHER city. Current FSM state before setting waiting_for_city: {await state.get_state()}, data: {await state.get_data()}")
    await callback.message.edit_text("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    await state.set_state(WeatherStates.waiting_for_city)
    logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city (from Other City callback).")
    await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    current_fsm_state_name_on_refresh = await state.get_state()
    logger.info(f"User {user_id} requested REFRESH. Current FSM state: {current_fsm_state_name_on_refresh}, FSM data: {user_data}")
    
    coords = user_data.get("current_coords")
    city_name_to_refresh = user_data.get("current_shown_city") 

    if coords:
        logger.info(f"User {user_id} refreshing weather by coords: {coords}")
        await _get_and_show_weather(bot, callback, state, session, coords=coords)
    elif city_name_to_refresh:
        logger.info(f"User {user_id} refreshing weather for city: '{city_name_to_refresh}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_name_to_refresh)
    else:
        logger.warning(f"User {user_id} requested REFRESH, but no city_name_to_refresh or coords found in FSM state. Attempting to use preferred city from DB.")
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: No specific city in state for refresh, using preferred city '{preferred_city_from_db}' from DB.")
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city in DB for refresh. Asking to input city.")
            await callback.message.edit_text("😔 Не вдалося визначити місто для оновлення. Будь ласка, введіть місто:", reply_markup=get_weather_enter_city_back_keyboard())
            await state.set_state(WeatherStates.waiting_for_city)
            await callback.answer("Не вдалося оновити", show_alert=True)


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city. FSM state: {await state.get_state()}, FSM data BEFORE save: {user_data}")

    city_to_actually_save_in_db = user_data.get("city_to_save") # Это имя от API, например "Novomoskovsk"
    city_name_user_saw_in_prompt = user_data.get("city_display_name", city_to_actually_save_in_db) # Например "Novomoskovsk" или "Прогноз за вашими..."

    if not city_to_actually_save_in_db:
        logger.error(f"User {user_id}: 'city_to_save' is missing in FSM data. Cannot save. Data: {user_data}")
        await callback.message.edit_text("Помилка: не вдалося визначити місто для збереження.", reply_markup=get_weather_actions_keyboard())
        await state.set_state(None) 
        await callback.answer("Помилка збереження", show_alert=True)
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
            # Обновляем 'preferred_city_from_db' в состоянии FSM, чтобы оно было актуальным
            # 'current_shown_city' уже должен быть городом, который только что показывали (например, "Novomoskovsk")
            await state.update_data(preferred_city_from_db=city_to_actually_save_in_db)
            logger.debug(f"User {user_id}: Updated 'preferred_city_from_db' in FSM state to '{city_to_actually_save_in_db}' after saving.")
            
            fsm_data_after_save_logic = await state.get_data()
            logger.debug(f"User {user_id}: FSM data AFTER save logic and state update, BEFORE clearing state enum: {fsm_data_after_save_logic}")

            await callback.message.edit_text(text_after_save, reply_markup=get_weather_actions_keyboard())
        except Exception as e:
            logger.exception(f"User {user_id}: DB error while saving preferred city '{city_to_actually_save_in_db}': {e}", exc_info=True)
            await session.rollback()
            await callback.message.edit_text("😥 Виникла помилка під час збереження міста.", reply_markup=get_weather_actions_keyboard())
    else:
        logger.error(f"User {user_id} not found in DB during save city.")
        await callback.message.edit_text("Помилка: не вдалося знайти ваші дані.", reply_markup=get_weather_actions_keyboard())
    
    await state.set_state(None) 
    logger.info(f"User {user_id}: Cleared FSM state enum (was WeatherStates.waiting_for_save_decision) after saving city. Data should persist for user.")
    await callback.answer("Місто збережено!")


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city. FSM state: {await state.get_state()}, FSM data: {user_data}")

    city_display_name_from_prompt = user_data.get("city_display_name", "поточне місто")
    
    original_weather_message_parts = callback.message.text.split('\n\n💾 Зберегти', 1)
    weather_part = original_weather_message_parts[0] if original_weather_message_parts else "Дані про погоду"

    text_after_no_save = f"{weather_part}\n\n(Місто <b>{city_display_name_from_prompt}</b> не було збережено як основне)"
    
    await callback.message.edit_text(text_after_no_save, reply_markup=get_weather_actions_keyboard())
    await state.set_state(None)
    logger.info(f"User {user_id}: Cleared FSM state enum (was WeatherStates.waiting_for_save_decision) after NOT saving city. Data should persist.")
    await callback.answer("Місто не збережено.")


@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} requested 5-day FORECAST. Current FSM state: {await state.get_state()}, FSM data: {user_data}")

    city_name_for_api_request = user_data.get("current_shown_city") # Город, который был показан (имя для API)
    city_display_name_for_user = user_data.get("city_display_name", city_name_for_api_request) # Что видел юзер

    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested forecast, but 'current_shown_city' not found in FSM state. Data: {user_data}")
        await callback.answer("Спочатку отримайте погоду для міста.", show_alert=True)
        return

    await callback.answer("Отримую прогноз на 5 днів...")
    status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{city_display_name_for_user}</b>...")
    
    forecast_api_data = await get_5day_forecast(bot, city_name_for_api_request)
    
    if forecast_api_data and str(forecast_api_data.get("cod")) == "200":
        message_text = format_forecast_message(forecast_api_data, city_display_name_for_user)
        reply_markup = get_forecast_keyboard()
        await status_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent 5-day forecast for API city '{city_name_for_api_request}' (display to user: '{city_display_name_for_user}').")
    else:
        error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'
        error_api_message = forecast_api_data.get('message', 'Невідома помилка API') if forecast_api_data else 'Не вдалося з\'єднатися з API'
        error_text = f"😥 Не вдалося отримати прогноз для <b>{city_display_name_for_user}</b>.\n<i>Помилка: {error_api_message} (Код: {error_code})</i>"
        await status_message.edit_text(error_text, reply_markup=get_weather_actions_keyboard())
        logger.error(f"User {user_id}: Failed to get 5-day forecast for API city '{city_name_for_api_request}'. API Response: {forecast_api_data}")


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} requested to show CURRENT weather again (from forecast view). FSM data: {user_data}")

    city_to_show_current = user_data.get("current_shown_city") # Имя для API
    coords_to_show_current = user_data.get("current_coords")

    if coords_to_show_current:
        logger.info(f"User {user_id}: Showing current weather by COORDS again: {coords_to_show_current}")
        await _get_and_show_weather(bot, callback, state, session, coords=coords_to_show_current)
    elif city_to_show_current:
        logger.info(f"User {user_id}: Showing current weather for CITY again: '{city_to_show_current}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_to_show_current)
    else:
        logger.warning(f"User {user_id}: Requested show current weather, but no city or coords in FSM state. Trying preferred city from DB.")
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: Showing weather for preferred city '{preferred_city_from_db}' as fallback.")
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city. Redirecting to city input.")
            await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:", reply_markup=get_weather_enter_city_back_keyboard())
            await state.set_state(WeatherStates.waiting_for_city)
            await callback.answer("Вкажіть місто", show_alert=True)

@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_fsm_state = await state.get_state()
    logger.info(f"User {user_id} requested back to main menu from weather module. Current FSM state: {current_fsm_state}. Clearing weather FSM state.")
    await state.clear()
    await show_main_menu_message(callback)
    await callback.answer()