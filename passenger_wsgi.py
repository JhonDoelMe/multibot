# /home3/anubisua/telegram_bot/passenger_wsgi.py
import sys
import os
import asyncio
import logging # For basic logging within this file

# --- Basic Error Logging to a file (especially for startup errors) ---
# This helps if the main application logger hasn't been initialized yet.
LOG_DIR_PASSENGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs_passenger")
if not os.path.exists(LOG_DIR_PASSENGER):
    try:
        os.makedirs(LOG_DIR_PASSENGER, exist_ok=True)
    except Exception:
        LOG_DIR_PASSENGER = os.path.dirname(os.path.abspath(__file__)) # Fallback to project root

PASSENGER_ERROR_LOG_FILE = os.path.join(LOG_DIR_PASSENGER, "passenger_wsgi_errors.log")

def _log_passenger_error(message):
    try:
        with open(PASSENGER_ERROR_LOG_FILE, "a") as f:
            f.write(f"[{os.getpid()}] {message}\n")
    except Exception:
        # If logging to file fails, print to stderr (might be captured by Passenger logs)
        print(f"PASSENGER_WSGI_ERROR: {message}", file=sys.stderr)

_log_passenger_error(f"--- passenger_wsgi.py started at {__import__('datetime').datetime.now()} ---")
_log_passenger_error(f"Python executable: {sys.executable}")
_log_passenger_error(f"Python version: {sys.version}")
_log_passenger_error(f"Current working directory: {os.getcwd()}")


# Add 'src' directory to Python's search path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
    _log_passenger_error(f"Added to sys.path: {SRC_DIR}")
else:
    _log_passenger_error(f"Already in sys.path: {SRC_DIR}")

_log_passenger_error(f"sys.path: {sys.path}")

# Import the function that returns our aiohttp application
try:
    _log_passenger_error("Attempting to import get_aiohttp_app from src.bot...")
    from bot import get_aiohttp_app # From your src/bot.py
    _log_passenger_error("Successfully imported get_aiohttp_app.")
except ImportError as e:
    _log_passenger_error(f"CRITICAL: Failed to import 'get_aiohttp_app' from 'bot'. Error: {e}")
    _log_passenger_error(f"Traceback: {__import__('traceback').format_exc()}")
    # This is a critical error; Passenger won't be able to serve the app.
    # We define a fallback WSGI app to make Passenger happy but indicate an error.
    def application(environ, start_response):
        status = '503 Service Unavailable'
        output = f"Application import error: Could not import 'get_aiohttp_app'. Check passenger_wsgi_errors.log. Error: {e}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
    # Exit or raise to make sure the error is prominent if not caught by Passenger logs
    # raise RuntimeError(f"Failed to import get_aiohttp_app: {e}")
except Exception as e_import:
    _log_passenger_error(f"CRITICAL: An unexpected error occurred during import of 'get_aiohttp_app'. Error: {e_import}")
    _log_passenger_error(f"Traceback: {__import__('traceback').format_exc()}")
    def application(environ, start_response): # Fallback
        status = '503 Service Unavailable'
        output = f"Application import error (unexpected). Check passenger_wsgi_errors.log. Error: {e_import}".encode('utf-8')
        response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
    # raise RuntimeError(f"Unexpected error importing get_aiohttp_app: {e_import}")


# This is the ASGI application instance Passenger will serve.
_app_instance = None

def _initialize_app_instance():
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    _log_passenger_error("Attempting to initialize aiohttp application instance...")
    try:
        # Ensure an event loop is available for asyncio.run() or loop.run_until_complete()
        # Modern Passenger versions might handle this better for ASGI.
        try:
            loop = asyncio.get_running_loop()
            _log_passenger_error(f"Found running asyncio loop: {loop}")
        except RuntimeError: # 'RuntimeError: no running event loop'
            _log_passenger_error("No running asyncio loop, creating a new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # get_aiohttp_app is an async function, so we need to run it in the loop
        _log_passenger_error("Calling loop.run_until_complete(get_aiohttp_app())...")
        _app_instance = loop.run_until_complete(get_aiohttp_app())
        _log_passenger_error(f"aiohttp application instance created: {_app_instance}")
        
        if _app_instance is None:
            _log_passenger_error("CRITICAL: get_aiohttp_app() returned None.")
            raise RuntimeError("get_aiohttp_app() returned None")

    except Exception as e:
        _log_passenger_error(f"CRITICAL: Failed to create aiohttp app instance in _initialize_app_instance. Error: {e}")
        _log_passenger_error(f"Traceback: {__import__('traceback').format_exc()}")
        # Define a fallback WSGI app if initialization fails
        def error_application_init(environ, start_response):
            status = '503 Service Unavailable'
            output = f"Application initialization error. Check passenger_wsgi_errors.log. Error: {e}".encode('utf-8')
            response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
            start_response(status, response_headers)
            return [output]
        _app_instance = error_application_init # Assign the error app
        # It's important that 'application' variable below gets *something* callable.
    return _app_instance

# The 'application' variable is what Phusion Passenger looks for.
# It should be the ASGI application instance.
if 'get_aiohttp_app' in globals(): # Check if import was successful
    application = _initialize_app_instance()
else:
    _log_passenger_error("CRITICAL: 'get_aiohttp_app' was not imported, 'application' cannot be initialized correctly.")
    # 'application' would have been set to an error app by the import exception handler.

_log_passenger_error(f"--- passenger_wsgi.py finished evaluation. 'application' type: {type(application)} ---")

# Note: Passenger will call the 'application' variable as a WSGI app.