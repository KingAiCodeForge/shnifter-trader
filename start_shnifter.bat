@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Environment missing. Run start_shnifter_setup.bat first. 1>&2
    exit /b 1
)
".venv\Scripts\python.exe" "%~dp0Multi_Model_Trading_Bot.py" %*
exit /b %errorlevel%
