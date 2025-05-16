# src/scheduler/weather_reminders.py
import asyncio
import logging
from datetime import datetime, time as dt_time

from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession

# Потрібно налаштувати доступ до конфігурації та ініціалізації бази даних
# Це може бути складно, якщо скрипт запускається повністю окремо.
# Можливо, краще зробити його частиною основного додатку, але з окремою точкою входу.

# --- Варіант 1: Запуск як окремого скрипта (потребує налаштування async context) ---
# Потрібно буде ініціалізувати config, logging, db_session_factory, bot_instance

# --- Варіант 2: Інтеграція як команди в manage.py або в __main__.py (якщо запускати окремою командою) ---
# Наприклад, python -m src --task process_reminders

# Для простоти, припустимо, що цей скрипт має доступ до session_factory та bot_instance
# Це припущення! В реальності це потрібно буде налаштувати.

# from src.db.database import get_db_session_context # Якщо у вас є така функція
from src.db.models import User
from src.modules.weather.service import get_weather_data, format_weather_message # Або get_5day_forecast
from src.modules.weather_backup.service import get_current_weather_weatherapi, format_weather_backup_message # Якщо потрібен fallback
from src_bot_instance_placeholder import bot # Заглушка, потрібен реальний інстанс бота
from src_db_session_factory_placeholder import async_session_factory # Заглушка

logger = logging.getLogger(__name__)

async def send_weather_reminders(session_factory, current_bot_instance):
    now_utc = datetime.utcnow()
    # Враховуємо, що cron запускається кожні 5 хвилин.
    # Шукаємо нагадування, час яких припадає на поточну годину та хвилину,
    # або на найближчі хвилини, щоб не пропустити через неточність запуску.
    # Найпростіше - перевіряти поточну годину та хвилину.
    # Якщо cron кожні 5 хв, то перевірка точного часу може спрацювати.

    current_time_obj = now_utc.time().replace(second=0, microsecond=0) 
    # Або, якщо ваш сервер і БД в одному часовому поясі, можна datetime.now().time()
    # Але краще працювати з UTC і потім конвертувати час користувача до UTC для порівняння,
    # або зберігати час користувача в UTC.
    # Для простоти, припустимо, що weather_reminder_time зберігається в UTC або локальному часі сервера.
    # Якщо час в БД локальний, а сервер в UTC, потрібна конвертація.
    # Поки що припускаємо, що час в БД відповідає часу, за яким працює now_utc.time()

    # Для прикладу, будемо вважати, що weather_reminder_time - це локальний час користувача,
    # а наш планувальник працює за UTC. Це ускладнює.
    # ПРОСТІШИЙ ВАРІАНТ: Припускаємо, що користувач вводить час за Київським часом,
    # і планувальник також орієнтується на Київський час.

    from src.config import TZ_KYIV # Потрібно імпортувати або передати
    now_kyiv = datetime.now(TZ_KYIV)
    current_time_kyiv_obj = now_kyiv.time().replace(second=0, microsecond=0)
    # Округлюємо до найближчих 5 хвилин, якщо cron запускається кожні 5 хв
    # current_minute_rounded = (now_kyiv.minute // 5) * 5
    # current_time_kyiv_obj = dt_time(now_kyiv.hour, current_minute_rounded)


    logger.info(f"Scheduler: Checking weather reminders for time ~ {current_time_kyiv_obj.strftime('%H:%M')}")

    async with session_factory() as session: # type: AsyncSession
        stmt = (
            select(User)
            .where(User.weather_reminder_enabled == True)
            .where(User.weather_reminder_time != None)
            # Порівнюємо тільки годину та хвилину
            .where(extract('hour', User.weather_reminder_time) == current_time_kyiv_obj.hour)
            .where(extract('minute', User.weather_reminder_time) == current_time_kyiv_obj.minute)
        )
        users_to_remind = (await session.execute(stmt)).scalars().all()

        if not users_to_remind:
            logger.info("Scheduler: No users found for weather reminder at this time.")
            return

        logger.info(f"Scheduler: Found {len(users_to_remind)} users for weather reminder.")

        for user in users_to_remind:
            if not user.preferred_city:
                logger.warning(f"Scheduler: User {user.user_id} has reminder enabled but no preferred city.")
                continue

            logger.info(f"Scheduler: Processing reminder for user {user.user_id}, city: {user.preferred_city}")

            # Визначаємо, який сервіс погоди використовувати
            weather_data_response = None
            formatted_weather = ""

            if user.preferred_weather_service == config.ServiceChoice.OPENWEATHERMAP:
                # Для нагадування можна брати поточну погоду або короткий прогноз
                weather_data_response = await get_weather_data(current_bot_instance, city_name=user.preferred_city)
                formatted_weather = format_weather_message(weather_data_response, user.preferred_city)
            elif user.preferred_weather_service == config.ServiceChoice.WEATHERAPI:
                weather_data_response = await get_current_weather_weatherapi(current_bot_instance, location=user.preferred_city)
                formatted_weather = format_weather_backup_message(weather_data_response, user.preferred_city)
            else: # Невідомий сервіс, пропускаємо
                logger.warning(f"Scheduler: Unknown weather service '{user.preferred_weather_service}' for user {user.user_id}")
                continue

            # Перевірка, чи не було помилки при отриманні погоди
            # Функції форматування вже повертають повідомлення про помилку, якщо вона була
            is_error = ("error" in weather_data_response and isinstance(weather_data_response["error"], dict)) or \
                       (str(weather_data_response.get("cod")) != "200" and "error_source" in weather_data_response)


            if is_error:
                logger.warning(f"Scheduler: Failed to get weather for user {user.user_id}, city {user.preferred_city}. API Response: {weather_data_response}")
                # Можна не надсилати нічого або надіслати повідомлення про помилку отримання погоди
                # await current_bot_instance.send_message(user.user_id, f"😔 Не вдалося отримати погоду для нагадування по місту {user.preferred_city}.")
                continue # Пропускаємо цього користувача

            try:
                reminder_header = f"🔔 <b>Щоденне нагадування про погоду ({user.weather_reminder_time.strftime('%H:%M')})</b>\n\n"
                await current_bot_instance.send_message(user.user_id, reminder_header + formatted_weather)
                logger.info(f"Scheduler: Sent weather reminder to user {user.user_id} for city {user.preferred_city}")
                await asyncio.sleep(0.2) # Невелика затримка між відправками, щоб уникнути спаму
            except Exception as e: # Обробка помилок відправки (користувач заблокував бота тощо)
                logger.error(f"Scheduler: Failed to send reminder to user {user.user_id}: {e}")
                if "bot was blocked by the user" in str(e).lower() or \
                   "user is deactivated" in str(e).lower() or \
                   "chat not found" in str(e).lower():
                    logger.warning(f"Scheduler: Disabling reminders for user {user.user_id} due to send error.")
                    user.weather_reminder_enabled = False
                    session.add(user)
                    # Потрібен commit для збереження зміни user.weather_reminder_enabled
                    # Якщо цей скрипт запускається окремо, він має сам робити commit
                    # await session.commit() 

        # Якщо скрипт робить commit самостійно (поза DbSessionMiddleware)
        try:
            await session.commit()
            logger.info("Scheduler: Committed changes for disabled reminders (if any).")
        except Exception as e_commit:
            logger.error(f"Scheduler: Error committing session: {e_commit}")
            await session.rollback()


# Це приклад, як можна було б запустити, якби це був окремий скрипт
# async def run_scheduler_standalone():
#     # Тут потрібно ініціалізувати:
#     # 1. logging
#     # 2. config (from src import config as app_config)
#     # 3. db_initialized, session_factory = await initialize_database()
#     # 4. bot = Bot(token=app_config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

#     # Перевірити, чи все ініціалізовано
#     # if not db_initialized or not session_factory or not bot:
#     #     logger.critical("Scheduler: Failed to initialize dependencies. Exiting.")
#     #     return

#     # await send_weather_reminders(session_factory, bot)

#     # Закрити сесію бота, якщо вона була створена тут
#     # await bot.session.close()
#     # logger.info("Scheduler: Bot session closed.")

# if __name__ == "__main__":
#     # Налаштування логування для окремого запуску
#     # logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
#     # asyncio.run(run_scheduler_standalone())