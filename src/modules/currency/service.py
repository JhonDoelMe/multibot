# src/modules/currency/service.py

import logging
import aiohttp
import asyncio # <<< Добавляем asyncio
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

PB_API_CASH_URL = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
PB_API_NONCASH_URL = "https://api.privatbank.ua/p24api/pubinfo?exchange&json&coursid=11"
TARGET_CURRENCIES = ["USD", "EUR"]

# Параметры для повторных попыток
MAX_RETRIES = 3
INITIAL_DELAY = 1 # Секунда

async def get_pb_exchange_rates(cash: bool = True) -> Optional[List[Dict[str, Any]]]:
    """ Получает курсы валют с API ПриватБанка с повторными попытками. """
    url = PB_API_CASH_URL if cash else PB_API_NONCASH_URL
    rate_type = "cash" if cash else "non-cash"
    logger.info(f"Requesting PrivatBank {rate_type} rates from {url}")

    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch PB {rate_type} rates")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"PrivatBank API response ({rate_type}): {data}")
                            filtered_data = [rate for rate in data if rate.get("ccy") in TARGET_CURRENCIES]
                            return filtered_data # <<< Успех
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from PB API ({rate_type}). Response: {await response.text()}")
                            return None # Не повторяем ошибку парсинга JSON
                    # Ошибки ПриватБанка >= 500 будем повторять
                    elif response.status >= 500:
                         last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}")
                         logger.warning(f"Attempt {attempt + 1}: PB API Server Error {response.status}. Retrying...")
                    else: # Другие ошибки (4xx) не повторяем
                         logger.error(f"Attempt {attempt + 1}: PB API Error {response.status}, Response: {await response.text()[:200]}")
                         return None

        # Повторяем сетевые ошибки и таймауты
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to PB API ({rate_type}): {e}. Retrying...")
        # Другие ошибки не повторяем
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred while fetching PB rates ({rate_type}): {e}", exc_info=True)
            return None

        # Ждем перед следующей попыткой
        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next PB rates retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for PB {rate_type} rates. Last error: {last_exception!r}")
            return None # Все попытки не удались

    return None # Если цикл завершился без успеха

# Функция format_rates_message остается БЕЗ ИЗМЕНЕНИЙ
# ... (ваш код format_rates_message) ...
def format_rates_message(rates: List[Dict[str, Any]], rate_type_name: str) -> str:
    # ... (код функции из ответа #76) ...
    if not rates:
        return f"Не вдалося отримати {rate_type_name.lower()}."
    message_lines = [f"<b>{rate_type_name}:</b>\n"]
    for rate in rates:
        ccy = rate.get('ccy')
        buy = float(rate.get('buy', 0))
        sale = float(rate.get('sale', 0))
        buy_str = f"{buy:.2f}"
        sale_str = f"{sale:.2f}"
        message_lines.append(f"<b>{ccy}:</b>  Купівля {buy_str} / Продаж {sale_str}")
    message_lines.append("\n<tg-spoiler>Джерело: api.privatbank.ua</tg-spoiler>")
    return "\n".join(message_lines)