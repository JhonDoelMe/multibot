# src/handlers/common.py

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext # <<< Добавляем FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

# --- Импорты клавиатур ---
# Убираем старую инлайн-клавиатуру
# from src.keyboards.inline_main import get_main_menu_keyboard, CALLBACK_WEATHER, CALLBACK_CURRENCY, CALLBACK_ALERT
# Добавляем новую Reply-клавиатуру
from src.keyboards.reply_main import get_main_reply_keyboard, BTN_WEATHER, BTN_CURRENCY, BTN_ALERTS

# --- Импорты точек входа модулей ---
from src.modules.weather.handlers import weather_entry_point
from src.modules.currency.handlers import currency_entry_point
from src.modules.alert.handlers import alert_entry_point

# --- Импорт модели User ---
from src.db.models import User

logger = logging.getLogger(__name__)
router = Router(name="common-handlers")

@router.message(CommandStart())
async def handle_start(message: Message, session: AsyncSession, state: FSMContext): # <<< Добавляем state
    """
    Обработчик команды /start.
    Регистрирует/обновляет пользователя и показывает ГЛАВНУЮ КЛАВИАТУРУ.
    """
    await state.clear() # Сбрасываем состояние при /start
    user = message.from_user
    user_id = user.id
    first_name = user.first_name
    last_name = user.last_name
    username = user.username

    db_user = await session.get(User, user_id)

    try:
        if db_user:
            # logger.info(f"User {user_id} ('{username}') found in DB. Updating info.") # Лог можно убрать
            db_user.first_name = first_name
            db_user.last_name = last_name
            db_user.username = username
            # Коммит убран, Middleware должен работать
        else:
            logger.info(f"User {user_id} ('{username}') not found. Creating new user.")
            new_user = User(
                user_id=user_id,
                first_name=first_name,
                last_name=last_name,
                username=username
            )
            session.add(new_user)
            # Коммит убран

    except Exception as e:
        logger.exception(f"Database error during /start for user {user_id}: {e}")
        await message.answer("Виникла помилка при роботі з базою даних.")
        # Не отправляем клавиатуру при ошибке БД
        return

    # Отправляем приветствие с ReplyKeyboard
    user_name_display = first_name
    text = f"Привіт, {user_name_display}! 👋\n\nОберіть опцію на клавіатурі нижче:"
    reply_markup = get_main_reply_keyboard()
    await message.answer(text=text, reply_markup=reply_markup)

# --- Удаляем старые обработчики колбэков главного меню ---
# @router.callback_query(F.data == CALLBACK_CURRENCY) ...
# @router.callback_query(F.data == CALLBACK_ALERT) ...
# @router.callback_query(F.data.startswith("main:")) ...

# --- НОВЫЕ обработчики для текста Reply-кнопок ---
@router.message(F.text == BTN_WEATHER)
async def handle_weather_text_request(message: Message, state: FSMContext, session: AsyncSession):
     # Вызываем точку входа модуля погоды, передавая всё необходимое
     await weather_entry_point(message, state, session)

@router.message(F.text == BTN_CURRENCY)
async def handle_currency_text_request(message: Message):
     # Вызываем точку входа модуля валют
     await currency_entry_point(message)

@router.message(F.text == BTN_ALERTS)
async def handle_alert_text_request(message: Message):
     # Вызываем точку входа модуля тревог
     await alert_entry_point(message)

# Функция для возврата в главное меню (просто отправляет сообщение)
# Старая клавиатура больше не нужна
async def show_main_menu_message(target: Union[Message, CallbackQuery]):
    """ Отправляет/редактирует сообщение, напоминая о главном меню. """
    text = "Головне меню  disponibili tramite i pulsanti qui sotto 👇" # Текст изменен
    target_message = target.message if isinstance(target, CallbackQuery) else target
    # Убираем клавиатуру при возврате в меню, т.к. основная теперь ReplyKeyboard
    try:
        # Пытаемся отредактировать без клавиатуры
        await target_message.edit_text(text, reply_markup=None)
    except Exception:
         # Если не вышло, отправляем новое сообщение без клавиатуры
         await target_message.answer(text, reply_markup=None)
    # Отвечаем на колбэк, если он был
    if isinstance(target, CallbackQuery):
        await target.answer()