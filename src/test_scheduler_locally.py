# test_scheduler_locally.py
import asyncio
import time
import subprocess
import os

PROJECT_ROOT = "C:\Users\marik\gitbot\multibot" # ВАШ ШЛЯХ
VENV_PYTHON = os.path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe") # Приклад шляху до Python у venv

async def run_reminder_task():
    # Переконайтеся, що шляхи правильні
    process = await asyncio.create_subprocess_exec(
        VENV_PYTHON, "-m", "src", "--task=process_weather_reminders",
        cwd=PROJECT_ROOT, # Встановлюємо робочу директорію
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if stdout:
        print(f"[STDOUT]\n{stdout.decode()}")
    if stderr:
        print(f"[STDERR]\n{stderr.decode()}")
    print("-" * 20)

async def main_loop():
    while True:
        print(f"Running reminder task at {time.strftime('%Y-%m-%d %H:%M:%S')}")
        await run_reminder_task()
        print(f"Task finished. Waiting for 60 seconds...")
        await asyncio.sleep(60) # Запускати кожну хвилину

if __name__ == "__main__":
    # Потрібно налаштувати логування і конфігурацію так само, як в __main__.py,
    # якщо скрипт завдань на це розраховує при прямому імпорті.
    # Або, як у прикладі вище, запускати через subprocess, тоді __main__.py сам все ініціалізує.
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("Local scheduler stopped.")