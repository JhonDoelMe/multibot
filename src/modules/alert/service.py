# src/modules/alert/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from aiogram import Bot

from src import config

logger = logging.getLogger(__name__)

# Константы API
UKRAINEALARM_API_URL = "https://alerts.in.ua/api/v2/alerts/active.json"

# Параметры Retry
MAX_RETRIES = 3
INITIAL_DELAY = 1  # Секунда

# Эмодзи для типов тревог
ALERT_TYPE_EMOJI = {
    "air": "✈️",
    "artillery": "💥",
    "urban": "🏙️",
    "chemical": "☣️",
    "nuclear": "☢️"
}

async def get_active_alerts(bot: Bot) -> Optional[Dict[str, Any]]:
    """ Получает данные об активных тревогах в Украине. """
    if not config.UKRAINEALARM_API_KEY:
        logger.error("UkraineAlarm API key (UKRAINEALARM_API_KEY) is not configured.")
        return None

    headers = {
        "X-API-Key": config.UKRAINEALARM_API_KEY,
        "Accept": "application/json"
    }
    last_exception = None

    logger.info("Requesting UA alerts...")
    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch UA alerts")
                async with session.get(UKRAINEALARM_API_URL, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"UA Alerts response: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UA Alerts. Response: {await response.text()}")
                            return None
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid UA Alerts API key (401).")
                        return None
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UA Alerts RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UA Alerts Server Error {response.status}. Retrying...")
                    else:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: UA Alerts Error {response.status}. Response: {error_text[:200]}")
                        return None

            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1}: Network error connecting to UA Alerts: {e}. Retrying...")
            except Exception as e:
                logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching UA alerts: {e}", exc_info=True)
                return None

            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_DELAY * (2 ** attempt)
                logger.info(f"Waiting {delay} seconds before next UA alerts retry...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for UA alerts. Last error: {last_exception!r}")
                return None
    return None

def format_alerts_message(alerts_data: Dict[str, Any]) -> str:
    """ Форматирует сообщение с информацией о тревогах. """
    try:
        if not alerts_data or not isinstance(alerts_data, dict):
            return "⚠️ Дані про тривоги відсутні або некоректні. Спробуйте пізніше."

        alerts = alerts_data.get("alerts", [])
        if not alerts:
            return "🟢 Наразі немає активних тривог в Україні."

        message_lines = ["<b>⚠️ Активні тривоги в Україні:</b>\n"]
        for alert in alerts:
            region = alert.get("region_title", "Невідомий регіон")
            alert_type = alert.get("type", "невідомий").lower()
            emoji = ALERT_TYPE_EMOJI.get(alert_type, "❓")
            last_updated = alert.get("updated_at", "невідомо")
            message_lines.append(f"{emoji} {region} ({alert_type}) — Оновлено: {last_updated}")
        return "\n".join(message_lines)
    except Exception as e:
        logger.exception(f"Error formatting alerts message: {e}")
        return "😥 Помилка обробки даних про тривоги."