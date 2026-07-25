"""Type renames and deletions, applied eagerly across every project."""

from dataclasses import dataclass, field
from pathlib import Path

import registry
import store


@dataclass
class SweepResult:
    changed: int = 0
    skipped: list[str] = field(default_factory=list)


def _reachable_projects(skipped: list[str]) -> list[registry.Project]:
    """Split registered projects into reachable ones and names to skip.

    Reachability is judged by the project's own path, not by whether its
    .tasks/ folder happens to exist yet. .tasks/ is gitignored for untracked
    projects, so a freshly cloned or newly re-registered project can be
    perfectly reachable with no .tasks/ folder on disk; store.list_tasks
    tolerates that (glob on a missing directory just yields nothing). Only a
    moved or disconnected project path should count as unreachable.
    """
    reachable = []
    for project in registry.load_projects():
        if Path(project.path).is_dir():
            reachable.append(project)
        else:
            skipped.append(project.name)
    return reachable


def _sweep(old: str, new: str) -> SweepResult:
    result = SweepResult()
    for project in _reachable_projects(result.skipped):
        for task in store.list_tasks(Path(project.path), include_done=True):
            if task.type != old:
                continue
            task.type = new
            store.save_task(task)
            result.changed += 1
    return result


def count_tasks_with_type(name: str) -> int:
    skipped: list[str] = []
    total = 0
    for project in _reachable_projects(skipped):
        tasks = store.list_tasks(Path(project.path), include_done=True)
        total += sum(1 for task in tasks if task.type == name)
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
