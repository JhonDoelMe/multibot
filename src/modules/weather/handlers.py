# src/modules/weather/handlers.py (возвращаем commit)

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

async def _get_and_show_weather(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, city_name: str):
    # (Эта функция остается без изменений)
    user_id = target.from_user.id
    message_to_edit = None

    if isinstance(target, CallbackQuery):
        message_to_edit = target.message
        await target.answer()
    else:
        message_to_edit = await target.answer("🔍 Отримую дані про погоду...")

    logger.info(f"User {user_id} requesting weather for city: {city_name}")
    weather_data = await get_weather_data(city_name)

    if weather_data and weather_data.get("cod") == 200:
        actual_city_name = weather_data.get("name", city_name)
        weather_message = format_weather_message(weather_data, actual_city_name)
        logger.info(f"Sent weather for {actual_city_name} to user {user_id}")

        await state.update_data(last_successful_city=actual_city_name)

        text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{actual_city_name}</b> як основне місто?"
        reply_markup = get_save_city_keyboard()
        await message_to_edit.edit_text(text_to_send, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_save_decision)

    elif weather_data and weather_data.get("cod") == 404:
        error_text = f"😔 На жаль, місто '<b>{city_name}</b>' не знайдено. Спробуйте іншу назву або перевірте написання."
        reply_markup = get_weather_back_keyboard()
        await message_to_edit.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"City '{city_name}' not found for user {user_id}")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди (Код: {error_code}). Спробуйте пізніше."
        reply_markup = get_weather_back_keyboard()
        await message_to_edit.edit_text(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {city_name} for user {user_id}. Code: {error_code}")
        await state.clear()

# --- Обработчики основного потока (остаются без изменений) ---
@router.callback_query(F.data == CALLBACK_WEATHER)
async def handle_weather_entry(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    # ... (код без изменений) ...
    user_id = callback.from_user.id
    db_user = await session.get(User, user_id)

    if db_user and db_user.preferred_city:
        logger.info(f"User {user_id} has preferred city: {db_user.preferred_city}")
        await state.update_data(preferred_city=db_user.preferred_city)
        text = f"Ваше збережене місто: <b>{db_user.preferred_city}</b>.\nПоказати погоду для нього?"
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
    # ... (код без изменений) ...
    user_data = await state.get_data()
    saved_city = user_data.get("preferred_city")
    user_id = callback.from_user.id

    if saved_city:
        logger.info(f"User {user_id} confirmed using saved city: {saved_city}")
        await _get_and_show_weather(callback, state, session, saved_city)
    else:
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
    # ... (код без изменений) ...
    city_name = message.text.strip()
    await _get_and_show_weather(message, state, session, city_name)


# --- Обработчики сохранения города (ВОЗВРАЩАЕМ ЯВНЫЙ COMMIT) ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Обрабатывает ответ 'Да' на вопрос о сохранении города. """
    user_data = await state.get_data()
    city_to_save = user_data.get("last_successful_city")
    user_id = callback.from_user.id

    if not city_to_save:
        logger.error(f"Cannot save city for user {user_id}: city name not found in state.")
        await state.clear()
        await show_main_menu(callback, "Помилка: не вдалося отримати назву міста для збереження.")
        return

    db_user = await session.get(User, user_id)
    if db_user:
        try:
            db_user.preferred_city = city_to_save
            session.add(db_user)
            # !!! ВОЗВРАЩАЕМ ЯВНЫЙ COMMIT !!!
            await session.commit()
            logger.info(f"User {user_id} saved city: {city_to_save}. Explicit commit executed.") # Обновили лог

            text = f"✅ Місто <b>{city_to_save}</b> збережено як основне.\n\n" + callback.message.text.split('\n\n')[0]
            reply_markup = get_weather_back_keyboard()
            await callback.message.edit_text(text, reply_markup=reply_markup)

        except Exception as e:
            logger.exception(f"Database error while saving city for user {user_id}: {e}")
            await session.rollback() # Явно откатываем сессию при ошибке коммита
            await callback.message.edit_text("😥 Виникла помилка при збереженні міста.")
    else:
        logger.error(f"Cannot save city for user {user_id}: user not found in DB.")
        await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження міста.")

    await state.clear()
    await callback.answer()

# --- Остальные обработчики без изменений ---
@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    # ... (код без изменений) ...
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    text = callback.message.text.split('\n\n')[0]
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