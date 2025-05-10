# src/modules/alert/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List # List використовується
from datetime import datetime
import pytz
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
UA_ALERTS_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
UA_REGION_API_URL = "https://api.ukrainealarm.com/api/v3/regions" # Може знадобитися для маппінгу ID на імена

# Часовой пояс Украины
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типів тривог на емодзі
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️",
    "NUCLEAR": "☢️",
    "INFO": "ℹ️",
    "UNKNOWN": "❓"
}

# Вспомогательная функція для форматування помилок API
def _generate_ualarm_api_error(status_code: int, message: str, service_name: str = "UkraineAlarm") -> Dict[str, Any]:
    logger.error(f"{service_name} API Error: Code {status_code}, Message: {message}")
    # Додаємо "error_source" для консистентності з іншими модулями, якщо потрібно
    return {"status": "error", "code": status_code, "message": message, "error_source": service_name}


@cached(ttl=config.CACHE_TTL_ALERTS, key_builder=lambda *args, **kwargs: f"ualarm:alerts:v3:{kwargs.get('region_id', 'all')}", namespace="alerts")
async def get_active_alerts(bot: Bot, region_id: str = "") -> Dict[str, Any]:
    """
    Отримує дані про тривоги по ID регіону або всій Україні з UkraineAlarm API v3.
    region_id: ID регіону. Пустий рядок - вся Україна.
    Повертає словник: {"status": "success", "data": List[Dict]} або {"status": "error", ...}
    """
    if not config.UKRAINEALARM_API_TOKEN:
        return _generate_ualarm_api_error(500, "API токен UkraineAlarm (UKRAINEALARM_API_TOKEN) не налаштовано.")

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    params = {"regionId": region_id} if region_id else {}
    last_exception = None
    request_description = f"region_id '{region_id or 'all'}'"

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch alerts for {request_description} from UkraineAlarm")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_ALERTS_API_URL, headers=headers, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500] # Для логів

                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"UkraineAlarm API v3 response for {request_description}: {str(data)[:300]}")

                            # API v3 для /alerts (навіть без regionId) повертає список регіонів.
                            # Кожен елемент списку - це об'єкт регіону, який містить поле activeAlerts (список).
                            if not isinstance(data, list):
                                logger.error(f"UkraineAlarm API v3 response for {request_description} is not a list: {type(data)}")
                                return _generate_ualarm_api_error(500, "Некоректний формат відповіді API (очікувався список регіонів).")
                            
                            # Перевіримо, чи кожен елемент є словником (хоча б перший, якщо список не порожній)
                            if data and not all(isinstance(item, dict) for item in data):
                                logger.error(f"UkraineAlarm API v3 list for {request_description} contains non-dict elements.")
                                return _generate_ualarm_api_error(500, "Некоректний формат даних у списку регіонів API.")

                            return {"status": "success", "data": data} # Повертаємо весь список регіонів
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm for {request_description}. Response: {response_text_preview}")
                            last_exception = Exception("Невірний формат JSON відповіді від UkraineAlarm.")
                            return _generate_ualarm_api_error(500, "Невірний формат JSON відповіді.")
                        except Exception as e: # Інші помилки при обробці успішної відповіді
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful UkraineAlarm response for {request_description}: {e}", exc_info=True)
                            return _generate_ualarm_api_error(500, f"Помилка обробки даних API: {e}")

                    elif response.status == 401: # Невірний токен
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401) for {request_description}. Response: {response_text_preview}")
                        return _generate_ualarm_api_error(401, "Невірний API токен.")
                    elif response.status == 404: # Може бути, якщо regionId некоректний або ендпоінт змінився
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm API returned 404 for {request_description}. Response: {response_text_preview}")
                        return _generate_ualarm_api_error(404, "Ресурс не знайдено (перевірте ID регіону або URL API).")
                    elif response.status == 429: # Rate limit
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=429, message="Rate limit exceeded (UkraineAlarm)")
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm RateLimit Error (429) for {request_description}. Retrying...")
                    elif response.status >= 500: # Серверні помилки
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} (UkraineAlarm)")
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Server Error {response.status} for {request_description}. Retrying...")
                    else: # Інші клієнтські помилки
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Client Error {response.status} for {request_description}. Response: {response_text_preview}")
                        return _generate_ualarm_api_error(response.status, f"Клієнтська помилка API: {response.status}.")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm for {request_description}: {e}. Retrying...")
        except Exception as e: # Будь-які інші винятки
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching alerts for {request_description}: {e}", exc_info=True)
            return _generate_ualarm_api_error(500, "Внутрішня помилка при обробці запиту тривог.")

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next UkraineAlarm alert retry for {request_description}...")
            await asyncio.sleep(delay)
        else: # Всі спроби вичерпано
            error_message = f"Не вдалося отримати дані тривог для {request_description} після {config.MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            
            final_error_code = 503 # Service Unavailable
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504 # Gateway Timeout
            return _generate_ualarm_api_error(final_error_code, error_message)
            
    return _generate_ualarm_api_error(500, f"Не вдалося отримати дані тривог для {request_description} (неочікуваний вихід).")


@cached(ttl=config.CACHE_TTL_REGIONS, key="ualarm:regions:v3", namespace="alerts") # Змінено ключ для v3
async def get_regions(bot: Bot) -> Dict[str, Any]:
    """
    Отримує список регіонів від UkraineAlarm API v3.
    Повертає словник: {"status": "success", "data": List[Dict]} або {"status": "error", ...}
    """
    if not config.UKRAINEALARM_API_TOKEN:
        return _generate_ualarm_api_error(500, "API токен UkraineAlarm (UKRAINEALARM_API_TOKEN) не налаштовано для отримання регіонів.", service_name="UkraineAlarm Regions")

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    last_exception = None

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch regions from UkraineAlarm v3")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_REGION_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500]

                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"UkraineAlarm regions v3 response: {str(data)[:300]}")
                            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                                logger.error(f"UkraineAlarm regions API v3 response is not a list of dicts: {type(data)}")
                                return _generate_ualarm_api_error(500, "Некоректний формат відповіді API (регіони).", service_name="UkraineAlarm Regions")
                            return {"status": "success", "data": data}
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm regions. Response: {response_text_preview}")
                            last_exception = Exception("Невірний формат JSON відповіді від UkraineAlarm (регіони).")
                            return _generate_ualarm_api_error(500, "Невірний формат JSON відповіді (регіони).", service_name="UkraineAlarm Regions")
                        except Exception as e:
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful UkraineAlarm regions response: {e}", exc_info=True)
                            return _generate_ualarm_api_error(500, f"Помилка обробки даних API (регіони): {e}", service_name="UkraineAlarm Regions")
                    # Обробка помилок аналогічно до get_active_alerts
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401) for regions. Response: {response_text_preview}")
                        return _generate_ualarm_api_error(401, "Невірний API токен (регіони).", service_name="UkraineAlarm Regions")
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=429, message="Rate limit exceeded (UkraineAlarm Regions)")
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Regions RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} (UkraineAlarm Regions)")
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Regions Server Error {response.status}. Retrying...")
                    else: # 404 та інші клієнтські помилки
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Regions Client Error {response.status}. Response: {response_text_preview}")
                        return _generate_ualarm_api_error(response.status, f"Клієнтська помилка API (регіони): {response.status}.", service_name="UkraineAlarm Regions")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm regions: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching regions: {e}", exc_info=True)
            return _generate_ualarm_api_error(500, "Внутрішня помилка при обробці запиту регіонів.", service_name="UkraineAlarm Regions")

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next UkraineAlarm region retry...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати список регіонів після {config.MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            
            final_error_code = 503
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504
            return _generate_ualarm_api_error(final_error_code, error_message, service_name="UkraineAlarm Regions")

    return _generate_ualarm_api_error(500, "Не вдалося отримати список регіонів (неочікуваний вихід).", service_name="UkraineAlarm Regions")


def format_alerts_message(api_response: Dict[str, Any], selected_region_name: Optional[str] = None) -> str:
    """
    Форматує повідомлення про тривоги від UkraineAlarm API v3.
    api_response: Результат виклику get_active_alerts.
    selected_region_name: Ім'я регіону, якщо запит був по конкретному регіону (для заголовка).
                        Якщо не передано або None, вважається, що запит був по всій Україні.
    """
    now_kyiv_str = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    
    region_display_for_header = ""
    if selected_region_name and isinstance(selected_region_name, str) and selected_region_name.strip():
        region_display_for_header = f" у регіоні <b>{selected_region_name.strip()}</b>"
    elif not selected_region_name : # Якщо selected_region_name порожній рядок або None (запит по всій Україні)
        region_display_for_header = " по Україні"
        
    header = f"<b>🚨 Статус тривог{region_display_for_header} станом на {now_kyiv_str}:</b>\n"

    if api_response.get("status") == "error":
        error_msg = api_response.get("message", "Невідома помилка API.")
        error_code = api_response.get("code", "N/A")
        # Якщо запит був для конкретного регіону і сталася помилка, згадуємо його
        location_context = f" для регіону '{selected_region_name}'" if selected_region_name else ""
        return header + f"\n😥 Помилка отримання даних{location_context}: {error_msg} (Код: {error_code}).\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>"

    # `data` - це список регіонів, кожен зі своїм списком `activeAlerts`
    list_of_regions_data = api_response.get("data")

    if list_of_regions_data is None: # Малоймовірно, якщо status == "success"
        logger.error("format_alerts_message (UkraineAlarm): 'data' key missing in successful API response.")
        return header + "\n😥 Помилка обробки даних: відсутні дані тривог.\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>"
    
    if not isinstance(list_of_regions_data, list):
        logger.error(f"format_alerts_message (UkraineAlarm): API data is not a list, but {type(list_of_regions_data)}")
        return header + "\n😥 Помилка обробки даних: некоректний тип відповіді API.\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>"

    active_alerts_summary: Dict[str, List[str]] = {} # Регіон -> список типів тривог (емодзі)
    any_alert_active_overall = False

    for region_info in list_of_regions_data:
        if not isinstance(region_info, dict):
            logger.warning(f"Skipping non-dict item in region list: {region_info}")
            continue
        
        region_name_api = region_info.get("regionName")
        if not region_name_api or not isinstance(region_name_api, str):
            logger.warning(f"Skipping region with missing or invalid name: {region_info}")
            continue
            
        current_active_alerts_in_region = region_info.get("activeAlerts", [])
        if not isinstance(current_active_alerts_in_region, list):
            logger.warning(f"activeAlerts for {region_name_api} is not a list: {current_active_alerts_in_region}")
            continue

        if current_active_alerts_in_region: # Якщо є активні тривоги в цьому регіоні
            any_alert_active_overall = True
            alert_emojis_in_region = set() # Використовуємо set для унікальних емодзі
            for alert_detail in current_active_alerts_in_region:
                if isinstance(alert_detail, dict):
                    alert_type_api = alert_detail.get("type", "UNKNOWN").upper()
                    alert_emojis_in_region.add(ALERT_TYPE_EMOJI.get(alert_type_api, ALERT_TYPE_EMOJI["UNKNOWN"]))
            
            if alert_emojis_in_region: # Якщо вдалося зібрати типи тривог
                # Сортуємо емодзі для консистентного вигляду
                active_alerts_summary[region_name_api] = sorted(list(alert_emojis_in_region))

    if not any_alert_active_overall or not active_alerts_summary:
        # Повідомлення, якщо немає активних тривог взагалі, або якщо запит був для конкретного регіону і там немає тривог
        no_alerts_message = "🟢 Наразі тривог немає. Все спокійно."
        if selected_region_name and any(reg_info.get("regionName") == selected_region_name for reg_info in list_of_regions_data if isinstance(reg_info, dict)):
            # Якщо запит був для конкретного регіону і цей регіон є у відповіді, але без активних тривог
             no_alerts_message = f"🟢 У регіоні <b>{selected_region_name}</b> наразі тривог немає. Все спокійно."
        return header + f"\n{no_alerts_message}\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>"

    message_lines = [header]
    # Сортуємо регіони за назвою для консистентного відображення
    for reg_name_sorted in sorted(active_alerts_summary.keys()):
        alert_emojis_str = ", ".join(active_alerts_summary[reg_name_sorted])
        message_lines.append(f"🔴 <b>{reg_name_sorted}:</b> {alert_emojis_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")
    return "\n".join(message_lines)