# src/modules/weather/service.py

import logging
import aiohttp
from typing import Optional, Dict, Any

from src import config # Импортируем конфиг для доступа к API ключу

logger = logging.getLogger(__name__)

# Константы для OpenWeatherMap API
OWM_API_URL = "https://api.openweathermap.org/data/2.5/weather"
# Если захотите использовать One Call API (требует координат, не только имени города)
# OWM_ONECALL_API_URL = "https://api.openweathermap.org/data/3.0/onecall"

async def get_weather_data(city_name: str) -> Optional[Dict[str, Any]]:
    """
    Получает данные о погоде для указанного города с OpenWeatherMap.

    Args:
        city_name: Название города.

    Returns:
        Словарь с данными о погоде или None в случае ошибки.
    """
    if not config.WEATHER_API_KEY:
        logger.error("OpenWeatherMap API key (WEATHER_API_KEY) is not configured.")
        return None

    params = {
        "q": city_name,
        "appid": config.WEATHER_API_KEY,
        "units": "metric",  # Градусы Цельсия
        "lang": "uk",       # Язык ответа (uk - украинский, ru - русский, en - английский)
    }

    try:
        # Создаем сессию aiohttp для выполнения запроса
        async with aiohttp.ClientSession() as session:
            async with session.get(OWM_API_URL, params=params) as response:
                # Проверяем статус ответа
                if response.status == 200:
                    data = await response.json()
                    logger.debug(f"OpenWeatherMap response for {city_name}: {data}")
                    return data
                elif response.status == 404:
                    logger.warning(f"City '{city_name}' not found by OpenWeatherMap.")
                    return {"cod": 404, "message": "City not found"} # Возвращаем маркер ошибки
                elif response.status == 401:
                    logger.error("Invalid OpenWeatherMap API key or key blocked.")
                    return {"cod": 401, "message": "Invalid API key"}
                else:
                    logger.error(f"OpenWeatherMap API error: Status {response.status}, Response: {await response.text()}")
                    return {"cod": response.status, "message": "API error"}

    except aiohttp.ClientConnectorError as e:
        logger.error(f"Network error connecting to OpenWeatherMap: {e}")
        return {"cod": 503, "message": "Network error"} # Service Unavailable
    except Exception as e:
        logger.exception(f"An unexpected error occurred while fetching weather for {city_name}: {e}")
        return {"cod": 500, "message": "Internal error"} # Internal Server Error


def format_weather_message(data: Dict[str, Any], city_name: str) -> str:
    """
    Форматирует данные о погоде в читаемое сообщение.

    Args:
        data: Словарь с данными от OpenWeatherMap API.
        city_name: Название города (для отображения, если API вернул другое).

    Returns:
        Строка с сообщением о погоде.
    """
    try:
        main_data = data.get("main", {})
        weather_info = data.get("weather", [{}])[0] # Берем первый элемент списка погоды
        wind_data = data.get("wind", {})
        cloud_data = data.get("clouds", {})

        temp = main_data.get("temp", "N/A")
        feels_like = main_data.get("feels_like", "N/A")
        humidity = main_data.get("humidity", "N/A")
        pressure_hpa = main_data.get("pressure") # Давление в гПа
        # Переведем гПа в мм рт. ст. (1 гПа ≈ 0.750062 мм рт. ст.)
        pressure_mmhg = round(pressure_hpa * 0.750062) if pressure_hpa else "N/A"

        description = weather_info.get("description", "невідомо").capitalize()
        # Emoji для погоды (можно расширить)
        weather_icons_map = {
             "clear sky": "☀️", "few clouds": "🌤️", "scattered clouds": "☁️",
             "broken clouds": "☁️", "overcast clouds": "🌥️", "shower rain": "🌦️",
             "rain": "🌧️", "light rain": "🌧️", "thunderstorm": "⛈️", "snow": "❄️", "mist": "🌫️"
        }
        # Ищем по частичному совпадению, если точного нет
        icon_emoji = "❓"
        for key, emoji in weather_icons_map.items():
            if key in description.lower():
                icon_emoji = emoji
                break

        wind_speed = wind_data.get("speed", "N/A")
        wind_deg = wind_data.get("deg") # Направление ветра в градусах
        # Функция для преобразования градусов в направление ветра
        def deg_to_compass(num):
            if num is None: return ""
            val=int((num/22.5)+.5)
            arr=["Пн","Пн-Пн-Сх","Пн-Сх","Сх-Пн-Сх","Сх","Сх-Пд-Сх","Пд-Сх","Пд-Пд-Сх","Пд","Пд-Пд-Зх","Пд-Зх","Зх-Пд-Зх","Зх","Зх-Пн-Зх","Пн-Зх","Пн-Пн-Зх"]
            return arr[(val % 16)]
        wind_direction = deg_to_compass(wind_deg)

        clouds_percent = cloud_data.get("all", "N/A") # Облачность в %

        # Название города из ответа API может быть точнее
        response_city_name = data.get("name", city_name.capitalize())

        # Формируем сообщение с HTML тегами для выделения
        message_lines = [
            f"<b>Погода в м. {response_city_name}:</b>\n",
            f"{icon_emoji} {description}",
            f"🌡️ Температура: {temp}°C (відчувається як {feels_like}°C)",
            f"💧 Вологість: {humidity}%",
            f"💨 Вітер: {wind_speed} м/с {wind_direction}",
            f"🧭 Тиск: {pressure_mmhg} мм рт.ст.",
            f"☁️ Хмарність: {clouds_percent}%"
        ]
        return "\n".join(message_lines)

    except Exception as e:
        logger.exception(f"Error formatting weather data for {city_name}: {e}")
        return f"Помилка обробки даних про погоду для м. {city_name.capitalize()}."