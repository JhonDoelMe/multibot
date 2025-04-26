import os
from pathlib import Path

# Определяем базовую директорию как текущую
BASE_DIR = Path(__file__).resolve().parent

# Структура директорий
DIRS = [
    "src/handlers",
    "src/keyboards",
    "src/modules/weather",
    "src/modules/currency",
    "src/modules/alert",
    "src/db",
    "src/utils",
    "src/middlewares",
]

# Структура файлов (включая __init__.py для пакетов)
FILES = [
    "src/__init__.py",
    "src/__main__.py",
    "src/bot.py",
    "src/config.py",
    "src/handlers/__init__.py",
    "src/handlers/common.py",
    "src/keyboards/__init__.py",
    "src/keyboards/inline_main.py",
    "src/modules/__init__.py",
    "src/modules/weather/__init__.py",
    "src/modules/weather/handlers.py",
    "src/modules/weather/keyboard.py",
    "src/modules/weather/service.py",
    "src/modules/currency/__init__.py",
    "src/modules/currency/handlers.py",
    "src/modules/currency/keyboard.py",
    "src/modules/currency/service.py",
    "src/modules/alert/__init__.py",
    "src/modules/alert/handlers.py",
    "src/modules/alert/keyboard.py",
    "src/modules/alert/service.py",
    "src/db/__init__.py",
    "src/db/database.py",
    "src/db/models.py",
    "src/utils/__init__.py",
    "src/middlewares/__init__.py",
    ".gitignore",
    "requirements.txt",
    ".env.example",
    ".env", # Создаем пустой .env
    "Dockerfile",
    "fly.toml",
]

# Содержимое для некоторых файлов
FILE_CONTENT = {
    ".gitignore": """\
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
pip-wheel-metadata/
share/python-wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Environments
.env
.venv
env/
venv/
ENV/
env.bak
venv.bak

# Spyder project settings
.spyderproject
.spyproject

# Rope project settings
.ropeproject

# mkdocs documentation
/site

# mypy
.mypy_cache/
.dmypy.json
dmypy.json

# Pyre type checker
.pyre/

# IDE specific files
.vscode/
.idea/
*.swp
*~
""",
    "requirements.txt": """\
aiogram>=3.0.0 # Используем aiogram 3+
python-dotenv>=1.0.0
aiohttp>=3.8.0 # Для вебхука и HTTP-запросов
# Добавим позже: sqlalchemy, asyncpg/aiosqlite, httpx (альтернатива aiohttp client)
""",
    ".env.example": """\
# Telegram Bot Token from BotFather
BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"

# API Keys (add as needed)
WEATHER_API_KEY="YOUR_OPENWEATHERMAP_API_KEY"
CURRENCY_API_KEY="YOUR_CURRENCY_API_KEY" # Specify which API you'll use
# ALERT_API_URL="URL_FOR_ALERT_API" # Or maybe token if needed

# Webhook settings (if using webhook for Fly.io)
# These might be set via Fly.io secrets instead
# WEBHOOK_HOST="your-app-name.fly.dev"
# WEBHOOK_PATH="/webhook/bot" # Random secure path is better
# WEBAPP_HOST="0.0.0.0" # Host for the web server inside the container
# WEBAPP_PORT="8080" # Port for the web server inside the container (Fly.io maps 80/443 to this)

# Database URL (Example for PostgreSQL)
# DATABASE_URL="postgresql+asyncpg://user:password@host:port/database"
# Example for SQLite (relative path)
# DATABASE_URL="sqlite+aiosqlite:///./database.db"
""",
}


def create_structure():
    print("Creating project structure...")

    # Создаем директории
    for dir_path in DIRS:
        full_path = BASE_DIR / dir_path
        try:
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"  Created directory: {full_path}")
        except OSError as e:
            print(f"Error creating directory {full_path}: {e}")

    # Создаем файлы
    for file_path in FILES:
        full_path = BASE_DIR / file_path
        try:
            # Убедимся, что родительская директория существует
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Создаем файл и записываем контент, если он есть
            content = FILE_CONTENT.get(file_path)
            with open(full_path, 'w', encoding='utf-8') as f:
                if content:
                    f.write(content)
                else:
                    # Просто создаем пустой файл, если контента нет
                    pass # Файл создается при открытии в режиме 'w'
            print(f"  Created file:      {full_path}")
        except OSError as e:
            print(f"Error creating file {full_path}: {e}")

    print("\nProject structure created successfully!")
    print("Remember to:")
    print("1. Fill in your actual tokens in the .env file.")
    print("2. Initialize Git (`git init`) if you haven't already.")
    print("3. Create a Python virtual environment and install requirements (`pip install -r requirements.txt`).")


if __name__ == "__main__":
    create_structure()
    input("Press Enter to exit...") # Пауза для Windows, чтобы окно не закрылось сразу