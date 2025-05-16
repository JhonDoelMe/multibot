#!/bin/bash

# Shell скрипт для запуску Python-завдань через cron
# Він активує віртуальне середовище та запускає src/__main__.py з відповідним завданням,
# ізолюючи його файлове логування від основного логу бота.

# --- Налаштування шляхів та імен ---
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

# Лог-файл для stdout/stderr Python-завдання ТА логів самого bash-скрипта
# Усі логи, пов'язані з одним запуском завдання, будуть тут.
TASK_EXECUTION_LOG_FILE="${LOG_DIR}/${TASK_NAME}_execution.log"

# Ім'я файлу, куди буде писати RotatingFileHandler всередині Python-завдання
PYTHON_TASK_SPECIFIC_FILE_LOG="${LOG_DIR}/${TASK_NAME}_python_file.log"

# --- Функція для логування дій цього bash-скрипта ---
log_action() {
    echo "$(date '+%Y-%m-%d %H:%M:%S %Z') - ${SCRIPT_BASENAME} (Task: ${TASK_NAME}): $1" >> "$TASK_EXECUTION_LOG_FILE"
}

# --- Початок роботи скрипта ---
echo "-------------------- TASK RUN AT $(date '+%Y-%m-%d %H:%M:%S %Z') --------------------" >> "$TASK_EXECUTION_LOG_FILE"
log_action "Script instance started to execute task: '${TASK_NAME}'"
log_action "Python FileHandler will write to: ${PYTHON_TASK_SPECIFIC_FILE_LOG}"
log_action "Shell script actions and Python stdout/stderr will be in: ${TASK_EXECUTION_LOG_FILE}"


# 1. Перехід в кореневу директорію проекту
log_action "Changing current directory to ${PROJECT_ROOT_DIR}..."
cd "$PROJECT_ROOT_DIR"
if [ $? -ne 0 ]; then
    log_action "FATAL ERROR: Failed to change directory to ${PROJECT_ROOT_DIR}. Exiting."
    echo "-------------------- SCRIPT END (FATAL ERROR) --------------------" >> "$TASK_EXECUTION_LOG_FILE"
    exit 1
fi
log_action "Successfully changed current directory to: $(pwd)"

# 2. Активація віртуального середовища
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

# 3. Встановлюємо змінну оточення LOG_FILENAME для Python-скрипта
export LOG_FILENAME="${PYTHON_TASK_SPECIFIC_FILE_LOG}"
log_action "Exported LOG_FILENAME=${LOG_FILENAME} for Python process."

# 4. Запуск Python-завдання
log_action "Executing Python task command: ${PYTHON_EXEC} -m src --task=${TASK_NAME}"
log_action "--- Python Task Output (stdout & stderr) START ---"

# Виконуємо Python-завдання. Його stdout та stderr будуть додані до $TASK_EXECUTION_LOG_FILE
"$PYTHON_EXEC" -m src --task="$TASK_NAME" >> "$TASK_EXECUTION_LOG_FILE" 2>&1
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

# Скасовуємо експорт змінної, хоча для cron-сесії це зазвичай не потрібно
unset LOG_FILENAME

log_action "Script instance finished with overall exit code ${PYTHON_TASK_EXIT_CODE}."
echo "-------------------- SCRIPT END (EXIT CODE: ${PYTHON_TASK_EXIT_CODE}) --------------------" >> "$TASK_EXECUTION_LOG_FILE"
echo "" >> "$TASK_EXECUTION_LOG_FILE"

exit $PYTHON_TASK_EXIT_CODE
# Кінець скрипта