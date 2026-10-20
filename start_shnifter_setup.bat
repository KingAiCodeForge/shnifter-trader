@echo off
setlocal
cd /d "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
    py -3.13 -m venv ".venv" || exit /b 1
)
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel || exit /b 1
".venv\Scripts\python.exe" -m pip install -e ".[market,api,gui,dev]" || exit /b 1
echo Shnifter research environment installed. Existing environments were preserved.
exit /b 0
