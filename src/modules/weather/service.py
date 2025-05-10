# src/modules/weather/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot
from aiocache import cached, Cache # Добавим Cache для возможной ручной проверки

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

# Вспомогательная функция для создания ключа кэша, чтобы избежать дублирования
def _weather_cache_key_builder(function_prefix: str, city_name: Optional[str] = None, latitude: Optional[float] = None, longitude: Optional[float] = None) -> str:
    if city_name:
        return f"weather:{function_prefix}:city:{city_name.lower()}"
    elif latitude is not None and longitude is not None:
        return f"weather:{function_prefix}:coords:{latitude:.4f}:{longitude:.4f}"
    return f"weather:{function_prefix}:unknown"


@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda f, *args, **kwargs: _weather_cache_key_builder("data", city_name=kwargs.get('city_name')), namespace="weather_service")
async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде. """
    logger.info(f"Service get_weather_data: Called for city_name='{city_name}'") # Лог входа
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
    # cache = caches.get('default') # Для возможной ручной работы с кэшем, если нужно

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for '{city_name}' from API")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text() # Прочитаем текст для логгирования в случае ошибки JSON
                    if response.status == 200:
                        try:
                            data = await response.json() # Попытка парсить из response, а не из прочитанного текста
                            logger.debug(f"OWM Weather API response for '{city_name}': status={response.status}, name in data='{data.get('name')}', raw_data_preview={str(data)[:200]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM for '{city_name}'. Response text: {response_data_text[:500]}")
                            return {"cod": 500, "message": "Invalid JSON response"}
                    # ... (остальная обработка ошибок без изменений) ...
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM (404).")
                        return {"cod": 404, "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for '{city_name}'. Response: {response_data_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for '{city_name}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Weather for '{city_name}'.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": response.status, "message": f"Unexpected status {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM for '{city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather for '{city_name}': {e}", exc_info=True)
            return {"cod": 500, "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry for '{city_name}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for weather '{city_name}'. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": 504, "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data after multiple retries"}
    return None

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda f, *args, **kwargs: _weather_cache_key_builder("data_coords", latitude=kwargs.get('latitude'), longitude=kwargs.get('longitude')), namespace="weather_service")
async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде по координатам. """
    logger.info(f"Service get_weather_data_by_coords: Called for lat={latitude}, lon={longitude}") # Лог входа
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
                    # ... (остальная обработка ошибок без изменений) ...
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for coords.")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429: # Client errors (кроме rate limit)
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for coords. Response: {response_data_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429: # Server errors or Rate limit
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status} for coords. Retrying...")
                    else: # Unexpected status
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
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": 504, "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data by coords after multiple retries"}
    return None # Should not be reached

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda f, *args, **kwargs: _weather_cache_key_builder("forecast", city_name=kwargs.get('city_name')), namespace="weather_service")
async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней. """
    logger.info(f"Service get_5day_forecast: Called for city_name='{city_name}'") # Лог входа
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured for forecast.")
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
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for '{city_name}' from API")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json()
                            # В ответе прогноза нет одного общего 'name', он есть в data['city']['name']
                            city_name_from_forecast_api = data.get("city", {}).get("name", "N/A")
                            logger.debug(f"OWM Forecast API response for '{city_name}': status={response.status}, city name in data='{city_name_from_forecast_api}', raw_data_preview={str(data)[:200]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM Forecast for '{city_name}'. Response text: {response_data_text[:500]}")
                            return {"cod": "500", "message": "Invalid JSON response"}
                    # ... (остальная обработка ошибок без изменений) ...
                    elif response.status == 404: # Город не найден
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM Forecast (404).")
                        return {"cod": "404", "message": "City not found"}
                    elif response.status == 401: # Неверный API ключ
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for Forecast.")
                        return {"cod": "401", "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429: # Другие клиентские ошибки
                        logger.error(f"Attempt {attempt + 1}: OWM Forecast Client Error {response.status} for '{city_name}'. Response: {response_data_text[:200]}")
                        return {"cod": str(response.status), "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429: # Серверные ошибки или Rate Limit
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Forecast Server/RateLimit Error {response.status} for '{city_name}'. Retrying...")
                    else: # Неожиданный статус
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Forecast for '{city_name}'.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": str(response.status), "message": f"Unexpected status {response.status}"}
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM Forecast for '{city_name}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching 5-day forecast for '{city_name}': {e}", exc_info=True)
            return {"cod": "500", "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next forecast retry for '{city_name}'...")
            await asyncio.sleep(delay)
        else:
            logger.error(f"All {MAX_RETRIES} attempts failed for 5-day forecast '{city_name}'. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": str(last_exception.status), "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": "504", "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": "500", "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": "500", "message": "Failed to get forecast data after multiple retries"}
    return None # Should not be reached


def format_weather_message(data: Dict[str, Any], city_display_name_for_user: str) -> str:
    """ Форматирует сообщение о погоде. city_display_name_for_user - это имя, которое увидит пользователь. """
    try:
        cod = data.get("cod")
        # API может вернуть cod как int (200) или str ("200")
        if str(cod) != "200":
            message = data.get("message", "Невідома помилка API.")
            logger.warning(f"Weather API error for display name '{city_display_name_for_user}'. Code: {cod}, Message: {message}, Raw Data: {str(data)[:200]}")
            return f"😔 Не вдалося отримати погоду для <b>{city_display_name_for_user}</b>.\n<i>Причина: {message} (Код: {cod})</i>"

        # ... (остальная часть функции форматирования без изменений) ...
        main = data.get("main", {})
        weather_desc_list = data.get("weather", [{}])
        weather_desc = weather_desc_list[0] if weather_desc_list else {} # Берем первый элемент, если есть
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
            except ValueError: # Если pressure_hpa не число
                 logger.warning(f"Could not convert pressure {pressure_hpa} to mmhg.")

        emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")

        sunrise_str, sunset_str = "N/A", "N/A"
        if sunrise_ts:
            try:
                sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=TZ_KYIV).strftime('%H:%M')
            except (TypeError, ValueError): # Если timestamp некорректный
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

        # API прогноза возвращает имя города в data['city']['name']
        api_city_name_in_forecast = data.get("city", {}).get("name")
        # Если city_display_name_for_user это что-то вроде "Прогноз за вашими координатами, м. Город", используем его.
        # Иначе, если есть имя от API прогноза, используем его.
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
                date_str = dt_obj_kyiv.strftime('%d.%m (%A)') # Более короткий формат даты
                
                # Сохраняем прогноз на 12:00 или 15:00 (ближе к полудню/дню)
                target_hours = [12, 15, 9] # Приоритет часов
                current_hour_diff = 24

                is_target_hour = False
                for th in target_hours:
                    if dt_obj_kyiv.hour == th:
                        is_target_hour = True
                        current_hour_diff = 0 # Точное попадание
                        break
                    # Если не точное попадание, вычисляем разницу для выбора ближайшего
                    # Это уже сделано в существующей логике, но можно упростить, если берем только конкретные часы
                
                # Логика для выбора одного прогноза в день (например, на 12:00 или 15:00)
                # Или можно показывать min/max температуру за день
                if date_str not in daily_forecasts or \
                   (daily_forecasts[date_str].get("hour_diff", 24) > abs(dt_obj_kyiv.hour - 12) and dt_obj_kyiv.hour > 6 and dt_obj_kyiv.hour < 18) or \
                   (dt_obj_kyiv.hour == 12): # Всегда предпочитаем 12:00

                    temp = item.get("main", {}).get("temp")
                    weather_desc_list = item.get("weather", [{}])
                    weather_desc_item = weather_desc_list[0] if weather_desc_list else {}
                    description = weather_desc_item.get("description", "N/A")
                    icon_code = weather_desc_item.get("icon")
                    emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")
                    
                    if temp is not None: # Убедимся, что температура есть
                        daily_forecasts[date_str] = {
                            "temp": temp,
                            "description": description,
                            "emoji": emoji,
                            "hour_diff": abs(dt_obj_kyiv.hour - 12), # для выбора ближайшего к полудню
                            "dt_obj_kyiv": dt_obj_kyiv # Сохраняем объект времени для сортировки
                        }
            except Exception as e_item:
                logger.warning(f"Could not parse forecast item {item} for '{header_city_name}': {e_item}")
                continue


        if not daily_forecasts:
            return f"😥 На жаль, детальний прогноз для <b>{header_city_name}</b> на найближчі дні відсутній."

        # Сортируем дни по дате
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