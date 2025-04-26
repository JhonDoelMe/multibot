import aiohttp
import os

async def get_weather(city: str = "London"):
    api_key = os.getenv('WEATHER_API_KEY')
    url = f'http://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                temp = data['main']['temp'] - 273.15
                return f"Температура в {city}: {temp:.1f}°C"
            return "Ошибка API: не удалось получить погоду"