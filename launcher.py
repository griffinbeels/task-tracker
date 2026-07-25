"""Hand selected tasks to a visible Claude Code session."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

import console_input
import store

NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

DEFAULT_LAUNCH = ["claude", "--dangerously-skip-permissions"]

# Variables that mark the current process as running *inside* a Claude session.
# Popen inherits the parent environment, so without stripping these the spawned
# terminal believes it is a nested child: it prints "Transcript saving is off —
# inherited CLAUDE_CODE_CHILD_SESSION marker" and keeps no history. A handed-off
# session is meant to be an ordinary top-level one with full history and memory,
# so it must not inherit whatever session happened to start the tracker.
NESTED_SESSION_VARS = (
    "AI_AGENT",
    "CLAUDECODE",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_EFFORT",
    "CLAUDE_PID",
)


def claude_environment() -> dict[str, str]:
    """This process's environment, fit for a fresh top-level Claude session."""
    environment = {key: value for key, value in os.environ.items()
                   if key not in NESTED_SESSION_VARS}
    environment["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] = "1"
    return environment


def build_prompt(tasks: list[store.Task]) -> str:
    """One line per task: its type, then its body verbatim.

    This is what lands in the session's prompt box, so it reads as the notes
    themselves rather than as a document about them — `FEATURE: <the idea>`,
    one per line, nothing else added. Trailing blank lines are dropped so the
    join is exactly one newline between tasks; nothing else about a body is
    touched, and a body is never trimmed at the front or re-wrapped.
    """
    return "\n".join(f"{task.type}: {task.body.rstrip()}" for task in tasks)


def spawn_claude(project_path: Path,
                 launch: list[str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        launch or DEFAULT_LAUNCH,
        cwd=Path(project_path),
        creationflags=NEW_CONSOLE,
        env=claude_environment(),
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
