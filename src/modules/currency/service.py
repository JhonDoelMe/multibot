# src/modules/currency/service.py

import logging
import aiohttp
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# URL API ПриватБанка
PB_API_CASH_URL = "https://api.privatbank.ua/p24api/pubinfo?json&exchange&coursid=5"
PB_API_NONCASH_URL = "https://api.privatbank.ua/p24api/pubinfo?exchange&json&coursid=11"

# Валюты, которые нас интересуют
TARGET_CURRENCIES = ["USD", "EUR"] # Можно добавить "PLN", "GBP" и т.д.

async def get_pb_exchange_rates(cash: bool = True) -> Optional[List[Dict[str, Any]]]:
    """
    Получает курсы валют с публичного API ПриватБанка.

    Args:
        cash: True для получения наличного курса, False для безналичного.

    Returns:
        Список словарей с курсами или None в случае ошибки.
    """
    url = PB_API_CASH_URL if cash else PB_API_NONCASH_URL
    rate_type = "cash" if cash else "non-cash"
    logger.info(f"Requesting PrivatBank {rate_type} rates from {url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    try:
                        data = await response.json()
                        logger.debug(f"PrivatBank API response ({rate_type}): {data}")
                        # Фильтруем только нужные валюты
                        filtered_data = [rate for rate in data if rate.get("ccy") in TARGET_CURRENCIES]
                        return filtered_data
                    except aiohttp.ContentTypeError:
                        logger.error(f"Failed to decode JSON from PrivatBank API ({rate_type}). Response: {await response.text()}")
                        return None
                else:
                    logger.error(f"PrivatBank API error ({rate_type}): Status {response.status}, Response: {await response.text()}")
                    return None
    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network error connecting to PrivatBank API ({rate_type}): {e}")
        return None
    except Exception as e:
        logger.exception(f"An unexpected error occurred while fetching PrivatBank rates ({rate_type}): {e}")
        return None

def format_rates_message(rates: List[Dict[str, Any]], rate_type_name: str) -> str:
    """
    Форматирует список курсов валют в читаемое сообщение.

    Args:
        rates: Список словарей с курсами от API.
        rate_type_name: Название типа курса (напр., "Готівковий курс").

    Returns:
        Строка с отформатированным сообщением.
    """
    if not rates:
        return f"Не вдалося отримати {rate_type_name.lower()}."

    message_lines = [f"<b>{rate_type_name}:</b>\n"]

    for rate in rates:
        ccy = rate.get('ccy')
        buy = float(rate.get('buy', 0))
        sale = float(rate.get('sale', 0))
        # Форматируем до 2 знаков после запятой
        buy_str = f"{buy:.2f}"
        sale_str = f"{sale:.2f}"
        message_lines.append(f"<b>{ccy}:</b>  Купівля {buy_str} / Продаж {sale_str}")

    # Добавляем информацию об источнике
    message_lines.append("\n<tg-spoiler>Джерело: api.privatbank.ua</tg-spoiler>")

    return "\n".join(message_lines)