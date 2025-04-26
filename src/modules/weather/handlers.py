# src/modules/weather/handlers.py

import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# Импортируем функции из других модулей проекта
from src.keyboards.inline_main import CALLBACK_WEATHER # Импортируем callback из главного меню
from src.handlers.common import show_main_menu # Импортируем функцию для возврата в меню
from .service import get_weather_data, format_weather_message # Сервис погоды
from .keyboard import get_weather_back_keyboard, CALLBACK_WEATHER_BACK # Клавиатура "Назад"

logger = logging.getLogger(__name__)

# Создаем роутер для этого модуля
router = Router(name="weather-module")

# Определяем состояния FSM для диалога погоды
class WeatherStates(StatesGroup):
    waiting_for_city = State() # Состояние ожидания названия города

# --- Обработчики ---

@router.callback_query(F.data == CALLBACK_WEATHER)
async def handle_weather_request(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки 'Погода' из главного меню.
    Запрашивает у пользователя город и переходит в состояние ожидания.
    """
    logger.info(f"User {callback.from_user.id} requested weather. Asking for city.")
    # Запрашиваем город
    await callback.message.edit_text("🌍 Будь ласка, введіть назву міста:")
    # Устанавливаем состояние ожидания ввода города
    await state.set_state(WeatherStates.waiting_for_city)
    # Отвечаем на колбэк, чтобы убрать "часики"
    await callback.answer()

@router.message(WeatherStates.waiting_for_city)
async def handle_city_input(message: Message, state: FSMContext):
    """
    Обрабатывает сообщение пользователя, когда бот находится в состоянии
    ожидания названия города. Получает погоду и отправляет результат.
    """
    city_name = message.text.strip()
    user_id = message.from_user.id
    logger.info(f"User {user_id} entered city: {city_name}")

    # Очищаем состояние FSM перед выполнением запроса
    await state.clear()

    # Показываем "загрузку"
    processing_message = await message.answer("🔍 Отримую дані про погоду...")

    # Получаем данные о погоде
    weather_data = await get_weather_data(city_name)

    if weather_data and weather_data.get("cod") == 200:
        # Если данные получены успешно (код 200)
        weather_message = format_weather_message(weather_data, city_name)
        reply_markup = get_weather_back_keyboard()
        await processing_message.edit_text(weather_message, reply_markup=reply_markup)
        logger.info(f"Sent weather for {city_name} to user {user_id}")
    elif weather_data and weather_data.get("cod") == 404:
        # Город не найден
        error_text = f"😔 На жаль, місто '{city_name}' не знайдено. Спробуйте іншу назву."
        reply_markup = get_weather_back_keyboard() # Даем возможность вернуться
        await processing_message.edit_text(error_text, reply_markup=reply_markup)
        logger.warning(f"City '{city_name}' not found for user {user_id}")
    else:
        # Другая ошибка API или внутренняя ошибка
        error_code = weather_data.get('cod', 'N/A') if weather_data else 'N/A'
        error_text = f"😥 Вибачте, сталася помилка при отриманні погоди (Код: {error_code}). Спробуйте пізніше."
        reply_markup = get_weather_back_keyboard() # Даем возможность вернуться
        await processing_message.edit_text(error_text, reply_markup=reply_markup)
        logger.error(f"Failed to get weather for {city_name} for user {user_id}. Code: {error_code}")


@router.callback_query(F.data == CALLBACK_WEATHER_BACK)
async def handle_weather_back(callback: CallbackQuery, state: FSMContext):
    """
    Обрабатывает нажатие кнопки 'Назад в меню' из модуля погоды.
    Возвращает пользователя в главное меню.
    """
    logger.info(f"User {callback.from_user.id} requested back to main menu from weather.")
    # Очищаем состояние FSM на всякий случай
    await state.clear()
    # Используем общую функцию для отображения главного меню
    await show_main_menu(callback)
    # Ответ на колбэк можно не отправлять, т.к. show_main_menu его отправит

# --- Конец обработчиков ---