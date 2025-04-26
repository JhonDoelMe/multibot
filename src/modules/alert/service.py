# src/modules/alert/service.py

import logging
import aiohttp
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz # Для работы с часовыми поясами

from src import config # Для API токена

logger = logging.getLogger(__name__)

# URL API и хедеры
UKRAINEALARM_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
# Часовой пояс Украины для отображения времени
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Маппинг типов тревог на эмодзи (можно расширить)
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️", # Химическая
    "NUCLEAR": "☢️",  # Ядерная
    "INFO": "ℹ️",    # Информационное сообщение (иногда используется)
    "UNKNOWN": "❓"   # Неизвестный тип
}

async def get_active_alerts() -> Optional[List[Dict[str, Any]]]:
    """
    Получает список активных тревог с API UkraineAlarm.

    Returns:
        Список словарей с данными об активных тревогах или None при ошибке.
    """
    if not config.UKRAINEALARM_API_TOKEN:
        logger.error("UkraineAlarm API token (UKRAINEALARM_API_TOKEN) is not configured.")
        return None

    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}
    logger.info(f"Requesting UkraineAlarm alerts from {UKRAINEALARM_API_URL}")

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(UKRAINEALARM_API_URL) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.debug(f"UkraineAlarm API response: {data}")
                        # API возвращает массив регионов, где есть *хотя бы одна* активная тревога
                        return data
                    except aiohttp.ContentTypeError:
                        logger.error(f"Failed to decode JSON from UkraineAlarm API. Response: {await response.text()}")
                        return None
                elif response.status == 401:
                     logger.error(f"UkraineAlarm API Error: Unauthorized (Invalid Token?). Status: {response.status}")
                     return {"error": 401, "message": "Invalid API Token"} # Возвращаем маркер ошибки
                elif response.status == 429:
                     logger.error(f"UkraineAlarm API Error: Too Many Requests. Status: {response.status}")
                     return {"error": 429, "message": "Rate limit exceeded"}
                else:
                    logger.error(f"UkraineAlarm API error: Status {response.status}, Response: {await response.text()}")
                    return {"error": response.status, "message": "API error"}

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network error connecting to UkraineAlarm API: {e}")
        return {"error": 503, "message": "Network error"}
    except Exception as e:
        logger.exception(f"An unexpected error occurred while fetching UkraineAlarm alerts: {e}")
        return {"error": 500, "message": "Internal error"}


def format_alerts_message(alerts_data: Optional[List[Dict[str, Any]]]) -> str:
    """
    Форматирует ответ API тревог в сообщение для пользователя.

    Args:
        alerts_data: Список данных об алертах от API или None/Dict с ошибкой.

    Returns:
        Строка с сообщением о статусе тревог.
    """
    # Получаем текущее время в Киеве
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Статус тривог по Україні станом на {now_kyiv}:</b>\n"

    if alerts_data is None:
        return header + "\nНе вдалося отримати дані. Спробуйте пізніше."
    if isinstance(alerts_data, dict) and "error" in alerts_data:
         # Обработка ошибок, возвращенных из get_active_alerts
         error_code = alerts_data.get("error")
         error_msg = alerts_data.get("message", "Невідома помилка API")
         if error_code == 401:
             return header + "\nПомилка: Недійсний токен доступу до API тривог."
         elif error_code == 429:
             return header + "\nПомилка: Перевищено ліміт запитів до API тривог. Спробуйте за хвилину."
         else:
              return header + f"\nПомилка API ({error_code}): {error_msg}. Спробуйте пізніше."

    if not alerts_data: # Пустой список означает отсутствие активных тревог
        return header + "\n🟢 Наразі тривог немає. Все спокійно."

    # Собираем информацию по регионам (областям)
    active_regions = {} # Словарь {RegionName: [List of alert types]}
    for region_alert_info in alerts_data:
        region_name = region_alert_info.get("regionName", "Невідомий регіон")
        # Берем только область (State) или если тип не указан - берем все
        # region_type = region_alert_info.get("regionType")
        # if region_type is None or region_type == "State":
        if region_name not in active_regions:
             active_regions[region_name] = []
        for alert in region_alert_info.get("activeAlerts", []):
            alert_type = alert.get("type", "UNKNOWN")
            if alert_type not in active_regions[region_name]:
                 active_regions[region_name].append(alert_type)


    if not active_regions: # Если после фильтрации (если бы она была) ничего не осталось
         return header + "\n🟢 Наразі тривог на рівні областей немає (можливі тривоги в окремих громадах)."


    message_lines = [header]
    # Сортируем регионы по имени для консистентности
    for region_name in sorted(active_regions.keys()):
         alerts_str = ", ".join([ALERT_TYPE_EMOJI.get(atype, atype) for atype in active_regions[region_name]])
         message_lines.append(f"🔴 <b>{region_name}:</b> {alerts_str}")

    # Добавляем общую информацию
    message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")

    return "\n".join(message_lines)