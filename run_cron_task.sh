#!/bin/bash

# --- Налаштування шляхів та імен ---

# Абсолютний шлях до кореневої директорії вашого проекту
PROJECT_ROOT_DIR="/home3/anubisua/virtualenv/telegram_bot"

# Абсолютний шлях до інтерпретатора Python у вашому віртуальному середовищі
# Використовуйте той, що відповідає вашому venv (python або python3.11_bin)
PYTHON_EXEC="${PROJECT_ROOT_DIR}/3.11/bin/python" 
# Або: PYTHON_EXEC="${PROJECT_ROOT_DIR}/3.11/bin/python3.11_bin"

# Назва скрипта для логування
SCRIPT_NAME="run_cron_task.sh"

# Директорія для логів (має існувати, або скрипт спробує її створити)
LOG_DIR="${PROJECT_ROOT_DIR}/logs" 

# Лог-файл для цього cron-скрипта
CRON_SCRIPT_LOG_FILE="${LOG_DIR}/${SCRIPT_NAME}.log"

# --- Перевірка аргументів ---
if [ -z "$1" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_NAME}: ERROR - Task name not provided. Usage: $0 <task_name>" >> "$CRON_SCRIPT_LOG_FILE"
    exit 1
fi
TASK_NAME="$1"

# Лог-файл для виводу конкретного завдання Python
PYTHON_TASK_LOG_FILE="${LOG_DIR}/${TASK_NAME}_task.log"

# --- Функція для логування дій цього скрипта ---
log_action() {
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_NAME} (Task: ${TASK_NAME}): $1" >> "$CRON_SCRIPT_LOG_FILE"
}

# --- Створення директорії для логів, якщо її немає ---
if [ ! -d "$LOG_DIR" ]; then
    mkdir -p "$LOG_DIR"
    if [ $? -eq 0 ]; then
        log_action "Log directory created: $LOG_DIR"
    else
        # Не можемо логувати в файл, якщо не створили директорію, виводимо в stderr
        echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_NAME}: CRITICAL - Failed to create log directory $LOG_DIR. Please create it manually." >&2
        # Продовжуємо, сподіваючись, що логування в файл завдання спрацює, якщо PROJECT_ROOT_DIR доступний для запису
    fi
fi

log_action "Script started."

# --- Перехід в кореневу директорію проекту ---
cd "$PROJECT_ROOT_DIR"
if [ $? -ne 0 ]; then
    log_action "ERROR: Failed to change directory to ${PROJECT_ROOT_DIR}. Exiting."
    exit 1
fi
log_action "Changed current directory to ${PROJECT_ROOT_DIR}."

# --- Активація віртуального середовища ---
VENV_ACTIVATE_SCRIPT="${PROJECT_ROOT_DIR}/3.11/bin/activate"
if [ -f "$VENV_ACTIVATE_SCRIPT" ]; then
    log_action "Activating virtual environment: ${VENV_ACTIVATE_SCRIPT}"
    source "$VENV_ACTIVATE_SCRIPT"
    if [ -z "$VIRTUAL_ENV" ]; then
        log_action "WARNING: Virtual environment activation might have failed (VIRTUAL_ENV not set)."
    else
        log_action "Virtual environment activated: $VIRTUAL_ENV"
    fi
else
    log_action "WARNING: Virtual environment activation script not found at ${VENV_ACTIVATE_SCRIPT}. Attempting to run with specified Python executable directly."
fi

# --- Запуск Python-завдання ---
log_action "Executing Python task: $PYTHON_EXEC -m src --task=$TASK_NAME"
log_action "Python task output will be logged to: $PYTHON_TASK_LOG_FILE"

# Запускаємо Python-скрипт, перенаправляючи його stdout та stderr у його власний лог-файл
# Використовуємо >> для додавання в лог, а не перезапису при кожному запуску
"$PYTHON_EXEC" -m src --task="$TASK_NAME" >> "$PYTHON_TASK_LOG_FILE" 2>&1
PYTHON_EXIT_CODE=$?

if [ $PYTHON_EXIT_CODE -eq 0 ]; then
    log_action "Python task '$TASK_NAME' completed successfully."
else
    log_action "ERROR: Python task '$TASK_NAME' failed with exit code $PYTHON_EXIT_CODE. Check ${PYTHON_TASK_LOG_FILE} for details."
fi

# --- Деактивація віртуального середовища, якщо воно було активоване ---
# `deactivate` команда доступна тільки якщо `source activate` був успішним і змінив середовище
if type deactivate > /dev/null 2>&1 && [ -n "$VIRTUAL_ENV" ]; then
    log_action "Deactivating virtual environment."
    deactivate
fi

log_action "Script finished."
echo "----------------------------------------" >> "$CRON_SCRIPT_LOG_FILE" # Розділювач

exit $PYTHON_EXIT_CODE