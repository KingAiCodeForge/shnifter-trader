@echo off
REM Explicitly requested interactive environment shell.
if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo ERROR: Environment missing. Run start_shnifter_setup.bat first. 1>&2
    exit /b 1
)
cmd /k ""%~dp0.venv\Scripts\activate.bat""
exit /b %errorlevel%
