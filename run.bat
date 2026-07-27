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

REM --- find the shared module's checkout ---
REM  pyproject.toml names claude-console as a dependency but deliberately gives
REM  no path to it. This repo is public: an absolute path there would publish one
REM  machine's home directory, a relative one cannot serve both this checkout and
REM  a worktree four levels under it, and a git URL would install a copy and end
REM  the live-edit property the shared module exists for. So the path is supplied
REM  at install time, here, and the convention is that the two repos sit side by
REM  side. Set CLAUDE_CONSOLE_PATH to override that.
REM
REM  Without this the install fails outright -- uv looks for claude-console on an
REM  index, does not find it, and reports the whole requirement set unsatisfiable.
set "CONSOLE=%CLAUDE_CONSOLE_PATH%"
if not defined CONSOLE if exist "%~dp0..\claude-console\pyproject.toml" set "CONSOLE=%~dp0..\claude-console"
if not defined CONSOLE if exist "%~dp0..\..\..\..\claude-console\pyproject.toml" set "CONSOLE=%~dp0..\..\..\..\claude-console"
if not defined CONSOLE (
  echo ERROR: could not find the claude-console checkout.
  echo It is a required dependency and is installed from a checkout, not an index.
  echo Clone it beside this repo, or point CLAUDE_CONSOLE_PATH at it.
  echo.
  pause
  exit /b 1
)

REM --- keep dependencies in step with pyproject.toml ---
REM  Reads pyproject.toml rather than naming packages, which is what makes the
REM  line above true. It used to list `pywebview pyperclip pyyaml` by hand, and
REM  the moment `claude-console` joined the dependencies that hand-written list
REM  went stale silently: the venv came up without it and the app died on
REM  `import claude_console` before drawing anything.
uv pip install --quiet --python ".venv\Scripts\python.exe" -e "%CONSOLE%" -e .
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
