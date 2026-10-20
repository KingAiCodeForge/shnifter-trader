@echo off
REM Call this script from cmd.exe. For PowerShell use the printed command.
if not exist "%~dp0.venv\Scripts\activate.bat" (
    echo ERROR: Environment missing. Run start_shnifter_setup.bat first. 1>&2
    exit /b 1
)
call "%~dp0.venv\Scripts\activate.bat"
exit /b %errorlevel%
