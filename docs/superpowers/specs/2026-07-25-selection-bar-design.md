# The selection bar — design

**Date:** 2026-07-25
**Status:** approved (revised after task groups landed — see "Why there is no Move")

## The problem

Ticking task checkboxes does exactly one thing: it feeds `Spin up Claude`.
Everything else is per-row — a bucket picker, a done button, a copy button, an
editor. There is no way to act on several tasks at once, and the selection
itself is invisible: nothing on screen changes when you tick a box, so a
selection you made and forgot silently changes what the next spin-up sends.

And there is no way to delete a task at all. Not in `ui/`, not in `Api`, not in
`store.py`. `complete_task` moves the file to `done/`; nothing ever unlinks one.
A task written by mistake, or one that stopped mattering, can only be finished
— which puts it in the progress view as work you did.

## What it does

A bar appears under the toolbar when anything is ticked, and disappears when
the last box is cleared:

```
3 selected                        [Done] [Delete] [Clear]
```

It is the answer to both problems at once: the selection becomes visible, and
it gets somewhere to act from.

It is a real row in flow, not an overlay: the list moves down by the bar's
height when it appears. That displacement is the point — it is user-triggered,
it reads as a mode you are in, and it never covers a task the way a floating bar
pinned to the top of `NOW` would.

## Delete erases the file

`Delete` asks first — `confirm()` naming the count, saying it cannot be undone
— and then unlinks each `.md`. No trash folder, no undo, nothing to sweep up
later. This app replaces a notepad, and a page you tear out of a notepad is
gone.

**Attachments are left behind**, which is the existing documented decision that
they are never garbage-collected. Reference counting across hand-editable files
is not worth the machinery here, and it is no more true after this feature than
before it.

`confirm()` is the one thing in this design that has not been proven in
pywebview's WebView2 host. `alert()` is used throughout the app, so script
dialogs do render, but `confirm()` is a different path. If it is suppressed it
returns `false`, so the failure direction is safe: nothing is deleted. The
fallback, if it does not appear, is a two-step button in the bar itself
(`Delete` → `Delete 3?`, reverting after a few seconds) and no dialog.

## Done, and Clear

`Done` is `complete_task` over the batch — the row button applied to several
rows, with no new semantics.

`Clear` unticks everything. It is the bar's own way out: without it, undoing a
ten-row selection means ten more clicks. It is `quiet`-styled, because it is the
way out, not an action.

## Why there is no Move

The first version of this design had a `Move to…` picker in the bar. Task groups
landed underneath it and made that wrong.

A group is a set of tasks with the same `group` string, and `groups.py`
guarantees that a group's members all sit in **one** bucket and are contiguous
in `order` — the renderer depends on both. `groups.set_bucket` is documented as
"the only way a member changes bucket", and `taskRow` now hides the per-row
bucket picker entirely for a grouped row, because the group header owns the
bucket. A bulk Move would therefore have to either refuse whenever a grouped
task was ticked, or grow a case table for whole-group and partial-group
selections.

Neither is worth it, because nothing is missing. Bucket changes already have
exactly two controls, one per kind of thing: a loose task moves from its own row
picker, a group moves from its header picker. The bar is left doing only the two
things nothing else can do in bulk.

## Both actions repair the bucket afterwards

`groups.renumber(project_path, bucket)` is what keeps each group one contiguous
run of `order` values, and every function in `groups.py` calls it on the buckets
it touched. Removing tasks from a bucket — by deleting them or by completing
them — leaves holes, and a hole lets a loose task's `order` fall inside a
group's run, which is exactly what `renumber` exists to repair.

So `delete_tasks` and `complete_tasks` each call `groups.renumber` for every
bucket they took a task out of. It is idempotent and only writes the tasks whose
`order` actually moved, so it stays quiet in `git status` for a tracked project.

The per-row `done` button does not do this today. That is pre-existing and out
of scope here; the bulk path is where the holes get big enough to matter.

## Where the code lives

A new `ui/selection.js`, loaded after `groups.js`.

`ui/tasks.js` is at 291 lines against this project's ~300-line split point, and
the selection bar is its own concern: what is ticked, and what you can do to it.

`selectedIds()` and the `spin-up` handler stay in `tasks.js`. One shared helper
goes the other way — `selection.js` defines

```
selectedInOneProject() -> { project, ids } | null
```

which returns the single project a selection belongs to, falling back to
`currentProject` when nothing is ticked, and returns `null` after alerting on a
mixed-project selection. `spin-up` is refactored onto it, so the rule that
guards invariant 6 exists once instead of three times.

That makes `tasks.js` call a function defined in the file *after* it, which is
fine and is how the rest of this project already works: the handler is assigned
at load, but its body resolves `selectedInOneProject` when the button is
clicked, long after every script has loaded.

## Showing and hiding

`renderSelectionBar()` reads `selectedIds()`, sets the count, and hides the bar
at zero. It is called from `render()` and from **one delegated `change`
listener on `#task-list`**, guarded on `.select` so neither the row's bucket
picker nor a group header's picker triggers it. Delegation is what makes this
survive `replaceChildren` — a per-row listener would have to be re-attached on
every render.

A group header's `select-group` checkbox ticks its members by setting
`.checked` in JS, which does **not** fire a `change` event. The bar would
therefore not notice a whole group being selected. `groups.js`'s existing
`selectAll.onchange` handler gets one line added to call `renderSelectionBar()`
after it sets the rows.

The bar needs `#selection-bar[hidden] { display: none }`. It carries the
existing `.actions` class for its button styling and 28px control height, and
`.actions` sets `display: flex`, which a bare `hidden` attribute loses to on
equal specificity. `style.css` documents this same trap twice already, for
`.overlay` and `.chips`.

**Selection stays ephemeral.** Every `refresh()` rebuilds the rows with fresh
unticked boxes, so acting on a batch clears it and the bar goes away. That is
the wanted behaviour, and it is what the code already does rather than something
this feature has to add.

The bar therefore never appears in the search or all-projects views: both
disable `.select`, so nothing can be ticked and `selectedIds()` returns empty.

## The backend

Two bridge methods, each returning the number of tasks it acted on:

| Method | Does |
|---|---|
| `Api.delete_tasks(project_name, task_ids) -> int` | unlinks each file, then renumbers |
| `Api.complete_tasks(project_name, task_ids) -> int` | `store.complete_task` over the batch, then renumbers |

They share a new `Api._tasks(project_name, task_ids) -> (Project, list[Task])`,
mirroring the existing `_find`: it resolves the project, raises on an id that
does not exist in it, **deduplicates while preserving order**, and returns the
tasks in the order the ids arrived.

`hand_off` and `reset_to_open` are refactored onto it. Both already carry that
lookup inline, character for character — the same four lines building `by_id`,
collecting `missing`, and raising. Three copies of a rule is the point at which
it should be one.

In `store.py`, one new function beside `complete_task`:

- `delete_task(task) -> None` — unlinks `task.path`, raising if the task has no
  path, exactly as `save_task` and `complete_task` do.

The count return values are non-null on success, but note that a count is falsy
at zero — the handlers compare against `API_FAILED`, never truthiness
(invariant 4). A backend `ValueError` already reaches the user as an alert
through `callApi`, so no handler needs its own error copy.

## What this does not do

- **No select-all.** Group headers already tick their members; a global
  select-all in this bar would be a second answer to the same question.
- **No bulk type change.** Type is the one field with no per-row control, but
  the editor already does it one task at a time.
- **No undo.** See above — the confirm is the guard.
- **No move.** See above — groups own bucket changes.

## The other features in flight

This branch is based on `feature/task-groups` at `6ea6523`, not on `main`, and
`feature/session-identity` is a third branch in a third worktree. Task groups is
through Task 7 of 11 of its plan; **Task 9 has not landed and adds the IN
PROGRESS section, whose rows are selectable across projects.** That is why every
action here goes through `selectedInOneProject()` rather than reading
`currentProject` — when Task 9 lands, that helper is the single place the rule
changes.

Merge `feature/task-groups` into this branch once it completes and before
implementing anything that touches selection semantics.

## Testing

- `tests/test_store.py` — `delete_task` removes the file; a task with no path
  raises; the project's attachments are left alone.
- `tests/test_app.py` — `delete_tasks` and `complete_tasks` each return their
  count and act on the right files; an unknown id raises on both; duplicate ids
  act once; `delete_tasks` leaves other projects untouched; both leave the
  touched bucket's `order` values contiguous when a grouped task is removed;
  `hand_off` and `reset_to_open` still behave exactly as their existing tests
  assert after the `_tasks` refactor.
- Frontend by hand, per CLAUDE.md: tick a box and confirm the bar appears and
  the list moves down without a scrollbar; untick and confirm it goes; tick a
  group header's select-all and confirm the count reflects every member;
  confirm the delete dialog actually renders in the pywebview window; confirm
  the bar never appears in the search or all-projects views.

## Touch set

`store.py`, `app.py`, `ui/selection.js` *(new)*, `ui/tasks.js`, `ui/groups.js`,
`ui/index.html`, `ui/style.css`, `tests/test_store.py`, `tests/test_app.py`,
`CLAUDE.md`.
