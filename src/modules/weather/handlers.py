# src/modules/weather/handlers.py

import logging
from typing import Union, Optional, Dict, Any # Добавили Dict, Any

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Union

# Импорты
from src.db.models import User
from .keyboard import (
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO,
    CALLBACK_WEATHER_FORECAST_5D, CALLBACK_WEATHER_SHOW_CURRENT, get_forecast_keyboard
)
# Добавляем импорт новой функции сервиса
from .service import (
    get_weather_data, format_weather_message,
    get_5day_forecast, format_forecast_message,
    get_weather_data_by_coords # <<< Импорт новой функции
)

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()

# --- ИЗМЕНЯЕМ ЭТУ ФУНКЦИЮ ---
async def _get_and_show_weather(
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    # Теперь принимаем или город, или координаты
    city_input: Optional[str] = None,
    coords: Optional[Dict[str, float]] = None
):
    """
    Получает погоду (по городу или координатам), отображает результат.
    Предлагает сохранить город только если погода получена по НАЗВАНИЮ города,
    и этот город не является сохраненным.
    """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    is_preferred = False # Флаг, является ли показанная погода погодой для сохраненного города
    request_details = "" # Для логирования

    # Отправляем/редактируем сообщение "Загрузка..."
    try:
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("🔍 Отримую дані про погоду...")
             await target.answer()
        else:
             # Если это ответ на локацию, редактировать нечего, отвечаем
             if target.location:
                  status_message = await target.answer("🔍 Отримую дані про погоду...")
             else: # Ответ на текст
                  status_message = await target.answer("🔍 Отримую дані про погоду...")
    except Exception as e:
         logger.error(f"Error sending/editing status message: {e}")
         status_message = message_to_edit_or_answer # Fallback

    # --- Определяем, как получать погоду ---
    weather_data = None
    if coords:
         request_details = f"coords ({coords['lat']:.4f}, {coords['lon']:.4f})"
         logger.info(f"User {user_id} requesting weather by {request_details}")
         weather_data = await get_weather_data_by_coords(coords['lat'], coords['lon'])
    elif city_input:
         request_details = f"city '{city_input}'"
         logger.info(f"User {user_id} requesting weather by {request_details}")
         weather_data = await get_weather_data(city_input)
         # Проверяем, совпадает ли запрошенный город с сохраненным
         db_user = await session.get(User, user_id)
         preferred_city = db_user.preferred_city if db_user else None
         if preferred_city and weather_data and weather_data.get("cod") == 200:
              api_city_name = weather_data.get("name")
              # Сравниваем и имя от API, и ввод пользователя (на всякий случай) с сохраненным
              if api_city_name and preferred_city.lower() == api_city_name.lower():
                   is_preferred = True
              elif preferred_city.lower() == city_input.lower():
                   is_preferred = True
    else:
         logger.error(f"No city or coords provided to _get_and_show_weather for user {user_id}")
         await status_message.edit_text("Помилка: Не вказано місто або координати.")
         await state.clear()
         return

    # Определяем сообщение или колбэк для окончательного ответа
    final_target_message = status_message if status_message else message_to_edit_or_answer

    # --- Обработка ответа API ---
    if weather_data and (weather_data.get("cod") == 200 or str(weather_data.get("cod")) == "200"):
        # Получаем название города из ответа API
        actual_city_name_from_api = weather_data.get("name")
        # Если запрашивали по координатам и API не вернул имя, используем запасной вариант
        if coords and not actual_city_name_from_api:
            city_display_name = "за вашими координатами"
        # Если запрашивали по имени, используем ввод пользователя для отображения
        elif city_input:
             city_display_name = city_input.capitalize()
        # Иначе (например, коорд + имя от API) используем имя от API
        else:
             city_display_name = actual_city_name_from_api

        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for {request_details} (display name: '{city_display_name}') for user {user_id}")

        # Сохраняем в состояние город от API (для сохранения) и город для показа/обновления
        current_shown_city_for_refresh = actual_city_name_from_api if actual_city_name_from_api else city_input if city_input else None # Для кнопки Обновить лучше имя от API
        await state.update_data(
            city_to_save=actual_city_name_from_api,
            city_display_name=city_display_name,
            current_shown_city=current_shown_city_for_refresh,
            current_coords=coords, # Сохраняем координаты, если они были
            preferred_city=preferred_city if city_input else None # Сохраняем preferred для сравнения
        )

        # Предлагаем сохранить ТОЛЬКО если запрашивали по НАЗВАНИЮ города и он НЕ сохраненный
        ask_to_save = city_input and not is_preferred

        if ask_to_save:
            text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
            await state.set_state(WeatherStates.waiting_for_save_decision)
        else:
            # Просто показываем погоду и кнопки действий
            reply_markup = get_weather_actions_keyboard()
            await final_target_message.edit_text(weather_message, reply_markup=reply_markup)
            # Состояние НЕ очищаем, чтобы работали кнопки действий

    # --- Обработка ошибок API ---
    elif weather_data and (weather_data.get("cod") == 404 or str(weather_data.get("cod")) == "404"):
        # Используем ввод пользователя для сообщения об ошибке, если он был
        city_error_name = city_input if city_input else "вказана локація"
        error_text = f"😔 На жаль, місто/локація '<b>{city_error_name}</b>' не знайдено..."
        reply_markup = get_weather_enter_city_back_keyboard()
        await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"Location '{request_details}' not found for user {user_id}")
        await state.clear() # Очищаем состояние при ошибке
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для {request_details} (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {request_details} for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
        await state.clear()


async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession):
    """ Точка входа в модуль погоды. Проверяет сохраненный город или запрашивает новый. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)

    if isinstance(target, CallbackQuery): await target.answer()

    preferred_city = db_user.preferred_city if db_user else None

    if preferred_city:
        logger.info(f"User {user_id} has preferred city: {preferred_city}. Showing weather directly.")
        await state.update_data(preferred_city=preferred_city)
        # Показываем погоду по НАЗВАНИЮ города, is_preferred=True
        await _get_and_show_weather(target, state, session, city_input=preferred_city, is_preferred=True)
    else:
        # Если город не сохранен, просим ввести
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        text = "🌍 Будь ласка, введіть назву міста або надішліть геолокацію:" # Обновили текст
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
             if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e: logger.error(f"Error editing/sending message: {e}"); await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_city)


# --- НОВЫЙ Обработчик для геолокации ---
@router.message(F.location)
async def handle_location(message: Message, state: FSMContext, session: AsyncSession):
    """ Обрабатывает полученную геолокацию. """
    if message.location:
         lat = message.location.latitude
         lon = message.location.longitude
         user_id = message.from_user.id
         logger.info(f"Received location from user {user_id}: lat={lat}, lon={lon}")
         await state.clear() # Очищаем предыдущее состояние, если было
         # Показываем погоду по координатам. is_preferred всегда False для геолокации.
         await _get_and_show_weather(message, state, session, coords={"lat": lat, "lon": lon}, is_preferred=False)


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    """ Обрабатывает ввод города пользователем. """
    user_city_input = message.text.strip()
    # Получаем пользователя и его сохраненный город
    db_user = await session.get(User, message.from_user.id)
    preferred_city = db_user.preferred_city if db_user else None
    # Считаем город предпочтительным, если он совпадает с сохраненным (игнорируя регистр)
    is_preferred = (preferred_city is not None and preferred_city.lower() == user_city_input.lower())
    await _get_and_show_weather(message, state, session, city_input=user_city_input, is_preferred=is_preferred)


# --- Обработчики кнопок действий ---
@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    logger.info(f"User {callback.from_user.id} requested OTHER city."); await callback.message.edit_text("🌍 Будь ласка, введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard()); await state.set_state(WeatherStates.waiting_for_city); await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Обновляет погоду для последнего показанного места (город или координаты). """
    user_data = await state.get_data()
    coords = user_data.get("current_coords")
    city_name = user_data.get("current_shown_city") # Город, который был показан
    preferred_city = user_data.get("preferred_city") # Сохраненный город
    user_id = callback.from_user.id

    if coords: # Если последний раз показывали по координатам
        logger.info(f"User {user_id} requested REFRESH for coords: {coords}")
        # is_preferred всегда False для координат
        await _get_and_show_weather(callback, state, session, coords=coords, is_preferred=False)
    elif city_name: # Если последний раз показывали по имени города
         logger.info(f"User {user_id} requested REFRESH for city: {city_name}")
         is_preferred_city = (preferred_city is not None and preferred_city.lower() == city_name.lower())
         await _get_and_show_weather(callback, state, session, city_input=city_name, is_preferred=is_preferred_city)
    else: # Если в состоянии ничего нет
        logger.warning(f"User {user_id} requested REFRESH, but no location/city found in state.")
        await callback.message.edit_text("Не вдалося визначити місце для оновлення. Введіть назву:", reply_markup=get_weather_enter_city_back_keyboard())
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.answer("Не вдалося оновити.", show_alert=True)


# --- Обработчики сохранения города ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, commit остается, state НЕ очищается) ...
    user_data = await state.get_data(); city_to_save_in_db = user_data.get("city_to_save"); city_display_name = user_data.get("city_display_name"); user_id = callback.from_user.id
    if not city_to_save_in_db or not city_display_name: logger.error(f"... city name not found ..."); from src.handlers.utils import show_main_menu_message; await show_main_menu_message(callback, "Помилка: не вдалося..."); return
    db_user = await session.get(User, user_id)
    if db_user:
         try: db_user.preferred_city = city_to_save_in_db; session.add(db_user); await session.commit(); logger.info(f"... saved city: {city_to_save_in_db}. Commit executed."); text = f"✅ Місто <b>{city_display_name}</b> збережено."; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
         except Exception as e: logger.exception(f"... DB error saving city: {e}"); await session.rollback(); await callback.message.edit_text("😥 Виникла помилка...")
    else: logger.error(f"... user not found in DB."); await callback.message.edit_text("Помилка: не вдалося знайти дані...")
    # НЕ ОЧИЩАЕМ СОСТОЯНИЕ ЗДЕСЬ
    await callback.answer()

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений, state НЕ очищается) ...
     logger.info(f"User {callback.from_user.id} chose not to save."); user_data = await state.get_data(); city_display_name = user_data.get("city_display_name", "місто"); weather_part = callback.message.text.split('\n\n')[0]; text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup)
     # НЕ ОЧИЩАЕМ СОСТОЯНИЕ ЗДЕСЬ
     await callback.answer()


# --- Обработчик кнопки "Назад в меню" из экрана ввода города ---
@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    from src.handlers.utils import show_main_menu_message
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather input.")
    await state.clear() # Очищаем состояние при явном выходе
    await show_main_menu_message(callback)