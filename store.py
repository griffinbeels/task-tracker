"""On-disk task format and .tasks/ directory operations."""

import base64
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

import yaml

BUCKETS = ("now", "next", "someday")
STATUSES = ("open", "in-progress", "done")

# The colours Claude Code's /color command accepts, minus `default` — every
# task has a real colour, so there is never a reason to send it.
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange",
                 "pink", "cyan")

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
    # A group is its name: tasks sharing this string within one project are one
    # group, and there is no id or registry that could dangle. Declared here,
    # after the last field without a default, so every existing construction
    # site keeps working untouched. See groups.py.
    group: str | None = None
    # A colour Claude Code's /color command accepts, for a session spawned off
    # this task to identify itself by. Normalised in __post_init__ rather than
    # by parse_task and create_task separately: one rule in one place means a
    # Task built anywhere — parsed, created, or hand-constructed in a test —
    # always carries a legal value, so no downstream caller has to defend
    # against "" or against a typo hand-edited into a task file.
    color: str = ""
    path: Path | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.color not in CLAUDE_COLORS:
            # Deterministic, not random: reads never write and no migration
            # sweep runs, so the same id must derive the same colour every
            # time it is parsed, and eight consecutive ids must land on eight
            # different colours, which randomness can't promise.
            self.color = CLAUDE_COLORS[self.id % len(CLAUDE_COLORS)]


def task_slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug[:50].rstrip("-")


def render_task(task: Task) -> str:
    meta = {
        "id": task.id,
        "title": task.title,
        "type": task.type,
        "color": task.color,
        "bucket": task.bucket,
        "group": task.group,
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
        # A missing key, an explicit null and an empty string all mean the same
        # thing — this task is not in a group. A group with no name has no
        # identity, so "" can never be a real value.
        group=str(meta["group"]) if meta.get("group") else None,
        # __post_init__ replaces anything illegal, so the only job here is to
        # not raise on a missing key or a non-string value.
        color=str(meta.get("color") or ""),
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
                bucket: str = "now", color: str = "") -> Task:
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
        color=color,
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


_EXTENSION_MIMES = {ext: mime for mime, ext in _ATTACHMENT_EXTENSIONS.items()}


def resolve_attachment(project_path: Path, reference: str) -> Path:
    """Turn a body's image reference into a path, or refuse.

    The reference comes out of a task body, which is a hand-editable file, and
    it is handed to us by the renderer. So it is untrusted input on a path that
    ends in "read these bytes" and "hand this to the shell" — anything outside
    the project's own attachments folder is refused, as is any extension we do
    not write ourselves. Without the extension check, a body could point
    open_attachment at an .exe and the click would run it.
    """
    path = Path(url2pathname(urlparse(reference).path)
                if reference.startswith("file:") else reference)
    directory = attachments_dir(project_path).resolve()
    try:
        resolved = path.resolve(strict=True)
    except OSError as error:
        raise ValueError(f"no such attachment: {reference}") from error
    if directory not in resolved.parents:
        raise ValueError(f"not inside this project's attachments: {reference}")
    if resolved.suffix.lower() not in _EXTENSION_MIMES:
        raise ValueError(f"not an image this app writes: {resolved.suffix}")
    return resolved


def attachment_data_url(project_path: Path, reference: str) -> str:
    """An attachment as a `data:` URL, which is the only form that renders.

    A `file://` URL is a perfectly valid URL and the sanitiser leaves it alone
    in WYSIWYG mode — the browser simply declines to load a `file://`
    subresource into a `file://` document, so the image comes out as a broken
    glyph with its alt text. `data:` is exempt for <img>, so the bytes travel
    inline. This is display only: the body on disk keeps the path, so it stays
    short and a handed-off session can still open the real file.
    """
    path = resolve_attachment(project_path, reference)
    mime = _EXTENSION_MIMES[path.suffix.lower()]
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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


def restore_task(task: Task) -> Task:
    """Move a completed task back into open/, at the end of its bucket.

    The inverse of complete_task. `bucket` is untouched because completion
    never touched it — the task still remembers where it lived, so it returns
    there. It lands last rather than reclaiming its old `order`: the tasks it
    sat among have moved on without it, and re-inserting it into the middle of
    a list the user has since reordered is a change nobody asked for.
    """
    if task.path is None:
        raise ValueError("task has no path")
    project_path = task.path.parent.parent.parent
    siblings = [t for t in list_tasks(project_path, include_done=False)
                if t.bucket == task.bucket]
    task.status = "open"
    task.done = None
    # The highest order plus one, not the sibling count: a count is only "the
    # end" of a contiguous run, and the bucket a restore lands in is the one
    # the completion hollowed out. Api.complete_task (the row's own `done`
    # button) does not renumber, so A(0) B(1) C(2) minus B leaves A(0) C(2) —
    # and len() would hand B back the order C already holds, putting it in the
    # middle of the list it was promised the end of.
    task.order = max((sibling.order for sibling in siblings), default=-1) + 1
    destination = tasks_dir(project_path) / "open" / task.path.name
    task.path.unlink(missing_ok=True)
    task.path = destination
    return save_task(task)


def delete_task(task: Task) -> None:
    """Unlink the task's file and nothing else.

    No attachment cleanup (they are deliberately never garbage-collected, see
    save_attachment) and no renumber — that is the caller's job, since
    store.py must not import groups.py, which imports store.
    """
    if task.path is None:
        raise ValueError("task has no path")
    task.path.unlink(missing_ok=True)


def reset_to_open(task: Task) -> Task:
    """Retract the claim that this task was ever started.

    The inverse of hand-off, not of completion: it clears `started` rather than
    keeping it, because what is being withdrawn is that the work began at all.
    `bucket` is untouched the whole time a task is in progress, so the task
    simply reappears where it came from.

    A completed task is refused — undoing that needs a move back out of done/,
    and the archive's dates are what the progress view is built on.
    """
    if task.status == "done":
        raise ValueError("a completed task cannot be reopened this way")
    task.status = "open"
    task.started = None
    return save_task(task)


def reorder_bucket(project_path: Path, bucket: str, ordered_ids: list[int]) -> None:
    by_id = {t.id: t for t in list_tasks(project_path, include_done=False)}
    for position, task_id in enumerate(ordered_ids):
        task = by_id.get(task_id)
        if task is None or task.bucket != bucket:
            continue
        task.order = position
        save_task(task)
