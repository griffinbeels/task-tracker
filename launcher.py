"""Hand selected tasks to a visible Claude Code session."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

import console_input
import store
import user_environment

NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

DEFAULT_LAUNCH = ["claude", "--dangerously-skip-permissions"]

# Show the new console, but do not make it the active window (SW_SHOWNOACTIVATE
# rather than the default SW_SHOWNORMAL). Hand-off is something you trigger and
# then carry on with: a window that grabs focus swallows whatever you type next
# and puts it into a session you were not looking at. Nothing here needs focus
# — console_input writes to the console's input buffer, which does not require
# the window to be active.
SW_SHOWNOACTIVATE = 4


def unfocused_startup() -> "subprocess.STARTUPINFO":
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = SW_SHOWNOACTIVATE
    return startup


def claude_environment() -> dict[str, str]:
    """The environment a session you opened by hand would have.

    Not this process's environment with the awkward parts removed — the
    tracker is usually started from a Claude session, and inheriting from it
    is the whole problem. See user_environment for why this is rebuilt rather
    than filtered.
    """
    return user_environment.login_environment()


def build_prompt(tasks: list[store.Task]) -> str:
    """One line per task: its type, then its body verbatim.

    This is what lands in the session's prompt box, so it reads as the notes
    themselves rather than as a document about them — `FEATURE: <the idea>`,
    one per line, nothing else added. Trailing blank lines are dropped so the
    join is exactly one newline between tasks; nothing else about a body is
    touched, and a body is never trimmed at the front or re-wrapped.

    A task with no body falls back to its title, because `FEATURE: ` on its own
    hands over nothing at all. That is still verbatim — it selects a different
    field of the task, it does not edit either one.
    """
    return "\n".join(f"{task.type}: {task.body.rstrip() or task.title}"
                     for task in tasks)


def copy_prompt(tasks: list[store.Task]) -> str:
    """Put the hand-off text on the clipboard, and change nothing else.

    Deliberately not a slice of hand_off(): no session is opened and no task is
    marked in-progress. Copying is a cheap gesture — the text might be going to
    an already-open session, a chat, or nowhere — so it commits you to nothing.
    Sharing build_prompt with hand_off is the point, though: the two ways of
    getting a task into Claude cannot then drift into two different formats.
    """
    prompt = build_prompt(tasks)
    pyperclip.copy(prompt)
    return prompt


def spawn_claude(project_path: Path,
                 launch: list[str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        launch or DEFAULT_LAUNCH,
        cwd=Path(project_path),
        creationflags=NEW_CONSOLE,
        env=claude_environment(),
        startupinfo=unfocused_startup(),
    )


def hand_off(project_path: Path, tasks: list[store.Task],
             launch: list[str] | None = None) -> str:
    """Open a session in the project with the selected tasks in its prompt box.

    The text is typed into the new window rather than submitted for you: it
    arrives as an editable prompt, so you can add to it or think again before
    sending. The clipboard copy is the backup for a session that took too long
    to come up, and the reason typing is allowed to fail silently.

    With nothing selected this is simply "open Claude in this project" —
    nothing is typed, and the clipboard is left alone.
    """
    prompt = build_prompt(tasks)
    session = spawn_claude(project_path, launch)
    if prompt:
        pyperclip.copy(prompt)
        console_input.paste_when_ready(session.pid, prompt)

    today = datetime.now(timezone.utc).date().isoformat()
    for task in tasks:
        task.status = "in-progress"
        task.started = task.started or today
        store.save_task(task)

    return prompt
