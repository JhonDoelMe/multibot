# src/modules/weather/handlers.py

import logging
import re
from typing import Union, Optional, Dict, Any
from aiogram import Bot, Router, F
# StateFilter не використовується напряму в декораторах, F.state є кращим варіантом
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup # StatesGroup вже був тут

from sqlalchemy.ext.asyncio import AsyncSession

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
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="weather-module")

class WeatherStates(StatesGroup):
    waiting_for_city = State()
    waiting_for_save_decision = State()
    showing_weather = State() # Додатковий стан для позначення, що погода показана (не для збереження)
    showing_forecast = State() # Додатковий стан для прогнозу


async def _get_and_show_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    city_input: Optional[str] = None,
    coords: Optional[Dict[str, float]] = None
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    answered_callback = False # Для відстеження відповіді на колбек

    request_details_log = f"city '{city_input}'" if city_input else f"coords {coords}"
    logger.info(f"_get_and_show_weather: User {user_id}, request: {request_details_log}")

    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e:
            logger.warning(f"Could not answer callback immediately in _get_and_show_weather for user {user_id}: {e}")
    
    try:
        action_text = "🔍 Отримую дані про погоду..."
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
        elif hasattr(target, 'location') and target.location: # Для повідомлень з геолокацією
             status_message = await target.answer(action_text)
        else: # Для звичайних текстових повідомлень
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.warning(f"Could not send/edit 'loading' status message for weather, user {user_id}: {e}")

    # Отримання даних з сервісу
    weather_api_response: Dict[str, Any]
    is_coords_request_flag = False

    if coords:
        is_coords_request_flag = True
        weather_api_response = await get_weather_data_by_coords(bot, coords['lat'], coords['lon'])
    elif city_input:
        weather_api_response = await get_weather_data(bot, city_input)
    else:
        logger.error(f"No city_input or coords provided for user {user_id} in _get_and_show_weather.")
        error_text = "Помилка: Не вказано місто або координати для запиту погоди."
        # Спроба повідомити користувача про помилку
        target_msg_for_error = status_message if status_message else message_to_edit_or_answer
        try:
            if status_message: await target_msg_for_error.edit_text(error_text)
            else: await target_msg_for_error.answer(error_text)
        except Exception as e_send: logger.error(f"Failed to send 'no city/coords' error: {e_send}")
        await state.set_state(None) # Скидаємо стан FSM
        return

    # Визначаємо повідомлення для редагування/відповіді з результатом
    final_target_message = status_message if status_message else message_to_edit_or_answer

    # Обробка відповіді API
    if weather_api_response.get("status") == "error" or str(weather_api_response.get("cod")) != "200":
        # Помилка від API або наша внутрішня помилка сервісу
        # format_weather_message вже вміє обробляти такі відповіді
        error_display_name = city_input if city_input else ("ваші координати" if coords else "вказана локація")
        weather_message_text = format_weather_message(weather_api_response, error_display_name, is_coords_request_flag)
        reply_markup = get_weather_enter_city_back_keyboard() # Кнопка "Назад"
        try:
            if status_message: await final_target_message.edit_text(weather_message_text, reply_markup=reply_markup)
            else: await message_to_edit_or_answer.answer(weather_message_text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit/send weather API error message: {e_edit}")
        await state.set_state(WeatherStates.waiting_for_city) # Повертаємо до стану введення міста
        logger.warning(f"API error for weather request {request_details_log} for user {user_id}. Response: {weather_api_response}")
        return

    # Успішна відповідь від API
    weather_data = weather_api_response # Тепер це дані без обгортки status/data
    
    api_city_name = weather_data.get("name") # Ім'я міста, яке повернуло API
    city_to_save_in_db = api_city_name if api_city_name and not is_coords_request_flag else None # Зберігаємо тільки якщо вводили назву і API її підтвердило

    # Визначаємо ім'я для відображення користувачу
    city_display_name_for_user_message: str
    if is_coords_request_flag:
        city_display_name_for_user_message = api_city_name if api_city_name else city_input if city_input else "ваші координати"
    else: # Запит за назвою міста
        city_display_name_for_user_message = api_city_name if api_city_name else city_input # Пріоритет імені від API

    logger.info(f"User {user_id}: API city name='{api_city_name}', display name='{city_display_name_for_user_message}', to_save='{city_to_save_in_db}'")

    weather_message_text = format_weather_message(weather_data, city_display_name_for_user_message, is_coords_request_flag)

    # Оновлюємо дані FSM для кнопки "Оновити" та "Прогноз"
    # `current_shown_city` - це те, що треба передавати API при оновленні (назва міста або координати)
    # `city_display_name` - те, що бачить користувач у заголовках/запитах на збереження
    fsm_update_data = {
        "current_shown_city_api": api_city_name if api_city_name else (f"{coords['lat']},{coords['lon']}" if coords else city_input), # Для запитів до API
        "city_display_name_user": city_display_name_for_user_message, # Для відображення користувачу
        "city_to_save_confirmed": city_to_save_in_db, # Підтверджене API ім'я для збереження
        "is_coords_request_fsm": is_coords_request_flag
    }
    await state.update_data(**fsm_update_data)
    logger.debug(f"User {user_id}: Updated FSM data: {fsm_update_data}")

    # Перевірка, чи потрібно пропонувати зберегти місто
    ask_to_save = False
    db_user = await session.get(User, user_id)
    preferred_city_from_db = db_user.preferred_city if db_user else None

    if city_to_save_in_db and (not preferred_city_from_db or preferred_city_from_db.lower() != city_to_save_in_db.lower()):
        ask_to_save = True

    reply_markup = None
    if ask_to_save:
        save_prompt_city_name = city_to_save_in_db.capitalize()
        weather_message_text += f"\n\n💾 Зберегти <b>{save_prompt_city_name}</b> як основне місто?"
        reply_markup = get_save_city_keyboard()
        await state.set_state(WeatherStates.waiting_for_save_decision)
        logger.info(f"User {user_id}: Asking to save '{save_prompt_city_name}'. Set FSM to waiting_for_save_decision.")
    else:
        reply_markup = get_weather_actions_keyboard()
        await state.set_state(WeatherStates.showing_weather) # Переходимо в стан показу погоди
        logger.info(f"User {user_id}: Weather shown (city '{city_display_name_for_user_message}' is preferred or from geo/no save needed). Set FSM to showing_weather.")

    try:
        if status_message: await final_target_message.edit_text(weather_message_text, reply_markup=reply_markup)
        else: await message_to_edit_or_answer.answer(weather_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Successfully sent/edited weather message for {request_details_log}.")
    except Exception as e_send_final:
        logger.error(f"Failed to send/edit final weather message for {request_details_log}: {e_send_final}")
        # Якщо не вдалося відправити основне повідомлення, спробувати хоча б помилку, якщо це була вона
        if weather_api_response.get("status") == "error":
             try: await message_to_edit_or_answer.answer("Помилка отримання погоди. Спробуйте пізніше.")
             except: pass # Остання спроба
    finally:
        if isinstance(target, CallbackQuery) and not answered_callback:
            try: await target.answer()
            except Exception: logger.warning(f"Final attempt to answer weather callback for user {user_id} failed.")


async def weather_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_entry_point.")
    
    current_fsm_state_name = await state.get_state()
    if current_fsm_state_name not in [None, WeatherStates.waiting_for_city.state, WeatherStates.showing_weather.state, WeatherStates.showing_forecast.state, WeatherStates.waiting_for_save_decision.state]:
        logger.info(f"User {user_id}: In an unrelated FSM state ({current_fsm_state_name}), clearing state before weather module.")
        await state.clear() # Повне очищення, якщо стан з іншого модуля
    elif current_fsm_state_name is None: # Якщо стан не встановлено
        await state.set_data({}) # Очищаємо тільки дані, якщо стан вже None

    answered_callback = False
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e: logger.warning(f"Could not answer callback in weather_entry_point: {e}")

    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    db_user = await session.get(User, user_id)
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
            if isinstance(target, CallbackQuery):
                # Якщо це колбек (наприклад, з головного меню), редагуємо повідомлення
                await message_to_edit_or_answer.edit_text(text, reply_markup=reply_markup)
            else: # Якщо це повідомлення (наприклад, команда /weather)
                await message_to_edit_or_answer.answer(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending/editing message in weather_entry_point (ask for city): {e}")
            if isinstance(target, CallbackQuery): # Якщо редагування не вдалося, спробуємо відправити нове
                try: await target.message.answer(text,reply_markup=reply_markup)
                except Exception as e2: logger.error(f"Fallback send message also failed in weather_entry_point: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)
        logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city.")
    
    if isinstance(target, CallbackQuery) and not answered_callback: # Остання спроба відповісти на колбек
        try: await target.answer()
        except: pass


@router.message(WeatherStates.waiting_for_city, F.location)
async def handle_location_when_waiting(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: handle_location_when_waiting for user {user_id}: lat={lat}, lon={lon}")
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: handle_location_when_waiting called without message.location.")
        try: await message.reply("Не вдалося отримати вашу геолокацію. Спробуйте ще раз.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' message: {e}")

async def process_main_geolocation_button(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    # Ця функція викликається з common_handlers.handle_any_geolocation
    # common_handlers вже мав би встановити state в None, якщо потрібно було вийти з іншого стану.
    if message.location:
        lat = message.location.latitude
        lon = message.location.longitude
        user_id = message.from_user.id
        logger.info(f"MAIN weather module: process_main_geolocation_button for user {user_id}: lat={lat}, lon={lon}")
        await _get_and_show_weather(bot, message, state, session, coords={"lat": lat, "lon": lon})
    else:
        logger.warning(f"User {message.from_user.id}: process_main_geolocation_button called without message.location.")
        try: await message.reply("Не вдалося отримати вашу геолокацію для погоди.")
        except Exception as e: logger.error(f"Error sending 'cannot get location' (from button): {e}")


@router.message(WeatherStates.waiting_for_city, F.text)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_city_input = message.text.strip() if message.text else ""
    user_id = message.from_user.id
    logger.info(f"handle_city_input: User {user_id} entered city '{user_city_input}'. Current FSM state: {await state.get_state()}")
    
    if not user_city_input:
        try: await message.answer("😔 Будь ласка, введіть назву міста (текст не може бути порожнім).", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending empty city input message: {e}")
        return
    if len(user_city_input) > 100:
        try: await message.answer("😔 Назва міста занадто довга (максимум 100 символів). Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending city name too long message: {e}")
        return
    # Дозволяємо цифри в назві міста (наприклад, для деяких міст або районів)
    if not re.match(r"^[A-Za-zА-Яа-яЁёІіЇїЄє\s\-\.\'\d]+$", user_city_input):
        try: await message.answer("😔 Назва міста може містити лише літери, цифри, пробіли, дефіси, апострофи та крапки. Спробуйте ще раз.", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e: logger.error(f"Error sending invalid city name chars message: {e}")
        return
        
    await _get_and_show_weather(bot, message, state, session, city_input=user_city_input)


@router.callback_query(F.data == CALLBACK_WEATHER_OTHER_CITY, WeatherStates.showing_weather) # Тільки зі стану показу погоди
async def handle_action_other_city(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    logger.info(f"User {user_id} requested OTHER city from showing_weather state. Current FSM data: {await state.get_data()}")
    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_other_city: {e}")
    
    try:
        await callback.message.edit_text("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
    except Exception as e:
        logger.error(f"Failed to edit message for 'other city' input: {e}")
        try: # Fallback
            await callback.message.answer("🌍 Введіть назву іншого міста:", reply_markup=get_weather_enter_city_back_keyboard())
        except Exception as e2: logger.error(f"Failed to send new message for 'other city' input either: {e2}")
    
    await state.set_state(WeatherStates.waiting_for_city)
    logger.info(f"User {user_id}: Set FSM state to WeatherStates.waiting_for_city (from Other City callback).")
    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_REFRESH, WeatherStates.showing_weather) # Тільки зі стану показу погоди
async def handle_action_refresh(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested REFRESH (main weather). FSM state: {await state.get_state()}, FSM data: {user_fsm_data}")
    
    # Використовуємо "current_shown_city_api" для запиту до API
    # Це може бути назва міста, підтверджена API, або рядок "lat,lon"
    api_request_location = user_fsm_data.get("current_shown_city_api")
    is_coords = user_fsm_data.get("is_coords_request_fsm", False)

    answered_callback = False
    try:
        await callback.answer("Оновлюю дані...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_action_refresh: {e}")

    if api_request_location:
        logger.info(f"User {user_id} refreshing main weather for API location: '{api_request_location}', is_coords={is_coords}")
        if is_coords and isinstance(api_request_location, str) and ',' in api_request_location:
            try:
                lat_str, lon_str = api_request_location.split(',')
                coords_for_refresh = {"lat": float(lat_str), "lon": float(lon_str)}
                await _get_and_show_weather(bot, callback, state, session, coords=coords_for_refresh)
            except ValueError:
                logger.error(f"User {user_id}: Could not parse coords '{api_request_location}' from FSM for refresh.")
                # Подальша обробка помилки (запит міста) нижче
                api_request_location = None # Скидаємо, щоб перейти до логіки "не вдалося визначити"
        elif not is_coords: # Якщо це назва міста
            await _get_and_show_weather(bot, callback, state, session, city_input=api_request_location)
        else: # Некоректні дані в FSM
            logger.warning(f"User {user_id}: Inconsistent FSM data for refresh. is_coords={is_coords}, but api_request_location='{api_request_location}'.")
            api_request_location = None # Скидаємо
    
    if not api_request_location: # Якщо не вдалося визначити місто/координати з FSM
        logger.warning(f"User {user_id}: No valid location found in FSM for refresh. Asking to input city.")
        error_text = "😔 Не вдалося визначити дані для оновлення. Будь ласка, введіть місто:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Failed to edit message after refresh failure: {e}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e2: logger.error(f"Failed to send new message after refresh failure either: {e2}")
        await state.set_state(WeatherStates.waiting_for_city)

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_YES, WeatherStates.waiting_for_save_decision)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose YES to save city. FSM data: {user_fsm_data}")

    # Використовуємо "city_to_save_confirmed" - ім'я, підтверджене API
    city_to_actually_save_in_db = user_fsm_data.get("city_to_save_confirmed")
    # Для відображення користувачу беремо "city_display_name_user"
    city_name_user_saw_in_prompt = user_fsm_data.get("city_display_name_user", city_to_actually_save_in_db)


    answered_callback = False
    try:
        await callback.answer("Зберігаю місто...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_yes: {e}")

    final_text = ""
    final_markup = get_weather_actions_keyboard() # Готуємо клавіатуру для дій після збереження

    if not city_to_actually_save_in_db:
        logger.error(f"User {user_id}: 'city_to_save_confirmed' is missing in FSM data. Cannot save. Data: {user_fsm_data}")
        final_text = "Помилка: не вдалося визначити місто для збереження."
        await state.set_state(WeatherStates.showing_weather) # Або None, залежно від бажаної поведінки
    else:
        db_user = await session.get(User, user_id)
        if db_user:
            try:
                old_preferred_city = db_user.preferred_city
                db_user.preferred_city = city_to_actually_save_in_db
                session.add(db_user)
                # Комміт буде виконаний DbSessionMiddleware (або await session.commit() якщо middleware не використовується для commit)
                logger.info(f"User {user_id}: Preferred city set to '{city_to_actually_save_in_db}' (was '{old_preferred_city}'). User saw prompt for '{city_name_user_saw_in_prompt}'.")
                final_text = f"✅ Місто <b>{city_name_user_saw_in_prompt}</b> збережено як основне."
                # Оновлюємо дані FSM, щоб відображати, що місто збережене
                await state.update_data(preferred_city_from_db_fsm=city_to_actually_save_in_db)
                await state.set_state(WeatherStates.showing_weather) # Переходимо в стан показу погоди
            except Exception as e_db:
                logger.exception(f"User {user_id}: DB error while saving preferred city '{city_to_actually_save_in_db}': {e_db}", exc_info=True)
                await session.rollback()
                final_text = "😥 Виникла помилка під час збереження міста."
                await state.set_state(WeatherStates.showing_weather) # Або None
        else:
            logger.error(f"User {user_id} not found in DB during save city operation.")
            final_text = "Помилка: не вдалося знайти ваші дані для збереження міста."
            await state.set_state(None) # Скидаємо стан, бо щось пішло не так

    try:
        await callback.message.edit_text(final_text, reply_markup=final_markup)
    except Exception as e_edit:
        logger.error(f"Failed to edit message after save city (YES) decision: {e_edit}")
        try: await callback.message.answer(final_text, reply_markup=final_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after save city (YES) decision: {e_ans}")

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SAVE_CITY_NO, WeatherStates.waiting_for_save_decision)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} chose NOT to save city. FSM data: {user_fsm_data}")
    
    city_display_name_from_prompt = user_fsm_data.get("city_display_name_user", "поточне місто")
    
    # Відновлюємо текст погоди без запиту на збереження
    # Потрібно мати вихідний текст погоди в FSM або переформатувати його.
    # Простіший варіант - просто повідомити, що не збережено, і показати кнопки дій.
    # Або, якщо текст повідомлення доступний:
    original_weather_message_parts = callback.message.text.split('\n\n💾 Зберегти', 1)
    weather_part = original_weather_message_parts[0] if original_weather_message_parts else "Дані про погоду"
    
    text_after_no_save = f"{weather_part}\n\n(Місто <b>{city_display_name_from_prompt}</b> не було збережено як основне)"

    answered_callback = False
    try:
        await callback.answer("Місто не збережено.")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_save_city_no: {e}")

    reply_markup = get_weather_actions_keyboard()
    try:
        await callback.message.edit_text(text_after_no_save, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Failed to edit message after user chose NOT to save city: {e_edit}")
        try: await callback.message.answer(text_after_no_save, reply_markup=reply_markup)
        except Exception as e_ans: logger.error(f"Failed to send new message after user chose NOT to save city: {e_ans}")

    await state.set_state(WeatherStates.showing_weather) # Переходимо в стан показу погоди
    logger.info(f"User {user_id}: City not saved. Set FSM state to showing_weather.")
    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_FORECAST_5D, WeatherStates.showing_weather)
async def handle_forecast_request(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): # session може не знадобитися
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested 5-day FORECAST. FSM state: {await state.get_state()}, FSM data: {user_fsm_data}")

    # Для запиту до API прогнозу використовуємо "current_shown_city_api"
    city_name_for_api_request = user_fsm_data.get("current_shown_city_api")
    # Для заголовка прогнозу використовуємо "city_display_name_user"
    display_name_for_forecast_header = user_fsm_data.get("city_display_name_user", city_name_for_api_request)

    answered_callback = False
    status_message = None

    if not city_name_for_api_request:
        logger.warning(f"User {user_id} requested forecast, but 'current_shown_city_api' not found. Data: {user_fsm_data}")
        try:
            await callback.answer("Помилка: не вдалося визначити місто для прогнозу. Спробуйте отримати погоду знову.", show_alert=True)
            answered_callback = True
        except Exception as e: logger.warning(f"Could not answer callback (no city for forecast): {e}")
        return

    try:
        await callback.answer("Отримую прогноз на 5 днів...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_forecast_request: {e}")

    try:
        status_message = await callback.message.edit_text(f"⏳ Отримую прогноз для: <b>{display_name_for_forecast_header}</b>...")
    except Exception as e_edit_status:
        logger.warning(f"Failed to edit message for forecast status: {e_edit_status}")

    final_target_message = status_message if status_message else callback.message
    forecast_api_response = await get_5day_forecast(bot, city_name_for_api_request)
    
    # format_forecast_message вже обробляє помилки з forecast_api_response
    message_text = format_forecast_message(forecast_api_response, display_name_for_forecast_header)
    reply_markup = get_forecast_keyboard() # Клавіатура "Назад до поточної погоди"

    try:
        if status_message: await final_target_message.edit_text(message_text, reply_markup=reply_markup)
        else: await callback.message.answer(message_text, reply_markup=reply_markup) # Якщо не вдалося змінити статус
        logger.info(f"User {user_id}: Sent 5-day forecast for API city '{city_name_for_api_request}' (display: '{display_name_for_forecast_header}').")
        await state.set_state(WeatherStates.showing_forecast) # Встановлюємо стан показу прогнозу
    except Exception as e_edit_final:
        logger.error(f"Failed to edit/send final forecast message: {e_edit_final}")
        # Якщо була помилка API, format_forecast_message вже повернув текст помилки
        # Тут можна спробувати відправити його ще раз, якщо edit_text не спрацював
        if forecast_api_response.get("status") == "error" and not status_message:
            try: await callback.message.answer(message_text, reply_markup=get_weather_actions_keyboard()) # Повертаємо кнопки дій
            except: pass

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_SHOW_CURRENT, WeatherStates.showing_forecast) # Зі стану показу прогнозу
async def handle_show_current_weather(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    logger.info(f"User {user_id} requested to show CURRENT weather again (from forecast view). FSM data: {user_fsm_data}")

    api_request_location = user_fsm_data.get("current_shown_city_api")
    is_coords = user_fsm_data.get("is_coords_request_fsm", False)
    
    answered_callback = False
    try:
        await callback.answer("Показую поточну погоду...")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in handle_show_current_weather: {e}")

    if api_request_location:
        if is_coords and isinstance(api_request_location, str) and ',' in api_request_location:
            try:
                lat_str, lon_str = api_request_location.split(',')
                coords_to_show = {"lat": float(lat_str), "lon": float(lon_str)}
                await _get_and_show_weather(bot, callback, state, session, coords=coords_to_show)
            except ValueError:
                logger.error(f"User {user_id}: Could not parse coords '{api_request_location}' from FSM for show_current.")
                api_request_location = None # Для переходу до блоку помилки
        elif not is_coords:
            await _get_and_show_weather(bot, callback, state, session, city_input=api_request_location)
        else:
             api_request_location = None # Некоректні дані
    
    if not api_request_location: # Якщо не вдалося визначити
        logger.warning(f"User {user_id}: No valid location in FSM to show current weather from forecast. Asking to input city.")
        error_text = "🌍 Будь ласка, введіть назву міста:"
        reply_markup = get_weather_enter_city_back_keyboard()
        try:
            await callback.message.edit_text(error_text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Failed to edit message after show current failure: {e_edit}")
            try: await callback.message.answer(error_text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Failed to send new message after show current failure: {e_ans}")
        await state.set_state(WeatherStates.waiting_for_city)

    if not answered_callback:
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CALLBACK_WEATHER_BACK_TO_MAIN, WeatherStates.waiting_for_city) # Тільки зі стану введення міста
async def handle_weather_back_to_main(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    current_fsm_state = await state.get_state()
    logger.info(f"User {user_id} requested back to main menu from weather module (state: {current_fsm_state}). Setting FSM state to None.")
    await state.set_state(None) # Скидаємо стан модуля погоди
    # await state.clear() # Якщо потрібно очистити і дані стану
    await show_main_menu_message(callback) # show_main_menu_message вже робить callback.answer()