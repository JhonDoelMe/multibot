# src/modules/weather_backup/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot
from aiocache import cached

from src import config
# Импортируем существующий словарь эмодзи и украинских дней недели
from src.modules.weather.service import ICON_CODE_TO_EMOJI as SHARED_ICON_EMOJI
from src.modules.weather.service import DAYS_OF_WEEK_UK

logger = logging.getLogger(__name__)

# Константы API для WeatherAPI.com
WEATHERAPI_BASE_URL = "http://api.weatherapi.com/v1"
WEATHERAPI_CURRENT_URL = f"{WEATHERAPI_BASE_URL}/current.json"
WEATHERAPI_FORECAST_URL = f"{WEATHERAPI_BASE_URL}/forecast.json"

# Часовой пояс и параметры Retry
TZ_KYIV = pytz.timezone('Europe/Kyiv') # Уже есть в основном модуле, но для независимости можно оставить
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

# Примерный маппинг кодов состояния WeatherAPI.com на эмодзи
# Это потребует изучения документации WeatherAPI.com для получения полного списка кодов
# и их соответствия существующим эмодзи.
# Ключи - это condition.code из ответа API.
# https://www.weatherapi.com/docs/weather_conditions.json
WEATHERAPI_CONDITION_CODE_TO_EMOJI = {
    1000: "☀️",  # Sunny / Clear (для ночи можно будет смотреть is_day)
    1003: "🌤️",  # Partly cloudy
    1006: "☁️",  # Cloudy
    1009: "🌥️",  # Overcast
    1030: "🌫️",  # Mist
    1063: "🌦️",  # Patchy rain possible
    1066: "🌨️",  # Patchy snow possible
    1069: "🌨️",  # Patchy sleet possible
    1072: "🌨️",  # Patchy freezing drizzle possible
    1087: "⛈️",  # Thundery outbreaks possible
    1114: "❄️",  # Blowing snow
    1117: " Blizzard", # Blizzard
    1135: "🌫️",  # Fog
    1147: "🌫️",  # Freezing fog
    1150: "🌦️",  # Patchy light drizzle
    1153: "🌦️",  # Light drizzle
    1168: "🌨️",  # Freezing drizzle
    1171: "🌨️",  # Heavy freezing drizzle
    1180: "🌦️",  # Patchy light rain
    1183: "🌧️",  # Light rain
    1186: "🌧️",  # Moderate rain at times
    1189: "🌧️",  # Moderate rain
    1192: "🌧️",  # Heavy rain at times
    1195: "🌧️",  # Heavy rain
    1198: "🌨️",  # Light freezing rain
    1201: "🌨️",  # Moderate or heavy freezing rain
    1204: "🌨️",  # Light sleet
    1207: "🌨️",  # Moderate or heavy sleet
    1210: "🌨️",  # Patchy light snow
    1213: "❄️",  # Light snow
    1216: "❄️",  # Patchy moderate snow
    1219: "❄️",  # Moderate snow
    1222: "❄️",  # Patchy heavy snow
    1225: "❄️",  # Heavy snow
    1237: "❄️",  # Ice pellets
    1240: "🌧️",  # Light rain shower
    1243: "🌧️",  # Moderate or heavy rain shower
    1246: "🌧️",  # Torrential rain shower
    1249: "🌨️",  # Light sleet showers
    1252: "🌨️",  # Moderate or heavy sleet showers
    1255: "❄️",  # Light snow showers
    1258: "❄️",  # Moderate or heavy snow showers
    1261: "❄️",  # Light showers of ice pellets
    1264: "❄️",  # Moderate or heavy showers of ice pellets
    1273: "⛈️",  # Patchy light rain with thunder
    1276: "⛈️",  # Moderate or heavy rain with thunder
    1279: "⛈️❄️", # Patchy light snow with thunder
    1282: "⛈️❄️", # Moderate or heavy snow with thunder
}


def _weatherapi_cache_key_builder(endpoint: str, location: str) -> str:
    safe_location = location.strip().lower() if location else "unknown_location"
    return f"weatherapi:{endpoint}:location:{safe_location}"

@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda func, bot_obj, location_str: _weatherapi_cache_key_builder("current", location_str),
        namespace="weather_backup_service")
async def get_current_weather_weatherapi(bot: Bot, location: str) -> Optional[Dict[str, Any]]:
    """ Получает текущую погоду с WeatherAPI.com. Location может быть городом или 'lat,lon'. """
    logger.info(f"Service get_current_weather_weatherapi: Called for location='{location}'")
    if not config.WEATHERAPI_COM_KEY:
        logger.error("WeatherAPI.com key (WEATHERAPI_COM_KEY) is not configured.")
        return {"error": {"code": 500, "message": "Ключ резервного API погоди не налаштовано"}}
    if not location:
        logger.warning("Service get_current_weather_weatherapi: Received empty location.")
        return {"error": {"code": 400, "message": "Назва міста або координати не можуть бути порожніми"}}

    params = {"key": config.WEATHERAPI_COM_KEY, "q": location, "lang": "uk"}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch current weather for '{location}' from WeatherAPI.com")
            async with aiohttp.ClientSession() as session:
                async with session.get(WEATHERAPI_CURRENT_URL, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            # Проверка на наличие ошибки в самом ответе API
                            if "error" in data:
                                logger.warning(f"WeatherAPI.com returned an error for '{location}': {data['error']}")
                                return data # Возвращаем структуру ошибки от API
                            logger.debug(f"WeatherAPI.com current weather response for '{location}': status={response.status}, data preview={str(data)[:300]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            # Приравниваем к стандартной структуре ошибки, если возможно
                            return {"error": {"code": 500, "message": "Невірний формат JSON відповіді від резервного API"}}
                    # WeatherAPI обычно возвращает ошибки в JSON с кодом 200, но обработаем и другие статусы
                    elif response.status == 400: # Bad Request (e.g. q not provided, or an internal API error reported as 400)
                         logger.warning(f"WeatherAPI.com returned 400 Bad Request for '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(); return data # Попытаться извлечь ошибку из JSON
                         except: return {"error": {"code": 400, "message": "Некоректний запит до резервного API"}}
                    elif response.status == 401: # Unauthorized
                        logger.error(f"WeatherAPI.com returned 401 Unauthorized (Invalid API key).")
                        return {"error": {"code": 401, "message": "Невірний ключ резервного API погоди"}}
                    elif response.status == 403: # Forbidden
                        logger.error(f"WeatherAPI.com returned 403 Forbidden (Key disabled or over quota).")
                        return {"error": {"code": 403, "message": "Доступ до резервного API погоди заборонено (можливо, перевищено ліміт)"}}
                    elif response.status >= 500 or response.status == 429: # Server errors or Rate limit (though 429 might be handled by 403 if over quota)
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: WeatherAPI.com Server/RateLimit Error {response.status} for '{location}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from WeatherAPI.com for '{location}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"error": {"code": response.status, "message": f"Неочікувана помилка резервного API: {response.status}"}}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to WeatherAPI.com for '{location}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching current weather from WeatherAPI.com for '{location}': {e}", exc_info=True)
            return {"error": {"code": 500, "message": "Внутрішня помилка обробки резервної погоди"}}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay}s before next WeatherAPI.com current weather retry for '{location}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for WeatherAPI.com current weather '{location}'. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError): return {"error": {"code": last_exception.status, "message": f"Помилка резервного API після ретраїв: {last_exception.message}"}}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)): return {"error": {"code": 504, "message": "Помилка мережі/таймауту резервного API"}}
            elif last_exception: return {"error": {"code": 500, "message": f"Не вдалося отримати дані після ретраїв: {str(last_exception)}"}}
            return {"error": {"code": 500, "message": "Не вдалося отримати резервні дані погоди"}}
    return None # Should not be reached

@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda func, bot_obj, location_str, days_arg: _weatherapi_cache_key_builder(f"forecast{days_arg}d", location_str),
        namespace="weather_backup_service")
async def get_forecast_weatherapi(bot: Bot, location: str, days: int = 3) -> Optional[Dict[str, Any]]:
    """ Получает прогноз погоды с WeatherAPI.com. Бесплатный план обычно до 3 дней. """
    logger.info(f"Service get_forecast_weatherapi: Called for location='{location}', days={days}")
    if not config.WEATHERAPI_COM_KEY:
        logger.error("WeatherAPI.com key (WEATHERAPI_COM_KEY) is not configured.")
        return {"error": {"code": 500, "message": "Ключ резервного API прогнозу не налаштовано"}}
    if not location:
        logger.warning("Service get_forecast_weatherapi: Received empty location.")
        return {"error": {"code": 400, "message": "Назва міста або координати не можуть бути порожніми"}}
    if not 1 <= days <= 10: # WeatherAPI позволяет до 10 (но бесплатный меньше)
        logger.warning(f"Service get_forecast_weatherapi: Invalid number of days requested: {days}. Using 3.")
        days = 3

    params = {"key": config.WEATHERAPI_COM_KEY, "q": location, "days": days, "lang": "uk", "alerts": "no", "aqi": "no"}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch {days}-day forecast for '{location}' from WeatherAPI.com")
            async with aiohttp.ClientSession() as session:
                async with session.get(WEATHERAPI_FORECAST_URL, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            if "error" in data:
                                logger.warning(f"WeatherAPI.com returned an error for forecast '{location}', {days}d: {data['error']}")
                                return data
                            logger.debug(f"WeatherAPI.com forecast response for '{location}', {days}d: status={response.status}, data preview={str(data)[:300]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON forecast from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            return {"error": {"code": 500, "message": "Невірний формат JSON відповіді від резервного API прогнозу"}}
                    # ... (аналогичная обработка ошибок, как в get_current_weather_weatherapi) ...
                    elif response.status == 400:
                         logger.warning(f"WeatherAPI.com returned 400 Bad Request for forecast '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(); return data
                         except: return {"error": {"code": 400, "message": "Некоректний запит до резервного API прогнозу"}}
                    elif response.status == 401:
                        logger.error(f"WeatherAPI.com returned 401 Unauthorized for forecast (Invalid API key).")
                        return {"error": {"code": 401, "message": "Невірний ключ резервного API прогнозу"}}
                    elif response.status == 403:
                        logger.error(f"WeatherAPI.com returned 403 Forbidden for forecast (Key disabled or over quota).")
                        return {"error": {"code": 403, "message": "Доступ до резервного API прогнозу заборонено"}}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: WeatherAPI.com Server/RateLimit Error {response.status} for forecast '{location}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from WeatherAPI.com for forecast '{location}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"error": {"code": response.status, "message": f"Неочікувана помилка резервного API прогнозу: {response.status}"}}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to WeatherAPI.com for forecast '{location}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching forecast from WeatherAPI.com for '{location}': {e}", exc_info=True)
            return {"error": {"code": 500, "message": "Внутрішня помилка обробки резервного прогнозу"}}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay}s before next WeatherAPI.com forecast retry for '{location}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for WeatherAPI.com forecast '{location}'. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError): return {"error": {"code": last_exception.status, "message": f"Помилка резервного API прогнозу після ретраїв: {last_exception.message}"}}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)): return {"error": {"code": 504, "message": "Помилка мережі/таймауту резервного API прогнозу"}}
            elif last_exception: return {"error": {"code": 500, "message": f"Не вдалося отримати дані прогнозу після ретраїв: {str(last_exception)}"}}
            return {"error": {"code": 500, "message": "Не вдалося отримати резервні дані прогнозу"}}
    return None # Should not be reached


def format_weather_backup_message(data: Dict[str, Any], requested_location: str) -> str:
    """ Форматирует сообщение о текущей погоде из WeatherAPI.com. """
    if "error" in data:
        error_info = data["error"]
        return f"😔 Не вдалося отримати резервну погоду для <b>{requested_location}</b>.\n<i>Причина: {error_info.get('message', 'Невідома помилка')} (Код: {error_info.get('code', 'N/A')})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    location = data.get("location", {})
    current = data.get("current", {})
    condition = current.get("condition", {})

    city_name = location.get("name", requested_location)
    region = location.get("region")
    country = location.get("country")
    
    display_location = city_name
    if region and region.lower() != city_name.lower():
        display_location += f", {region}"
    # if country and country.lower() != city_name.lower() and country.lower() != region.lower() :
    #     display_location += f", {country}" # Можно добавить страну, если нужно

    temp_c = current.get("temp_c")
    feelslike_c = current.get("feelslike_c")
    condition_text = condition.get("text", "немає опису")
    condition_code = condition.get("code") # Числовой код состояния
    wind_kph = current.get("wind_kph")
    wind_dir = current.get("wind_dir")
    pressure_mb = current.get("pressure_mb") # Миллибары, почти то же, что hPa
    humidity = current.get("humidity")
    cloud = current.get("cloud") # Облачность в процентах
    is_day = current.get("is_day", 1) # 1 = Да, 0 = Нет
    
    localtime_epoch = location.get("localtime_epoch")
    time_info = ""
    if localtime_epoch:
        try:
            # Время уже локальное для города, просто форматируем
            dt_local = datetime.fromtimestamp(localtime_epoch) 
            # Для консистентности можно привести к Киевскому времени, но API уже дает локальное.
            # Если хотим всегда Киевское, нужно знать TZ города или использовать UTC из API.
            # Пока оставим локальное время города.
            current_time_str = dt_local.strftime('%H:%M, %d.%m.%Y')
            time_info = f"<i>Дані актуальні на {current_time_str} (місцевий час)</i>"
        except Exception as e:
            logger.warning(f"Could not format localtime_epoch {localtime_epoch}: {e}")


    emoji = WEATHERAPI_CONDITION_CODE_TO_EMOJI.get(condition_code, "")
    if not emoji and condition_code == 1000 and not is_day: # Clear night
        emoji = "🌙"


    pressure_mmhg_str = "N/A"
    if pressure_mb is not None:
        try:
            pressure_mmhg_str = f"{int(pressure_mb * 0.750062)}"
        except ValueError:
            logger.warning(f"Could not convert pressure {pressure_mb} (mb) to mmhg.")

    wind_mps_str = "N/A"
    if wind_kph is not None:
        try:
            wind_mps = wind_kph * 1000 / 3600
            wind_mps_str = f"{wind_mps:.1f}"
        except ValueError:
            logger.warning(f"Could not convert wind speed {wind_kph} (kph) to m/s.")


    message_lines = [
        f"<b>Резервна погода в: {display_location}</b> {emoji}",
        f"🌡️ Температура: <b>{temp_c}°C</b> (відчувається як {feelslike_c}°C)",
        f"🌬️ Вітер: {wind_mps_str} м/с ({wind_dir})",
        f"💧 Вологість: {humidity}%",
        f"🌫️ Тиск: {pressure_mmhg_str} мм рт.ст.",
        f"☁️ Хмарність: {cloud}%",
        f"📝 Опис: {condition_text.capitalize()}",
        time_info,
        "\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"
    ]
    return "\n".join(filter(None, message_lines))


def format_forecast_backup_message(data: Dict[str, Any], requested_location: str) -> str:
    """ Форматирует прогноз погоды на несколько дней от WeatherAPI.com. """
    if "error" in data:
        error_info = data["error"]
        return f"😔 Не вдалося отримати резервний прогноз для <b>{requested_location}</b>.\n<i>Причина: {error_info.get('message', 'Невідома помилка')} (Код: {error_info.get('code', 'N/A')})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    location_data = data.get("location", {})
    forecast_data = data.get("forecast", {})
    forecast_days = forecast_data.get("forecastday", [])

    city_name = location_data.get("name", requested_location)
    
    message_lines = [f"<b>Резервний прогноз для: {city_name}</b>\n"]

    if not forecast_days:
        message_lines.append("😥 На жаль, детальний прогноз на найближчі дні відсутній.")
    else:
        for day_data in forecast_days:
            date_epoch = day_data.get("date_epoch")
            day_info = day_data.get("day", {})
            condition = day_info.get("condition", {})

            date_str_formatted = "N/A"
            if date_epoch:
                try:
                    dt_obj = datetime.fromtimestamp(date_epoch)
                    day_name_en = dt_obj.strftime('%A')
                    day_name_uk = DAYS_OF_WEEK_UK.get(day_name_en, day_name_en)
                    date_str_formatted = dt_obj.strftime(f'%d.%m ({day_name_uk})')
                except Exception as e:
                    logger.warning(f"Could not format forecast date_epoch {date_epoch}: {e}")
                    date_str_formatted = day_data.get("date", "N/A") # Fallback to YYYY-MM-DD

            avg_temp_c = day_info.get("avgtemp_c")
            max_temp_c = day_info.get("maxtemp_c")
            min_temp_c = day_info.get("mintemp_c")
            condition_text = condition.get("text", "немає опису")
            condition_code = condition.get("code")
            
            emoji = WEATHERAPI_CONDITION_CODE_TO_EMOJI.get(condition_code, "")

            temp_display = f"{avg_temp_c}°C" if avg_temp_c is not None else f"{min_temp_c}°C / {max_temp_c}°C"

            message_lines.append(
                f"<b>{date_str_formatted}:</b> {temp_display}, {condition_text.capitalize()} {emoji}"
            )
            
    message_lines.append("\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>")
    return "\n".join(filter(None, message_lines))