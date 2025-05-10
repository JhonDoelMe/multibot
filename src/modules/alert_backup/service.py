# src/modules/alert_backup/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime
import pytz
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
ALERTS_IN_UA_API_URL = "https://api.alerts.in.ua/v1/alerts/active.json"

# Часовой пояс Украины
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типов тревог на эмодзи
ALERT_TYPE_EMOJI_BACKUP = {
    "air_raid": "🚨",
    "artillery_shelling": "💣",
    "urban_fights": "💥",
    "chemical": "☣️",
    "nuclear": "☢️",
    "info": "ℹ️",
    "unknown": "❓",
}

@cached(ttl=config.CACHE_TTL_ALERTS_BACKUP, key="active_alerts_backup", namespace="alerts_backup")
async def get_backup_alerts(bot: Bot) -> Dict[str, Any]: # Изменен тип возврата для большей ясности
    """
    Получает активные тревоги с alerts.in.ua.
    Возвращает словарь: {"status": "success", "data": List[Dict]} или {"status": "error", "message": str}
    """
    if not config.ALERTS_IN_UA_TOKEN:
        logger.error("Alerts.in.ua API token (ALERTS_IN_UA_TOKEN) is not configured.")
        return {"status": "error", "message": "Резервний API токен не налаштовано"}

    headers = {"Authorization": f"Bearer {config.ALERTS_IN_UA_TOKEN}"}
    last_exception = None

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch backup alerts")
            async with aiohttp.ClientSession() as session:
                async with session.get(ALERTS_IN_UA_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500] # Для логов, читаем один раз

                    if response.status == 200:
                        try:
                            data = await response.json() # Пытаемся парсить JSON из уже прочитанного текста
                            logger.debug(f"Alerts.in.ua response JSON: {data}")
                            alerts = data.get("alerts")
                            if alerts is None: # Проверяем, что ключ "alerts" существует
                                logger.error("Alerts.in.ua: 'alerts' key is missing in response.")
                                return {"status": "error", "message": "Некоректний формат відповіді від резервного API (відсутній ключ 'alerts')"}
                            if not isinstance(alerts, list):
                                logger.error(f"Alerts.in.ua: 'alerts' is not a list, but {type(alerts)}.")
                                return {"status": "error", "message": "Некоректний формат відповіді від резервного API (дані тривог не є списком)"}

                            logger.debug(f"Extracted {len(alerts)} alerts from backup API")
                            return {"status": "success", "data": alerts}
                        except aiohttp.ContentTypeError as json_err: # Если response.json() не сработает
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from Alerts.in.ua. Error: {json_err}. Response: {response_text_preview}")
                            # Не ретраим при ContentTypeError, сразу возвращаем ошибку
                            return {"status": "error", "message": "Невірний формат JSON відповіді від резервного API"}
                        except Exception as e: # Другие ошибки при обработке успешного ответа
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful backup alerts response: {e}", exc_info=True)
                            return {"status": "error", "message": f"Помилка обробки даних резервного API: {e}"}

                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid Alerts.in.ua API token (401). Response: {response_text_preview}")
                        return {"status": "error", "message": "Невірний токен резервного API"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: Received 404 from Alerts.in.ua. Response: {response_text_preview}")
                        return {"status": "error", "message": "Резервне API не знайдено (404)"}
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded (Alerts.in.ua)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} (Alerts.in.ua)"
                        )
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua Server Error {response.status}. Retrying...")
                    else: # Другие клиентские ошибки
                        logger.error(f"Attempt {attempt + 1}: Alerts.in.ua Client Error {response.status}. Response: {response_text_preview}")
                        return {"status": "error", "message": f"Помилка резервного API {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to Alerts.in.ua: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching backup alerts: {e}", exc_info=True)
            return {"status": "error", "message": "Внутрішня помилка обробки резервних тривог"}

        if attempt < config.MAX_RETRIES - 1:
            delay = config.INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next backup alert retry...")
            await asyncio.sleep(delay)
        else: # Все попытки исчерпаны
            logger.error(f"All {config.MAX_RETRIES} attempts failed for backup alerts. Last error: {last_exception!r}")
            error_message = "Не вдалося отримати резервні дані після ретраїв"
            if isinstance(last_exception, aiohttp.ClientResponseError):
                error_message = f"Помилка резервного API {last_exception.status} після ретраїв"
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                error_message = "Помилка мережі резервного API після ретраїв"
            elif isinstance(last_exception, asyncio.TimeoutError):
                error_message = "Таймаут резервного API після ретраїв"
            elif last_exception:
                error_message = f"Не вдалося отримати резервні дані: {str(last_exception)}"
            return {"status": "error", "message": error_message}
            
    # Этот return не должен достигаться, если цикл всегда возвращает значение
    return {"status": "error", "message": "Не вдалося отримати резервні дані після всіх ретраїв (неочікуваний вихід)"}


def format_backup_alerts_message(api_response: Dict[str, Any]) -> str:
    """ Форматирует сообщение о тревогах с alerts.in.ua """
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Резервний статус тривог станом на {now_kyiv}:</b>\n"

    if api_response.get("status") == "error":
        error_msg = api_response.get("message", "Невідома помилка API")
        return header + f"\n😥 Помилка: {error_msg}. Спробуйте пізніше."

    alerts_data = api_response.get("data")
    if alerts_data is None: # Дополнительная проверка, хотя get_backup_alerts должен это покрыть
        logger.error("format_backup_alerts_message: 'data' key missing in successful API response.")
        return header + "\n😥 Помилка обробки даних (відсутні дані тривог)."
    
    if not isinstance(alerts_data, list):
        logger.error(f"Invalid data type for alerts_data in format_backup_alerts_message: {type(alerts_data)}")
        return header + "\n😥 Помилка обробки даних (неправильний тип)."

    if not alerts_data:
        return header + "\n🟢 Наразі тривог немає. Все спокійно (резервне джерело)."

    active_oblasts = {}
    for alert in alerts_data:
        if not isinstance(alert, dict): # Проверка что каждый элемент списка - словарь
            logger.warning(f"Skipping non-dict item in alerts_data: {alert}")
            continue
            
        # API alerts.in.ua использует 'location_title' для названия области,
        # 'location_oblast' может быть, а может и не быть.
        # Используем 'location_title' как более надежный источник названия.
        # Если 'location_type' == 'oblast', то 'location_title' и есть название области.
        # Если тревога по району/громаде, 'location_title' будет район/громада,
        # а 'location_oblast' - соответствующая область.
        
        oblast = alert.get("location_oblast")
        location_title = alert.get("location_title") # Например, "м. Київ" или "Харківська область"
        location_type = alert.get("location_type") # 'oblast', 'raion', 'hromada', 'city'
        
        # Определяем отображаемое имя региона
        display_region_name = location_title # По умолчанию используем location_title
        if location_type != "oblast" and oblast:
            # Если это не тревога по всей области, а по ее части,
            # и есть название области, можно уточнить.
            # Например: "Балаклійська громада (Харківська область)"
            # Для простоты пока оставим просто location_title
            pass # display_region_name = f"{location_title} ({oblast})"


        alert_type = alert.get("alert_type", "unknown")
        
        if not display_region_name: # Если имя региона не удалось определить
            logger.warning(f"Пропущено alert без location_title: {alert}")
            continue

        if display_region_name not in active_oblasts:
            active_oblasts[display_region_name] = set()

        active_oblasts[display_region_name].add(alert_type)

    if not active_oblasts: # Если после фильтрации ничего не осталось
        return header + "\n🟢 Наразі тривог немає (після фільтрації). Все спокійно (резервне джерело)."

    message_lines = [header]
    # Сортируем по названию региона
    for region_name in sorted(active_oblasts.keys()):
        alerts_str = ", ".join(
            ALERT_TYPE_EMOJI_BACKUP.get(atype, ALERT_TYPE_EMOJI_BACKUP["unknown"])
            for atype in sorted(list(active_oblasts[region_name]))
        )
        message_lines.append(f"🔴 <b>{region_name}:</b> {alerts_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе!")
    return "\n".join(message_lines)