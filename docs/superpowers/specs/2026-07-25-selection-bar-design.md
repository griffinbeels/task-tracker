# The selection bar — design

**Date:** 2026-07-25
**Status:** approved

## The problem

Ticking task checkboxes does exactly one thing: it feeds `Spin up Claude`.
Everything else is per-row — one bucket picker, one done button, one copy
button, one editor. There is no way to act on several tasks at once, and the
selection itself is invisible: nothing on screen changes when you tick a box,
so a selection you made and forgot silently changes what the next spin-up
sends.

And there is no way to delete a task at all. Not in `ui/`, not in `Api`, not in
`store.py`. `complete_task` moves the file to `done/`; nothing ever unlinks one.
A task written by mistake, or one that stopped mattering, can only be finished
— which puts it in the progress view as work you did.

## What it does

A bar appears under the toolbar when anything is ticked, and disappears when
the last box is cleared:

```
3 selected              [Move to… ▾] [Done] [Delete] [Clear]
```

It is the answer to both problems at once: the selection becomes visible, and
it gets somewhere to act from.

Four controls plus a count is the most this row can carry at the window's
default 420px, and it has not been measured — if it wraps, `Clear` is the first
thing to drop. It is a real row in flow, not an overlay: the list moves down by
the bar's height when it appears. That displacement is
the point: it is user-triggered, it reads as a mode you are in, and it never
covers a task the way a floating bar pinned to the top of `NOW` would.

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

## Move appends, in the order you see

Selected tasks land at the **end of the target bucket, in their current
relative order** — which is DOM order, top to bottom, because `selectedIds()`
reads the document. This is the same rule the per-row bucket picker already
follows for one task, and the same rule the editor follows when a save changes
the bucket; three controls doing the same thing must agree.

A task already in the target bucket is repositioned to the end along with the
rest, rather than being skipped. Skipping it would mean a batch of three
arrives split, some at the end and one wherever it was.

Tasks left behind in the source bucket keep their `order` values and therefore
have gaps. That is already true of `complete_task` and is harmless: the list
sorts on `order`, it does not index by it.

The control is a `<select>` with a disabled `Move to…` placeholder, matching
the per-row picker's idiom, and it resets to the placeholder after each use so
it never reads as a statement about what the selection currently is.

## Done, and Clear

`Done` is `complete_task` over the batch — the row button applied to several
rows, with no new semantics.

`Clear` unticks everything. It is the bar's own way out: without it, undoing a
ten-row selection means ten more clicks. It is `quiet`-styled, because it is the
way out, not an action.

## Where the code lives

A new `ui/selection.js`, loaded between `tasks.js` and `editor.js`.

`ui/tasks.js` is at 247 lines against this project's ~300-line split point, and
the selection bar is its own concern: what is ticked, and what you can do to it.
Putting it in `tasks.js` would push that file over the line for a feature that
does not belong to the task list.

`selectedIds()` and the `spin-up` handler stay in `tasks.js`. `selection.js`
calls `selectedIds()` at call time, which is the cross-file pattern this project
already relies on (`triage.js` calls into `editor.js`, `editor.js` reads
`triage.js`'s queue).

One shared helper moves the other way. `selection.js` defines

```
selectedInOneProject() -> { project, ids } | null
```

which returns the single project a selection belongs to, falling back to
`currentProject` when nothing is ticked, and returns `null` after alerting on a
mixed-project selection. `spin-up` is refactored onto it, so the rule that
guards invariant 6 exists once instead of four times.

That makes `tasks.js` call a function defined in the file *after* it, which is
fine and is how the rest of this project already works: the handler is assigned
at load, but its body resolves `selectedInOneProject` when the button is
clicked, long after every script has loaded.

## Showing and hiding

`renderSelectionBar()` reads `selectedIds()`, sets the count, and hides the bar
at zero. It is called from `render()` and from **one delegated `change`
listener on `#task-list`**, guarded on `.select` so the row's bucket picker does
not trigger it. Delegation is what makes this survive `replaceChildren` — a
per-row listener would have to be re-attached on every render.

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

Three bridge methods, each returning the number of tasks it acted on:

| Method | Does |
|---|---|
| `Api.delete_tasks(project_name, task_ids) -> int` | unlinks each file |
| `Api.complete_tasks(project_name, task_ids) -> int` | `store.complete_task` over the batch |
| `Api.move_tasks(project_name, task_ids, bucket) -> int` | the append rule above |

They share a new `Api._tasks(project_name, task_ids) -> (Project, list[Task])`,
mirroring the existing `_find`: it resolves the project, raises on an id that
does not exist in it, **deduplicates while preserving order**, and returns the
tasks in the order the ids arrived. `hand_off` is refactored onto it — it
already does this lookup inline, and the dedup is a no-op for it in practice
since `selectedIds()` reads one checkbox per row.

In `store.py`:

- `delete_task(task) -> None` — unlinks `task.path`, raising if the task has no
  path, exactly as `save_task` and `complete_task` do.
- `move_tasks(project_path, tasks, bucket) -> list[Task]` — validates the
  bucket, counts the target bucket's members that are *not* in the batch, and
  numbers the batch from there. Excluding the batch from that count is what
  keeps two tasks from being given the same `order` when one of them was already
  in the target bucket.

The count return values are non-null on success, but note that a count is
falsy at zero — the handlers compare against `API_FAILED`, never truthiness
(invariant 4).

## What this does not do

- **No select-all.** The task-groups design gives each group header a checkbox
  that ticks its members; a global select-all in this bar would be a second
  answer to the same question.
- **No bulk type change.** Type is the one field with no per-row control, but it
  is a fourth control in a 420px row and the editor already does it one task at
  a time.
- **No undo.** See above — the confirm is the guard.

## Interaction with the task-groups design

`docs/superpowers/specs/2026-07-25-task-groups-design.md` is written but not
implemented, and it is built on selection: group headers tick their members,
and spin-up auto-groups what was ticked. Two consequences for this feature.

First, `selection.js` is the obvious home for a future `Group` button, which is
part of why the bar is its own file rather than a block in `tasks.js`.

Second, that design makes the IN PROGRESS section selectable **across
projects**, which this design must not assume away. Hence
`selectedInOneProject()` rejecting a mixed selection with the same message
`spin-up` already uses, rather than reading `currentProject` and hoping. When
groups lands, that helper is the single place the rule changes.

Both features modify `app.py`, `store.py`, `ui/index.html` and `ui/style.css`.
Nothing here should be built in a worktree at the same time as the groups plan
without checking those four files.

## Testing

- `tests/test_store.py` — `delete_task` removes the file and leaves the
  project's attachments alone; `move_tasks` appends in the given order at the
  end of the target bucket; `move_tasks` over a batch that includes tasks
  already in the target bucket produces no duplicate `order` values; an unknown
  bucket raises.
- `tests/test_app.py` — each of the three methods returns its count and acts on
  the right files; an unknown id raises on all three; duplicate ids are handled
  once; `delete_tasks` leaves other projects untouched.
- Frontend by hand, per CLAUDE.md: tick a box and confirm the bar appears and
  the list moves down without a scrollbar; untick and confirm it goes; confirm
  the delete dialog actually renders in the pywebview window; move two tasks and
  confirm both land at the bottom of the target bucket in the order they were
  in; confirm the bar never appears in the search or all-projects views.

## Touch set

`store.py`, `app.py`, `ui/selection.js` *(new)*, `ui/tasks.js`, `ui/index.html`,
`ui/style.css`, `tests/test_store.py`, `tests/test_app.py`, `CLAUDE.md`.
