# A completed task is still a task

2026-07-25

## The problem

Completing a task is one-way. `store.complete_task` moves the file to `done/`,
and nothing in the codebase moves one back — `reset_to_open` sounds like it
would, but it retracts *in-progress*, and both of those states live in `open/`.

The progress view compounds it. It renders finished tasks as plain `<div>`s
carrying a type tag, a title and an optional `## Outcome`; the body, the
colour, the group and the bucket are all on disk and none of them are
reachable. A task you finished is a row of text you can read and nothing else.

So a mis-click on `done` — and this app is about to grow a button that
completes five tasks at once — is unrecoverable through the UI. The only exit
is moving a file by hand.

## What ships

A completed task opens in the normal editor from the progress view, with
everything on it, and can be restored to where it came from.

## `store.restore_task`

The mirror of `complete_task`, and it can follow that function's shape exactly,
including how it recovers the project root from `task.path.parent.parent.parent`.

```
restore_task(task) -> Task
```

- moves the file `done/` → `open/`
- `status = "open"`, `done = None`
- `order` = the end of its bucket, counted over that bucket's open tasks
- raises `ValueError` if the task has no path, as `save_task` and
  `complete_task` already do

**`bucket` is not touched, because it never was.** `complete_task` leaves it
alone, so a finished task still remembers where it lived and restoring returns
it there. Landing at the *end* rather than reclaiming its old `order` is
deliberate: the tasks it sat among have moved on without it, and silently
inserting it back into the middle of a list the user has since reordered is a
change they did not ask for.

`Api.restore_task(project_name, task_id) -> dict` — `_find`, then
`store.restore_task`, returning `_task_dict`. Singular, matching
`complete_task`; nothing restores in bulk.

## The editor opens it

Progress rows become clickable and call `openEditor({ mode: 'edit', … })` with
the task's fields — the same overlay, no second mode, no read-only variant.

A `Restore` button joins the action row through the existing
`showEditorActions` list, shown only when the task being edited has
`status === 'done'`. `taskRow` already passes `status` into the editor context,
so the editor can already tell; the progress view passes it the same way.

Two things verified rather than assumed:

- **Editing a completed task already works end to end.** `Api.update_task`
  resolves it through `_find`, which lists `done/` as well, and
  `store.save_task` writes to whatever path the task holds — so a save lands
  back in `done/`, correctly. `update_task`'s group enforcement already
  special-cases `task.status == "done"`, so editing a finished task cannot drag
  its still-open former siblings between buckets.
- **Invariant 13 still holds.** The body is written only when it differs from
  the editor's own normalised baseline, so opening a finished task to read it
  and closing again rewrites nothing.

## The progress list must not keep showing a restored task

The progress body is currently built inside the `progress-button` click
handler, so there is no way to redraw it. That rendering moves into a function
the restore path can call again.

Restoring therefore: closes the editor, `await refresh()`, **then** redraws the
progress list. Closing the whole progress overlay would also be correct but is
abrupt — you asked to restore one task, not to leave the view.

**The order is load-bearing.** The progress list is derived from `state.tasks`,
and `refresh()` is what reloads it. Redrawing first would filter the state that
still contains the restored task as `done`, so it would draw the row it just
removed. The same mistake in the triage save path — rendering before
refreshing — was caught in review on 2026-07-25 and cost a colour suggestion
computed against a task list missing the task just filed.

## Testing

- `store.restore_task` moves the file out of `done/` and into `open/`; the old
  path is gone and the new one exists.
- It sets `status` to `open` and clears `done`.
- It lands the task at the end of its own bucket, not at its old `order`, and
  does not disturb the order of the tasks already there.
- It raises on a task with no path.
- A `complete_task` → `restore_task` round trip leaves the task in `open/` with
  the same id, title, body, type, colour, group and bucket it started with —
  the point of the feature is that nothing else changes.
- `Api.restore_task` returns the task dict with `project` set and no `path`
  key, and raises on an unknown id.

Frontend by hand, per this project's standing decision:

- Complete a task, open Progress, click it — the editor opens with its body,
  type, colour and bucket intact.
- Press Restore — it leaves the progress list, reappears at the bottom of its
  original bucket, and the editor closes.
- Open a completed task, change nothing, close — `git status` in a tracked
  project shows no diff at all.
- Open a completed task, edit its body, save — the change lands and the file
  stays in `done/`.

## Files touched

`store.py`, `app.py`, `ui/settings.js`, `ui/editor.js`, `ui/index.html`,
`tests/test_store.py`, `tests/test_app.py`, `CLAUDE.md`.

## Deliberately not built

- **Bulk restore.** Nothing needs it; `complete_task`'s counterpart is
  singular.
- **A hover `↩` on the progress row.** Restoring is a decision made after
  reading, and a one-click un-complete on a list you are scrolling is the same
  mis-click hazard in the other direction.
- **An undo for restore.** `done` is right there.
