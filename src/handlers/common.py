# src/handlers/common.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, StateFilter # StateFilter уже импортирован
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.reply_main import (
    get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS,
    BTN_ALERTS_BACKUP, BTN_WEATHER_BACKUP,
    BTN_LOCATION_MAIN, BTN_LOCATION_BACKUP
)
# Импортируем сами классы состояний для использования в StateFilter
from src.modules.weather.handlers import weather_entry_point, process_main_geolocation_button, WeatherStates as MainWeatherStates
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.modules.alert_backup.handlers import alert_backup_entry_point
from src.modules.weather_backup.handlers import weather_backup_entry_point, weather_backup_geolocation_entry_point, WeatherBackupStates
from src.db.models import User
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")
location_router = Router(name="location-handlers")


@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    # ... (код без изменений) ...
    await state.clear()
    user_tg = message.from_user;
    if not user_tg: logger.warning("Received /start from a user with no user info (message.from_user is None)."); await message.answer("Не вдалося отримати інформацію про користувача. Спробуйте пізніше."); return
    user_id = user_tg.id; first_name = user_tg.first_name if user_tg.first_name else "Користувач"; last_name = user_tg.last_name; username = user_tg.username
    db_user = None
    try:
        db_user = await session.get(User, user_id)
        if db_user:
             needs_update = False
             if db_user.first_name != first_name: db_user.first_name = first_name; needs_update = True
             if db_user.last_name != last_name: db_user.last_name = last_name; needs_update = True
             if db_user.username != username: db_user.username = username; needs_update = True
             if needs_update: logger.info(f"User {user_id} ('{username}') found. Updating info..."); session.add(db_user)
             else: logger.info(f"User {user_id} ('{username}') found. No info update needed.")
        else: logger.info(f"User {user_id} ('{username}') not found. Creating..."); new_user = User(user_id=user_id, first_name=first_name, last_name=last_name, username=username); session.add(new_user)
    except Exception as e: logger.exception(f"DB error during /start for user {user_id}: {e}", exc_info=True); await session.rollback(); await message.answer("Виникла помилка під час роботи з базою даних. Будь ласка, спробуйте пізніше."); return
    user_name_display = first_name; text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"; reply_markup = get_main_reply_keyboard(); await message.answer(text=text, reply_markup=reply_markup)

@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_entry_point(message, state, session, bot)

@router.message(F.text == BTN_WEATHER_BACKUP)
async def handle_weather_backup_text_request(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
     await weather_backup_entry_point(message, state, session, bot)

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot): await currency_entry_point(message, bot)
@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot): await alert_entry_point(message, bot)
@router.message(F.text == BTN_ALERTS_BACKUP)
async def handle_alert_backup_text_request(message: Message, bot: Bot): await alert_backup_entry_point(message, bot)


# --- ОБРАБОТКА ГЕОЛОКАЦИИ ЧЕРЕЗ LOCATION_ROUTER ---

# Этот фильтр означает: НЕ в состоянии MainWeatherStates.waiting_for_city И НЕ в состоянии WeatherBackupStates.waiting_for_location
# StateFilter(None) - без состояния
# MainWeatherStates.waiting_for_save_decision - если основной модуль ждет решения о сохранении
# WeatherBackupStates.showing_current - если резервный модуль показывает текущую
# WeatherBackupStates.showing_forecast - если резервный модуль показывает прогноз
# Важно! MainWeatherStates не имеет showing_current/forecast, поэтому их убираем оттуда.
allowed_states_for_direct_geo_buttons = StateFilter(
    None, # Нет состояния
    MainWeatherStates.waiting_for_save_decision, # Основной модуль решает сохранять ли
    WeatherBackupStates.showing_current,         # Резервный показывает текущую
    WeatherBackupStates.showing_forecast         # Резервный показывает прогноз
)

@location_router.message(F.location, F.reply_to_message.text.contains(BTN_LOCATION_MAIN), allowed_states_for_direct_geo_buttons)
async def handle_main_location_button_press(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    logger.info(f"User {message.from_user.id} used MAIN location button (detected by reply). Current state: {await state.get_state()}")
    await process_main_geolocation_button(message, state, session, bot)

@location_router.message(F.location, F.reply_to_message.text.contains(BTN_LOCATION_BACKUP), allowed_states_for_direct_geo_buttons)
async def handle_backup_location_button_press(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    logger.info(f"User {message.from_user.id} used BACKUP location button (detected by reply). Current state: {await state.get_state()}")
    await weather_backup_geolocation_entry_point(message, state, session, bot)

# Обработчик для геолокации, если она пришла НЕ в состоянии ожидания (waiting_for_location в любом из модулей)
# и НЕ как ответ на специфичную кнопку. По умолчанию - основной сервис.
# Этот хендлер сработает, если мы не в waiting_for_city и не в waiting_for_location И не сработали верхние по reply_to_message.
@location_router.message(F.location, allowed_states_for_direct_geo_buttons)
async def handle_any_other_location(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    current_state_for_any_other = await state.get_state()
    logger.info(f"User {user_id} sent location directly. Current state: {current_state_for_any_other}. Reply_to: {message.reply_to_message}. Defaulting to main weather.")
    
    # Дополнительная проверка, чтобы убедиться, что это не было ответом на кнопки,
    # которые должны были быть обработаны выше (на случай, если contains не сработал идеально)
    is_reply_context_handled = False
    if message.reply_to_message and message.reply_to_message.from_user.id == bot.id:
        replied_text = message.reply_to_message.text
        if BTN_LOCATION_MAIN in replied_text or BTN_LOCATION_BACKUP in replied_text:
            is_reply_context_handled = True # Уже должно было быть обработано выше, но на всякий случай
            logger.warning(f"User {user_id}: handle_any_other_location caught a reply that should have been handled by button-specific handlers. Replied text: '{replied_text}'")
            # Можно решить не делать ничего, если это так, или все же дефолтить. Пока дефолтим.

    if not is_reply_context_handled:
        await process_main_geolocation_button(message, state, session, bot)
    # Если is_reply_context_handled is True, это значит, что предыдущие хендлеры должны были сработать.
    # Если они не сработали из-за ошибки в фильтре contains, то здесь мы, возможно, не должны ничего делать,
    # или это указывает на проблему с replied_text. Пока что, если is_reply_context_handled, этот блок не выполнится.