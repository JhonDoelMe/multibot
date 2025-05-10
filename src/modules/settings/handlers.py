# src/modules/settings/handlers.py

import logging
from typing import Union, Optional
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession
from aiocache import Cache # Змінено імпорт з caches на Cache

from src.db.models import User, ServiceChoice
from .keyboard import (
    get_main_settings_keyboard,
    get_weather_service_selection_keyboard,
    get_alert_service_selection_keyboard,
    CB_SETTINGS_WEATHER, CB_SETTINGS_ALERTS, CB_SETTINGS_BACK_TO_MAIN_MENU,
    CB_SET_WEATHER_SERVICE_PREFIX, CB_SET_ALERTS_SERVICE_PREFIX,
    CB_BACK_TO_SETTINGS_MENU
)
from src.handlers.utils import show_main_menu_message

logger = logging.getLogger(__name__)
router = Router(name="settings-module")

async def _get_user_settings(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user:
        logger.warning(f"User {user_id} not found in DB for settings. Creating one now with defaults.")
        user = User(
            user_id=user_id,
            first_name="Unknown User",
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM
        )
        session.add(user)
    else:
        if user.preferred_weather_service is None:
            user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if user.preferred_alert_service is None:
            user.preferred_alert_service = ServiceChoice.UKRAINEALARM
    return user

async def settings_entry_point(target: Union[Message, CallbackQuery], session: AsyncSession, bot: Bot):
    user_id = target.from_user.id
    db_user = await _get_user_settings(session, user_id)

    text = "⚙️ <b>Налаштування</b>\n\nОберіть, що саме ви хочете налаштувати:"
    reply_markup = get_main_settings_keyboard(
        current_weather_service=db_user.preferred_weather_service,
        current_alert_service=db_user.preferred_alert_service
    )

    answered_callback = False
    if isinstance(target, CallbackQuery):
        try:
            await target.answer()
            answered_callback = True
        except Exception as e: logger.warning(f"Could not answer callback in settings_entry_point: {e}")
        
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e_edit:
            logger.error(f"Error editing message for settings_entry_point: {e_edit}")
            try:
                await target.message.answer(text, reply_markup=reply_markup)
            except Exception as e_ans: logger.error(f"Error sending new message for settings_entry_point either: {e_ans}")
    else:
        try:
            await target.answer(text, reply_markup=reply_markup)
        except Exception as e: logger.error(f"Error sending message for settings_entry_point: {e}")

    if isinstance(target, CallbackQuery) and not answered_callback:
        try: await target.answer()
        except: pass


@router.callback_query(F.data == CB_SETTINGS_BACK_TO_MAIN_MENU)
async def cq_back_to_main_bot_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await show_main_menu_message(callback)


@router.callback_query(F.data == CB_BACK_TO_SETTINGS_MENU)
async def cq_back_to_settings_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await settings_entry_point(callback, session, bot)


@router.callback_query(F.data == CB_SETTINGS_WEATHER)
async def cq_select_weather_service_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)

    text = "🌦️ <b>Вибір сервісу погоди</b>\n\nОберіть бажаний сервіс для отримання даних про погоду:"
    reply_markup = get_weather_service_selection_keyboard(db_user.preferred_weather_service)

    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in cq_select_weather_service_menu: {e}")
    
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message for weather service selection menu: {e_edit}")
        try: await callback.message.answer(text, reply_markup=reply_markup)
        except Exception as e_ans: logger.error(f"Error sending new message for weather service selection menu either: {e_ans}")
    
    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data.startswith(CB_SET_WEATHER_SERVICE_PREFIX))
async def cq_set_weather_service(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    chosen_service_code = callback.data.split(':')[-1]

    valid_weather_services = [ServiceChoice.OPENWEATHERMAP, ServiceChoice.WEATHERAPI]
    if chosen_service_code not in valid_weather_services:
        logger.warning(f"User {user_id} tried to set invalid weather service: {chosen_service_code}")
        try: await callback.answer("Некоректний вибір сервісу!", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (invalid weather service): {e}")
        return

    db_user = await _get_user_settings(session, user_id)
    old_service = db_user.preferred_weather_service
    message_text_after_selection = f"Сервіс погоди вже встановлено на {chosen_service_code}."
    alert_on_answer = True

    if old_service != chosen_service_code:
        db_user.preferred_weather_service = chosen_service_code
        session.add(db_user)
        logger.info(f"User {user_id} set preferred_weather_service to '{chosen_service_code}' (was '{old_service}').")
        message_text_after_selection = f"Сервіс погоди змінено на {chosen_service_code}."
        alert_on_answer = False

        try:
            # ВИПРАВЛЕНО: Створюємо екземпляри Cache з потрібними неймспейсами
            weather_cache_main = Cache(namespace="weather_service") # Використовує default конфігурацію
            await weather_cache_main.clear()
            logger.info(f"User {user_id}: Cleared 'weather_service' cache.")
            
            weather_cache_backup = Cache(namespace="weather_backup_service") # Використовує default конфігурацію
            await weather_cache_backup.clear()
            logger.info(f"User {user_id}: Cleared 'weather_backup_service' cache.")
        except Exception as e_cache:
             logger.error(f"User {user_id}: Failed to clear weather caches after service change to {chosen_service_code}: {e_cache}", exc_info=True)
    else:
        logger.info(f"User {user_id}: Weather service '{chosen_service_code}' was already selected.")

    answered_callback = False
    try:
        await callback.answer(message_text_after_selection, show_alert=alert_on_answer)
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback (set weather service): {e}")

    text = "🌦️ <b>Вибір сервісу погоди</b>\n\nОберіть бажаний сервіс для отримання даних про погоду:"
    reply_markup = get_weather_service_selection_keyboard(chosen_service_code)
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message after setting weather service: {e_edit}")
    
    if not answered_callback:
        try: await callback.answer(message_text_after_selection, show_alert=alert_on_answer)
        except: pass


@router.callback_query(F.data == CB_SETTINGS_ALERTS)
async def cq_select_alert_service_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)

    text = "🚨 <b>Вибір сервісу тривог</b>\n\nОберіть бажаний сервіс для отримання даних про повітряні тривоги:"
    reply_markup = get_alert_service_selection_keyboard(db_user.preferred_alert_service)

    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in cq_select_alert_service_menu: {e}")
    
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message for alert service selection menu: {e_edit}")
        try: await callback.message.answer(text, reply_markup=reply_markup)
        except Exception as e_ans: logger.error(f"Error sending new message for alert service selection menu either: {e_ans}")

    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data.startswith(CB_SET_ALERTS_SERVICE_PREFIX))
async def cq_set_alert_service(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    chosen_service_code = callback.data.split(":")[-1]

    valid_alert_services = [ServiceChoice.UKRAINEALARM, ServiceChoice.ALERTSINUA]
    if chosen_service_code not in valid_alert_services:
        logger.warning(f"User {user_id} tried to set invalid alert service: {chosen_service_code}")
        try: await callback.answer("Некоректний вибір сервісу!", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (invalid alert service): {e}")
        return

    db_user = await _get_user_settings(session, user_id)
    old_service = db_user.preferred_alert_service
    message_text_after_selection = f"Сервіс тривог вже встановлено на {chosen_service_code}."
    alert_on_answer = True

    if old_service != chosen_service_code:
        db_user.preferred_alert_service = chosen_service_code
        session.add(db_user)
        logger.info(f"User {user_id} set preferred_alert_service to '{chosen_service_code}' (was '{old_service}').")
        message_text_after_selection = f"Сервіс тривог змінено на {chosen_service_code}."
        alert_on_answer = False

        try:
            # ВИПРАВЛЕНО: Створюємо екземпляри Cache з потрібними неймспейсами
            alert_cache_main = Cache(namespace="alerts") # Неймспейс для UkraineAlarm
            await alert_cache_main.clear()
            logger.info(f"User {user_id}: Cleared 'alerts' cache.")

            alert_cache_backup = Cache(namespace="alerts_backup") # Неймспейс для Alerts.in.ua
            await alert_cache_backup.clear()
            logger.info(f"User {user_id}: Cleared 'alerts_backup' cache.")
        except Exception as e_cache:
             logger.error(f"User {user_id}: Failed to clear alert caches after service change to {chosen_service_code}: {e_cache}", exc_info=True)
    else:
        logger.info(f"User {user_id}: Alert service '{chosen_service_code}' was already selected.")

    answered_callback = False
    try:
        await callback.answer(message_text_after_selection, show_alert=alert_on_answer)
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback (set alert service): {e}")

    text = "🚨 <b>Вибір сервісу тривог</b>\n\nОберіть бажаний сервіс для отримання даних про повітряні тривоги:"
    reply_markup = get_alert_service_selection_keyboard(chosen_service_code)
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message after setting alert service: {e_edit}")

    if not answered_callback:
        try: await callback.answer(message_text_after_selection, show_alert=alert_on_answer)
        except: pass