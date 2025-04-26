# src/handlers/common.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart

# Импортируем нашу клавиатуру и callback data
from src.keyboards.inline_main import (
    get_main_menu_keyboard,
    CALLBACK_WEATHER, # Оставляем импорт, но убираем обработчик ниже
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
    # Отправляем новое сообщение или редактируем старое, если возможно
    # Для /start обычно отправляем новое
    await message.answer(text=text, reply_markup=reply_markup)

# --- Обработчики кнопок главного меню ---

# !!! УДАЛЯЕМ ОБРАБОТЧИК ДЛЯ CALLBACK_WEATHER ОТСЮДА !!!
# @router.callback_query(F.data == CALLBACK_WEATHER)
# async def handle_weather_callback(callback: CallbackQuery):
#     await callback.message.edit_text("Ви обрали розділ 'Погода'. Функціонал в розробці.")
#     await callback.answer()

@router.callback_query(F.data == CALLBACK_CURRENCY)
async def handle_currency_callback(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Курс валют'."""
    await callback.message.edit_text("Ви обрали розділ 'Курс валют'. Функціонал в розробці.")
    await callback.answer() # Не забываем подтвердить колбэк

@router.callback_query(F.data == CALLBACK_ALERT)
async def handle_alert_callback(callback: CallbackQuery):
    """Обработчик нажатия кнопки 'Повітряна тривога'."""
    await callback.message.edit_text("Ви обрали розділ 'Повітряна тривога'. Функціонал в розробці.")
    await callback.answer() # Не забываем подтвердить колбэк

# Можно добавить обработчик для неизвестных callback_data главного меню
@router.callback_query(F.data.startswith("main:"))
async def handle_unknown_main_callback(callback: CallbackQuery):
    """Обработчик для неизвестных колбэков главного меню."""
    # Отвечаем во всплывающем уведомлении
    await callback.answer("Невідома опція!", show_alert=True)

# Функция для возврата в главное меню (может пригодиться в модулях)
async def show_main_menu(message: Message, text: str = "Головне меню. Оберіть опцію:"):
    """Отображает главное меню."""
    reply_markup = get_main_menu_keyboard()
    # Если message это CallbackQuery, используем message.message
    target_message = message.message if isinstance(message, CallbackQuery) else message
    # Пытаемся отредактировать сообщение, если не получается - отправляем новое
    try:
        await target_message.edit_text(text, reply_markup=reply_markup)
    except Exception: # Ловим широкое исключение на случай разных ошибок API
         await target_message.answer(text, reply_markup=reply_markup)
    # Если это был колбэк, отвечаем на него
    if isinstance(message, CallbackQuery):
        await message.answer()