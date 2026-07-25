"""Hand selected tasks to a visible Claude Code session."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

import store

NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)


def build_prompt(tasks: list[store.Task]) -> str:
    """Concatenate task bodies verbatim. Nothing is appended."""
    sections = [f"## {t.type} {t.id} - {t.title}\n\n{t.body}" for t in tasks]
    return "\n\n".join(sections)


def spawn_claude(project_path: Path, launch: list[str] | None = None) -> None:
    subprocess.Popen(
        launch or ["claude"],
        cwd=Path(project_path),
        creationflags=NEW_CONSOLE,
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
