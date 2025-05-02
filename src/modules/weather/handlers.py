# src/modules/weather/handlers.py

import logging
from typing import Union

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

# Убираем импорт CALLBACK_WEATHER из inline_main, он больше не нужен для входа
# from src.keyboards.inline_main import CALLBACK_WEATHER
from src.handlers.common import show_main_menu_message # Импортируем новую функцию возврата
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

async def _get_and_show_weather(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, user_city_input: str):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target

    # Отправляем/редактируем сообщение "Загрузка..."
    try:
        # Пытаемся редактировать, если это колбэк
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("🔍 Отримую дані про погоду...")
             await target.answer() # Отвечаем на колбэк
        else: # Отправляем новое сообщение
             status_message = await message_to_edit_or_answer.answer("🔍 Отримую дані про погоду...")
    except Exception as e:
         logger.error(f"Error sending/editing status message: {e}")
         # Если не удалось отправить статус, пробуем отправить ответ позже новым сообщением
         status_message = message_to_edit_or_answer # Используем исходное сообщение/колбэк

    logger.info(f"User {user_id} requesting weather for user input: {user_city_input}")
    weather_data = await get_weather_data(user_city_input)

    if weather_data and weather_data.get("cod") == 200:
        actual_city_name_from_api = weather_data.get("name", user_city_input)
        city_display_name = user_city_input.capitalize()
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for display name '{city_display_name}' (API name: '{actual_city_name_from_api}') for user {user_id}")
        await state.update_data(
            city_to_save=actual_city_name_from_api,
            city_display_name=city_display_name
        )
        text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?"
        reply_markup = get_save_city_keyboard()
        # Пытаемся отредактировать статусное сообщение, или исходное, или отправляем новое
        try:
             await status_message.edit_text(text_to_send, reply_markup=reply_markup)
        except Exception:
             await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup)

        await state.set_state(WeatherStates.waiting_for_save_decision)
    elif weather_data and weather_data.get("cod") == 404:
        error_text = f"😔 На жаль, місто '<b>{user_city_input}</b>' не знайдено..." # ... (текст без изменений)
        reply_markup = get_weather_back_keyboard()
        try:
             await status_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception:
             await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
        logger.warning(f"City '{user_city_input}' not found for user {user_id}")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди..." # ... (текст без изменений)
        reply_markup = get_weather_back_keyboard()
        try:
             await status_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception:
             await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {user_city_input} for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
        await state.clear()


# --- Точка входа в модуль Погоды ---
# @router.callback_query(F.data == CALLBACK_WEATHER) # <- Убираем этот декоратор
async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession): # <<< Новое имя и тип
    """
    Точка входа в модуль погоды. Проверяет сохраненный город или запрашивает новый.
    Может вызываться из Message или CallbackQuery.
    """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)

    # Отвечаем на колбэк, если он был
    if isinstance(target, CallbackQuery):
        await target.answer()

    if db_user and db_user.preferred_city:
        saved_city = db_user.preferred_city
        logger.info(f"User {user_id} has preferred city: {saved_city}")
        await state.update_data(preferred_city=saved_city)
        text = f"Ваше збережене місто: <b>{saved_city}</b>.\nПоказати погоду для нього?"
        reply_markup = get_city_confirmation_keyboard()
        # Пытаемся редактировать, если это колбэк, иначе отвечаем
        try:
             if isinstance(target, CallbackQuery):
                  await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else:
                  await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Error editing/sending message in weather_entry_point: {e}")
             await message_to_edit_or_answer.answer(text, reply_markup=reply_markup) # Fallback

        await state.set_state(WeatherStates.waiting_for_confirmation)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        text = "🌍 Будь ласка, введіть назву міста:"
        # Пытаемся редактировать или отвечаем
        try:
             if isinstance(target, CallbackQuery):
                  await message_to_edit_or_answer.edit_text(text)
             else:
                  await message_to_edit_or_answer.answer(text)
        except Exception as e:
             logger.error(f"Error editing/sending message in weather_entry_point: {e}")
             await message_to_edit_or_answer.answer(text) # Fallback

        await state.set_state(WeatherStates.waiting_for_city)


# --- Остальные обработчики (колбэки и сообщения внутри модуля) остаются почти без изменений ---
# Они уже привязаны к своему роутеру и состояниям FSM

@router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_USE_SAVED)
async def handle_use_saved_city(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, вызывает _get_and_show_weather) ...
    user_data = await state.get_data()
    saved_city = user_data.get("preferred_city")
    user_id = callback.from_user.id
    if saved_city:
        logger.info(f"User {user_id} confirmed using saved city: {saved_city}")
        await _get_and_show_weather(callback, state, session, user_city_input=saved_city)
    else: # ... (обработка ошибки) ...
        logger.warning(f"User {user_id} confirmed using saved city, but city not found in state.")
        await callback.message.edit_text("Щось пішло не так. Будь ласка, введіть назву міста:")
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.answer()


@router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_other_city_request(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    logger.info(f"User {callback.from_user.id} chose to enter another city.")
    await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.answer()


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, вызывает _get_and_show_weather) ...
    user_city_input = message.text.strip()
    await _get_and_show_weather(message, state, session, user_city_input=user_city_input)


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений, с явным commit) ...
    user_data = await state.get_data()
    city_to_save_in_db = user_data.get("city_to_save")
    city_display_name = user_data.get("city_display_name")
    user_id = callback.from_user.id
    if not city_to_save_in_db or not city_display_name: # ... (обработка ошибки) ...
        logger.error(f"Cannot save city for user {user_id}: city name (API or display) not found in state.")
        await state.clear()
        await show_main_menu_message(callback, "Помилка: не вдалося отримати назву міста для збереження.") # Используем новую функцию возврата
        return
    db_user = await session.get(User, user_id)
    if db_user: # ... (try/except с commit) ...
        try:
            db_user.preferred_city = city_to_save_in_db
            session.add(db_user)
            await session.commit()
            logger.info(f"User {user_id} saved city to DB: {city_to_save_in_db}. Explicit commit executed.")
            text = f"✅ Місто <b>{city_display_name}</b> збережено як основне.\n\n" + callback.message.text.split('\n\n')[0]
            reply_markup = get_weather_back_keyboard()
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e: # ... (обработка ошибки commit) ...
            logger.exception(f"Database error while saving city for user {user_id}: {e}")
            await session.rollback()
            await callback.message.edit_text("😥 Виникла помилка при збереженні міста.")
    else: # ... (обработка ненайденного пользователя) ...
         logger.error(f"Cannot save city for user {user_id}: user not found in DB.")
         await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження міста.")

    await state.clear()
    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код почти без изменений, использует текст из пред. сообщения) ...
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    user_data = await state.get_data()
    city_display_name = user_data.get("city_display_name", "місто")
    weather_part = callback.message.text.split('\n\n')[0]
    text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"
    reply_markup = get_weather_back_keyboard()
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_BACK)
async def handle_weather_back(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений, но вызывает новую функцию возврата) ...
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather.")
    await state.clear()
    await show_main_menu_message(callback) # Используем новую функцию возврата