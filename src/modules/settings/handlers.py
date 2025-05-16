# src/modules/settings/handlers.py

import logging
from typing import Union, Optional
from datetime import time as dt_time, datetime as dt_datetime # Для роботи з часом

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
    CB_BACK_TO_SETTINGS_MENU,
    # Нові колбеки для нагадувань
    CB_SETTINGS_WEATHER_REMINDER, CB_WEATHER_REMINDER_TOGGLE,
    CB_WEATHER_REMINDER_SET_TIME, CB_WEATHER_REMINDER_TIME_SELECT_PREFIX
)
from .keyboard import ( # Нові клавіатури
    get_weather_reminder_settings_keyboard, get_weather_reminder_time_selection_keyboard
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
            first_name="Unknown User", # Можна спробувати отримати з Telegram User, якщо є доступ
            preferred_weather_service=ServiceChoice.OPENWEATHERMAP,
            preferred_alert_service=ServiceChoice.UKRAINEALARM,
            weather_reminder_enabled=False, # Значення за замовчуванням для нових полів
            weather_reminder_time=None      # Значення за замовчуванням
        )
        session.add(user)
    else:
        # Переконуємося, що у існуючого користувача є значення за замовчуванням для всіх полів
        if user.preferred_weather_service is None:
            user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if user.preferred_alert_service is None:
            user.preferred_alert_service = ServiceChoice.UKRAINEALARM
        if user.weather_reminder_enabled is None: # Для старих записів, де поле могло бути NULL
            user.weather_reminder_enabled = False
        # weather_reminder_time може бути None, це нормально
    return user

async def settings_entry_point(target: Union[Message, CallbackQuery], session: AsyncSession, bot: Bot):
    user_id = target.from_user.id
    db_user = await _get_user_settings(session, user_id)

    text = "⚙️ <b>Налаштування</b>\n\nОберіть, що саме ви хочете налаштувати:"
    reply_markup = get_main_settings_keyboard(
        current_weather_service=db_user.preferred_weather_service,
        current_alert_service=db_user.preferred_alert_service,
        weather_reminder_enabled=db_user.weather_reminder_enabled,
        weather_reminder_time=db_user.weather_reminder_time
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
                await target.message.answer(text, reply_markup=reply_markup) # Fallback
            except Exception as e_ans: logger.error(f"Error sending new message for settings_entry_point either: {e_ans}")
    else: # Message
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


# --- Налаштування сервісу погоди ---
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


# --- Налаштування сервісу тривог ---
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

# --- Нові обробники для налаштувань нагадувань про погоду ---

@router.callback_query(F.data == CB_SETTINGS_WEATHER_REMINDER)
async def cq_weather_reminder_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
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
        # Немає сенсу відправляти нове повідомлення, якщо редагування меню не вдалося,
        # бо це, ймовірно, те саме повідомлення.
    
    if not answered_callback: # Якщо перша спроба callback.answer() не вдалася
        try: await callback.answer()
        except: pass


@router.callback_query(F.data == CB_WEATHER_REMINDER_TOGGLE)
async def cq_weather_reminder_toggle(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)

    db_user.weather_reminder_enabled = not db_user.weather_reminder_enabled
    
    status_text = "увімкнено" if db_user.weather_reminder_enabled else "вимкнено"
    
    if db_user.weather_reminder_enabled and db_user.weather_reminder_time is None:
        # Встановлюємо час за замовчуванням 07:00, якщо увімкнули і час ще не встановлено
        default_time = dt_time(7, 0, 0) # Година, хвилина, секунда
        db_user.weather_reminder_time = default_time
        logger.info(f"User {user_id}: Weather reminder enabled, default time set to {default_time.strftime('%H:%M')}.")
    
    session.add(db_user) # Додаємо зміни до сесії
    # DbSessionMiddleware має зробити commit
    
    logger.info(f"User {user_id}: Weather reminder toggled to {status_text}.")

    # Оновлюємо повідомлення з налаштуваннями нагадувань, викликаючи попередній хендлер
    # Це оновить текст кнопки та загальний вигляд меню
    await cq_weather_reminder_menu(callback, session, bot) # Передаємо оригінальний callback
    
    # Відповідаємо на колбек, щоб користувач бачив підтвердження дії
    # Це потрібно зробити ПІСЛЯ того, як cq_weather_reminder_menu спробує відповісти,
    # щоб уникнути конфлікту "відповідь вже надіслано".
    # cq_weather_reminder_menu вже робить callback.answer(), тому тут це може бути зайвим,
    # або потрібно переконатися, що він не відповідає, якщо його викликають таким чином.
    # Краще, щоб cq_weather_reminder_menu завжди відповідав, а тут ми просто оновлюємо.
    # Тому відповідь на колбек тут закоментована, бо cq_weather_reminder_menu вже це зробить.
    # try:
    #     await callback.answer(f"Нагадування про погоду {status_text}.")
    # except Exception:
    #     pass


@router.callback_query(F.data == CB_WEATHER_REMINDER_SET_TIME)
async def cq_weather_reminder_set_time_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)

    if not db_user.weather_reminder_enabled:
        try: await callback.answer("Спочатку увімкніть нагадування, щоб встановити час.", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (reminder disabled for set time): {e}")
        return

    text = "🕒 <b>Вибір часу для нагадування про погоду:</b>"
    # Передаємо поточний встановлений час (об'єкт dt_time) у функцію генерації клавіатури
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


@router.callback_query(F.data.startswith(CB_WEATHER_REMINDER_TIME_SELECT_PREFIX))
async def cq_weather_reminder_time_selected(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)

    if not db_user.weather_reminder_enabled:
        try: await callback.answer("Нагадування вимкнені. Вибір часу неможливий.", show_alert=True)
        except Exception as e: logger.warning(f"Could not answer callback (reminder disabled on time select): {e}")
        return

    try:
        # Витягуємо час з callback_data, наприклад, "settings:wr_time_sel:07:00" -> "07:00"
        time_str_parts = callback.data.split(':')
        if len(time_str_parts) >= 4: # settings:wr_time_sel:HH:MM
            time_str = f"{time_str_parts[-2]}:{time_str_parts[-1]}"
            selected_time_obj = dt_datetime.strptime(time_str, "%H:%M").time()
            
            db_user.weather_reminder_time = selected_time_obj
            session.add(db_user)
            logger.info(f"User {user_id}: Weather reminder time set to {time_str}.")

            await callback.answer(f"Час нагадування встановлено на {time_str}.")
            
            # Оновлюємо меню вибору часу, щоб показати галочку на новому часі
            text = "🕒 <b>Вибір часу для нагадування про погоду:</b>"
            reply_markup = get_weather_reminder_time_selection_keyboard(db_user.weather_reminder_time)
            try:
                await callback.message.edit_text(text, reply_markup=reply_markup)
            except Exception as e_edit:
                logger.error(f"Error editing message after time selection: {e_edit}")
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
