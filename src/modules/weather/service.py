# src/modules/weather/service.py

import logging
import aiohttp
from typing import Optional, Dict, Any, List # Добавили List
from datetime import datetime
import pytz

from src import config

logger = logging.getLogger(__name__)

OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
TZ_KYIV = pytz.timezone('Europe/Kyiv') # Добавили определение TZ_KYIV

async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return {"cod": 500, "message": "API key not configured"} # Возвращаем ошибку

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",
        "lang": "uk",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(OWM_API_URL, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"OpenWeatherMap response for {city_name}: {data}")
                    return data
                elif response.status == 404:
                    logger.warning(f"City '{city_name}' not found by OpenWeatherMap.")
                    return {"cod": 404, "message": "City not found"}
                elif response.status == 401:
                    logger.error("Invalid OpenWeatherMap API key or key blocked.")
                    return {"cod": 401, "message": "Invalid API key"}
                else:
                    error_text = await response.text()
                    logger.error(f"OpenWeatherMap API error: Status {response.status}, Response: {error_text}")
                    # Пытаемся извлечь сообщение из JSON, если возможно
                    try:
                        error_data = await response.json()
                        api_message = error_data.get("message", "Unknown API error")
                    except Exception:
                        api_message = error_text[:100] # Обрезаем длинный текст
                    return {"cod": response.status, "message": api_message}

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network error connecting to OpenWeatherMap: {e}")
        return {"cod": 503, "message": "Network error"}
    except Exception as e:
        logger.exception(f"An unexpected error occurred while fetching weather for {city_name}: {e}")
        return {"cod": 500, "message": "Internal error"}


def format_weather_message(weather_data: Dict[str, Any], city_display_name: str) -> str: # <<< Принимаем city_display_name
    """
    Форматирует данные о погоде в читаемое сообщение.
    Использует city_display_name для отображения в заголовке.
    """
    try:
        main_data = weather_data.get("main", {})
        weather_info = weather_data.get("weather", [{}])[0]
        wind_data = weather_data.get("wind", {})
        cloud_data = weather_data.get("clouds", {})

        temp = main_data.get("temp")
        feels_like = main_data.get("feels_like")
        humidity = main_data.get("humidity")
        pressure_hpa = main_data.get("pressure")
        pressure_mmhg = round(pressure_hpa * 0.750062) if pressure_hpa is not None else "N/A" # Проверка на None

        # Описание погоды от API (уже должно быть на укр из-за lang=uk)
        description = weather_info.get("description", "невідомо").capitalize()
        # Эмодзи
        weather_icons_map = {
             "clear sky": "☀️", "few clouds": "🌤️", "scattered clouds": "☁️",
             "broken clouds": "☁️", "overcast clouds": "🌥️", "shower rain": "🌦️",
             "rain": "🌧️", "light rain": "🌧️", "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️"
        }
        icon_emoji = "❓"
        # Используем 'in' для поиска подстроки, так как описание может быть длиннее
        for key, emoji in weather_icons_map.items():
             if key in description.lower():
                  icon_emoji = emoji
                  break

        wind_speed = wind_data.get("speed")
        wind_deg = wind_data.get("deg")

        def deg_to_compass(num):
            if num is None: return ""
            # Проверка типа и преобразование к int, если возможно
            try:
                val = int((float(num) / 22.5) + 0.5)
                arr = ["Пн","Пн-Пн-Сх","Пн-Сх","Сх-Пн-Сх","Сх","Сх-Пд-Сх","Пд-Сх","Пд-Пд-Сх","Пд","Пд-Пд-Зх","Пд-Зх","Зх-Пд-Зх","Зх","Зх-Пн-Зх","Пн-Зх","Пн-Пн-Зх"]
                return arr[(val % 16)]
            except (ValueError, TypeError):
                return "" # Возвращаем пустую строку при ошибке
        wind_direction = deg_to_compass(wind_deg)

        clouds_percent = cloud_data.get("all", "N/A")

        # Используем имя, которое ввел пользователь, для заголовка
        display_name_formatted = city_display_name.capitalize() # <<< Используем ввод пользователя

        # Формируем сообщение
        message_lines = [
            f"<b>Погода в м. {display_name_formatted}:</b>\n", # <<< Отображаем ввод пользователя
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