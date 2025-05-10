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
from src.modules.weather.service import ICON_CODE_TO_EMOJI as SHARED_ICON_EMOJI
from src.modules.weather.service import DAYS_OF_WEEK_UK

logger = logging.getLogger(__name__)

WEATHERAPI_BASE_URL = "http://api.weatherapi.com/v1"
WEATHERAPI_CURRENT_URL = f"{WEATHERAPI_BASE_URL}/current.json"
WEATHERAPI_FORECAST_URL = f"{WEATHERAPI_BASE_URL}/forecast.json"

TZ_KYIV = pytz.timezone('Europe/Kyiv')
MAX_RETRIES = config.MAX_RETRIES
INITIAL_DELAY = config.INITIAL_DELAY

WEATHERAPI_CONDITION_CODE_TO_EMOJI = {
    1000: "☀️", 1003: "🌤️", 1006: "☁️", 1009: "🌥️", 1030: "🌫️", 1063: "🌦️",
    1066: "🌨️", 1069: "🌨️", 1072: "🌨️", 1087: "⛈️", 1114: "❄️", 1117: "❄️",
    1135: "🌫️", 1147: "🌫️", 1150: "🌦️", 1153: "🌦️", 1168: "🌨️", 1171: "🌨️",
    1180: "🌦️", 1183: "🌧️", 1186: "🌧️", 1189: "🌧️", 1192: "🌧️", 1195: "🌧️",
    1198: "🌨️", 1201: "🌨️", 1204: "🌨️", 1207: "🌨️", 1210: "🌨️", 1213: "❄️",
    1216: "❄️", 1219: "❄️", 1222: "❄️", 1225: "❄️", 1237: "❄️", 1240: "🌧️",
    1243: "🌧️", 1246: "🌧️", 1249: "🌨️", 1252: "🌨️", 1255: "❄️", 1258: "❄️",
    1261: "❄️", 1264: "❄️", 1273: "⛈️", 1276: "⛈️", 1279: "⛈️❄️", 1282: "⛈️❄️",
}

# <<< НОВЫЙ СЛОВАРЬ ДЛЯ ПЕРЕВОДА НАПРАВЛЕНИЙ ВЕТРА >>>
WIND_DIRECTIONS_UK = {
    "N": "Пн", "NNE": "Пн-Пн-Сх", "NE": "Пн-Сх", "ENE": "Сх-Пн-Сх",
    "E": "Сх", "ESE": "Сх-Пд-Сх", "SE": "Пд-Сх", "SSE": "Пд-Пд-Сх",
    "S": "Пд", "SSW": "Пд-Пд-Зх", "SW": "Пд-Зх", "WSW": "Зх-Пд-Зх",
    "W": "Зх", "WNW": "Зх-Пн-Зх", "NW": "Пн-Зх", "NNW": "Пн-Пн-Зх",
    # Добавим возможные варианты с нижним регистром или полные названия, если API их может вернуть
    "North": "Пн", "East": "Сх", "South": "Пд", "West": "Зх",
}

def _weatherapi_generic_key_builder(func_ref, *args, **kwargs) -> str:
    endpoint_name = kwargs.get("endpoint_name", "unknown_endpoint")
    location_str = kwargs.get("location", "unknown_location")
    days_arg = kwargs.get("days", None)
    safe_location = str(location_str).strip().lower() if location_str else "unknown_location"
    key = f"weatherapi:{endpoint_name}:location:{safe_location}"
    if days_arg is not None:
        key += f":days:{days_arg}"
    return key

@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda f, *a, **kw: _weatherapi_generic_key_builder(f, *a, **kw, endpoint_name="current"),
        namespace="weather_backup_service")
async def get_current_weather_weatherapi(bot: Bot, *, location: str) -> Optional[Dict[str, Any]]:
    logger.info(f"Service get_current_weather_weatherapi: Called with location='{location}'")
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
                            if "error" in data:
                                # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                                logger.error(f"WeatherAPI.com returned an error for '{location}': {data['error']}")
                                return data
                            logger.debug(f"WeatherAPI.com current weather response for '{location}': status={response.status}, data preview={str(data)[:300]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            return {"error": {"code": 500, "message": "Невірний формат JSON відповіді від резервного API"}}
                    elif response.status == 400:
                         # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                         logger.error(f"WeatherAPI.com returned 400 Bad Request for '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(); return data
                         except: return {"error": {"code": 400, "message": "Некоректний запит до резервного API"}}
                    elif response.status == 401:
                        # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                        logger.error(f"WeatherAPI.com returned 401 Unauthorized (Invalid API key).")
                        return {"error": {"code": 401, "message": "Невірний ключ резервного API погоди"}}
                    elif response.status == 403:
                        # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                        logger.error(f"WeatherAPI.com returned 403 Forbidden (Key disabled or over quota).")
                        return {"error": {"code": 403, "message": "Доступ до резервного API погоди заборонено (можливо, перевищено ліміт)"}}
                    elif response.status >= 500 or response.status == 429:
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
    return None

@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda f, *a, **kw: _weatherapi_generic_key_builder(f, *a, **kw, endpoint_name="forecast"),
        namespace="weather_backup_service")
async def get_forecast_weatherapi(bot: Bot, *, location: str, days: int = 3) -> Optional[Dict[str, Any]]:
    logger.info(f"Service get_forecast_weatherapi: Called for location='{location}', days={days}")
    if not config.WEATHERAPI_COM_KEY:
        logger.error("WeatherAPI.com key (WEATHERAPI_COM_KEY) is not configured.")
        return {"error": {"code": 500, "message": "Ключ резервного API прогнозу не налаштовано"}}
    if not location:
        logger.warning("Service get_forecast_weatherapi: Received empty location.")
        return {"error": {"code": 400, "message": "Назва міста або координати не можуть бути порожніми"}}
    if not 1 <= days <= 10:
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
                                # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                                logger.error(f"WeatherAPI.com returned an error for forecast '{location}', {days}d: {data['error']}")
                                return data
                            logger.debug(f"WeatherAPI.com forecast response for '{location}', {days}d: status={response.status}, data preview={str(data)[:300]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON forecast from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            return {"error": {"code": 500, "message": "Невірний формат JSON відповіді від резервного API прогнозу"}}
                    elif response.status == 400:
                         # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com как error
                         logger.error(f"WeatherAPI.com returned 400 Bad Request for forecast '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(); return data
                         except: return {"error": {"code": 400, "message": "Некоректний запит до резервного API прогнозу"}}
                    elif response.status == 401:
                        # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com як error
                        logger.error(f"WeatherAPI.com returned 401 Unauthorized for forecast (Invalid API key).")
                        return {"error": {"code": 401, "message": "Невірний ключ резервного API прогнозу"}}
                    elif response.status == 403:
                        # ИСПРАВЛЕНИЕ: Логируем ошибку API WeatherAPI.com як error
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
    return None

def format_weather_backup_message(data: Dict[str, Any], requested_location: str) -> str:
    if "error" in data:
        error_info = data["error"]
        return f"😔 Не вдалося отримати резервну погоду для <b>{requested_location}</b>.\n<i>Причина: {error_info.get('message', 'Невідома помилка')} (Код: {error_info.get('code', 'N/A')})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    location = data.get("location", {})
    current = data.get("current", {})
    condition = current.get("condition", {})

    city_name = location.get("name", requested_location)
    region = location.get("region")
    # country = location.get("country") # Можно добавить, если нужно
    
    display_location = city_name
    if region and region.lower() != city_name.lower():
        display_location += f", {region}"

    temp_c = current.get("temp_c")
    feelslike_c = current.get("feelslike_c")
    condition_text = condition.get("text", "немає опису")
    condition_code = condition.get("code")
    wind_kph = current.get("wind_kph")
    wind_dir_en = current.get("wind_dir", "")  # Например "SSW"
    pressure_mb = current.get("pressure_mb")
    humidity = current.get("humidity")
    cloud = current.get("cloud")
    is_day = current.get("is_day", 1)
    
    localtime_epoch = location.get("localtime_epoch")
    time_info = ""
    if localtime_epoch:
        try:
            dt_local = datetime.fromtimestamp(localtime_epoch)
            current_time_str = dt_local.strftime('%H:%M, %d.%m.%Y')
            time_info = f"<i>Дані актуальні на {current_time_str} (місцевий час)</i>"
        except Exception as e:
            logger.warning(f"Could not format localtime_epoch {localtime_epoch}: {e}")

    emoji = WEATHERAPI_CONDITION_CODE_TO_EMOJI.get(condition_code, "")
    if not emoji and condition_code == 1000 and not is_day: emoji = "🌙"

    pressure_mmhg_str = "N/A"
    if pressure_mb is not None:
        try: pressure_mmhg_str = f"{int(pressure_mb * 0.750062)}"
        except ValueError: logger.warning(f"Could not convert pressure {pressure_mb} (mb) to mmhg.")

    wind_mps_str = "N/A"
    if wind_kph is not None:
        try:
            wind_mps = wind_kph * 1000 / 3600
            wind_mps_str = f"{wind_mps:.1f}"
        except ValueError: logger.warning(f"Could not convert wind speed {wind_kph} (kph) to m/s.")

    # <<< ИСПРАВЛЕНИЕ: Перевод направления ветра >>>
    wind_dir_uk = WIND_DIRECTIONS_UK.get(wind_dir_en.upper(), wind_dir_en) # Переводим или оставляем как есть

    message_lines = [
        f"<b>Резервна погода в: {display_location}</b> {emoji}",
        f"🌡️ Температура: <b>{temp_c}°C</b> (відчувається як {feelslike_c}°C)",
        f"🌬️ Вітер: {wind_mps_str} м/с ({wind_dir_uk})", # Используем переведенное направление
        f"💧 Вологість: {humidity}%",
        f"🌫️ Тиск: {pressure_mmhg_str} мм рт.ст.",
        f"☁️ Хмарність: {cloud}%",
        f"📝 Опис: {condition_text.capitalize()}",
        time_info,
        "\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"
    ]
    return "\n".join(filter(None, message_lines))


def format_forecast_backup_message(data: Dict[str, Any], requested_location: str) -> str:
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
                    date_str_formatted = day_data.get("date", "N/A")

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