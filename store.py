"""On-disk task format and .tasks/ directory operations."""

import re
from dataclasses import dataclass, field
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
