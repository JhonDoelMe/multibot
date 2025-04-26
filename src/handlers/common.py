# src/handlers/common.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

# Импортируем нашу клавиатуру и callback data
from src.keyboards.inline_main import (
    get_main_menu_keyboard,
    CALLBACK_WEATHER,
    CALLBACK_CURRENCY,
    CALLBACK_ALERT
)

# Создаем роутер для общих обработчиков
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message):
    """Обработчик команды /start."""
    user_name = message.from_user.first_name
    text = f"Привіт, {user_name}! 👋\n\nЯ твій помічник. Оберіть опцію нижче:"
    reply_markup = get_main_menu_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

# --- Обработчики кнопок главного меню ---
# Пока они будут просто уведомлять пользователя, что раздел в разработке

@router.callback_query(F.data == CALLBACK_WEATHER)
async def handle_weather_callback(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Погода'."""
    # В будущем здесь будет вызов логики модуля погоды
    await callback.message.edit_text("Ви обрали розділ 'Погода'. Функціонал в розробці.")
    # Уведомляем Telegram, что колбэк обработан
    await callback.answer()

@router.callback_query(F.data == CALLBACK_CURRENCY)
async def handle_currency_callback(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Курс валют'."""
    # В будущем здесь будет вызов логики модуля валют
    await callback.message.edit_text("Ви обрали розділ 'Курс валют'. Функціонал в розробці.")
    await callback.answer()

@router.callback_query(F.data == CALLBACK_ALERT)
async def handle_alert_callback(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Повітряна тривога'."""
    # В будущем здесь будет вызов логики модуля тревог
    await callback.message.edit_text("Ви обрали розділ 'Повітряна тривога'. Функціонал в розробці.")
    await callback.answer()

# Можно добавить обработчик для неизвестных callback_data главного меню
@router.callback_query(F.data.startswith("main:"))
async def handle_unknown_main_callback(callback: CallbackQuery):
    """Обработчик для неизвестных колбэков главного меню."""
    await callback.answer("Невідома опція!", show_alert=True)