# src/modules/weather/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot
from aiocache import cached, Cache

from src import config

logger = logging.getLogger(__name__)

# Константы API
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Часовой пояс и параметры Retry
TZ_KYIV = pytz.timezone('Europe/Kyiv')
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

ICON_CODE_TO_EMOJI = {
    "01d": "☀️", "01n": "🌙", "02d": "🌤️", "02n": "☁️", "03d": "☁️", "03n": "☁️",
    "04d": "🌥️", "04n": "☁️", "09d": "🌦️", "09n": "🌦️", "10d": "🌧️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️", "50d": "🌫️", "50n": "🌫️",
}

def _weather_cache_key_builder(function_prefix: str, city_name: Optional[str] = None, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
    if city_name:
        # Приводим к нижнему регистру и убираем лишние пробелы для консистентности ключа
        return f"weather:{function_prefix}:city:{city_name.strip().lower()}"
    elif latitude is not None and longitude is not None:
        return f"weather:{function_prefix}:coords:{latitude:.4f}:{longitude:.4f}"
    logger.warning(f"_weather_cache_key_builder called with no city_name or coords for prefix {function_prefix}")
    return f"weather:{function_prefix}:unknown_params_{datetime.now().timestamp()}" # Делаем ключ уникальным, если нет параметров


# ИСПРАВЛЕНИЕ: key_builder теперь правильно извлекает позиционные аргументы
@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func_ref, bot_obj, city_name_arg, *pos_args, **named_args: _weather_cache_key_builder(
            "data", city_name=city_name_arg
        ),
        namespace="weather_service")
async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде. """
    # Убедимся, что city_name это строка и не пустая, прежде чем логировать или использовать
    safe_city_name = str(city_name).strip() if city_name else "UNKNOWN_CITY_INPUT"
    logger.info(f"Service get_weather_data: Called for city_name='{safe_city_name}'")
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}
    if not safe_city_name or safe_city_name == "UNKNOWN_CITY_INPUT":
        logger.warning(f"Service get_weather_data: Received empty or invalid city_name.")
        return {"cod": 400, "message": "City name cannot be empty"}


    params = {
        "q": safe_city_name, # Используем очищенное имя
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    last_exception = None
    api_url = OWM_API_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for '{safe_city_name}' from API")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OWM Weather API response for '{safe_city_name}': status={response.status}, name in data='{data.get('name')}', raw_data_preview={str(data)[:200]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM for '{safe_city_name}'. Response text: {response_data_text[:500]}")
                            return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{safe_city_name}' not found by OWM (404).")
                        return {"cod": 404, "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for '{safe_city_name}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Weather for '{safe_city_name}'.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": response.status, "message": f"Unexpected status {response.status}"}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM for '{safe_city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather for '{safe_city_name}': {e}", exc_info=True)
            return {"cod": 500, "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry for '{safe_city_name}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for weather '{safe_city_name}'. Last error: {last_exception!r}")
            # ... (возврат ошибок без изменений)
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": 504, "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data after multiple retries"}
    return None

# ИСПРАВЛЕНИЕ: key_builder теперь правильно извлекает позиционные аргументы
@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func_ref, bot_obj, lat_arg, lon_arg, *pos_args, **named_args: _weather_cache_key_builder(
            "data_coords", latitude=lat_arg, longitude=lon_arg
        ),
        namespace="weather_service")
async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде по координатам. """
    logger.info(f"Service get_weather_data_by_coords: Called for lat={latitude}, lon={longitude}")
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured for coords.")
        return {"cod": 500, "message": "API key not configured"}

    params = {
        "lat": latitude,
        "lon": longitude,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    # ... (остальная часть функции без изменений в логике, только возможное логгирование как в get_weather_data)
    last_exception = None
    api_url = OWM_API_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for coords ({latitude:.4f}, {longitude:.4f}) from API")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OWM Weather API response for coords ({latitude:.4f}, {longitude:.4f}): status={response.status}, name in data='{data.get('name')}', raw_data_preview={str(data)[:200]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM for coords. Response text: {response_data_text[:500]}")
                            return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for coords.")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for coords. Response: {response_data_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for coords. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM for coords.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": response.status, "message": f"Unexpected status {response.status}"}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM for coords: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather by coords: {e}", exc_info=True)
            return {"cod": 500, "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather by coords retry...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for coords ({latitude:.4f}, {longitude:.4f}). Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)): return {"cod": 504, "message": "Network/Timeout error after retries"}
            elif last_exception: return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data by coords after multiple retries"}
    return None

# ИСПРАВЛЕНИЕ: key_builder теперь правильно извлекает позиционные аргументы
@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func_ref, bot_obj, city_name_arg, *pos_args, **named_args: _weather_cache_key_builder(
            "forecast", city_name=city_name_arg
        ),
        namespace="weather_service")
async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней. """
    safe_city_name = str(city_name).strip() if city_name else "UNKNOWN_CITY_INPUT"
    logger.info(f"Service get_5day_forecast: Called for city_name='{safe_city_name}'")
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured for forecast.")
        return {"cod": "500", "message": "API key not configured"}
    if not safe_city_name or safe_city_name == "UNKNOWN_CITY_INPUT":
        logger.warning(f"Service get_5day_forecast: Received empty or invalid city_name.")
        return {"cod": "400", "message": "City name cannot be empty"}


    params = {
        "q": safe_city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }
    # ... (остальная часть функции без изменений в логике, только возможное логгирование как в get_weather_data)
    last_exception = None
    api_url = OWM_FORECAST_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for '{safe_city_name}' from API")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            city_name_from_forecast_api = data.get("city", {}).get("name", "N/A")
                            logger.debug(f"OWM Forecast API response for '{safe_city_name}': status={response.status}, city name in data='{city_name_from_forecast_api}', raw_data_preview={str(data)[:200]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM Forecast for '{safe_city_name}'. Response text: {response_data_text[:500]}")
                            return {"cod": "500", "message": "Invalid JSON response"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{safe_city_name}' not found by OWM Forecast (404).")
                        return {"cod": "404", "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for Forecast.")
                        return {"cod": "401", "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Forecast Client Error {response.status} for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        return {"cod": str(response.status), "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: OWM Forecast Server/RateLimit Error {response.status} for '{safe_city_name}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Forecast for '{safe_city_name}'.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": str(response.status), "message": f"Unexpected status {response.status}"}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM Forecast for '{safe_city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching 5-day forecast for '{safe_city_name}': {e}", exc_info=True)
            return {"cod": "500", "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next forecast retry for '{safe_city_name}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for 5-day forecast '{safe_city_name}'. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": str(last_exception.status), "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)): return {"cod": "504", "message": "Network/Timeout error after retries"}
            elif last_exception: return {"cod": "500", "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": "500", "message": "Failed to get forecast data after multiple retries"}
    return None


# --- format_weather_message и format_forecast_message остаются без изменений относительно предыдущей версии ---
# (они уже были достаточно детализированы в плане логирования и обработки ошибок)
def format_weather_message(data: Dict[str, Any], city_display_name_for_user: str) -> str:
    """ Форматирует сообщение о погоде. city_display_name_for_user - это имя, которое увидит пользователь. """
    try:
        cod = data.get("cod")
        if str(cod) != "200":
            message = data.get("message", "Невідома помилка API.")
            logger.warning(f"Weather API error for display name '{city_display_name_for_user}'. Code: {cod}, Message: {message}, Raw Data: {str(data)[:200]}")
            return f"😔 Не вдалося отримати погоду для <b>{city_display_name_for_user}</b>.\n<i>Причина: {message} (Код: {cod})</i>"

        main = data.get("main", {})
        weather_desc_list = data.get("weather", [{}])
        weather_desc = weather_desc_list[0] if weather_desc_list else {}
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        sys_info = data.get("sys", {})

        temp = main.get("temp")
        feels_like = main.get("feels_like")
        pressure_hpa = main.get("pressure")
        humidity = main.get("humidity")
        description = weather_desc.get("description", "немає опису")
        icon_code = weather_desc.get("icon")
        wind_speed = wind.get("speed")
        cloudiness = clouds.get("all")
        sunrise_ts = sys_info.get("sunrise")
        sunset_ts = sys_info.get("sunset")

        pressure_mmhg_str = "N/A"
        if pressure_hpa is not None:
            try:
                pressure_mmhg_str = f"{int(pressure_hpa * 0.750062)}"
            except ValueError:
                 logger.warning(f"Could not convert pressure {pressure_hpa} to mmhg.")

        emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")

        sunrise_str, sunset_str = "N/A", "N/A"
        if sunrise_ts:
            try:
                sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=TZ_KYIV).strftime('%H:%M')
            except (TypeError, ValueError):
                 logger.warning(f"Could not format sunrise timestamp {sunrise_ts}.")
        if sunset_ts:
            try:
                sunset_str = datetime.fromtimestamp(sunset_ts, tz=TZ_KYIV).strftime('%H:%M')
            except (TypeError, ValueError):
                 logger.warning(f"Could not format sunset timestamp {sunset_ts}.")

        dt_unix = data.get("dt")
        time_info = ""
        if dt_unix:
            try:
                current_time_str = datetime.fromtimestamp(dt_unix, tz=TZ_KYIV).strftime('%H:%M, %d.%m.%Y')
                time_info = f"<i>Дані актуальні на {current_time_str} (Київ)</i>"
            except (TypeError, ValueError):
                logger.warning(f"Could not format weather dt timestamp {dt_unix}.")

        message_lines = [
            f"<b>Погода в: {city_display_name_for_user}</b> {emoji}",
            f"🌡️ Температура: <b>{temp}°C</b> (відчувається як {feels_like}°C)",
            f"🌬️ Вітер: {wind_speed} м/с",
            f"💧 Вологість: {humidity}%",
            f"🌫️ Тиск: {pressure_mmhg_str} мм рт.ст.",
            f"☁️ Хмарність: {cloudiness}%",
            f"📝 Опис: {description.capitalize()}",
            f"🌅 Схід сонця: {sunrise_str}",
            f"🌇 Захід сонця: {sunset_str}",
            time_info
        ]
        return "\n".join(filter(None, message_lines))

    except Exception as e:
        logger.exception(f"Error formatting weather message for '{city_display_name_for_user}': {e}. Data: {str(data)[:500]}", exc_info=True)
        return f"😥 Помилка обробки даних погоди для <b>{city_display_name_for_user}</b>."

def format_forecast_message(data: Dict[str, Any], city_display_name_for_user: str) -> str:
    """ Форматирует сообщение с прогнозом погоды на 5 дней. """
    try:
        cod = data.get("cod")
        if str(cod) != "200":
            message = data.get("message", "Невідома помилка API.")
            logger.warning(f"Forecast API error for display name '{city_display_name_for_user}'. Code: {cod}, Message: {message}, Raw Data: {str(data)[:200]}")
            return f"😔 Не вдалося отримати прогноз для <b>{city_display_name_for_user}</b>.\n<i>Причина: {message} (Код: {cod})</i>"

        api_city_name_in_forecast = data.get("city", {}).get("name")
        header_city_name = city_display_name_for_user
        if "координатами" not in city_display_name_for_user.lower() and api_city_name_in_forecast:
            header_city_name = api_city_name_in_forecast.capitalize()

        message_lines = [f"<b>Прогноз погоди для: {header_city_name} на 5 днів:</b>\n"]
        forecast_list = data.get("list", [])
        
        daily_forecasts = {}
        if not forecast_list:
             logger.warning(f"Forecast list is empty for '{header_city_name}'. Data: {str(data)[:200]}")
             return "😥 На жаль, детальний прогноз на найближчі дні відсутній."

        for item in forecast_list:
            dt_txt = item.get("dt_txt")
            if not dt_txt:
                continue
            
            try:
                dt_obj_utc = datetime.strptime(dt_txt, '%Y-%m-%d %H:%M:%S')
                dt_obj_kyiv = dt_obj_utc.replace(tzinfo=pytz.utc).astimezone(TZ_KYIV)
                date_str = dt_obj_kyiv.strftime('%d.%m (%A)')
                
                if date_str not in daily_forecasts or \
                   (daily_forecasts[date_str].get("hour_diff", 24) > abs(dt_obj_kyiv.hour - 12) and dt_obj_kyiv.hour > 6 and dt_obj_kyiv.hour < 18) or \
                   (dt_obj_kyiv.hour == 12):

                    temp = item.get("main", {}).get("temp")
                    weather_desc_list = item.get("weather", [{}])
                    weather_desc_item = weather_desc_list[0] if weather_desc_list else {}
                    description = weather_desc_item.get("description", "N/A")
                    icon_code = weather_desc_item.get("icon")
                    emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")
                    
                    if temp is not None:
                        daily_forecasts[date_str] = {
                            "temp": temp,
                            "description": description,
                            "emoji": emoji,
                            "hour_diff": abs(dt_obj_kyiv.hour - 12),
                            "dt_obj_kyiv": dt_obj_kyiv
                        }
            except Exception as e_item:
                logger.warning(f"Could not parse forecast item {item} for '{header_city_name}': {e_item}")
                continue

        if not daily_forecasts:
            return f"😥 На жаль, детальний прогноз для <b>{header_city_name}</b> на найближчі дні відсутній."

        sorted_dates_keys = sorted(daily_forecasts.keys(), key=lambda d_key: daily_forecasts[d_key]["dt_obj_kyiv"])

        for date_key_str in sorted_dates_keys:
            forecast = daily_forecasts[date_key_str]
            message_lines.append(
                f"<b>{date_key_str}:</b> {forecast['temp']:.1f}°C, {forecast['description'].capitalize()} {forecast['emoji']}"
            )
        
        message_lines.append("\n<tg-spoiler>Прогноз може уточнюватися.</tg-spoiler>")
        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting forecast message for '{city_display_name_for_user}': {e}. Data: {str(data)[:500]}", exc_info=True)
        return f"😥 Помилка обробки даних прогнозу для <b>{city_display_name_for_user}</b>."