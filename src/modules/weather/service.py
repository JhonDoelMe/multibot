# src/modules/weather/service.py

import logging
import aiohttp # Оставляем для типов исключений
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import pytz
from aiogram import Bot # Импортируем Bot

from src import config

logger = logging.getLogger(__name__)

# Константы API
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

# Часовой пояс и параметры Retry
TZ_KYIV = pytz.timezone('Europe/Kyiv')
MAX_RETRIES = 3
INITIAL_DELAY = 1 # Секунда

# Словарь для эмодзи по коду иконки OpenWeatherMap
ICON_CODE_TO_EMOJI = {
    "01d": "☀️", "01n": "🌙", # clear sky
    "02d": "🌤️", "02n": "☁️", # few clouds
    "03d": "☁️", "03n": "☁️", # scattered clouds
    "04d": "🌥️", "04n": "☁️", # broken clouds
    "09d": "🌦️", "09n": "🌦️", # shower rain
    "10d": "🌧️", "10n": "🌧️", # rain
    "11d": "⛈️", "11n": "⛈️", # thunderstorm
    "13d": "❄️", "13n": "❄️", # snow
    "50d": "🌫️", "50n": "🌫️", # mist
}

# --- Функция для текущей погоды ---
async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде, используя сессию бота. """
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

    # Используем сессию из объекта bot
    async with bot.session as session: # <<< Открываем сессию здесь
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {city_name}")
                # Вызываем get у полученной сессии
                async with session.get(api_url, params=params, timeout=10) as response:
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
                    elif 400 <= response.status < 500:
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
                 if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
                 elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": 503, "message": "Network error after retries"}
                 elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": 504, "message": "Timeout error after retries"}
                 else: return {"cod": 500, "message": "Failed after multiple retries"}
    return {"cod": 500, "message": "Failed after all weather retries"} # Fallback

# --- Функция для погоды по координатам ---
async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде по координатам, используя сессию бота. """
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

    async with bot.session as session: # <<< Открываем сессию здесь
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for coords ({latitude:.4f}, {longitude:.4f})")
                async with session.get(api_url, params=params, timeout=10) as response: # <<< Используем session.get
                    # ... (Та же логика обработки ответа, что и в get_weather_data) ...
                    if response.status == 200:
                        try: data = await response.json(); return data
                        except aiohttp.ContentTypeError: logger.error("..."); return {"cod": 500, "message": "..."}
                    elif response.status == 401: return {"cod": 401, "message": "..."}
                    elif 400 <= response.status < 500 and response.status != 429: return {"cod": response.status, "message": "..."}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                    else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                 last_exception = e; logger.warning(f"... Network error coords: {e}. Retrying...")
            except Exception as e:
                 logger.exception(f"... Unexpected error coords: {e}", exc_info=True); return {"cod": 500, "message": "..."}

            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else:
                 logger.error(f"All attempts failed coords ({latitude:.4f}, {longitude:.4f}). Last error: {last_exception!r}")
                 if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": ...}
                 # ... (остальные возвраты ошибок) ...
                 else: return {"cod": 500, "message": "Failed after retries"}
    return {"cod": 500, "message": "Failed after all weather retries"}

# --- Функция для прогноза на 5 дней ---
async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней, используя сессию бота. """
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

    async with bot.session as session: # <<< Открываем сессию здесь
        for attempt in range(MAX_RETRIES):
            try:
                logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for {city_name}")
                async with session.get(api_url, params=params, timeout=15) as response: # <<< Используем session.get
                    # ... (Та же логика обработки ответа, что и в get_weather_data, но cod - строка) ...
                    if response.status == 200:
                        try: data = await response.json(); return data
                        except aiohttp.ContentTypeError: logger.error("..."); return {"cod": "500", "message": "..."}
                    elif response.status == 404: return {"cod": "404", "message": "..."}
                    elif response.status == 401: return {"cod": "401", "message": "..."}
                    elif 400 <= response.status < 500 and response.status != 429: return {"cod": str(response.status), "message": "..."}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(...); logger.warning("... Retrying...")
                    else: last_exception = Exception(...); logger.error("... Unexpected status ...")
            except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
                last_exception = e; logger.warning(f"... Network error forecast: {e}. Retrying...")
            except Exception as e:
                logger.exception(f"... Unexpected error fetching forecast: {e}", exc_info=True); return {"cod": "500", "message": "..."}

            if attempt < MAX_RETRIES - 1:
                delay = INITIAL_DELAY * (2 ** attempt); await asyncio.sleep(delay)
            else:
                 logger.error(f"All attempts failed forecast {city_name}. Last error: {last_exception!r}")
                 if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": str(last_exception.status), "message": ...}
                 # ... (остальные возвраты ошибок) ...
                 else: return {"cod": "500", "message": "Failed after retries"}
    return {"cod": "500", "message": "Failed after all forecast retries"}


# --- Функции форматирования ---
def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код форматирования без изменений, как в ответе #116) ...
    try:
        main_data=weather_data.get("main", {}); weather_info=weather_data.get("weather", [{}])[0]; wind_data=weather_data.get("wind", {}); cloud_data=weather_data.get("clouds", {})
        temp=main_data.get("temp"); feels_like=main_data.get("feels_like"); humidity=main_data.get("humidity"); pressure_hpa=main_data.get("pressure")
        pressure_mmhg=round(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A"
        wind_speed=wind_data.get("speed"); wind_deg=wind_data.get("deg"); clouds_percent=cloud_data.get("all", "N/A")
        description_uk=weather_info.get("description", "невідомо").capitalize(); icon_code=weather_info.get("icon")
        icon_emoji=ICON_CODE_TO_EMOJI.get(icon_code, "❓")
        def deg_to_compass(num):
            if num is None: return ""; try: val=int((float(num)/22.5)+.5); arr=["Пн",..."Нд"]; return arr[(val%16)]
            except (ValueError,TypeError): return ""
        wind_direction=deg_to_compass(wind_deg); display_name_formatted=city_display_name.capitalize()
        message_lines=[f"<b>Погода в м. {display_name_formatted}:</b>\n", f"{icon_emoji} {description_uk}", f"🌡️ Температура: {temp:+.1f}°C..." if temp is not None else "...", f"💧 Вологість: {humidity}%" if humidity is not None else "...", f"💨 Вітер: {wind_speed:.1f} м/с {wind_direction}" if wind_speed is not None else "...", f"🧭 Тиск: {pressure_mmhg} мм рт.ст." if pressure_mmhg != "N/A" else "...", f"☁️ Хмарність: {clouds_percent}%" if clouds_percent != "N/A" else "..."]
        return "\n".join(message_lines)
    except Exception as e: logger.exception(f"Error formatting weather: {e}"); return f"Помилка обробки погоди для м. {city_display_name.capitalize()}."


def format_forecast_message(forecast_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код форматирования без изменений, как в ответе #116) ...
    try:
        if forecast_data.get("cod") != "200": api_message = forecast_data.get("message", "..."); return f"Не вдалося отримати прогноз...: {api_message}"
        forecast_list = forecast_data.get("list");
        if not forecast_list: return f"Не знайдено даних прогнозу..."
        daily_forecasts = {}; processed_dates = set(); today_kyiv = datetime.now(TZ_KYIV).date()
        for item in forecast_list: # ... (группировка по дням) ...
        message_lines=[f"<b>Прогноз для м. {city_display_name.capitalize()}:</b>\n"]
        if not daily_forecasts: return f"Не знайдено даних прогнозу..."
        sorted_dates = sorted(daily_forecasts.keys())
        for date_str in sorted_dates: # ... (форматирование каждого дня) ...
             date_obj=datetime.strptime(date_str,'%Y-%m-%d'); day_month=date_obj.strftime('%d.%m'); day_index=date_obj.weekday(); uk_days=["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]; day_name=uk_days[day_index]
             min_temp=min(data["temps"]) if data["temps"] else "N/A"; max_temp=max(data["temps"]) if data["temps"] else "N/A"
             icon_emoji="❓"; # ... (логика выбора эмодзи) ...
             temp_str=f"{max_temp:+.0f}°C / {min_temp:+.0f}°C" if min_temp!="N/A" and max_temp!="N/A" else "N/A"
             message_lines.append(f"<b>{day_name} ({day_month}):</b> {temp_str} {icon_emoji}")
        return "\n".join(message_lines)
    except Exception as e: logger.exception(f"Error formatting forecast msg: {e}"); return f"Помилка обробки прогнозу для м. {city_display_name.capitalize()}."