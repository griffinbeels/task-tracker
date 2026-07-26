"""Global config: registered projects and app settings."""

import json
from dataclasses import asdict, dataclass, field, fields
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
    # Named for what it counts: concurrent Claude sessions, one per group. Ten
    # tasks handed to one session are one window, not ten — a field called
    # wip_limit that counted groups would be the kind of quiet mismatch that
    # costs an hour later, so the key on disk was renamed with it.
    group_limit: int = 5
    stale_days: int = 90
    types: list[TaskType] = field(default_factory=default_types)


def _projects_file() -> Path:
    return CONFIG_DIR / "projects.json"


def _settings_file() -> Path:
    return CONFIG_DIR / "settings.json"


def _session_file() -> Path:
    return CONFIG_DIR / "session.json"


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return fallback


def _write_json(path: Path, payload) -> None:
    store.write_text_atomic(path, json.dumps(payload, indent=2))


def load_projects() -> list[Project]:
    known = {f.name for f in fields(Project)}
    return [Project(**{k: v for k, v in row.items() if k in known})
            for row in _read_json(_projects_file(), [])]


def save_projects(projects: list[Project]) -> None:
    _write_json(_projects_file(), [asdict(p) for p in projects])


def add_project(name: str, path: str) -> Project:
    projects = load_projects()
    if any(p.name == name for p in projects):
        raise ValueError(f"project already registered: {name}")
    if not Path(path).is_dir():
        raise ValueError(f"not a directory: {path}")
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


def _types_from(raw) -> list[TaskType]:
    """Every well-formed type in this list, and nothing else.

    settings.json is hand-editable, so `types` can be any JSON at all. A row
    that is not an object, or is missing name/color, or carries a key TaskType
    does not have, all used to reach TaskType(**t) and raise — out of
    load_settings, which get_state calls for the window as a whole, so one
    stray character in this file blanked the app instead of one row of a
    settings panel. Same judgement store.read_tasks already makes about a
    malformed task file: skip the row, keep the app.
    """
    if not isinstance(raw, list):
        return []
    known = {f.name for f in fields(TaskType)}
    types = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kept = {k: v for k, v in row.items() if k in known}
        if all(isinstance(kept.get(key), str) for key in known):
            types.append(TaskType(**kept))
    return types


def load_settings() -> Settings:
    raw = _read_json(_settings_file(), None)
    # A corrupt settings.json already falls back through _read_json, but valid
    # JSON of the wrong SHAPE does not — `null`, or a list, or a string all
    # parse fine and then answer .get with an AttributeError. This file is
    # documented as hand-editable, and the app refusing to start is not an
    # acceptable answer to a stray keystroke in it.
    if not isinstance(raw, dict):
        return Settings()
    defaults = Settings()

    def positive(value, fallback: int) -> int:
        """A count the app can act on, or the default. Never 0.

        The settings panel refuses these below 1, so a non-positive value here
        means the file was hand-edited. Readers on the JS side fall back
        through `x || 5`, which silently turns a stored 0 into a working 5 —
        the stored number and the behaviour then disagree with nothing on
        screen admitting it. Resolve it once, on the way in.
        """
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 1 else fallback

    return Settings(
        # wip_limit is the pre-groups name for this setting. Reading it as a
        # fallback is what lets an existing settings.json keep the user's
        # number; nothing writes it any more, so it drops out on the next save.
        group_limit=positive(raw.get("group_limit", raw.get("wip_limit")), defaults.group_limit),
        stale_days=positive(raw.get("stale_days"), defaults.stale_days),
        types=_types_from(raw.get("types")) or default_types(),
    )


def save_settings(settings: Settings) -> None:
    _write_json(_settings_file(), asdict(settings))


# Which project the window was left on. This is how the window was last used,
# not something the user configured, so it lives in its own file rather than on
# Settings — Api.save_settings rebuilds that dataclass from the three fields the
# settings overlay sends, and a key kept there would be silently wiped every
# time those settings were saved.
def _read_session() -> dict:
    stored = _read_json(_session_file(), {})
    return stored if isinstance(stored, dict) else {}


def _update_session(**changes) -> None:
    """Read, change, write. session.json holds several unrelated keys now, and
    replacing the file to set one of them silently drops the rest."""
    _write_json(_session_file(), {**_read_session(), **changes})


def last_project() -> str | None:
    value = _read_session().get("last_project")
    return value if isinstance(value, str) else None


def set_last_project(name: str | None) -> None:
    """Written on every change, so a crash cannot lose the selection."""
    _update_session(last_project=name)


# Which group blocks and project headings the user has folded away. View state
# like last_project, and hand-editable like every other file here — so it is
# filtered rather than trusted on the way out. The renderer indexes each group
# entry by position, and a bare string where a list belongs is iterable, which
# would turn "sm64_tracker" into eleven collapsed projects.
def collapsed_view() -> dict:
    raw = _read_session().get("collapsed")
    if not isinstance(raw, dict):
        return {"projects": [], "groups": []}
    names, pairs = raw.get("projects"), raw.get("groups")
    return {
        "projects": [n for n in names if isinstance(n, str)]
                    if isinstance(names, list) else [],
        "groups": [[pair[0], pair[1]] for pair in pairs
                   if isinstance(pair, list) and len(pair) == 2
                   and all(isinstance(part, str) for part in pair)]
                  if isinstance(pairs, list) else [],
    }


def set_collapsed_view(projects, groups) -> None:
    _update_session(collapsed={
        "projects": [str(name) for name in projects],
        "groups": [[str(pair[0]), str(pair[1])] for pair in groups],
    })
