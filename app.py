"""pywebview window and the JS bridge. This module is wiring only."""

import json
from dataclasses import asdict
from pathlib import Path

import webview

import inbox
import launcher
import migrate
import registry
import singleton
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
        tasks, unreadable = [], []
        for project in projects:
            found, bad = store.read_tasks(Path(project.path))
            tasks.extend(_task_dict(t, project.name) for t in found)
            unreadable.extend(bad)
        return {
            "projects": [asdict(p) for p in projects],
            "settings": asdict(registry.load_settings()),
            "tasks": tasks,
            "notes": [asdict(n) for n in inbox.list_notes()],
            "unreadable": unreadable,
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
        if "bucket" in fields and fields["bucket"] not in store.BUCKETS:
            raise ValueError(f"unknown bucket: {fields['bucket']}")
        if "status" in fields and fields["status"] not in store.STATUSES:
            raise ValueError(f"unknown status: {fields['status']}")
        if "order" in fields:
            fields = {**fields, "order": int(fields["order"])}
        for key in ("title", "type", "body"):
            if key in fields and not isinstance(fields[key], str):
                raise ValueError(f"{key} must be a string")
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
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise ValueError(f"no such task in {project_name}: {missing}")
        tasks = [by_id[i] for i in wanted]
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
    defaults = {"width": 420, "height": 900, "x": None, "y": None, "on_top": True}
    if not WINDOW_STATE.exists():
        return defaults
    try:
        return json.loads(WINDOW_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return defaults


def _save_window_state(window) -> None:
    WINDOW_STATE.parent.mkdir(parents=True, exist_ok=True)
    WINDOW_STATE.write_text(json.dumps({
        "width": window.width, "height": window.height,
        "x": window.x, "y": window.y, "on_top": window.on_top,
    }, indent=2), encoding="utf-8", newline="\n")


def _report_fatal(message: str) -> None:
    """Surface a startup failure even when launched without a console.

    run.bat uses pythonw.exe so the tracker opens without a console window,
    which means a bare print() on the failure path would go nowhere.
    """
    print(message)
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Task Tracker", 0x10)
    except (AttributeError, OSError):
        pass


def main() -> None:
    # Taking the lock shuts down any window already open, so launching always
    # leaves exactly one, running the current code.
    lock = singleton.acquire()
    if lock is None:
        _report_fatal(
            f"Port {singleton.LOCK_PORT} is held by something that is not "
            f"Task Tracker, so it did not shut down when asked.\n\n"
            f"Free that port and try again."
        )
        return

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
    # destroy() closes the window, which fires `closing` on the UI thread and
    # saves geometry there — the socket thread must not read window.x/width
    # itself, those properties are only safe to touch on the UI thread.
    singleton.serve(lock, window.destroy)
    webview.start()


if __name__ == "__main__":
    main()
