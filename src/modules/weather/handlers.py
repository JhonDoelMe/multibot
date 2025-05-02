# src/modules/weather/handlers.py

import logging
from typing import Union, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

# Note: show_main_menu_message is imported inside handle_weather_back_to_main
from src.db.models import User
from .service import get_weather_data, format_weather_message
from .keyboard import (
    get_weather_actions_keyboard, CALLBACK_WEATHER_OTHER_CITY, CALLBACK_WEATHER_REFRESH,
    get_weather_enter_city_back_keyboard, CALLBACK_WEATHER_BACK_TO_MAIN,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO
)

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
    """ Gets weather, displays result, asks to save if needed or shows actions. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None

    try:
        if isinstance(target, CallbackQuery):
             status_message = await message_to_edit_or_answer.edit_text("🔍 Отримую дані про погоду...")
             await target.answer()
        else:
             status_message = await message_to_edit_or_answer.answer("🔍 Отримую дані про погоду...")
    except Exception as e:
         logger.error(f"Error sending/editing status message: {e}")
         status_message = message_to_edit_or_answer

    logger.info(f"User {user_id} requesting weather for user input: {user_city_input}")
    weather_data = await get_weather_data(user_city_input)

    final_target_message = status_message if status_message else message_to_edit_or_answer

    if weather_data and weather_data.get("cod") == 200:
        actual_city_name_from_api = weather_data.get("name", user_city_input)
        city_display_name = user_city_input.capitalize()
        weather_message = format_weather_message(weather_data, city_display_name)
        logger.info(f"Formatted weather for display name '{city_display_name}' (API name: '{actual_city_name_from_api}') for user {user_id}")

        await state.update_data(
            city_to_save=actual_city_name_from_api,
            city_display_name=city_display_name,
            current_shown_city=user_city_input
        )

        if not is_preferred:
            text_to_send = f"{weather_message}\n\n💾 Зберегти <b>{city_display_name}</b> як основне місто?"
            reply_markup = get_save_city_keyboard()
            try:
                await final_target_message.edit_text(text_to_send, reply_markup=reply_markup)
            except Exception:
                 await message_to_edit_or_answer.answer(text_to_send, reply_markup=reply_markup) # Fallback
            await state.set_state(WeatherStates.waiting_for_save_decision)
        else:
            reply_markup = get_weather_actions_keyboard()
            try:
                await final_target_message.edit_text(weather_message, reply_markup=reply_markup)
            except Exception:
                 await message_to_edit_or_answer.answer(weather_message, reply_markup=reply_markup) # Fallback
            # Keep state for refresh/other actions

    elif weather_data and weather_data.get("cod") == 404:
        error_text = f"😔 На жаль, місто '<b>{user_city_input}</b>' не знайдено. Спробуйте іншу назву або перевірте написання."
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception:
             await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup) # Fallback
        logger.warning(f"City '{user_city_input}' not found for user {user_id}")
        await state.clear()
    else:
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_api_message = weather_data.get('message', 'Internal error') if weather_data else 'Internal error'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди для '<b>{user_city_input}</b>' (Код: {error_code} - {error_api_message}). Спробуйте пізніше."
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await final_target_message.edit_text(error_text, reply_markup=reply_markup)
        except Exception:
             await message_to_edit_or_answer.answer(error_text, reply_markup=reply_markup) # Fallback
        logger.error(f"Failed to get weather for {user_city_input} for user {user_id}. Code: {error_code}, Msg: {error_api_message}")
        await state.clear()


async def weather_entry_point(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession):
    """ Entry point for the weather module. Checks saved city or asks for input. """
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)

    if isinstance(target, CallbackQuery): await target.answer()

    preferred_city = db_user.preferred_city if db_user else None

    if preferred_city:
        logger.info(f"User {user_id} has preferred city: {preferred_city}. Showing weather directly.")
        await state.update_data(preferred_city=preferred_city)
        await _get_and_show_weather(target, state, session, user_city_input=preferred_city, is_preferred=True)
    else:
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        text = "🌍 Будь ласка, введіть назву міста:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
             if isinstance(target, CallbackQuery): await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
             else: await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
             logger.error(f"Error editing/sending message in weather_entry_point: {e}")
             await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_city)


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    """ Handles user's city name input. """
    user_city_input = message.text.strip()
    # Check if user already has a preferred city (for the is_preferred flag)
    db_user = await session.get(User, message.from_user.id)
    preferred_city = db_user.preferred_city if db_user else None
    is_preferred = (preferred_city is not None and preferred_city.lower() == user_city_input.lower())
    await _get_and_show_weather(message, state, session, user_city_input=user_city_input, is_preferred=is_preferred)


@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY)
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    """ Handles 'Інше місто' button after weather is shown. """
    logger.info(f"User {callback.from_user.id} requested OTHER city from weather view.")
    await callback.message.edit_text("🌍 Будь ласка, введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.answer()

@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH)
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Handles 'Оновити' button after weather is shown. """
    user_data = await state.get_data()
    current_city = user_data.get("current_shown_city") # Use the city that was just shown
    preferred_city = user_data.get("preferred_city") # Get potentially saved preferred city from state
    user_id = callback.from_user.id

    if current_city:
        logger.info(f"User {user_id} requested REFRESH for city: {current_city}")
        is_preferred_city = (preferred_city is not None and preferred_city.lower() == current_city.lower())
        await _get_and_show_weather(callback, state, session, user_city_input=current_city, is_preferred=is_preferred_city)
    else:
        logger.warning(f"User {user_id} requested REFRESH, but no city found in state.")
        await callback.message.edit_text("Не вдалося визначити місто для оновлення. Введіть назву:", reply_markup=get_weather_enter_city_back_keyboard())
        await state.set_state(WeatherStates.waiting_for_city)
        await callback.answer("Не вдалося оновити.", show_alert=True)


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    """ Handles 'Yes' to save city. """
    user_data = await state.get_data()
    city_to_save_in_db = user_data.get("city_to_save")
    city_display_name = user_data.get("city_display_name")
    user_id = callback.from_user.id

    if not city_to_save_in_db or not city_display_name:
        logger.error(f"Cannot save city for user {user_id}: city name not found in state.")
        await state.clear()
        from src.handlers.utils import show_main_menu_message # Import inside function
        await show_main_menu_message(callback, "Помилка: не вдалося отримати назву міста для збереження.")
        return

    db_user = await session.get(User, user_id)
    if db_user:
         try:
            db_user.preferred_city = city_to_save_in_db
            session.add(db_user)
            await session.commit() # Keep explicit commit for reliability
            logger.info(f"User {user_id} saved city to DB: {city_to_save_in_db}. Explicit commit executed.")
            text = f"✅ Місто <b>{city_display_name}</b> збережено як основне."
            reply_markup = get_weather_actions_keyboard() # Show actions keyboard
            await callback.message.edit_text(text, reply_markup=reply_markup)
         except Exception as e:
             logger.exception(f"Database error while saving city for user {user_id}: {e}")
             await session.rollback()
             await callback.message.edit_text("😥 Виникла помилка при збереженні міста.")
    else:
         logger.error(f"Cannot save city for user {user_id}: user not found in DB.")
         await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження міста.")

    # Clear state ONLY AFTER successful save or handling DB error
    # Keep current_shown_city for potential refresh? Or clear? Let's clear for now.
    await state.clear()
    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    """ Handles 'No' to save city. """
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    user_data = await state.get_data()
    city_display_name = user_data.get("city_display_name", "місто")
    weather_part = callback.message.text.split('\n\n')[0] # Get weather part
    text = f"{weather_part}\n\n(Місто <b>{city_display_name}</b> не збережено)"
    reply_markup = get_weather_actions_keyboard() # Show actions keyboard
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await state.clear()
    await callback.answer()


@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN)
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    """ Handles 'Back' button from the enter city screen. """
    # Import inside function to break circular import
    from src.handlers.utils import show_main_menu_message
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather input.")
    await state.clear()
    await show_main_menu_message(callback)