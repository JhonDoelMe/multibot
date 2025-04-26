import aiohttp
import os

async def get_currency_rate(base: str = "USD", target: str = "UAH"):
    api_key = os.getenv('EXCHANGE_API_KEY')
    url = f'https://v6.exchangerate-api.com/v6/{api_key}/latest/{base}'
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                data = await resp.json()
                rate = data['conversion_rates'][target]
                return f"Курс {base} к {target}: {rate:.2f}"
            return "Ошибка API: не удалось получить курс"