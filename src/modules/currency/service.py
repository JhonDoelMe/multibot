# src/modules/currency/service.py (Исправлен AttributeError)

import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from aiogram import Bot

logger = logging.getLogger(__name__)
# ... (Константы PB_API_..., TARGET_CURRENCIES, MAX_RETRIES, INITIAL_DELAY) ...
PB_API_CASH_URL = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"; PB_API_NONCASH_URL = "https://api.privatbank.ua/p24api/pubinfo?exchange&json&coursid=11"; TARGET_CURRENCIES = ["USD", "EUR"]; MAX_RETRIES = 3; INITIAL_DELAY = 1

async def get_pb_exchange_rates(bot: Bot, cash: bool = True) -> Optional[List[Dict[str, Any]]]:
    url = PB_API_CASH_URL if cash else PB_API_NONCASH_URL
    rate_type = "cash" if cash else "non-cash"; logger.info(f"Requesting PB {rate_type} rates...")
    last_exception = None
    # <<< Добавляем контекстный менеджер >>>
    async with bot.session as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1} PB {rate_type} rates")
                # <<< Используем session.get >>>
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        try: data = await response.json(); filtered_data = [r for r in data if r.get("ccy") in TARGET_CURRENCIES]; return filtered_data
                        except aiohttp.ContentTypeError: logger.error("... Failed decode JSON PB ..."); return None
                    elif response.status >= 500: last_exception = aiohttp.ClientResponseError(...); logger.warning("... PB Server Error. Retrying...")
                    else: logger.error("... PB API Error ..."); return None
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error PB: {e}. Retrying...")
            except Exception as e: logger.exception(f"... Unexpected error PB: {e}"); return None
            if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else: logger.error(f"All attempts failed PB {rate_type}. Last error: {last_exception!r}"); return None
    return None # Fallback

# Функция format_rates_message без изменений
def format_rates_message(rates: List[Dict[str, Any]], rate_type_name: str) -> str:
    # ... (код как в ответе #76) ...
    if not rates: return f"Не вдалося отримати {rate_type_name.lower()}." # ... (остальное форматирование) ...
    return "\n".join(message_lines)