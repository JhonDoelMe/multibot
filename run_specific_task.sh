#!/bin/bash

# Shell скрипт для запуску Python-завдань через cron
# Він активує віртуальне середовище, завантажує .env та запускає src/__main__.py з відповідним завданням.

# --- Налаштування ---
PROJECT_ROOT_DIR="/home3/anubisua/telegram_bot"
VENV_DIR="/home3/anubisua/virtualenv/telegram_bot/3.11"
PYTHON_EXEC="${VENV_DIR}/bin/python3.11"
VENV_ACTIVATE_SCRIPT="${VENV_DIR}/bin/activate"
LOG_DIR="${PROJECT_ROOT_DIR}/logs_cron_tasks"
mkdir -p "$LOG_DIR"
SCRIPT_BASENAME=$(basename "$0")

# --- Перевірка аргументів ---
if [ -z "$1" ]; then
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME}: ERROR - Task name not provided. Usage: $0 <task_name>" >&2
    if [ -d "$LOG_DIR" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME}: ERROR - Task name not provided. Usage: $0 <task_name>" >> "${LOG_DIR}/${SCRIPT_BASENAME}.errors.log"
    fi
    exit 1
fi
TASK_NAME="$1"
CRON_JOB_LOG_FILE="${LOG_DIR}/${TASK_NAME}_task_runs.log"

log_action() {
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME} (Task: ${TASK_NAME}): $1" >> "$CRON_JOB_LOG_FILE"
}

echo "-------------------- TASK RUN AT $(date '+%Y-%m-%d %H:%M:%S %Z') --------------------" >> "$CRON_JOB_LOG_FILE"
log_action "Script instance started to execute task: '${TASK_NAME}'"

# 1. Перехід в кореневу директорію проекту
log_action "Changing current directory to ${PROJECT_ROOT_DIR}..."
cd "$PROJECT_ROOT_DIR"
if [ $? -ne 0 ]; then
    log_action "FATAL ERROR: Failed to change directory to ${PROJECT_ROOT_DIR}. Exiting."
    echo "-------------------- SCRIPT END (FATAL ERROR) --------------------" >> "$CRON_JOB_LOG_FILE"
    exit 1
fi
log_action "Current directory: $(pwd)"

# 2. Явне завантаження змінних з .env файлу (якщо він існує)
ENV_FILE="${PROJECT_ROOT_DIR}/.env"
if [ -f "$ENV_FILE" ]; then
    log_action "Sourcing environment variables from ${ENV_FILE}..."
    # Використовуємо `set -a` для автоматичного експорту всіх змінних, визначених у .env
    # та `set +a` для вимкнення цього режиму після.
    # Переконуємося, що .env файл не містить складних команд, а лише пари КЛЮЧ=ЗНАЧЕННЯ.
    # Видаляємо коментарі та порожні рядки перед сорсингом.
    # Важливо: цей метод може мати проблеми з багаторядковими змінними або спеціальними символами.
    # Для простих .env файлів він має працювати.
    # Альтернатива - використовувати `export $(grep -v '^#' $ENV_FILE | xargs)` але це теж має обмеження.
    # Найпростіший варіант, якщо .env простий:
    set -a # Automatically export all variables
    source "$ENV_FILE"
    set +a # Disable auto-export
    log_action ".env file sourced. DATABASE_URL from env (if set): $DATABASE_URL" 
    # $DATABASE_URL тут покаже значення, яке тепер є в оточенні bash
else
    log_action "WARNING: .env file not found at ${ENV_FILE}. Python script will rely on globally set environment variables or defaults."
fi

# 3. Активація віртуального середовища
if [ -f "$VENV_ACTIVATE_SCRIPT" ]; then
    log_action "Activating virtual environment: ${VENV_ACTIVATE_SCRIPT}..."
    source "$VENV_ACTIVATE_SCRIPT"
    if [ -z "$VIRTUAL_ENV" ]; then
        log_action "WARNING: Virtual environment activation might have failed (VIRTUAL_ENV shell variable not set by activate script)."
    else
        log_action "Virtual environment activated: $VIRTUAL_ENV"
    fi
else
    log_action "WARNING: Virtual environment activation script not found at ${VENV_ACTIVATE_SCRIPT}."
fi

# 4. Запуск Python-завдання
log_action "Executing Python task command: ${PYTHON_EXEC} -m src --task=${TASK_NAME}"
log_action "--- Python Task Output (stdout & stderr) START ---"

"$PYTHON_EXEC" -m src --task="$TASK_NAME" >> "$CRON_JOB_LOG_FILE" 2>&1
PYTHON_TASK_EXIT_CODE=$?

log_action "--- Python Task Output (stdout & stderr) END ---"

if [ $PYTHON_TASK_EXIT_CODE -eq 0 ]; then
    log_action "Python task '${TASK_NAME}' completed successfully (exit code ${PYTHON_TASK_EXIT_CODE})."
else
    log_action "ERROR: Python task '${TASK_NAME}' failed with exit code ${PYTHON_TASK_EXIT_CODE}. Review the output above."
fi

# 5. Деактивація віртуального середовища
if type deactivate > /dev/null 2>&1 && [ -n "$VIRTUAL_ENV" ]; then
    log_action "Deactivating virtual environment."
    deactivate
fi

log_action "Script instance finished with overall exit code ${PYTHON_TASK_EXIT_CODE}."
echo "-------------------- SCRIPT END (EXIT CODE: ${PYTHON_TASK_EXIT_CODE}) --------------------" >> "$CRON_JOB_LOG_FILE"
echo "" >> "$CRON_JOB_LOG_FILE"

exit $PYTHON_TASK_EXIT_CODE
# Кінець скрипта