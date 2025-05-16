#!/bin/bash

# Путь к интерпретатору Python в виртуальном окружении
PYTHON_EXEC="/home3/anubisua/virtualenv/telegram_bot/3.11/bin/python3.11"
# Директория, где лежит бот
BOT_DIR="/home3/anubisua/telegram_bot"
# Лог-файл для вывода бота, запущенного через этот скрипт
LOG_FILE="$BOT_DIR/cron_bot.log"
# Команда для поиска процесса
PGREP_PATTERN="$PYTHON_EXEC -m src"

# Ищем процесс
pgrep -f "$PGREP_PATTERN" > /dev/null

# $? содержит код возврата последней команды (0 - если pgrep нашел процесс, не 0 - если не нашел)
if [ $? -ne 0 ]; then
  echo "$(date): Bot process not found. Starting..." >> $LOG_FILE
  cd "$BOT_DIR" || exit 1 # Переходим в директорию или выходим, если не удалось
  # Запускаем через nohup в фоне, перенаправляя вывод в лог
  nohup "$PYTHON_EXEC" -m src >> $LOG_FILE 2>&1 &
# else
  # Если нужно логировать, что процесс уже работает (для отладки Cron)
  # echo "$(date): Bot process is running." >> $LOG_FILE
fi

exit 0