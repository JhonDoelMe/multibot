# src/modules/currency/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, List, Dict, Any
from aiogram import Bot # <<< Импортируем Bot

logger = logging.getLogger(__name__)

PB_API_CASH_URL = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
PB_API_NONCASH_URL = "https://api.privatbank.ua/p24api/pubinfo?exchange&json&coursid=11"
TARGET_CURRENCIES = ["USD", "EUR"]
MAX_RETRIES = 3
INITIAL_DELAY = 1

# --- ИЗМЕНЯЕМ ФУНКЦИЮ ---
async def get_pb_exchange_rates(bot: Bot, cash: bool = True) -> Optional[List[Dict[str, Any]]]: # <<< Добавили bot: Bot
    """ Получает курсы валют, используя сессию бота. """
    url = PB_API_CASH_URL if cash else PB_API_NONCASH_URL
    rate_type = "cash" if cash else "non-cash"
    logger.info(f"Requesting PrivatBank {rate_type} rates from {url}")
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch PB {rate_type} rates")
            # <<< ИСПОЛЬЗУЕМ bot.session >>>
            async with bot.session.get(url, timeout=10) as response:
                # ... (логика обработки response и ошибок остается прежней) ...
                if response.status == 200:
                    try: data = await response.json(); logger.debug(f"PB API response ({rate_type}): {data}"); filtered_data = [r for r in data if r.get("ccy") in TARGET_CURRENCIES]; return filtered_data
                    except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON from PB API ({rate_type})..."); return None
                elif response.status >= 500: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... PB API Server Error {response.status}. Retrying...")
                else: logger.error(f"... PB API Error {response.status}, Response: {await response.text()[:200]}"); return None
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error PB API ({rate_type}): {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error fetching PB rates ({rate_type}): {e}", exc_info=True); return None
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next PB retry..."); await asyncio.sleep(delay)
        else: logger.error(f"All {MAX_RETRIES} attempts failed for PB {rate_type} rates. Last error: {last_exception!r}"); return None
    return None

# Функция format_rates_message остается без изменений
def format_rates_message(rates: List[Dict[str, Any]], rate_type_name: str) -> str:
    # ... (код как в ответе #76) ...
    if not rates: return f"Не вдалося отримати {rate_type_name.lower()}."
    message_lines = [f"<b>{rate_type_name}:</b>\n"]
    for rate in rates: ccy = rate.get('ccy'); buy = float(rate.get('buy', 0)); sale = float(rate.get('sale', 0)); buy_str = f"{buy:.2f}"; sale_str = f"{sale:.2f}"; message_lines.append(f"<b>{ccy}:</b>  Купівля {buy_str} / Продаж {sale_str}")
    message_lines.append("\n<tg-spoiler>Джерело: api.privatbank.ua</tg-spoiler>")
    return "\n".join(message_lines)