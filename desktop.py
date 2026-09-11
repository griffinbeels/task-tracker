"""The tracker's small native boundary; safe to import before GUI dependencies.

Task/file validation belongs to the calling module. These functions only hand
validated targets to the OS and surface errors when no app window exists yet.
"""

import os
import subprocess
import sys
from pathlib import Path


def shortcuts() -> dict[str, str]:
    """The primary keyboard modifier, shared with the page and notices."""
    if sys.platform == "darwin":
        return {"modifier": "meta", "label": "Command"}
    return {"modifier": "ctrl", "label": "Ctrl"}


def open_target(target: str | Path) -> None:
    """Open an already validated file or URL with its native association."""
    if sys.platform == "win32":
        os.startfile(str(target))
        return
    opener = "/usr/bin/open" if sys.platform == "darwin" else "xdg-open"
    try:
        subprocess.run([opener, str(target)], check=True, capture_output=True,
                       text=True, timeout=15)
    except subprocess.CalledProcessError as error:
        raise OSError(error.stderr.strip() or f"Could not open {target}") from error


def report_fatal(message: str) -> None:
    """Show startup errors without depending on pywebview or a terminal."""
    if sys.stderr is not None:
        print(message, file=sys.stderr)
    try:
        if sys.platform == "win32":
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, message, "Task Tracker", 0x10)
        elif sys.platform == "darwin":
            # argv is data: a filename or exception may contain AppleScript
            # punctuation and must never become part of the script itself.
            subprocess.run(
                ["/usr/bin/osascript", "-", message],
                input='on run argv\n display alert "Task Tracker" message '
                      '(item 1 of argv) as critical\nend run\n',
                text=True, capture_output=True, check=True,
            )
    except (AttributeError, OSError, subprocess.SubprocessError):
        # stderr remains available to the source launcher and app-bundle log.
        pass
