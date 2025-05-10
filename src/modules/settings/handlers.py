# src/modules/settings/handlers.py

import logging
from typing import Union
from aiogram import Bot, Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext # FSM здесь не используется, но импорт может остаться
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import User, ServiceChoice
from .keyboard import (
    get_main_settings_keyboard,
    get_weather_service_selection_keyboard,
    get_alert_service_selection_keyboard,
    CB_SETTINGS_WEATHER, CB_SETTINGS_ALERTS, CB_SETTINGS_BACK_TO_MAIN_MENU,
    CB_SET_WEATHER_SERVICE_PREFIX, CB_SET_ALERTS_SERVICE_PREFIX,
    CB_BACK_TO_SETTINGS_MENU
)
from src.handlers.utils import show_main_menu_message # Для кнопки "Назад в головне меню"

logger = logging.getLogger(__name__)
router = Router(name="settings-module")

# Вспомогательная функция для получения пользователя и его настроек
async def _get_user_settings(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if not user: # На случай, если пользователь как-то обошел /start, но это маловероятно
        logger.warning(f"User {user_id} not found in DB for settings. Creating one now.")
        user = User(user_id=user_id, first_name="Unknown User") # Минимальные данные
        # Устанавливаем значения по умолчанию, если они не были установлены при создании модели
        if not user.preferred_weather_service:
            user.preferred_weather_service = ServiceChoice.OPENWEATHERMAP
        if not user.preferred_alert_service:
            user.preferred_alert_service = ServiceChoice.UKRAINEALARM
        session.add(user)
        await session.commit() # Коммитим сразу, т.к. это критично для дальнейшей работы
        logger.info(f"Created new user {user_id} with default settings from settings module.")
    return user

# Точка входа в настройки
async def settings_entry_point(target: Union[Message, CallbackQuery], session: AsyncSession, bot: Bot):
    user_id = target.from_user.id
    db_user = await _get_user_settings(session, user_id)
    
    text = "⚙️ **Налаштування**\n\nОберіть, що саме ви хочете налаштувати:"
    reply_markup = get_main_settings_keyboard(
        current_weather_service=db_user.preferred_weather_service,
        current_alert_service=db_user.preferred_alert_service
    )

    if isinstance(target, CallbackQuery):
        await target.answer()
        try:
            await target.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message for settings_entry_point: {e}")
            # Если редактирование не удалось, можно отправить новое сообщение
            await target.message.answer(text, reply_markup=reply_markup) 
    else: # Если это Message (например, команда /settings)
        await target.answer(text, reply_markup=reply_markup)

# Навигация: Назад в главное меню бота
@router.callback_query(F.data == CB_SETTINGS_BACK_TO_MAIN_MENU)
async def cq_back_to_main_bot_menu(callback: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    # state и session здесь могут не понадобиться, если show_main_menu_message их не использует
    await show_main_menu_message(callback) # Эта функция должна отредактировать сообщение и убрать инлайн-клавиатуру
    await callback.answer()


# Навигация: Назад в главное меню настроек
@router.callback_query(F.data == CB_BACK_TO_SETTINGS_MENU)
async def cq_back_to_settings_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    await settings_entry_point(callback, session, bot)
    # await callback.answer() # settings_entry_point уже делает answer


# --- Настройки сервиса погоды ---
@router.callback_query(F.data == CB_SETTINGS_WEATHER)
async def cq_select_weather_service_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    
    text = "🌦️ **Вибір сервісу погоди**\n\nОберіть бажаний сервіс для отримання даних про погоду:"
    reply_markup = get_weather_service_selection_keyboard(db_user.preferred_weather_service)
    
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=reply_markup)

@router.callback_query(F.data.startswith(CB_SET_WEATHER_SERVICE_PREFIX))
async def cq_set_weather_service(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    chosen_service = callback.data.split(":")[-1] # Извлекаем код сервиса из callback_data

    # Валидация выбранного сервиса
    if chosen_service not in [ServiceChoice.OPENWEATHERMAP, ServiceChoice.WEATHERAPI]:
        logger.warning(f"User {user_id} tried to set invalid weather service: {chosen_service}")
        await callback.answer("Некоректний вибір сервісу!", show_alert=True)
        return

    db_user = await _get_user_settings(session, user_id)
    if db_user.preferred_weather_service == chosen_service:
        await callback.answer("Цей сервіс вже обрано.", show_alert=True)
    else:
        db_user.preferred_weather_service = chosen_service
        session.add(db_user)
        # Коммит будет выполнен через DbSessionMiddleware
        logger.info(f"User {user_id} set preferred_weather_service to '{chosen_service}'. Waiting for commit.")
        await callback.answer(f"Сервіс погоди змінено на {chosen_service}.", show_alert=False)
        
        # Обновляем клавиатуру, чтобы показать новый выбор
        text = "🌦️ **Вибір сервісу погоди**\n\nОберіть бажаний сервіс для отримання даних про погоду:"
        reply_markup = get_weather_service_selection_keyboard(chosen_service)
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message after setting weather service: {e}")


# --- Настройки сервиса тревог ---
@router.callback_query(F.data == CB_SETTINGS_ALERTS)
async def cq_select_alert_service_menu(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    db_user = await _get_user_settings(session, user_id)
    
    text = "🚨 **Вибір сервісу тривог**\n\nОберіть бажаний сервіс для отримання даних про повітряні тривоги:"
    reply_markup = get_alert_service_selection_keyboard(db_user.preferred_alert_service)
    
    await callback.answer()
    await callback.message.edit_text(text, reply_markup=reply_markup)

@router.callback_query(F.data.startswith(CB_SET_ALERTS_SERVICE_PREFIX))
async def cq_set_alert_service(callback: CallbackQuery, session: AsyncSession, bot: Bot):
    user_id = callback.from_user.id
    chosen_service = callback.data.split(":")[-1]

    if chosen_service not in [ServiceChoice.UKRAINEALARM, ServiceChoice.ALERTSINUA]:
        logger.warning(f"User {user_id} tried to set invalid alert service: {chosen_service}")
        await callback.answer("Некоректний вибір сервісу!", show_alert=True)
        return

    db_user = await _get_user_settings(session, user_id)
    if db_user.preferred_alert_service == chosen_service:
        await callback.answer("Цей сервіс вже обрано.", show_alert=True)
    else:
        db_user.preferred_alert_service = chosen_service
        session.add(db_user)
        logger.info(f"User {user_id} set preferred_alert_service to '{chosen_service}'. Waiting for commit.")
        await callback.answer(f"Сервіс тривог змінено на {chosen_service}.", show_alert=False)

        text = "🚨 **Вибір сервісу тривог**\n\nОберіть бажаний сервіс для отримання даних про повітряні тривоги:"
        reply_markup = get_alert_service_selection_keyboard(chosen_service)
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error editing message after setting alert service: {e}")