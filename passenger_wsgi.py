# /home3/anubisua/telegram_bot/passenger_wsgi.py
import sys
import os
import datetime # For logging timestamp
import traceback # For full tracebacks

# --- Basic Error Logging to a file ---
LOG_DIR_PASSENGER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs_passenger")
if not os.path.exists(LOG_DIR_PASSENGER):
    try:
        os.makedirs(LOG_DIR_PASSENGER, exist_ok=True)
    except Exception:
        # If directory creation fails, try to log in the project root
        LOG_DIR_PASSENGER = os.path.dirname(os.path.abspath(__file__))

PASSENGER_LOG_FILE = os.path.join(LOG_DIR_PASSENGER, "passenger_wsgi_startup.log")

def _log_passenger_message(message_type, message):
    try:
        with open(PASSENGER_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now()}] [{os.getpid()}] [{message_type}] {message}\n")
    except Exception:
        # Fallback to stderr if logging to file fails
        print(f"PASSENGER_WSGI_{message_type}: {message}", file=sys.stderr)

_log_passenger_message("INFO", "--- passenger_wsgi.py (test_config_import version) started ---")
_log_passenger_message("INFO", f"Python executable: {sys.executable}")
_log_passenger_message("INFO", f"Python version: {sys.version}")
_log_passenger_message("INFO", f"Initial sys.path: {sys.path}")
_log_passenger_message("INFO", f"Current working directory: {os.getcwd()}")


PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(PROJECT_ROOT, "src")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
    _log_passenger_message("INFO", f"Added to sys.path: {SRC_DIR}")
else:
    _log_passenger_message("INFO", f"Already in sys.path: {SRC_DIR}")

_log_passenger_message("INFO", f"Modified sys.path: {sys.path}")

imported_config_module = None
config_import_error = None

try:
    _log_passenger_message("INFO", "Attempting to import 'src.config' as app_config...")
    # We need to ensure that 'src' itself is not treated as a package that is being re-imported.
    # The structure is /home3/anubisua/telegram_bot/src/config.py
    # And passenger_wsgi.py is in /home3/anubisua/telegram_bot/
    # So, `from src import config` should work if `src` is in sys.path.

    # Check if 'src' is already loaded as a module, which might indicate issues
    if 'src' in sys.modules:
        _log_passenger_message("WARNING", f"'src' is already in sys.modules: {sys.modules['src']}")
        # If src is a namespace package or something unusual, this could be an issue.
        # For a simple directory, this might be okay if sys.path is set up correctly before this.

    import src.config as app_config # Direct import
    imported_config_module = app_config
    _log_passenger_message("INFO", "Successfully imported 'src.config'.")

    if hasattr(imported_config_module, 'BOT_TOKEN'):
        _log_passenger_message("INFO", f"Config BOT_TOKEN: {'Loaded' if imported_config_module.BOT_TOKEN else 'NOT SET'}")
    else:
        _log_passenger_message("WARNING", "Config module does not have BOT_TOKEN attribute.")

except RecursionError as re:
    config_import_error = f"RecursionError during import: {re}"
    _log_passenger_message("CRITICAL_ERROR", config_import_error)
    _log_passenger_message("CRITICAL_ERROR", f"Traceback: {traceback.format_exc()}")
except ImportError as ie:
    config_import_error = f"ImportError: {ie}"
    _log_passenger_message("ERROR", config_import_error)
    _log_passenger_message("ERROR", f"Traceback: {traceback.format_exc()}")
except Exception as e:
    config_import_error = f"Unexpected error during config import: {e}"
    _log_passenger_message("ERROR", config_import_error)
    _log_passenger_message("ERROR", f"Traceback: {traceback.format_exc()}")


# Minimal WSGI application to satisfy Passenger
def application(environ, start_response):
    status = '200 OK'
    output_lines = [
        b"--- Passenger WSGI Test (Config Import) ---",
        f"Python: {sys.version}".encode('utf-8'),
        f"PID: {os.getpid()}".encode('utf-8'),
    ]

    if imported_config_module:
        output_lines.append(b"src.config imported successfully.")
        if hasattr(imported_config_module, 'BOT_TOKEN') and imported_config_module.BOT_TOKEN:
            output_lines.append(b"BOT_TOKEN found in config.")
        else:
            output_lines.append(b"BOT_TOKEN NOT found or empty in config.")
    elif config_import_error:
        output_lines.append(f"Failed to import src.config: {config_import_error}".encode('utf-8'))
    else:
        output_lines.append(b"Unknown state of src.config import.")

    output = b"\n".join(output_lines)
    response_headers = [('Content-type', 'text/plain'),
                        ('Content-Length', str(len(output)))]
    start_response(status, response_headers)
    return [output]

_log_passenger_message("INFO", "--- passenger_wsgi.py (test_config_import version) finished evaluation ---")
_log_passenger_message("INFO", f"Final sys.path: {sys.path}")