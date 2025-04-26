# src/modules/weather/handlers.py

import logging
from typing import Union # Для аннотаций Union[Message, CallbackQuery]

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

# Импортируем функции из других модулей проекта
from src.keyboards.inline_main import CALLBACK_WEATHER
from src.handlers.common import show_main_menu
from src.db.models import User # Модель пользователя
from .service import get_weather_data, format_weather_message # Сервис погоды
from .keyboard import ( # Клавиатуры погоды
    get_weather_back_keyboard, CALLBACK_WEATHER_BACK,
    get_city_confirmation_keyboard, CALLBACK_WEATHER_USE_SAVED, CALLBACK_WEATHER_OTHER_CITY,
    get_save_city_keyboard, CALLBACK_WEATHER_SAVE_CITY_YES, CALLBACK_WEATHER_SAVE_CITY_NO
)

logger = logging.getLogger(__name__)

# Создаем роутер для этого модуля
router = Router(name="weather-module")

# Определяем состояния FSM для диалога погоды
class WeatherStates(StatesGroup):
    waiting_for_confirmation = State() # Ожидание подтверждения (Да/Інше місто)
    waiting_for_city = State()         # Ожидание названия города
    waiting_for_save_decision = State() # Ожидание решения о сохранении (Так/Ні)

# --- Вспомогательная функция для получения погоды и отображения ---

async def _get_and_show_weather(target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, city_name: str):
    """
    Получает погоду, отображает результат и предлагает сохранить город.
    target: Объект Message или CallbackQuery, куда/относительно которого отвечать.
    state: Контекст FSM.
    session: Сессия БД.
    city_name: Название города для запроса.
    """
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


# --- Обработчики основного потока ---

@router.callback_query(F.data == CALLBACK_WEATHER)
async def handle_weather_entry(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    # Используем session.get для получения пользователя (более прямой способ по PK)
    db_user = await session.get(User, user_id)
    # Важно обновить объект в сессии, чтобы получить актуальные данные, если они изменились извне
    # В нашем случае это не критично, но полезно знать: await session.refresh(db_user)

    if db_user and db_user.preferred_city:
        logger.info(f"User {user_id} has preferred city: {db_user.preferred_city}")
        await state.update_data(preferred_city=db_user.preferred_city)
        text = f"Ваше збережене місто: <b>{db_user.preferred_city}</b>.\nПоказати погоду для нього?"
        reply_markup = get_city_confirmation_keyboard()
        await callback.message.edit_text(text, reply_markup=reply_markup)
        await state.set_state(WeatherStates.waiting_for_confirmation)
    else:
        # Логируем, даже если пользователь есть, но города нет
        log_msg = f"User {user_id}" + ("" if db_user else " (just created?)") + " has no preferred city. Asking for input."
        logger.info(log_msg)
        await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
        await state.set_state(WeatherStates.waiting_for_city)

    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_confirmation, F.data == CALLBACK_WEATHER_USE_SAVED)
async def handle_use_saved_city(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
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
    logger.info(f"User {callback.from_user.id} chose to enter another city.")
    await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
    await state.set_state(WeatherStates.waiting_for_city)
    await callback.answer()


@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext, session: AsyncSession):
    city_name = message.text.strip()
    await _get_and_show_weather(message, state, session, city_name)


# --- Обработчики сохранения города ---

@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_YES)
async def handle_save_city_yes(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
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
        try: # Добавим try/except для коммита
            db_user.preferred_city = city_to_save
            session.add(db_user)
            # !!! Добавляем явный коммит ЗДЕСЬ !!!
            await session.commit()
            logger.info(f"User {user_id} saved city: {city_to_save}. Explicit commit executed.")

            # Редактируем сообщение, подтверждая сохранение
            text = f"✅ Місто <b>{city_to_save}</b> збережено як основне.\n\n" + callback.message.text.split('\n\n')[0]
            reply_markup = get_weather_back_keyboard()
            await callback.message.edit_text(text, reply_markup=reply_markup)

        except Exception as e:
            logger.exception(f"Database error while saving city for user {user_id}: {e}")
            await callback.message.edit_text("😥 Виникла помилка при збереженні міста.")
            # await session.rollback() # Middleware должен сделать роллбэк
    else:
        logger.error(f"Cannot save city for user {user_id}: user not found in DB.")
        await callback.message.edit_text("Помилка: не вдалося знайти ваші дані для збереження міста.")

    await state.clear()
    await callback.answer()


@router.callback_query(WeatherStates.waiting_for_save_decision, F.data == CALLBACK_WEATHER_SAVE_CITY_NO)
async def handle_save_city_no(callback: CallbackQuery, state: FSMContext):
    logger.info(f"User {callback.from_user.id} chose not to save the city.")
    text = callback.message.text.split('\n\n')[0]
    reply_markup = get_weather_back_keyboard()
    await callback.message.edit_text(text, reply_markup=reply_markup)
    await state.clear()
    await callback.answer()


# --- Обработчик кнопки "Назад" ---

@router.callback_query(F.data == CALLBACK_WEATHER_BACK)
async def handle_weather_back(callback: CallbackQuery, state: FSMContext):
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather.")
    await state.clear()
    await show_main_menu(callback)

# --- Конец обработчиков ---