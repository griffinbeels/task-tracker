"""pywebview window and the JS bridge. This module is wiring only."""

import json
import os
from dataclasses import asdict
from pathlib import Path

import webview

import groups
import inbox
import launcher
import migrate
import registry
import restart
import singleton
import store

WINDOW_STATE = registry.CONFIG_DIR / "window.json"


def _project(name: str) -> registry.Project:
    for project in registry.load_projects():
        if project.name == name:
            return project
    raise ValueError(f"unknown project: {name}")


def _text(value, field: str) -> str:
    """Refuse anything but a string, rather than coercing it.

    A group name arrives from JS, where a number is a perfectly ordinary value.
    str(5) would create a group called "5" and look like it worked.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    return value


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
            "last_project": registry.last_project(),
        }

    def set_last_project(self, name):
        registry.set_last_project(name)

    def restart(self):
        """Relaunch from source. The replacement closes this window itself.

        Nothing is returned and nothing is awaited: success means this process
        is about to be destroyed over the singleton port, so there is no state
        for the renderer to come back to.
        """
        restart.spawn_replacement()

    def pick_project_folder(self):
        """Open the OS folder picker and return the chosen path, or None.

        Hand-typing an absolute path into a JS prompt is a bad control for the
        job — you cannot browse, cannot see what exists, and a typo is silent.
        """
        if not webview.windows:
            return None
        projects = registry.load_projects()
        start_in = str(Path(projects[-1].path).parent) if projects else ""
        chosen = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG, directory=start_in)
        return chosen[0] if chosen else None

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

    def file_note(self, note_id, project_name, title, type, bucket, body=None, color=""):
        if body is not None and not isinstance(body, str):
            raise ValueError("body must be a string")
        # "" means the caller has no preference and the backend should derive
        # one, same as create_task — only a non-empty value Claude Code's
        # /color would reject is an error.
        if color and color not in store.CLAUDE_COLORS:
            raise ValueError(f"unknown color: {color}")
        project = _project(project_name)
        task = inbox.file_note(note_id, Path(project.path), title, type, bucket, body, color=color)
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
        # store.Task.__post_init__ silently repairs a bad colour, which is
        # right for a hand-edited file — here a bad value means the JS caller
        # is broken, so raise instead of letting that repair hide it.
        if "color" in fields and fields["color"] not in store.CLAUDE_COLORS:
            raise ValueError(f"unknown color: {fields['color']}")
        if "order" in fields:
            fields = {**fields, "order": int(fields["order"])}
        for key in ("title", "type", "body", "color"):
            if key in fields and not isinstance(fields[key], str):
                raise ValueError(f"{key} must be a string")
        project, task = self._find(project_name, task_id)
        # A group lives in one bucket and its members are contiguous in order
        # (invariant 16). Both are enforced here rather than in whichever
        # control happened to call, so every writer gets them: a bucket change
        # on one member moves the whole group instead of splitting it, and an
        # `order` aimed at a single member is ignored because the group owns
        # its own ordering.
        # A completed task keeps its group string in done/ but is not part of
        # the group the renderer draws (invariant 15), so editing one must not
        # drag its still-open siblings around.
        in_a_group = bool(task.group) and task.status != "done"
        moving_group = (in_a_group and "bucket" in fields
                        and fields["bucket"] != task.bucket)
        if moving_group:
            ignored = {"bucket", "order"}
        elif in_a_group:
            ignored = {"order"}
        else:
            ignored = set()

        for key in ("title", "type", "bucket", "status", "order", "body", "color"):
            if key in fields and key not in ignored:
                setattr(task, key, fields[key])
        store.save_task(task)

        if moving_group:
            groups.set_bucket(Path(project.path), task.group, fields["bucket"])
        elif in_a_group:
            groups.renumber(Path(project.path), task.bucket)
        if in_a_group:
            _, task = self._find(project_name, task_id)
        return _task_dict(task, project_name)

    def create_task(self, project_name, title, body, type, bucket, color=""):
        if bucket not in store.BUCKETS:
            raise ValueError(f"unknown bucket: {bucket}")
        # "" means no preference, let the backend derive one (store.create_task
        # already does this) — only a colour Claude Code's /color would reject
        # is an error.
        if color and color not in store.CLAUDE_COLORS:
            raise ValueError(f"unknown color: {color}")
        for key, value in (("title", title), ("body", body), ("type", type)):
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
        project = _project(project_name)
        task = store.create_task(Path(project.path), title, body, type, bucket, color=color)
        return _task_dict(task, project_name)

    def save_attachment(self, project_name, data_url):
        """Persist a pasted image and return a URL the editor can render.

        as_uri(), not as_posix(): the markdown this lands in is rendered as
        HTML, and `C:/repos/x/a.png` is not a URL — a leading `C:` parses as a
        scheme, so the browser never resolves it as a path and the image
        silently fails to load. The file:// form is also unambiguous for the
        Claude session the body is handed to, which is the other half of why
        the path is absolute.
        """
        project = _project(project_name)
        path = store.save_attachment(Path(project.path), data_url)
        return path.as_uri()

    def read_attachment(self, project_name, reference):
        """The bytes behind a body's image reference, as a renderable data URL."""
        project = _project(project_name)
        return store.attachment_data_url(Path(project.path), reference)

    def open_attachment(self, project_name, reference):
        """Hand the real file to whatever the user opens images with.

        Full-size viewing with zoom and pan, for free, instead of a half-built
        lightbox in a 420px window. store.resolve_attachment is what keeps this
        from being an arbitrary-file-launcher: the reference comes from a
        hand-editable task body.
        """
        project = _project(project_name)
        os.startfile(store.resolve_attachment(Path(project.path), reference))

    def complete_task(self, project_name, task_id):
        _, task = self._find(project_name, task_id)
        return _task_dict(store.complete_task(task), project_name)

    def reorder_bucket(self, project_name, bucket, ordered_ids):
        project = _project(project_name)
        store.reorder_bucket(Path(project.path), bucket, [int(i) for i in ordered_ids])

    def group_tasks(self, project_name, task_ids, name):
        """Put these tasks in that EXACT group. Use create_group for a seed."""
        project = _project(project_name)
        return groups.assign(Path(project.path), [int(i) for i in task_ids],
                             _text(name, "name"))

    def create_group(self, project_name, task_ids, seed):
        """Put these tasks in a NEW group named after `seed`, deduped."""
        project = _project(project_name)
        return groups.create(Path(project.path), [int(i) for i in task_ids],
                             _text(seed, "seed"))

    def ungroup_tasks(self, project_name, task_ids):
        project = _project(project_name)
        groups.remove(Path(project.path), [int(i) for i in task_ids])

    def rename_group(self, project_name, old, new):
        project = _project(project_name)
        return groups.rename(Path(project.path), _text(old, "old"), _text(new, "new"))

    def disband_group(self, project_name, name):
        project = _project(project_name)
        groups.disband(Path(project.path), _text(name, "name"))

    def set_group_bucket(self, project_name, name, bucket):
        project = _project(project_name)
        groups.set_bucket(Path(project.path), _text(name, "name"),
                          _text(bucket, "bucket"))

    def reset_to_open(self, project_name, task_ids):
        """Retract "in progress" for these tasks — see store.reset_to_open."""
        project = _project(project_name)
        wanted = [int(i) for i in task_ids]
        by_id = {t.id: t for t in store.list_tasks(Path(project.path))}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise ValueError(f"no such task in {project_name}: {missing}")
        return [_task_dict(store.reset_to_open(by_id[i]), project_name)
                for i in wanted]

    def copy_task_prompt(self, project_name, task_id):
        """The task's hand-off text, on the clipboard. Nothing is written.

        Takes the project by name rather than assuming the selected one, so
        this is safe from the search and all-projects views where a row can
        belong to any project (ids are per-project — invariant 6).
        """
        _, task = self._find(project_name, task_id)
        return launcher.copy_prompt([task])

    def _selected_tasks(self, project_name, task_ids):
        """The project and its tasks named by id, in the order the ids arrived.

        Shared by hand_off and suggest_session_name so there is exactly one
        id-to-task lookup — and exactly one unknown-id error — rather than two
        that could drift apart.
        """
        project = _project(project_name)
        wanted = [int(i) for i in task_ids]
        by_id = {t.id: t for t in store.list_tasks(Path(project.path))}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise ValueError(f"no such task in {project_name}: {missing}")
        return project, [by_id[i] for i in wanted]

    def hand_off(self, project_name, task_ids, name=""):
        if not isinstance(name, str):
            raise ValueError("name must be a string")
        project, tasks = self._selected_tasks(project_name, task_ids)
        # launch is the third positional on launcher.hand_off's own signature —
        # pass name as a keyword, or it lands in `launch` and spawns the wrong
        # process.
        prompt = launcher.hand_off(Path(project.path), tasks, project.launch,
                                   name=name)
        # After the hand-off, never before. launcher.hand_off saves the Task
        # objects above; grouping first would rewrite those same files and
        # leave these objects stale, so the save would silently discard the
        # group. Going second also means a session that failed to start leaves
        # nothing grouped, matching the guarantee that a failed spawn leaves
        # tasks untouched.
        #
        # That ordering is also why the group's name is not what renames the
        # session yet: auto_group cannot run before the name is needed. Wiring
        # the two together is a designed follow-up, not this merge's job — see
        # "Relationship to the task-groups design" in
        # docs/superpowers/specs/2026-07-25-session-identity-design.md.
        groups.auto_group(Path(project.path), [task.id for task in tasks])
        return prompt

    def suggest_session_name(self, project_name, task_ids):
        """What hand_off would `/rename` the session to if given no name.

        The frontend needs this for a placeholder, and computing the rule in
        JavaScript would be a second copy of launcher.session_name, free to
        drift from the one hand_off actually uses.
        """
        _, tasks = self._selected_tasks(project_name, task_ids)
        return launcher.session_name(tasks)

    def save_settings(self, payload):
        settings = registry.Settings(
            group_limit=int(payload["group_limit"]),
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
