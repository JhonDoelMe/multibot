# src/modules/weather/handlers.py

import logging
from typing import Union, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Union

# Импорты
from src.db.models import User
# <<< ИСПРАВЛЕННЫЙ ИМПОРТ КЛАВИАТУР/КОЛБЭКОВ >>>
from .keyboard import (
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO,
    CALLBACK_WEATHER_FORECAST_5D, # Добавлено
    CALLBACK_WEATHER_SHOW_CURRENT, # Добавлено
    get_forecast_keyboard # Добавлено
)
from .service import get_weather_data, format_weather_message, get_5day_forecast, format_forecast_message # Добавили импорты для прогноза

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()

async def _get_and_show_weather(
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    user_city_input: str,
    is_preferred: bool
):
    # ... (код функции без изменений) ...
    user_id = target.from_user.id; message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target; status_message = None
    try:
        if isinstance(target, CallbackQuery): status_message = await message_to_edit_or_answer.edit_text("🔍 Отримую дані про погоду..."); await target.answer()
        else: status_message = await message_to_edit_or_answer.answer("🔍 Отримую дані про погоду...")
    except Exception as e: logger.error(f"Error sending/editing status message: {e}"); status_message = message_to_edit_or_answer
    logger.info(f"User {user_id} requesting weather for user input: {user_city_input}")
    weather_data = await get_weather_data(user_city_input)
    final_target_message = status_message if status_message else message_to_edit_or_answer
    if weather_data and weather_data.get("cod") == 200:
        actual_city_name_from_api = weather_data.get("name", user_city_input); city_display_name = user_city_input.capitalize()
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for display name '{city_display_name}' (API name: '{actual_city_name_from_api}') for user {user_id}")
        # Сохраняем в состояние preferred_city, если он есть, чтобы помнить, какой город сохраненный
        db_user = await session.get(User, user_id)
        await state.update_data(
            city_to_save=actual_city_name_from_api, city_display_name=city_display_name,
            current_shown_city=user_city_input, preferred_city=(db_user.preferred_city if db_user else None) # <<< Сохраняем preferred_city
        )
        if not is_preferred:
            text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?"; reply_markup = get_save_city_keyboard()
            try: await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
            except Exception: await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup) # Fallback
            await state.set_state(WeatherStates.waiting_for_save_decision)
        else:
            reply_markup = get_weather_actions_keyboard() # Клавиатура действий
            try: await final_target_message.edit_text(weather_message, reply_markup=reply_markup)
            except Exception: await message_to_edit_or_answer.answer(weather_message, reply_markup=reply_markup) # Fallback
            # Состояние не очищаем, чтобы работали кнопки Обновить/Прогноз
    elif weather_data and weather_data.get("cod") == 404: # ... (обработка 404) ...
         error_text = f"😔 На жаль, місто '<b>{user_city_input}</b>' не знайдено..."; reply_markup = get_weather_enter_city_back_keyboard()
         try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
         except Exception: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
         logger.warning(f"City '{user_city_input}' not found for user {user_id}"); await state.clear()
    else: # ... (обработка других ошибок) ...
         error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'; error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
         error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для '<b>{user_city_input}</b>' (Код: {error_code} - {error_api_message}). Спробуйте пізніше."; reply_markup = get_weather_enter_city_back_keyboard()
         try: await final_target_message.edit_text(error_text, reply_markup=reply_markup)
         except Exception: await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
         logger.error(f"Failed to get weather for {user_city_input} for user {user_id}. Code: {error_code}, Msg: {error_api_message}"); await state.clear()


async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession):
    # ... (код функции без изменений) ...
    user_id = target.from_user.id; message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target; db_user = await session.get(User, user_id)
    if isinstance(target, CallbackQuery): await target.answer()
    preferred_city = db_user.preferred_city if db_user else None
    if preferred_city:
        logger.info(f"User {user_id} has preferred city: {preferred_city}. Showing weather directly.")
        await state.update_data(preferred_city=preferred_city) # Передаем сохраненный город в состояние
        await _get_and_show_weather(target, state, session, user_city_input=preferred_city, is_preferred=True)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg); text = "🌍 Будь ласка, введіть назву міста:"; reply_markup = get_weather_enter_city_back_keyboard()
        try:
             if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e: logger.error(f"Error editing/sending message: {e}"); await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_city)


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    # ... (код без изменений) ...
     user_city_input = message.text.strip(); db_user = await session.get(User, message.from_user.id); preferred_city = db_user.preferred_city if db_user else None; is_preferred = (preferred_city is not None and preferred_city.lower() == user_city_input.lower()); await _get_and_show_weather(message, state, session, user_city_input=user_city_input, is_preferred=is_preferred)

@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
     logger.info(f"User {callback.from_user.id} requested OTHER city."); await callback.message.edit_text("🌍 Будь ласка, введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard()); await state.set_state(WeatherStates.waiting_for_city); await callback.answer()

@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений) ...
     user_data = await state.get_data(); current_city = user_data.get("current_shown_city"); preferred_city = user_data.get("preferred_city"); user_id = callback.from_user.id
     if current_city: logger.info(f"User {user_id} requested REFRESH for: {current_city}"); is_preferred_city = (preferred_city is not None and preferred_city.lower() == current_city.lower()); await _get_and_show_weather(callback, state, session, user_city_input=current_city, is_preferred=is_preferred_city)
     else: logger.warning(f"User {user_id} requested REFRESH, no city in state."); await callback.message.edit_text("...", reply_markup=get_weather_enter_city_back_keyboard()); await state.set_state(WeatherStates.waiting_for_city); await callback.answer("...", show_alert=True)

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, с явным commit, но без state.clear()) ...
    user_data = await state.get_data(); city_to_save_in_db = user_data.get("city_to_save"); city_display_name = user_data.get("city_display_name"); user_id = callback.from_user.id
    if not city_to_save_in_db or not city_display_name: logger.error(f"... city name not found ..."); from src.handlers.utils import show_main_menu_message; await show_main_menu_message(callback, "Помилка: не вдалося..."); return
    db_user = await session.get(User, user_id)
    if db_user:
         try: db_user.preferred_city = city_to_save_in_db; session.add(db_user); await session.commit(); logger.info(f"... saved city: {city_to_save_in_db}. Commit executed."); text = f"✅ Місто <b>{city_display_name}</b> збережено."; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
         except Exception as e: logger.exception(f"... DB error saving city: {e}"); await session.rollback(); await callback.message.edit_text("😥 Виникла помилка...")
    else: logger.error(f"... user not found in DB."); await callback.message.edit_text("Помилка: не вдалося знайти дані...")
    # await state.clear() # НЕ ОЧИЩАЕМ, чтобы работали кнопки Обновить/Прогноз
    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений, без state.clear()) ...
     logger.info(f"User {callback.from_user.id} chose not to save."); user_data = await state.get_data(); city_display_name = user_data.get("city_display_name", "місто"); weather_part = callback.message.text.split('\n\n')[0]; text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
     # await state.clear() # НЕ ОЧИЩАЕМ
     await callback.answer()

# --- НОВЫЕ Обработчики для прогноза ---
@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D) # Используем импортированную константу
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Обрабатывает запрос прогноза на 5 дней. """
    user_data = await state.get_data()
    # !!! Используем current_shown_city для запроса прогноза !!!
    city_name_for_request = user_data.get("current_shown_city")
    # Используем имя для отображения из состояния
    city_display_name = user_data.get("city_display_name", city_name_for_request) # Fallback на city_name_for_request
    user_id = callback.from_user.id

    if not city_name_for_request:
         logger.warning(f"User {user_id} requested forecast, but no city found in state.")
         await callback.answer("Не вдалося визначити місто для прогнозу.", show_alert=True)
         return

    # Показываем статус и отвечаем на колбэк
    await callback.answer("Отримую прогноз...")
    status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для м. {city_display_name}...")

    forecast_api_data = await get_5day_forecast(city_name_for_request) # Запрашиваем по имени для API

    if forecast_api_data and forecast_api_data.get("cod") == "200":
         message_text = format_forecast_message(forecast_api_data, city_display_name) # Форматируем с именем для показа
         reply_markup = get_forecast_keyboard()
         await status_message.edit_text(message_text, reply_markup=reply_markup)
         logger.info(f"Sent 5-day forecast for {city_display_name} to user {user_id}")
    else: # ... (обработка ошибок API прогноза) ...
         error_code = forecast_api_data.get('cod', 'N/A') if forecast_api_data else 'N/A'
         error_api_message = forecast_api_data.get('message', 'Internal error') if forecast_api_data else 'Internal error'
         error_text = f"😥 Не вдалося отримати прогноз для м. {city_display_name} (Помилка: {error_code} - {error_api_message})."
         await status_message.edit_text(error_text) # Убираем кнопки при ошибке
         logger.error(f"Failed to get 5-day forecast for {city_display_name} (request: {city_name_for_request}) for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
         # Очищаем состояние при ошибке? Можно.
         await state.clear()


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT) # Используем импортированную константу
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
     """ Обрабатывает кнопку 'Назад до поточної погоди'. """
     user_data = await state.get_data()
     current_city = user_data.get("current_shown_city")
     preferred_city = user_data.get("preferred_city") # preferred_city тоже должен быть в state
     user_id = callback.from_user.id

     if current_city:
         logger.info(f"User {user_id} requested back to current weather for city: {current_city}")
         is_preferred_city = (preferred_city is not None and preferred_city.lower() == current_city.lower())
         await _get_and_show_weather(callback, state, session, user_city_input=current_city, is_preferred=is_preferred_city)
     else:
         logger.warning(f"User {user_id} requested back to current weather, but no city in state.")
         await callback.answer("Не вдалося визначити місто.", show_alert=True)
         from src.handlers.utils import show_main_menu_message # Импорт внутри
         await state.clear()
         await show_main_menu_message(callback)


# --- Обработчик кнопки "Назад в меню" из экрана ввода города ---
@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    from src.handlers.utils import show_main_menu_message
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather input.")
    await state.clear()
    await show_main_menu_message(callback)