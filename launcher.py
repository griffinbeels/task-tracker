"""Hand selected tasks to a visible Claude Code session."""

import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

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
    """Concatenate task bodies verbatim. Nothing is appended."""
    sections = [f"## {t.type} {t.id} - {t.title}\n\n{t.body}" for t in tasks]
    return "\n\n".join(sections)


def spawn_claude(project_path: Path, launch: list[str] | None = None) -> None:
    subprocess.Popen(
        launch or DEFAULT_LAUNCH,
        cwd=Path(project_path),
        creationflags=NEW_CONSOLE,
        env=claude_environment(),
    )


def hand_off(project_path: Path, tasks: list[store.Task],
             launch: list[str] | None = None) -> str:
    prompt = build_prompt(tasks)
    spawn_claude(project_path, launch)

    pyperclip.copy(prompt)
    today = datetime.now(timezone.utc).date().isoformat()
    for task in tasks:
        task.status = "in-progress"
        task.started = task.started or today
        store.save_task(task)

    return prompt
