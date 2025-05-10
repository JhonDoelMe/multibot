# src/modules/weather/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

# Константы API
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Часовой пояс и параметры Retry
TZ_KYIV = pytz.timezone('Europe/Kyiv')
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

# Словарь для эмодзи по коду иконки OpenWeatherMap
ICON_CODE_TO_EMOJI = {
    "01d": "☀️", "01n": "🌙",  # clear sky
    "02d": "🌤️", "02n": "☁️",  # few clouds
    "03d": "☁️", "03n": "☁️",  # scattered clouds
    "04d": "🌥️", "04n": "☁️",  # broken clouds
    "09d": "🌦️", "09n": "🌦️",  # shower rain
    "10d": "🌧️", "10n": "🌧️",  # rain
    "11d": "⛈️", "11n": "⛈️",  # thunderstorm
    "13d": "❄️", "13n": "❄️",  # snow
    "50d": "🌫️", "50n": "🌫️",  # mist
}

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda *args, **kwargs: f"weather:city:{kwargs.get('city_name', '').lower()}", namespace="weather")
async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    last_exception = None
    api_url = OWM_API_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {city_name}")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OWM Weather response: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM. Response: {await response.text()}")
                            return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM (404).")
                        return {"cod": 404, "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status}. Response: {error_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Weather.")
                        last_exception = Exception(f"Unexpected status {response.status}")

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather: {e}", exc_info=True)
            return {"cod": 500, "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for weather {city_name}. Last error: {last_exception!r}")
            return None
    return None

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda *args, **kwargs: f"weather:coords:{kwargs.get('latitude', 0):.4f}:{kwargs.get('longitude', 0):.4f}", namespace="weather")
async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде по координатам. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    last_exception = None
    api_url = OWM_API_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for coords ({latitude:.4f}, {longitude:.4f})")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OWM Weather response for coords: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM. Response: {await response.text()}")
                            return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status}. Response: {error_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM.")
                        last_exception = Exception(f"Unexpected status {response.status}")

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather by coords: {e}", exc_info=True)
            return {"cod": 500, "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for coords ({latitude:.4f}, {longitude:.4f}). Last error: {last_exception!r}")
            return None
    return None

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda *args, **kwargs: f"forecast:city:{kwargs.get('city_name', '').lower()}", namespace="weather")
async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": "500", "message": "API key not configured"}

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    last_exception = None
    api_url = OWM_FORECAST_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for {city_name}")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OWM Forecast response: {data}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM. Response: {await response.text()}")
                            return {"cod": "500", "message": "Invalid JSON response"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM (404).")
                        return {"cod": "404", "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": "401", "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status}. Response: {error_text[:200]}")
                        return {"cod": str(response.status), "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status}"
                        )
                        logger.warning(f"Attempt {