# src/modules/weather/service.py (Исправлен AttributeError)

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot

from src import config

logger = logging.getLogger(__name__)
# ... (Константы и ICON_CODE_TO_EMOJI) ...
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"; OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"; TZ_KYIV = pytz.timezone('Europe/Kyiv'); MAX_RETRIES = 3; INITIAL_DELAY = 1; ICON_CODE_TO_EMOJI = {"01d": "☀️", "01n": "🌙", "02d": "🌤️", "02n": "☁️", "03d": "☁️","03n": "☁️", "04d": "🌥️", "04n": "☁️", "09d": "🌦️", "09n": "🌦️","10d": "🌧️", "10n": "🌧️", "11d": "⛈️", "11n": "⛈️", "13d": "❄️","13n": "❄️", "50d": "🌫️", "50n": "🌫️"}

async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    if not config.WEATHER_API_KEY: logger.error("..."); return {"cod": 500, "message": "..."}
    params = {"q": city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_API_URL
    # <<< Добавляем контекстный менеджер >>>
    async with bot.session as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1} weather for {city_name}")
                # <<< Используем session.get >>>
                async with session.get(api_url, params=params, timeout=10) as response:
                    # ... (логика обработки response/ошибок/retry) ...
                    if response.status == 200:
                         try: data = await response.json(); return data
                         except aiohttp.ContentTypeError: return {"cod": 500, "message": "..."}
                    # ... (404, 401, 4xx) ...
                    elif response.status == 404: return {"cod": 404, "message": "..."}
                    elif response.status == 401: return {"cod": 401, "message": "..."}
                    elif 400 <= response.status < 500: return {"cod": response.status, "message": "..."}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                    else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
            except Exception as e: logger.exception(f"... Unexpected error: {e}"); return {"cod": 500, "message": "..."}
            if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else: logger.error(f"All attempts failed... Last error: {last_exception!r}"); # ... (return error) ...
    return {"cod": 500, "message": "Failed after all retries"}

async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    if not config.WEATHER_API_KEY: logger.error("..."); return {"cod": 500, "message": "..."}
    params = {"lat": latitude, "lon": longitude, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_API_URL
    # <<< Добавляем контекстный менеджер >>>
    async with bot.session as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1} weather for coords")
                # <<< Используем session.get >>>
                async with session.get(api_url, params=params, timeout=10) as response:
                    # ... (логика обработки response/ошибок/retry) ...
                    if response.status == 200:
                         try: data = await response.json(); return data
                         except aiohttp.ContentTypeError: return {"cod": 500, "message": "..."}
                    elif response.status == 401: return {"cod": 401, "message": "..."}
                    elif 400 <= response.status < 500 and response.status != 429: return {"cod": response.status, "message": "..."}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                    else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
            except Exception as e: logger.exception(f"... Unexpected error: {e}"); return {"cod": 500, "message": "..."}
            if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else: logger.error(f"All attempts failed... Last error: {last_exception!r}"); # ... (return error) ...
    return {"cod": 500, "message": "Failed after all retries"}

async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    if not config.WEATHER_API_KEY: logger.error("..."); return {"cod": "500", "message": "..."}
    params = {"q": city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_FORECAST_URL
    # <<< Добавляем контекстный менеджер >>>
    async with bot.session as session:
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1} forecast for {city_name}")
                # <<< Используем session.get >>>
                async with session.get(api_url, params=params, timeout=15) as response:
                    # ... (логика обработки response/ошибок/retry) ...
                     if response.status == 200:
                         try: data = await response.json(); return data
                         except aiohttp.ContentTypeError: return {"cod": "500", "message": "..."}
                     elif response.status == 404: return {"cod": "404", "message": "..."}
                     elif response.status == 401: return {"cod": "401", "message": "..."}
                     elif 400 <= response.status < 500 and response.status != 429: return {"cod": str(response.status), "message": "..."}
                     elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                     else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
            except Exception as e: logger.exception(f"... Unexpected error: {e}"); return {"cod": "500", "message": "..."}
            if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else: logger.error(f"All attempts failed... Last error: {last_exception!r}"); # ... (return error) ...
    return {"cod": "500", "message": "Failed after all forecast retries"}

# --- Функции форматирования без изменений ---
def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код как в ответе #121) ...
    try: # ... (извлечение данных) ...
        icon_code=weather_info.get("icon"); icon_emoji=ICON_CODE_TO_EMOJI.get(icon_code, "❓") # ... (остальное форматирование) ...
        return "\n".join(message_lines)
    except Exception as e: logger.exception(...); return "..."

def format_forecast_message(forecast_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код как в ответе #121) ...
    try: # ... (проверка cod='200') ...
         forecast_list = forecast_data.get("list"); # ... (группировка по дням) ...
         for date_str in sorted_dates: # ... (форматирование каждого дня) ...
              message_lines.append(...)
         return "\n".join(message_lines)
    except Exception as e: logger.exception(...); return "..."