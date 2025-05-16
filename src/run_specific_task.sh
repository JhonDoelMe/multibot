#!/bin/bash

# --- Налаштування ---

# Абсолютний шлях до кореневої директорії вашого проекту (де знаходиться папка `src`)
PROJECT_ROOT_DIR="/home3/anubisua/telegram_bot"

# Абсолютний шлях до директорії віртуального середовища, керованого cPanel Python App
# (де знаходиться папка bin з python та activate)
VENV_DIR="/home3/anubisua/virtualenv/telegram_bot/3.11" # Або просто /home3/anubisua/virtualenv/telegram_bot/, якщо 3.11 - це версія Python всередині

# Абсолютний шлях до інтерпретатора Python у вашому віртуальному середовищі
PYTHON_EXEC="${VENV_DIR}/bin/python3.11" # Або просто "python", якщо VENV_DIR/bin додається в PATH після активації
# Перевірте точну назву файлу: python, python3, python3.11, python3.11_bin

# Скрипт активації віртуального середовища
VENV_ACTIVATE_SCRIPT="${VENV_DIR}/bin/activate"

# Директорія для логів цього скрипта та завдань, які він запускає
# Створюється всередині PROJECT_ROOT_DIR
LOG_DIR="${PROJECT_ROOT_DIR}/logs_cron_tasks"
mkdir -p "$LOG_DIR" # Створюємо директорію, якщо її немає

# Назва скрипта для логування
SCRIPT_BASENAME=$(basename "$0")

# --- Перевірка аргументів ---
if [ -z "$1" ]; then
    # Логуємо помилку в стандартний потік помилок, cron може це кудись перенаправити
    # або в лог самого cron-скрипта, якщо він вже визначений
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME}: ERROR - Task name not provided. Usage: $0 <task_name>" >&2
    # Також запишемо в лог скрипта, якщо LOG_DIR вже доступний
    if [ -d "$LOG_DIR" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME}: ERROR - Task name not provided. Usage: $0 <task_name>" >> "${LOG_DIR}/${SCRIPT_BASENAME}.errors.log"
    fi
    exit 1
fi
TASK_NAME="$1"

# Лог-файл для цього конкретного запуску скрипта (включаючи дії самого скрипта та вивід Python)
# Лог буде перезаписуватися для кожного завдання окремо, щоб не змішувати.
# Якщо потрібно додавати, змініть > на >> у першому echo.
CRON_JOB_LOG_FILE="${LOG_DIR}/${TASK_NAME}_task_run.log" 

# --- Функція для логування ---
log_message() {
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME} (Task: ${TASK_NAME}): $1" >> "$CRON_JOB_LOG_FILE"
}

# --- Початок роботи скрипта ---
# Очищаємо/створюємо лог-файл для цього запуску
echo "-------------------- SCRIPT RUN AT $(date '+%Y-%m-%d %H:%M:%S %Z') --------------------" > "$CRON_JOB_LOG_FILE"
log_message "Script started to execute task: ${TASK_NAME}"

# 1. Перехід в кореневу директорію проекту
log_message "Changing current directory to ${PROJECT_ROOT_DIR}..."
cd "$PROJECT_ROOT_DIR"
if [ $? -ne 0 ]; then
    log_message "ERROR: Failed to change directory to ${PROJECT_ROOT_DIR}. Exiting."
    echo "-------------------- SCRIPT END (ERROR) --------------------" >> "$CRON_JOB_LOG_FILE"
    exit 1
fi
log_message "Current directory: $(pwd)"

# 2. Активація віртуального середовища
if [ -f "$VENV_ACTIVATE_SCRIPT" ]; then
    log_message "Activating virtual environment: ${VENV_ACTIVATE_SCRIPT}..."
    source "$VENV_ACTIVATE_SCRIPT"
    if [ -z "$VIRTUAL_ENV" ]; then # $VIRTUAL_ENV встановлюється скриптом activate
        log_message "WARNING: Virtual environment activation might have failed (VIRTUAL_ENV shell variable not set)."
        log_message "Current PATH: $PATH"
        log_message "Python executable being used (after attempt to source): $(which python || echo 'python not in PATH')"
    else
        log_message "Virtual environment activated: $VIRTUAL_ENV"
        log_message "Python executable in venv (from which python): $(which python)"
        log_message "Using PYTHON_EXEC explicitly: $PYTHON_EXEC"
    fi
else
    log_message "WARNING: Virtual environment activation script not found at ${VENV_ACTIVATE_SCRIPT}. Will attempt to run using the absolute PYTHON_EXEC path."
fi

# 3. Запуск Python-завдання
log_message "Executing Python task with command: ${PYTHON_EXEC} -m src --task=${TASK_NAME}"
log_message "--- Python Task Output (stdout & stderr) START ---"

# Виконуємо команду і логуємо її вивід та код виходу
# `set -e` змусить скрипт вийти, якщо команда завершиться з помилкою
# `set -o pipefail` важливий, якщо вивід передається через pipe (тут не використовується pipe для самої команди)
"$PYTHON_EXEC" -m src --task="$TASK_NAME" >> "$CRON_JOB_LOG_FILE" 2>&1
PYTHON_EXIT_CODE=$?

log_message "--- Python Task Output (stdout & stderr) END ---"

if [ $PYTHON_EXIT_CODE -eq 0 ]; then
    log_message "Python task '${TASK_NAME}' completed successfully (exit code ${PYTHON_EXIT_CODE})."
else
    log_message "ERROR: Python task '${TASK_NAME}' failed with exit code ${PYTHON_EXIT_CODE}."
fi

# 4. Деактивація віртуального середовища (якщо було активоване і команда `deactivate` існує)
if type deactivate > /dev/null 2>&1 && [ -n "$VIRTUAL_ENV" ]; then
    log_message "Deactivating virtual environment."
    deactivate
fi

log_message "Script finished."
echo "-------------------- SCRIPT END (EXIT CODE: ${PYTHON_EXIT_CODE}) --------------------" >> "$CRON_JOB_LOG_FILE"
echo "" >> "$CRON_JOB_LOG_FILE" # Порожній рядок для кращої читабельності між запусками

exit $PYTHON_EXIT_CODE