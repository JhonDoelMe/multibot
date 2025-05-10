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
UA_REGION_API_URL = "https://api.ukrainealarm.com/api/v3/regions" # Не используется в текущей логике отображения, но оставим

# Часовой пояс Украины
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типов тревог на эмодзи
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️",
    "NUCLEAR": "☢️",
    "INFO": "ℹ️", # Добавим INFO, если API его вернет
    "UNKNOWN": "❓" # Для неизвестных типов
}

# Вспомогательная функция для более чистого возврата ошибок API
def _format_api_error(status_code: int, message: str, service_name: str = "API") -> Dict[str, Any]:
    return {"status": "error", "code": status_code, "message": f"{service_name}: {message}"}


@cached(ttl=config.CACHE_TTL_ALERTS, key_builder=lambda *args, **kwargs: f"alerts:v3:{kwargs.get('region_id', 'all')}", namespace="alerts")
async def get_active_alerts(bot: Bot, region_id: str = "") -> Dict[str, Any]: # Изменен тип возврата
    """
    Получает данные о тревогах по ID региона или всей Украине.
    region_id: ID региона из API (например, "32"). Пустая строка - вся Украина.
    Возвращает словарь: {"status": "success", "data": List[Dict]} или {"status": "error", ...}
    """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        return _format_api_error(500, "API token not configured", "UkraineAlarm")

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    last_exception = None
    # API v3 ожидает regionId в параметрах, если он есть
    params = {"regionId": region_id} if region_id else {}
    # Если region_id пуст, API вернет все активные тревоги по стране, сгруппированные по регионам

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch alerts for region_id '{region_id or 'all'}' from UkraineAlarm")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_ALERTS_API_URL, headers=headers, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500] # Для логов

                    if response.status == 200:
                        try:
                            # API UkraineAlarm v3 возвращает список объектов региона,
                            # каждый из которых содержит список activeAlerts
                            data = await response.json()
                            logger.debug(f"UkraineAlarm response: {data}")

                            if not isinstance(data, list):
                                logger.error(f"UkraineAlarm API v3 response is not a list: {data}")
                                return _format_api_error(500, "Invalid API response format (not a list)", "UkraineAlarm")
                            
                            # Тут data - это уже список регионов с их тревогами,
                            # который и нужен для format_alerts_message
                            return {"status": "success", "data": data}
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm. Response: {response_text_preview}")
                            return _format_api_error(500, "Invalid JSON response", "UkraineAlarm")
                        except Exception as e:
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful UkraineAlarm response: {e}", exc_info=True)
                            return _format_api_error(500, f"Error processing API data: {e}", "UkraineAlarm")

                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401). Response: {response_text_preview}")
                        return _format_api_error(401, "Invalid API token", "UkraineAlarm")
                    elif response.status == 404: # Может быть, если regionId некорректный
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm API returned 404 (region_id: '{region_id}'). Response: {response_text_preview}")
                        return _format_api_error(404, "Resource not found (check region_id)", "UkraineAlarm")
                    elif response.status == 429: # Rate limit
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded (UkraineAlarm)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm RateLimit Error (429). Retrying...")
                    elif response.status >= 500: # Серверные ошибки
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} (UkraineAlarm)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Server Error {response.status}. Retrying...")
                    else: # Другие клиентские ошибки
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Client Error {response.status}. Response: {response_text_preview}")
                        return _format_api_error(response.status, f"Client error {response.status}", "UkraineAlarm")

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching alerts: {e}", exc_info=True)
            return _format_api_error(500, "Internal processing error", "UkraineAlarm")

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next UkraineAlarm alert retry...")
            await asyncio.sleep(delay)
        else: # Все попытки исчерпаны
            logger.error(f"All {config.MAX_RETRIES} attempts failed for UkraineAlarm alerts (region_id: {region_id or 'all'}). Last error: {last_exception!r}")
            error_message = "Failed after multiple retries"
            status_code = 500
            if isinstance(last_exception, aiohttp.ClientResponseError):
                error_message = f"API error {last_exception.status} after retries"
                status_code = last_exception.status
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                error_message = "Network error after retries"
                status_code = 504 # Gateway Timeout
            elif isinstance(last_exception, asyncio.TimeoutError):
                error_message = "Timeout error after retries"
                status_code = 504
            elif last_exception:
                error_message = f"Failed after retries: {str(last_exception)}"
            return _format_api_error(status_code, error_message, "UkraineAlarm")
            
    return _format_api_error(500, "Failed after all alert retries (unexpected exit)", "UkraineAlarm")


@cached(ttl=config.CACHE_TTL_ALERTS, key="regions_v3", namespace="alerts") # Изменен ключ для v3
async def get_regions(bot: Bot) -> Dict[str, Any]: # Изменен тип возврата
    """
    Получает список регионов от UkraineAlarm API v3.
    Возвращает словарь: {"status": "success", "data": List[Dict]} или {"status": "error", ...}
    """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured for regions.")
        return _format_api_error(500, "API token not configured", "UkraineAlarm Regions")

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    last_exception = None

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch regions from UkraineAlarm")
            async with aiohttp.ClientSession() as session:
                async with session.get(UA_REGION_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500]

                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"UkraineAlarm regions response: {data}")
                            if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
                                logger.error(f"UkraineAlarm regions API v3 response is not a list of dicts: {data}")
                                return _format_api_error(500, "Invalid API response format (regions)", "UkraineAlarm Regions")
                            # API /regions возвращает список объектов регионов, где каждый содержит regionId, regionName и т.д.
                            return {"status": "success", "data": data}
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from UkraineAlarm regions. Response: {response_text_preview}")
                            return _format_api_error(500, "Invalid JSON response (regions)", "UkraineAlarm Regions")
                        except Exception as e:
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful UkraineAlarm regions response: {e}", exc_info=True)
                            return _format_api_error(500, f"Error processing API data (regions): {e}", "UkraineAlarm Regions")
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid UkraineAlarm API token (401) for regions. Response: {response_text_preview}")
                        return _format_api_error(401, "Invalid API token", "UkraineAlarm Regions")
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded (UkraineAlarm Regions)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Regions RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} (UkraineAlarm Regions)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: UkraineAlarm Regions Server Error {response.status}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: UkraineAlarm Regions Client Error {response.status}. Response: {response_text_preview}")
                        return _format_api_error(response.status, f"Client error {response.status}", "UkraineAlarm Regions")

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to UkraineAlarm regions: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching regions: {e}", exc_info=True)
            return _format_api_error(500, "Internal processing error (regions)", "UkraineAlarm Regions")

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next UkraineAlarm region retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {config.MAX_RETRIES} attempts failed for UkraineAlarm regions. Last error: {last_exception!r}")
            error_message = "Failed to get regions after multiple retries"
            status_code = 500
            if isinstance(last_exception, aiohttp.ClientResponseError):
                error_message = f"API error {last_exception.status} after retries"
                status_code = last_exception.status
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                error_message = "Network error after retries"
                status_code = 504
            elif isinstance(last_exception, asyncio.TimeoutError):
                error_message = "Timeout error after retries"
                status_code = 504
            elif last_exception:
                 error_message = f"Failed after retries: {str(last_exception)}"
            return _format_api_error(status_code, error_message, "UkraineAlarm Regions")

    return _format_api_error(500, "Failed after all region retries (unexpected exit)", "UkraineAlarm Regions")


def format_alerts_message(api_response: Dict[str, Any], selected_region_name: str = "") -> str:
    """
    Форматирует сообщение о тревогах от UkraineAlarm API v3.
    selected_region_name: Имя региона, если запрос был по конкретному региону (для заголовка).
    """
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    # selected_region_name сейчас не используется для фильтрации, т.к. API уже отдает нужные данные.
    # Оно может быть полезно для заголовка, если мы запросили конкретный регион.
    # Однако, если region_id был пуст, API вернет все регионы, и selected_region_name не нужен.
    # Пока оставим логику как есть: если selected_region_name передано, оно используется в заголовке.
    region_display_for_header = f" у регіоні {selected_region_name}" if selected_region_name else " по Україні"
    header = f"<b>🚨 Статус тривог{region_display_for_header} станом на {now_kyiv}:</b>\n"

    if api_response.get("status") == "error":
        error_msg = api_response.get("message", "Невідома помилка API")
        error_code = api_response.get("code", "")
        return header + f"\n😥 Помилка: {error_msg} (Код: {error_code}). Спробуйте пізніше."

    # alert_data это список регионов, каждый со своим списком activeAlerts
    alert_data_list_of_regions = api_response.get("data")

    if alert_data_list_of_regions is None:
        logger.error("format_alerts_message (UkraineAlarm): 'data' key missing in successful API response.")
        return header + "\n😥 Помилка обробки даних (відсутні дані тривог)."
    
    if not isinstance(alert_data_list_of_regions, list):
        logger.error(f"format_alerts_message (UkraineAlarm): API data is not a list, but {type(alert_data_list_of_regions)}")
        return header + "\n😥 Помилка обробки даних (неправильний тип відповіді API)."


    # Собираем информацию о тревогах по регионам
    active_alerts_by_region = {}
    any_alert_active = False

    for region_info in alert_data_list_of_regions:
        if not isinstance(region_info, dict):
            logger.warning(f"Skipping non-dict item in region list: {region_info}")
            continue
        
        region_name = region_info.get("regionName", "Невідомий регіон")
        current_active_alerts_in_region = region_info.get("activeAlerts", [])

        if not isinstance(current_active_alerts_in_region, list):
            logger.warning(f"activeAlerts for {region_name} is not a list: {current_active_alerts_in_region}")
            continue

        if current_active_alerts_in_region: # Если есть активные тревоги в этом регионе
            any_alert_active = True
            alert_types_in_region = set()
            for alert_detail in current_active_alerts_in_region:
                if isinstance(alert_detail, dict):
                    alert_type = alert_detail.get("type", "UNKNOWN").upper() # Приводим к верхнему регистру для консистентности с ALERT_TYPE_EMOJI
                    alert_types_in_region.add(alert_type)
            
            if alert_types_in_region: # Если удалось собрать типы тревог
                active_alerts_by_region[region_name] = sorted(list(alert_types_in_region))


    if not any_alert_active or not active_alerts_by_region:
        return header + "\n🟢 Наразі тривог немає. Все спокійно."

    message_lines = [header]
    # Сортируем регионы по названию для консистентного отображения
    for reg_name in sorted(active_alerts_by_region.keys()):
        alert_emojis_str = ", ".join([
            ALERT_TYPE_EMOJI.get(atype, ALERT_TYPE_EMOJI["UNKNOWN"]) 
            for atype in active_alerts_by_region[reg_name]
        ])
        message_lines.append(f"🔴 <b>{reg_name}:</b> {alert_emojis_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")
    return "\n".join(message_lines)