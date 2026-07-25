# Task Tracker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single always-on-top window that manages freeform tasks stored as markdown inside each project's own repo, and hands selected tasks to a live Claude Code session.

**Architecture:** Six small Python modules with no framework between them. `store.py` owns the on-disk task format, `registry.py` owns global config, `inbox.py` owns untriaged capture, `migrate.py` owns the type-rename sweep, `launcher.py` owns the Claude handoff, and `app.py` is the only wiring — a pywebview window exposing those modules to a vanilla JS frontend through pywebview's `js_api` bridge. There is no HTTP server, no port, and no bundler.

**Tech Stack:** Python 3.12, pywebview (native window + JS bridge), pyperclip (clipboard), pyyaml (frontmatter), pytest (tests). Vanilla HTML/CSS/JS frontend.

**Spec:** `docs/superpowers/specs/2026-07-25-task-tracker-design.md`

## Global Constraints

- Python is pinned to **3.12**. Create the venv with `uv venv --python 3.12 .venv`. System Python is 3.14 and breaks many packages.
- **Never** invoke bare `python`. Always `& ".venv\Scripts\python.exe" ...`.
- The venv has **no pip**. Install with `uv pip install --python ".venv\Scripts\python.exe" <pkg>`.
- Run all Python and git commands through **PowerShell**, not the Bash tool — Bash on this machine cannot resolve `.venv\Scripts\python.exe`.
- Runtime dependencies are exactly: `pywebview`, `pyperclip`, `pyyaml`. Dev adds `pytest`. Do not add others.
- All timestamps are **UTC**, stored as ISO dates (`datetime.now(timezone.utc).date().isoformat()`).
- **A task body is verbatim.** Never reformat, normalize, wrap, or append to it. It is copied to the clipboard exactly as the user typed it.
- `.tasks/` is **untracked by default** — bootstrapped with a `.gitignore` containing `*`.
- Buckets are exactly `now`, `next`, `someday`. Statuses are exactly `open`, `in-progress`, `done`.
- Keep every file under ~300 lines. Split if one grows past it.
- The frontend is four plain `<script>` files sharing global scope, loaded in this order: `state.js`, `tasks.js`, `triage.js`, `settings.js`. No ES modules, no bundler. Each task adds its own `<script>` tag to `index.html` when it creates its file. Functions defined in one file are callable from another at runtime.
- Commit messages: imperative mood, single line, no embedded double quotes (PowerShell 5.1 mangles them).

---

## File Structure

| File | Responsibility |
|---|---|
| `store.py` | Task dataclass, markdown+frontmatter round-trip, `.tasks/` layout, CRUD, `.gitignore` bootstrap |
| `registry.py` | `~/.task-tracker/projects.json` and `settings.json`; Project, TaskType, Settings |
| `inbox.py` | Raw untriaged notes in `~/.task-tracker/inbox/`; filing a note into a project |
| `migrate.py` | Type rename/delete sweep across every registered project |
| `launcher.py` | Verbatim prompt assembly, clipboard, Claude process spawn |
| `app.py` | pywebview window + `Api` bridge class — the only wiring |
| `ui/index.html`, `ui/style.css` | Markup and styles for the single page |
| `ui/state.js` | Shared `state`, `currentProject`, `refresh()`, project picker, `typeColor()`, `daysSince()` |
| `ui/tasks.js` | Task list, buckets, drag ordering, search, cross-project view, handoff, WIP warning |
| `ui/triage.js` | Capture and triage overlays |
| `ui/settings.js` | Progress view, type editor, git-tracking toggle |

---

### Task 1: Scaffolding and the task file format

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `store.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: nothing
- Produces: `Task` dataclass with fields `id: int`, `title: str`, `type: str`, `bucket: str`, `status: str`, `order: int`, `created: str`, `started: str | None`, `done: str | None`, `body: str`, `path: Path | None`. Functions `parse_task(text: str, path: Path | None = None) -> Task`, `render_task(task: Task) -> str`, `task_slug(title: str) -> str`. Constants `BUCKETS`, `STATUSES`.

- [ ] **Step 1: Initialise the repo and environment**

```powershell
git init
uv venv --python 3.12 .venv
uv pip install --python ".venv\Scripts\python.exe" pywebview pyperclip pyyaml pytest
```

- [ ] **Step 2: Write `pyproject.toml` and `.gitignore`**

`pyproject.toml`:

```toml
[project]
name = "task-tracker"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["pywebview", "pyperclip", "pyyaml"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.superpowers/
```

`.gitignore` already exists with the `.superpowers/` line — extend it, do not overwrite it.

- [ ] **Step 3: Write the failing test**

`tests/test_store.py`:

```python
from pathlib import Path

import store


def test_render_then_parse_preserves_every_field():
    original = store.Task(
        id=42,
        title="Replay audio desync after ~2 minutes",
        type="BUG",
        bucket="now",
        status="open",
        order=1,
        created="2026-07-25",
        started=None,
        done=None,
        body="Audio drifts out of sync.\n\nProbably the pts rebase.",
    )

    reparsed = store.parse_task(store.render_task(original))

    assert reparsed.id == 42
    assert reparsed.title == "Replay audio desync after ~2 minutes"
    assert reparsed.type == "BUG"
    assert reparsed.bucket == "now"
    assert reparsed.status == "open"
    assert reparsed.order == 1
    assert reparsed.created == "2026-07-25"
    assert reparsed.started is None
    assert reparsed.done is None


def test_body_survives_verbatim_including_yaml_lookalikes():
    tricky = 'key: value\n---\n"quoted" and `backticks`\n\n  indented\ttab'
    task = store.Task(
        id=1, title="t", type="BUG", bucket="now", status="open", order=0,
        created="2026-07-25", started=None, done=None, body=tricky,
    )

    assert store.parse_task(store.render_task(task)).body == tricky


def test_task_slug_is_filename_safe_and_bounded():
    assert store.task_slug("Replay audio desync after ~2 minutes!") == "replay-audio-desync-after-2-minutes"
    assert len(store.task_slug("x" * 200)) <= 50
```

- [ ] **Step 4: Run the test to verify it fails**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'store'`.

- [ ] **Step 5: Write the minimal implementation**

`store.py`:

```python
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
        order=int(meta.get("order", 0)),
        created=str(meta["created"]),
        started=meta.get("started") or None,
        done=meta.get("done") or None,
        body=body,
        path=path,
    )
```

Note the `body` handling: `render_task` writes exactly one blank line after the closing `---`, and `parse_task` strips exactly that one newline. Anything else in the body is untouched, which is what makes the verbatim guarantee hold.

- [ ] **Step 6: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -v
```

Expected: 3 passed.

- [ ] **Step 7: Commit**

```powershell
git add pyproject.toml .gitignore store.py tests/test_store.py
git commit -m "feat: add task model with verbatim body round-trip"
```

---

### Task 2: Task directory operations

**Files:**
- Modify: `store.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: `Task`, `parse_task`, `render_task`, `task_slug` from Task 1.
- Produces: `tasks_dir(project_path: Path) -> Path`, `ensure_tasks_dir(project_path: Path, tracked: bool = False) -> Path`, `set_tracked(project_path: Path, tracked: bool) -> None`, `list_tasks(project_path: Path, include_done: bool = True) -> list[Task]`, `next_task_id(project_path: Path) -> int`, `create_task(project_path: Path, title: str, body: str, type: str, bucket: str = "now") -> Task`, `save_task(task: Task) -> Task`, `complete_task(task: Task) -> Task`, `reorder_bucket(project_path: Path, bucket: str, ordered_ids: list[int]) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
import pytest


def test_ensure_tasks_dir_bootstraps_untracked(tmp_path):
    store.ensure_tasks_dir(tmp_path, tracked=False)

    assert (tmp_path / ".tasks" / "open").is_dir()
    assert (tmp_path / ".tasks" / "done").is_dir()
    assert (tmp_path / ".tasks" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_set_tracked_true_removes_the_gitignore(tmp_path):
    store.ensure_tasks_dir(tmp_path, tracked=False)

    store.set_tracked(tmp_path, True)
    assert not (tmp_path / ".tasks" / ".gitignore").exists()

    store.set_tracked(tmp_path, False)
    assert (tmp_path / ".tasks" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_create_task_assigns_sequential_ids_and_writes_to_open(tmp_path):
    first = store.create_task(tmp_path, "First thing", "body one", "BUG")
    second = store.create_task(tmp_path, "Second thing", "body two", "FEATURE")

    assert first.id == 1
    assert second.id == 2
    assert second.path == tmp_path / ".tasks" / "open" / "0002-second-thing.md"
    assert second.path.exists()


def test_next_task_id_counts_done_tasks_so_ids_are_never_reused(tmp_path):
    task = store.create_task(tmp_path, "First thing", "body", "BUG")
    store.complete_task(task)

    assert store.next_task_id(tmp_path) == 2


def test_complete_task_moves_to_done_and_stamps_the_date(tmp_path):
    task = store.create_task(tmp_path, "Ship it", "body", "FEATURE")

    completed = store.complete_task(task)

    assert completed.status == "done"
    assert completed.done is not None
    assert completed.path == tmp_path / ".tasks" / "done" / "0001-ship-it.md"
    assert not (tmp_path / ".tasks" / "open" / "0001-ship-it.md").exists()


def test_list_tasks_can_exclude_the_done_archive(tmp_path):
    store.create_task(tmp_path, "Open one", "body", "BUG")
    store.complete_task(store.create_task(tmp_path, "Closed one", "body", "BUG"))

    assert len(store.list_tasks(tmp_path, include_done=True)) == 2
    assert [t.title for t in store.list_tasks(tmp_path, include_done=False)] == ["Open one"]


def test_reorder_bucket_rewrites_order_to_match_the_given_sequence(tmp_path):
    first = store.create_task(tmp_path, "A", "body", "BUG", bucket="now")
    second = store.create_task(tmp_path, "B", "body", "BUG", bucket="now")
    third = store.create_task(tmp_path, "C", "body", "BUG", bucket="next")

    store.reorder_bucket(tmp_path, "now", [second.id, first.id])

    by_id = {t.id: t for t in store.list_tasks(tmp_path)}
    assert by_id[second.id].order == 0
    assert by_id[first.id].order == 1
    assert by_id[third.id].order == 0


def test_create_task_rejects_an_unknown_bucket(tmp_path):
    with pytest.raises(ValueError):
        store.create_task(tmp_path, "A", "body", "BUG", bucket="urgent")
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -v
```

Expected: the new tests FAIL with `AttributeError: module 'store' has no attribute 'ensure_tasks_dir'`.

- [ ] **Step 3: Write the implementation**

Append to `store.py`:

```python
from datetime import datetime, timezone

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
        ignore.write_text(GITIGNORE_BODY, encoding="utf-8")


def _task_files(project_path: Path, include_done: bool) -> list[Path]:
    root = tasks_dir(project_path)
    folders = ["open", "done"] if include_done else ["open"]
    files: list[Path] = []
    for folder in folders:
        files.extend(sorted((root / folder).glob("*.md")))
    return files


def list_tasks(project_path: Path, include_done: bool = True) -> list[Task]:
    tasks = []
    for path in _task_files(project_path, include_done):
        tasks.append(parse_task(path.read_text(encoding="utf-8"), path))
    return tasks


def next_task_id(project_path: Path) -> int:
    ids = [task.id for task in list_tasks(project_path, include_done=True)]
    return max(ids, default=0) + 1


def create_task(project_path: Path, title: str, body: str, type: str,
                bucket: str = "now") -> Task:
    if bucket not in BUCKETS:
        raise ValueError(f"unknown bucket: {bucket}")
    ensure_tasks_dir(project_path, tracked=not (tasks_dir(project_path) / ".gitignore").exists()
                     if tasks_dir(project_path).exists() else False)
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


def save_task(task: Task) -> Task:
    if task.path is None:
        raise ValueError("task has no path")
    task.path.write_text(render_task(task), encoding="utf-8")
    return task


def complete_task(task: Task) -> Task:
    if task.path is None:
        raise ValueError("task has no path")
    project_path = task.path.parent.parent.parent
    task.status = "done"
    task.done = _today()
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
```

- [ ] **Step 4: Simplify the tracked-detection in `create_task`**

The inline conditional above is unreadable. Replace the `ensure_tasks_dir(...)` call inside `create_task` with:

```python
    if not tasks_dir(project_path).exists():
        ensure_tasks_dir(project_path, tracked=False)
```

A project's tracked state is owned by the registry and applied via `set_tracked`; `create_task` must never silently change it.

- [ ] **Step 5: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```powershell
git add store.py tests/test_store.py
git commit -m "feat: add task directory operations and gitignore bootstrap"
```

---

### Task 3: Registry — projects and settings

**Files:**
- Create: `registry.py`, `tests/test_registry.py`

**Interfaces:**
- Consumes: `store.set_tracked`, `store.ensure_tasks_dir`.
- Produces: `CONFIG_DIR: Path`, dataclasses `Project(name, path, tracked=False, launch=None)`, `TaskType(name, color)`, `Settings(wip_limit=5, stale_days=90, types=[...])`. Functions `load_projects() -> list[Project]`, `save_projects(list[Project]) -> None`, `add_project(name: str, path: str) -> Project`, `remove_project(name: str) -> None`, `set_project_tracked(name: str, tracked: bool) -> Project`, `load_settings() -> Settings`, `save_settings(Settings) -> None`. Module-level `CONFIG_DIR` is monkeypatched by tests.

- [ ] **Step 1: Write the failing tests**

`tests/test_registry.py`:

```python
import pytest

import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def test_settings_default_when_no_file_exists():
    settings = registry.load_settings()

    assert settings.wip_limit == 5
    assert settings.stale_days == 90
    assert [t.name for t in settings.types] == ["BUG", "FEATURE", "ITERATION"]


def test_settings_round_trip(tmp_path):
    settings = registry.load_settings()
    settings.wip_limit = 3
    settings.types.append(registry.TaskType("CHORE", "#8e8e8e"))
    registry.save_settings(settings)

    reloaded = registry.load_settings()
    assert reloaded.wip_limit == 3
    assert [t.name for t in reloaded.types] == ["BUG", "FEATURE", "ITERATION", "CHORE"]


def test_add_project_creates_tasks_dir_untracked(tmp_path):
    repo = tmp_path / "sm64_tracker"
    repo.mkdir()

    project = registry.add_project("sm64_tracker", str(repo))

    assert project.tracked is False
    assert (repo / ".tasks" / "open").is_dir()
    assert (repo / ".tasks" / ".gitignore").exists()


def test_add_project_rejects_a_duplicate_name(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))

    with pytest.raises(ValueError):
        registry.add_project("repo", str(repo))


def test_set_project_tracked_flips_the_gitignore(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))

    registry.set_project_tracked("repo", True)
    assert not (repo / ".tasks" / ".gitignore").exists()
    assert registry.load_projects()[0].tracked is True

    registry.set_project_tracked("repo", False)
    assert (repo / ".tasks" / ".gitignore").exists()


def test_remove_project_leaves_the_task_files_on_disk(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    store.create_task(repo, "Keep me", "body", "BUG")

    registry.remove_project("repo")

    assert registry.load_projects() == []
    assert (repo / ".tasks" / "open" / "0001-keep-me.md").exists()
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_registry.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'registry'`.

- [ ] **Step 3: Write the implementation**

`registry.py`:

```python
"""Global config: registered projects and app settings."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import store

CONFIG_DIR = Path.home() / ".task-tracker"


@dataclass
class Project:
    name: str
    path: str
    tracked: bool = False
    launch: list[str] | None = None


@dataclass
class TaskType:
    name: str
    color: str


def default_types() -> list[TaskType]:
    return [
        TaskType("BUG", "#e5484d"),
        TaskType("FEATURE", "#30a46c"),
        TaskType("ITERATION", "#0090ff"),
    ]


@dataclass
class Settings:
    wip_limit: int = 5
    stale_days: int = 90
    types: list[TaskType] = field(default_factory=default_types)


def _projects_file() -> Path:
    return CONFIG_DIR / "projects.json"


def _settings_file() -> Path:
    return CONFIG_DIR / "settings.json"


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_projects() -> list[Project]:
    return [Project(**row) for row in _read_json(_projects_file(), [])]


def save_projects(projects: list[Project]) -> None:
    _write_json(_projects_file(), [asdict(p) for p in projects])


def add_project(name: str, path: str) -> Project:
    projects = load_projects()
    if any(p.name == name for p in projects):
        raise ValueError(f"project already registered: {name}")
    project = Project(name=name, path=str(path))
    store.ensure_tasks_dir(Path(project.path), tracked=False)
    projects.append(project)
    save_projects(projects)
    return project


def remove_project(name: str) -> None:
    save_projects([p for p in load_projects() if p.name != name])


def set_project_tracked(name: str, tracked: bool) -> Project:
    projects = load_projects()
    for project in projects:
        if project.name == name:
            store.set_tracked(Path(project.path), tracked)
            project.tracked = tracked
            save_projects(projects)
            return project
    raise ValueError(f"unknown project: {name}")


def load_settings() -> Settings:
    raw = _read_json(_settings_file(), None)
    if raw is None:
        return Settings()
    return Settings(
        wip_limit=raw.get("wip_limit", 5),
        stale_days=raw.get("stale_days", 90),
        types=[TaskType(**t) for t in raw.get("types", [])] or default_types(),
    )


def save_settings(settings: Settings) -> None:
    _write_json(_settings_file(), asdict(settings))
```

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_registry.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add registry.py tests/test_registry.py
git commit -m "feat: add project registry and settings"
```

---

### Task 4: Inbox — capture and filing

**Files:**
- Create: `inbox.py`, `tests/test_inbox.py`

**Interfaces:**
- Consumes: `registry.CONFIG_DIR`, `store.create_task`.
- Produces: dataclass `Note(id: str, text: str, created: str)`. Functions `inbox_dir() -> Path`, `save_note(text: str) -> Note`, `list_notes() -> list[Note]`, `delete_note(note_id: str) -> None`, `file_note(note_id: str, project_path: Path, title: str, type: str, bucket: str) -> store.Task`.

Note IDs are the filename stem, `YYYY-MM-DD-HHMMSS`, with a numeric suffix on collision.

- [ ] **Step 1: Write the failing tests**

`tests/test_inbox.py`:

```python
import pytest

import inbox
import registry


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def test_save_note_stores_text_verbatim():
    tricky = 'line one\n---\n"quoted"\n\n  indented'

    note = inbox.save_note(tricky)

    assert inbox.list_notes()[0].text == tricky
    assert note.id


def test_save_note_never_overwrites_an_existing_note():
    first = inbox.save_note("one")
    second = inbox.save_note("two")

    assert first.id != second.id
    assert sorted(n.text for n in inbox.list_notes()) == ["one", "two"]


def test_list_notes_is_oldest_first():
    inbox.save_note("one")
    inbox.save_note("two")

    assert [n.text for n in inbox.list_notes()] == ["one", "two"]


def test_file_note_creates_the_task_and_clears_the_note(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    note = inbox.save_note("Audio drifts out of sync after ~2 minutes")

    task = inbox.file_note(note.id, repo, "Replay audio desync", "BUG", "now")

    assert task.body == "Audio drifts out of sync after ~2 minutes"
    assert task.title == "Replay audio desync"
    assert task.bucket == "now"
    assert inbox.list_notes() == []


def test_file_note_rejects_an_unknown_note(tmp_path):
    with pytest.raises(FileNotFoundError):
        inbox.file_note("nope", tmp_path, "t", "BUG", "now")
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_inbox.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'inbox'`.

- [ ] **Step 3: Write the implementation**

`inbox.py`:

```python
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
    _note_path(note_id).write_text(text, encoding="utf-8")
    return Note(id=note_id, text=text, created=now.date().isoformat())


def list_notes() -> list[Note]:
    directory = inbox_dir()
    if not directory.exists():
        return []
    notes = []
    for path in sorted(directory.glob("*.md")):
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
```

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_inbox.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add inbox.py tests/test_inbox.py
git commit -m "feat: add inbox capture and note filing"
```

---

### Task 5: Type migration sweep

**Files:**
- Create: `migrate.py`, `tests/test_migrate.py`

**Interfaces:**
- Consumes: `registry.load_projects`, `registry.load_settings`, `registry.save_settings`, `store.list_tasks`, `store.save_task`.
- Produces: dataclass `SweepResult(changed: int, skipped: list[str])`. Functions `rename_type(old: str, new: str) -> SweepResult`, `delete_type(name: str, replacement: str) -> SweepResult`, `count_tasks_with_type(name: str) -> int`.

Both functions rewrite `open/` **and** `done/` across every registered project, then update `settings.types`. A project whose path is unreachable is added to `skipped` and does not abort the sweep.

- [ ] **Step 1: Write the failing tests**

`tests/test_migrate.py`:

```python
import pytest

import migrate
import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def make_project(tmp_path, name):
    repo = tmp_path / name
    repo.mkdir()
    registry.add_project(name, str(repo))
    return repo


def test_rename_rewrites_open_and_done_across_every_project(tmp_path):
    first = make_project(tmp_path, "alpha")
    second = make_project(tmp_path, "beta")
    store.create_task(first, "A", "body", "FEATURE")
    store.complete_task(store.create_task(first, "B", "body", "FEATURE"))
    store.create_task(second, "C", "body", "FEATURE")
    store.create_task(second, "D", "body", "BUG")

    result = migrate.rename_type("FEATURE", "FEAT")

    assert result.changed == 3
    assert result.skipped == []
    assert {t.type for t in store.list_tasks(first)} == {"FEAT"}
    assert {t.type for t in store.list_tasks(second)} == {"FEAT", "BUG"}


def test_rename_updates_the_settings_type_list(tmp_path):
    make_project(tmp_path, "alpha")

    migrate.rename_type("FEATURE", "FEAT")

    assert [t.name for t in registry.load_settings().types] == ["BUG", "FEAT", "ITERATION"]


def test_rename_preserves_the_task_body_verbatim(tmp_path):
    repo = make_project(tmp_path, "alpha")
    tricky = 'line one\n---\n"quoted" and `backticks`'
    store.create_task(repo, "A", tricky, "FEATURE")

    migrate.rename_type("FEATURE", "FEAT")

    assert store.list_tasks(repo)[0].body == tricky


def test_delete_reassigns_tasks_then_removes_the_type(tmp_path):
    repo = make_project(tmp_path, "alpha")
    store.create_task(repo, "A", "body", "ITERATION")

    result = migrate.delete_type("ITERATION", "FEATURE")

    assert result.changed == 1
    assert store.list_tasks(repo)[0].type == "FEATURE"
    assert [t.name for t in registry.load_settings().types] == ["BUG", "FEATURE"]


def test_delete_rejects_a_replacement_that_does_not_exist(tmp_path):
    make_project(tmp_path, "alpha")

    with pytest.raises(ValueError):
        migrate.delete_type("ITERATION", "NONSENSE")


def test_unreachable_project_is_skipped_not_fatal(tmp_path):
    reachable = make_project(tmp_path, "alpha")
    missing = tmp_path / "gone"
    missing.mkdir()
    registry.add_project("beta", str(missing))
    store.create_task(reachable, "A", "body", "FEATURE")
    import shutil
    shutil.rmtree(missing)

    result = migrate.rename_type("FEATURE", "FEAT")

    assert result.changed == 1
    assert result.skipped == ["beta"]


def test_count_tasks_with_type_spans_projects_and_archives(tmp_path):
    first = make_project(tmp_path, "alpha")
    second = make_project(tmp_path, "beta")
    store.create_task(first, "A", "body", "BUG")
    store.complete_task(store.create_task(second, "B", "body", "BUG"))

    assert migrate.count_tasks_with_type("BUG") == 2
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_migrate.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'migrate'`.

- [ ] **Step 3: Write the implementation**

`migrate.py`:

```python
"""Type renames and deletions, applied eagerly across every project."""

from dataclasses import dataclass, field
from pathlib import Path

import registry
import store


@dataclass
class SweepResult:
    changed: int = 0
    skipped: list[str] = field(default_factory=list)


def _sweep(old: str, new: str) -> SweepResult:
    result = SweepResult()
    for project in registry.load_projects():
        root = store.tasks_dir(Path(project.path))
        if not root.is_dir():
            result.skipped.append(project.name)
            continue
        for task in store.list_tasks(Path(project.path), include_done=True):
            if task.type != old:
                continue
            task.type = new
            store.save_task(task)
            result.changed += 1
    return result


def count_tasks_with_type(name: str) -> int:
    total = 0
    for project in registry.load_projects():
        if not store.tasks_dir(Path(project.path)).is_dir():
            continue
        total += sum(1 for t in store.list_tasks(Path(project.path)) if t.type == name)
    return total


def rename_type(old: str, new: str) -> SweepResult:
    settings = registry.load_settings()
    names = [t.name for t in settings.types]
    if old not in names:
        raise ValueError(f"unknown type: {old}")
    if new != old and new in names:
        raise ValueError(f"type already exists: {new}")

    result = _sweep(old, new)

    for task_type in settings.types:
        if task_type.name == old:
            task_type.name = new
    registry.save_settings(settings)
    return result


def delete_type(name: str, replacement: str) -> SweepResult:
    settings = registry.load_settings()
    names = [t.name for t in settings.types]
    if name not in names:
        raise ValueError(f"unknown type: {name}")
    if replacement not in names:
        raise ValueError(f"unknown replacement type: {replacement}")
    if replacement == name:
        raise ValueError("replacement must differ from the deleted type")

    result = _sweep(name, replacement)

    settings.types = [t for t in settings.types if t.name != name]
    registry.save_settings(settings)
    return result
```

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_migrate.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add migrate.py tests/test_migrate.py
git commit -m "feat: migrate existing tasks on type rename and delete"
```

---

### Task 6: Claude handoff

**Files:**
- Create: `launcher.py`, `tests/test_launcher.py`

**Interfaces:**
- Consumes: `store.Task`, `store.save_task`.
- Produces: `build_prompt(tasks: list[store.Task]) -> str`, `spawn_claude(project_path: Path, launch: list[str] | None = None) -> None`, `hand_off(project_path: Path, tasks: list[store.Task], launch: list[str] | None = None) -> str`.

`hand_off` marks each task `in-progress` with a `started` date, copies the prompt to the clipboard, spawns the terminal, and returns the prompt.

- [ ] **Step 1: Write the failing tests**

`tests/test_launcher.py`:

```python
import subprocess
from pathlib import Path

import launcher
import store


def make_task(task_id, title, type, body):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
    )


def test_prompt_contains_each_body_verbatim():
    tricky = 'audio drifts\n---\n"quoted" and `backticks`\n\n  indented'
    prompt = launcher.build_prompt([make_task(42, "Replay audio desync", "BUG", tricky)])

    assert tricky in prompt
    assert "## BUG 42 - Replay audio desync" in prompt


def test_prompt_joins_multiple_tasks_in_the_given_order():
    prompt = launcher.build_prompt([
        make_task(1, "First", "BUG", "body one"),
        make_task(2, "Second", "FEATURE", "body two"),
    ])

    assert prompt.index("body one") < prompt.index("## FEATURE 2 - Second")


def test_prompt_appends_no_instructions():
    prompt = launcher.build_prompt([make_task(1, "Only", "BUG", "just this")])

    assert prompt.strip().endswith("just this")


def test_spawn_uses_a_new_console_in_the_project_directory(monkeypatch):
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    launcher.spawn_claude(Path("C:/repos/sm64_tracker"))

    assert captured["args"] == ["claude"]
    assert captured["kwargs"]["cwd"] == Path("C:/repos/sm64_tracker")
    assert captured["kwargs"]["creationflags"] == launcher.NEW_CONSOLE


def test_spawn_honours_a_per_project_launch_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(args=args))

    launcher.spawn_claude(Path("C:/repos/x"), launch=["pwsh", "-c", "claude"])

    assert captured["args"] == ["pwsh", "-c", "claude"]


def test_hand_off_marks_tasks_in_progress_and_copies_the_prompt(tmp_path, monkeypatch):
    copied = {}
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: None)
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "in-progress"
    assert reloaded.started is not None
    assert copied["text"] == prompt
    assert "drifts" in prompt
```

- [ ] **Step 2: Run the tests to verify they fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_launcher.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'launcher'`.

- [ ] **Step 3: Write the implementation**

`launcher.py`:

```python
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
    today = datetime.now(timezone.utc).date().isoformat()
    for task in tasks:
        task.status = "in-progress"
        task.started = task.started or today
        store.save_task(task)

    prompt = build_prompt(tasks)
    pyperclip.copy(prompt)
    spawn_claude(project_path, launch)
    return prompt
```

`NEW_CONSOLE` is read via `getattr` so the module imports on non-Windows machines; the flag only exists on Windows. Passing a list to `Popen` means Windows receives the argument vector directly — no shell parses the prompt, which is what makes quotes and newlines in task bodies safe.

- [ ] **Step 4: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_launcher.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```powershell
git add launcher.py tests/test_launcher.py
git commit -m "feat: add verbatim Claude handoff with clipboard prefill"
```

---

### Task 7: Window and API bridge

**Files:**
- Create: `app.py`, `ui/index.html`, `ui/style.css`, `ui/state.js`

**Interfaces:**
- Consumes: every module from Tasks 2–6.
- Produces: class `Api` whose public methods are callable from JS as `pywebview.api.<method>(...)`, all returning JSON-safe dicts/lists. Methods: `get_state()`, `add_project(name, path)`, `remove_project(name)`, `set_project_tracked(name, tracked)`, `list_tasks(project_name)`, `save_note(text)`, `list_notes()`, `file_note(note_id, project_name, title, type, bucket)`, `delete_note(note_id)`, `update_task(project_name, task_id, fields)`, `complete_task(project_name, task_id)`, `reorder_bucket(project_name, bucket, ordered_ids)`, `hand_off(project_name, task_ids)`, `save_settings(payload)`, `rename_type(old, new)`, `delete_type(name, replacement)`, `count_tasks_with_type(name)`.

- [ ] **Step 1: Write `app.py`**

```python
"""pywebview window and the JS bridge. This module is wiring only."""

import json
from dataclasses import asdict
from pathlib import Path

import webview

import inbox
import launcher
import migrate
import registry
import store

WINDOW_STATE = registry.CONFIG_DIR / "window.json"


def _project(name: str) -> registry.Project:
    for project in registry.load_projects():
        if project.name == name:
            return project
    raise ValueError(f"unknown project: {name}")


def _task_dict(task: store.Task, project_name: str) -> dict:
    payload = asdict(task)
    payload.pop("path", None)
    payload["project"] = project_name
    return payload


class Api:
    def get_state(self) -> dict:
        projects = registry.load_projects()
        tasks = []
        for project in projects:
            if not store.tasks_dir(Path(project.path)).is_dir():
                continue
            tasks.extend(_task_dict(t, project.name)
                         for t in store.list_tasks(Path(project.path)))
        return {
            "projects": [asdict(p) for p in projects],
            "settings": asdict(registry.load_settings()),
            "tasks": tasks,
            "notes": [asdict(n) for n in inbox.list_notes()],
        }

    def add_project(self, name, path):
        return asdict(registry.add_project(name, path))

    def remove_project(self, name):
        registry.remove_project(name)

    def set_project_tracked(self, name, tracked):
        return asdict(registry.set_project_tracked(name, bool(tracked)))

    def list_tasks(self, project_name):
        project = _project(project_name)
        return [_task_dict(t, project_name)
                for t in store.list_tasks(Path(project.path))]

    def save_note(self, text):
        return asdict(inbox.save_note(text))

    def list_notes(self):
        return [asdict(n) for n in inbox.list_notes()]

    def delete_note(self, note_id):
        inbox.delete_note(note_id)

    def file_note(self, note_id, project_name, title, type, bucket):
        project = _project(project_name)
        task = inbox.file_note(note_id, Path(project.path), title, type, bucket)
        return _task_dict(task, project_name)

    def _find(self, project_name, task_id):
        project = _project(project_name)
        for task in store.list_tasks(Path(project.path)):
            if task.id == int(task_id):
                return project, task
        raise ValueError(f"unknown task: {task_id}")

    def update_task(self, project_name, task_id, fields):
        _, task = self._find(project_name, task_id)
        for key in ("title", "type", "bucket", "status", "order", "body"):
            if key in fields:
                setattr(task, key, fields[key])
        store.save_task(task)
        return _task_dict(task, project_name)

    def complete_task(self, project_name, task_id):
        _, task = self._find(project_name, task_id)
        return _task_dict(store.complete_task(task), project_name)

    def reorder_bucket(self, project_name, bucket, ordered_ids):
        project = _project(project_name)
        store.reorder_bucket(Path(project.path), bucket, [int(i) for i in ordered_ids])

    def hand_off(self, project_name, task_ids):
        project = _project(project_name)
        wanted = [int(i) for i in task_ids]
        by_id = {t.id: t for t in store.list_tasks(Path(project.path))}
        tasks = [by_id[i] for i in wanted if i in by_id]
        return launcher.hand_off(Path(project.path), tasks, project.launch)

    def save_settings(self, payload):
        settings = registry.Settings(
            wip_limit=int(payload["wip_limit"]),
            stale_days=int(payload["stale_days"]),
            types=[registry.TaskType(**t) for t in payload["types"]],
        )
        registry.save_settings(settings)
        return asdict(settings)

    def count_tasks_with_type(self, name):
        return migrate.count_tasks_with_type(name)

    def rename_type(self, old, new):
        return asdict(migrate.rename_type(old, new))

    def delete_type(self, name, replacement):
        return asdict(migrate.delete_type(name, replacement))


def _load_window_state() -> dict:
    if WINDOW_STATE.exists():
        return json.loads(WINDOW_STATE.read_text(encoding="utf-8"))
    return {"width": 420, "height": 900, "x": None, "y": None, "on_top": True}


def _save_window_state(window) -> None:
    WINDOW_STATE.parent.mkdir(parents=True, exist_ok=True)
    WINDOW_STATE.write_text(json.dumps({
        "width": window.width, "height": window.height,
        "x": window.x, "y": window.y, "on_top": window.on_top,
    }, indent=2), encoding="utf-8")


def main() -> None:
    state = _load_window_state()
    window = webview.create_window(
        "Tasks",
        str(Path(__file__).parent / "ui" / "index.html"),
        js_api=Api(),
        width=state["width"], height=state["height"],
        x=state["x"], y=state["y"],
        on_top=state["on_top"],
    )
    window.events.closing += lambda: _save_window_state(window)
    webview.start()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write a minimal `ui/index.html` that proves the bridge works**

```html
<!doctype html>
<html>
  <head><meta charset="utf-8"><link rel="stylesheet" href="style.css"></head>
  <body>
    <div id="app">loading…</div>
    <script src="state.js"></script>
  </body>
</html>
```

`ui/state.js`:

```js
window.addEventListener('pywebviewready', async () => {
  const state = await window.pywebview.api.get_state();
  document.getElementById('app').textContent =
    `${state.projects.length} projects, ${state.tasks.length} tasks`;
});
```

`ui/style.css`:

```css
:root { color-scheme: dark; }
body { font: 13px/1.5 "Segoe UI", system-ui, sans-serif; margin: 0; padding: 12px; }
```

- [ ] **Step 3: Run the app and verify the bridge**

```powershell
& ".venv\Scripts\python.exe" app.py
```

Expected: a native window opens showing `0 projects, 0 tasks`. Close it, confirm `~/.task-tracker/window.json` was written.

- [ ] **Step 4: Commit**

```powershell
git add app.py ui/
git commit -m "feat: add pywebview window and JS API bridge"
```

---

### Task 8: Task list UI — projects, buckets, drag ordering

**Files:**
- Modify: `ui/index.html`, `ui/state.js`, `ui/style.css`
- Create: `ui/tasks.js`

**Interfaces:**
- Consumes: `get_state`, `list_tasks`, `update_task`, `complete_task`, `reorder_bucket`, `add_project` from Task 7.
- Produces: in `ui/state.js` — `BUCKETS`, `state`, `currentProject`, `typeColor(name)`, `refresh()`, `renderProjectPicker()`. In `ui/tasks.js` — `taskRow(task)`, `bucketSection(bucket)`, `wireDrag(section, bucket)`, `render()`. All are globals shared across the four script files and reused by Tasks 9–11.

- [ ] **Step 1: Build the layout**

`ui/index.html` body:

```html
<header>
  <select id="project-picker"></select>
  <button id="add-project">+</button>
  <button id="capture-button">Capture</button>
</header>
<div id="wip-warning" hidden></div>
<main id="task-list"></main>
```

- [ ] **Step 2: Render buckets as sections with drag-and-drop**

Create `ui/tasks.js` with the following, and add `<script src="tasks.js"></script>` to `index.html` after the `state.js` tag. The first four declarations (`BUCKETS`, `state`, `currentProject`, `typeColor`) belong in `ui/state.js` instead — move them there, replacing the Task 7 smoke-test body:

```js
const BUCKETS = ['now', 'next', 'someday'];
let state = { projects: [], settings: {}, tasks: [], notes: [] };
let currentProject = null;

function tasksFor(project, bucket) {
  return state.tasks
    .filter(t => t.project === project && t.bucket === bucket && t.status !== 'done')
    .sort((a, b) => a.order - b.order);
}

function typeColor(name) {
  const found = (state.settings.types || []).find(t => t.name === name);
  return found ? found.color : '#8e8e8e';
}

function taskRow(task) {
  const row = document.createElement('div');
  row.className = 'task';
  row.draggable = true;
  row.dataset.id = task.id;
  row.innerHTML = `
    <input type="checkbox" class="select">
    <span class="type" style="background:${typeColor(task.type)}">${task.type}</span>
    <span class="title">${task.title}</span>
    <button class="done" title="Mark done">done</button>`;
  row.querySelector('.done').onclick = async () => {
    await window.pywebview.api.complete_task(task.project, task.id);
    await refresh();
  };
  return row;
}

function bucketSection(bucket) {
  const section = document.createElement('section');
  section.dataset.bucket = bucket;
  section.innerHTML = `<h2>${bucket.toUpperCase()}</h2>`;
  tasksFor(currentProject, bucket).forEach(t => section.append(taskRow(t)));
  wireDrag(section, bucket);
  return section;
}

function wireDrag(section, bucket) {
  let dragged = null;
  section.addEventListener('dragstart', e => { dragged = e.target.closest('.task'); });
  section.addEventListener('dragover', e => {
    e.preventDefault();
    const over = e.target.closest('.task');
    if (!over || over === dragged || !dragged) return;
    const after = over.getBoundingClientRect().top + over.offsetHeight / 2 < e.clientY;
    section.insertBefore(dragged, after ? over.nextSibling : over);
  });
  section.addEventListener('drop', async () => {
    const ids = [...section.querySelectorAll('.task')].map(el => Number(el.dataset.id));
    await window.pywebview.api.reorder_bucket(currentProject, bucket, ids);
    await refresh();
  });
}

function render() {
  const list = document.getElementById('task-list');
  list.replaceChildren(...BUCKETS.map(bucketSection));
  renderWipWarning();
}

async function refresh() {
  state = await window.pywebview.api.get_state();
  if (!currentProject && state.projects.length) currentProject = state.projects[0].name;
  renderProjectPicker();
  render();
}
```

- [ ] **Step 3: Wire the project picker and add-project button**

```js
function renderProjectPicker() {
  const picker = document.getElementById('project-picker');
  picker.replaceChildren(...state.projects.map(p => {
    const option = document.createElement('option');
    option.value = p.name;
    option.textContent = p.name;
    option.selected = p.name === currentProject;
    return option;
  }));
  picker.onchange = () => { currentProject = picker.value; render(); };
}

document.getElementById('add-project').onclick = async () => {
  const path = prompt('Project folder path');
  if (!path) return;
  const name = prompt('Project name', path.split(/[\\/]/).filter(Boolean).pop());
  if (!name) return;
  await window.pywebview.api.add_project(name, path);
  currentProject = name;
  await refresh();
};

window.addEventListener('pywebviewready', refresh);
```

- [ ] **Step 4: Style the list**

```css
header { display: flex; gap: 6px; margin-bottom: 10px; }
h2 { font-size: 10px; letter-spacing: .1em; opacity: .5; margin: 14px 0 4px; }
.task { display: flex; align-items: center; gap: 6px; padding: 5px 6px;
        border-radius: 5px; cursor: grab; }
.task:hover { background: rgba(127,127,127,.12); }
.type { font-size: 9px; font-weight: 700; padding: 1px 5px; border-radius: 3px;
        color: #fff; }
.title { flex: 1; }
.done { opacity: 0; font-size: 10px; }
.task:hover .done { opacity: .6; }
```

- [ ] **Step 5: Verify manually**

Run the app, add a project pointing at a scratch folder, and confirm: tasks appear under their buckets, dragging within a bucket persists across a restart, and the done button moves a task out of the list.

- [ ] **Step 6: Commit**

```powershell
git add ui/
git commit -m "feat: add bucketed task list with drag ordering"
```

---

### Task 9: Capture and triage UI

**Files:**
- Modify: `ui/index.html`, `ui/style.css`
- Create: `ui/triage.js`

**Interfaces:**
- Consumes: `save_note`, `list_notes`, `file_note`, `delete_note`; the globals `state`, `currentProject`, `BUCKETS`, `refresh()` from Task 8.
- Produces: `openCapture()` and `openTriage()`, both callable from Task 11's settings view.

- [ ] **Step 1: Add the two overlays to `index.html`**

```html
<div id="capture" class="overlay" hidden>
  <textarea id="capture-text" placeholder="Write anything. No fields."></textarea>
  <div class="actions"><button id="capture-save">Save</button>
    <button id="capture-cancel">Cancel</button></div>
</div>

<div id="triage" class="overlay" hidden>
  <div id="triage-progress"></div>
  <pre id="triage-text"></pre>
  <input id="triage-title" placeholder="Title">
  <div id="triage-projects" class="chips"></div>
  <div id="triage-types" class="chips"></div>
  <div id="triage-buckets" class="chips"></div>
  <div class="actions"><button id="triage-file">File</button>
    <button id="triage-skip">Skip</button>
    <button id="triage-discard">Discard</button>
    <button id="triage-close">Close</button></div>
</div>
```

- [ ] **Step 2: Implement capture**

```js
function openCapture() {
  document.getElementById('capture-text').value = '';
  document.getElementById('capture').hidden = false;
  document.getElementById('capture-text').focus();
}

document.getElementById('capture-button').onclick = openCapture;
document.getElementById('capture-cancel').onclick =
  () => { document.getElementById('capture').hidden = true; };
document.getElementById('capture-save').onclick = async () => {
  const text = document.getElementById('capture-text').value;
  if (text.trim()) await window.pywebview.api.save_note(text);
  document.getElementById('capture').hidden = true;
  await refresh();
};
```

Capture sends the textarea value unmodified — no trimming of the saved text, no template. The `trim()` check only decides whether an empty box counts as a note.

- [ ] **Step 3: Implement triage**

```js
let triageQueue = [];
let triageIndex = 0;
let triagePick = { project: null, type: null, bucket: 'now' };

function chip(label, selected, onClick) {
  const button = document.createElement('button');
  button.className = 'chip' + (selected ? ' on' : '');
  button.textContent = label;
  button.onclick = onClick;
  return button;
}

function renderTriage() {
  const note = triageQueue[triageIndex];
  if (!note) { document.getElementById('triage').hidden = true; return; }
  document.getElementById('triage-progress').textContent =
    `note ${triageIndex + 1} / ${triageQueue.length}`;
  document.getElementById('triage-text').textContent = note.text;
  document.getElementById('triage-title').value =
    note.text.split('\n')[0].slice(0, 80);

  document.getElementById('triage-projects').replaceChildren(
    ...state.projects.map(p => chip(p.name, triagePick.project === p.name,
      () => { triagePick.project = p.name; renderTriage(); })));
  document.getElementById('triage-types').replaceChildren(
    ...state.settings.types.map(t => chip(t.name, triagePick.type === t.name,
      () => { triagePick.type = t.name; renderTriage(); })));
  document.getElementById('triage-buckets').replaceChildren(
    ...BUCKETS.map(b => chip(b, triagePick.bucket === b,
      () => { triagePick.bucket = b; renderTriage(); })));
}

async function openTriage() {
  triageQueue = await window.pywebview.api.list_notes();
  triageIndex = 0;
  triagePick = {
    project: currentProject,
    type: (state.settings.types[0] || {}).name,
    bucket: 'now',
  };
  document.getElementById('triage').hidden = triageQueue.length === 0;
  renderTriage();
}

document.getElementById('triage-file').onclick = async () => {
  const note = triageQueue[triageIndex];
  const title = document.getElementById('triage-title').value.trim();
  if (!note || !title || !triagePick.project || !triagePick.type) return;
  await window.pywebview.api.file_note(
    note.id, triagePick.project, title, triagePick.type, triagePick.bucket);
  triageQueue.splice(triageIndex, 1);
  renderTriage();
  await refresh();
};

document.getElementById('triage-skip').onclick =
  () => { triageIndex = (triageIndex + 1) % Math.max(triageQueue.length, 1); renderTriage(); };

document.getElementById('triage-discard').onclick = async () => {
  const note = triageQueue[triageIndex];
  if (!note) return;
  await window.pywebview.api.delete_note(note.id);
  triageQueue.splice(triageIndex, 1);
  renderTriage();
  await refresh();
};

document.getElementById('triage-close').onclick =
  () => { document.getElementById('triage').hidden = true; };
```

- [ ] **Step 4: Add an inbox badge that opens triage**

In `index.html` header, after the capture button:

```html
<button id="inbox-button" hidden></button>
```

In `ui/tasks.js`, inside `render()`:

```js
  const inboxButton = document.getElementById('inbox-button');
  inboxButton.hidden = state.notes.length === 0;
  inboxButton.textContent = `Inbox ${state.notes.length}`;
  inboxButton.onclick = openTriage;
```

- [ ] **Step 5: Style the overlays**

```css
.overlay { position: fixed; inset: 0; background: #111; padding: 12px;
           display: flex; flex-direction: column; gap: 8px; }
.overlay[hidden] { display: none; }
#capture-text { flex: 1; resize: none; font: inherit; }
#triage-text { flex: 1; overflow: auto; white-space: pre-wrap;
               background: rgba(127,127,127,.1); padding: 8px; border-radius: 5px; }
.chips { display: flex; flex-wrap: wrap; gap: 4px; }
.chip { font-size: 11px; padding: 2px 8px; border-radius: 10px; opacity: .55; }
.chip.on { opacity: 1; outline: 1px solid currentColor; }
.actions { display: flex; gap: 6px; }
```

- [ ] **Step 6: Verify manually**

Capture a note containing quotes, newlines and a `---` line. Confirm the triage view shows it byte-identical, and that filing it produces a task whose body matches exactly.

- [ ] **Step 7: Commit**

```powershell
git add ui/
git commit -m "feat: add capture and triage views"
```

---

### Task 10: Handoff, cross-project view, search, staleness, WIP warning

**Files:**
- Modify: `ui/index.html`, `ui/tasks.js`, `ui/state.js`, `ui/style.css`

**Interfaces:**
- Consumes: `hand_off`, `get_state`; the globals from Task 8; `openTriage()` from Task 9.
- Produces: `daysSince(isoDate)` in `ui/state.js`. Everything else stays inside `ui/tasks.js`.

- [ ] **Step 1: Add the controls to `index.html`**

```html
<div id="toolbar">
  <input id="search" placeholder="Search all projects">
  <label><input type="checkbox" id="all-projects"> All projects</label>
  <button id="spin-up" disabled>Spin up Claude</button>
</div>
```

Place it directly below `<header>`.

- [ ] **Step 2: Implement the handoff**

```js
function selectedIds() {
  return [...document.querySelectorAll('.task .select:checked')]
    .map(el => Number(el.closest('.task').dataset.id));
}

document.getElementById('task-list').addEventListener('change', () => {
  document.getElementById('spin-up').disabled = selectedIds().length === 0;
});

document.getElementById('spin-up').onclick = async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  await window.pywebview.api.hand_off(currentProject, ids);
  await refresh();
};
```

Selection is disabled in cross-project mode, since a handoff targets one project.

- [ ] **Step 3: Implement search, cross-project mode and staleness**

```js
function daysSince(isoDate) {
  return Math.floor((Date.now() - new Date(isoDate).getTime()) / 86400000);
}

function matches(task, query) {
  const needle = query.toLowerCase();
  return task.title.toLowerCase().includes(needle)
      || task.body.toLowerCase().includes(needle);
}

function renderSearch(query) {
  const hits = state.tasks.filter(t => matches(t, query)).slice(0, 200);
  const list = document.getElementById('task-list');
  list.replaceChildren(...hits.map(task => {
    const row = taskRow(task);
    row.draggable = false;
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    if (task.status === 'done') row.classList.add('archived');
    return row;
  }));
}

function renderAllProjects() {
  const rows = state.tasks
    .filter(t => t.bucket === 'now' && t.status !== 'done')
    .sort((a, b) => a.project.localeCompare(b.project) || a.order - b.order);
  const list = document.getElementById('task-list');
  list.replaceChildren(...rows.map(task => {
    const row = taskRow(task);
    row.draggable = false;
    row.querySelector('.select').disabled = true;
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    return row;
  }));
}
```

Then replace the body of `render()` with:

```js
function render() {
  const query = document.getElementById('search').value.trim();
  if (query) renderSearch(query);
  else if (document.getElementById('all-projects').checked) renderAllProjects();
  else document.getElementById('task-list')
        .replaceChildren(...BUCKETS.map(bucketSection));
  renderWipWarning();
  const inboxButton = document.getElementById('inbox-button');
  inboxButton.hidden = state.notes.length === 0;
  inboxButton.textContent = `Inbox ${state.notes.length}`;
  inboxButton.onclick = openTriage;
}

document.getElementById('search').oninput = render;
document.getElementById('all-projects').onchange = render;
```

Add the staleness marker inside `taskRow`, just before `return row;`:

```js
  const age = daysSince(task.created);
  if (age >= (state.settings.stale_days || 90) && task.status !== 'done') {
    const marker = document.createElement('span');
    marker.className = 'age';
    marker.textContent = age >= 365 ? `${Math.floor(age / 365)}y` : `${Math.floor(age / 30)}mo`;
    row.append(marker);
  }
```

- [ ] **Step 4: Implement the WIP warning**

```js
function renderWipWarning() {
  const active = state.tasks.filter(t => t.status === 'in-progress').length;
  const limit = state.settings.wip_limit || 5;
  const banner = document.getElementById('wip-warning');
  banner.hidden = active <= limit;
  banner.textContent = `${active} tasks in progress — over your limit of ${limit}`;
}
```

- [ ] **Step 5: Style the additions**

```css
#toolbar { display: flex; gap: 6px; align-items: center; margin-bottom: 8px; }
#search { flex: 1; }
#wip-warning { background: #7a3b00; padding: 5px 8px; border-radius: 5px;
               font-size: 11px; margin-bottom: 8px; }
#wip-warning[hidden] { display: none; }
.age { font-size: 10px; opacity: .35; }
.archived .title { opacity: .45; text-decoration: line-through; }
```

- [ ] **Step 6: Verify manually**

Select two tasks and hit spin up. Confirm a terminal opens in the project directory, `Ctrl+V` pastes both task bodies verbatim in selection order with nothing appended, and both tasks show as in-progress after a refresh.

- [ ] **Step 7: Commit**

```powershell
git add ui/
git commit -m "feat: add Claude handoff, cross-project view, search and staleness"
```

---

### Task 11: Progress view and type editor

**Files:**
- Modify: `ui/index.html`, `ui/style.css`
- Create: `ui/settings.js`, `README.md`

**Interfaces:**
- Consumes: `save_settings`, `rename_type`, `delete_type`, `count_tasks_with_type`, `set_project_tracked`; the globals `state`, `currentProject`, `typeColor()`, `refresh()` from Task 8.
- Produces: nothing.

- [ ] **Step 1: Add the progress view**

`index.html` header gets `<button id="progress-button">Progress</button>`, and:

```html
<div id="progress" class="overlay" hidden>
  <div id="progress-body"></div>
  <div class="actions"><button id="progress-close">Close</button></div>
</div>
```

```js
function monthLabel(isoDate) {
  return new Date(isoDate).toLocaleDateString('en', { month: 'long', year: 'numeric' });
}

document.getElementById('progress-button').onclick = () => {
  const done = state.tasks
    .filter(t => t.project === currentProject && t.status === 'done' && t.done)
    .sort((a, b) => b.done.localeCompare(a.done));

  const body = document.getElementById('progress-body');
  body.replaceChildren();
  let month = null;
  for (const task of done) {
    const label = monthLabel(task.done);
    if (label !== month) {
      month = label;
      const heading = document.createElement('h2');
      heading.textContent = label;
      body.append(heading);
    }
    const entry = document.createElement('div');
    entry.className = 'entry';
    entry.innerHTML = `<span class="type" style="background:${typeColor(task.type)}">${task.type}</span>
                       <span>${task.title}</span>`;
    body.append(entry);
    const outcome = task.body.split(/^## Outcome$/m)[1];
    if (outcome && outcome.trim()) {
      const note = document.createElement('div');
      note.className = 'outcome';
      note.textContent = outcome.trim();
      body.append(note);
    }
  }
  if (!done.length) body.textContent = 'Nothing completed yet.';
  document.getElementById('progress').hidden = false;
};

document.getElementById('progress-close').onclick =
  () => { document.getElementById('progress').hidden = true; };
```

- [ ] **Step 2: Add the settings overlay with the type editor**

```html
<div id="settings" class="overlay" hidden>
  <label>WIP limit <input id="wip-limit" type="number" min="1"></label>
  <label>Stale after (days) <input id="stale-days" type="number" min="1"></label>
  <div id="type-editor"></div>
  <button id="add-type">Add type</button>
  <div id="tracked-editor"></div>
  <div class="actions"><button id="settings-save">Save</button>
    <button id="settings-close">Close</button></div>
</div>
```

```js
function renderTypeEditor() {
  const editor = document.getElementById('type-editor');
  editor.replaceChildren(...state.settings.types.map(type => {
    const row = document.createElement('div');
    row.className = 'type-row';
    row.innerHTML = `<input class="type-name" value="${type.name}">
                     <input class="type-color" type="color" value="${type.color}">
                     <button class="type-delete">delete</button>`;

    row.querySelector('.type-name').onchange = async event => {
      const next = event.target.value.trim();
      if (!next || next === type.name) return;
      const count = await window.pywebview.api.count_tasks_with_type(type.name);
      if (count && !confirm(`Rename ${type.name} to ${next} on ${count} task(s)?`)) {
        event.target.value = type.name;
        return;
      }
      const result = await window.pywebview.api.rename_type(type.name, next);
      reportSkipped(result);
      await refresh();
      renderTypeEditor();
    };

    row.querySelector('.type-delete').onclick = async () => {
      const count = await window.pywebview.api.count_tasks_with_type(type.name);
      const others = state.settings.types.filter(t => t.name !== type.name);
      if (!others.length) { alert('At least one type is required.'); return; }
      let replacement = others[0].name;
      if (count) {
        replacement = prompt(
          `${count} task(s) use ${type.name}. Reassign them to which type?\n` +
          others.map(t => t.name).join(', '), replacement);
        if (!replacement) return;
      }
      const result = await window.pywebview.api.delete_type(type.name, replacement);
      reportSkipped(result);
      await refresh();
      renderTypeEditor();
    };

    return row;
  }));
}

function reportSkipped(result) {
  if (result && result.skipped && result.skipped.length) {
    alert(`Could not reach: ${result.skipped.join(', ')}. ` +
          `Tasks in those projects keep the old type.`);
  }
}
```

The rename confirm and the delete reassignment prompt are what make the eager migration safe — the user always sees how many task files are about to be rewritten, and a delete can never orphan a task.

- [ ] **Step 3: Wire settings save and the per-project tracked toggle**

```js
function renderTrackedEditor() {
  const editor = document.getElementById('tracked-editor');
  editor.replaceChildren(...state.projects.map(project => {
    const row = document.createElement('label');
    row.className = 'tracked-row';
    row.innerHTML = `<input type="checkbox" ${project.tracked ? 'checked' : ''}>
                     commit ${project.name}/.tasks to git`;
    row.querySelector('input').onchange = async event => {
      await window.pywebview.api.set_project_tracked(project.name, event.target.checked);
      await refresh();
    };
    return row;
  }));
}

document.getElementById('add-type').onclick = () => {
  state.settings.types.push({ name: 'NEW', color: '#8e8e8e' });
  renderTypeEditor();
};

document.getElementById('settings-save').onclick = async () => {
  await window.pywebview.api.save_settings({
    wip_limit: Number(document.getElementById('wip-limit').value),
    stale_days: Number(document.getElementById('stale-days').value),
    types: [...document.querySelectorAll('.type-row')].map(row => ({
      name: row.querySelector('.type-name').value.trim(),
      color: row.querySelector('.type-color').value,
    })),
  });
  document.getElementById('settings').hidden = true;
  await refresh();
};
```

Add a `<button id="settings-button">⚙</button>` to the header, opening the overlay after calling `renderTypeEditor()` and `renderTrackedEditor()` and populating the two number inputs from `state.settings`.

- [ ] **Step 4: Write `README.md`**

```markdown
# Task Tracker

An always-on-top window for tracking tasks across projects. Tasks are markdown
files inside each project's own repo; the app is a view over them.

## Run

    uv venv --python 3.12 .venv
    uv pip install --python ".venv\Scripts\python.exe" pywebview pyperclip pyyaml
    & ".venv\Scripts\python.exe" app.py

## Layout

    ~/.task-tracker/projects.json   registered projects
    ~/.task-tracker/settings.json   WIP limit, staleness, task types
    ~/.task-tracker/inbox/          untriaged notes
    <project>/.tasks/open/          active tasks
    <project>/.tasks/done/          the archive, and the progress view's source

`.tasks/` is gitignored by default. Toggle per project in settings.

## Tests

    & ".venv\Scripts\python.exe" -m pytest -v
```

- [ ] **Step 5: Run the full suite and the app**

```powershell
& ".venv\Scripts\python.exe" -m pytest -v
& ".venv\Scripts\python.exe" app.py
```

Expected: all tests pass. In the app, rename a type used by tasks in two projects and confirm both projects' tasks — open and done — show the new name after refresh.

- [ ] **Step 6: Commit**

```powershell
git add ui/ README.md
git commit -m "feat: add progress view, type editor and git tracking toggle"
```

---

## Self-Review Notes

Checked against the spec:

- Every spec section maps to a task. Storage → 1–2, registry and settings → 3, capture and triage → 4 and 9, migration → 5 and 11, handoff → 6 and 10, window → 7, priority buckets → 8, progress/cross-project/search/staleness/WIP → 10–11.
- Signatures are consistent across tasks: `store.Task` fields, `hand_off(project_path, tasks, launch)`, `SweepResult(changed, skipped)`, and the `Api` method names used by the JS all match their definitions.
- No placeholders. Every code step contains runnable code.
- The one spec behaviour with no automated test is window geometry persistence, verified manually in Task 7 Step 3. Automating it would mean driving a native window, which is not worth the machinery here.
