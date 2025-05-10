# src/modules/currency/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
PB_API_URL_CASH = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=5"
PB_API_URL_NONCASH = "https://api.privatbank.ua/p24api/pubinfo?exchange&coursid=11"

# Параметры Retry
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

# Целевые валюты
TARGET_CURRENCIES = {"USD", "EUR"}

@cached(ttl=config.CACHE_TTL_CURRENCY, key_builder=lambda *args, **kwargs: f"rates:{'cash' if kwargs.get('cash', True) else 'noncash'}", namespace="currency")
async def get_pb_exchange_rates(bot: Bot, cash: bool = True) -> Optional[List[Dict[str, Any]]]:
    """ Получает курсы валют ПриватБанка (наличные или безналичные). """
    cache_key = f"rates:{'cash' if cash else 'noncash'}"
    logger.info(f"Requesting PB {'cash' if cash else 'noncash'} rates (cache key: {cache_key})...")
    url = PB_API_URL_CASH if cash else PB_API_URL_NONCASH
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch PB rates (cash={cash})")
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.info(f"PB API response: {data}")
                            if not isinstance(data, list): # Добавим проверку, что ответ это список
                                logger.error(f"PB API response is not a list: {data}")
                                last_exception = TypeError("PB API response is not a list")
                                # Сразу выходим, если формат ответа неожиданный
                                return None # Или вернуть структуру ошибки {"status": "error", ...}
                            
                            filtered_data = [
                                item for item in data
                                if isinstance(item, dict) and item.get("ccy") in TARGET_CURRENCIES
                            ]
                            if not filtered_data:
                                logger.warning(f"No valid currency data found in PB response for cash={cash}")
                                # Если API вернул 200, но данных нет, это не ошибка, а пустой результат
                                return [] # Возвращаем пустой список, а не None
                            logger.info(f"Returning {len(filtered_data)} currency rates from API or cache")
                            return filtered_data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from PB. Response: {await response.text()}")
                            last_exception = Exception("Invalid JSON response from PB")
                            # Если ContentTypeError, последующие попытки вряд ли помогут
                            return None # Или структуру ошибки
                    elif response.status == 429: # Rate limit
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=429, message="Rate limit exceeded"
                        )
                        logger.warning(f"Attempt {attempt + 1}: PB RateLimit Error (429). Retrying...")
                    elif response.status >= 500: # Серверные ошибки
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: PB Server Error {response.status}. Retrying...")
                    else: # Другие клиентские ошибки (4xx, кроме 429)
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: PB Client Error {response.status}. Response: {error_text[:200]}")
                        # Для клиентских ошибок обычно нет смысла ретраить
                        return None # Или структуру ошибки

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to PB: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching PB rates: {e}", exc_info=True)
            return None # Или структуру ошибки

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next PB retry...")
            await asyncio.sleep(delay)
        else: # Все попытки исчерпаны
            logger.error(f"All {MAX_RETRIES} attempts failed for PB rates (cash={cash}). Last error: {last_exception!r}")
            # Можно возвращать структуру ошибки для хендлера
            # if isinstance(last_exception, aiohttp.ClientResponseError):
            #     return {"status": "error", "code": last_exception.status, "message": ...}
            return None
    return None # Недостижимо

def format_rates_message(rates_data: Optional[List[Dict[str, Any]]], cash: bool = True) -> str: # rates_data может быть None
    """ Форматирует сообщение с курсами валют. """
    try:
        # Изменили условие: rates_data может быть None или пустым списком
        if rates_data is None: # Если была ошибка и вернулся None
            return "😥 Не вдалося отримати курси валют. Спробуйте пізніше."
        if not rates_data: # Если API вернул пустой список (нет целевых валют)
             return "⚠️ На даний момент інформація по курсам USD та EUR відсутня."

        course_type = "Готівковий" if cash else "Безготівковий"
        # В оригинальном коде PB_API_URL_NONCASH (coursid=11) это "Курсы для карточных операций и Приват24"
        # "Безготівковий" - это более общее понятие. Можно уточнить, если нужно.
        message_lines = [f"<b>{course_type} курс ПриватБанку:</b>\n"]
        
        found_currencies = False
        for rate in rates_data:
            currency = rate.get("ccy")
            # Убедимся, что buy и sale существуют и являются числами
            try:
                buy_str = rate.get("buy")
                sale_str = rate.get("sale")
                if buy_str is None or sale_str is None:
                    logger.warning(f"Missing buy/sale for {currency} in rates: {rate}")
                    continue
                
                buy = float(buy_str)
                sale = float(sale_str)
                
                base_ccy = rate.get("base_ccy", "UAH") # Обычно UAH для этого API

                message_lines.append(
                    f"💵 <b>{currency}/{base_ccy}</b>: Купівля {buy:.2f} | Продаж {sale:.2f}"
                )
                found_currencies = True
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing rate data for {currency}: {rate}, error: {e}")
                continue
        
        if not found_currencies: # Если после фильтрации не осталось валидных курсов
            return "⚠️ Не вдалося отримати дані по курсам USD та EUR."

        return "\n".join(message_lines)
    except Exception as e:
        logger.exception(f"Error formatting rates message: {e}")
        return "😥 Помилка обробки курсів валют."