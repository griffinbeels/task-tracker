"""pywebview window and the JS bridge. This module is wiring only."""

import os
from dataclasses import asdict
from pathlib import Path

# claude_console is the one dependency that lives OUTSIDE this repo, and a
# missing one fails harder than the others: it raises at import time, before
# main() and therefore before _report_fatal exists on any reachable path, and
# run.bat launches through pythonw.exe — so the whole app becomes a launcher
# that does nothing at all. No window, no console, no error, nothing to read.
#
# run.bat installs it (`uv pip install -e .`, which resolves the path source in
# pyproject.toml), so the realistic way to reach this is a worktree whose venv
# was built by hand without `-e .`.
try:
    import claude_console  # noqa: F401
except ImportError as missing:
    import ctypes

    ctypes.windll.user32.MessageBoxW(
        0,
        f"{missing}\n\n"
        f"The shared claude_console module is not installed in this "
        f"environment. From the checkout you launched:\n\n"
        f'    uv pip install --python ".venv\\Scripts\\python.exe" -e .',
        "Task Tracker", 0x10)
    raise

import webview

import groups
import inbox
import launcher
import migrate
import registry
import restart
import singleton
import store
import window_state


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


_DESTINATION_FIELDS = ("bucket", "group", "status")


def _destination(payload) -> dict:
    """The three fields a drop resolves to — refused rather than coerced.

    A key outside the three is an error, not something to ignore: a misspelled
    field would otherwise half-apply, and the drop would look like it worked
    while silently leaving out whichever part was typed wrong. A missing key
    means None, which every field reads as "unchanged" (see groups.place).

    Values go through _text for the reason it exists: a group name arriving
    from JS as a number would become the group "5" and look deliberate.
    """
    if not isinstance(payload, dict):
        raise ValueError("destination must be an object")
    unknown = sorted(set(payload) - set(_DESTINATION_FIELDS))
    if unknown:
        raise ValueError(f"unknown destination field(s): {unknown}")
    return {field: (None if payload.get(field) is None
                    else _text(payload[field], field))
            for field in _DESTINATION_FIELDS}


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
            "collapsed": registry.collapsed_view(),
            "in_progress_order": registry.in_progress_order(),
        }

    def set_collapsed(self, projects, groups):
        """Which group blocks and project headings are folded away.

        The renderer owns the whole set and sends it back wholesale — there is
        no per-item add/remove, so a fold and an unfold cannot race into
        disagreeing halves of one list.
        """
        pairs = []
        for pair in groups:
            if len(pair) != 2:
                raise ValueError("a collapsed group is [project, name]")
            pairs.append([_text(pair[0], "project"), _text(pair[1], "group")])
        registry.set_collapsed_view(
            [_text(name, "project") for name in projects], pairs)

    def set_in_progress_order(self, pairs):
        """The order of the IN PROGRESS list — see registry.in_progress_order.

        Entries are [project, block key], where a key is "group:<name>" or
        "task:<id>". Sent wholesale for the same reason set_collapsed is: the
        renderer owns the list, so two partial writes cannot race into
        disagreeing halves of it.
        """
        cleaned = []
        for pair in pairs:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise ValueError("an in-progress entry is [project, block key]")
            cleaned.append([_text(pair[0], "project"), _text(pair[1], "key")])
        registry.set_in_progress_order(cleaned)

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

    def _tasks(self, project_name, task_ids):
        """Task objects for these ids, in the order given, or a ValueError.

        Deduplicates while preserving first-seen order, so a repeated id acts
        once — the one addition over the four-line block this replaces at
        every bulk call site.

        Refuses anything but a real sequence of ids, rather than coercing it,
        following the precedent of _text above. A string is refused
        specifically even though it is technically a sequence: task_ids="12"
        would otherwise iterate as the characters "1" and "2" and silently
        resolve to tasks 1 and 2, which is exactly the wrong two ids for a
        bridge method (delete_tasks) that cannot be undone.
        """
        if isinstance(task_ids, str) or not isinstance(task_ids, (list, tuple)):
            raise ValueError("task_ids must be a list of ids, not a bare string")
        project = _project(project_name)
        by_id = {t.id: t for t in store.list_tasks(Path(project.path))}
        wanted = []
        seen = set()
        for task_id in task_ids:
            task_id = int(task_id)
            if task_id not in seen:
                seen.add(task_id)
                wanted.append(task_id)
        missing = [task_id for task_id in wanted if task_id not in by_id]
        if missing:
            raise ValueError(f"no such task in {project_name}: {missing}")
        return project, [by_id[task_id] for task_id in wanted]

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

    def restore_task(self, project_name, task_id):
        """Undo a completion — see store.restore_task for where it lands.

        Renumbered afterwards for the same domain rule delete_tasks and
        complete_tasks below spell out, arrived at from the other direction:
        those two hollow a bucket out, this one adds into a bucket already
        hollowed out by the completion it is undoing. Reread rather than
        returned straight from the store call, because the renumber can move
        the task's order again and the payload must say what is on disk.
        """
        project, task = self._find(project_name, task_id)
        restored = store.restore_task(task)
        groups.renumber(Path(project.path), restored.bucket)
        _, reloaded = self._find(project_name, task_id)
        return _task_dict(reloaded, project_name)

    # delete_tasks and complete_tasks below each pair a store.py mutation with
    # a groups.renumber call for every bucket it touched — a domain rule
    # ("removing tasks from a bucket obliges a renumber of that bucket"), not
    # wiring, even though the module docstring says this file is wiring only.
    # It lives here anyway: store.py must not import groups.py (groups.py
    # already imports store, and a cycle would follow), and completing a task
    # is not groups.py's concern either — so this bridge module is the only
    # one that already imports both and can call across that seam.
    def delete_tasks(self, project_name, task_ids):
        """Erase every file in this selection, then repair the buckets it hollowed out.

        The bucket set is captured before any file is touched: after a delete
        the task object is gone, so its bucket could not be read afterwards.
        """
        project, tasks = self._tasks(project_name, task_ids)
        buckets = {task.bucket for task in tasks}
        for task in tasks:
            store.delete_task(task)
        for bucket in buckets:
            groups.renumber(Path(project.path), bucket)
        return len(tasks)

    def complete_tasks(self, project_name, task_ids):
        """Move every task in this selection to done/, then repair the buckets.

        Same reason as delete_tasks for capturing buckets first: a completed
        task still reads its old bucket, but it is no longer live, so leaving
        it out of the renumber pass would leave a hole in the run.
        """
        project, tasks = self._tasks(project_name, task_ids)
        buckets = {task.bucket for task in tasks}
        for task in tasks:
            store.complete_task(task)
        for bucket in buckets:
            groups.renumber(Path(project.path), bucket)
        return len(tasks)

    def reorder_bucket(self, project_name, bucket, ordered_ids):
        # Refused rather than no-opped, matching update_task above: an unknown
        # bucket means the JS caller is wrong, and store.reorder_bucket skips
        # every id whose bucket does not match, so a typo here would silently
        # reorder nothing and look like it worked.
        if bucket not in store.BUCKETS:
            raise ValueError(f"unknown bucket: {bucket}")
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

    def reorder_group(self, project_name, name, ordered_ids):
        """Rearrange tasks inside one group — see groups.reorder_members."""
        project = _project(project_name)
        groups.reorder_members(Path(project.path), _text(name, "name"),
                               [int(i) for i in ordered_ids])

    def set_group_bucket(self, project_name, name, bucket):
        project = _project(project_name)
        groups.set_bucket(Path(project.path), _text(name, "name"),
                          _text(bucket, "bucket"))

    def place_task(self, project_name, task_id, destination, ordered_ids=None):
        """Where one dragged task landed — bucket, group and status together.

        One call rather than a sequence of update_task/group_tasks/
        reorder_bucket, because the states between those calls are ones no
        rule permits and a raise part-way through would leave one on disk.
        groups.place owns the domain checks; this refuses only what says the
        JS caller is broken, which is the same split update_task makes
        (invariant 23).

        `ordered_ids` is the destination bucket's full id list, read off the
        DOM after the live reorder, or omitted for a drop on a heading — which
        has no position in it and means "at the end".
        """
        project = _project(project_name)
        groups.place(Path(project.path), [int(task_id)],
                     ordered_ids=ordered_ids, **_destination(destination))

    def place_group(self, project_name, name, destination, ordered_ids=None):
        """Where a dragged group landed. Every member moves, always.

        A group lives in one bucket (invariant 16), so there is no such thing
        as moving part of one — a header reading "2 of 5" in IN PROGRESS still
        moves all five. That deliberately differs from the `done` button
        beside it, which acts on the two rows it drew: done completes tasks, a
        drag moves the group.

        Members are resolved by name from disk rather than sent by the
        renderer, so a list that went stale between the drag starting and the
        drop landing cannot leave part of a group behind.
        """
        project = _project(project_name)
        name = _text(name, "name")
        fields = _destination(destination)
        # A group IS its name (invariant 15). Moving one is not an opportunity
        # to rename it, and pointing it at another name would be the merge
        # that every other path here refuses.
        if fields["group"] is not None and fields["group"] != name:
            raise ValueError("a group drag cannot rename or merge the group")
        fields["group"] = name

        members = [task.id for task
                   in store.list_tasks(Path(project.path), include_done=False)
                   if task.group == name]
        if not members:
            raise ValueError(f"no group named {name} in this project")
        groups.place(Path(project.path), members,
                     ordered_ids=ordered_ids, **fields)

    def reset_to_open(self, project_name, task_ids):
        """Retract "in progress" for these tasks — see store.reset_to_open."""
        _, tasks = self._tasks(project_name, task_ids)
        return [_task_dict(store.reset_to_open(task), project_name)
                for task in tasks]

    def copy_task_prompt(self, project_name, task_id):
        """The task's hand-off text, on the clipboard. Nothing is written.

        Takes the project by name rather than assuming the selected one, so
        this is safe from the search and all-projects views where a row can
        belong to any project (ids are per-project — invariant 6).
        """
        _, task = self._find(project_name, task_id)
        return launcher.copy_prompt([task])

    def hand_off(self, project_name, task_ids, name=""):
        if not isinstance(name, str):
            raise ValueError("name must be a string")
        project, tasks = self._tasks(project_name, task_ids)
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
        # A group formed HERE cannot name the session, because it does not
        # exist yet when the name is chosen. A group the user selected already
        # does — see launcher.session_name, which reads it off the tasks.
        groups.auto_group(Path(project.path), [task.id for task in tasks])
        return prompt

    def suggest_session_name(self, project_name, task_ids):
        """What hand_off would `/rename` the session to if given no name.

        The frontend needs this for a placeholder, and computing the rule in
        JavaScript would be a second copy of launcher.session_name, free to
        drift from the one hand_off actually uses.
        """
        _, tasks = self._tasks(project_name, task_ids)
        return launcher.session_name(tasks)

    def save_settings(self, payload):
        # Both counts are refused below 1 rather than stored as given. An
        # emptied number input crosses the bridge as 0, and every reader of
        # these falls back through `x || 5` — so a stored 0 behaves as 5 while
        # the file claims otherwise, and nothing on screen shows the gap. The
        # settings panel checks this too; it lives here as well so the rule
        # belongs to the data rather than to one form.
        counts = {}
        for key in ("group_limit", "stale_days"):
            counts[key] = int(payload[key])
            if counts[key] < 1:
                raise ValueError(f"{key} must be 1 or more")
        settings = registry.Settings(
            **counts,
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

    # webview.screens initialises the GUI backend on first access, so it is
    # readable here, before there is a window to place. It is read again at
    # closing rather than reused: a monitor can be attached or unplugged while
    # the window is open, and what counts as a reachable position moves with it.
    geometry = window_state.load(webview.screens)
    window = webview.create_window(
        "Tasks",
        str(Path(__file__).parent / "ui" / "index.html"),
        js_api=Api(),
        width=geometry["width"], height=geometry["height"],
        x=geometry["x"], y=geometry["y"],
        on_top=geometry["on_top"],
    )
    window.events.closing += lambda: window_state.save({
        "width": window.width, "height": window.height,
        "x": window.x, "y": window.y, "on_top": window.on_top,
    }, webview.screens)
    # destroy() closes the window, which fires `closing` on the UI thread and
    # saves geometry there — the socket thread must not read window.x/width
    # itself, those properties are only safe to touch on the UI thread.
    singleton.serve(lock, window.destroy)
    webview.start()


if __name__ == "__main__":
    main()
