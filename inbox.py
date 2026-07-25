"""Untriaged raw notes — the zero-decision capture surface."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import registry
import store


@dataclass
class Note:
    id: str
    text: str
    created: str


def inbox_dir() -> Path:
    return registry.CONFIG_DIR / "inbox"


def _note_path(note_id: str) -> Path:
    return inbox_dir() / f"{note_id}.md"


def save_note(text: str) -> Note:
    directory = inbox_dir()
    directory.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stem = now.strftime("%Y-%m-%d-%H%M%S")
    note_id, suffix = stem, 1
    while _note_path(note_id).exists():
        note_id = f"{stem}-{suffix}"
        suffix += 1
    _note_path(note_id).write_text(text, encoding="utf-8", newline="\n")
    return Note(id=note_id, text=text, created=now.date().isoformat())


def _chronological_key(path: Path) -> tuple[str, int]:
    # Filenames sort lexicographically, but a collision suffix like "-1"
    # sorts *before* the bare timestamp ("-" < "." in ASCII), which would
    # put a later note ahead of the one it collided with. Sort on the
    # timestamp prefix and suffix number instead so save order is preserved.
    stem = path.stem
    timestamp, suffix = stem[:17], stem[18:]
    return (timestamp, int(suffix) if suffix else 0)


def list_notes() -> list[Note]:
    directory = inbox_dir()
    if not directory.exists():
        return []
    notes = []
    for path in sorted(directory.glob("*.md"), key=_chronological_key):
        notes.append(Note(
            id=path.stem,
            text=path.read_text(encoding="utf-8"),
            created=path.stem[:10],
        ))
    return notes


def delete_note(note_id: str) -> None:
    _note_path(note_id).unlink(missing_ok=True)


def file_note(note_id: str, project_path: Path, title: str, type: str,
              bucket: str) -> store.Task:
    path = _note_path(note_id)
    if not path.exists():
        raise FileNotFoundError(f"unknown note: {note_id}")
    body = path.read_text(encoding="utf-8")
    task = store.create_task(Path(project_path), title, body, type, bucket)
    delete_note(note_id)
    return task
