# src/modules/weather/service.py

import logging
import aiohttp
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
import pytz

from src import config

logger = logging.getLogger(__name__)

OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
TZ_KYIV = pytz.timezone('Europe/Kyiv')

# Параметры для повторных попыток
MAX_RETRIES = 3
INITIAL_DELAY = 1 # Секунда

# --- НОВЫЙ СЛОВАРЬ: Код иконки OWM -> Эмодзи ---
# См. https://openweathermap.org/weather-conditions#Weather-Condition-Codes-2
ICON_CODE_TO_EMOJI = {
    # День
    "01d": "☀️", # clear sky
    "02d": "🌤️", # few clouds
    "03d": "☁️", # scattered clouds
    "04d": "☁️", # broken clouds (используем ту же, что и scattered)
    "09d": "🌦️", # shower rain
    "10d": "🌧️", # rain
    "11d": "⛈️", # thunderstorm
    "13d": "❄️", # snow
    "50d": "🌫️", # mist
    # Ночь (можно использовать те же или другие)
    "01n": "🌙", # clear sky
    "02n": "☁️", # few clouds # Используем облако без солнца
    "03n": "☁️", # scattered clouds
    "04n": "☁️", # broken clouds
    "09n": "🌦️", # shower rain
    "10n": "🌧️", # rain
    "11n": "⛈️", # thunderstorm
    "13n": "❄️", # snow
    "50n": "🌫️", # mist
}

async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде с OpenWeatherMap с повторными попытками. """
    # ... (Код функции get_weather_data остается БЕЗ ИЗМЕНЕНИЙ с ответа #88) ...
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}
    params = {"q": city_name, "appid": config.WEATHER_API_KEY, "units": "metric", "lang": "uk"}
    last_exception = None
    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {city_name}")
            async with aiohttp.ClientSession() as session:
                async with session.get(OWM_API_URL, params=params, timeout=10) as response:
                    if response.status == 200:
                        try: data = await response.json(); logger.debug(f"OWM response: {data}"); return data
                        except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON ..."); return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 404: logger.warning(f"... City '{city_name}' not found (404)."); return {"cod": 404, "message": "City not found"}
                    elif response.status == 401: logger.error(f"... Invalid OWM API key (401)."); return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500: error_text = await response.text(); logger.error(f"... OWM Client Error {response.status}. Resp: {error_text[:200]}"); return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... OWM Server/RateLimit Error {response.status}. Retrying...")
                    else: logger.error(f"... Unexpected status {response.status} from OWM."); last_exception = Exception(f"Unexpected status {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error: {e}", exc_info=True); return {"cod": 500, "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next retry..."); await asyncio.sleep(delay)
        else:
             logger.error(f"All {MAX_RETRIES} attempts failed for city {city_name}. Last error: {last_exception!r}")
             if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
             elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": 503, "message": "Network error after retries"}
             elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": 504, "message": "Timeout error after retries"}
             else: return {"cod": 500, "message": "Failed after multiple retries"}
    return {"cod": 500, "message": "Failed after all retries"}


# --- ИЗМЕНЯЕМ ФУНКЦИЮ ФОРМАТИРОВАНИЯ ---
def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str:
    """
    Форматирует данные о погоде в читаемое сообщение.
    Использует код иконки от API для эмодзи.
    """
    try:
        main_data = weather_data.get("main", {})
        # Берем первый элемент списка погоды (обычно он один)
        weather_info = weather_data.get("weather", [{}])[0]
        wind_data = weather_data.get("wind", {})
        cloud_data = weather_data.get("clouds", {})

        # Получаем данные или N/A
        temp = main_data.get("temp")
        feels_like = main_data.get("feels_like")
        humidity = main_data.get("humidity")
        pressure_hpa = main_data.get("pressure")
        pressure_mmhg = round(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A"
        wind_speed = wind_data.get("speed")
        wind_deg = wind_data.get("deg")
        clouds_percent = cloud_data.get("all", "N/A")

        # --- Логика Эмодзи по коду иконки ---
        description_uk = weather_info.get("description", "невідомо").capitalize() # Описание на украинском
        icon_code = weather_info.get("icon") # Код иконки (e.g., "01d", "10n")
        icon_emoji = ICON_CODE_TO_EMOJI.get(icon_code, "❓") # Получаем эмодзи из словаря
        # --- Конец логики Эмодзи ---

        # Направление ветра
        def deg_to_compass(num):
            if num is None: return ""
            try:
                val = int((float(num) / 22.5) + 0.5)
                arr = ["Пн","Пн-Пн-Сх","Пн-Сх","Сх-Пн-Сх","Сх","Сх-Пд-Сх","Пд-Сх","Пд-Пд-Сх","Пд","Пд-Пд-Зх","Пд-Зх","Зх-Пд-Зх","Зх","Зх-Пн-Зх","Пн-Зх","Пн-Пн-Зх"]
                return arr[(val % 16)]
            except (ValueError, TypeError): return ""
        wind_direction = deg_to_compass(wind_deg)

        # Используем имя, которое ввел пользователь
        display_name_formatted = city_display_name.capitalize()

        # Формируем сообщение
        message_lines = [
            f"<b>Погода в м. {display_name_formatted}:</b>\n",
            f"{icon_emoji} {description_uk}", # Используем description_uk
            f"🌡️ Температура: {temp:.1f}°C (відчувається як {feels_like:.1f}°C)" if temp is not None and feels_like is not None else "🌡️ Температура: N/A",
            f"💧 Вологість: {humidity}%" if humidity is not None else "💧 Вологість: N/A",
            f"💨 Вітер: {wind_speed:.1f} м/с {wind_direction}" if wind_speed is not None else "💨 Вітер: N/A",
            f"🧭 Тиск: {pressure_mmhg} мм рт.ст." if pressure_mmhg != "N/A" else "🧭 Тиск: N/A",
            f"☁️ Хмарність: {clouds_percent}%" if clouds_percent != "N/A" else "☁️ Хмарність: N/A"
        ]
        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting weather data for {city_display_name}: {e}")
        return f"Помилка обробки даних про погоду для м. {city_display_name.capitalize()}."
    # --- ДОБАВЛЕНИЯ ДЛЯ ПРОГНОЗА ---

OWM_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

async def get_5day_forecast(city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает прогноз на 5 дней (3-часовой интервал) с OpenWeatherMap. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
        # "cnt": 40 # Можно ограничить количество временных точек, если нужно
    }
    last_exception = None
    api_url = OWM_FORECAST_URL # Используем URL прогноза

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch 5-day forecast for {city_name}")
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=15) as response: # Увеличим таймаут для прогноза
                    if response.status == 200:
                        try: data = await response.json(); logger.debug(f"OWM Forecast response: {data}"); return data # Возвращаем весь ответ
                        except aiohttp.ContentTypeError: logger.error(f"... Failed to decode JSON ..."); return {"cod": 500, "message": "Invalid JSON response"}
                    elif response.status == 404: logger.warning(f"... City '{city_name}' not found for forecast (404)."); return {"cod": 404, "message": "City not found"}
                    elif response.status == 401: logger.error(f"... Invalid OWM API key (401)."); return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500: error_text = await response.text(); logger.error(f"... OWM Client Error {response.status}. Resp: {error_text[:200]}"); return {"cod": response.status, "message": f"Client error {response.status}"}
                    elif response.status >= 500 or response.status == 429: last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status}"); logger.warning(f"... OWM Server/RateLimit Error {response.status}. Retrying...")
                    else: logger.error(f"... Unexpected status {response.status} from OWM Forecast."); last_exception = Exception(f"Unexpected status {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e: last_exception = e; logger.warning(f"... Network error: {e}. Retrying...")
        except Exception as e: logger.exception(f"... Unexpected error fetching forecast: {e}", exc_info=True); return {"cod": 500, "message": "Internal processing error"}
        if attempt < MAX_RETRIES - 1: delay = INITIAL_DELAY * (2 ** attempt); logger.info(f"Waiting {delay}s before next forecast retry..."); await asyncio.sleep(delay)
        else:
             logger.error(f"All {MAX_RETRIES} attempts failed for forecast {city_name}. Last error: {last_exception!r}")
             if isinstance(last_exception, aiohttp.ClientResponseError): return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
             # ... (остальные обработки ошибок как в get_weather_data) ...
             elif isinstance(last_exception, aiohttp.ClientConnectorError): return {"cod": 503, "message": "Network error after retries"}
             elif isinstance(last_exception, asyncio.TimeoutError): return {"cod": 504, "message": "Timeout error after retries"}
             else: return {"cod": 500, "message": "Failed after multiple retries"}
    return {"cod": 500, "message": "Failed after all forecast retries"}


def format_forecast_message(forecast_data: Dict[str, Any], city_display_name: str) -> str:
    """ Форматирует данные прогноза в сообщение по дням (упрощенно). """
    try:
        forecast_list = forecast_data.get("list")
        if not forecast_list:
            return f"Не вдалося отримати деталі прогнозу для м. {city_display_name}."

        daily_forecasts = {} # Словарь {дата: {"temps": [], "icons": [], "descs": []}}

        # Группируем данные по дням
        for item in forecast_list:
            # Преобразуем timestamp в дату в часовом поясе Киева
            dt_utc = datetime.utcfromtimestamp(item.get('dt', 0))
            dt_kyiv = dt_utc.replace(tzinfo=pytz.utc).astimezone(TZ_KYIV)
            date_str = dt_kyiv.strftime('%Y-%m-%d') # Дата как ключ

            if date_str not in daily_forecasts:
                 # Ограничим количество дней, например, 5
                 if len(daily_forecasts) >= 5:
                      break
                 daily_forecasts[date_str] = {"temps": [], "icons": set(), "descs": set()}

            # Собираем температуры и коды иконок/описания за день
            temp = item.get("main", {}).get("temp")
            if temp is not None:
                 daily_forecasts[date_str]["temps"].append(temp)

            icon_code = item.get("weather", [{}])[0].get("icon")
            if icon_code:
                 daily_forecasts[date_str]["icons"].add(icon_code[:2]) # Берем только код погоды (01, 02, 10...), без d/n

            desc = item.get("weather", [{}])[0].get("description")
            if desc:
                 daily_forecasts[date_str]["descs"].add(desc.capitalize())

        # Формируем сообщение
        message_lines = [f"<b>Прогноз для м. {city_display_name}:</b>\n"]
        if not daily_forecasts:
             return f"Не знайдено даних прогнозу для м. {city_display_name}."

        for date_str, data in daily_forecasts.items():
             try:
                 # Форматируем дату для вывода
                 date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                 day_month = date_obj.strftime('%d.%m')
                 day_name = date_obj.strftime('%a').capitalize() # Название дня недели (укр.)

                 # Считаем мин/макс температуру
                 min_temp = min(data["temps"]) if data["temps"] else "N/A"
                 max_temp = max(data["temps"]) if data["temps"] else "N/A"

                 # Пытаемся получить основной эмодзи (берем первый попавшийся код иконки)
                 icon_emoji = "❓"
                 if data["icons"]:
                      # Пытаемся взять дневную иконку (d), если есть, иначе любую
                      day_icon = next((f"{code}d" for code in data["icons"] if f"{code}d" in ICON_CODE_TO_EMOJI), None)
                      if day_icon:
                           icon_emoji = ICON_CODE_TO_EMOJI.get(day_icon, "❓")
                      else: # Берем первую попавшуюся ночную/дневную
                           any_icon_code = list(data["icons"])[0]
                           icon_day = ICON_CODE_TO_EMOJI.get(f"{any_icon_code}d", "❓")
                           icon_night = ICON_CODE_TO_EMOJI.get(f"{any_icon_code}n", icon_day) # Если ночной нет, берем дневную
                           icon_emoji = icon_day if icon_day != "❓" else icon_night


                 # Форматируем температуру
                 temp_str = f"{max_temp:.0f}°C / {min_temp:.0f}°C" if min_temp != "N/A" else "N/A"

                 message_lines.append(f"<b>{day_name} ({day_month}):</b> {temp_str} {icon_emoji}")

             except Exception as e:
                 logger.error(f"Error formatting forecast for date {date_str}: {e}")
                 continue # Пропускаем день, если ошибка форматирования

        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting forecast message for {city_display_name}: {e}")
        return f"Помилка обробки даних прогнозу для м. {city_display_name}."