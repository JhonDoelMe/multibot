# src/modules/weather/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime as dt_datetime, timedelta, timezone
import pytz
from aiogram import Bot
from aiocache import cached

from src import config

logger = logging.getLogger(__name__)

OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

try:
    TZ_KYIV = pytz.timezone('Europe/Kyiv')
except pytz.exceptions.UnknownTimeZoneError:
    logger.error("Timezone 'Europe/Kyiv' not found. Using UTC as fallback for Kyiv time.")
    TZ_KYIV = timezone.utc

MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

ICON_CODE_TO_EMOJI = {
    "01d": "☀️", "01n": "🌙", "02d": "🌤️", "02n": "☁️", "03d": "☁️", "03n": "☁️",
    "04d": "🌥️", "04n": "☁️", "09d": "🌦️", "09n": "🌦️", "10d": "🌧️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️", "50d": "🌫️", "50n": "🌫️",
}

DAYS_OF_WEEK_UK = {
    "Monday": "Понеділок", "Tuesday": "Вівторок", "Wednesday": "Середа",
    "Thursday": "Четвер", "Friday": "П'ятниця", "Saturday": "Субота", "Sunday": "Неділя",
}

def _generate_error_response(code: int, message: str, service_name: str = "OpenWeatherMap") -> Dict[str, Any]:
    logger.error(f"{service_name} API Error: Code {code}, Message: {message}")
    return {"cod": str(code), "message": message, "error_source": service_name}

def _weather_cache_key_builder(function_prefix: str, city_name: Optional[str] = None, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
    safe_prefix = str(function_prefix).strip().lower()
    if city_name:
        safe_city_name = str(city_name).strip().lower()
        return f"weather:{safe_prefix}:city:{safe_city_name}"
    elif latitude is not None and longitude is not None:
        return f"weather:{safe_prefix}:coords:{latitude:.4f}:{longitude:.4f}"
    logger.warning(f"_weather_cache_key_builder called with no city_name or coords for prefix {safe_prefix}. Generating unique key.")
    return f"weather:{safe_prefix}:unknown_params_{dt_datetime.now().timestamp()}_{city_name}_{latitude}_{longitude}"

@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func, bot_arg, **kwargs: _weather_cache_key_builder(
            "data_city", 
            city_name=kwargs.get("city_name") 
        ),
        namespace="weather_service")
async def get_weather_data(bot: Bot, *, city_name: str) -> Dict[str, Any]:
    safe_city_name = str(city_name).strip() if city_name else ""
    logger.info(f"Service get_weather_data: Called for city_name='{safe_city_name}'")

    if not config.WEATHER_API_KEY:
        return _generate_error_response(500, "Ключ OpenWeatherMap API (WEATHER_API_KEY) не налаштовано.")
    if not safe_city_name:
        logger.warning("Service get_weather_data: Received empty city_name.")
        return _generate_error_response(400, "Назва міста не може бути порожньою.")

    params = { "q": safe_city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None
    api_url = OWM_API_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for '{safe_city_name}' from OWM")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"OWM Weather API response for '{safe_city_name}': status={response.status}, name in data='{data.get('name')}', raw_data_preview={str(data)[:200]}")
                            
                            # --- ТИМЧАСОВО ВИМКНЕНО ПЕРЕВІРКУ КРАЇНИ ---
                            # country_code = data.get("sys", {}).get("country")
                            # if country_code and country_code.upper() != "UA":
                            #     api_name = data.get('name', safe_city_name)
                            #     logger.warning(f"City '{safe_city_name}' (API name: {api_name}) found in country {country_code}, not UA. (Country check currently disabled for testing)")
                            #     # Замість повернення помилки, просто логуємо і продовжуємо
                            #     # return _generate_error_response(404, f"Місто '{api_name}' знаходиться поза межами України.")
                            # --- КІНЕЦЬ ТИМЧАСОВО ВИМКНЕНОЇ ПЕРЕВІРКИ ---
                            
                            if str(data.get("cod")) == "200":
                                return data
                            else:
                                api_err_message = data.get("message", "Невідома помилка від API OpenWeatherMap")
                                api_err_code = data.get("cod", response.status)
                                logger.warning(f"OWM API returned HTTP 200 but error in JSON for '{safe_city_name}': Code {api_err_code}, Msg: {api_err_message}")
                                return _generate_error_response(int(api_err_code), api_err_message)
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM for '{safe_city_name}'. Response text: {response_data_text[:500]}")
                            last_exception = Exception("Невірний формат JSON відповіді від OpenWeatherMap")
                            return _generate_error_response(500, "Невірний формат JSON відповіді від OpenWeatherMap.")
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{safe_city_name}' not found by OWM (404).")
                        return _generate_error_response(404, f"Місто '{safe_city_name}' не знайдено.")
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return _generate_error_response(401, "Невірний ключ API OpenWeatherMap.")
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        return _generate_error_response(response.status, f"Клієнтська помилка OpenWeatherMap: {response.status}.")
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for '{safe_city_name}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Weather for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Неочікуваний статус відповіді: {response.status}")
                        return _generate_error_response(response.status, f"Неочікуваний статус відповіді: {response.status}.")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM for '{safe_city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather for '{safe_city_name}': {e}", exc_info=True)
            return _generate_error_response(500, "Внутрішня помилка при обробці запиту погоди.")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry for '{safe_city_name}'...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати дані погоди для '{safe_city_name}' після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            final_error_code = 503 
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504
            return _generate_error_response(final_error_code, error_message)
    return _generate_error_response(500, f"Не вдалося отримати дані для '{safe_city_name}' (неочікуваний вихід з функції).")

@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func, bot_arg, **kwargs: _weather_cache_key_builder(
            "data_coords", 
            latitude=kwargs.get("latitude"), 
            longitude=kwargs.get("longitude")
        ),
        namespace="weather_service")
async def get_weather_data_by_coords(bot: Bot, *, latitude: float, longitude: float) -> Dict[str, Any]:
    logger.info(f"Service get_weather_data_by_coords: Called for lat={latitude}, lon={longitude}")
    if not config.WEATHER_API_KEY:
        return _generate_error_response(500, "Ключ OpenWeatherMap API (WEATHER_API_KEY) не налаштовано.")

    params = {"lat": latitude, "lon": longitude, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None
    api_url = OWM_API_URL
    location_str = f"coords ({latitude:.4f}, {longitude:.4f})"

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {location_str} from OWM")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            logger.debug(f"OWM Weather API response for {location_str}: status={response.status}, name in data='{data.get('name')}', raw_data_preview={str(data)[:200]}")
                            
                            # --- ТИМЧАСОВО ВИМКНЕНО ПЕРЕВІРКУ КРАЇНИ ДЛЯ КООРДИНАТ (якщо ви вирішили її тут не робити) ---
                            # country_code = data.get("sys", {}).get("country")
                            # if country_code and country_code.upper() != "UA":
                            #     api_name = data.get('name', location_str)
                            #     logger.warning(f"Coords {location_str} (API name: {api_name}) resolved to country {country_code}, not UA. (Country check disabled for coords)")
                            #     # return _generate_error_response(404, f"Локація за координатами ({api_name}) знаходиться поза межами України.")
                            # --- КІНЕЦЬ ТИМЧАСОВО ВИМКНЕНОЇ ПЕРЕВІРКИ ---

                            if str(data.get("cod")) == "200":
                                return data
                            else:
                                api_err_message = data.get("message", "Невідома помилка від API OpenWeatherMap")
                                api_err_code = data.get("cod", response.status)
                                logger.warning(f"OWM API returned HTTP 200 but error in JSON for {location_str}: Code {api_err_code}, Msg: {api_err_message}")
                                return _generate_error_response(int(api_err_code), api_err_message)
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM for {location_str}. Response text: {response_data_text[:500]}")
                            last_exception = Exception("Невірний формат JSON відповіді від OpenWeatherMap")
                            return _generate_error_response(500, "Невірний формат JSON відповіді від OpenWeatherMap.")
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for {location_str}.")
                        return _generate_error_response(401, "Невірний ключ API OpenWeatherMap.")
                    elif 400 <= response.status < 500 and response.status != 404 and response.status != 429 :
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for {location_str}. Response: {response_data_text[:200]}")
                        return _generate_error_response(response.status, f"Клієнтська помилка OpenWeatherMap: {response.status}.")
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for {location_str}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM for {location_str}. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Неочікуваний статус відповіді: {response.status}")
                        return _generate_error_response(response.status, f"Неочікуваний статус відповіді: {response.status}.")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM for {location_str}: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather by {location_str}: {e}", exc_info=True)
            return _generate_error_response(500, "Внутрішня помилка при обробці запиту погоди за координатами.")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather by {location_str} retry...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати дані погоди для {location_str} після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            final_error_code = 503
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504
            return _generate_error_response(final_error_code, error_message)
    return _generate_error_response(500, f"Не вдалося отримати дані для {location_str} (неочікуваний вихід з функції).")


@cached(ttl=config.CACHE_TTL_WEATHER,
        key_builder=lambda func, bot_arg, **kwargs: _weather_cache_key_builder(
            "forecast_city", city_name=kwargs.get("city_name")
        ),
        namespace="weather_service")
async def get_5day_forecast(bot: Bot, *, city_name: str) -> Dict[str, Any]:
    safe_city_name = str(city_name).strip() if city_name else ""
    logger.info(f"Service get_5day_forecast: Called for city_name='{safe_city_name}'")

    if not config.WEATHER_API_KEY:
        return _generate_error_response(500, "Ключ OpenWeatherMap API (WEATHER_API_KEY) не налаштовано для прогнозу.")
    if not safe_city_name:
        logger.warning("Service get_5day_forecast: Received empty city_name.")
        return _generate_error_response(400, "Назва міста для прогнозу не може бути порожньою.")

    params = {"q": safe_city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None
    api_url = OWM_FORECAST_URL

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for '{safe_city_name}' from OWM")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            city_name_from_forecast_api = data.get("city", {}).get("name", "N/A")
                            logger.debug(f"OWM Forecast API response for '{safe_city_name}': status={response.status}, city name in data='{city_name_from_forecast_api}', raw_data_preview={str(data)[:200]}")
                            
                            # --- ТИМЧАСОВО ВИМКНЕНО ПЕРЕВІРКУ КРАЇНИ ---
                            # country_code_forecast = data.get("city", {}).get("country")
                            # if country_code_forecast and country_code_forecast.upper() != "UA":
                            #     api_name = data.get("city", {}).get("name", safe_city_name)
                            #     logger.warning(f"Forecast for city '{safe_city_name}' (API name: {api_name}) is for country {country_code_forecast}, not UA. (Country check disabled)")
                            #     # return _generate_error_response(404, f"Прогноз для міста '{api_name}' доступний, але воно поза межами України.", service_name="OpenWeatherMap Forecast")
                            # --- КІНЕЦЬ ТИМЧАСОВО ВИМКНЕНОЇ ПЕРЕВІРКИ ---

                            if str(data.get("cod")) == "200":
                                return data
                            else:
                                api_err_message = data.get("message", "Невідома помилка від API прогнозу OpenWeatherMap")
                                api_err_code = data.get("cod", response.status)
                                logger.warning(f"OWM Forecast API returned HTTP 200 but error in JSON for '{safe_city_name}': Code {api_err_code}, Msg: {api_err_message}")
                                return _generate_error_response(int(api_err_code), api_err_message, service_name="OpenWeatherMap Forecast")
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM Forecast for '{safe_city_name}'. Response text: {response_data_text[:500]}")
                            last_exception = Exception("Невірний формат JSON відповіді від OWM Forecast")
                            return _generate_error_response(500, "Невірний формат JSON відповіді від OWM Forecast.", service_name="OpenWeatherMap Forecast")
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{safe_city_name}' not found by OWM Forecast (404).")
                        return _generate_error_response(404, f"Місто '{safe_city_name}' не знайдено для прогнозу.", service_name="OpenWeatherMap Forecast")
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for Forecast.")
                        return _generate_error_response(401, "Невірний ключ API OpenWeatherMap для прогнозу.", service_name="OpenWeatherMap Forecast")
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Forecast Client Error {response.status} for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        return _generate_error_response(response.status, f"Клієнтська помилка OWM Forecast: {response.status}.", service_name="OpenWeatherMap Forecast")
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: OWM Forecast Server/RateLimit Error {response.status} for '{safe_city_name}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Forecast for '{safe_city_name}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Неочікуваний статус відповіді: {response.status}")
                        return _generate_error_response(response.status, f"Неочікуваний статус відповіді: {response.status}.", service_name="OpenWeatherMap Forecast")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM Forecast for '{safe_city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching 5-day forecast for '{safe_city_name}': {e}", exc_info=True)
            return _generate_error_response(500, "Внутрішня помилка при обробці запиту прогнозу.", service_name="OpenWeatherMap Forecast")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next forecast retry for '{safe_city_name}'...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати прогноз для '{safe_city_name}' після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            final_error_code = 503
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504
            return _generate_error_response(final_error_code, error_message, service_name="OpenWeatherMap Forecast")
    return _generate_error_response(500, f"Не вдалося отримати прогноз для '{safe_city_name}' (неочікуваний вихід з функції).", service_name="OpenWeatherMap Forecast")

def format_weather_message(data: Dict[str, Any], city_display_name_for_user: str, is_coords_request: bool = False) -> str:
    try:
        if "error_source" in data or str(data.get("cod")) != "200":
            error_message = data.get("message", "Невідома помилка API.")
            error_code = data.get("cod", "N/A")
            logger.warning(f"Weather API error for display name '{city_display_name_for_user}'. Code: {error_code}, Message: {error_message}, Raw Data: {str(data)[:200]}")
            return f"😔 Не вдалося отримати погоду для <b>{city_display_name_for_user}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>"

        main = data.get("main", {})
        weather_desc_list = data.get("weather", [])
        weather_desc = weather_desc_list[0] if weather_desc_list else {}
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        sys_info = data.get("sys", {})
        
        api_city_name = data.get("name_display") or data.get("name")

        header_text: str
        if is_coords_request:
            if api_city_name:
                header_text = f"<b>Погода (м. {api_city_name}, за координатами)</b>"
            else: 
                header_text = f"<b>Погода за вашими координатами ({city_display_name_for_user})</b>"
        else:
            header_text = f"<b>Погода в: {api_city_name or city_display_name_for_user}</b>"

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
            try: pressure_mmhg_str = f"{int(pressure_hpa * 0.750062)}"
            except (ValueError, TypeError) as e: logger.warning(f"Could not convert pressure {pressure_hpa} to mmhg: {e}")

        emoji = ICON_CODE_TO_EMOJI.get(icon_code, "🛰️")

        sunrise_str, sunset_str = "N/A", "N/A"
        if sunrise_ts:
            try: sunrise_str = dt_datetime.fromtimestamp(sunrise_ts, tz=TZ_KYIV).strftime('%H:%M')
            except (TypeError, ValueError) as e: logger.warning(f"Could not format sunrise timestamp {sunrise_ts}: {e}")
        if sunset_ts:
            try: sunset_str = dt_datetime.fromtimestamp(sunset_ts, tz=TZ_KYIV).strftime('%H:%M')
            except (TypeError, ValueError) as e: logger.warning(f"Could not format sunset timestamp {sunset_ts}: {e}")

        dt_unix = data.get("dt")
        time_info = ""
        if dt_unix:
            try:
                current_time_str = dt_datetime.fromtimestamp(dt_unix, tz=TZ_KYIV).strftime('%H:%M, %d.%m.%Y')
                time_info = f"<i>Дані актуальні на {current_time_str} (Київ)</i>"
            except (TypeError, ValueError) as e: logger.warning(f"Could not format weather dt timestamp {dt_unix}: {e}")

        message_lines = [f"{header_text} {emoji}"]
        if temp is not None and feels_like is not None: message_lines.append(f"🌡️ Температура: <b>{temp:.1f}°C</b> (відчувається як {feels_like:.1f}°C)")
        elif temp is not None: message_lines.append(f"🌡️ Температура: <b>{temp:.1f}°C</b>")
        if wind_speed is not None: message_lines.append(f"🌬️ Вітер: {wind_speed} м/с")
        if humidity is not None: message_lines.append(f"💧 Вологість: {humidity}%")
        message_lines.append(f"🌫️ Тиск: {pressure_mmhg_str} мм рт.ст.")
        if cloudiness is not None: message_lines.append(f"☁️ Хмарність: {cloudiness}%")
        message_lines.append(f"📝 Опис: {description.capitalize()}")
        message_lines.append(f"🌅 Схід сонця: {sunrise_str}")
        message_lines.append(f"🌇 Захід сонця: {sunset_str}")
        if time_info: message_lines.append(time_info)

        return "\n".join(filter(None, message_lines))
    except Exception as e:
        logger.exception(f"Error formatting weather message for '{city_display_name_for_user}': {e}. Data: {str(data)[:500]}", exc_info=True)
        return f"😥 Вибачте, сталася помилка при обробці даних погоди для <b>{city_display_name_for_user}</b>."

def format_forecast_message(data: Dict[str, Any], city_display_name_for_user: str) -> str:
    try:
        if "error_source" in data or str(data.get("cod")) != "200":
            error_message = data.get("message", "Невідома помилка API прогнозу.")
            error_code = data.get("cod", "N/A")
            logger.warning(f"Forecast API error for display name '{city_display_name_for_user}'. Code: {error_code}, Message: {error_message}, Raw Data: {str(data)[:200]}")
            return f"😔 Не вдалося отримати прогноз для <b>{city_display_name_for_user}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>"

        api_city_info = data.get("city", {})
        api_city_name_in_forecast = api_city_info.get("name_display") or api_city_info.get("name")
        
        header_city_name = city_display_name_for_user
        if "координатами" in city_display_name_for_user.lower() and api_city_name_in_forecast:
            header_city_name = f"м. {api_city_name_in_forecast} (за координатами)"
        elif api_city_name_in_forecast:
            header_city_name = api_city_name_in_forecast.capitalize()

        message_lines = [f"<b>Прогноз погоди для: {header_city_name} на найближчі дні:</b>\n"]
        forecast_list = data.get("list", [])
        
        if not forecast_list:
             logger.warning(f"Forecast list is empty for '{header_city_name}'. Data: {str(data)[:200]}")
             return f"😥 На жаль, детальний прогноз для <b>{header_city_name}</b> на найближчі дні відсутній."

        daily_forecasts: Dict[str, Dict[str, Any]] = {}

        for item in forecast_list:
            dt_txt = item.get("dt_txt")
            if not dt_txt: continue
            main_item_data = item.get("main", {})
            temp = main_item_data.get("temp")
            weather_desc_list_item = item.get("weather", [])
            weather_desc_item = weather_desc_list_item[0] if weather_desc_list_item else {}
            description = weather_desc_item.get("description")
            icon_code = weather_desc_item.get("icon")
            if temp is None or description is None: continue

            try:
                dt_obj_utc = dt_datetime.strptime(dt_txt, '%Y-%m-%d %H:%M:%S')
                dt_obj_kyiv = dt_obj_utc.replace(tzinfo=timezone.utc).astimezone(TZ_KYIV)
                day_name_en = dt_obj_kyiv.strftime('%A')
                day_name_uk = DAYS_OF_WEEK_UK.get(day_name_en, day_name_en)
                date_str = dt_obj_kyiv.strftime(f'%d.%m ({day_name_uk})')
                current_hour_diff = abs(dt_obj_kyiv.hour - 12)

                if date_str not in daily_forecasts or \
                   current_hour_diff < daily_forecasts[date_str].get("hour_diff_from_noon", 24) :
                    daily_forecasts[date_str] = {
                        "temp": temp, "description": description,
                        "emoji": ICON_CODE_TO_EMOJI.get(icon_code, "🛰️"),
                        "hour_diff_from_noon": current_hour_diff,
                        "dt_obj_kyiv": dt_obj_kyiv
                    }
            except Exception as e_item:
                logger.warning(f"Could not parse forecast item {item} for '{header_city_name}': {e_item}")
                continue

        if not daily_forecasts:
            return f"😥 На жаль, детальний прогноз для <b>{header_city_name}</b> на найближчі дні відсутній (після обробки)."

        sorted_dates_keys = sorted(daily_forecasts.keys(), key=lambda d_key: daily_forecasts[d_key]["dt_obj_kyiv"])
        
        days_to_show = 0
        for date_key_str in sorted_dates_keys:
            if days_to_show >= 5: 
                break
            forecast_details = daily_forecasts[date_key_str]
            message_lines.append(
                f"<b>{date_key_str}:</b> {forecast_details['temp']:.1f}°C, {forecast_details['description'].capitalize()} {forecast_details['emoji']}"
            )
            days_to_show += 1
        
        message_lines.append("\n<tg-spoiler>Прогноз може уточнюватися. Дані наведені для денного часу.</tg-spoiler>")
        return "\n".join(message_lines)
    except Exception as e:
        logger.exception(f"Error formatting forecast message for '{city_display_name_for_user}': {e}. Data: {str(data)[:500]}", exc_info=True)
        return f"😥 Вибачте, сталася помилка при обробці даних прогнозу для <b>{city_display_name_for_user}</b>."

def format_tomorrow_forecast_message(
    forecast_api_response: Dict[str, Any],
    city_display_name_for_user: str
) -> str:
    try:
        if "error_source" in forecast_api_response or str(forecast_api_response.get("cod")) != "200":
            error_message = forecast_api_response.get("message", "Невідома помилка API прогнозу.")
            error_code = forecast_api_response.get("cod", "N/A")
            logger.warning(f"Tomorrow's forecast: API error for '{city_display_name_for_user}'. Code: {error_code}, Msg: {error_message}")
            return f"😔 Не вдалося отримати прогноз на завтра для <b>{city_display_name_for_user}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>"

        forecast_list_all_days = forecast_api_response.get("list", [])
        api_city_info = forecast_api_response.get("city", {})
        api_city_name = api_city_info.get("name_display") or api_city_info.get("name")
        
        header_city_name = city_display_name_for_user
        if "координатами" in city_display_name_for_user.lower() and api_city_name:
            header_city_name = f"м. {api_city_name} (за координатами)"
        elif api_city_name:
            header_city_name = api_city_name.capitalize()

        if not forecast_list_all_days:
            logger.warning(f"Tomorrow's forecast: Forecast list is empty for '{header_city_name}'.")
            return f"😥 Детальний прогноз на завтра для <b>{header_city_name}</b> відсутній (немає даних)."

        now_in_kyiv = dt_datetime.now(TZ_KYIV)
        tomorrow_date_kyiv = (now_in_kyiv + timedelta(days=1)).date()
        
        logger.debug(f"Tomorrow's forecast: Looking for date {tomorrow_date_kyiv} for '{header_city_name}'")

        tomorrow_hourly_forecasts = []
        for item in forecast_list_all_days:
            dt_txt = item.get("dt_txt")
            if not dt_txt: continue
            try:
                dt_obj_utc = dt_datetime.strptime(dt_txt, '%Y-%m-%d %H:%M:%S')
                dt_obj_kyiv = dt_obj_utc.replace(tzinfo=timezone.utc).astimezone(TZ_KYIV)
                if dt_obj_kyiv.date() == tomorrow_date_kyiv:
                    tomorrow_hourly_forecasts.append(item)
            except ValueError:
                logger.warning(f"Tomorrow's forecast: Could not parse dt_txt '{dt_txt}' for item.")
                continue
        
        if not tomorrow_hourly_forecasts:
            logger.warning(f"Tomorrow's forecast: No forecast items found for {tomorrow_date_kyiv} for '{header_city_name}'.")
            return f"😥 Детальний прогноз на завтра для <b>{header_city_name}</b> відсутній (немає даних на завтра)."

        day_name_en = tomorrow_date_kyiv.strftime('%A')
        day_name_uk = DAYS_OF_WEEK_UK.get(day_name_en, day_name_en)
        date_str_formatted = tomorrow_date_kyiv.strftime(f'%d.%m.%Y ({day_name_uk})')

        message_lines = [f"☀️ <b>Прогноз на завтра, {date_str_formatted}, для: {header_city_name}</b>\n"]
        
        min_temp_tomorrow = float('inf')
        max_temp_tomorrow = float('-inf')
        condition_counts: Dict[str, int] = {}
        
        hourly_details_lines = ["\n<b>Погодинно:</b>"]

        for item in tomorrow_hourly_forecasts:
            main_info = item.get("main", {})
            weather_info_list = item.get("weather", [{}])
            weather_info = weather_info_list[0] if weather_info_list else {}
            
            temp = main_info.get("temp")
            description = weather_info.get("description", "")
            icon_code = weather_info.get("icon")
            dt_txt = item.get("dt_txt")
            dt_obj_kyiv = dt_datetime.strptime(dt_txt, '%Y-%m-%d %H:%M:%S').replace(tzinfo=timezone.utc).astimezone(TZ_KYIV)
            time_str = dt_obj_kyiv.strftime('%H:%M')
            emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")

            if temp is not None:
                min_temp_tomorrow = min(min_temp_tomorrow, temp)
                max_temp_tomorrow = max(max_temp_tomorrow, temp)
            
            if description:
                condition_counts[description.capitalize()] = condition_counts.get(description.capitalize(), 0) + 1
            
            hourly_details_lines.append(f"  <b>{time_str}</b>: {temp:.0f}°C, {description.capitalize()} {emoji}")

        if min_temp_tomorrow != float('inf'):
             message_lines.append(f"🌡️ Температура: від {min_temp_tomorrow:.0f}°C до {max_temp_tomorrow:.0f}°C")
        
        if condition_counts:
            dominant_condition = max(condition_counts, key=condition_counts.get)
            message_lines.append(f"📝 Переважно: {dominant_condition}")
        
        message_lines.extend(hourly_details_lines)
        message_lines.append("\n<tg-spoiler>Прогноз може уточнюватися.</tg-spoiler>")
        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting tomorrow's detailed forecast for '{city_display_name_for_user}': {e}", exc_info=True)
        return f"😥 Вибачте, сталася помилка при обробці детального прогнозу на завтра для <b>{city_display_name_for_user}</b>."