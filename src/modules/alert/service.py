# src/modules/alert/service.py (Исправлен SyntaxError в ALERT_TYPE_EMOJI)

import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import pytz
from aiogram import Bot

from src import config

logger = logging.getLogger(__name__)

UKRAINEALARM_API_URL = "https://api.ukrainealarm.com/api/v3/alerts"
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# --- ПОЛНОЕ ОПРЕДЕЛЕНИЕ СЛОВАРЯ ---
ALERT_TYPE_EMOJI = {
    "AIR": "🚨",
    "ARTILLERY": "💣",
    "URBAN_FIGHTS": "💥",
    "CHEMICAL": "☣️",
    "NUCLEAR": "☢️",
    "INFO": "ℹ️",
    "UNKNOWN": "❓"
}
# --- КОНЕЦ СЛОВАРЯ ---

MAX_RETRIES = 3
INITIAL_DELAY = 1

async def get_active_alerts(bot: Bot) -> Optional[List[Dict[str, Any]]]:
    # ... (код функции без изменений, как в ответе #123) ...
    if not config.UKRAINEALARM_API_TOKEN: logger.error("..."); return {"error": 500, "message": "..."}
    headers = {"Authorization": config.UKRAINEALARM_API_TOKEN}; logger.info(f"Requesting UA alerts...")
    last_exception = None
    async with bot.session as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1} UA alerts")
                async with session.get(UKRAINEALARM_API_URL, headers=headers, timeout=15) as response:
                    if response.status == 200:
                        try: data = await response.json(); return data
                        except aiohttp.ContentTypeError: return {"error": 500, "message": "..."}
                    elif response.status == 401: return {"error": 401, "message": "..."}
                    elif 400 <= response.status < 500 and response.status != 429: return {"error": response.status, "message": "..."}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                    else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error UA: {e}. Retrying...")
            except Exception as e: logger.exception(f"... Unexpected error UA alerts: {e}"); return {"error": 500, "message": "..."}
            if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else: logger.error(f"All attempts failed UA alerts. Last error: {last_exception!r}"); # ... (return error) ...
    return {"error": 500, "message": "Failed after all retries"}


def format_alerts_message(alerts_data: Optional[List[Dict[str, Any]]]) -> str:
    # ... (код функции без изменений, как в ответе #107) ...
     now_kyiv = datetime.now(TZ_KYIV).strftime('%H:%M %d.%m.%Y'); header = f"<b>🚨 Статус тривог ... {now_kyiv}:</b>\n"
     if alerts_data is None: return header + "\nНе вдалося отримати дані..."
     if isinstance(alerts_data, dict) and "error" in alerts_data:
         error_code = alerts_data.get("error"); error_msg = alerts_data.get("message", "...");
         if error_code == 401: return header + "\nПомилка: Недійсний токен API тривог."
         elif error_code == 429: return header + "\nПомилка: Перевищено ліміт запитів API тривог..."
         else: return header + f"\nПомилка API ({error_code}): {error_msg}..."
     if not alerts_data: return header + "\n🟢 Наразі тривог немає. Все спокійно."
     active_regions = {}
     for region_alert_info in alerts_data:
         region_name = region_alert_info.get("regionName", "...")
         if region_name not in active_regions: active_regions[region_name] = []
         for alert in region_alert_info.get("activeAlerts", []):
             alert_type = alert.get("type", "UNKNOWN")
             # Теперь отступ правильный
             if alert_type not in active_regions[region_name]:
                  active_regions[region_name].append(alert_type)
     if not active_regions: return header + "\n🟢 Наразі тривог на рівні областей/громад немає."
     message_lines = [header]
     for region_name in sorted(active_regions.keys()): alerts_str = ", ".join([ALERT_TYPE_EMOJI.get(atype, atype) for atype in active_regions[region_name]]); message_lines.append(f"🔴 <b>{region_name}:</b> {alerts_str}")
     message_lines.append("\n<tg-spoiler>Джерело: api.ukrainealarm.com</tg-spoiler>"); message_lines.append("🙏 Будь ласка, бережіть себе та прямуйте в укриття!")
     return "\n".join(message_lines)