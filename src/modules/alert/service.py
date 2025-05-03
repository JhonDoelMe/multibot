# src/modules/alert/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
from aiogram import Bot
import pytz

from src import config

logger = logging.getLogger(__name__)

# Константы API
UKRAINEALARM_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"

# Параметры Retry
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

# Часовой пояс Украины
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типов тревог на эмодзи
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️",
    "NUCLEAR": "☢️",
    "INFO": "ℹ️",
    "UNKNOWN": "❓"
}

async def get_active_alerts(bot: Bot) -> Optional[List[Dict[str, Any]]]:
    """
    Получает список активных тревог с API UkraineAlarm.

    Args:
        bot: Экземпляр бота Aiogram (для совместимости с текущей архитектурой).

    Returns:
        Список словарей с данными об активных тревогах или None при ошибке.
    """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        return None

    headers = {
        "Authorization": config.UKRAINEALARM_API_TOKEN,
        "Accept": "application/json"
    }
    last_exception = None

    logger.info(f"Requesting UkraineAlarm alerts from {UKRAINEALARM_API_URL}")
    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch UA alerts")
                async with session.get(UKRAINEALARM_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
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
                        logger.error(f"Attempt {attempt + 1}: UA Alerts Error {response.status}. Response: {error_text}")
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

def format_alerts_message(alerts_data: Optional[List[Dict[str, Any]]]) -> str:
    """
    Форматирует ответ API тревог в сообщение для пользователя.

    Args:
        alerts_data: Список данных об алертах от API или None.

    Returns:
        Строка с сообщением о статусе тревог.
    """
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Статус тривог по Україні станом на {now_kyiv}:</b>\n"

    if alerts_data is None:
        return header + "\n⚠️ Не вдалося отримати дані. Спробуйте пізніше."

    if isinstance(alerts_data, dict) and "error" in alerts_data:
        error_code = alerts_data.get("error")
        error_msg = alerts_data.get("message", "Невідома помилка API")
        if error_code == 401:
            return header + "\nПомилка: Недійсний токен доступу до API тривог."
        elif error_code == 429:
            return header + "\nПомилка: Перевищено ліміт запитів до API тривог. Спробуйте за хвилину."
        else:
            return header + f"\nПомилка API ({error_code}): {error_msg}. Спробуйте пізніше."

    if not alerts_data:
        return header + "\n🟢 Наразі тривог немає. Все спокійно."

    active_regions = {}
    for region_alert_info in alerts_data:
        region_name = region_alert_info.get("regionName", "Невідомий регіон")
        if region_name not in active_regions:
            active_regions[region_name] = []
        for alert in region_alert_info.get("activeAlerts", []):
            alert_type = alert.get("type", "UNKNOWN")
            if alert_type not in active_regions[region_name]:
                active_regions[region_name].append(alert_type)

    if not active_regions:
        return header + "\n🟢 Наразі тривог на рівні областей немає (можливі тривоги в окремих громадах)."

    message_lines = [header]
    for region_name in sorted(active_regions.keys()):
        alerts_str = ", ".join([ALERT_TYPE_EMOJI.get(atype, atype) for atype in active_regions[region_name]])
        message_lines.append(f"🔴 <b>{region_name}:</b> {alerts_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")

    return "\n".join(message_lines)