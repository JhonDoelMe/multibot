# src/modules/weather/handlers.py

import logging
from typing import Union, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from src.handlers.common import show_main_menu_message
from src.db.models import User
from .service import get_weather_data, format_weather_message
from .keyboard import (
    # Клавиатура для действий после показа погоды
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    # Клавиатура при ошибке ввода / запросе ввода
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    # Клавиатура для сохранения (если город не основной)
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO
)

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    # Убираем waiting_for_confirmation, больше не нужно
    waiting_for_city = State()         # Ожидание названия города
    waiting_for_save_decision = State() # Ожидание решения о сохранении

async def _get_and_show_weather(
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    user_city_input: str,
    is_preferred: bool # <<< Новый флаг: является ли этот город сохраненным?
):
    """
    Получает погоду, отображает результат.
    Предлагает сохранить город только если is_preferred=False.
    Показывает кнопки действий после погоды.
    """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None

    # Отправляем/редактируем сообщение "Загрузка..."
    try:
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("🔍 Отримую дані про погоду...")
             await target.answer()
        else:
             status_message = await message_to_edit_or_answer.answer("🔍 Отримую дані про погоду...")
    except Exception as e:
         logger.error(f"Error sending/editing status message: {e}")
         status_message = message_to_edit_or_answer

    logger.info(f"User {user_id} requesting weather for city: {user_city_input}")
    weather_data = await get_weather_data(user_city_input)

    # Определяем сообщение или колбэк для окончательного ответа
    final_target_message = status_message if status_message else message_to_edit_or_answer

    if weather_data and weather_data.get("cod") == 200:
        actual_city_name_from_api = weather_data.get("name", user_city_input)
        city_display_name = user_city_input.capitalize() # Используем ввод пользователя для показа
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for display name '{city_display_name}' (API name: '{actual_city_name_from_api}') for user {user_id}")

        # Сохраняем в состояние имя от API (для сохранения) и имя от пользователя (для показа)
        # Сохраняем также текущий город, для которого показали погоду (для кнопки Обновить)
        await state.update_data(
            city_to_save=actual_city_name_from_api,
            city_display_name=city_display_name,
            current_shown_city=user_city_input # Сохраняем исходный ввод для кнопки Обновить
        )

        # Спрашиваем о сохранении ТОЛЬКО если это НЕ уже сохраненный город
        if not is_preferred:
            text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
            await state.set_state(WeatherStates.waiting_for_save_decision)
        else:
            # Если это сохраненный город, просто показываем погоду и кнопки действий
            reply_markup = get_weather_actions_keyboard()
            await final_target_message.edit_text(weather_message, reply_markup=reply_markup)
            # Состояние можно очистить, если мы не ждем нажатия Обновить/Другой город в FSM
            # Но лучше оставить, если кнопки действий требуют FSM
            # await state.clear() # Пока не очищаем, может понадобиться current_shown_city

    # --- Обработка ошибок (без изменений) ---
    elif weather_data and weather_data.get("cod") == 404:
        error_text = f"😔 На жаль, місто '<b>{user_city_input}</b>' не знайдено..."
        reply_markup = get_weather_enter_city_back_keyboard() # Предлагаем вернуться в меню
        await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"City '{user_city_input}' not found for user {user_id}")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для '<b>{user_city_input}</b>' (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {user_city_input} for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
        await state.clear()

# --- Точка входа в модуль Погоды ---
async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)

    if isinstance(target, CallbackQuery): await target.answer()

    if db_user and db_user.preferred_city:
        # Если город сохранен, сразу показываем погоду
        saved_city = db_user.preferred_city
        logger.info(f"User {user_id} has preferred city: {saved_city}. Showing weather directly.")
        await state.update_data(preferred_city=saved_city) # Сохраняем для _get_and_show_weather
        # Вызываем показ погоды, передавая город и флаг is_preferred=True
        await _get_and_show_weather(target, state, session, user_city_input=saved_city, is_preferred=True)
    else:
        # Если город не сохранен, просим ввести
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        text = "🌍 Будь ласка, введіть назву міста:"
        reply_markup = get_weather_enter_city_back_keyboard() # Клавиатура с кнопкой Назад
        try:
             if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Error editing/sending message in weather_entry_point: {e}")
             await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_city)


# --- Обработчики ---

# Убираем обработчик city_confirmation, он больше не нужен
# @router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_USE_SAVED) ...
# @router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_OTHER_CITY) ...

@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    """ Обрабатывает ввод города пользователем. """
    user_city_input = message.text.strip()
    # Вызываем показ погоды, is_preferred=False, так как город только что введен
    await _get_and_show_weather(message, state, session, user_city_input=user_city_input, is_preferred=False)

# --- НОВЫЕ Обработчики для кнопок действий ---
@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    """ Обрабатывает кнопку 'Інше місто'. """
    logger.info(f"User {callback.from_user.id} requested OTHER city from weather view.")
    await callback.message.edit_text("🌍 Будь ласка, введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.answer()

@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Обрабатывает кнопку 'Оновити'. """
    user_data = await state.get_data()
    current_city = user_data.get("current_shown_city") # Берем город, который был показан
    preferred_city = user_data.get("preferred_city") # Берем сохраненный
    user_id = callback.from_user.id

    if current_city:
        logger.info(f"User {user_id} requested REFRESH for city: {current_city}")
        # Определяем, является ли текущий город сохраненным
        is_preferred_city = (current_city == preferred_city)
        # Показываем погоду для текущего отображенного города
        await _get_and_show_weather(callback, state, session, user_city_input=current_city, is_preferred=is_preferred_city)
    else:
        # Если в состоянии нет города (странно), просим ввести заново
        logger.warning(f"User {user_id} requested REFRESH, but no city found in state.")
        await callback.message.edit_text("Не вдалося визначити місто для оновлення. Введіть назву:", reply_markup=get_weather_enter_city_back_keyboard())
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.answer("Не вдалося оновити.", show_alert=True)


# --- Обработчики сохранения города (остаются) ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, с явным commit) ...
    user_data = await state.get_data(); city_to_save_in_db = user_data.get("city_to_save"); city_display_name = user_data.get("city_display_name"); user_id = callback.from_user.id
    if not city_to_save_in_db or not city_display_name: logger.error(f"... city name not found ..."); await state.clear(); from src.handlers.common import show_main_menu_message; await show_main_menu_message(callback, "Помилка: не вдалося..."); return
    db_user = await session.get(User, user_id)
    if db_user:
         try: db_user.preferred_city = city_to_save_in_db; session.add(db_user); await session.commit(); logger.info(f"... saved city to DB: {city_to_save_in_db}. Explicit commit executed."); text = f"✅ Місто <b>{city_display_name}</b> збережено як основне."; reply_markup = get_weather_actions_keyboard(); await callback.message.edit_text(text, reply_markup=reply_markup) # Показываем кнопки действий после сохранения
         except Exception as e: logger.exception(f"... DB error saving city: {e}"); await session.rollback(); await callback.message.edit_text("😥 Виникла помилка...")
    else: logger.error(f"... user not found in DB."); await callback.message.edit_text("Помилка: не вдалося знайти дані...")
    await state.clear(); await callback.answer()


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений, но показывает кнопки действий) ...
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    user_data = await state.get_data(); city_display_name = user_data.get("city_display_name", "місто");
    # Получаем погоду из текста сообщения, чтобы показать ее снова
    weather_part = callback.message.text.split('\n\n')[0]
    text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"
    reply_markup = get_weather_actions_keyboard() # <<< Показываем кнопки действий
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await state.clear(); await callback.answer()


# Обработчик кнопки Назад из экрана ввода города
@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    from src.handlers.common import show_main_menu_message
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather input.")
    await state.clear()
    await show_main_menu_message(callback)