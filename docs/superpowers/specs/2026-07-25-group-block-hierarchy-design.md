# The group block: done, alignment, and a hierarchy that reads

2026-07-25

Three faults in the same block of UI, all small, all in `ui/groups.js`,
`ui/inprogress.js` and `ui/style.css`. They ship together because they are one
question — does the tree read as a tree — not because they are one mechanism.

## 1. A group can be marked done

A task row has a `done` button. A group header does not, so finishing a group
means clicking `done` on every member, or ticking them all and using the
selection bar.

**A `done` button joins the group header**, in bucket sections and in
IN PROGRESS, and completes exactly the members drawn under that header.

- It sits between `↩` and `×`, so the two "change these tasks" actions are
  adjacent and "unmake the group" stays last. Bucket sections have no `↩`, so
  there it reads `[bucket] [done] [×]`.
- Hover-revealed on `.group-header:hover` with `opacity: 0 → .6`, exactly as
  the row's `done` is on `.task:hover`. Opacity, never `display` — the control
  stays in layout, so hovering never shifts the name beside it.
- It needs `releaseDragWhileUsing(done, header)`. The header is draggable in
  bucket sections, and without that a mousedown on the button starts a drag
  instead of a click. Every other header control already does this.

**Scope is what the header drew.** `block.tasks`, not the whole group. In
IN PROGRESS a header can read `2 of 5`; `done` completes those 2 and leaves the
other 3 in their bucket with the group intact. This is what the `↩` beside it
already does — it resets `block.tasks` — so the two header actions agree, and
what you see is what you act on.

**The confirmation is not reimplemented.** The selection bar's `Done` already
asks above `DONE_CONFIRM_THRESHOLD` (3) with a specific dialog, and already
handles a failure mode that is easy to miss: `Api.complete_tasks` validates
every id up front but then acts file-by-file, so a failure partway through can
leave earlier tasks already moved to `done/` — its handler refreshes anyway so
the list stops drawing rows for files that are gone. That whole body is
extracted into one function in `ui/selection.js`, beside `selectedInOneProject()`,
and both callers use it. A second copy that forgot the partial-failure refresh
would leave the UI showing tasks that no longer exist.

`ui/selection.js` is the home because it is already the "act on many tasks at
once" module and already exports a helper `tasks.js` calls. `groups.js` loading
before it does not matter: references resolve at call time.

**Completing every member empties the group, so the block disappears.** A group
is derived from its open and in-progress members only (invariant 15). The
members keep their `group` string in `done/`, so the archive stays meaningful.
That is the intended outcome, not something to guard against.

## 2. The group's checkbox is two pixels right of its siblings

Measured, not guessed:

```
.task          padding-left: calc(6px + var(--caret-gutter))  = 21px
.group-header  padding-left: calc(6px + var(--caret-gutter))  = 21px
.group         border-left: 2px
```

A group header is a sibling of a top-level task row and both intend their
checkbox at 21px. The group's 2px left border is a real box-model edge, so
everything inside it starts at 23px.

**Fix: draw the rail with `box-shadow: inset 2px 0 0` instead of
`border-left`.** Identical appearance, zero layout space, and the two line up
exactly. `.group > .task { margin-left: var(--caret-gutter) }` still gives
members their one level of indent.

Adjusting the header's padding instead would work for the header and leave the
members 2px off, trading a visible misalignment for a subtler one.

## 3. The hierarchy is inverted

| | now | |
|---|---|---|
| project heading | 10px, opacity .45 | weakest |
| group name | 13px, weight 600 | **strongest** |
| task title | 13px, weight 400 | |

The project — the outermost container — is the faintest thing in its own
section, and the group nested inside it is the boldest.

**The rule: the label chain shrinks with depth; task titles are content and sit
outside that chain.** This is already how the app works — `NOW` and
`IN PROGRESS` are 10px dim labels while task titles are 13px. Without the
exemption, "smaller as you go deeper" eventually makes the text you actually
read the smallest on screen.

| | proposed |
|---|---|
| section (`IN PROGRESS`, `NOW`) | 10px, .1em tracking, opacity .5 — unchanged |
| project heading | **12px, weight 700, opacity .85** |
| group name | **11px, weight 600, opacity .7** |
| task title | 13px, weight 400, opacity 1 — unchanged |

Project beats group on size, weight *and* opacity rather than resting on one
cue. Project names stay sentence case: `task_tracker` is a folder name, and
uppercasing it would misrepresent what it is.

`.group-name-input` — the rename box — must match `.group-name`'s new size and
weight, or renaming a group visibly resizes its own text mid-edit.

## Testing

`Api.complete_tasks` already exists and is covered; this design adds no backend
and therefore **no Python tests**. That is a fact about the change, not an
omission. The gate is `tests/test_conventions.py` plus these by-hand checks,
which go into `CLAUDE.md`:

- A group of 2 → `done` completes both with no prompt, and the block goes.
- A group of 5 → `done` asks first; Cancel leaves all five untouched.
- In IN PROGRESS, a header reading `2 of 5` → `done` completes 2; the other 3
  stay in their bucket and the group survives.
- A group header's checkbox lines up exactly with a top-level task row's.
- Dragging a group by its header still works, and pressing `done` does not
  start a drag.
- A project heading reads as more important than a group header inside it,
  which reads as more important than a task title's label furniture.

## Files touched

`ui/groups.js`, `ui/selection.js`, `ui/style.css`, `CLAUDE.md`.
