# src/handlers/common.py

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from sqlalchemy.ext.asyncio import AsyncSession # <<< Импорт для аннотации типа сессии
from sqlalchemy import select # <<< Импорт для select запросов (хотя session.get удобнее для PK)

# Импортируем нашу клавиатуру и callback data
from src.keyboards.inline_main import (
    get_main_menu_keyboard,
    CALLBACK_WEATHER,
    CALLBACK_CURRENCY,
    CALLBACK_ALERT
)
# Импортируем модель User
from src.db.models import User # <<< Импорт модели User

logger = logging.getLogger(__name__)

# Создаем роутер для общих обработчиков
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession): # <<< Добавили session: AsyncSession
    """
    Обработчик команды /start.
    Регистрирует нового пользователя или обновляет данные существующего.
    """
    user = message.from_user
    user_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    username = user.username

    # Пытаемся найти пользователя в БД по ID
    db_user = await session.get(User, user_id)

    if db_user:
        logger.info(f"User {user_id} ('{username}') found in DB. Updating info.")
        # Пользователь найден, обновляем данные, если они изменились
        db_user.first_name = first_name
        db_user.last_name = last_name
        db_user.username = username
        # Поле updated_at обновится автоматически благодаря onupdate=func.now() в модели
    else:
        logger.info(f"User {user_id} ('{username}') not found. Creating new user.")
        # Пользователь не найден, создаем нового
        new_user = User(
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            username=username
            # preferred_city пока оставляем пустым (None)
        )
        session.add(new_user)
        # Коммит не нужен здесь, Middleware сделает это после успешного выполнения хэндлера

    # Отправляем приветственное сообщение с главным меню
    user_name_display = first_name # Используем только имя для приветствия
    text = f"Привіт, {user_name_display}! 👋\n\nЯ твій помічник. Оберіть опцію нижче:"
    reply_markup = get_main_menu_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)


# --- Обработчики кнопок главного меню ---
# (Остаются без изменений, если им не нужна сессия БД прямо сейчас)

@router.callback_query(F.data == CALLBACK_CURRENCY)
async def handle_currency_callback(callback: CallbackQuery):
    await callback.message.edit_text("Ви обрали розділ 'Курс валют'. Функціонал в розробці.")
    await callback.answer()

@router.callback_query(F.data == CALLBACK_ALERT)
async def handle_alert_callback(callback: CallbackQuery):
    await callback.message.edit_text("Ви обрали розділ 'Повітряна тривога'. Функціонал в розробці.")
    await callback.answer()

@router.callback_query(F.data.startswith("main:"))
async def handle_unknown_main_callback(callback: CallbackQuery):
    await callback.answer("Невідома опція!", show_alert=True)


# Функция для возврата в главное меню (остается без изменений)
async def show_main_menu(message: Message | CallbackQuery, text: str = "Головне меню. Оберіть опцію:"):
    reply_markup = get_main_menu_keyboard()
    target_message = message.message if isinstance(message, CallbackQuery) else message
    try:
        await target_message.edit_text(text, reply_markup=reply_markup)
    except Exception:
         await target_message.answer(text, reply_markup=reply_markup)
    if isinstance(message, CallbackQuery):
        await message.answer() # Важно подтверждать колбэк