# src/scheduler_tasks.py

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta, timezone

from sqlalchemy import select, extract
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError, TelegramRetryAfter, TelegramForbiddenError,
    TelegramBadRequest, TelegramNotFound, TelegramConflictError
)


# Імпортуємо необхідні компоненти з вашого проекту
from src.db.models import User, ServiceChoice # ServiceChoice для визначення сервісу
from src.modules.weather.service import get_weather_data, format_weather_message
from src.modules.weather_backup.service import get_current_weather_weatherapi, format_weather_backup_message
from src import config # Для доступу до TZ_KYIV та інших налаштувань

logger = logging.getLogger(__name__)

# Визначаємо TZ_KYIV, намагаючись імпортувати pytz, якщо він є, інакше UTC
# Це робиться тут, оскільки цей скрипт може викликатися окремо.
try:
    import pytz
    TZ_KYIV = pytz.timezone('Europe/Kyiv')
    logger.info("Scheduler: Kyiv timezone (Europe/Kyiv) loaded using pytz.")
except ImportError:
    logger.warning("Scheduler: pytz not installed. Using system's understanding of 'Europe/Kyiv' or UTC as fallback for Kyiv time.")
    # Спроба отримати часовий пояс без pytz (може не працювати на всіх системах або давати UTC)
    try:
        # from zoneinfo import ZoneInfo # Python 3.9+
        # TZ_KYIV = ZoneInfo("Europe/Kyiv")
        # Для сумісності, якщо zoneinfo немає, можна залишити UTC або покладатися на системний localtime
        # Для простоти, якщо pytz немає, будемо використовувати UTC і логувати попередження.
        # Або краще зробити pytz обов'язковою залежністю.
        # Наразі, якщо config.TZ_KYIV не встановлено і pytz немає, це може призвести до помилок.
        # Перевіримо, чи є TZ_KYIV в config.py (ви його туди додали раніше)
        if hasattr(config, 'TZ_KYIV') and config.TZ_KYIV:
            TZ_KYIV = config.TZ_KYIV
            logger.info(f"Scheduler: Kyiv timezone loaded from config: {config.TZ_KYIV_NAME if hasattr(config, 'TZ_KYIV_NAME') else 'Europe/Kyiv'}")
        else: # Fallback, якщо ніде не визначено
            logger.warning("Scheduler: TZ_KYIV not found in config and pytz not available. Using UTC as fallback.")
            TZ_KYIV = timezone.utc
    except Exception as e_tz:
        logger.error(f"Scheduler: Error setting up Kyiv timezone: {e_tz}. Using UTC as fallback.")
        TZ_KYIV = timezone.utc


async def send_weather_reminders_task(
    session_factory: async_sessionmaker[AsyncSession],
    bot_instance: Bot
):
    """
    Завдання для перевірки та відправки нагадувань про погоду.
    Викликається періодично (наприклад, cron'ом кожні 1-5 хвилин).
    """
    if not TZ_KYIV:
        logger.critical("Scheduler: Kyiv timezone (TZ_KYIV) is not properly configured. Weather reminders cannot be processed accurately. Exiting task.")
        return

    now_localized = datetime.now(TZ_KYIV)
    
    # Якщо cron запускається кожні 5 хвилин, ми можемо перевіряти нагадування,
    # час яких потрапляє в поточний 5-хвилинний інтервал.
    # Наприклад, якщо зараз 07:03, а cron запускався о 07:00, ми перевіряємо час 07:00, 07:01, 07:02, 07:03, 07:04.
    # Або простіше: якщо cron кожну хвилину, то перевіряємо точну хвилину.
    # Якщо cron кожні 5 хвилин, то перевіряємо, чи поточна хвилина кратна 5 (0, 5, 10, ...).
    # Це спрощення, бо якщо cron спрацював о 07:01, а нагадування на 07:00, воно буде пропущено.
    
    # Більш надійний підхід для cron, що запускається кожні N хвилин (наприклад, 5):
    # Перевіряємо всі нагадування, час яких настав *протягом останніх N хвилин*.
    # Це вимагає зберігання часу останнього успішного запуску цього завдання.
    # Для простоти, поки що будемо перевіряти точну поточну годину та хвилину.
    # Це означає, що cron має запускати це завдання ЩОХВИЛИНИ для максимальної точності.
    
    current_time_for_check = now_localized.time().replace(second=0, microsecond=0)
    logger.info(f"Scheduler: Checking weather reminders for current time {current_time_for_check.strftime('%H:%M')} ({TZ_KYIV}).")

    async with session_factory() as session:  # type: AsyncSession
        stmt = (
            select(User)
            .where(User.weather_reminder_enabled == True)
            .where(User.weather_reminder_time != None)
            # Порівнюємо збережений час нагадування (який вважається локальним для користувача,
            # і ми припускаємо, що він відповідає TZ_KYIV) з поточним часом в TZ_KYIV.
            .where(extract('hour', User.weather_reminder_time) == current_time_for_check.hour)
            .where(extract('minute', User.weather_reminder_time) == current_time_for_check.minute)
        )
        
        result = await session.execute(stmt)
        users_to_remind = result.scalars().all()

        if not users_to_remind:
            logger.info(f"Scheduler: No users found for weather reminder at {current_time_for_check.strftime('%H:%M')}.")
            return

        logger.info(f"Scheduler: Found {len(users_to_remind)} users for weather reminder at {current_time_for_check.strftime('%H:%M')}.")

        successful_sends = 0
        failed_sends = 0
        users_to_disable_reminders = []

        for user in users_to_remind:
            if not user.preferred_city:
                logger.warning(f"Scheduler: User {user.user_id} has reminder enabled but no preferred_city set. Skipping.")
                continue
            
            logger.info(f"Scheduler: Processing reminder for user {user.user_id} (chat_id), city: {user.preferred_city}, reminder time: {user.weather_reminder_time.strftime('%H:%M') if user.weather_reminder_time else 'N/A'}")
            
            weather_data_response: Optional[dict] = None
            formatted_weather: str = f"😔 Не вдалося отримати дані про погоду для м. {user.preferred_city} для вашого нагадування."
            is_error_getting_weather = True

            try:
                service_name_log = ""
                if user.preferred_weather_service == ServiceChoice.OPENWEATHERMAP:
                    service_name_log = "OWM"
                    weather_data_response = await get_weather_data(bot_instance, city_name=user.preferred_city)
                    if weather_data_response and weather_data_response.get("status") != "error" and str(weather_data_response.get("cod")) == "200":
                        # Передаємо місто, яке користувач зберіг, для заголовка
                        formatted_weather = format_weather_message(weather_data_response, user.preferred_city)
                        is_error_getting_weather = False
                    else:
                        error_msg = weather_data_response.get("message", "Невідома помилка") if weather_data_response else "Відповідь порожня"
                        logger.warning(f"Scheduler: Failed to get {service_name_log} weather for user {user.user_id}, city {user.preferred_city}. Error: {error_msg}")
                        formatted_weather = f"😔 Не вдалося отримати погоду для нагадування по м. {user.preferred_city} ({service_name_log}): {error_msg}"
                
                elif user.preferred_weather_service == ServiceChoice.WEATHERAPI:
                    service_name_log = "WeatherAPI"
                    weather_data_response = await get_current_weather_weatherapi(bot_instance, location=user.preferred_city)
                    if weather_data_response and not ("error" in weather_data_response and isinstance(weather_data_response.get("error"), dict)):
                        formatted_weather = format_weather_backup_message(weather_data_response, user.preferred_city)
                        is_error_getting_weather = False
                    else:
                        error_details = weather_data_response.get("error", {}) if weather_data_response else {}
                        error_msg = error_details.get("message", "Невідома помилка")
                        logger.warning(f"Scheduler: Failed to get {service_name_log} weather for user {user.user_id}, city {user.preferred_city}. Error: {error_msg}")
                        formatted_weather = f"😔 Не вдалося отримати погоду для нагадування по м. {user.preferred_city} ({service_name_log}): {error_msg}"
                else:
                    logger.warning(f"Scheduler: Unknown preferred_weather_service '{user.preferred_weather_service}' for user {user.user_id}")
                    continue
            except Exception as e_weather_fetch:
                logger.exception(f"Scheduler: Exception while fetching weather for user {user.user_id}, city {user.preferred_city}.", exc_info=e_weather_fetch)
                # formatted_weather вже має повідомлення про помилку за замовчуванням

            message_to_send = formatted_weather
            if not is_error_getting_weather:
                reminder_time_str = user.weather_reminder_time.strftime('%H:%M') if user.weather_reminder_time else "встановлений час"
                reminder_header = f"🔔 <b>Нагадування про погоду ({reminder_time_str})</b>\n\n"
                message_to_send = reminder_header + formatted_weather
            
            try:
                await bot_instance.send_message(user.user_id, message_to_send)
                logger.info(f"Scheduler: Sent weather reminder to user {user.user_id} for city {user.preferred_city}.")
                successful_sends += 1
            except TelegramRetryAfter as e_retry:
                logger.warning(f"Scheduler: Flood control for user {user.user_id}. Retry after {e_retry.retry_after}s. Skipping this reminder cycle for user.")
                failed_sends += 1
                await asyncio.sleep(e_retry.retry_after) # Чекаємо перед наступним користувачем
            except (TelegramForbiddenError, TelegramBadRequest, TelegramNotFound, TelegramConflictError) as e_tg_user_issue:
                logger.error(f"Scheduler: Failed to send reminder to user {user.user_id} due to user-related API error: {e_tg_user_issue}. Disabling reminders.")
                users_to_disable_reminders.append(user)
                failed_sends += 1
            except TelegramAPIError as e_tg_api:
                logger.error(f"Scheduler: Failed to send reminder to user {user.user_id} due to other Telegram API error: {e_tg_api}.")
                failed_sends += 1
            except Exception as e_send_unknown:
                logger.exception(f"Scheduler: Unknown error sending reminder to user {user.user_id}.", exc_info=e_send_unknown)
                failed_sends += 1
            
            # Затримка між відправками, щоб не перевищити глобальні ліміти Telegram
            if len(users_to_remind) > 1: # Якщо є ще користувачі в черзі
                await asyncio.sleep(0.1) # 100 мс, можна налаштувати

        if users_to_disable_reminders:
            logger.info(f"Scheduler: Disabling reminders for {len(users_to_disable_reminders)} users.")
            for user_to_disable in users_to_disable_reminders:
                user_to_disable.weather_reminder_enabled = False
                session.add(user_to_disable)
        
        if users_to_disable_reminders or successful_sends > 0 or failed_sends > 0: # Тільки якщо були якісь дії
            try:
                await session.commit()
                logger.info(f"Scheduler: Committed DB changes. Successful sends: {successful_sends}, Failed sends: {failed_sends}, Disabled reminders for: {len(users_to_disable_reminders)} users.")
            except Exception as e_commit:
                logger.error(f"Scheduler: Error committing session after processing reminders: {e_commit}")
                await session.rollback()
        else:
            logger.info("Scheduler: No DB changes to commit regarding reminders.")
            # Можливо, варто закрити сесію тут, але вона закриється автоматично