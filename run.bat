@echo off
REM ============================================================
REM  Task Tracker  --  run from source.
REM
REM  Creates the venv and installs dependencies on first run, so
REM  a fresh clone needs nothing on PATH but `uv`.
REM
REM  Running this while a window is already open shuts that one
REM  down first and takes over, so you always end up with exactly
REM  one window, running the current code. Nothing to stop by
REM  hand -- just run it again after making a change.
REM
REM  Usage:
REM    run.bat
REM ============================================================
setlocal
cd /d "%~dp0"

REM --- uv is required ---
where uv >nul 2>nul
if errorlevel 1 (
  echo ERROR: 'uv' is not on your PATH.
  echo Install it from https://docs.astral.sh/uv/ then run this again.
  echo.
  pause
  exit /b 1
)

REM --- create the venv on first run (3.12; system Python is too new) ---
if not exist ".venv\Scripts\pythonw.exe" (
  echo Creating the virtual environment ^(Python 3.12^)...
  uv venv --python 3.12 .venv
  if errorlevel 1 (
    echo.
    echo ERROR: could not create the virtual environment.
    pause
    exit /b 1
  )
)

REM --- keep dependencies in step with pyproject.toml ---
echo Syncing dependencies...
uv pip install --quiet --python ".venv\Scripts\python.exe" pywebview pyperclip pyyaml
if errorlevel 1 (
  echo.
  echo ERROR: could not install dependencies.
  pause
  exit /b 1
)

REM --- launch ---
REM  pythonw.exe, so the tracker opens as a window with no console
REM  hanging around beside it. Startup failures still surface: app.py
REM  reports them in a message box precisely because there is no console.
echo Starting Task Tracker...
start "" ".venv\Scripts\pythonw.exe" app.py

endlocal
