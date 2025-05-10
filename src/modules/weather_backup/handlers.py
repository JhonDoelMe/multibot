# src/modules/weather_backup/handlers.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User # Для получения сохраненного города
from .service import (
    get_current_weather_weatherapi,
    format_weather_backup_message,
    get_forecast_weatherapi,
    format_forecast_backup_message
)
from .keyboard import (
    get_current_weather_backup_keyboard,
    get_forecast_weather_backup_keyboard,
    CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT,
    CALLBACK_WEATHER_BACKUP_SHOW_FORECAST,
    CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST,
    CALLBACK_WEATHER_BACKUP_SHOW_CURRENT
)
# Для возврата в главное меню и клавиатуры ввода города из основного модуля (если решим использовать)
from src.handlers.utils import show_main_menu_message
from src.modules.weather.keyboard import get_weather_enter_city_back_keyboard # Пример
from src.modules.weather.handlers import WeatherStates as MainWeatherStates # Если будем читать состояние из основного модуля

logger = logging.getLogger(__name__)
router = Router(name="weather-backup-module")

# Состояния для этого модуля (если понадобятся для ввода города)
class WeatherBackupStates(StatesGroup):
    waiting_for_location = State() # Ожидание ввода города/координат для резервного сервиса
    showing_current = State()      # Показываем текущую резервную погоду
    showing_forecast = State()     # Показываем резервный прогноз


async def _fetch_and_show_backup_weather(
    bot: Bot,
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    session: AsyncSession,
    location_input: str, # Город или "lat,lon"
    show_forecast: bool = False
):
    user_id = target.from_user.id
    message_to_edit_or_answer = target.message if isinstance(target, CallbackQuery) else target
    status_message = None
    action_text = "⏳ Отримую резервні дані..."
    if show_forecast:
        action_text = "⏳ Отримую резервний прогноз..."

    try:
        if isinstance(target, CallbackQuery):
            status_message = await message_to_edit_or_answer.edit_text(action_text)
            await target.answer()
        else:
            status_message = await target.answer(action_text)
    except Exception as e:
        logger.error(f"Error sending/editing status message for backup weather: {e}")
        status_message = message_to_edit_or_answer

    final_target_message = status_message if status_message else message_to_edit_or_answer
    
    api_response_data = None
    formatted_message_text = ""
    reply_markup = None

    if show_forecast:
        api_response_data = await get_forecast_weatherapi(bot, location=location_input, days=3)
        formatted_message_text = format_forecast_backup_message(api_response_data, requested_location=location_input)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_forecast_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_forecast)
        # Если ошибка, клавиатура по умолчанию (или никакая) будет установлена ниже
    else: # Показываем текущую погоду
        api_response_data = await get_current_weather_weatherapi(bot, location=location_input)
        formatted_message_text = format_weather_backup_message(api_response_data, requested_location=location_input)
        if api_response_data and "error" not in api_response_data:
            reply_markup = get_current_weather_backup_keyboard()
            await state.set_state(WeatherBackupStates.showing_current)

    # Если была ошибка API и reply_markup не установлен, можно поставить клавиатуру для повторного ввода или возврата
    if api_response_data and "error" in api_response_data and not reply_markup:
        # Можно добавить кнопку "Повторити" или "Ввести інше місто (резерв)"
        # Пока просто сообщение без кнопок или можно get_weather_enter_city_back_keyboard() из основного модуля
        pass


    try:
        await final_target_message.edit_text(formatted_message_text, reply_markup=reply_markup)
        logger.info(f"User {user_id}: Sent backup weather/forecast for location '{location_input}'.")
        # Сохраняем использованный location_input в состояние для кнопки "Обновить"
        await state.update_data(current_backup_location=location_input)
    except Exception as e:
        logger.error(f"Error editing final message for backup weather: {e}")
        try:
            await message_to_edit_or_answer.answer(formatted_message_text, reply_markup=reply_markup)
        except Exception as e2:
            logger.error(f"Error sending new final message for backup weather: {e2}")


# Точка входа для резервной погоды
async def weather_backup_entry_point(
    target: Union[Message, CallbackQuery], state: FSMContext, session: AsyncSession, bot: Bot
):
    user_id = target.from_user.id
    logger.info(f"User {user_id} initiated weather_backup_entry_point.")
    
    # Попробуем получить город из состояния основного модуля погоды или из БД
    location_to_use: Optional[str] = None
    
    # 1. Попробовать взять из состояния основного модуля (если пользователь только что смотрел погоду там)
    main_weather_fsm_data = await state.get_data() # Читаем данные из текущего контекста FSM
    # Если мы хотим читать состояние ДРУГОГО FSM (например, WeatherStates), это сложнее и не рекомендуется напрямую.
    # Вместо этого, `current_shown_city` из основного модуля должен был бы быть сохранен в `user_data` на более высоком уровне,
    # или мы запрашиваем город заново для резервного сервиса.

    # Для простоты, сначала используем сохраненный город пользователя.
    db_user = await session.get(User, user_id)
    if db_user and db_user.preferred_city:
        location_to_use = db_user.preferred_city
        logger.info(f"User {user_id}: Using preferred city '{location_to_use}' for backup weather.")
    
    # Если preferred_city нет, можно попытаться взять город, который пользователь смотрел в основном модуле.
    # Это потребует, чтобы основной модуль сохранял `current_shown_city` в user_data FSM,
    # а не только в своем состоянии. Либо мы можем передать его как параметр.

    # Пока что, если нет preferred_city, будем запрашивать.
    if location_to_use:
        await state.set_state(WeatherBackupStates.showing_current) # Устанавливаем начальное состояние для этого модуля
        await _fetch_and_show_backup_weather(bot, target, state, session, location_input=location_to_use, show_forecast=False)
    else:
        logger.info(f"User {user_id}: No preferred city for backup weather. Asking for location.")
        if isinstance(target, CallbackQuery): await target.answer()
        target_message = target.message if isinstance(target, CallbackQuery) else target
        await target_message.answer( # Отправляем новое сообщение с запросом
            "Будь ласка, введіть назву міста (або 'lat,lon') для резервного сервісу погоди:",
            # reply_markup=get_weather_enter_city_back_keyboard() # Можно использовать клавиатуру из основного модуля
        )
        await state.set_state(WeatherBackupStates.waiting_for_location)

@router.message(WeatherBackupStates.waiting_for_location)
async def handle_backup_location_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    location_input = message.text.strip() if message.text else ""
    logger.info(f"User {user_id} entered location '{location_input}' for backup weather.")

    if not location_input:
        await message.answer("Назва міста або координати не можуть бути порожніми. Спробуйте ще раз.")
        return # Остаемся в состоянии waiting_for_location

    # Здесь можно добавить валидацию для location_input, если нужно
    
    await _fetch_and_show_backup_weather(bot, message, state, session, location_input=location_input, show_forecast=False)


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_CURRENT, WeatherBackupStates.showing_current)
async def handle_refresh_current_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    logger.info(f"User {user_id} refreshing current backup weather for location: '{location}'.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False)
    else:
        logger.warning(f"User {user_id}: No location found in state for refreshing current backup weather.")
        await callback.answer("Не вдалося знайти місто для оновлення.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location) # Предложить ввести заново
        await callback.message.edit_text("Будь ласка, введіть місто для резервної погоди:")


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_FORECAST, WeatherBackupStates.showing_current)
async def handle_show_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    logger.info(f"User {user_id} requesting backup forecast for location: '{location}'.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True)
    else:
        logger.warning(f"User {user_id}: No location found in state for backup forecast.")
        await callback.answer("Не вдалося знайти місто для прогнозу.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто для резервного прогнозу:")


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_REFRESH_FORECAST, WeatherBackupStates.showing_forecast)
async def handle_refresh_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    logger.info(f"User {user_id} refreshing backup forecast for location: '{location}'.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=True)
    else:
        logger.warning(f"User {user_id}: No location found in state for refreshing backup forecast.")
        await callback.answer("Не вдалося знайти місто для оновлення прогнозу.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто для резервного прогнозу:")


@router.callback_query(F.data == CALLBACK_WEATHER_BACKUP_SHOW_CURRENT, WeatherBackupStates.showing_forecast)
async def handle_show_current_from_forecast_backup(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    user_fsm_data = await state.get_data()
    location = user_fsm_data.get("current_backup_location")
    logger.info(f"User {user_id} requesting to show current backup weather (from forecast view) for: '{location}'.")
    if location:
        await _fetch_and_show_backup_weather(bot, callback, state, session, location_input=location, show_forecast=False)
    else:
        logger.warning(f"User {user_id}: No location found in state for showing current backup weather from forecast.")
        await callback.answer("Не вдалося знайти місто.", show_alert=True)
        await state.set_state(WeatherBackupStates.waiting_for_location)
        await callback.message.edit_text("Будь ласка, введіть місто для резервної погоди:")

# Можно добавить обработчик для кнопки "Назад в меню" из этого модуля, если он будет иметь свою клавиатуру с такой кнопкой.
# @router.callback_query(F.data == "weatherbk:back_main", WeatherBackupStates.any_state)
# async def handle_weather_backup_back_to_main(callback: CallbackQuery, state: FSMContext):
#     await state.clear()
#     await show_main_menu_message(callback)
#     await callback.answer()