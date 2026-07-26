# Copy a task as a prompt — design

**Date:** 2026-07-25
**Status:** approved

## The problem

`Spin up Claude` is the only way to get a task's text into Claude, and it does a
lot: it opens a console, rebuilds an environment, types into another process's
input buffer, and marks the task in-progress. Often all you want is the text —
to paste into a session that is already open, into a chat, or into a note.

## What it does

Every task row gets a copy button, revealed on hover, that puts

```
TYPE: <body>
```

on the clipboard — byte-identical to what `Spin up Claude` would type for that
one task. Nothing on disk changes.

## Where the text comes from

The backend, not the browser.

- `launcher.copy_prompt(tasks) -> str` — `build_prompt` then `pyperclip.copy`,
  returning what it copied.
- `Api.copy_task_prompt(project_name, task_id) -> str` — resolves the task via
  the existing `Api._find` and calls it.

`pyperclip` is already this app's clipboard (`hand_off` uses it), which makes
this testable under pytest with no browser and sidesteps any clipboard
permission question in a `file://` WebView2 document. The point of routing
through `build_prompt` rather than formatting in JS is that copy and hand-off
then share one prompt-building path, so their output cannot drift apart.

## Empty bodies fall back to the title

`build_prompt` currently emits a bare `FEATURE:` for a task with no body —
useless in the hand-off path too, not just this one. The fallback goes *in*
`build_prompt` so both paths get it, rather than special-casing copy and
forking the format.

This does not weaken invariant 2. The fallback picks a different verbatim
field; it does not strip, trim, re-wrap or append to any text.

## The button

An inline SVG copy glyph — the classic two overlapping sheets — placed just
before `done` in the row, reusing the hover pattern `.done` already has:
`opacity: 0`, rising to `.6` on `.task:hover`. Opacity keeps the button in
layout at all times, so hovering reveals it without shifting the title beside
it.

`pointer-events: none` on the SVG so the click target is always the `<button>`,
which `taskRow`'s existing `closest('input, select, button')` guard already
excludes from opening the editor.

On success the icon swaps to a check mark for ~1.2s, then reverts. That is the
only confirmation — no toast, and no element that appears or disappears.

The glyph is static markup with no user-authored text in it, so invariant 5
does not apply to it.

## It appears on every row

Including search results and the all-projects view. Those two disable selection
and editing because task ids are per-project and both of those paths resolve an
id against `currentProject` (invariant 6). Copy does not: it passes the row's
own `dataset.project`, so it names exactly the task the row shows. Archived
rows in search results get it too — copying a finished task's text is harmless.

## Status is untouched

Copy is a cheap gesture you might make to paste anywhere, or nowhere. Stamping
`started` and flipping `status` to `in-progress` on it would be surprising, would
count against the WIP warning, and would be awkward to undo. Only `hand_off`
and the editor change a task.

## Testing

- `tests/test_launcher.py` — `copy_prompt` copies exactly `TYPE: body`; the
  title fallback fires only for an empty body; the task file is untouched.
- `tests/test_app.py` — `copy_task_prompt` resolves the right task, raises on an
  unknown id, and leaves `status` / `started` alone.
- Frontend by hand, per CLAUDE.md: hover a row, copy, paste; confirm the title
  does not shift on hover; confirm clicking the button does not open the editor.

## Touch set

`launcher.py`, `app.py`, `ui/tasks.js`, `ui/style.css`, `tests/test_launcher.py`,
`tests/test_app.py`.
