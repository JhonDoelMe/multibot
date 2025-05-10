# src/handlers/common.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, StateFilter # Добавляем StateFilter
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from src.keyboards.reply_main import (
    get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS,
    BTN_ALERTS_BACKUP, BTN_WEATHER_BACKUP,
    BTN_LOCATION_MAIN, BTN_LOCATION_BACKUP
)
# Импортируем функции напрямую, а не весь модуль handlers, если это возможно
from src.modules.weather.handlers import weather_entry_point, process_main_geolocation_button, WeatherStates as MainWeatherStates
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point
from src.modules.alert_backup.handlers import alert_backup_entry_point
from src.modules.weather_backup.handlers import weather_backup_entry_point, weather_backup_geolocation_entry_point, WeatherBackupStates
from src.db.models import User
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")
location_router = Router(name="location-handlers") # Этот роутер будет обрабатывать геолокацию от кнопок


@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext):
    # ... (код без изменений) ...
    await state.clear()
    user_tg = message.from_user; # ... (остальной код start без изменений)
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

# ... (остальные текстовые кнопки без изменений)
@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message, bot: Bot): await currency_entry_point(message, bot)
@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message, bot: Bot): await alert_entry_point(message, bot)
@router.message(F.text == BTN_ALERTS_BACKUP)
async def handle_alert_backup_text_request(message: Message, bot: Bot): await alert_backup_entry_point(message, bot)


# --- ОБРАБОТКА ГЕОЛОКАЦИИ ЧЕРЕЗ LOCATION_ROUTER ---

# Этот обработчик будет вызван, если пришла геолокация, И мы НЕ находимся в одном из состояний ожидания геолокации
# И это был ответ на кнопку BTN_LOCATION_MAIN
@location_router.message(F.location, F.reply_to_message.text.contains(BTN_LOCATION_MAIN), StateFilter(None, MainWeatherStates.showing_current, MainWeatherStates.showing_forecast, WeatherBackupStates.showing_current, WeatherBackupStates.showing_forecast) )
async def handle_main_location_button_press(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    logger.info(f"User {message.from_user.id} used MAIN location button (detected by reply).")
    await process_main_geolocation_button(message, state, session, bot)

# Этот обработчик будет вызван, если пришла геолокация, И мы НЕ находимся в одном из состояний ожидания геолокации
# И это был ответ на кнопку BTN_LOCATION_BACKUP
@location_router.message(F.location, F.reply_to_message.text.contains(BTN_LOCATION_BACKUP), StateFilter(None, MainWeatherStates.showing_current, MainWeatherStates.showing_forecast, WeatherBackupStates.showing_current, WeatherBackupStates.showing_forecast) )
async def handle_backup_location_button_press(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    logger.info(f"User {message.from_user.id} used BACKUP location button (detected by reply).")
    await weather_backup_geolocation_entry_point(message, state, session, bot)

# Общий обработчик для геолокации, если она пришла НЕ в состоянии ожидания (waiting_for_location)
# и НЕ как ответ на специфичную кнопку. По умолчанию - основной сервис.
# StateFilter(None) означает, что этот хендлер сработает, только если FSM не установлен (None)
# или можно добавить сюда состояния, в которых мы НЕ ожидаем специальной обработки геолокации.
# Например, если мы уже показываем погоду (showing_current / showing_forecast в любом из модулей).
@location_router.message(F.location, StateFilter(None, MainWeatherStates.showing_current, MainWeatherStates.showing_forecast, WeatherBackupStates.showing_current, WeatherBackupStates.showing_forecast))
async def handle_any_other_location(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    logger.info(f"User {user_id} sent location directly (not in waiting state, not specific reply). Defaulting to main weather.")
    # Если это был ответ на какую-то кнопку, но текст не совпал с BTN_LOCATION_MAIN/BACKUP,
    # этот хендлер все равно может сработать, если нет другого более специфичного.
    # Для большей точности, можно проверить message.reply_to_message здесь снова,
    # но это усложнит. Пока оставим так.
    await process_main_geolocation_button(message, state, session, bot)