# src/modules/alert_backup/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List # List використовується
from datetime import datetime
import pytz # pytz потрібен для TZ_KYIV
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
ALERTS_IN_UA_API_URL = "https://api.alerts.in.ua/v1/alerts/active.json"

# Часовий пояс України
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппінг типів тривог на емодзі
ALERT_TYPE_EMOJI_BACKUP = {
    "air_raid": "🚨", # Повітряна тривога
    "artillery_shelling": "💣", # Артилерійський обстріл
    "urban_fights": "💥", # Вуличні бої
    "chemical": "☣️", # Хімічна загроза
    "nuclear": "☢️", # Ядерна загроза
    "info": "ℹ️", # Інформаційне сповіщення (якщо API таке повертає)
    "unknown": "❓", # Невідомий тип
}

# Допоміжна функція для форматування помилок API
def _generate_alerts_in_ua_api_error(status_code: int, message: str, service_name: str = "Alerts.in.ua") -> Dict[str, Any]:
    logger.error(f"{service_name} API Error: Code {status_code}, Message: {message}")
    return {"status": "error", "code": status_code, "message": message, "error_source": service_name}


@cached(ttl=config.CACHE_TTL_ALERTS_BACKUP, key="alerts_in_ua:active_alerts", namespace="alerts_backup")
async def get_backup_alerts(bot: Bot) -> Dict[str, Any]:
    """
    Отримує активні тривоги з alerts.in.ua.
    Повертає словник: {"status": "success", "data": List[Dict]} або {"status": "error", ...}
    """
    if not config.ALERTS_IN_UA_TOKEN:
        return _generate_alerts_in_ua_api_error(500, "Резервний API токен (ALERTS_IN_UA_TOKEN) не налаштовано.")

    headers = {"Authorization": f"Bearer {config.ALERTS_IN_UA_TOKEN}"}
    last_exception = None

    for attempt in range(config.MAX_RETRIES): # Використовуємо MAX_RETRIES з глобального конфігу
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch backup alerts from Alerts.in.ua")
            async with aiohttp.ClientSession() as session:
                async with session.get(ALERTS_IN_UA_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500]

                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"Alerts.in.ua API response JSON: {str(data)[:300]}")
                            
                            # Перевіряємо, чи відповідь є словником і містить ключ "alerts"
                            if not isinstance(data, dict):
                                logger.error(f"Alerts.in.ua: API response is not a dictionary, but {type(data)}.")
                                return _generate_alerts_in_ua_api_error(500, "Некоректний формат відповіді від резервного API (очікувався словник).")

                            alerts_list = data.get("alerts")
                            if alerts_list is None: # Ключ "alerts" відсутній
                                logger.error("Alerts.in.ua: 'alerts' key is missing in the response dictionary.")
                                return _generate_alerts_in_ua_api_error(500, "Некоректний формат відповіді від резервного API (відсутній ключ 'alerts').")
                            
                            if not isinstance(alerts_list, list): # Значення за ключем "alerts" не є списком
                                logger.error(f"Alerts.in.ua: 'alerts' value is not a list, but {type(alerts_list)}.")
                                return _generate_alerts_in_ua_api_error(500, "Некоректний формат відповіді від резервного API (дані тривог не є списком).")

                            # Перевірка, чи кожен елемент у списку alerts_list є словником
                            if not all(isinstance(item, dict) for item in alerts_list):
                                logger.error("Alerts.in.ua: Not all items in 'alerts' list are dictionaries.")
                                return _generate_alerts_in_ua_api_error(500, "Некоректний формат даних у списку тривог (окремі елементи не є словниками).")

                            logger.debug(f"Extracted {len(alerts_list)} alerts from backup API (Alerts.in.ua)")
                            return {"status": "success", "data": alerts_list} # Повертаємо сам список тривог
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from Alerts.in.ua. Response: {response_text_preview}")
                            last_exception = Exception("Невірний формат JSON відповіді від Alerts.in.ua.")
                            return _generate_alerts_in_ua_api_error(500, "Невірний формат JSON відповіді від резервного API.")
                        except Exception as e:
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful backup alerts response from Alerts.in.ua: {e}", exc_info=True)
                            return _generate_alerts_in_ua_api_error(500, f"Помилка обробки даних резервного API: {e}")

                    elif response.status == 401: # Невірний токен
                        logger.error(f"Attempt {attempt + 1}: Invalid Alerts.in.ua API token (401). Response: {response_text_preview}")
                        return _generate_alerts_in_ua_api_error(401, "Невірний токен резервного API.")
                    elif response.status == 404: # Ресурс не знайдено
                        logger.warning(f"Attempt {attempt + 1}: Received 404 from Alerts.in.ua. URL: {ALERTS_IN_UA_API_URL}. Response: {response_text_preview}")
                        return _generate_alerts_in_ua_api_error(404, "Резервне API не знайдено (404).")
                    elif response.status == 429: # Rate limit
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=429, message="Rate limit exceeded (Alerts.in.ua)")
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua RateLimit Error (429). Retrying...")
                    elif response.status >= 500: # Серверні помилки
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} (Alerts.in.ua)")
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua Server Error {response.status}. Retrying...")
                    else: # Інші клієнтські помилки
                        logger.error(f"Attempt {attempt + 1}: Alerts.in.ua Client Error {response.status}. Response: {response_text_preview}")
                        return _generate_alerts_in_ua_api_error(response.status, f"Помилка резервного API {response.status}.")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to Alerts.in.ua: {e}. Retrying...")
        except Exception as e: # Будь-які інші винятки
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching backup alerts: {e}", exc_info=True)
            return _generate_alerts_in_ua_api_error(500, "Внутрішня помилка обробки резервних тривог.")

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt) # Використовуємо INITIAL_DELAY з глобального конфігу
            logger.info(f"Waiting {delay} seconds before next backup alert (Alerts.in.ua) retry...")
            await asyncio.sleep(delay)
        else: # Всі спроби вичерпано
            error_message = f"Не вдалося отримати резервні дані тривог (Alerts.in.ua) після {config.MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)

            final_error_code = 503 # Service Unavailable
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504 # Gateway Timeout
            return _generate_alerts_in_ua_api_error(final_error_code, error_message)
            
    return _generate_alerts_in_ua_api_error(500, "Не вдалося отримати резервні дані тривог (Alerts.in.ua) (неочікуваний вихід).")


def format_backup_alerts_message(api_response: Dict[str, Any]) -> str:
    """ Форматує повідомлення про тривоги з alerts.in.ua """
    now_kyiv_str = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Резервний статус тривог станом на {now_kyiv_str}:</b>\n"

    if api_response.get("status") == "error":
        error_msg = api_response.get("message", "Невідома помилка резервного API.")
        # error_code = api_response.get("code", "N/A") # Можна додати код, якщо потрібно
        return header + f"\n😥 Помилка: {error_msg}\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>"

    # Очікуємо, що "data" - це список тривог
    alerts_data_list = api_response.get("data")
    
    if alerts_data_list is None: # Малоймовірно, якщо status == "success"
        logger.error("format_backup_alerts_message (Alerts.in.ua): 'data' key missing in successful API response.")
        return header + "\n😥 Помилка обробки даних (відсутні дані тривог).\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>"
    
    if not isinstance(alerts_data_list, list):
        logger.error(f"format_backup_alerts_message (Alerts.in.ua): API data is not a list, but {type(alerts_data_list)}")
        return header + "\n😥 Помилка обробки даних (неправильний тип відповіді API).\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>"

    if not alerts_data_list: # Якщо список тривог порожній
        return header + "\n🟢 Наразі тривог немає. Все спокійно (резервне джерело).\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>"

    # Збираємо інформацію про тривоги, групуючи за регіоном (location_title або location_oblast)
    active_regions_alerts: Dict[str, set] = {} # Регіон -> set типів тривог (емодзі)

    for alert_item in alerts_data_list:
        if not isinstance(alert_item, dict):
            logger.warning(f"Skipping non-dict item in alerts_data_list (Alerts.in.ua): {alert_item}")
            continue
            
        # API alerts.in.ua може використовувати різні поля для назви регіону/місцевості.
        # Пріоритет: location_title, потім location_oblast.
        # location_title може бути "м. Київ", "Київська область", або назва громади.
        # location_oblast зазвичай містить назву області.
        
        location_title = alert_item.get("location_title")
        location_oblast = alert_item.get("location_oblast")
        
        display_region_name = None
        if location_title and isinstance(location_title, str):
            display_region_name = location_title.strip()
        elif location_oblast and isinstance(location_oblast, str):
            display_region_name = location_oblast.strip()
        
        if not display_region_name:
            logger.warning(f"Skipping alert item with no identifiable region name (Alerts.in.ua): {alert_item}")
            continue

        alert_type_api = alert_item.get("alert_type", "unknown").lower() # API повертає в snake_case
        alert_emoji = ALERT_TYPE_EMOJI_BACKUP.get(alert_type_api, ALERT_TYPE_EMOJI_BACKUP["unknown"])
        
        if display_region_name not in active_regions_alerts:
            active_regions_alerts[display_region_name] = set()
        active_regions_alerts[display_region_name].add(alert_emoji)

    if not active_regions_alerts: # Якщо після фільтрації нічого не залишилося
        return header + "\n🟢 Наразі тривог немає (після фільтрації). Все спокійно (резервне джерело).\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>"

    message_lines = [header]
    # Сортуємо за назвою регіону
    for region_name_sorted in sorted(active_regions_alerts.keys()):
        alerts_emojis_str = ", ".join(sorted(list(active_regions_alerts[region_name_sorted])))
        message_lines.append(f"🔴 <b>{region_name_sorted}:</b> {alerts_emojis_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе!")
    return "\n".join(message_lines)