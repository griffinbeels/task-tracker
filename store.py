"""On-disk task format and .tasks/ directory operations."""

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import yaml

BUCKETS = ("now", "next", "someday")
STATUSES = ("open", "in-progress", "done")

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


@dataclass
class Task:
    id: int
    title: str
    type: str
    bucket: str
    status: str
    order: int
    created: str
    started: str | None
    done: str | None
    body: str
    path: Path | None = field(default=None, compare=False)


def task_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50].rstrip("-")


def render_task(task: Task) -> str:
    meta = {
        "id": task.id,
        "title": task.title,
        "type": task.type,
        "bucket": task.bucket,
        "status": task.status,
        "order": task.order,
        "created": task.created,
        "started": task.started,
        "done": task.done,
    }
    frontmatter = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)
    return f"---\n{frontmatter}---\n\n{task.body}"


def parse_task(text: str, path: Path | None = None) -> Task:
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ValueError(f"missing frontmatter in {path or '<string>'}")
    meta = yaml.safe_load(match.group(1)) or {}
    body = text[match.end():]
    if body.startswith("\n"):
        body = body[1:]
    return Task(
        id=int(meta["id"]),
        title=str(meta["title"]),
        type=str(meta["type"]),
        bucket=str(meta["bucket"]),
        status=str(meta["status"]),
        order=int(meta.get("order") or 0),
        created=str(meta["created"]),
        started=str(meta["started"]) if meta.get("started") else None,
        done=str(meta["done"]) if meta.get("done") else None,
        body=body,
        path=path,
    )


GITIGNORE_BODY = "*\n"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def tasks_dir(project_path: Path) -> Path:
    return Path(project_path) / ".tasks"


def ensure_tasks_dir(project_path: Path, tracked: bool = False) -> Path:
    root = tasks_dir(project_path)
    (root / "open").mkdir(parents=True, exist_ok=True)
    (root / "done").mkdir(parents=True, exist_ok=True)
    set_tracked(project_path, tracked)
    return root


def set_tracked(project_path: Path, tracked: bool) -> None:
    ignore = tasks_dir(project_path) / ".gitignore"
    if tracked:
        ignore.unlink(missing_ok=True)
    else:
        ignore.write_text(GITIGNORE_BODY, encoding="utf-8", newline="\n")


def _task_files(project_path: Path, include_done: bool) -> list[Path]:
    root = tasks_dir(project_path)
    folders = ["open", "done"] if include_done else ["open"]
    files: list[Path] = []
    for folder in folders:
        files.extend(sorted((root / folder).glob("*.md")))
    return files


def read_tasks(project_path: Path, include_done: bool = True) -> tuple[list[Task], list[str]]:
    """Parse every task file, collecting any that fail to parse rather than raising.

    A single malformed file must cost one row, not the whole app — get_state
    fans out over every project, so a raise here blanks the entire window.
    Caught broadly (not just ValueError/KeyError/OSError) because parse_task
    can also fail with yaml.YAMLError (malformed YAML, e.g. an unclosed quote
    or a tab used for indentation) or TypeError (e.g. `id:` given as a list
    instead of a scalar) — every path skipped this way is reported back to
    the caller via `unreadable`, so nothing is hidden by catching broadly.
    """
    tasks, unreadable = [], []
    for path in _task_files(project_path, include_done):
        try:
            tasks.append(parse_task(path.read_text(encoding="utf-8"), path))
        except Exception:
            unreadable.append(str(path))
    return tasks, unreadable


def list_tasks(project_path: Path, include_done: bool = True) -> list[Task]:
    return read_tasks(project_path, include_done)[0]


def next_task_id(project_path: Path) -> int:
    ids = [task.id for task in list_tasks(project_path, include_done=True)]
    return max(ids, default=0) + 1


def create_task(project_path: Path, title: str, body: str, type: str,
                bucket: str = "now") -> Task:
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket: {bucket}")
    if not tasks_dir(project_path).exists():
        ensure_tasks_dir(project_path, tracked=False)
    siblings = [t for t in list_tasks(project_path, include_done=False) if t.bucket == bucket]
    task = Task(
        id=next_task_id(project_path),
        title=title,
        type=type,
        bucket=bucket,
        status="open",
        order=len(siblings),
        created=_today(),
        started=None,
        done=None,
        body=body,
    )
    task.path = tasks_dir(project_path) / "open" / f"{task.id:04d}-{task_slug(title)}.md"
    return save_task(task)


_ATTACHMENT_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

_DATA_URL = re.compile(r"\Adata:([^;,]+);base64,(.*)\Z", re.DOTALL)


def attachments_dir(project_path: Path) -> Path:
    return tasks_dir(project_path) / "attachments"


def save_attachment(project_path: Path, data_url: str) -> Path:
    """Decode a pasted `data:image/...;base64,...` URL and write it to disk.

    Validates and decodes before touching the directory at all, so a
    malformed URL never leaves an empty attachments/ folder behind as a
    side effect of a raise.
    """
    match = _DATA_URL.match(data_url)
    if match is None:
        raise ValueError("not a data URL")
    mime, payload = match.group(1), match.group(2)
    extension = _ATTACHMENT_EXTENSIONS.get(mime)
    if extension is None:
        raise ValueError(f"unsupported attachment type: {mime}")
    # validate=True is load-bearing: without it, b64decode silently drops
    # characters outside the base64 alphabet instead of raising, which would
    # turn a garbled paste into a garbage file instead of a clear error.
    data = base64.b64decode(payload, validate=True)

    # A project registered before .tasks/ exists must still get its
    # .gitignore — same reason create_task does this: .tasks/ is untracked
    # by default so a pasted screenshot never gets auto-published alongside
    # a public repo's tracked files.
    if not tasks_dir(project_path).exists():
        ensure_tasks_dir(project_path, tracked=False)
    directory = attachments_dir(project_path)
    directory.mkdir(parents=True, exist_ok=True)
    # Same collision scheme as inbox.save_note: a UTC timestamp stem, with a
    # -1, -2... suffix if another attachment already landed the same second.
    stem = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M%S")
    name, suffix = stem, 1
    while (directory / f"{name}{extension}").exists():
        name = f"{stem}-{suffix}"
        suffix += 1
    path = directory / f"{name}{extension}"
    path.write_bytes(data)
    return path


def save_task(task: Task) -> Task:
    if task.path is None:
        raise ValueError("task has no path")
    task.path.write_text(render_task(task), encoding="utf-8", newline="\n")
    return task


def complete_task(task: Task) -> Task:
    if task.path is None:
        raise ValueError("task has no path")
    project_path = task.path.parent.parent.parent
    task.status = "done"
    task.done = task.done or _today()
    destination = tasks_dir(project_path) / "done" / task.path.name
    task.path.unlink(missing_ok=True)
    task.path = destination
    return save_task(task)


def reorder_bucket(project_path: Path, bucket: str, ordered_ids: list[int]) -> None:
    by_id = {t.id: t for t in list_tasks(project_path, include_done=False)}
    for position, task_id in enumerate(ordered_ids):
        task = by_id.get(task_id)
        if task is None or task.bucket != bucket:
            continue
        task.order = position
        save_task(task)
