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
                            # Возвращаем ошибку, чтобы хендлер мог ее обработать
                            last_exception = Exception("Invalid JSON response")
                            # Не выходим из цикла сразу, даем шанс другим попыткам, если это не ContentTypeError
                            # Однако, если ContentTypeError, то последующие попытки вряд ли помогут
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
                    elif response.status >= 500 or response.status == 429: # Серверные ошибки или Rate Limit
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server/RateLimit Error {response.status}. Retrying...")
                    else: # Неожиданный статус
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Weather.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        # Для неожиданных статусов, возможно, не стоит ретраить, сразу вернуть ошибку
                        return {"cod": response.status, "message": f"Unexpected status {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM: {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching weather: {e}", exc_info=True)
            # Для неизвестных ошибок прекращаем попытки и возвращаем ошибку
            return {"cod": 500, "message": "Internal processing error"}

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next weather retry...")
            await asyncio.sleep(delay)
        else: # Если все попытки исчерпаны
            logger.error(f"All {MAX_RETRIES} attempts failed for weather {city_name}. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": 504, "message": "Network/Timeout error after retries"} # 504 Gateway Timeout
            elif last_exception: # Если было какое-то другое исключение
                 return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data after multiple retries"}
    return None # Этот return не должен достигаться, если цикл ретраев всегда возвращает значение

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
                    # Координаты обычно не дают 404, но на всякий случай можно добавить обработку клиентских ошибок
                    elif 400 <= response.status < 500 and response.status != 429:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status} for coords. Response: {error_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
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
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": last_exception.status, "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": 504, "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": 500, "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": 500, "message": "Failed to get weather data by coords after multiple retries"}
    return None # Недостижимо

@cached(ttl=config.CACHE_TTL_WEATHER, key_builder=lambda *args, **kwargs: f"forecast:city:{kwargs.get('city_name', '').lower()}", namespace="weather")
async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": "500", "message": "API key not configured"} # Используем строки для `cod` как в оригинале

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
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM Forecast. Response: {await response.text()}")
                            return {"cod": "500", "message": "Invalid JSON response"}
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM Forecast (404).")
                        return {"cod": "404", "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401) for Forecast.")
                        return {"cod": "401", "message": "Invalid API key"}
                    elif 400 <= response.status < 500 and response.status != 429:
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Forecast Client Error {response.status}. Response: {error_text[:200]}")
                        return {"cod": str(response.status), "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info, response.history,
                            status=response.status, message=f"Server error {response.status} or Rate limit"
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Forecast Server/RateLimit Error {response.status}. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM Forecast.")
                        last_exception = Exception(f"Unexpected status {response.status}")
                        return {"cod": str(response.status), "message": f"Unexpected status {response.status}"}

        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM Forecast: {e}. Retrying...")
        except Exception as e: # Общее исключение
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching 5-day forecast: {e}", exc_info=True)
            return {"cod": "500", "message": "Internal processing error"} # Возвращаем ошибку

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next forecast retry...")
            await asyncio.sleep(delay)
        else: # Все попытки исчерпаны
            logger.error(f"All {MAX_RETRIES} attempts failed for 5-day forecast {city_name}. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError):
                return {"cod": str(last_exception.status), "message": f"API error after retries: {last_exception.message}"}
            elif isinstance(last_exception, (aiohttp.ClientConnectorError, asyncio.TimeoutError)):
                return {"cod": "504", "message": "Network/Timeout error after retries"}
            elif last_exception:
                 return {"cod": "500", "message": f"Failed after retries: {str(last_exception)}"}
            return {"cod": "500", "message": "Failed to get forecast data after multiple retries"}
    return None # Недостижимо

def format_weather_message(data: Dict[str, Any], city_display_name: str) -> str:
    """ Форматирует сообщение о погоде. """
    try:
        cod = data.get("cod")
        if str(cod) != "200": # OWM возвращает cod как int для успеха, но может быть str для ошибок в прогнозе
            message = data.get("message", "Невідома помилка API.")
            logger.warning(f"Weather API error for {city_display_name}. Code: {cod}, Message: {message}")
            return f"😔 Не вдалося отримати погоду для <b>{city_display_name}</b>.\n<i>Причина: {message} (Код: {cod})</i>"

        main = data.get("main", {})
        weather_desc = data.get("weather", [{}])[0]
        wind = data.get("wind", {})
        clouds = data.get("clouds", {})
        sys_info = data.get("sys", {})

        temp = main.get("temp")
        feels_like = main.get("feels_like")
        pressure_hpa = main.get("pressure")
        humidity = main.get("humidity")
        description = weather_desc.get("description", "Немає опису")
        icon_code = weather_desc.get("icon")
        wind_speed = wind.get("speed")
        cloudiness = clouds.get("all")
        sunrise_ts = sys_info.get("sunrise")
        sunset_ts = sys_info.get("sunset")

        # Преобразование давления из гПа в мм рт.ст.
        pressure_mmhg = int(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A"
        emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")

        sunrise_str, sunset_str = "N/A", "N/A"
        if sunrise_ts:
            sunrise_str = datetime.fromtimestamp(sunrise_ts, tz=TZ_KYIV).strftime('%H:%M')
        if sunset_ts:
            sunset_str = datetime.fromtimestamp(sunset_ts, tz=TZ_KYIV).strftime('%H:%M')

        dt_unix = data.get("dt")
        if dt_unix:
            current_time_str = datetime.fromtimestamp(dt_unix, tz=TZ_KYIV).strftime('%H:%M %d.%m.%Y')
            time_info = f"<i>Дані актуальні на {current_time_str} (Київ)</i>"
        else:
            time_info = ""

        message_lines = [
            f"<b>Погода в м. {city_display_name.capitalize()}</b> {emoji}",
            f"🌡️ Температура: <b>{temp}°C</b> (відчувається як {feels_like}°C)",
            f"🌬️ Вітер: {wind_speed} м/с",
            f"💧 Вологість: {humidity}%",
            f"🌫️ Тиск: {pressure_mmhg} мм рт.ст.",
            f"☁️ Хмарність: {cloudiness}%",
            f"📝 Опис: {description.capitalize()}",
            f"🌅 Схід сонця: {sunrise_str}",
            f"🌇 Захід сонця: {sunset_str}",
            time_info
        ]
        return "\n".join(filter(None, message_lines))

    except Exception as e:
        logger.exception(f"Error formatting weather message for {city_display_name}: {e}", exc_info=True)
        return f"😥 Помилка обробки даних погоди для <b>{city_display_name}</b>."


def format_forecast_message(data: Dict[str, Any], city_display_name: str) -> str:
    """ Форматирует сообщение с прогнозом погоды на 5 дней. """
    try:
        cod = data.get("cod")
        if str(cod) != "200":
            message = data.get("message", "Невідома помилка API.")
            logger.warning(f"Forecast API error for {city_display_name}. Code: {cod}, Message: {message}")
            return f"😔 Не вдалося отримати прогноз для <b>{city_display_name}</b>.\n<i>Причина: {message} (Код: {cod})</i>"

        message_lines = [f"<b>Прогноз погоди для м. {city_display_name.capitalize()} на 5 днів:</b>\n"]
        forecast_list = data.get("list", [])
        
        # Группируем прогнозы по дням (полдень или ближайшее время)
        daily_forecasts = {}
        for item in forecast_list:
            dt_txt = item.get("dt_txt")
            if not dt_txt:
                continue
            
            # Преобразуем в datetime объект, учитывая UTC от API
            dt_obj_utc = datetime.strptime(dt_txt, '%Y-%m-%d %H:%M:%S')
            dt_obj_kyiv = dt_obj_utc.replace(tzinfo=pytz.utc).astimezone(TZ_KYIV)
            
            date_str = dt_obj_kyiv.strftime('%d.%m.%Y (%A)')
            
            # Сохраняем прогноз на 12:00 или первый доступный после полуночи
            if date_str not in daily_forecasts or \
               (daily_forecasts[date_str].get("hour_diff", 24) > abs(dt_obj_kyiv.hour - 12)):
                
                temp = item.get("main", {}).get("temp")
                weather_desc = item.get("weather", [{}])[0].get("description", "N/A")
                icon_code = item.get("weather", [{}])[0].get("icon")
                emoji = ICON_CODE_TO_EMOJI.get(icon_code, "")
                
                daily_forecasts[date_str] = {
                    "temp": temp,
                    "description": weather_desc,
                    "emoji": emoji,
                    "hour_diff": abs(dt_obj_kyiv.hour - 12) # для выбора ближайшего к полудню
                }

        if not daily_forecasts:
            return "😥 На жаль, детальний прогноз на найближчі дні відсутній."

        # Сортируем дни для корректного отображения
        sorted_dates = sorted(daily_forecasts.keys(), key=lambda d: datetime.strptime(d.split(" ")[0], '%d.%m.%Y'))

        for date_str in sorted_dates:
            forecast = daily_forecasts[date_str]
            message_lines.append(
                f"<b>{date_str}:</b> {forecast['temp']:.1f}°C, {forecast['description'].capitalize()} {forecast['emoji']}"
            )
        
        message_lines.append("\n<tg-spoiler>Прогноз може уточнюватися.</tg-spoiler>")
        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting forecast message for {city_display_name}: {e}", exc_info=True)
        return f"😥 Помилка обробки даних прогнозу для <b>{city_display_name}</b>."