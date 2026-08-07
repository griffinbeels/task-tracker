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
REM
REM  An unreachable index is NOT a reason to refuse to launch. On 2026-08-03 a
REM  stale DNS answer sent pypi.org to the router, which served its own
REM  certificate, and this step failed on a machine whose venv already had
REM  every dependency installed and working. Offline should launch too.
uv pip install --quiet --python ".venv\Scripts\python.exe" -e "%CONSOLE%" -e .
if not errorlevel 1 goto :dependencies_ready

REM  The index was unreachable, so ask a different question: is the venv ALREADY
REM  coherent? `uv pip check` reads the installed task-tracker's own metadata --
REM  which came from pyproject.toml, so this still hardcodes no package list, for
REM  the reason above -- and names any dependency that is missing. Measured
REM  2026-08-03: exit 0 in 1ms with the index pointed at a dead host, so it
REM  touches no network; exit 1 naming pyperclip once pyperclip was uninstalled.
REM
REM  `uv pip install --offline` was tried here first and is worse: an editable
REM  install REBUILDS both packages, so it needs hatchling from uv's cache and
REM  fails on a cold one even when the venv is perfectly fine.
REM
REM  What this cannot see is a dependency added to pyproject.toml since the last
REM  successful install -- the installed metadata predates it. That case still
REM  launches, and app.py's import guard catches it in a message box.
echo.
echo WARNING: could not reach the package index -- checking what is installed.
uv pip check --python ".venv\Scripts\python.exe"
if errorlevel 1 (
  echo.
  echo ERROR: the index is unreachable AND a dependency is missing, so there
  echo is nothing here to run. Reconnect and run this again.
  echo.
  echo If you believe you ARE online, a stale DNS answer looks exactly like
  echo this -- run this in PowerShell, then try again:
  echo     Clear-DnsClientCache
  echo.
  pause
  exit /b 1
)
echo Launching with the dependencies already installed.

REM  This file must stay CRLF. cmd seeks a label by BYTE OFFSET assuming CRLF,
REM  so the `goto` above resumes mid-line in an LF copy and runs garbage. The
REM  flat shape is deliberate too: nesting the retry inside the first failure
REM  block instead swallows `exit /b 1`, and the launcher reports success on
REM  the one path where nothing can run. Both measured 2026-08-03.
:dependencies_ready

REM --- launch ---
REM  pythonw.exe, so the tracker opens as a window with no console
REM  hanging around beside it. Startup failures still surface: app.py
REM  reports them in a message box precisely because there is no console.
echo Starting Task Tracker...
start "" ".venv\Scripts\pythonw.exe" app.py

endlocal
