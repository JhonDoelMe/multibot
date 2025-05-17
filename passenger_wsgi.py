# /home3/anubisua/telegram_bot/passenger_wsgi.py
import sys
import os
import asyncio # Може знадобитися для запуску event loop, якщо Passenger його не надає

# Додаємо директорію 'src' до шляху пошуку Python
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

# Імпортуємо функцію, яка повертає наш aiohttp додаток
try:
    from bot import get_aiohttp_app # З вашого src/bot.py
except ImportError as e:
    # Це критична помилка, якщо Passenger не може знайти ваш додаток
    # Можна спробувати створити простий текстовий файл помилки,
    # щоб побачити її в логах Passenger або при прямому запиті.
    def application(environ, start_response): # Заглушка для WSGI, щоб Passenger не падав одразу
        status = '500 Internal Server Error'
        output = f"Failed to import bot application: {e}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
    # Або просто підняти виключення, щоб побачити трейсбек в логах Passenger
    # raise

# Phusion Passenger очікує змінну 'application', яка є ASGI або WSGI callable.
# Наш get_aiohttp_app() є асинхронною функцією, яка повертає aiohttp.web.Application.
# Потрібно запустити її в event loop, щоб отримати сам додаток.
# Однак, сучасні версії Passenger можуть підтримувати ASGI "з коробки"
# і можуть очікувати саму ASGI-сумісну програму.

# Спроба 1: Пряме присвоєння (якщо Passenger може обробити async factory)
# application = get_aiohttp_app() # Це не спрацює, бо get_aiohttp_app - це корутина

# Спроба 2: Запуск корутини для отримання додатку.
# Це потрібно робити обережно, оскільки Passenger може мати свій власний event loop.
# Якщо Passenger запускає це в своєму власному event loop, то це може спрацювати.
# Якщо ні, то потрібно буде створити та запустити loop тут.

_app_instance = None

def _get_or_create_app_instance():
    global _app_instance
    if _app_instance is None:
        try:
            # Спроба отримати існуючий event loop або створити новий
            loop = asyncio.get_event_loop_policy().get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            _app_instance = loop.run_until_complete(get_aiohttp_app())
        except Exception as e:
            # Логування помилки тут важливе, але стандартний logger може ще не бути налаштований
            # Можна писати в stderr або тимчасовий файл
            print(f"CRITICAL ERROR in passenger_wsgi.py: Failed to create aiohttp app instance: {e}", file=sys.stderr)
            # Повертаємо заглушку, щоб Passenger не падав з помилкою про відсутність 'application'
            def error_app(environ, start_response):
                status = '500 Internal Server Error'
                output = f"Application startup error: {e}".encode('utf-8')
                response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
                start_response(status, response_headers)
                return [output]
            return error_app # Повертаємо WSGI-сумісну заглушку
    return _app_instance

# Головний об'єкт додатку для Passenger
application = _get_or_create_app_instance()

# Важливо: Переконайтеся, що ваш cPanel "Setup Python App" налаштований:
# 1. Application Root: /home3/anubisua/telegram_bot
# 2. Application Startup File: passenger_wsgi.py (цей файл)
# 3. Application Entry point / Callable Object: application (ця змінна)
