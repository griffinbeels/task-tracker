"""Relaunch the tracker from source, in a fresh process.

The new process does the shutting down, not this one. Its `singleton.acquire()`
cannot bind the lock port, so it asks the running window to quit, waits for it
to save its geometry and release the port, then takes over — the same handover
a second `run.bat` performs. That is why nothing here closes the current window:
closing first would open a gap in which a failed launch leaves no window at all.
As it stands, a replacement that dies before reaching `acquire()` — an added
dependency that `run.bat` would have installed is the realistic case — never
sends the shutdown, so the existing window simply stays open.

The environment is inherited rather than rebuilt, which is deliberately the
opposite of `launcher.claude_environment()`. Invariant 8 rebuilds the
environment so that a spawned *Claude session* matches one opened by hand; a
tracker replacing itself should instead match the tracker it replaces, venv
`PATH` and all. Sessions the new tracker goes on to spawn are unaffected either
way, because `spawn_claude` rebuilds through `login_environment()` regardless of
what the tracker itself inherited.
"""

import subprocess
import sys
from pathlib import Path

import launcher

# Read via getattr so this module still imports on a non-Windows machine, the
# same way launcher.NEW_CONSOLE is. The flag only exists on Windows.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

APP_ROOT = Path(__file__).parent


def interpreter() -> str:
    """The windowless Python beside the one running us.

    run.bat launches pythonw.exe, so sys.executable is normally already it and
    the sibling lookup finds the same file. It earns its keep on a dev run
    started with python.exe, which would otherwise restart the tracker into a
    console window it never had before.

    `sys.executable` is the venv's path here, not the base interpreter's, even
    though the OS disagrees: uv's `.venv\\Scripts\\pythonw.exe` is a trampoline
    that execs the real interpreter, so Task Manager and `Win32_Process` report
    the running tracker's command line as
    `AppData\\Roaming\\uv\\python\\...\\pythonw.exe app.py` while Python still
    reports `sys.prefix` as the venv. Launching that base path directly would
    not resolve the venv's packages and the replacement would die on
    `import webview` — which is why this reads sys.executable rather than
    anything the process list says. One launch is also two processes, the
    trampoline and its child; the child is the one that binds the lock port.
    """
    windowless = Path(sys.executable).with_name("pythonw.exe")
    return str(windowless) if windowless.exists() else sys.executable


def spawn_replacement() -> subprocess.Popen:
    """Start a new instance, which shuts this one down as it comes up.

    Paths come from `__file__`, not the working directory: the tracker is
    launched from wherever the user happened to be.
    """
    return subprocess.Popen(
        [interpreter(), str(APP_ROOT / "app.py")],
        cwd=str(APP_ROOT),
        creationflags=NO_WINDOW,
        startupinfo=launcher.unfocused_startup(),
    )
