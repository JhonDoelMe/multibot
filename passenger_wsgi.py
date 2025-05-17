# /home3/anubisua/telegram_bot/passenger_wsgi.py
import sys
import os
import asyncio
import datetime # For logging timestamp
import traceback # For full tracebacks

# --- Basic Error Logging to a file ---
LOG_DIR_PASSENGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs_passenger")
if not os.path.exists(LOG_DIR_PASSENGER):
    try:
        os.makedirs(LOG_DIR_PASSENGER, exist_ok=True)
    except Exception:
        LOG_DIR_PASSENGER = os.path.dirname(os.path.abspath(__file__))

PASSENGER_LOG_FILE = os.path.join(LOG_DIR_PASSENGER, "passenger_wsgi_startup.log")

def _log_passenger_message(message_type, message):
    """Logs a message to the passenger_wsgi_startup.log file."""
    try:
        with open(PASSENGER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] [{os.getpid()}] [{message_type}] {message}\n")
    except Exception:
        print(f"PASSENGER_WSGI_{message_type}: {message}", file=sys.stderr)

_log_passenger_message("INFO", "--- passenger_wsgi.py (project_root_path version) started ---")
_log_passenger_message("INFO", f"Python executable: {sys.executable}")
_log_passenger_message("INFO", f"Python version: {sys.version}")
_log_passenger_message("INFO", f"Initial sys.path: {sys.path}")
_log_passenger_message("INFO", f"Current working directory: {os.getcwd()}")


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__)) # This should be /home3/anubisua/telegram_bot

# Add the PROJECT_ROOT to sys.path so that imports like 'from src import ...' work.
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
    _log_passenger_message("INFO", f"Added to sys.path: {PROJECT_ROOT}")
else:
    _log_passenger_message("INFO", f"Already in sys.path: {PROJECT_ROOT}")

_log_passenger_message("INFO", f"Modified sys.path: {sys.path}")

imported_bot_module_successfully = False
bot_import_error_message = None
aiohttp_app_instance = None
app_creation_error_message = None

try:
    _log_passenger_message("INFO", "Attempting to import 'get_aiohttp_app' from 'src.bot'...")
    from src.bot import get_aiohttp_app # This should now work correctly
    imported_bot_module_successfully = True
    _log_passenger_message("INFO", "Successfully imported 'get_aiohttp_app' from 'src.bot'.")

    _log_passenger_message("INFO", "Attempting to initialize aiohttp application instance via get_aiohttp_app()...")
    try:
        try:
            loop = asyncio.get_running_loop()
            _log_passenger_message("INFO", f"Found running asyncio loop: {loop}")
        except RuntimeError: 
            _log_passenger_message("INFO", "No running asyncio loop, creating a new one.")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        aiohttp_app_instance = loop.run_until_complete(get_aiohttp_app())
        _log_passenger_message("INFO", f"aiohttp application instance created: {aiohttp_app_instance}")
        
        if aiohttp_app_instance is None:
            app_creation_error_message = "get_aiohttp_app() returned None"
            _log_passenger_message("CRITICAL_ERROR", app_creation_error_message)
    except Exception as e_app_create:
        app_creation_error_message = f"Failed to create aiohttp app instance: {e_app_create}"
        _log_passenger_message("CRITICAL_ERROR", app_creation_error_message)
        _log_passenger_message("CRITICAL_ERROR", f"Traceback: {traceback.format_exc()}")

except RecursionError as re:
    bot_import_error_message = f"RecursionError during import of src.bot: {re}"
    _log_passenger_message("CRITICAL_ERROR", bot_import_error_message)
    _log_passenger_message("CRITICAL_ERROR", f"Traceback: {traceback.format_exc()}")
except ImportError as ie:
    bot_import_error_message = f"ImportError for src.bot or its dependencies: {ie}"
    _log_passenger_message("ERROR", bot_import_error_message)
    _log_passenger_message("ERROR", f"Traceback: {traceback.format_exc()}")
except Exception as e_general_import:
    bot_import_error_message = f"Unexpected error during import of src.bot: {e_general_import}"
    _log_passenger_message("ERROR", bot_import_error_message)
    _log_passenger_message("ERROR", f"Traceback: {traceback.format_exc()}")

if aiohttp_app_instance:
    application = aiohttp_app_instance
    _log_passenger_message("INFO", f"'application' set to the aiohttp app instance: {application}")
elif bot_import_error_message or app_creation_error_message:
    _log_passenger_message("ERROR", "Setting 'application' to an error display app due to import/creation failure.")
    def error_display_wsgi_app(environ, start_response):
        status = '503 Service Unavailable'
        error_to_display = bot_import_error_message or app_creation_error_message or "Unknown startup error"
        output_content = (
            f"Application Startup Error.\n"
            f"Please check the server logs, specifically 'passenger_wsgi_startup.log' in the application root's 'logs_passenger' directory.\n"
            f"Error details: {error_to_display}"
        ).encode('utf-8')
        response_headers = [('Content-type', 'text/plain; charset=utf-8'), 
                            ('Content-Length', str(len(output_content)))]
        start_response(status, response_headers)
        return [output_content]
    application = error_display_wsgi_app
else:
    _log_passenger_message("CRITICAL_ERROR", "Fell through: 'application' could not be determined (aiohttp_app_instance is None and no specific error was caught for it).")
    def critical_fallback_wsgi_app(environ, start_response):
        status = '500 Internal Server Error'
        output = b"Critical fallback: Unknown error during passenger_wsgi.py execution. Check logs."
        response_headers = [('Content-type', 'text/plain'), ('Content-Length', str(len(output)))]
        start_response(status, response_headers)
        return [output]
    application = critical_fallback_wsgi_app

_log_passenger_message("INFO", f"--- passenger_wsgi.py (project_root_path version) finished evaluation. 'application' type: {type(application)} ---")