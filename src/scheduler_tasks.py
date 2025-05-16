# src/scheduler_tasks.py

import asyncio
import logging
from datetime import datetime, time as dt_time, timedelta, timezone

from sqlalchemy import select, extract, or_, cast, Integer # Додано cast, Integer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError, TelegramRetryAfter, TelegramForbiddenError,
    TelegramBadRequest, TelegramNotFound, TelegramConflictError
)

from src.db.models import User, ServiceChoice
from src.modules.weather.service import get_weather_data, format_weather_message
from src.modules.weather_backup.service import get_current_weather_weatherapi, format_weather_backup_message
from src import config

logger = logging.getLogger(__name__)

try:
    import pytz
    TZ_KYIV = pytz.timezone('Europe/Kyiv')
    logger.info("Scheduler: Kyiv timezone (Europe/Kyiv) loaded using pytz.")
except ImportError:
    logger.warning("Scheduler: pytz not installed. Using system's understanding of 'Europe/Kyiv' or UTC as fallback for Kyiv time.")
    if hasattr(config, 'TZ_KYIV') and config.TZ_KYIV:
        TZ_KYIV = config.TZ_KYIV
        logger.info(f"Scheduler: Kyiv timezone loaded from config: {config.TZ_KYIV_NAME if hasattr(config, 'TZ_KYIV_NAME') else 'Europe/Kyiv'}")
    else:
        logger.warning("Scheduler: TZ_KYIV not found in config and pytz not available. Using UTC as fallback.")
        TZ_KYIV = timezone.utc
except Exception as e_tz:
    logger.error(f"Scheduler: Error setting up Kyiv timezone: {e_tz}. Using UTC as fallback.")
    TZ_KYIV = timezone.utc


async def send_weather_reminders_task(
    session_factory: async_sessionmaker[AsyncSession],
    bot_instance: Bot
):
    if not TZ_KYIV:
        logger.critical("Scheduler: Kyiv timezone (TZ_KYIV) is not properly configured. Exiting task.")
        return

    now_localized = datetime.now(TZ_KYIV)
    current_time_for_check = now_localized.time().replace(second=0, microsecond=0)
    time_one_minute_ago = (now_localized - timedelta(minutes=1)).time().replace(second=0, microsecond=0)

    logger.info(f"Scheduler: Checking weather reminders for times around {current_time_for_check.strftime('%H:%M')} ({TZ_KYIV}). Will check current and previous minute.")

    async with session_factory() as session:
        # ВИПРАВЛЕННЯ: Використовуємо CAST для порівняння з Integer,
        # оскільки SQLite strftime повертає рядок, а PostgreSQL extract повертає число.
        # CAST(... AS INTEGER) працюватиме для обох.
        current_hour = current_time_for_check.hour
        current_minute = current_time_for_check.minute
        prev_hour = time_one_minute_ago.hour
        prev_minute = time_one_minute_ago.minute

        stmt = (
            select(User)
            .where(User.weather_reminder_enabled == True)
            .where(User.weather_reminder_time != None)
            .where(
                or_(
                    (cast(extract('hour', User.weather_reminder_time), Integer) == current_hour) &
                    (cast(extract('minute', User.weather_reminder_time), Integer) == current_minute),
                    
                    (cast(extract('hour', User.weather_reminder_time), Integer) == prev_hour) &
                    (cast(extract('minute', User.weather_reminder_time), Integer) == prev_minute)
                )
            )
        )
        
        result = await session.execute(stmt)
        users_to_remind = result.scalars().all()

        if not users_to_remind:
            logger.info(f"Scheduler: No users found for weather reminder for {time_one_minute_ago.strftime('%H:%M')} or {current_time_for_check.strftime('%H:%M')}.")
            return

        processed_users_for_this_run = set()
        logger.info(f"Scheduler: Found {len(users_to_remind)} potential users for weather reminder.")

        successful_sends = 0
        failed_sends = 0
        users_to_disable_reminders = []

        for user in users_to_remind:
            if user.user_id in processed_users_for_this_run:
                continue 
            
            if not user.preferred_city:
                logger.warning(f"Scheduler: User {user.user_id} has reminder enabled but no preferred_city set. Skipping.")
                continue
            
            logger.info(f"Scheduler: Processing reminder for user {user.user_id} (chat_id), city: {user.preferred_city}, set time: {user.weather_reminder_time.strftime('%H:%M') if user.weather_reminder_time else 'N/A'}")
            
            weather_data_response: Optional[dict] = None
            formatted_weather: str = f"😔 Не вдалося отримати дані про погоду для м. {user.preferred_city} для вашого нагадування."
            is_error_getting_weather = True

            try:
                service_name_log = ""
                if user.preferred_weather_service == ServiceChoice.OPENWEATHERMAP:
                    service_name_log = "OWM"
                    weather_data_response = await get_weather_data(bot_instance, city_name=user.preferred_city)
                    if weather_data_response and weather_data_response.get("status") != "error" and str(weather_data_response.get("cod")) == "200":
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

            message_to_send = formatted_weather
            if not is_error_getting_weather:
                reminder_time_str = user.weather_reminder_time.strftime('%H:%M') if user.weather_reminder_time else "встановлений час"
                reminder_header = f"🔔 <b>Нагадування про погоду ({reminder_time_str})</b>\n\n"
                message_to_send = reminder_header + formatted_weather
            
            try:
                await bot_instance.send_message(user.user_id, message_to_send)
                logger.info(f"Scheduler: Sent weather reminder to user {user.user_id} for city {user.preferred_city}.")
                successful_sends += 1
                processed_users_for_this_run.add(user.user_id)
            except TelegramRetryAfter as e_retry:
                logger.warning(f"Scheduler: Flood control for user {user.user_id}. Retry after {e_retry.retry_after}s. Skipping.")
                failed_sends += 1
                await asyncio.sleep(e_retry.retry_after) 
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
            
            if len(users_to_remind) > 1 and user.user_id != users_to_remind[-1].user_id : 
                await asyncio.sleep(0.1)

        if users_to_disable_reminders:
            logger.info(f"Scheduler: Disabling reminders for {len(users_to_disable_reminders)} users.")
            for user_to_disable in users_to_disable_reminders:
                if user_to_disable in session:
                    user_to_disable.weather_reminder_enabled = False
                    session.add(user_to_disable)
                else: 
                    user_from_db = await session.get(User, user_to_disable.user_id)
                    if user_from_db:
                        user_from_db.weather_reminder_enabled = False
                        session.add(user_from_db)
        
        if users_to_disable_reminders or successful_sends > 0 or failed_sends > 0:
            try:
                await session.commit()
                logger.info(f"Scheduler: Committed DB changes. Successful: {successful_sends}, Failed: {failed_sends}, Disabled: {len(users_to_disable_reminders)}.")
            except Exception as e_commit:
                logger.error(f"Scheduler: Error committing session after processing reminders: {e_commit}")
                await session.rollback()
        else:
            logger.info("Scheduler: No DB changes to commit regarding reminders.")