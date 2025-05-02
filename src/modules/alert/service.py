# src/modules/alert/service.py

import logging
import aiohttp
import asyncio # <<< Добавляем asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz

from src import config

logger = logging.getLogger(__name__)

UKRAINEALARM_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
TZ_KYIV = pytz.timezone('Europe/Kyiv')
ALERT_TYPE_EMOJI = {
    "AIR": "🚨", "ARTILLERY": "💣", "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️", "NUCLEAR": "☢️", "INFO": "ℹ️", "UNKNOWN": "❓"
}

# Параметры для повторных попыток
MAX_RETRIES = 3
INITIAL_DELAY = 1 # Секунда

async def get_active_alerts() -> Optional[List[Dict[str, Any]]]:
    """ Получает список активных тревог с API UkraineAlarm с повторными попытками. """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        # Возвращаем словарь с ошибкой, чтобы обработчик мог ее показать
        return {"error": 500, "message": "API token not configured"}

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    logger.info(f"Requesting UkraineAlarm alerts from {UKRAINEALARM_API_URL}")

    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch UkraineAlarm alerts")
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(UKRAINEALARM_API_URL, timeout=15) as response: # Увеличим таймаут
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"UkraineAlarm API response: {data}")
                            return data # <<< Успех
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm API. Response: {await response.text()}")
                            return {"error": 500, "message": "Invalid JSON response"} # Не повторяем

                    # Ошибки, которые НЕ повторяем
                    elif response.status == 401:
                         logger.error(f"Attempt {attempt + 1}: UkraineAlarm API Error: Unauthorized (401).")
                         return {"error": 401, "message": "Invalid API Token"}
                    elif 400 <= response.status < 500 and response.status != 429: # Исключаем 429 из ошибок клиента
                         error_text = await response.text()
                         logger.error(f"Attempt {attempt + 1}: UkraineAlarm Client Error {response.status}. Response: {error_text[:200]}")
                         return {"error": response.status, "message": f"Client error {response.status}"}

                    # Ошибки сервера (5xx) и 429 (Too Many Requests) - ПОВТОРЯЕМ
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server/RateLimit error {response.status}")
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Server/RateLimit Error {response.status}. Retrying...")
                        # Переходим к блоку except для задержки
                    else: # Неожиданный статус
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from UkraineAlarm.")
                        last_exception = Exception(f"Unexpected status {response.status}")

        # Повторяем сетевые ошибки и таймауты
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm API: {e}. Retrying...")
        # Другие ошибки не повторяем
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred while fetching UkraineAlarm alerts: {e}", exc_info=True)
            return {"error": 500, "message": "Internal processing error"}

        # Ждем перед следующей попыткой
        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next UkraineAlarm retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for UkraineAlarm alerts. Last error: {last_exception!r}")
            # Возвращаем информацию о последней ошибке
            if isinstance(last_exception, aiohttp.ClientResponseError):
                 return {"error": last_exception.status, "message": f"API Error {last_exception.status} after retries"}
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                 return {"error": 503, "message": "Network error after retries"}
            elif isinstance(last_exception, asyncio.TimeoutError):
                  return {"error": 504, "message": "Timeout error after retries"}
            else:
                 return {"error": 500, "message": "Failed after multiple retries"}

    return {"error": 500, "message": "Failed after all retries"}


# Функция format_alerts_message остается БЕЗ ИЗМЕНЕНИЙ (из ответа #75)
# ... (ваш код format_alerts_message) ...
def format_alerts_message(alerts_data: Optional[List[Dict[str, Any]]]) -> str:
    # ... (код функции из ответа #75) ...
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Статус тривог по Україні станом на {now_kyiv}:</b>\n"
    if alerts_data is None:
        return header + "\nНе вдалося отримати дані. Спробуйте пізніше."
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
         return header + "\n🟢 Наразі тривог на рівні областей/громад немає."
    message_lines = [header]
    for region_name in sorted(active_regions.keys()):
         alerts_str = ", ".join([ALERT_TYPE_EMOJI.get(atype, atype) for atype in active_regions[region_name]])
         message_lines.append(f"🔴 <b>{region_name}:</b> {alerts_str}")
    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")
    return "\n".join(message_lines)