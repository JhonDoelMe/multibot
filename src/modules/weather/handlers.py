# src/modules/weather/handlers.py

import logging
import re
# ... (другие импорты остаются) ...
from aiogram import Bot, Router, F, MagicFilter # Добавляем MagicFilter
from aiogram.filters import StateFilter # Для фильтрации по None состоянию
# ...

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()

# ... (_get_and_show_weather, weather_entry_point, handle_city_input без изменений в этой части) ...
# Но в weather_entry_point, когда нет preferred_city, устанавливается WeatherStates.waiting_for_city

# ИЗМЕНЕНИЕ: Возвращаем декоратор, но с фильтром по состоянию FSM
# Этот обработчик сработает, если мы в состоянии WeatherStates.waiting_for_city И пришла локация
@router.message(WeatherStates.waiting_for_city, F.location)
async def handle_location_when_waiting(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Обрабатывает геолокацию, когда бот ее ожидает для основного сервиса."""
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: handle_location_when_waiting for user {user_id}: lat={lat}, lon={lon}")
        # Состояние уже waiting_for_city, после получения погоды оно сбросится или изменится
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else: # На всякий случай, хотя фильтр F.location должен это покрывать
        logger.warning(f"User {message.from_user.id}: handle_location_when_waiting (main weather) called without message.location.")
        await message.reply("Не вдалося отримати вашу геолокацію.")


# Эта функция теперь будет вызываться только по кнопке "📍 Погода по геолокації (осн.)"
# Она не должна быть message handler-ом сама по себе, если мы хотим избежать конфликтов.
# common.py будет ее вызывать.
async def process_main_geolocation_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    """Обрабатывает геолокацию, присланную по кнопке 'Погода по геолокації (осн.)'."""
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: process_main_geolocation_button for user {user_id}: lat={lat}, lon={lon}")
        
        current_fsm_state_name = await state.get_state()
        if current_fsm_state_name is not None: # Очищаем любое предыдущее состояние, т.к. это прямой запрос
            logger.info(f"User {user_id}: Clearing FSM state ({current_fsm_state_name}) before main weather by location button.")
            await state.clear()
        
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: process_main_geolocation_button called without message.location.")
        # Ответ пользователю будет дан из common.py, если reply_to_message не сработает
# ... (остальные обработчики этого модуля: _get_and_show_weather, weather_entry_point, handle_city_input, и колбэки)
# В weather_entry_point, если нет preferred_city, он уже устанавливает WeatherStates.waiting_for_city.

# ... (код _get_and_show_weather, weather_entry_point, handle_city_input, и колбэков без изменений относительно предыдущей версии)
# ... (они уже были предоставлены и должны быть здесь)
# Убедитесь, что `_get_and_show_weather` корректно сбрасывает или изменяет состояние после показа погоды,
# особенно если оно было `WeatherStates.waiting_for_city`.
# Например, в `_get_and_show_weather`, если погода успешно показана (не ошибка API):
#   ...
#   else: # Если не ask_to_save (т.е. город предпочтительный или это геолокация)
#       reply_markup = get_weather_actions_keyboard()
#       current_fsm_state_name = await state.get_state()
#       if current_fsm_state_name == WeatherStates.waiting_for_city.state:
#           logger.info(f"User {user_id}: Weather shown successfully. Clearing FSM state from waiting_for_city.")
#           await state.set_state(None) # Сбрасываем состояние ожидания
#   ...
# Это уже было в одной из предыдущих версий _get_and_show_weather.

# Код _get_and_show_weather (убедитесь, что эта часть есть и актуальна):
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
        await status_message.edit_text("Помилка: Не вказано місто або координати.")
        await state.clear()
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
            # Если мы были в состоянии ожидания города (т.е. пользователь ввел город) и не спрашиваем о сохранении
            # (значит, город уже предпочтительный или это геолокация), то сбрасываем состояние ожидания.
            if current_fsm_state_name == WeatherStates.waiting_for_city.state:
                logger.info(f"User {user_id}: Weather shown (city '{city_input}' is preferred or from geo). Clearing FSM state from waiting_for_city.")
                await state.set_state(None)
            # Если это был прямой вызов по геолокации (coords is not None), состояние и так должно было быть очищено перед вызовом _get_and_show_weather
            # или установлено в None, если это первая команда /start
        try:
            await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit final weather message: {e}")
            try: await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new final weather message either: {e2}")
    elif weather_data and (str(weather_data.get("cod")) == "404"):
        # ... (код обработки 404 без изменений) ...
        city_error_name = city_input if city_input else "вказана локація"
        error_text = f"😔 На жаль, місто/локація '<b>{city_error_name}</b>' не знайдено."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit 404 error message: {e}")
            try: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new 404 error message either: {e2}")
        logger.warning(f"Location '{request_details}' not found for user {user_id} (404). Clearing FSM state.")
        await state.clear()
    else:
        # ... (код обработки других ошибок без изменений) ...
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details} (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit other error message: {e}")
            try: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new other error message either: {e2}")
        logger.error(f"Failed to get weather for {request_details} for user {user_id}. API Response: {weather_data}. Clearing FSM state.")
        await state.clear()

# Остальные хендлеры (weather_entry_point, handle_city_input, колбэки) остаются как в предыдущей версии.
# ...
async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    if isinstance(target, Message) or \
       (isinstance(target, CallbackQuery) and not target.data.startswith(CALLBACK_WEATHER_REFRESH.split(':')[0])):
        current_fsm_state_name = await state.get_state()
        if current_fsm_state_name is not None and current_fsm_state_name.startswith("WeatherStates"):
             logger.info(f"User {user_id}: Clearing previous weather FSM state ({current_fsm_state_name}) at weather_entry_point.")
             await state.clear()
        elif current_fsm_state_name is None and isinstance(target, Message):
             await state.clear()
             logger.info(f"User {user_id}: State was None, cleared data at weather_entry_point on Message.")

    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)
    if isinstance(target, CallbackQuery): await target.answer()
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
            if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
            else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message in weather_entry_point (ask for city): {e}")
            if isinstance(target, CallbackQuery):
                try: await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city.")

@router.message(WeatherStates.waiting_for_city, F.text) # Изменили F.text чтобы не конфликтовать с F.location выше
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
    logger.info(f"User {user_id} requested REFRESH (main weather). Current FSM state: {current_fsm_state_name_on_refresh}, FSM data: {user_data}")
    coords = user_data.get("current_coords")
    city_name_to_refresh = user_data.get("current_shown_city") 
    if coords:
        logger.info(f"User {user_id} refreshing main weather by coords: {coords}")
        await _get_and_show_weather(bot, callback, state, session, coords=coords)
    elif city_name_to_refresh:
        logger.info(f"User {user_id} refreshing main weather for city: '{city_name_to_refresh}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_name_to_refresh)
    else:
        logger.warning(f"User {user_id} requested REFRESH (main), but no city_name_to_refresh or coords found in FSM state. Attempting preferred city from DB.")
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: No specific city in state for main refresh, using preferred city '{preferred_city_from_db}' from DB.")
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city in DB for main refresh. Asking to input city.")
            await callback.message.edit_text("😔 Не вдалося визначити місто для оновлення. Будь ласка, введіть місто:", reply_markup=get_weather_enter_city_back_keyboard())
            await state.set_state(WeatherStates.waiting_for_city)
            await callback.answer("Не вдалося оновити", show_alert=True)

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city. FSM state: {await state.get_state()}, FSM data BEFORE save: {user_data}")
    city_to_actually_save_in_db = user_data.get("city_to_save")
    city_name_user_saw_in_prompt = user_data.get("city_display_name", city_to_actually_save_in_db)
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
            logger.info(f"User {user_id}: Preferred city changed from '{old_preferred_city}' to '{city_to_actually_save_in_db}' for DB commit. User saw prompt for '{city_name_user_saw_in_prompt}'.")
            text_after_save = f"✅ Місто <b>{city_name_user_saw_in_prompt}</b> збережено як основне."
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
    logger.info(f"User {user_id} requested 5-day FORECAST (main). Current FSM state: {await state.get_state()}, FSM data: {user_data}")
    city_name_for_api_request = user_data.get("current_shown_city")
    display_name_for_forecast_header = user_data.get("city_display_name", city_name_for_api_request)
    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested forecast (main), but 'current_shown_city' not found. Data: {user_data}")
        await callback.answer("Спочатку отримайте погоду для міста.", show_alert=True)
        return
    await callback.answer("Отримую прогноз на 5 днів...")
    status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{display_name_for_forecast_header}</b>...")
    forecast_api_data = await get_5day_forecast(bot, city_name_for_api_request)
    if forecast_api_data and str(forecast_api_data.get("cod")) == "200":
        message_text = format_forecast_message(forecast_api_data, display_name_for_forecast_header)
        reply_markup = get_forecast_keyboard()
        await status_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent 5-day forecast (main) for API city '{city_name_for_api_request}' (display: '{display_name_for_forecast_header}').")
    else:
        error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'
        error_api_message = forecast_api_data.get('message', 'Невідома помилка API') if forecast_api_data else 'Не вдалося з\'єднатися з API'
        error_text = f"😥 Не вдалося отримати прогноз для <b>{display_name_for_forecast_header}</b>.\n<i>Помилка: {error_api_message} (Код: {error_code})</i>"
        await status_message.edit_text(error_text, reply_markup=get_weather_actions_keyboard())
        logger.error(f"User {user_id}: Failed to get 5-day forecast (main) for API city '{city_name_for_api_request}'. API Response: {forecast_api_data}")

@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} requested to show CURRENT weather again (main, from forecast view). FSM data: {user_data}")
    city_to_show_current = user_data.get("current_shown_city")
    coords_to_show_current = user_data.get("current_coords")
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