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
from src.handlers.utils import show_main_menu_message # Импортируем для возврата в главное меню

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
    is_preferred = False # Сбрасываем флаг для каждого нового запроса
    request_details = ""

    try:
        action_text = "🔍 Отримую дані про погоду..."
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
            await target.answer() # Отвечаем на коллбэк как можно раньше
        elif hasattr(target, 'location') and target.location : # Проверка на наличие атрибута location
            status_message = await target.answer(action_text)
        else:
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.error(f"Error sending/editing status message for weather: {e}")
        status_message = message_to_edit_or_answer # Fallback

    weather_data = None
    preferred_city_from_db = None # Город из БД
    city_to_save_in_db = None # Город, который будет записан в БД (имя из API)

    if coords:
        request_details = f"coords ({coords['lat']:.4f}, {coords['lon']:.4f})"
        logger.info(f"User {user_id} requesting weather by {request_details}")
        weather_data = await get_weather_data_by_coords(bot, coords['lat'], coords['lon'])
        # Для координат не предлагаем сохранение и is_preferred всегда False
        is_preferred = False
        # Получим preferred_city из БД для информации в state, но не для логики is_preferred здесь
        db_user_for_coords = await session.get(User, user_id)
        if db_user_for_coords:
            preferred_city_from_db = db_user_for_coords.preferred_city

    elif city_input:
        request_details = f"city '{city_input}'"
        logger.info(f"User {user_id} requesting weather by {request_details}")
        weather_data = await get_weather_data(bot, city_input)
        
        db_user = await session.get(User, user_id)
        if db_user:
            preferred_city_from_db = db_user.preferred_city

        if weather_data and str(weather_data.get("cod")) == "200": # Успешный ответ API
            api_city_name = weather_data.get("name") # Имя города от API
            city_to_save_in_db = api_city_name # Это имя будем сохранять

            if preferred_city_from_db and api_city_name:
                if preferred_city_from_db.lower() == api_city_name.lower():
                    is_preferred = True
            # Дополнительная проверка на случай, если пользователь ввел город так же, как он сохранен, но API вернуло немного другое написание
            if preferred_city_from_db and not is_preferred:
                 if preferred_city_from_db.lower() == city_input.strip().lower():
                      is_preferred = True
    else:
        logger.error(f"No city_input or coords provided for user {user_id} in _get_and_show_weather.")
        await status_message.edit_text("Помилка: Не вказано місто або координати.")
        await state.clear() # Очищаем состояние, так как нечего обрабатывать
        return

    final_target_message = status_message if status_message else message_to_edit_or_answer

    if weather_data and str(weather_data.get("cod")) == "200":
        actual_city_name_from_api = weather_data.get("name")
        
        city_display_name_for_message: str # Имя для отображения в сообщении
        if coords and actual_city_name_from_api:
            city_display_name_for_message = f"Прогноз за вашими координатами, м. {actual_city_name_from_api}"
        elif coords:
            city_display_name_for_message = "за вашими координатами"
        elif actual_city_name_from_api: # Если был ввод города и API вернуло имя
             city_display_name_for_message = actual_city_name_from_api.capitalize()
        elif city_input: # Если API не вернуло имя, но был ввод
            city_display_name_for_message = city_input.capitalize()
        else: # Не должно случиться, если есть city_input или coords
            city_display_name_for_message = "Невідоме місце"

        weather_message_text = format_weather_message(weather_data, city_display_name_for_message)
        logger.info(f"Formatted weather for {request_details} (display: '{city_display_name_for_message}') for user {user_id}")

        # current_shown_city должен быть тем городом, который мы фактически показываем и который можно обновить
        # Это должно быть имя, которое можно снова передать в API (т.е. имя от API или пользовательский ввод, если API не вернуло имя)
        current_shown_city_for_refresh_state = actual_city_name_from_api if actual_city_name_from_api else city_input if city_input else None

        # Данные для сохранения в состоянии FSM
        state_data_to_update = {
            "city_to_save": city_to_save_in_db, # Имя от API для сохранения в БД (если не по координатам)
            "city_display_name": city_display_name_for_message, # Имя для отображения пользователю
            "current_shown_city": current_shown_city_for_refresh_state, # Город для кнопки "Обновить"
            "current_coords": coords, # Текущие координаты, если были
            "preferred_city_from_db": preferred_city_from_db # Предпочитаемый город из БД (для информации)
        }
        logger.debug(f"Updating FSM state with data: {state_data_to_update}")
        await state.update_data(**state_data_to_update)
        
        # Логируем текущее полное состояние после обновления
        current_fsm_data = await state.get_data()
        logger.debug(f"Full FSM data after update in _get_and_show_weather: {current_fsm_data}")

        ask_to_save = city_input is not None and not is_preferred and city_to_save_in_db is not None
        reply_markup = None
        text_to_send = weather_message_text

        if ask_to_save:
            # Используем city_display_name_for_message для вопроса, т.к. оно отформатировано для пользователя
            text_to_send += f"\n\n💾 Зберегти <b>{city_display_name_for_message}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await state.set_state(WeatherStates.waiting_for_save_decision)
            logger.info(f"Set FSM state to WeatherStates.waiting_for_save_decision for user {user_id}")
        else:
            reply_markup = get_weather_actions_keyboard()
            # Если не спрашиваем о сохранении, значит, либо это уже предпочтительный город,
            # либо это геолокация, либо была ошибка. В любом случае, можно сбросить состояние FSM, если оно было.
            # Но если это предпочтительный город, то состояние и так не было установлено (кроме waiting_for_city)
            # Если это геолокация, состояние было очищено перед вызовом _get_and_show_weather
            # Если это просто обновление, состояние также не должно быть установлено специфично.
            # Поэтому очистка состояния здесь может быть излишней или даже вредной.
            # Оставим очистку состояния в обработчиках колбэков "Да/Нет" при сохранении.
            pass


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
        await state.clear() # Очищаем состояние при ошибке 404
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details} (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard() # Даем возможность вернуться
        try:
            await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit other error message: {e}")
            try:
                # Важно: здесь была опечатка text_to_send вместо error_text
                await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
            except Exception as e2:
                logger.error(f"Failed to send new other error message either: {e2}")
        logger.error(f"Failed to get weather for {request_details} for user {user_id}. API Response: {weather_data}. Clearing FSM state.")
        await state.clear() # Очищаем состояние при других ошибках API


async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    
    # Очищаем предыдущее состояние FSM модуля погоды, чтобы избежать путаницы
    # Особенно если пользователь переключается между модулями
    if await state.get_state() is not None: # Проверяем, есть ли вообще состояние
        logger.info(f"User {user_id}: Clearing previous weather FSM state before weather_entry_point.")
        await state.clear() # Используем clear для сброса и состояния, и данных этого состояния

    db_user = await session.get(User, user_id)
    if isinstance(target, CallbackQuery):
        await target.answer() # Отвечаем на коллбэк

    preferred_city = db_user.preferred_city if db_user else None

    if preferred_city:
        logger.info(f"User {user_id} has preferred city: {preferred_city}. Showing weather for it.")
        # Сохраняем prefered_city в состояние для информации, но _get_and_show_weather сам его прочитает из БД
        # await state.update_data(preferred_city_from_db=preferred_city) # Это делается внутри _get_and_show_weather
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
            # Попытка отправить новое сообщение, если редактирование не удалось
            if isinstance(target, CallbackQuery):
                try:
                    await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2:
                    logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"Set FSM state to WeatherStates.waiting_for_city for user {user_id}")


@router.message(F.location)
async def handle_location(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"Received location from user {user_id}: lat={lat}, lon={lon}")
        # Очищаем состояние перед показом погоды по геолокации,
        # так как это новый, независимый запрос.
        await state.clear() # Сбрасываем предыдущее состояние и его данные
        logger.info(f"User {user_id}: Cleared FSM state before showing weather by location.")
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_city_input = message.text.strip() if message.text else ""
    
    if not user_city_input:
        await message.answer("😔 Будь ласка, введіть назву міста (текст не може бути порожнім).", reply_markup=get_weather_enter_city_back_keyboard())
        return
    if len(user_city_input) > 100:
        await message.answer("😔 Назва міста занадто довга (максимум 100 символів). Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        return
    # Немного смягчим валидацию, разрешив апострофы и точки (например, St. Louis)
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄє\s\-\.\']+$", user_city_input):
        await message.answer("😔 Назва міста може містити лише літери, пробіли, дефіси, апострофи та крапки. Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        return
    
    # Данные состояния от предыдущего шага (например, если пользователь нажал "Інше місто")
    # могут быть не нужны здесь, так как мы начинаем новый поиск.
    # _get_and_show_weather сам обновит состояние нужными данными.
    # await state.clear() # Можно раскомментировать, если хотим полностью чистый старт для каждого ввода города.
    # Но _get_and_show_weather и так перезапишет нужные ключи.

    await _get_and_show_weather(bot, message, state, session, city_input=user_city_input)


@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested OTHER city.")
    # Сохраняем текущие данные FSM, если они могут понадобиться (например, для кнопки "Назад")
    # но для ввода другого города они обычно не нужны.
    # Просто устанавливаем состояние ожидания города.
    await callback.message.edit_text("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    await state.set_state(WeatherStates.waiting_for_city)
    logger.info(f"Set FSM state to WeatherStates.waiting_for_city for user {user_id} (Other City)")
    await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.debug(f"User {user_id} requested REFRESH. Current FSM data: {user_data}")
    
    coords = user_data.get("current_coords")
    # Используем 'current_shown_city' для обновления, так как это город, который был показан пользователю.
    city_name_to_refresh = user_data.get("current_shown_city") 

    if coords: # Если есть координаты, обновляем по ним
        logger.info(f"User {user_id} refreshing weather by coords: {coords}")
        # При обновлении по координатам, состояние FSM (кроме самих координат) не так критично,
        # _get_and_show_weather его обновит.
        await _get_and_show_weather(bot, callback, state, session, coords=coords)
    elif city_name_to_refresh: # Если есть имя города, обновляем по нему
        logger.info(f"User {user_id} refreshing weather for city: '{city_name_to_refresh}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_name_to_refresh)
    else:
        logger.warning(f"User {user_id} requested REFRESH, but no city_name_to_refresh or coords found in FSM state. Attempting to use preferred city.")
        # Попытка получить предпочитаемый город из БД как fallback
        db_user = await session.get(User, user_id)
        preferred_city_from_db = db_user.preferred_city if db_user else None
        if preferred_city_from_db:
            logger.info(f"User {user_id}: No specific city in state for refresh, using preferred city '{preferred_city_from_db}' from DB.")
            await _get_and_show_weather(bot, callback, state, session, city_input=preferred_city_from_db)
        else:
            logger.warning(f"User {user_id}: No city in state and no preferred city in DB for refresh. Asking to input city.")
            await callback.message.edit_text("😔 Не вдалося визначити місто для оновлення. Будь ласка, введіть місто:")
            await state.set_state(WeatherStates.waiting_for_city)
            await callback.answer("Не вдалося оновити", show_alert=True)


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.debug(f"User {user_id} chose YES to save city. FSM data before save: {user_data}")

    # 'city_to_save' должно содержать имя города от API, которое подходит для сохранения.
    city_to_save_in_db = user_data.get("city_to_save")
    # 'city_display_name' - это то, что видел пользователь, может включать "Прогноз за вашими координатами..."
    # Для сообщения об успехе лучше использовать отформатированное имя, если 'city_to_save' существует.
    city_name_for_confirmation_message = user_data.get("city_display_name", city_to_save_in_db)


    if not city_to_save_in_db: # Проверяем, что есть что сохранять
        logger.error(f"User {user_id}: 'city_to_save' is missing in FSM data. Cannot save. Data: {user_data}")
        await callback.message.edit_text("Помилка: не вдалося визначити місто для збереження. Спробуйте ще раз.", reply_markup=get_weather_actions_keyboard())
        await state.set_state(None) # Сбрасываем состояние
        await callback.answer("Помилка збереження", show_alert=True)
        return

    db_user = await session.get(User, user_id)
    if db_user:
        try:
            db_user.preferred_city = city_to_save_in_db
            session.add(db_user)
            # Коммит произойдет через middleware
            logger.info(f"User {user_id}: Preferred city '{city_to_save_in_db}' set for DB commit. Display name for confirm: '{city_name_for_confirmation_message}'")
            
            text_after_save = f"✅ Місто <b>{city_name_for_confirmation_message}</b> збережено як основне."
            # Важно: После сохранения, preferred_city в FSM тоже должно обновиться,
            # чтобы следующее "Обновить" или "Погода" сразу использовало новый город.
            # _get_and_show_weather при следующем вызове сам прочитает из БД,
            # но для консистентности можно обновить и в текущем FSM.
            # Однако, `current_shown_city` должно оставаться тем, что только что показали.
            # `city_to_save` уже есть в стейте, `current_shown_city` тоже.
            # `preferred_city_from_db` можно обновить.
            await state.update_data(preferred_city_from_db=city_to_save_in_db)
            logger.debug(f"User {user_id}: Updated 'preferred_city_from_db' in FSM state to '{city_to_save_in_db}' after saving.")

            await callback.message.edit_text(text_after_save, reply_markup=get_weather_actions_keyboard())
        except Exception as e:
            logger.exception(f"User {user_id}: DB error while saving preferred city '{city_to_save_in_db}': {e}", exc_info=True)
            await session.rollback() # Явный откат, если middleware не успеет
            await callback.message.edit_text("😥 Виникла помилка під час збереження міста. Спробуйте пізніше.", reply_markup=get_weather_actions_keyboard())
    else:
        logger.error(f"User {user_id} not found in DB during save city. This shouldn't happen if /start worked.")
        await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження.", reply_markup=get_weather_actions_keyboard())
    
    await state.set_state(None) # ИСПРАВЛЕНИЕ: Сбрасываем состояние после обработки решения
    logger.info(f"User {user_id}: Cleared FSM state (was WeatherStates.waiting_for_save_decision) after saving city.")
    await callback.answer("Місто збережено!")


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city. FSM data: {user_data}")

    # city_display_name - это то, что было в вопросе о сохранении.
    city_display_name = user_data.get("city_display_name", "поточне місто")
    
    # Текст погоды был в предыдущем сообщении. Мы его не сохраняли целиком в FSM.
    # Поэтому просто сообщим, что город не сохранен, и покажем кнопки действий.
    # Можно было бы переформатировать сообщение о погоде, но это усложнит.
    # Вместо этого, извлекаем первую часть сообщения (саму погоду)
    original_weather_message_parts = callback.message.text.split('\n\n💾 Зберегти', 1)
    weather_part = original_weather_message_parts[0] if original_weather_message_parts else "Дані про погоду"

    text_after_no_save = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не було збережено як основне)"
    
    await callback.message.edit_text(text_after_no_save, reply_markup=get_weather_actions_keyboard())
    await state.set_state(None) # ИСПРАВЛЕНИЕ: Сбрасываем состояние после обработки решения
    logger.info(f"User {user_id}: Cleared FSM state (was WeatherStates.waiting_for_save_decision) after NOT saving city.")
    await callback.answer("Місто не збережено.")


@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): # Добавили session, если понадобится
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.debug(f"User {user_id} requested 5-day FORECAST. Current FSM data: {user_data}")

    # Для прогноза используем 'current_shown_city', так как это город, который сейчас отображается.
    city_name_for_request = user_data.get("current_shown_city")
    # Отображаемое имя для сообщения (может включать "Прогноз за вашими координатами...")
    city_display_name_for_forecast_message = user_data.get("city_display_name", city_name_for_request)


    if not city_name_for_request:
        logger.warning(f"User {user_id} requested forecast, but 'current_shown_city' not found in FSM state. Data: {user_data}")
        await callback.answer("Не вдалося визначити місто для прогнозу. Спробуйте показати погоду спочатку.", show_alert=True)
        return

    await callback.answer("Отримую прогноз на 5 днів...") # Ответ на коллбэк
    status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{city_display_name_for_forecast_message}</b>...")
    
    forecast_api_data = await get_5day_forecast(bot, city_name_for_request)
    
    if forecast_api_data and str(forecast_api_data.get("cod")) == "200":
        message_text = format_forecast_message(forecast_api_data, city_display_name_for_forecast_message)
        reply_markup = get_forecast_keyboard() # Клавиатура "Назад к текущей погоде"
        await status_message.edit_text(message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent 5-day forecast for '{city_name_for_request}' (display: '{city_display_name_for_forecast_message}').")
    else:
        error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'
        error_api_message = forecast_api_data.get('message', 'Невідома помилка API') if forecast_api_data else 'Не вдалося з\'єднатися з API'
        error_text = f"😥 Не вдалося отримати прогноз для <b>{city_display_name_for_forecast_message}</b>.\n<i>Помилка: {error_api_message} (Код: {error_code})</i>"
        # При ошибке прогноза, можно вернуть клавиатуру с кнопкой "Назад к текущей погоде", если есть текущая погода.
        # Или просто сообщение об ошибке без клавиатуры / с кнопкой "В меню".
        # Пока оставим так, клавиатура для прогноза здесь не нужна.
        await status_message.edit_text(error_text, reply_markup=get_weather_actions_keyboard()) # Возвращаем к обычным действиям
        logger.error(f"User {user_id}: Failed to get 5-day forecast for '{city_name_for_request}'. API Response: {forecast_api_data}")
        # Состояние FSM не меняем, чтобы пользователь мог вернуться к текущей погоде или обновить ее.


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_data = await state.get_data()
    logger.debug(f"User {user_id} requested to show CURRENT weather again. FSM data: {user_data}")

    # Город для показа текущей погоды - это 'current_shown_city'
    city_to_show_current = user_data.get("current_shown_city")
    coords_to_show_current = user_data.get("current_coords")

    if coords_to_show_current:
        logger.info(f"User {user_id}: Showing current weather by COORDS again: {coords_to_show_current}")
        await _get_and_show_weather(bot, callback, state, session, coords=coords_to_show_current)
    elif city_to_show_current:
        logger.info(f"User {user_id}: Showing current weather for CITY again: '{city_to_show_current}'")
        await _get_and_show_weather(bot, callback, state, session, city_input=city_to_show_current)
    else:
        logger.warning(f"User {user_id}: Requested show current weather, but no city or coords in FSM state. Trying preferred city.")
        # Если в состоянии ничего нет, пробуем показать погоду для предпочитаемого города (если есть)
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
    logger.info(f"User {user_id} requested back to main menu from weather module. Clearing weather FSM state.")
    await state.clear() # Очищаем состояние модуля погоды перед выходом
    await show_main_menu_message(callback) # Используем импортированную функцию
    await callback.answer()