# src/modules/weather/service.py

import logging
import aiohttp
import asyncio # <<< Добавляем asyncio для sleep
from typing import Optional, Dict, Any

from src import config

logger = logging.getLogger(__name__)

OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"

# Параметры для повторных попыток
MAX_RETRIES = 3
INITIAL_DELAY = 1 # Секунда

async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """ Получает данные о погоде с OpenWeatherMap с повторными попытками. """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"}

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }

    last_exception = None # Сохраняем последнюю ошибку для логирования

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch weather for {city_name}")
            async with aiohttp.ClientSession() as session:
                # Устанавливаем таймаут для запроса (например, 10 секунд)
                async with session.get(OWM_API_URL, params=params, timeout=10) as response:
                    # Успешный ответ 200 OK
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logger.debug(f"OpenWeatherMap response for {city_name}: {data}")
                            return data # <<< Успех, выходим
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from OWM. Response: {await response.text()}")
                            # Это не временная ошибка, нет смысла повторять
                            return {"cod": 500, "message": "Invalid JSON response"}

                    # Ошибки клиента (4xx), которые не нужно повторять
                    elif response.status == 404:
                        logger.warning(f"Attempt {attempt + 1}: City '{city_name}' not found by OWM (404).")
                        return {"cod": 404, "message": "City not found"}
                    elif response.status == 401:
                        logger.error(f"Attempt {attempt + 1}: Invalid OWM API key (401).")
                        return {"cod": 401, "message": "Invalid API key"}
                    elif 400 <= response.status < 500:
                        # Другие ошибки клиента (4xx) - тоже не повторяем
                        error_text = await response.text()
                        logger.error(f"Attempt {attempt + 1}: OWM Client Error {response.status}. Response: {error_text[:200]}")
                        return {"cod": response.status, "message": f"Client error {response.status}"}

                    # Ошибки сервера (5xx) или 429 (слишком много запросов) - ПОПРОБУЕМ ПОВТОРИТЬ
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(
                            response.request_info,
                            response.history,
                            status=response.status,
                            message=f"Server error {response.status}",
                            headers=response.headers,
                        )
                        logger.warning(f"Attempt {attempt + 1}: OWM Server Error {response.status}. Retrying...")
                        # Переходим к блоку except для задержки

                    else: # Неожиданный статус
                         logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from OWM.")
                         last_exception = Exception(f"Unexpected status {response.status}")
                         # Продолжаем, чтобы сработал sleep и retry

        # Ловим сетевые ошибки и таймауты - ПОПРОБУЕМ ПОВТОРИТЬ
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to OWM: {e}. Retrying...")
        # Ловим другие неожиданные ошибки при запросе - НЕ ПОВТОРЯЕМ
        except Exception as e:
             logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred: {e}", exc_info=True)
             # Считаем это фатальной ошибкой для этого запроса
             return {"cod": 500, "message": "Internal processing error"}

        # Если мы здесь, значит была ошибка, которую нужно повторить
        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay} seconds before next retry...")
            await asyncio.sleep(delay)
        else:
             logger.error(f"All {MAX_RETRIES} attempts failed for city {city_name}. Last error: {last_exception!r}")
             # Возвращаем информацию о последней ошибке, если она была поймана
             if isinstance(last_exception, aiohttp.ClientResponseError):
                 return {"cod": last_exception.status, "message": f"Server error {last_exception.status} after retries"}
             elif isinstance(last_exception, aiohttp.ClientConnectorError):
                 return {"cod": 503, "message": "Network error after retries"}
             elif isinstance(last_exception, asyncio.TimeoutError):
                  return {"cod": 504, "message": "Timeout error after retries"}
             else:
                 return {"cod": 500, "message": "Failed after multiple retries"}

    return {"cod": 500, "message": "Failed after all retries"} # На всякий случай, если цикл завершился иначе


# Функция format_weather_message остается БЕЗ ИЗМЕНЕНИЙ (из ответа #81)
# ... (ваш код format_weather_message) ...
def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str:
    # ... (код функции из ответа #81) ...
    try:
        main_data = weather_data.get("main", {})
        weather_info = weather_data.get("weather", [{}])[0]
        wind_data = weather_data.get("wind", {})
        cloud_data = weather_data.get("clouds", {})

        temp = main_data.get("temp")
        feels_like = main_data.get("feels_like")
        humidity = main_data.get("humidity")
        pressure_hpa = main_data.get("pressure")
        pressure_mmhg = round(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A"

        description = weather_info.get("description", "невідомо").capitalize()
        weather_icons_map = {
             "clear sky": "☀️", "few clouds": "🌤️", "scattered clouds": "☁️",
             "broken clouds": "☁️", "overcast clouds": "🌥️", "shower rain": "🌦️",
             "rain": "🌧️", "light rain": "🌧️", "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️"
        }
        icon_emoji = "❓"
        for key, emoji in weather_icons_map.items():
             if key in description.lower():
                  icon_emoji = emoji
                  break

        wind_speed = wind_data.get("speed")
        wind_deg = wind_data.get("deg")

        def deg_to_compass(num):
            if num is None: return ""
            try:
                val = int((float(num) / 22.5) + 0.5)
                arr = ["Пн","Пн-Пн-Сх","Пн-Сх","Сх-Пн-Сх","Сх","Сх-Пд-Сх","Пд-Сх","Пд-Пд-Сх","Пд","Пд-Пд-Зх","Пд-Зх","Зх-Пд-Зх","Зх","Зх-Пн-Зх","Пн-Зх","Пн-Пн-Зх"]
                return arr[(val % 16)]
            except (ValueError, TypeError):
                return ""
        wind_direction = deg_to_compass(wind_deg)

        clouds_percent = cloud_data.get("all", "N/A")
        display_name_formatted = city_display_name.capitalize()

        message_lines = [
            f"<b>Погода в м. {display_name_formatted}:</b>\n",
            f"{icon_emoji} {description}",
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