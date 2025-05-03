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

# Маппинг типов тревог на эмодзи (можно расширить на основе API)
# Источник: https://devs.alerts.in.ua/#alert-types
ALERT_TYPE_EMOJI_BACKUP = {
    "air_raid": "🚨",
    "artillery_shelling": "💣",
    "urban_fights": "💥",
    "chemical": "☣️",
    "nuclear": "☢️",
    "info": "ℹ️", # Пример, если API будет возвращать такой тип
    "unknown": "❓", # Общий для неизвестных
}

@cached(ttl=config.CACHE_TTL_ALERTS_BACKUP, key="active_alerts_backup", namespace="alerts_backup")
async def get_backup_alerts(bot: Bot) -> Optional[List[Dict[str, Any]]]:
    """ Получает активные тревоги с alerts.in.ua """
    if not config.ALERTS_IN_UA_TOKEN:
        logger.error("Alerts.in.ua API token (ALERTS_IN_UA_TOKEN) is not configured.")
        return {"status": "error", "message": "Резервний API токен не налаштовано"}

    # Заголовки для alerts.in.ua API (Bearer Token)
    headers = {"Authorization": f"Bearer {config.ALERTS_IN_UA_TOKEN}"}
    last_exception = None

    for attempt in range(config.MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{config.MAX_RETRIES} to fetch backup alerts")
            # Используем сессию из aiohttp напрямую
            async with aiohttp.ClientSession() as session:
                async with session.get(ALERTS_IN_UA_API_URL, headers=headers, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            # API возвращает {"alerts": [...]}
                            alerts = data.get("alerts", [])
                            logger.debug(f"Alerts.in.ua response: {len(alerts)} alerts")
                            return alerts # Возвращаем список
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from Alerts.in.ua. Response: {await response.text()}")
                            return {"status": "error", "message": "Невірний формат JSON відповіді від резервного API"}
                        except Exception as json_err: # Обработка других ошибок парсинга JSON
                             logger.error(f"Attempt {attempt + 1}: Error parsing JSON from Alerts.in.ua: {json_err}. Response: {await response.text()[:200]}")
                             return {"status": "error", "message": "Помилка обробки відповіді резервного API"}

                    elif response.status == 401:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: Invalid Alerts.in.ua API token (401). Response: {error_text[:200]}")
                        return {"status": "error", "message": f"Невірний токен резервного API"}
                    elif response.status == 404: # API может вернуть 404 если нет активных тревог или неверный URL
                         error_text = await response.text()
                         logger.warning(f"Attempt {attempt + 1}: Received 404 from Alerts.in.ua. Response: {error_text[:200]}")
                         # Предполагаем, что 404 означает отсутствие тревог, но лучше уточнить документацию API
                         # Если 404 - это "нет тревог", то вернуть пустой список: return []
                         # Пока оставим как ошибку:
                         return {"status": "error", "message": f"Помилка резервного API {response.status} (можливо, не знайдено)"}
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: Alerts.in.ua Server Error {response.status}. Retrying...")
                    else:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: Alerts.in.ua Error {response.status}. Response: {error_text[:200]}")
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
        else:
            logger.error(f"All {config.MAX_RETRIES} attempts failed for backup alerts. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"status": "error", "message": f"Помилка резервного API {last_exception.status} після ретраїв"}
            elif isinstance(last_exception, aiohttp.ClientConnectorError):
                return {"status": "error", "message": "Помилка мережі резервного API після ретраїв"}
            elif isinstance(last_exception, asyncio.TimeoutError):
                return {"status": "error", "message": "Таймаут резервного API після ретраїв"}
            else:
                return {"status": "error", "message": "Не вдалося отримати резервні дані після ретраїв"}
    return {"status": "error", "message": "Не вдалося отримати резервні дані після всіх ретраїв"}


def format_backup_alerts_message(alerts_data: Optional[List[Dict[str, Any]]]) -> str:
    """ Форматирует сообщение о тревогах с alerts.in.ua """
    now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y')
    header = f"<b>🚨 Резервний статус тривог станом на {now_kyiv}:</b>\n"

    if alerts_data is None:
        return header + "\n😥 Не вдалося отримати дані. Спробуйте пізніше."
    # Проверка на ошибку, которую мы сами вернули из get_backup_alerts
    if isinstance(alerts_data, dict) and "status" in alerts_data and alerts_data["status"] == "error":
        error_msg = alerts_data.get("message", "Невідома помилка API")
        return header + f"\n😥 Помилка: {error_msg}. Спробуйте пізніше."
    # Проверка, что это действительно список (успешный ответ API)
    if not isinstance(alerts_data, list):
         logger.error(f"Invalid data type passed to format_backup_alerts_message: {type(alerts_data)}")
         return header + "\n😥 Помилка обробки даних."

    if not alerts_data:
        return header + "\n🟢 Наразі тривог немає. Все спокійно (резервне джерело)."

    active_oblasts = {}
    for alert in alerts_data:
        oblast = alert.get("oblast")
        alert_type = alert.get("alert_type", "unknown") # 'air_raid', 'artillery_shelling', etc.
        if not oblast:
            continue

        if oblast not in active_oblasts:
            active_oblasts[oblast] = set() # Используем set для уникальных типов

        active_oblasts[oblast].add(alert_type)

    if not active_oblasts:
         return header + "\n🟢 Наразі тривог немає. Все спокійно (резервне джерело)."

    message_lines = [header]
    # Сортируем области по названию
    for oblast_name in sorted(active_oblasts.keys()):
        # Получаем эмодзи для каждого типа тревоги в области
        alerts_str = ", ".join([
            ALERT_TYPE_EMOJI_BACKUP.get(atype, atype)
            for atype in sorted(list(active_oblasts[oblast_name])) # Сортируем типы для консистентности
        ])
        message_lines.append(f"🔴 <b>{oblast_name}:</b> {alerts_str}")

    message_lines.append("\n<tg-spoiler>Джерело: api.alerts.in.ua</tg-spoiler>")
    message_lines.append("🙏 Будь ласка, бережіть себе!")
    return "\n".join(message_lines)