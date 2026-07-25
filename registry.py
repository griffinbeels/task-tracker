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
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def load_projects() -> list[Project]:
    return [Project(**row) for row in _read_json(_projects_file(), [])]


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


def load_settings() -> Settings:
    raw = _read_json(_settings_file(), None)
    if raw is None:
        return Settings()
    defaults = Settings()
    return Settings(
        wip_limit=raw.get("wip_limit", defaults.wip_limit),
        stale_days=raw.get("stale_days", defaults.stale_days),
        types=[TaskType(**t) for t in raw.get("types", [])] or default_types(),
    )


def save_settings(settings: Settings) -> None:
    _write_json(_settings_file(), asdict(settings))
