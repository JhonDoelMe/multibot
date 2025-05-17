# src/modules/settings/handlers.py

import logging
import re 
from typing import Union, Optional
from datetime import time as dt_time, datetime as dt_datetime 

from aiogram import Bot, Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select 
from aiocache import Cache
from aiogram.filters import Command 

from src.db.models import User, ServiceChoice
from .keyboard import (
    get_main_settings_keyboard,
    get_weather_service_selection_keyboard,
    get_alert_service_selection_keyboard,
    CB_SETTINGS_WEATHER, CB_SETTINGS_ALERTS, CB_SETTINGS_BACK_TO_MAIN_MENU,
    CB_SET_WEATHER_SERVICE_PREFIX, CB_SET_ALERTS_SERVICE_PREFIX,
    CB_BACK_TO_SETTINGS_MENU,
    CB_SETTINGS_WEATHER_REMINDER, CB_WEATHER_REMINDER_TOGGLE,
    CB_WEATHER_REMINDER_SET_TIME, CB_WEATHER_REMINDER_TIME_SELECT_PREFIX,
    CB_WEATHER_REMINDER_CUSTOM_TIME_INPUT,
    CB_SETTINGS_ADMIN_PANEL 
)
from .keyboard import ( 
    get_weather_reminder_settings_keyboard, get_weather_reminder_time_selection_keyboard
)
from .admin_keyboard import (
    get_admin_panel_main_keyboard, 
    CB_ADMIN_BACK_TO_SETTINGS,
    CB_ADMIN_LIST_USERS, 
    CB_ADMIN_USER_INFO,  
    CB_ADMIN_BLOCK_USER, 
    CB_ADMIN_UNBLOCK_USER 
)

from src.handlers.utils import show_main_menu_message
from src import config as app_config 

logger = logging.getLogger(__name__)
router = Router(name="settings-module")

# Стани для адмін-панелі
class AdminPanelStates(StatesGroup):
    waiting_for_user_id_for_info = State()
    waiting_for_user_id_to_block = State()
    waiting_for_user_id_to_unblock = State()


class SettingsStates(StatesGroup):
    waiting_for_custom_reminder_time = State()


async def _get_user_settings(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user:
        logger.warning(f"User {user_id} not found in DB for settings. Creating one now with defaults.")
        user = User(
            user_id=user_id,
            first_name="Unknown User", 
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, 
            weather_reminder_time=None,
            is_blocked=False 
        )
        session.add(user)
    else:
        if user.preferred_weather_service is None:
            user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if user.preferred_alert_service is None:
            user.preferred_alert_service = ServiceChoice.UKRAINEALARM
        if not hasattr(user, 'weather_reminder_enabled') or user.weather_reminder_enabled is None: 
            user.weather_reminder_enabled = False
        if not hasattr(user, 'is_blocked') or user.is_blocked is None: 
            user.is_blocked = False
    return user

async def settings_entry_point(target: Union[Message, CallbackQuery], session: AsyncSession, bot: Bot, state: FSMContext):
    user_id = target.from_user.id
    await state.clear() 
    db_user = await _get_user_settings(session, user_id)

    text = "⚙️ <b>Налаштування</b>\n\nОберіть, що саме ви хочете налаштувати:"
    reply_markup = get_main_settings_keyboard(
        current_weather_service=db_user.preferred_weather_service,
        current_alert_service=db_user.preferred_alert_service,
        weather_reminder_enabled=db_user.weather_reminder_enabled,
        weather_reminder_time=db_user.weather_reminder_time,
        current_user_id=user_id 
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
async def cq_back_to_main_bot_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear() 
    await show_main_menu_message(callback)


@router.callback_query(F.data == CB_BACK_TO_SETTINGS_MENU)
async def cq_back_to_settings_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    await settings_entry_point(callback, session, bot, state)

# --- Обробник для кнопки "Адмін-панель" ---
@router.callback_query(F.data == CB_SETTINGS_ADMIN_PANEL)
async def cq_admin_panel_entry(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot): 
    user_id = callback.from_user.id
    
    if user_id not in app_config.ADMIN_USER_IDS:
        logger.warning(f"User {user_id} (not an admin) somehow pressed admin panel button. Ignoring.")
        try:
            await callback.answer("Ця функція доступна тільки адміністраторам.", show_alert=True)
        except Exception: pass
        return

    logger.info(f"Admin user {user_id} accessed admin panel main menu.")
    await state.clear() 

    admin_text = "👑 <b>Головне меню Адмін-панелі</b> 👑\n\nОберіть дію:"
    admin_reply_markup = get_admin_panel_main_keyboard()

    try:
        await callback.answer()
    except Exception: pass

    try:
        await callback.message.edit_text(admin_text, reply_markup=admin_reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message for admin panel entry: {e_edit}")
        try:
            await callback.message.answer(admin_text, reply_markup=admin_reply_markup)
        except Exception as e_ans:
            logger.error(f"Error sending new message for admin panel entry: {e_ans}")

@router.callback_query(F.data == CB_ADMIN_BACK_TO_SETTINGS)
async def cq_admin_back_to_settings(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    logger.info(f"Admin user {callback.from_user.id} going back to main settings menu from admin panel.")
    await settings_entry_point(callback, session, bot, state) # settings_entry_point clears state


@router.callback_query(F.data == CB_ADMIN_LIST_USERS)
async def cq_admin_list_users(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    if user_id not in app_config.ADMIN_USER_IDS:
        await callback.answer("Доступ заборонено.", show_alert=True)
        return
    
    # TODO: Implement user listing with pagination
    await callback.answer("Функція 'Список користувачів' в розробці.")


@router.callback_query(F.data == CB_ADMIN_USER_INFO)
async def cq_admin_user_info_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in app_config.ADMIN_USER_IDS:
        await callback.answer("Доступ заборонено.", show_alert=True)
        return
    
    await state.set_state(AdminPanelStates.waiting_for_user_id_for_info)
    try:
        await callback.message.edit_text("Введіть ID користувача для отримання інформації:", reply_markup=None)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cq_admin_user_info_prompt: {e}")
        await callback.answer("Помилка. Спробуйте ще раз.")


@router.message(AdminPanelStates.waiting_for_user_id_for_info, F.text)
async def process_admin_user_id_for_info(message: Message, state: FSMContext, session: AsyncSession):
    admin_id = message.from_user.id
    # No need to check admin_id here again if state can only be set by admin
    
    try:
        target_user_id = int(message.text.strip())
    except ValueError:
        await message.reply(
            "Неправильний формат ID. Введення скасовано.\n"
            "Ви повернені до головного меню адмін-панелі."
        )
        await state.clear()
        await message.answer(
            "👑 <b>Головне меню Адмін-панелі</b> 👑\n\nОберіть дію:",
            reply_markup=get_admin_panel_main_keyboard()
        )
        return 

    target_user = await session.get(User, target_user_id)
    info_text = ""
    if target_user:
        info_text = (
            f"<b>Інформація про користувача ID: {target_user.user_id}</b>\n"
            f"Ім'я: {target_user.first_name or 'N/A'} {target_user.last_name or ''}\n"
            f"Username: @{target_user.username or 'N/A'}\n"
            f"Місто: {target_user.preferred_city or 'Не вказано'}\n"
            f"Сервіс погоди: {target_user.preferred_weather_service}\n"
            f"Сервіс тривог: {target_user.preferred_alert_service}\n"
            f"Нагадування: {'Увімк.' if target_user.weather_reminder_enabled else 'Вимк.'} "
            f"({target_user.weather_reminder_time.strftime('%H:%M') if target_user.weather_reminder_time else 'час не вст.'})\n"
            f"Заблокований: {'Так' if target_user.is_blocked else 'Ні'}\n"
            f"Зареєстрований: {target_user.created_at.strftime('%Y-%m-%d %H:%M:%S %Z') if target_user.created_at else 'N/A'}\n"
            f"Оновлено: {target_user.updated_at.strftime('%Y-%m-%d %H:%M:%S %Z') if target_user.updated_at else 'N/A'}"
        )
    else:
        info_text = f"Користувача з ID {target_user_id} не знайдено."
    
    await state.clear()
    await message.answer(info_text, reply_markup=get_admin_panel_main_keyboard())


@router.callback_query(F.data == CB_ADMIN_BLOCK_USER)
async def cq_admin_block_user_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in app_config.ADMIN_USER_IDS:
        await callback.answer("Доступ заборонено.", show_alert=True)
        return
    
    await state.set_state(AdminPanelStates.waiting_for_user_id_to_block)
    try:
        await callback.message.edit_text("Введіть ID користувача, якого потрібно заблокувати:", reply_markup=None)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cq_admin_block_user_prompt: {e}")
        await callback.answer("Помилка. Спробуйте ще раз.")


@router.message(AdminPanelStates.waiting_for_user_id_to_block, F.text)
async def process_admin_user_id_to_block(message: Message, state: FSMContext, session: AsyncSession):
    admin_id = message.from_user.id
    
    try:
        target_user_id_to_block = int(message.text.strip())
    except ValueError:
        await message.reply(
            "Неправильний формат ID. Введення скасовано.\n"
            "Ви повернені до головного меню адмін-панелі."
        )
        await state.clear()
        await message.answer(
            "👑 <b>Головне меню Адмін-панелі</b> 👑\n\nОберіть дію:",
            reply_markup=get_admin_panel_main_keyboard()
        )
        return

    target_user = await session.get(User, target_user_id_to_block)
    response_text = ""
    if target_user:
        if not target_user.is_blocked:
            target_user.is_blocked = True
            session.add(target_user)
            response_text = f"Користувач ID {target_user_id_to_block} ({target_user.first_name or ''}) успішно заблокований."
            logger.info(f"Admin {admin_id} blocked user {target_user_id_to_block}.")
        else:
            response_text = f"Користувач ID {target_user_id_to_block} вже заблокований."
    else:
        response_text = f"Користувача з ID {target_user_id_to_block} не знайдено."
        
    await state.clear()
    await message.answer(response_text, reply_markup=get_admin_panel_main_keyboard())


@router.callback_query(F.data == CB_ADMIN_UNBLOCK_USER)
async def cq_admin_unblock_user_prompt(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    if user_id not in app_config.ADMIN_USER_IDS:
        await callback.answer("Доступ заборонено.", show_alert=True)
        return
        
    await state.set_state(AdminPanelStates.waiting_for_user_id_to_unblock)
    try:
        await callback.message.edit_text("Введіть ID користувача, якого потрібно розблокувати:", reply_markup=None)
        await callback.answer()
    except Exception as e:
        logger.error(f"Error in cq_admin_unblock_user_prompt: {e}")
        await callback.answer("Помилка. Спробуйте ще раз.")


@router.message(AdminPanelStates.waiting_for_user_id_to_unblock, F.text)
async def process_admin_user_id_to_unblock(message: Message, state: FSMContext, session: AsyncSession):
    admin_id = message.from_user.id

    try:
        target_user_id_to_unblock = int(message.text.strip())
    except ValueError:
        await message.reply(
            "Неправильний формат ID. Введення скасовано.\n"
            "Ви повернені до головного меню адмін-панелі."
        )
        await state.clear()
        await message.answer(
            "👑 <b>Головне меню Адмін-панелі</b> 👑\n\nОберіть дію:",
            reply_markup=get_admin_panel_main_keyboard()
        )
        return

    target_user = await session.get(User, target_user_id_to_unblock)
    response_text = ""
    if target_user:
        if target_user.is_blocked:
            target_user.is_blocked = False
            session.add(target_user)
            response_text = f"Користувач ID {target_user_id_to_unblock} ({target_user.first_name or ''}) успішно розблокований."
            logger.info(f"Admin {admin_id} unblocked user {target_user_id_to_unblock}.")
        else:
            response_text = f"Користувач ID {target_user_id_to_unblock} не був заблокований."
    else:
        response_text = f"Користувача з ID {target_user_id_to_unblock} не знайдено."
        
    await state.clear()
    await message.answer(response_text, reply_markup=get_admin_panel_main_keyboard())


# Попередні обробники (налаштування погоди, тривог, часу нагадувань)
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
            weather_cache_main = Cache(namespace="weather_service")
            await weather_cache_main.clear()
            logger.info(f"User {user_id}: Cleared 'weather_service' cache.")
            weather_cache_backup = Cache(namespace="weather_backup_service")
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
            alert_cache_main = Cache(namespace="alerts")
            await alert_cache_main.clear()
            logger.info(f"User {user_id}: Cleared 'alerts' cache.")
            alert_cache_backup = Cache(namespace="alerts_backup")
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

@router.callback_query(F.data == CB_SETTINGS_WEATHER_REMINDER)
async def cq_weather_reminder_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    await state.set_state(None) 
    db_user = await _get_user_settings(session, user_id)
    text = "⏰ <b>Налаштування нагадувань про погоду</b>"
    reply_markup = get_weather_reminder_settings_keyboard(
        reminder_enabled=db_user.weather_reminder_enabled,
        reminder_time=db_user.weather_reminder_time
    )
    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in cq_weather_reminder_menu: {e}")
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message for weather reminder menu: {e_edit}")
    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data == CB_WEATHER_REMINDER_TOGGLE)
async def cq_weather_reminder_toggle(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    db_user.weather_reminder_enabled = not db_user.weather_reminder_enabled
    status_text = "увімкнено" if db_user.weather_reminder_enabled else "вимкнено"
    if db_user.weather_reminder_enabled and db_user.weather_reminder_time is None:
        default_time = dt_time(7, 0, 0) 
        db_user.weather_reminder_time = default_time
        logger.info(f"User {user_id}: Weather reminder enabled, default time set to {default_time.strftime('%H:%M')}.")
    session.add(db_user)
    logger.info(f"User {user_id}: Weather reminder toggled to {status_text}.")
    await cq_weather_reminder_menu(callback, state, session, bot) 

@router.callback_query(F.data == CB_WEATHER_REMINDER_SET_TIME)
async def cq_weather_reminder_set_time_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    if not db_user.weather_reminder_enabled:
        try: await callback.answer("Спочатку увімкніть нагадування, щоб встановити час.", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (reminder disabled for set time): {e}")
        return
    text = "🕒 <b>Вибір часу для нагадування про погоду:</b>\nОберіть зі списку або введіть свій час."
    reply_markup = get_weather_reminder_time_selection_keyboard(db_user.weather_reminder_time)
    answered_callback = False
    try:
        await callback.answer()
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in cq_weather_reminder_set_time_menu: {e}")
    try:
        await callback.message.edit_text(text, reply_markup=reply_markup)
    except Exception as e_edit:
        logger.error(f"Error editing message for set time menu: {e_edit}")
    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.callback_query(F.data == CB_WEATHER_REMINDER_CUSTOM_TIME_INPUT)
async def cq_weather_reminder_custom_time_input(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    if not db_user.weather_reminder_enabled:
        try: await callback.answer("Спочатку увімкніть нагадування.", show_alert=True)
        except Exception: pass
        return
    await state.set_state(SettingsStates.waiting_for_custom_reminder_time)
    logger.info(f"User {user_id}: Set FSM state to SettingsStates.waiting_for_custom_reminder_time.")
    text = "Будь ласка, введіть бажаний час для нагадування у форматі <b>ГГ:ХХ</b> (наприклад, 08:30 або 19:00).\n\nАбо натисніть /cancel_time_input, щоб скасувати."
    answered_callback = False
    try:
        await callback.answer("Введіть час")
        answered_callback = True
    except Exception as e: logger.warning(f"Could not answer callback in cq_weather_reminder_custom_time_input: {e}")
    try:
        await callback.message.edit_text(text) 
    except Exception as e_edit:
        logger.error(f"Error editing message for custom time input prompt: {e_edit}")
        try: 
            await callback.message.answer(text)
        except Exception as e_ans:
            logger.error(f"Error sending new message for custom time input prompt: {e_ans}")
    if not answered_callback:
        try: await callback.answer()
        except: pass

@router.message(Command("cancel_time_input"), SettingsStates.waiting_for_custom_reminder_time)
async def cmd_cancel_custom_time_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = message.from_user.id
    logger.info(f"User {user_id} cancelled custom time input.")
    await state.clear() # Очищаємо стан
    
    db_user = await _get_user_settings(session, user_id)
    text_menu = "⏰ <b>Налаштування нагадувань про погоду</b>"
    reply_markup_menu = get_weather_reminder_settings_keyboard(
        reminder_enabled=db_user.weather_reminder_enabled,
        reminder_time=db_user.weather_reminder_time
    )
    try:
        # Повертаємо до меню налаштувань нагадувань
        await message.answer("Введення часу скасовано.", reply_markup=reply_markup_menu)
    except Exception as e:
        logger.error(f"Error sending message after cancelling custom time input: {e}")


@router.message(SettingsStates.waiting_for_custom_reminder_time, F.text)
async def handle_custom_reminder_time_input(message: Message, state: FSMContext, session: AsyncSession, bot: Bot): # Додано bot
    user_id = message.from_user.id
    time_input_str = message.text.strip() if message.text else ""
    time_pattern = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
    
    if not time_pattern.match(time_input_str):
        logger.warning(f"User {user_id} entered invalid time format: '{time_input_str}'")
        await message.reply(
            "Неправильний формат часу. Введення скасовано.\n"
            "Повернення до налаштувань нагадувань."
        )
        await state.clear() 
        db_user = await _get_user_settings(session, user_id)
        await message.answer(
            "⏰ <b>Налаштування нагадувань про погоду</b>",
            reply_markup=get_weather_reminder_settings_keyboard(
                reminder_enabled=db_user.weather_reminder_enabled,
                reminder_time=db_user.weather_reminder_time
            )
        )
        return

    try:
        selected_time_obj = dt_datetime.strptime(time_input_str, "%H:%M").time()
        db_user = await _get_user_settings(session, user_id)
        db_user.weather_reminder_time = selected_time_obj
        session.add(db_user)
        logger.info(f"User {user_id}: Custom weather reminder time set to {time_input_str}.")
        await message.reply(f"✅ Час нагадування встановлено на <b>{time_input_str}</b>.")
        await state.clear() 
        text_menu = "⏰ <b>Налаштування нагадувань про погоду</b>"
        reply_markup_menu = get_weather_reminder_settings_keyboard(
            reminder_enabled=db_user.weather_reminder_enabled,
            reminder_time=db_user.weather_reminder_time
        )
        try:
            await message.answer(text_menu, reply_markup=reply_markup_menu)
        except Exception as e_send_menu:
            logger.error(f"Error sending reminder settings menu after custom time set: {e_send_menu}")
    except ValueError: 
        logger.error(f"User {user_id}: Could not parse validated time string '{time_input_str}' into time object.")
        await message.reply("Внутрішня помилка обробки часу. Введення скасовано.")
        await state.clear() 
        db_user = await _get_user_settings(session, user_id) # Потрібно для меню
        await message.answer(
            "⏰ <b>Налаштування нагадувань про погоду</b>",
            reply_markup=get_weather_reminder_settings_keyboard(
                reminder_enabled=db_user.weather_reminder_enabled,
                reminder_time=db_user.weather_reminder_time
            )
        )
    except Exception as e:
        logger.exception(f"Unexpected error processing custom reminder time for user {user_id}", exc_info=True)
        await message.reply("Не вдалося встановити час. Введення скасовано.")
        await state.clear()
        db_user = await _get_user_settings(session, user_id) # Потрібно для меню
        await message.answer(
            "⏰ <b>Налаштування нагадувань про погоду</b>",
            reply_markup=get_weather_reminder_settings_keyboard(
                reminder_enabled=db_user.weather_reminder_enabled,
                reminder_time=db_user.weather_reminder_time
            )
        )


@router.callback_query(F.data.startswith(CB_WEATHER_REMINDER_TIME_SELECT_PREFIX))
async def cq_weather_reminder_time_selected(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    if not db_user.weather_reminder_enabled:
        try: await callback.answer("Нагадування вимкнені. Вибір часу неможливий.", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (reminder disabled on time select): {e}")
        return
    try:
        time_str_parts = callback.data.split(':')
        if len(time_str_parts) >= 4: 
            time_str = f"{time_str_parts[-2]}:{time_str_parts[-1]}"
            selected_time_obj = dt_datetime.strptime(time_str, "%H:%M").time()
            db_user.weather_reminder_time = selected_time_obj
            session.add(db_user)
            logger.info(f"User {user_id}: Weather reminder time set to {time_str} via button.")
            await callback.answer(f"Час нагадування встановлено на {time_str}.")
            await state.clear() # Очищаємо стан, якщо він був (хоча тут його не повинно бути)
            await cq_weather_reminder_menu(callback, state, session, bot) # Повертаємо до меню налаштувань нагадувань
        else:
            raise ValueError("Invalid callback data format for time selection")
    except (ValueError, IndexError) as e_parse:
        logger.error(f"Error parsing time from callback data '{callback.data}': {e_parse}")
        try: await callback.answer("Помилка формату часу. Спробуйте ще раз.", show_alert=True)
        except Exception: pass
    except Exception as e:
        logger.exception(f"Unexpected error setting reminder time for user {user_id}", exc_info=True)
        try: await callback.answer("Не вдалося встановити час. Спробуйте пізніше.", show_alert=True)
        except Exception: pass