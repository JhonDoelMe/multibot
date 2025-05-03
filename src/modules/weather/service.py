# src/modules/weather/service.py

import logging
import aiohttp # Оставляем для типов исключений
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import pytz
from aiogram import Bot # <<< Импортируем Bot

from src import config

logger = logging.getLogger(__name__)

# Константы и словари остаются
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
TZ_KYIV = pytz.timezone('Europe/Kyiv')
MAX_RETRIES = 3
INITIAL_DELAY = 1
ICON_CODE_TO_EMOJI = {
    "01d": "☀️", "01n": "🌙", "02d": "🌤️", "02n": "☁️", "03d": "☁️",
    "03n": "☁️", "04d": "🌥️", "04n": "☁️", "09d": "🌦️", "09n": "🌦️",
    "10d": "🌧️", "10n": "🌧️", "11d": "⛈️", "11n": "⛈️", "13d": "❄️",
    "13n": "❄️", "50d": "🌫️", "50n": "🌫️",
}

# --- ИЗМЕНЯЕМ ФУНКЦИИ API ---
async def get_weather_data(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]: # <<< Добавили bot: Bot
    """ Получает данные о погоде, используя сессию бота. """
    if not config.WEATHER_API_KEY: # ... (проверка ключа) ...
         logger.error("OWM API key not configured."); return {"cod": 500, "message": "API key not configured"}
    params = {"q": city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_API_URL
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {city_name}")
            # <<< ИСПОЛЬЗУЕМ bot.session ВМЕСТО создания новой сессии >>>
            async with bot.session.get(api_url, params=params, timeout=10) as response:
                # ... (вся логика обработки response и ошибок остается прежней) ...
                if response.status == 200:
                    try: data = await response.json(); logger.debug(f"OWM Weather response: {data}"); return data
                    except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON ..."); return {"cod": 500, "message": "Invalid JSON response"}
                elif response.status == 404: logger.warning(f"... City '{city_name}' not found (404)."); return {"cod": 404, "message": "City not found"}
                elif response.status == 401: logger.error(f"... Invalid OWM API key (401)."); return {"cod": 401, "message": "Invalid API key"}
                elif 400 <= response.status < 500: error_text = await response.text(); logger.error(f"... OWM Client Error {response.status}. Resp: {error_text[:200]}"); return {"cod": response.status, "message": f"Client error {response.status}"}
                elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... OWM Server/RateLimit Error {response.status}. Retrying...")
                else: logger.error(f"... Unexpected status {response.status} from OWM Weather."); last_exception = Exception(f"Unexpected status {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error fetching weather: {e}", exc_info=True); return {"cod": 500, "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next weather retry..."); await asyncio.sleep(delay)
        else: # ... (обработка ошибок после всех попыток) ...
            logger.error(f"All {MAX_RETRIES} attempts failed for weather {city_name}. Last error: {last_exception!r}")
            if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
            elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": 503, "message": "Network error after retries"}
            elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": 504, "message": "Timeout error after retries"}
            else: return {"cod": 500, "message": "Failed after multiple retries"}
    return {"cod": 500, "message": "Failed after all weather retries"}

async def get_weather_data_by_coords(bot: Bot, latitude: float, longitude: float) -> Optional[Dict[str, Any]]: # <<< Добавили bot: Bot
    """ Получает данные о погоде по координатам, используя сессию бота. """
    if not config.WEATHER_API_KEY: # ... (проверка ключа) ...
        logger.error("OWM API key not configured."); return {"cod": 500, "message": "API key not configured"}
    params = {"lat": latitude, "lon": longitude, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_API_URL
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for coords ({latitude}, {longitude})")
            # <<< ИСПОЛЬЗУЕМ bot.session >>>
            async with bot.session.get(api_url, params=params, timeout=10) as response:
                # ... (логика обработки response и ошибок остается прежней) ...
                if response.status == 200:
                    try: data = await response.json(); logger.debug(f"OWM Weather response: {data}"); return data
                    except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON ..."); return {"cod": 500, "message": "Invalid JSON response"}
                elif response.status == 401: logger.error(f"... Invalid OWM API key (401)."); return {"cod": 401, "message": "Invalid API key"}
                elif 400 <= response.status < 500 and response.status != 429: error_text = await response.text(); logger.error(f"... OWM Client Error {response.status}. Resp: {error_text[:200]}"); return {"cod": response.status, "message": f"Client error {response.status}"}
                elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... OWM Server/RateLimit Error {response.status}. Retrying...")
                else: logger.error(f"... Unexpected status {response.status} from OWM Weather."); last_exception = Exception(f"Unexpected status {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error fetching weather by coords: {e}", exc_info=True); return {"cod": 500, "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next weather retry..."); await asyncio.sleep(delay)
        else: # ... (обработка ошибок после всех попыток) ...
             logger.error(f"All {MAX_RETRIES} attempts failed for weather coords ({latitude}, {longitude}). Last error: {last_exception!r}")
             if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
             elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": 503, "message": "Network error after retries"}
             elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": 504, "message": "Timeout error after retries"}
             else: return {"cod": 500, "message": "Failed after multiple retries"}
    return {"cod": 500, "message": "Failed after all weather retries"}


async def get_5day_forecast(bot: Bot, city_name: str) -> Optional[Dict[str, Any]]: # <<< Добавили bot: Bot
    """ Получает прогноз на 5 дней, используя сессию бота. """
    if not config.WEATHER_API_KEY: # ... (проверка ключа) ...
         logger.error("OWM API key not configured."); return {"cod": "500", "message": "API key not configured"}
    params = {"q": city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None; api_url = OWM_FORECAST_URL
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for {city_name}")
             # <<< ИСПОЛЬЗУЕМ bot.session >>>
            async with bot.session.get(api_url, params=params, timeout=15) as response:
                # ... (логика обработки response и ошибок остается прежней) ...
                if response.status == 200:
                    try: data = await response.json(); logger.debug(f"OWM Forecast response (status {response.status}): {str(data)[:500]}..."); return data
                    except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON forecast ..."); return {"cod": "500", "message": "Invalid JSON response"}
                elif response.status == 404: logger.warning(f"... City '{city_name}' not found for forecast (404)."); return {"cod": "404", "message": "City not found"}
                elif response.status == 401: logger.error(f"... Invalid OWM API key (401)."); return {"cod": "401", "message": "Invalid API key"}
                elif 400 <= response.status < 500 and response.status != 429: error_text = await response.text(); logger.error(f"... OWM Forecast Client Error {response.status}. Resp: {error_text[:200]}"); return {"cod": str(response.status), "message": f"Client error {response.status}"}
                elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... OWM Forecast Server/RateLimit Error {response.status}. Retrying...")
                else: logger.error(f"... Unexpected status {response.status} from OWM Forecast."); last_exception = Exception(f"Unexpected status {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error forecast: {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error fetching forecast: {e}", exc_info=True); return {"cod": "500", "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next forecast retry..."); await asyncio.sleep(delay)
        else: # ... (обработка ошибок после всех попыток) ...
             logger.error(f"All {MAX_RETRIES} attempts failed for forecast {city_name}. Last error: {last_exception!r}")
             if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": str(last_exception.status), "message": f"Server error {last_exception.status} after retries"}
             elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": "503", "message": "Network error after retries"}
             elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": "504", "message": "Timeout error after retries"}
             else: return {"cod": "500", "message": "Failed after multiple retries"}
    return {"cod": "500", "message": "Failed after all forecast retries"}


# --- Функции форматирования остаются без изменений ---
def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код как в ответе #116) ...
    try:
        main_data=weather_data.get("main", {}); weather_info=weather_data.get("weather", [{}])[0]; wind_data=weather_data.get("wind", {}); cloud_data=weather_data.get("clouds", {})
        temp=main_data.get("temp"); feels_like=main_data.get("feels_like"); humidity=main_data.get("humidity"); pressure_hpa=main_data.get("pressure")
        pressure_mmhg=round(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A"
        wind_speed=wind_data.get("speed"); wind_deg=wind_data.get("deg"); clouds_percent=cloud_data.get("all", "N/A")
        description_uk=weather_info.get("description", "невідомо").capitalize(); icon_code=weather_info.get("icon")
        icon_emoji=ICON_CODE_TO_EMOJI.get(icon_code, "❓")
        def deg_to_compass(num):
            if num is None: return ""; try: val=int((float(num)/22.5)+.5); arr=["Пн","Пн-Пн-Сх","Пн-Сх","Сх-Пн-Сх","Сх","Сх-Пд-Сх","Пд-Сх","Пд-Пд-Сх","Пд","Пд-Пд-Зх","Пд-Зх","Зх-Пд-Зх","Зх","Зх-Пн-Зх","Пн-Зх","Пн-Пн-Зх"]; return arr[(val%16)]
            except (ValueError,TypeError): return ""
        wind_direction=deg_to_compass(wind_deg); display_name_formatted=city_display_name.capitalize()
        message_lines=[f"<b>Погода в м. {display_name_formatted}:</b>\n", f"{icon_emoji} {description_uk}", f"🌡️ Температура: {temp:+.1f}°C (відчувається як {feels_like:+.1f}°C)" if temp is not None and feels_like is not None else "...", f"💧 Вологість: {humidity}%" if humidity is not None else "...", f"💨 Вітер: {wind_speed:.1f} м/с {wind_direction}" if wind_speed is not None else "...", f"🧭 Тиск: {pressure_mmhg} мм рт.ст." if pressure_mmhg != "N/A" else "...", f"☁️ Хмарність: {clouds_percent}%" if clouds_percent != "N/A" else "..."]
        return "\n".join(message_lines)
    except Exception as e: logger.exception(f"Error formatting weather: {e}"); return f"Помилка обробки даних про погоду для м. {city_display_name.capitalize()}."

def format_forecast_message(forecast_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код как в ответе #116) ...
    try:
        if forecast_data.get("cod") != "200": api_message = forecast_data.get("message", "..."); logger.warning(f"API error forecast: {forecast_data.get('cod')} - {api_message}"); return f"Не вдалося отримати прогноз...: {api_message}"
        forecast_list = forecast_data.get("list");
        if not forecast_list: return f"Не знайдено даних прогнозу для м. {city_display_name.capitalize()}."
        daily_forecasts = {}; processed_dates = set(); today_kyiv = datetime.now(TZ_KYIV).date()
        for item in forecast_list:
            dt_utc=datetime.utcfromtimestamp(item.get('dt',0)); dt_kyiv=dt_utc.replace(tzinfo=pytz.utc).astimezone(TZ_KYIV); item_date=dt_kyiv.date()
            if item_date < today_kyiv: continue
            if len(processed_dates) >= 5 and item_date not in processed_dates: break
            date_str=item_date.strftime('%Y-%m-%d')
            if date_str not in daily_forecasts: daily_forecasts[date_str]={"temps":[], "icons":set()}; processed_dates.add(item_date)
            temp=item.get("main",{}).get("temp"); icon_code=item.get("weather",[{}])[0].get("icon")
            if temp is not None: daily_forecasts[date_str]["temps"].append(temp)
            if icon_code: daily_forecasts[date_str]["icons"].add(icon_code[:2])
        message_lines=[f"<b>Прогноз для м. {city_display_name.capitalize()}:</b>\n"]
        if not daily_forecasts: return f"Не знайдено даних прогнозу..."
        sorted_dates = sorted(daily_forecasts.keys())
        for date_str in sorted_dates:
             data = daily_forecasts[date_str]
             try:
                 date_obj=datetime.strptime(date_str,'%Y-%m-%d'); day_month=date_obj.strftime('%d.%m')
                 day_index=date_obj.weekday(); uk_days=["Пн","Вт","Ср","Чт","Пт","Сб","Нд"]; day_name=uk_days[day_index]
                 min_temp=min(data["temps"]) if data["temps"] else "N/A"; max_temp=max(data["temps"]) if data["temps"] else "N/A"
                 icon_emoji="❓";
                 if data["icons"]:
                      icons_list=sorted(list(data["icons"])); day_icon_code=next((f"{code}d" for code in icons_list if f"{code}d" in ICON_CODE_TO_EMOJI),None)
                      if day_icon_code: icon_emoji=ICON_CODE_TO_EMOJI.get(day_icon_code,"❓")
                      else: any_icon_code=icons_list[0]; icon_d=ICON_CODE_TO_EMOJI.get(f"{any_icon_code}d","❓"); icon_n=ICON_CODE_TO_EMOJI.get(f"{any_icon_code}n",icon_d); icon_emoji=icon_d if icon_d!="❓" else icon_n
                 temp_str=f"{max_temp:+.0f}°C / {min_temp:+.0f}°C" if min_temp!="N/A" and max_temp!="N/A" else "N/A"
                 message_lines.append(f"<b>{day_name} ({day_month}):</b> {temp_str} {icon_emoji}")
             except Exception as e: logger.error(f"Error formatting forecast date {date_str}: {e}"); continue
        return "\n".join(message_lines)
    except Exception as e: logger.exception(f"Error formatting forecast msg: {e}"); return f"Помилка обробки прогнозу для м. {city_display_name.capitalize()}."