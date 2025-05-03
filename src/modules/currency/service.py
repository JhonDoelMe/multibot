# src/modules/currency/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from aiogram import Bot

from src import config

logger = logging.getLogger(__name__)

# Константы API
PB_API_URL_CASH = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=5"
PB_API_URL_NONCASH = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=11"

# Параметры Retry
MAX_RETRIES = 3
INITIAL_DELAY = 1  # Секунда

# Целевые валюты
TARGET_CURRENCIES = {"USD", "EUR"}

async def get_pb_exchange_rates(bot: Bot, cash: bool = True) -> Optional[List[Dict[str, Any]]]:
    """ Получает курсы валют ПриватБанка (наличные или безналичные). """
    logger.info(f"Requesting PB {'cash' if cash else 'noncash'} rates...")
    url = PB_API_URL_CASH if cash else PB_API_URL_NONCASH
    last_exception = None

    async with aiohttp.ClientSession() as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch PB rates (cash={cash})")
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"PB API response: {data}")
                            filtered_data = [
                                item for item in data
                                if item.get("ccy") in TARGET_CURRENCIES
                            ]
                            return filtered_data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from PB. Response: {await response.text()}")
                            return None
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: PB RateLimit Error (429). Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: PB Server Error {response.status}. Retrying...")
                    else:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: PB Error {response.status}. Response: {error_text[:200]}")
                        return None

            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                last_exception = e
                logger.warning(f"Attempt {attempt + 1}: Network error connecting to PB: {e}. Retrying...")
            except Exception as e:
                logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching PB rates: {e}", exc_info=True)
                return None

            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_DELAY * (2 ** attempt)
                logger.info(f"Waiting {delay} seconds before next PB retry...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {MAX_RETRIES} attempts failed for PB rates (cash={cash}). Last error: {last_exception!r}")
                return None
    return None

def format_rates_message(rates_data: List[Dict[str, Any]], cash: bool = True) -> str:
    """ Форматирует сообщение с курсами валют. """
    try:
        if not rates_data:
            return "😥 Не вдалося отримати курси валют. Спробуйте пізніше."
        course_type = "Готівковий" if cash else "Безготівковий"
        message_lines = [f"<b>{course_type} курс ПриватБанку:</b>\n"]
        for rate in rates_data:
            currency = rate.get("ccy", "N/A")
            buy = float(rate.get("buy", "0"))
            sale = float(rate.get("sale", "0"))
            message_lines.append(
                f"💵 <b>{currency}</b>: Купівля {buy:.2f} UAH | Продаж {sale:.2f} UAH"
            )
        return "\n".join(message_lines)
    except Exception as e:
        logger.exception(f"Error formatting rates message: {e}")
        return "😥 Помилка обробки курсів валют."