@echo off
REM Устанавливаем кодировку консоли на UTF-8
chcp 65001 > nul
ECHO Code page set to 65001 (UTF-8)

REM --- Виртуальное окружение не используется ---
ECHO No virtual environment activation attempted. Using system Python.

REM Запускаем бота, ПЕРЕНАПРАВЛЯЯ Поток Ошибок (stderr) в Стандартный Вывод (stdout)
ECHO Starting bot (python -m src 2^>^&1)...
python -m src 2>&1

REM Пауза СРАЗУ ПОСЛЕ попытки запуска Python, чтобы увидеть ЛЮБОЙ вывод
ECHO === Pausing after Python command ===
ECHO Python command finished or errored out. Check output above.
ECHO Press any key to exit...
pause