# src/modules/weather/handlers.py

import logging
from typing import Union, Optional, Dict, Any
from aiogram import Bot, Router, F # <<< Добавили Bot
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
# Обновляем импорт сервисов
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

# --- ИЗМЕНЯЕМ ЭТУ ФУНКЦИЮ: Добавляем bot ---
async def _get_and_show_weather(
    bot: Bot, # <<< Добавили bot
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    city_input: Optional[str] = None,
    coords: Optional[Dict[str, float]] = None
):
    # ... (логика внутри остается прежней, НО вызовы сервисов меняются) ...
    user_id = target.from_user.id; message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target; status_message = None; is_preferred = False; request_details = ""
    try: # Отправка статуса
         if isinstance(target, CallbackQuery): status_message = await message_to_edit_or_answer.edit_text("..."); await target.answer()
         elif target.location: status_message = await target.answer("...")
         else: status_message = await target.answer("...")
    except Exception as e: logger.error(f"Error sending/editing status msg: {e}"); status_message = message_to_edit_or_answer

    weather_data = None; preferred_city = None
    if coords:
         request_details = f"coords ({coords['lat']:.4f}, {coords['lon']:.4f})"; logger.info(f"User {user_id} req weather by {request_details}")
         weather_data = await get_weather_data_by_coords(bot, coords['lat'], coords['lon']) # <<< Передаем bot
         is_preferred = False
    elif city_input:
         request_details = f"city '{city_input}'"; logger.info(f"User {user_id} req weather by {request_details}")
         weather_data = await get_weather_data(bot, city_input) # <<< Передаем bot
         db_user = await session.get(User, user_id); preferred_city = db_user.preferred_city if db_user else None
         if preferred_city and weather_data and weather_data.get("cod") == 200: # ... (определение is_preferred) ...
              api_city_name = weather_data.get("name");
              if api_city_name and preferred_city.lower() == api_city_name.lower(): is_preferred = True
              elif preferred_city.lower() == city_input.lower(): is_preferred = True
    else: logger.error(f"No city/coords provided for user {user_id}"); await status_message.edit_text("Помилка: Не вказано."); await state.clear(); return

    final_target_message = status_message if status_message else message_to_edit_or_answer
    if weather_data and (weather_data.get("cod") == 200 or str(weather_data.get("cod")) == "200"): # ... (обработка успеха) ...
        actual_city_name_from_api = weather_data.get("name"); city_display_name = city_input.capitalize() if city_input else actual_city_name_from_api if actual_city_name_from_api else "за вашими координатами"
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for {request_details} (display: '{city_display_name}') user {user_id}")
        current_shown_city_for_refresh = actual_city_name_from_api if actual_city_name_from_api else city_input if city_input else None
        await state.update_data(city_to_save=actual_city_name_from_api, city_display_name=city_display_name, current_shown_city=current_shown_city_for_refresh, current_coords=coords, preferred_city=preferred_city)
        ask_to_save = city_input is not None and not is_preferred; reply_markup = None; text_to_send = weather_message
        if ask_to_save: text_to_send += f"\n\n💾 Зберегти <b>{city_display_name}</b> ...?"; reply_markup = get_save_city_keyboard(); await state.set_state(WeatherStates.waiting_for_save_decision)
        else: reply_markup = get_weather_actions_keyboard()
        try: await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
        except Exception as e: logger.error(f"Failed edit final msg: {e}"); try: await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup)
             except Exception as e2: logger.error(f"Failed send final msg either: {e2}")
    elif weather_data and (weather_data.get("cod") == 404 or str(weather_data.get("cod")) == "404"): # ... (обработка 404) ...
          city_error_name = city_input if city_input else "вказана локація"; error_text = f"😔 На жаль, місто/локація '<b>{city_error_name}</b>' не знайдено..."; reply_markup = get_weather_enter_city_back_keyboard()
          try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
          except Exception: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
          logger.warning(f"Location '{request_details}' not found for user {user_id}"); await state.clear()
    else: # ... (обработка других ошибок) ...
         error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'; error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
         error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details}..."; reply_markup = get_weather_enter_city_back_keyboard()
         try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
         except Exception: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
         logger.error(f"Failed get weather for {request_details}... Code: {error_code}, Msg: {error_api_message}"); await state.clear()


# --- ИЗМЕНЯЕМ ВЫЗОВЫ: Добавляем bot ---
async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
    user_id = target.from_user.id; message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target; db_user = await session.get(User, user_id)
    if isinstance(target, CallbackQuery): await target.answer()
    preferred_city = db_user.preferred_city if db_user else None
    if preferred_city:
        logger.info(f"User {user_id} has preferred city: {preferred_city}.")
        await state.update_data(preferred_city=preferred_city)
        await _get_and_show_weather(bot, target, state, session, city_input=preferred_city) # <<< Передаем bot
    else: # ... (код запроса города без изменений) ...
         log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city..."
         logger.info(log_msg); text = "🌍 Будь ласка, введіть назву міста або надішліть геолокацію:"; reply_markup = get_weather_enter_city_back_keyboard()
         try:
             if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
         except Exception as e: logger.error(f"Error editing/sending message: {e}"); await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
         await state.set_state(WeatherStates.waiting_for_city)


@router.message(F.location)
async def handle_location(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
     if message.location:
         lat = message.location.latitude; lon = message.location.longitude; user_id = message.from_user.id
         logger.info(f"Received location from user {user_id}: lat={lat}, lon={lon}")
         await state.clear()
         await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon}) # <<< Передаем bot


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
     user_city_input = message.text.strip()
     await _get_and_show_weather(bot, message, state, session, city_input=user_city_input) # <<< Передаем bot


@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    logger.info(f"User {callback.from_user.id} requested OTHER city."); await callback.message.edit_text("🌍 Будь ласка, введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard()); await state.set_state(WeatherStates.waiting_for_city); await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
     user_data = await state.get_data(); coords = user_data.get("current_coords"); city_name = user_data.get("current_shown_city"); user_id = callback.from_user.id
     if coords:
         logger.info(f"User {user_id} requested REFRESH for coords: {coords}")
         await _get_and_show_weather(bot, callback, state, session, coords=coords) # <<< Передаем bot
     elif city_name:
         logger.info(f"User {user_id} requested REFRESH for city: {city_name}")
         await _get_and_show_weather(bot, callback, state, session, city_input=city_name) # <<< Передаем bot
     else: # ... (обработка ошибки) ...
          logger.warning(f"User {user_id} requested REFRESH, no location/city in state."); await callback.message.edit_text("..."); await state.set_state(WeatherStates.waiting_for_city); await callback.answer("...", show_alert=True)


# Обработчики сохранения остаются без изменений (commit убран ранее)
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений) ...
    user_data = await state.get_data(); city_to_save_in_db = user_data.get("city_to_save"); city_display_name = user_data.get("city_display_name"); user_id = callback.from_user.id
    if not city_to_save_in_db or not city_display_name: logger.error(f"... city name not found ..."); await state.clear(); from src.handlers.utils import show_main_menu_message; await show_main_menu_message(callback, "Помилка: не вдалося..."); return
    db_user = await session.get(User, user_id)
    if db_user:
         try: db_user.preferred_city = city_to_save_in_db; session.add(db_user); logger.info(f"... saved city: {city_to_save_in_db}. Middleware should commit."); text = f"✅ Місто <b>{city_display_name}</b> збережено."; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
         except Exception as e: logger.exception(f"... DB error saving city: {e}"); await session.rollback(); await callback.message.edit_text("😥 Виникла помилка...")
    else: logger.error(f"... user not found in DB."); await callback.message.edit_text("Помилка: не вдалося знайти дані...")
    await callback.answer() # Отвечаем на колбэк

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
     logger.info(f"User {callback.from_user.id} chose not to save."); user_data = await state.get_data(); city_display_name = user_data.get("city_display_name", "місто"); weather_part = callback.message.text.split('\n\n')[0]; text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
     await callback.answer()


# Обработчики прогноза остаются без изменений (вызывают сервис с bot)
@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
    user_data = await state.get_data(); city_name_for_request = user_data.get("current_shown_city"); city_display_name = user_data.get("city_display_name", city_name_for_request); user_id = callback.from_user.id
    if not city_name_for_request: logger.warning(f"User {user_id} requested forecast, but no city in state."); await callback.answer("...", show_alert=True); return
    await callback.answer("Отримую прогноз..."); status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для м. {city_display_name}...")
    forecast_api_data = await get_5day_forecast(bot, city_name_for_request) # <<< Передаем bot
    if forecast_api_data and forecast_api_data.get("cod") == "200": message_text = format_forecast_message(forecast_api_data, city_display_name); reply_markup = get_forecast_keyboard(); await status_message.edit_text(message_text, reply_markup=reply_markup); logger.info(f"Sent 5-day forecast...")
    else: error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'; error_api_message = forecast_api_data.get('message', '...') if forecast_api_data else '...'; error_text = f"😥 Не вдалося отримати прогноз... (Помилка: {error_code} - {error_api_message})."; await status_message.edit_text(error_text); logger.error(f"Failed to get forecast... Code: {error_code}, Msg: {error_api_message}"); await state.clear()


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT)
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): # <<< Добавили bot
     user_data = await state.get_data(); current_city = user_data.get("current_shown_city"); user_id = callback.from_user.id
     if current_city:
         logger.info(f"User {user_id} requested back to current weather: {current_city}")
         await _get_and_show_weather(bot, callback, state, session, city_input=current_city) # <<< Передаем bot
     else: logger.warning(f"User {user_id} requested back to current weather, no city in state."); await callback.answer("...", show_alert=True); from src.handlers.utils import show_main_menu_message; await state.clear(); await show_main_menu_message(callback)


# Обработчик "Назад в меню" (без изменений)
@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    from src.handlers.utils import show_main_menu_message; logger.info(f"User {callback.from_user.id} requested back to main menu..."); await state.clear(); await show_main_menu_message(callback)