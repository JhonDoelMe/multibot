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

# Параметри Retry
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

# Цільові валюти
TARGET_CURRENCIES = {"USD", "EUR"}

def _generate_pb_api_error(http_status_code: Optional[int], message: str, service_name: str = "PrivatBank Currency") -> Dict[str, Any]:
    logger.error(f"{service_name} API Error: HTTP Status {http_status_code if http_status_code else 'N/A'}, Message: {message}")
    return {"status": "error", "code": http_status_code or 500, "message": message, "error_source": service_name}


@cached(ttl=config.CACHE_TTL_CURRENCY,
        # ВИПРАВЛЕНО key_builder:
        key_builder=lambda f, bot_obj, *args, **kwargs: f"pb_rates:{'cash' if kwargs.get('cash', True) else 'noncash'}",
        namespace="currency_service")
async def get_pb_exchange_rates(bot: Bot, *, cash: bool = True) -> Dict[str, Any]: # Додано `*` щоб `cash` був тільки keyword-only
    api_url = PB_API_URL_CASH if cash else PB_API_URL_NONCASH
    cache_key_info = 'cash' if cash else 'noncash'
    logger.info(f"Requesting PrivatBank {cache_key_info} rates (URL: {api_url})...")
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch PB rates (cash={cash})")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_text_preview = (await response.text())[:500]

                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"PrivatBank API response for {cache_key_info}: {str(data)[:300]}")

                            if not isinstance(data, list):
                                logger.error(f"PrivatBank API response for {cache_key_info} is not a list: {type(data)}. Response: {response_text_preview}")
                                return _generate_pb_api_error(response.status, "Некоректний формат відповіді від API ПриватБанку (очікувався список).")

                            filtered_data = []
                            for item in data:
                                if isinstance(item, dict) and item.get("ccy") in TARGET_CURRENCIES:
                                    buy_rate = item.get("buy")
                                    sale_rate = item.get("sale")
                                    if buy_rate is not None and sale_rate is not None:
                                        try:
                                            float(buy_rate)
                                            float(sale_rate)
                                            filtered_data.append(item)
                                        except (ValueError, TypeError):
                                            logger.warning(f"Skipping item with non-numeric buy/sale rate for {item.get('ccy')}: {item}")
                                    else:
                                        logger.warning(f"Skipping item with missing buy/sale rate for {item.get('ccy')}: {item}")
                                else:
                                     logger.debug(f"Skipping non-target currency or invalid item: {item}")

                            if not filtered_data:
                                logger.warning(f"No valid target currency data (USD, EUR) found in PrivatBank response for {cache_key_info} after filtering.")
                                return {"status": "success", "data": []}

                            logger.info(f"Returning {len(filtered_data)} currency rates from PrivatBank API or cache for {cache_key_info}")
                            return {"status": "success", "data": filtered_data}
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from PrivatBank for {cache_key_info}. Response: {response_text_preview}")
                            last_exception = Exception("Невірний формат JSON відповіді від API ПриватБанку.")
                            return _generate_pb_api_error(response.status, "Невірний формат JSON відповіді від API ПриватБанку.")
                        except Exception as e:
                            logger.exception(f"Attempt {attempt + 1}: Error processing successful PrivatBank response for {cache_key_info}: {e}", exc_info=True)
                            return _generate_pb_api_error(response.status, f"Помилка обробки даних API ПриватБанку: {e}")
                    
                    elif response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=429, message="Rate limit from PrivatBank API")
                        logger.warning(f"Attempt {attempt + 1}: PrivatBank API RateLimit Error (429) for {cache_key_info}. Retrying...")
                    elif response.status >= 500:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} from PrivatBank API")
                        logger.warning(f"Attempt {attempt + 1}: PrivatBank API Server Error {response.status} for {cache_key_info}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: PrivatBank API Client Error {response.status} for {cache_key_info}. Response: {response_text_preview}")
                        return _generate_pb_api_error(response.status, f"Клієнтська помилка API ПриватБанку: {response.status}.")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to PrivatBank API for {cache_key_info}: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching PB rates for {cache_key_info}: {e}", exc_info=True)
            return _generate_pb_api_error(None, "Внутрішня помилка при обробці запиту курсів валют.")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next PrivatBank API retry for {cache_key_info}...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати курси валют ПриватБанку ({cache_key_info}) після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            
            final_error_code = 503
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504
            return _generate_pb_api_error(final_error_code, error_message)
            
    return _generate_pb_api_error(None, f"Не вдалося отримати курси валют ПриватБанку ({cache_key_info}) (неочікуваний вихід).")


def format_rates_message(api_response_wrapper: Dict[str, Any], cash: bool = True) -> str:
    course_type_name = "Готівковий" if cash else "Безготівковий (карти/Приват24)"
    
    if api_response_wrapper.get("status") == "error":
        error_msg = api_response_wrapper.get("message", "Невідома помилка API курсів.")
        return f"😥 Не вдалося отримати {course_type_name.lower()} курси валют.\n<i>Причина: {error_msg}</i>"

    rates_data_list = api_response_wrapper.get("data")

    if rates_data_list is None:
        logger.error("format_rates_message (PrivatBank): 'data' key missing in successful API response wrapper.")
        return f"😥 Помилка обробки даних курсів ({course_type_name.lower()})."
    
    if not isinstance(rates_data_list, list):
        logger.error(f"format_rates_message (PrivatBank): API data is not a list, but {type(rates_data_list)}")
        return f"😥 Помилка обробки даних: некоректний тип відповіді API ({course_type_name.lower()})."

    if not rates_data_list:
         return f"⚠️ {course_type_name} курси для USD та EUR на даний момент відсутні в API ПриватБанку."

    message_lines = [f"<b>{course_type_name} курс ПриватБанку:</b>\n"]
    
    found_valid_currencies = False
    for rate_item in rates_data_list:
        if not isinstance(rate_item, dict):
            logger.warning(f"Skipping non-dict item in rates_data_list (PrivatBank): {rate_item}")
            continue

        currency = rate_item.get("ccy")
        buy_str = rate_item.get("buy")
        sale_str = rate_item.get("sale")
        base_ccy = rate_item.get("base_ccy", "UAH")

        if currency not in TARGET_CURRENCIES:
            continue

        if buy_str is None or sale_str is None:
            logger.warning(f"Missing buy/sale for {currency} in PrivatBank rates: {rate_item}")
            continue
        
        try:
            buy_val = float(buy_str)
            sale_val = float(sale_str)
            message_lines.append(
                f"💵 <b>{currency}/{base_ccy}</b>: Купівля {buy_val:.2f} | Продаж {sale_val:.2f}"
            )
            found_valid_currencies = True
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing rate data for {currency} (PrivatBank): {rate_item}, error: {e}")
            continue
    
    if not found_valid_currencies:
        return f"⚠️ Не вдалося отримати коректні дані по курсам USD та EUR ({course_type_name.lower()})."

    return "\n".join(message_lines)