# src/modules/weather/handlers.py

import logging
from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.inline_main import CALLBACK_WEATHER
from src.handlers.common import show_main_menu
from src.db.models import User
from .service import get_weather_data, format_weather_message
from .keyboard import (
    get_weather_back_keyboard, CALLBACK_WEATHER_BACK,
    get_city_confirmation_keyboard, CALLBACK_WEATHER_USE_SAVED, CALLBACK_WEATHER_OTHER_CITY,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO
)

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_confirmation = State()
    waiting_for_city = State()
    waiting_for_save_decision = State()

async def _get_and_show_weather(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, user_city_input: str): # <<< Принимаем user_city_input
    """
    Получает погоду, отображает результат (используя user_city_input для отображения)
    и предлагает сохранить город (используя user_city_input для вопроса, но сохраняя API-версию).
    """
    user_id = target.from_user.id
    message_to_edit = None

    if isinstance(target, CallbackQuery):
        message_to_edit = target.message
        await target.answer()
    else:
        # Отправляем новое сообщение и сохраняем его для редактирования
        message_to_edit = await target.answer("🔍 Отримую дані про погоду...")

    # Запрашиваем погоду по тому, что ввел пользователь
    logger.info(f"User {user_id} requesting weather for user input: {user_city_input}")
    weather_data = await get_weather_data(user_city_input)

    if weather_data and weather_data.get("cod") == 200:
        # Успех. Берем имя из ответа API для сохранения, а ввод пользователя для отображения
        actual_city_name_from_api = weather_data.get("name", user_city_input) # Имя, которое понял OWM
        city_display_name = user_city_input.capitalize() # Имя для показа пользователю

        # Форматируем сообщение, передавая ИМЯ ДЛЯ ОТОБРАЖЕНИЯ
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for display name '{city_display_name}' (API name: '{actual_city_name_from_api}') for user {user_id}")

        # Сохраняем ОБА имени в состояние FSM для следующего шага
        await state.update_data(
            city_to_save=actual_city_name_from_api, # Имя от API для сохранения в БД
            city_display_name=city_display_name     # Имя от пользователя для показа в сообщении подтверждения
        )

        # Формируем текст: погода + вопрос о сохранении (с именем от пользователя)
        text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?" # <<< Используем ввод пользователя
        reply_markup = get_save_city_keyboard()
        await message_to_edit.edit_text(text_to_send, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_save_decision)

    # --- Обработка ошибок (без изменений) ---
    elif weather_data and weather_data.get("cod") == 404:
        error_text = f"😔 На жаль, місто '<b>{user_city_input}</b>' не знайдено. Спробуйте іншу назву або перевірте написання."
        reply_markup = get_weather_back_keyboard()
        await message_to_edit.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"City '{user_city_input}' not found for user {user_id}")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для '<b>{user_city_input}</b>' (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_back_keyboard()
        await message_to_edit.edit_text(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {user_city_input} for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
        await state.clear()

# --- Обработчики основного потока ---
@router.callback_query(F.data == CALLBACK_WEATHER)
async def handle_weather_entry(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    db_user = await session.get(User, user_id)

    if db_user and db_user.preferred_city:
        # Используем сохраненный город (который был от API)
        saved_city = db_user.preferred_city
        logger.info(f"User {user_id} has preferred city: {saved_city}")
        await state.update_data(preferred_city=saved_city) # Сохраняем в FSM
        # Показываем его пользователю (можно его же, можно попытаться найти укр. вариант - пока показываем его)
        text = f"Ваше збережене місто: <b>{saved_city}</b>.\nПоказати погоду для нього?"
        reply_markup = get_city_confirmation_keyboard()
        await callback.message.edit_text(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_confirmation)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
        await state.set_state(WeatherStates.waiting_for_city)

    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_USE_SAVED)
async def handle_use_saved_city(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    saved_city = user_data.get("preferred_city") # Берем сохраненное ИЗ БД (оно же от API)
    user_id = callback.from_user.id

    if saved_city:
        logger.info(f"User {user_id} confirmed using saved city: {saved_city}")
        # Передаем его как user_city_input, так как пользователь согласился с ним
        await _get_and_show_weather(callback, state, session, user_city_input=saved_city)
    else:
        logger.warning(f"User {user_id} confirmed using saved city, but city not found in state.")
        await callback.message.edit_text("Щось пішло не так. Будь ласка, введіть назву міста:")
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.answer()


@router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_other_city_request(callback: CallbackQuery, state: FSMContext):
    logger.info(f"User {callback.from_user.id} chose to enter another city.")
    await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.answer()


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    user_city_input = message.text.strip()
    # Передаем ввод пользователя в функцию
    await _get_and_show_weather(message, state, session, user_city_input=user_city_input)


# --- Обработчики сохранения города (изменены) ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_data = await state.get_data()
    # Берем имя от API для сохранения в БД
    city_to_save_in_db = user_data.get("city_to_save")
    # Берем имя от пользователя для отображения в сообщении
    city_display_name = user_data.get("city_display_name")
    user_id = callback.from_user.id

    if not city_to_save_in_db or not city_display_name: # Проверяем оба
        logger.error(f"Cannot save city for user {user_id}: city name (API or display) not found in state.")
        await state.clear()
        await show_main_menu(callback, "Помилка: не вдалося отримати назву міста для збереження.")
        return

    db_user = await session.get(User, user_id)
    if db_user:
        try:
            # В БД сохраняем имя, которое вернуло API
            db_user.preferred_city = city_to_save_in_db
            session.add(db_user)
            await session.commit() # Оставляем явный коммит здесь
            logger.info(f"User {user_id} saved city to DB: {city_to_save_in_db}. Explicit commit executed.")

            # В сообщении показываем имя, которое ввел пользователь
            text = f"✅ Місто <b>{city_display_name}</b> збережено як основне.\n\n" + callback.message.text.split('\n\n')[0]
            reply_markup = get_weather_back_keyboard()
            await callback.message.edit_text(text, reply_markup=reply_markup)

        except Exception as e:
            logger.exception(f"Database error while saving city for user {user_id}: {e}")
            await session.rollback()
            await callback.message.edit_text("😥 Виникла помилка при збереженні міста.")
    else:
        logger.error(f"Cannot save city for user {user_id}: user not found in DB.")
        await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження міста.")

    await state.clear()
    await callback.answer()

# --- Остальные обработчики без изменений ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений, использует текст из предыдущего сообщения) ...
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    # Берем имя для отображения из состояния, если оно есть, чтобы точно убрать вопрос
    user_data = await state.get_data()
    city_display_name = user_data.get("city_display_name", "місто") # Запасной вариант

    # Формируем текст заново, используя только погодную часть
    weather_part = callback.message.text.split('\n\n')[0]
    text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)" # Показываем, что не сохранили

    reply_markup = get_weather_back_keyboard()
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await state.clear()
    await callback.answer()

@router.callback_query(F.data == CALLBACK_WEATHER_BACK)
async def handle_weather_back(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather.")
    await state.clear()
    await show_main_menu(callback)