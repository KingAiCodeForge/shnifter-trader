@echo off
REM Compatibility wrapper; never removes an existing environment.
call "%~dp0start_shnifter_setup.bat" %*
exit /b %errorlevel%
