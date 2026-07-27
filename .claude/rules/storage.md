---
paths:
  - "store.py"
  - "registry.py"
  - "groups.py"
  - "inbox.py"
  - "migrate.py"
  - "window_state.py"
  - "singleton.py"
  - "restart.py"
  - "tests/test_store.py"
  - "tests/test_registry.py"
  - "tests/test_groups.py"
---

# Storage — task files, the registry, groups, and window state

Invariants 1, 7, 15, 16, 17, 20, 23 and 26, and what is on disk.

1. **Every `write_text` passes `newline="\n"`.** Windows otherwise translates
   `\n` to `\r\n`; a body containing `\r\n` then gains a blank line on every
   save. Reads deliberately use universal newlines so hand-edited CRLF files
   still parse — net behaviour is "line endings normalise to LF".

   **In practice that means going through `store.write_text_atomic`**, which is
   how every text file this app owns is now written — task files,
   `projects.json`, `settings.json`, `session.json`, `window.json`, inbox
   notes. It passes the newline for you, and it writes a sibling `.tmp` and
   `os.replace`s it over the target, so a crash cannot leave a file truncated
   to nothing: a plain `write_text` is a truncate followed by a write, and this
   machine has taken a bugcheck mid-session before. It also unlinks the temp
   file when the write raises — `.tasks/open/` is globbed for `*.md` and a
   surviving `0007-x.md.tmp` would read as a second copy of the task. A new
   writer that reaches for `write_text` directly is the way to reintroduce
   both problems at once.

7. **Reach `registry.CONFIG_DIR` through the module at call time.** Tests
   monkeypatch it; binding it into a module-level constant at import captures
   the real home directory and makes the suite write to the user's actual
   config. `_projects_file()` / `_settings_file()` / `inbox_dir()` are functions
   for this reason, and so is `window_state._state_file()`. There is no
   exception: `app.WINDOW_STATE` used to be one, and it was never as safe as its
   note claimed — `tests/test_app.py` does import `app.py`, and only a
   `monkeypatch.setattr(app, "WINDOW_STATE", ...)` in its fixture kept the suite
   off the real `~/.task-tracker/`.

15. **A group is its name.** There is no group id and no registry file, so a
    name must be non-empty and unique within a project, compared
    **case-insensitively** — otherwise "Editor polish" and "editor polish"
    quietly become two blocks the user reads as one. `groups.assign` joins
    *that exact* name and `groups.create` dedupes a *seed* into a fresh one;
    passing a seed to `assign` swallows the task into whatever group already
    answers to it. Renaming to a name another group holds, and merging two
    groups on spin-up, are both refused rather than guessed: a merge destroys
    one of the two names, and the name is the only identity a group has.

16. **A group lives in one bucket, and its members are contiguous in `order`.**
    Every membership change ends with `groups.renumber` on every bucket it
    touched — skip it and the group renders as two blocks with other rows
    wedged between them. The group header owns the bucket picker for the same
    reason; a member that could move on its own would render in two places at
    once. `Api.update_task` enforces both for anything that edits a single
    task: a bucket change on a member moves the whole group via
    `groups.set_bucket`, and an `order` aimed at a member is ignored. That
    lives in the bridge rather than in the editor so every writer inherits it,
    and it is skipped for a completed task, which keeps its `group` string in
    done/ but is not part of the group any more (invariant 15). The renderer is deliberately forgiving of a hand-edited file: a
    group's bucket and position come from its **lowest-order member**, and
    every member draws inside that block whatever its own `bucket:` line says.

17. **`session.json` is read-modify-write.** It holds `last_project` and the
    fold state, and it will hold the next piece of view state too. Replacing
    the file to set one key drops the others — `set_last_project` did exactly
    that, so a project switch would have silently unfolded everything. Go
    through `registry._update_session`.

20. **Window geometry is only trusted if a monitor can show it.** While a
    window is minimized Windows parks it at a sentinel rectangle — measured
    here as -32000,-32000 at 237x39 — and that is what pywebview reports for
    `window.x/y/width/height`. Saving it is unrecoverable rather than merely
    wrong: the next launch opens somewhere the user cannot reach, so they
    cannot move it anywhere better, and closing re-saves the same value
    forever. The only exit is deleting a JSON file nobody knows exists.
    `window_state.on_screen` is therefore checked on **both** sides of the
    trip: `save` keeps the previous position instead of overwriting it with the
    sentinel, and `load` discards a rectangle that overlaps no screen, which is
    what repairs a `window.json` that is already poisoned. The load-side check
    also covers a window left on a monitor that has since been unplugged —
    different cause, identical symptom. Overlapping a screen by any amount
    passes, and a negative coordinate is normal, not suspicious: a monitor to
    the left of the primary starts at a negative x.

23. **`Task.color` is always one of the eight `CLAUDE_COLORS` — parsing repairs
    it, the bridge refuses to.** `Task.__post_init__` replaces a missing,
    empty, or hand-edited-into-garbage colour with `CLAUDE_COLORS[id % 8]`, so
    nothing downstream — the `/color` argument, the renderer's hex lookup —
    ever has to defend against a bad value. `Api.update_task` and
    `Api.create_task` do the opposite on purpose: an out-of-range colour there
    means the JS caller sent something wrong, not that a file was hand-edited,
    so they raise instead of silently repairing it — repairing it there would
    hide the bug that produced it.

26. **A drop resolves to one destination, applied by one call.** A drag can
    change a task's bucket, its group and whether it is running, all in one
    gesture — and the states between those three changes are ones no rule
    permits. A task that has changed bucket but not yet left its group is a
    member sitting in the wrong bucket, which is invariant 16 broken; a
    sequence of `update_task` → `group_tasks` → `reorder_bucket` passes
    through that state on disk every time, and leaves it there if any step
    raises. `groups.place` applies the triple `{bucket, group, status}` with
    one write per task and renumbers **both** the source and destination
    buckets, so the intermediate state never exists. `Api.place_task` and
    `Api.place_group` are its only callers.

    Two rules inside it that a reader cannot infer. **An explicit bucket beats
    the group's**, which is what lets a group header dragged into `next` carry
    every member while a lone task dropped into that same group is instead
    pulled into the group's bucket — without the precedence, one of those two
    has to become a special case somewhere else. And **status is written only
    when it differs**: `store.reset_to_open` clears `started`, so releasing a
    half-running group would otherwise erase the start dates of the members
    that were never running. A task already in the destination group *and*
    bucket also keeps its `order`, or claiming one member would shunt it to
    the end of its own group.

## Data on disk

```
~/.task-tracker/projects.json   name -> path, tracked flag, launch override
~/.task-tracker/settings.json   group_limit (5), stale_days (90), task types,
                                zoom_whole_window (off), always_on_top (off)
~/.task-tracker/session.json    last_project, which groups/projects are folded,
                                the order of the IN PROGRESS list, and how far
                                each of the two regions is zoomed
~/.task-tracker/inbox/          untriaged raw notes
~/.task-tracker/session.json    last_project — restored on every launch
~/.task-tracker/window.json     window geometry
<project>/.tasks/.gitignore     contains `*` — the folder is invisible to git
<project>/.tasks/open/          NNNN-slug.md
<project>/.tasks/done/          the archive, and the progress view's source
<project>/.tasks/attachments/   pasted screenshots, YYYY-MM-DD-HHMMSS.png
```

A task file's frontmatter carries `id`, `title`, `type`, `color`, `bucket`,
`group`, `status`, `order`, `created`, `started`, `done` — `render_task`'s
`meta` dict is the single source of that key order, and `parse_task` is the
only reader of it.

`.tasks/` is **untracked by default** because several tracked repos are public
and committing would publish raw backlog prose. A per-project `tracked` flag
flips it (settings → the tracked checkboxes), which deletes that `.gitignore`.
Attachments live under the same `.gitignore` on the same terms, which is why
`store.save_attachment` calls `ensure_tasks_dir` before writing: creating the
directory tree without that file would publish a pasted screenshot on the next
commit.

Attachments are **never garbage-collected** — deleting a task leaves its images
behind. Reference counting across hand-editable files is not worth the
machinery here. Their absolute paths also make a task file **non-portable**
between machines, which only matters for a tracked project cloned elsewhere:
the images arrive, the paths do not resolve.

`store.next_task_id` is `max(ids, default=0) + 1` over open and done combined.
Before the selection bar, nothing ever removed a task, so ids only went up for
a project's whole life. `delete_tasks` unlinks files outright, so deleting the
newest task frees its id — the next task created can land on the same number.
Nothing breaks (ids are still unique among live tasks, and only ever meaningful
paired with a project — invariant 6), but a tracked repo's git history can now
show two unrelated tasks under one id at different points in time.
