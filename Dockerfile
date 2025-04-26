# Используем официальный образ Python 3.11 (slim - урезанная версия)
FROM python:3.11-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Устанавливаем переменные окружения
# PYTHONUNBUFFERED=1: гарантирует, что выводы print и logging идут сразу в консоль
ENV PYTHONUNBUFFERED=1
# PYTHONDONTWRITEBYTECODE=1: не создавать .pyc файлы
ENV PYTHONDONTWRITEBYTECODE=1

# Обновляем pip и устанавливаем зависимости
# Копируем только requirements.txt сначала, чтобы использовать кеширование Docker
COPY requirements.txt .
# --no-cache-dir - не сохранять кеш pip для уменьшения размера образа
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем исходный код нашего приложения в рабочую директорию
COPY ./src ./src

# Указываем команду для запуска приложения при старте контейнера
# Запускаем бота как модуль через python -m src
CMD ["python", "-m", "src"]