# src/modules/alert/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import pytz
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
UA_ALERTS_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
UA_REGION_API_URL = "https://api.ukrainealarm.com/api/v3/regions"

# Часовой пояс Украины
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типов тревог на эмодзи (можно расширить)
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️",
    "NUCLEAR": "☢️",
    "INFO": "ℹ️",
    "UNKNOWN": "❓"
}

@cached(ttl=config.CACHE_TTL_ALERTS, key_builder=lambda *args, **kwargs: f"alerts:{kwargs.get('region_name', '').lower()}", namespace="alerts")
async def get_active_alerts(bot: Bot, region_name: str = "") -> Optional[List[Dict[str, Any]]]:
    """ Получает данные о тревогах по региону или всей Украине. """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        return {"status": "error", "message": "API token not configured"}

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    last_exception = None
    params = {} if not region_name else {"regionId": region_name}

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch alerts for region '{region_name or 'all'}'")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_ALERTS_API_URL, headers=headers, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"UkraineAlarm response: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm. Response: {await response.text()}")
                            return {"status": "error", "message": "Invalid JSON response"}
                    elif response.status == 401:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401). Response: {error_text[:200]}")
                        return {"status": "error", "message": f"Invalid API token: {error_text[:100]}"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: Region '{region_name}' not found by UkraineAlarm (404).")
                        return {"status": "error", "message": "Region not found"}
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Server Error {response.status}. Retrying...")
                    else:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Error {response.status}. Response: {error_text[:200]}")
                        return {"status": "error", "message": f"Client error {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching alerts: {e}", exc_info=True)
            return {"status": "error", "message": "Internal processing error"}

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next alert retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {config.MAX_RETRIES} attempts failed for alerts (region: {region_name or 'all'}). Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"status": "error", "message": f"Server error {last_exception.status} after retries"}
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                return {"status": "error", "message": "Network error after retries"}
            elif isinstance(last_exception, asyncio.TimeoutError):
                return {"status": "error", "message": "Timeout error after retries"}
            else:
                return {"status": "error", "message": "Failed after multiple retries"}
    return {"status": "error", "message": "Failed after all alert retries"}

@cached(ttl=config.CACHE_TTL_ALERTS, key_builder=lambda *args, **kwargs: "regions", namespace="alerts")
async def get_regions(bot: Bot) -> Optional[Dict[str, Any]]:
    """ Получает список регионов. """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        return {"status": "error", "message": "API token not configured"}

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    last_exception = None

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch regions")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_REGION_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"UkraineAlarm regions response: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm. Response: {await response.text()}")
                            return {"status": "error", "message": "Invalid JSON response"}
                    elif response.status == 401:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401). Response: {error_text[:200]}")
                        return {"status": "error", "message": f"Invalid API token: {error_text[:100]}"}
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Server Error {response.status}. Retrying...")
                    else:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Error {response.status}. Response: {error_text[:200]}")
                        return {"status": "error", "message": f"Client error {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching regions: {e}", exc_info=True)
            return {"status": "error", "message": "Internal processing error"}

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next region retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {config.MAX_RETRIES} attempts failed for regions. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"status": "error", "message": f"Server error {last_exception.status} after retries"}
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                return {"status": "error", "message": "Network error after retries"}
            elif isinstance(last_exception, asyncio.TimeoutError):
                return {"status": "error", "message": "Timeout error after retries"}
            else:
                return {"status": "error", "message": "Failed after multiple retries"}
    return {"status": "error", "message": "Failed after all region retries"}

def format_alerts_message(alert_data: Optional[List[Dict[str, Any]]], region_name: str = "") -> str:
    """ Форматирует сообщение о тревогах. """
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    region_display = f" у регіоні {region_name}" if region_name else " по Україні"
    header = f"<b>🚨 Статус тривог{region_display} станом на {now_kyiv}:</b>\n"

    if alert_data is None:
        return header + "\n😥 Не вдалося отримати дані. Спробуйте пізніше."
    if isinstance(alert_data, dict) and "status" in alert_data:
        error_msg = alert_data.get("message", "Невідома помилка API")
        return header + f"\n😥 Помилка: {error_msg}. Спробуйте пізніше."

    # Проверяем формат ответа API
    active_regions = {}
    if alert_data and isinstance(alert_data, list) and alert_data:
        if "activeAlerts" in alert_data[0]:  # Формат справочной версии
            for region_alert_info in alert_data:
                reg_name = region_alert_info.get("regionName", "Невідомий регіон")
                if reg_name not in active_regions:
                    active_regions[reg_name] = []
                for alert in region_alert_info.get("activeAlerts", []):
                    alert_type = alert.get("type", "UNKNOWN").upper()
                    if alert_type not in active_regions[reg_name]:
                        active_regions[reg_name].append(alert_type)
        else:  # Формат текущей версии
            for alert in alert_data:
                if alert.get("status") != "active" and alert.get("type") != "air_raid":
                    continue
                reg_name = alert.get("regionName", "Невідомий регіон")
                alert_type = alert.get("type", "UNKNOWN").upper()
                if reg_name not in active_regions:
                    active_regions[reg_name] = []
                if alert_type not in active_regions[reg_name]:
                    active_regions[reg_name].append(alert_type)

    if not active_regions:
        return header + "\n🟢 Наразі тривог немає. Все спокійно."

    message_lines = [header]
    for reg_name in sorted(active_regions.keys()):
        alerts_str = ", ".join([ALERT_TYPE_EMOJI.get(atype, atype) for atype in active_regions[reg_name]])
        message_lines.append(f"🔴 <b>{reg_name}:</b> {alerts_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")
    return "\n".join(message_lines)