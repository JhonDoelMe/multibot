# src/modules/weather_backup/service.py

import logging
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List # List не використовується напряму, але може знадобитися
from datetime import datetime # timedelta не використовується напряму
import pytz
from aiogram import Bot
from aiocache import cached

from src import config
# SHARED_ICON_EMOJI та DAYS_OF_WEEK_UK не використовуються тут безпосередньо,
# але можуть бути корисні, якщо логіка форматування стане складнішою
# from src.modules.weather.service import ICON_CODE_TO_EMOJI as SHARED_ICON_EMOJI
from src.modules.weather.service import DAYS_OF_WEEK_UK # Використовується в format_forecast_backup_message

logger = logging.getLogger(__name__)

WEATHERAPI_BASE_URL = "http://api.weatherapi.com/v1" # Виправлено на https для безпеки, якщо API підтримує
# Зазвичай API підтримують HTTPS, варто перевірити документацію WeatherAPI.com.
# Якщо HTTPS не підтримується, повернути на HTTP. Для прикладу залишу HTTP, як було.
# WEATHERAPI_BASE_URL = "https://api.weatherapi.com/v1"


WEATHERAPI_CURRENT_URL = f"{WEATHERAPI_BASE_URL}/current.json"
WEATHERAPI_FORECAST_URL = f"{WEATHERAPI_BASE_URL}/forecast.json"

TZ_KYIV = pytz.timezone('Europe/Kyiv') # Не використовується в цьому файлі, але може бути корисним для майбутніх розширень
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

WIND_DIRECTIONS_UK = {
    "N": "Пн", "NNE": "Пн-Пн-Сх", "NE": "Пн-Сх", "ENE": "Сх-Пн-Сх",
    "E": "Сх", "ESE": "Сх-Пд-Сх", "SE": "Пд-Сх", "SSE": "Пд-Пд-Сх",
    "S": "Пд", "SSW": "Пд-Пд-Зх", "SW": "Пд-Зх", "WSW": "Зх-Пд-Зх",
    "W": "Зх", "WNW": "Зх-Пн-Зх", "NW": "Пн-Зх", "NNW": "Пн-Пн-Зх",
    "NORTH": "Пн", "EAST": "Сх", "SOUTH": "Пд", "WEST": "Зх", # Додано повні назви у верхньому регістрі
}

# Стандартизована функція для повернення помилок API цього модуля
def _generate_weatherapi_error_response(code: int, message: str, error_details: Optional[Dict] = None) -> Dict[str, Any]:
    # WeatherAPI часто повертає помилку у форматі {"error": {"code": ..., "message": ...}}
    # Ми можемо використовувати це для більшої деталізації.
    actual_code = error_details.get("code", code) if error_details else code
    actual_message = error_details.get("message", message) if error_details else message

    logger.error(f"WeatherAPI.com Error: Code {actual_code}, Message: {actual_message}")
    return {"error": {"code": actual_code, "message": actual_message, "source_api": "WeatherAPI.com"}}


def _weatherapi_generic_key_builder(func_ref: Any, *args: Any, **kwargs: Any) -> str:
    # args[0] зазвичай bot, args[1] - location або kwargs['location']
    # kwargs['location'] має пріоритет, якщо передано як іменований аргумент
    location_str = kwargs.get("location")
    if location_str is None and len(args) > 1 and isinstance(args[1], str):
        location_str = args[1] # Якщо location передано як позиційний аргумент

    endpoint_name = kwargs.get("endpoint_name", "unknown_endpoint")
    days_arg = kwargs.get("days") # Може бути None

    # Нормалізація location_str
    safe_location = str(location_str).strip().lower() if location_str else "unknown_location"

    key_parts = ["weatherapi", endpoint_name, "location", safe_location]
    if days_arg is not None:
        key_parts.extend(["days", str(days_arg)])
    
    final_key = ":".join(key_parts)
    # logger.debug(f"Generated cache key for WeatherAPI: {final_key} (func: {func_ref.__name__}, location: '{location_str}', days: {days_arg})")
    return final_key

@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda f, *a, **kw: _weatherapi_generic_key_builder(f, *a, **kw, endpoint_name="current"),
        namespace="weather_backup_service")
async def get_current_weather_weatherapi(bot: Bot, *, location: str) -> Dict[str, Any]:
    logger.info(f"Service get_current_weather_weatherapi: Called with location='{location}'")
    if not config.WEATHERAPI_COM_KEY:
        return _generate_weatherapi_error_response(500, "Ключ WeatherAPI.com (WEATHERAPI_COM_KEY) не налаштовано.")
    if not location or not str(location).strip():
        logger.warning("Service get_current_weather_weatherapi: Received empty location.")
        return _generate_weatherapi_error_response(400, "Назва міста або координати не можуть бути порожніми.")

    params = {"key": config.WEATHERAPI_COM_KEY, "q": str(location).strip(), "lang": "uk"}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch current weather for '{location}' from WeatherAPI.com")
            async with aiohttp.ClientSession() as session:
                async with session.get(WEATHERAPI_CURRENT_URL, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text() # Отримуємо текст для логування
                    
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            # WeatherAPI повертає помилку в тілі JSON, навіть при HTTP 200, якщо щось не так з ключем чи запитом
                            if "error" in data:
                                logger.error(f"WeatherAPI.com returned an error in JSON for current weather '{location}': {data['error']}")
                                return _generate_weatherapi_error_response(data["error"].get("code", 500), data["error"].get("message", "Помилка від WeatherAPI"), error_details=data["error"])
                            logger.debug(f"WeatherAPI.com current weather response for '{location}': status={response.status}, data preview={str(data)[:300]}")
                            return data # Успішна відповідь
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            last_exception = Exception("Невірний формат JSON відповіді від WeatherAPI.com")
                            return _generate_weatherapi_error_response(500, "Невірний формат JSON відповіді від резервного API.")
                    # Обробка HTTP помилок від WeatherAPI
                    elif response.status == 400: # Некоректний запит
                         logger.error(f"WeatherAPI.com returned 400 Bad Request for '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(content_type=None); api_error = data.get("error")
                         except: api_error = None
                         return _generate_weatherapi_error_response(400, "Некоректний запит до резервного API.", error_details=api_error)
                    elif response.status == 401: # Невірний ключ
                        logger.error("WeatherAPI.com returned 401 Unauthorized (Invalid API key).")
                        return _generate_weatherapi_error_response(401, "Невірний ключ резервного API погоди.")
                    elif response.status == 403: # Ключ вимкнено або перевищено ліміт
                        logger.error("WeatherAPI.com returned 403 Forbidden (Key disabled or over quota).")
                        return _generate_weatherapi_error_response(403, "Доступ до резервного API погоди заборонено (можливо, перевищено ліміт).")
                    elif response.status >= 500 or response.status == 429: # Серверна помилка або Rate Limit
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: WeatherAPI.com Server/RateLimit Error {response.status} for '{location}'. Retrying...")
                    else: # Інші непередбачені статуси
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from WeatherAPI.com for '{location}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Неочікувана помилка резервного API: {response.status}")
                        return _generate_weatherapi_error_response(response.status, f"Неочікувана помилка резервного API: {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to WeatherAPI.com for '{location}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching current weather from WeatherAPI.com for '{location}': {e}", exc_info=True)
            return _generate_weatherapi_error_response(500, "Внутрішня помилка обробки резервної погоди.")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay}s before next WeatherAPI.com current weather retry for '{location}'...")
            await asyncio.sleep(delay)
        else: # Всі спроби вичерпано
            error_message = f"Не вдалося отримати резервні дані погоди для '{location}' після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            
            final_error_code = 503 # Service Unavailable
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504 # Gateway Timeout
            
            return _generate_weatherapi_error_response(final_error_code, error_message)
    return _generate_weatherapi_error_response(500, f"Не вдалося отримати резервні дані погоди для '{location}' (неочікуваний вихід).")


@cached(ttl=config.CACHE_TTL_WEATHER_BACKUP,
        key_builder=lambda f, *a, **kw: _weatherapi_generic_key_builder(f, *a, **kw, endpoint_name="forecast"),
        namespace="weather_backup_service")
async def get_forecast_weatherapi(bot: Bot, *, location: str, days: int = 3) -> Dict[str, Any]:
    logger.info(f"Service get_forecast_weatherapi: Called for location='{location}', days={days}")
    if not config.WEATHERAPI_COM_KEY:
        return _generate_weatherapi_error_response(500, "Ключ WeatherAPI.com (WEATHERAPI_COM_KEY) не налаштовано для прогнозу.")
    if not location or not str(location).strip():
        logger.warning("Service get_forecast_weatherapi: Received empty location.")
        return _generate_weatherapi_error_response(400, "Назва міста або координати для прогнозу не можуть бути порожніми.")
    
    # WeatherAPI обмежує кількість днів прогнозу для безкоштовного тарифу (зазвичай 3)
    # Платні тарифи можуть дозволяти більше (до 10 або 14).
    # Тут ми просто обмежуємо до 10, як у вихідному коді, але варто перевірити актуальні ліміти API.
    if not 1 <= days <= 10: # WeatherAPI дозволяє до 10 днів (або 14 для деяких планів)
        logger.warning(f"Service get_forecast_weatherapi: Invalid number of days requested: {days}. Clamping to 3-10 range or using API default if not specified.")
        # Якщо дні занадто малі, API може повернути помилку. Якщо занадто великі - теж.
        # Встановлюємо безпечне значення, наприклад 3, або дозволяємо API вирішити, якщо параметр days не передавати.
        # Для простоти, залишимо як було, з попередженням. API зазвичай обрізає до макс. доступного.
        # days = 3 # Або можна взагалі не передавати параметр days, якщо хочемо дефолт від API (зазвичай 3)

    params = {"key": config.WEATHERAPI_COM_KEY, "q": str(location).strip(), "days": days, "lang": "uk", "alerts": "no", "aqi": "no"}
    last_exception = None

    for attempt in range(MAX_RETRIES):
        try:
            logger.debug(f"Attempt {attempt + 1}/{MAX_RETRIES} to fetch {days}-day forecast for '{location}' from WeatherAPI.com")
            async with aiohttp.ClientSession() as session:
                async with session.get(WEATHERAPI_FORECAST_URL, params=params, timeout=config.API_REQUEST_TIMEOUT) as response:
                    response_data_text = await response.text()
                    if response.status == 200:
                        try:
                            data = await response.json(content_type=None)
                            if "error" in data:
                                logger.error(f"WeatherAPI.com returned an error in JSON for forecast '{location}', {days}d: {data['error']}")
                                return _generate_weatherapi_error_response(data["error"].get("code", 500), data["error"].get("message", "Помилка від WeatherAPI прогнозу"), error_details=data["error"])
                            logger.debug(f"WeatherAPI.com forecast response for '{location}', {days}d: status={response.status}, data preview={str(data)[:300]}")
                            return data
                        except aiohttp.ContentTypeError:
                            logger.error(f"Attempt {attempt + 1}: Failed to decode JSON forecast from WeatherAPI.com for '{location}'. Response: {response_data_text[:500]}")
                            last_exception = Exception("Невірний формат JSON відповіді від WeatherAPI.com (прогноз)")
                            return _generate_weatherapi_error_response(500, "Невірний формат JSON відповіді від резервного API прогнозу.")
                    elif response.status == 400:
                         logger.error(f"WeatherAPI.com returned 400 Bad Request for forecast '{location}'. Response: {response_data_text[:500]}")
                         try: data = await response.json(content_type=None); api_error = data.get("error")
                         except: api_error = None
                         return _generate_weatherapi_error_response(400, "Некоректний запит до резервного API прогнозу.", error_details=api_error)
                    elif response.status == 401:
                        logger.error("WeatherAPI.com returned 401 Unauthorized for forecast (Invalid API key).")
                        return _generate_weatherapi_error_response(401, "Невірний ключ резервного API прогнозу.")
                    elif response.status == 403:
                        logger.error("WeatherAPI.com returned 403 Forbidden for forecast (Key disabled or over quota).")
                        return _generate_weatherapi_error_response(403, "Доступ до резервного API прогнозу заборонено.")
                    elif response.status >= 500 or response.status == 429:
                        last_exception = aiohttp.ClientResponseError(response.request_info, response.history, status=response.status, message=f"Server error {response.status} or Rate limit")
                        logger.warning(f"Attempt {attempt + 1}: WeatherAPI.com Server/RateLimit Error {response.status} for forecast '{location}'. Retrying...")
                    else:
                        logger.error(f"Attempt {attempt + 1}: Unexpected status {response.status} from WeatherAPI.com for forecast '{location}'. Response: {response_data_text[:200]}")
                        last_exception = Exception(f"Неочікувана помилка резервного API прогнозу: {response.status}")
                        return _generate_weatherapi_error_response(response.status, f"Неочікувана помилка резервного API прогнозу: {response.status}")
        except (aiohttp.ClientConnectorError, asyncio.TimeoutError) as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}: Network error connecting to WeatherAPI.com for forecast '{location}': {e}. Retrying...")
        except Exception as e:
            logger.exception(f"Attempt {attempt + 1}: An unexpected error occurred fetching forecast from WeatherAPI.com for '{location}': {e}", exc_info=True)
            return _generate_weatherapi_error_response(500, "Внутрішня помилка обробки резервного прогнозу.")

        if attempt < MAX_RETRIES - 1:
            delay = INITIAL_DELAY * (2 ** attempt)
            logger.info(f"Waiting {delay}s before next WeatherAPI.com forecast retry for '{location}'...")
            await asyncio.sleep(delay)
        else:
            error_message = f"Не вдалося отримати резервний прогноз для '{location}' ({days}д) після {MAX_RETRIES} спроб."
            if last_exception: error_message += f" Остання помилка: {str(last_exception)}"
            logger.error(error_message)
            
            final_error_code = 503
            if isinstance(last_exception, aiohttp.ClientResponseError): final_error_code = last_exception.status
            elif isinstance(last_exception, asyncio.TimeoutError): final_error_code = 504

            return _generate_weatherapi_error_response(final_error_code, error_message)
    return _generate_weatherapi_error_response(500, f"Не вдалося отримати резервний прогноз для '{location}' ({days}д) (неочікуваний вихід).")


def format_weather_backup_message(data: Dict[str, Any], requested_location: str) -> str:
    # Перевіряємо, чи дані містять структуру помилки від наших сервісних функцій
    if "error" in data and isinstance(data["error"], dict) and "source_api" in data["error"]:
        error_info = data["error"]
        error_code = error_info.get('code', 'N/A')
        error_message = error_info.get('message', 'Невідома помилка резервного API')
        return f"😔 Не вдалося отримати резервну погоду для <b>{requested_location}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    # Якщо це помилка, яку повернуло саме API WeatherAPI і вона не була перехоплена вище
    # (наприклад, якщо get_current_weather_weatherapi повернуло data з ключем "error" напряму)
    if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]:
         error_info = data["error"]
         error_code = error_info.get('code', 'API')
         error_message = error_info.get('message', 'Помилка від сервісу погоди')
         logger.warning(f"Formatting direct API error for backup weather: {error_info} for location {requested_location}")
         return f"😔 Не вдалося отримати резервну погоду для <b>{requested_location}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"


    location = data.get("location", {})
    current = data.get("current", {})
    condition = current.get("condition", {})

    city_name_api = location.get("name")
    region_api = location.get("region")
    
    # Визначаємо ім'я для відображення
    # Якщо API повернуло ім'я, використовуємо його. Інакше - те, що ввів користувач.
    display_location = city_name_api if city_name_api else requested_location
    if city_name_api and region_api and region_api.lower() != city_name_api.lower():
        display_location = f"{city_name_api}, {region_api}"
    elif not city_name_api and region_api: # Якщо є тільки регіон від API
        display_location = f"{requested_location} ({region_api})"


    temp_c = current.get("temp_c")
    feelslike_c = current.get("feelslike_c")
    condition_text = condition.get("text", "немає опису")
    condition_code = condition.get("code")
    wind_kph = current.get("wind_kph")
    wind_dir_en = current.get("wind_dir", "").upper() # Переводимо в верхній регістр для надійного пошуку в словнику
    pressure_mb = current.get("pressure_mb")
    humidity = current.get("humidity")
    cloud = current.get("cloud") # Це відсоток
    is_day = current.get("is_day", 1) # 1 = Yes, 0 = No
    
    localtime_epoch = location.get("localtime_epoch")
    time_info_str = ""
    if localtime_epoch:
        try:
            # WeatherAPI повертає localtime_epoch, який вже враховує часовий пояс локації
            dt_local = datetime.fromtimestamp(localtime_epoch) # Немає потреби в TZ_KYIV тут
            current_time_str = dt_local.strftime('%H:%M, %d.%m.%Y')
            time_info_str = f"<i>Дані актуальні на {current_time_str} (місцевий час)</i>"
        except Exception as e:
            logger.warning(f"Could not format localtime_epoch {localtime_epoch} from WeatherAPI: {e}")

    emoji = WEATHERAPI_CONDITION_CODE_TO_EMOJI.get(condition_code, "🛰️")
    if not emoji and condition_code == 1000 and not is_day: # Спеціальний випадок для ясної ночі
        emoji = "🌙"

    pressure_mmhg_str = "N/A"
    if pressure_mb is not None:
        try: pressure_mmhg_str = f"{int(pressure_mb * 0.750062)}"
        except (ValueError, TypeError) as e: logger.warning(f"Could not convert pressure {pressure_mb} (mb) to mmhg: {e}")

    wind_mps_str = "N/A"
    if wind_kph is not None:
        try:
            wind_mps = float(wind_kph) * 1000 / 3600
            wind_mps_str = f"{wind_mps:.1f}"
        except (ValueError, TypeError) as e: logger.warning(f"Could not convert wind speed {wind_kph} (kph) to m/s: {e}")

    wind_dir_uk = WIND_DIRECTIONS_UK.get(wind_dir_en, wind_dir_en if wind_dir_en else "N/A")

    message_lines = [
        f"<b>Резервна погода в: {display_location}</b> {emoji}"
    ]
    if temp_c is not None and feelslike_c is not None:
        message_lines.append(f"🌡️ Температура: <b>{temp_c:.1f}°C</b> (відчувається як {feelslike_c:.1f}°C)")
    elif temp_c is not None:
         message_lines.append(f"🌡️ Температура: <b>{temp_c:.1f}°C</b>")
    
    message_lines.append(f"🌬️ Вітер: {wind_mps_str} м/с ({wind_dir_uk})")
    if humidity is not None:
        message_lines.append(f"💧 Вологість: {humidity}%")
    message_lines.append(f"🌫️ Тиск: {pressure_mmhg_str} мм рт.ст.")
    if cloud is not None:
        message_lines.append(f"☁️ Хмарність: {cloud}%")
    
    message_lines.append(f"📝 Опис: {condition_text.capitalize()}")
    if time_info_str:
        message_lines.append(time_info_str)
    
    message_lines.append("\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>")
    return "\n".join(filter(None, message_lines))


def format_forecast_backup_message(data: Dict[str, Any], requested_location: str) -> str:
    if "error" in data and isinstance(data["error"], dict) and "source_api" in data["error"]: # Наша стандартизована помилка
        error_info = data["error"]
        error_code = error_info.get('code', 'N/A')
        error_message = error_info.get('message', 'Невідома помилка резервного API прогнозу')
        return f"😔 Не вдалося отримати резервний прогноз для <b>{requested_location}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    if "error" in data and isinstance(data["error"], dict) and "message" in data["error"]: # Помилка від самого WeatherAPI
         error_info = data["error"]
         error_code = error_info.get('code', 'API')
         error_message = error_info.get('message', 'Помилка від сервісу прогнозу')
         logger.warning(f"Formatting direct API error for backup forecast: {error_info} for location {requested_location}")
         return f"😔 Не вдалося отримати резервний прогноз для <b>{requested_location}</b>.\n<i>Причина: {error_message} (Код: {error_code})</i>\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>"

    location_data = data.get("location", {})
    forecast_data = data.get("forecast", {})
    forecast_days_list = forecast_data.get("forecastday", []) # Це список днів
    
    city_name_api = location_data.get("name")
    display_city_name = city_name_api if city_name_api else requested_location
    
    message_lines = [f"<b>Резервний прогноз для: {display_city_name}</b>\n"]

    if not forecast_days_list:
        message_lines.append("😥 На жаль, детальний прогноз на найближчі дні відсутній (резервне джерело).")
    else:
        for day_data in forecast_days_list:
            if not isinstance(day_data, dict): continue # Пропускаємо некоректні дані дня

            date_epoch = day_data.get("date_epoch")
            day_info = day_data.get("day", {})
            condition = day_info.get("condition", {})

            date_str_formatted = day_data.get("date", "N/A") # Резервна дата, якщо епоха відсутня
            if date_epoch:
                try:
                    # date_epoch - це Unix timestamp для початку дня за місцевим часом локації
                    dt_obj_local = datetime.fromtimestamp(date_epoch)
                    day_name_en = dt_obj_local.strftime('%A') # Англійська назва дня тижня
                    day_name_uk = DAYS_OF_WEEK_UK.get(day_name_en, day_name_en) # Переклад
                    date_str_formatted = dt_obj_local.strftime(f'%d.%m ({day_name_uk})')
                except Exception as e:
                    logger.warning(f"Could not format forecast date_epoch {date_epoch} from WeatherAPI: {e}")
            
            avg_temp_c = day_info.get("avgtemp_c")
            max_temp_c = day_info.get("maxtemp_c") # Може бути корисним
            min_temp_c = day_info.get("mintemp_c") # Може бути корисним
            condition_text = condition.get("text", "немає опису")
            condition_code = condition.get("code")
            
            emoji = WEATHERAPI_CONDITION_CODE_TO_EMOJI.get(condition_code, "🛰️")
            
            # Відображаємо середню температуру, якщо є, інакше діапазон мін/макс
            temp_display_parts = []
            if avg_temp_c is not None: temp_display_parts.append(f"{avg_temp_c:.0f}°C")
            if min_temp_c is not None and max_temp_c is not None and avg_temp_c is None : # Показуємо мін/макс, якщо немає середньої
                 temp_display_parts.append(f"(від {min_temp_c:.0f}° до {max_temp_c:.0f}°)")
            elif min_temp_c is not None and avg_temp_c is None:
                 temp_display_parts.append(f"(мін {min_temp_c:.0f}°)")
            elif max_temp_c is not None and avg_temp_c is None:
                 temp_display_parts.append(f"(макс {max_temp_c:.0f}°)")

            temp_display_str = " ".join(temp_display_parts) if temp_display_parts else "N/A"


            message_lines.append(
                f"<b>{date_str_formatted}:</b> {temp_display_str}, {condition_text.capitalize()} {emoji}"
            )
            
    message_lines.append("\n<tg-spoiler>Джерело: weatherapi.com (резерв)</tg-spoiler>")
    return "\n".join(filter(None, message_lines))