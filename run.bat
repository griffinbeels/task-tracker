@echo off
REM Task Tracker: create/repair this checkout's environment, then launch quietly.
REM Dependency discovery and offline readiness live in tools\bootstrap.py.
REM This launcher must remain CRLF for cmd label seeking.
setlocal
cd /d "%~dp0"
where uv >nul 2>nul
if errorlevel 1 goto :missing_uv

".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info[:2] != (3, 12))" >nul 2>nul
if not errorlevel 1 goto :runtime_ready
uv venv --python 3.12 --clear .venv
if errorlevel 1 goto :failed

:runtime_ready
REM Shared policy supplies editable claude-console and keeps warm startup offline.
".venv\Scripts\python.exe" tools\bootstrap.py
if errorlevel 1 goto :failed
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:missing_uv
echo ERROR: 'uv' is not on your PATH.
echo Install it from https://docs.astral.sh/uv/ then run this again.
:failed
echo.
echo Task Tracker could not start. Repair the problem above and run.bat again.
pause
exit /b 1
