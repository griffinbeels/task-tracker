# Task groups, and a limit that counts them

2026-07-25

A group is a set of tasks in one project that will be handed to **one** Claude
session. It is the unit the WIP limit counts, the unit the IN PROGRESS section
displays, and the unit you select with one click. Everything below follows from
that sentence.

## What is wrong today

Three separate problems, one of which is a live bug.

**The banner counts what the list cannot show.** `renderWipWarning` in
`ui/state.js` counts `status === 'in-progress'` across *every* registered
project, while `tasksFor` in `ui/tasks.js` only ever renders `currentProject`.
"8 tasks in progress" therefore includes tasks in projects you are not looking
at. Even the ones in view are unmarked: `taskRow` has no branch for
`in-progress`, so they sit in `now`/`next`/`someday` looking like every other
row. The count is right and there is nothing on screen to reconcile it against.

**Nothing can leave `in-progress`.** `launcher.hand_off` is the only writer of
that status, and there is no reader that can undo it. A session you abandoned
leaves its tasks in-progress forever, which is how thirteen accumulated.

**The limit counts the wrong noun.** Ten tasks handed to one session is one
Claude window, not ten. The limit models concurrent sessions, so it must count
groups.

## The data model

`store.Task` gains one field:

```yaml
---
id: 12
title: chips rewrite the row
type: BUG
bucket: now
group: Editor polish      # new; null when the task is not in a group
status: open
order: 3
created: 2026-07-25
started: null
done: null
---
```

`group` is `str | None`, parsed with `.get` so every existing task file stays
valid with no migration, and emitted by `render_task` as `group: null` when
absent — the same shape `started` and `done` already use.

**A group is its name.** There is no group id, no `groups.json`, no second
source of truth. Two tasks are in the same group if and only if they are in the
same project and their `group` strings are equal. This is what the design buys:

- No orphan references. A hand-edited file cannot point at a group that does
  not exist, because naming one *is* creating one.
- Deleting the last member deletes the group, with nothing left to clean up.
- A completed task keeps its group in `done/`, which stays meaningful.
- Renaming rewrites every member's file — the identical sweep `migrate.py`
  already performs for a type rename.

The costs, which are accepted:

- A group name must be non-empty. An unnamed group has no identity.
- Names must be unique within a project, compared **case-insensitively**, so
  "Editor polish" and "editor polish" cannot both exist and quietly split what
  the user reads as one group.
- Renaming touches N files instead of one. At the scale this app operates on,
  that is not a consideration.

`migrate.py` needs no change: `_sweep` parses a task, edits `type`, and saves,
so `group` round-trips as soon as `Task` carries it. `tests/test_conventions.py`
needs no change either — it globs `*.py` and `ui/*.js`, so new modules are
covered by the newline and `API_FAILED` conventions automatically.

## What must be true of a group

These are the invariants the implementation enforces and the renderer relies on.

1. **One group, one bucket.** Every member shares the group's bucket. The
   **group header owns the bucket dropdown**; child rows do not have one.
   Changing it moves every member. This is what makes "one group = one Claude
   session" true rather than aspirational.

2. **Members are contiguous in `order`.** After any group mutation, the
   affected bucket is renumbered: build one block per group (keyed by its
   lowest member `order`) and one block per ungrouped task (keyed by its own
   `order`), sort blocks by key with `id` breaking ties, sort members within a
   block the same way, then assign `order` `0..n-1` across the flattened
   result. Deterministic, idempotent, and it repairs a hand-edited file rather
   than arguing with it.

3. **Rendering derives the group's position and bucket from its lowest-order
   member, and renders every member inside that block regardless of that
   member's own `bucket` field.** Files are hand-editable; without this rule a
   group split across two buckets would render twice.

4. **A task joining a group takes the group's bucket** — read before the join,
   from the group's lowest-order existing member — and lands at the end of the
   group. When the group is *new*, its bucket is that of the first task in the
   assignment, and any others follow it.

5. **A group is derived from its open and in-progress members only.** Completed
   tasks keep their `group` string in `done/` but are not part of the group the
   renderer draws, so finishing a member shrinks the group rather than leaving
   a row behind.

6. **Grouping never crosses projects.** Ids are per-project (invariant 6 in
   `CLAUDE.md`), and so is a group name.

## Gestures

### Forming a group

Drag gets three zones instead of one. Within a bucket section:

| Where you drop | What it means |
|---|---|
| Top or bottom quarter of a top-level row | reorder (an insertion line, as today) |
| Middle half of a top-level row | **group with that row** — the target outlines |
| Anywhere on a group's header or between its child rows | **join that group**, at that position |
| A gap between top-level blocks, from inside a group | **leave the group** |

The last two rows are why the group container is joining territory throughout
rather than only in the middle band: dropping between two child rows would
otherwise write an `order` that interleaves a non-member into the group's
contiguous range, and invariant 2's renumber would then silently eject it below
the block. Making the whole container mean "join" removes the case.

Drag stays within one bucket section, as it does today — the bucket dropdown is
how a task changes bucket.

Group headers drag as a block, reorder-only. **Dropping a group onto another
group does not merge them**, because merging two named things silently destroys
one of the names.

### Naming

On creation the group takes the dropped-onto task's title as its name, and the
header's name box opens **focused with the text selected** — type the real name
immediately, or click away to keep the seed. If that seed collides with an
existing group in the project, ` 2`, ` 3`… is appended until it does not.

This fires **only when the group is born**, never when a later task joins one.
That is `CLAUDE.md` invariant 11 applied to a new field: a suggested value is
written once, into an untouched box.

Renaming later: click the name. Enter or blur commits; Escape reverts. An empty
name reverts to the previous one. A name that collides with another group in
the project is refused with an alert naming the conflict, and the box keeps
focus and the attempted text so it can be fixed rather than retyped.

### Disbanding and leaving

The header carries an `×` that disbands the group in place: every member's
`group` is cleared, and they keep their positions. This is the undo for a
mis-drag, and the reason drag-out does not have to be the only way back.

### Selecting

The header carries a checkbox that ticks or unticks every member at once. Its
own checked state is derived from the members: checked when all are ticked,
unchecked otherwise. This is the "one button to select the whole group" that
makes spinning up a session from a pre-made group a two-click operation.

### Drop → API sequence

A **grouping** drop does not send a reorder. The DOM has not moved the dragged
row next to its new group at that point, so sending DOM order would write the
old positions; the backend's renumber (invariant 2) places it correctly
instead. So: call the grouping method, then `refresh()`.

A **reorder** drop moves the DOM live as today and sends `reorder_bucket` with
the resulting ids. A **drag-out** is a reorder that first calls the ungroup
method — `reorder_bucket` then runs last and wins, which is correct because the
DOM is what the user just saw.

## The IN PROGRESS section

A section above `NOW`, spanning **all projects**, split by project heading, with
groups inside each project. In-progress tasks are **removed from their bucket
sections** so nothing appears in two places.

```
IN PROGRESS · 4 GROUPS

  task_tracker
  ┌ ☐ Editor polish        2 of 5   [↩]
  │   ☐ BUG  editor drops the title  [↩]
  │   ☐ BUG  chips rewrite the row   [↩]
  └
    ☐ FEATURE  group limit counts groups   [↩]

  marelo
    ☐ BUG  rank-up popup is too fast       [↩]
```

`↩` is **"not actually in progress"**: status back to `open`, `started`
cleared, and the task reappears in whatever bucket it came from — `bucket` was
never touched while it was in progress, so the return costs nothing. `started`
is cleared rather than kept because the claim being retracted is that the task
was ever started. It sits on each row, revealed on hover exactly as `done`
already is, and on the group header for every member at once.

**`2 of 5`** appears when only part of a group is in progress, which happens
when a subset is ticked and spun up. The denominator is the group's whole
membership excluding completed tasks, per invariant 5. The same group name then
legitimately appears both here and in a bucket section below; without the
fraction that reads as a rendering fault rather than as the true state. The
block left behind in the bucket section carries the mirror-image label —
`3 of 5` — for the same reason.

An ungrouped in-progress task renders as a bare row under its project heading —
no header, no rail. It is a group of one, and drawing a container around it
would claim otherwise.

Rows in this section **are** selectable, including rows from projects other than
`currentProject`: `selectedIds()` already carries each row's own project, and
`spin-up` derives its target project from the selection rather than from
`currentProject`, rejecting only mixed-project selections. Row-click-to-edit
stays disabled for foreign rows — resolving an id against the wrong project is
the actual hazard.

`CLAUDE.md` invariant 6 is reworded accordingly: from "any view spanning
projects must disable selection" to what it has always meant — **never resolve
a task id against `currentProject`; a row's project comes from its own
`dataset.project`.** Search and the all-projects view keep selection disabled,
because there a row's project is not visible in the layout.

Drag is disabled throughout this section. Reordering a running session means
nothing.

## The limit counts groups

`renderWipWarning` counts **distinct `(project, group)` pairs** among
in-progress tasks; each ungrouped in-progress task counts as one. The banner
reads:

```
7 groups in progress — over your limit of 5
```

The settings label becomes **Group limit**, with a line under it saying it
counts concurrent Claude sessions, not tasks — the number is otherwise correct
and unexplained, which reads as a bug.

The stored key becomes `group_limit`. `registry.load_settings` reads
`group_limit`, falling back to `wip_limit`, falling back to the default of 5, so
an existing `settings.json` carries its value over and the old key drops out on
the next save. Renaming the key rather than leaving `wip_limit` in place is
deliberate: a field named for tasks that counts groups is the kind of quiet
mismatch that costs an hour later.

## Auto-grouping on spin-up

Handing several tasks to one session is a statement that they are one unit, so
spin-up records it. The rule, in four cases, none of which ever splits a group
made by hand:

| Selection | What happens |
|---|---|
| 0 or 1 task | nothing grouped |
| 2+, none already grouped | a new group, named after the title of the first task in `task_ids` — which is list order, the topmost ticked row, since `selectedIds()` reads the DOM (deduped as above) |
| 2+, spanning exactly one existing group | the ungrouped ones **join** that group |
| 2+, spanning two or more existing groups | nothing regrouped |

The last row is the merge refusal again: two named groups cannot be silently
combined. The third is the common case — tick a whole group, add the one loose
task you just remembered, spin up.

**What gets typed into Claude is always exactly what was ticked.** Grouping
never adds a task to the prompt, never removes one, and never reorders them.
`launcher.build_prompt` is untouched, and `CLAUDE.md` invariant 2 continues to
hold verbatim.

A group formed this way does **not** grab focus for renaming — a console is
being spawned at that moment, and `CLAUDE.md` invariant 10 exists because
anything that takes the keyboard during hand-off takes it mid-sentence. It is
renamed from the IN PROGRESS section afterwards.

## Modules

`store.py` (289 lines) and `ui/tasks.js` (247) are both at the ~300-line mark
this project splits at, and group membership is its own concern in any case.

| File | Owns |
|---|---|
| `groups.py` *(new)* | group membership: assign, remove, rename, disband, set bucket, unique name, the renumber, and the spin-up rule |
| `ui/groups.js` *(new)* | the group block and header, rename-in-place, select-all, and the three-zone drag engine |
| `ui/inprogress.js` *(new)* | the IN PROGRESS section and its reset actions |
| `store.py` | the `group` field, and `reset_to_open` beside `complete_task` |
| `app.py` | bridge wiring for the above. Nothing else — the spin-up rule lives in `groups.py` precisely so it can be tested without spawning a process |
| `ui/state.js` | the banner counts groups |
| `ui/settings.js`, `ui/index.html`, `ui/style.css` | Group limit label and hint, markup, the indent rail |

Seven `ui/*.js` files instead of five. They continue to share one global scope
and resolve references at call time; load order in `index.html` becomes
`state`, `tasks`, `groups`, `inprogress`, `editor`, `triage`, `settings`.

**No group entity crosses the bridge.** `get_state` already returns every task
with its fields; the renderer derives groups from the `group` field it is
holding. A second representation would be a second source of truth.

### `groups.py` contracts

Each takes a project path and returns nothing unless stated. Each leaves every
affected bucket satisfying invariant 2.

- `unique_name(project_path, seed) -> str` — `seed` if free, else `seed 2`,
  `seed 3`… Comparison is case-insensitive. `seed` is stripped of surrounding
  whitespace; an empty or whitespace-only seed is a `ValueError`.
- `assign(project_path, task_ids, name) -> str` — put those tasks in that
  group, creating it if new. Members take the group's bucket, read before the
  join. Returns the group name actually used.
- `remove(project_path, task_ids)` — clear `group` on exactly those tasks.
- `rename(project_path, old, new) -> str` — `ValueError` if `old` has no
  members, if `new` is empty, or if `new` collides case-insensitively with a
  different existing group. Renaming a group to a differently-cased form of its
  own name is allowed.
- `disband(project_path, name)` — clear `group` on every member.
- `set_bucket(project_path, name, bucket)` — every member moves; they land at
  the end of the target bucket. `ValueError` on an unknown bucket.
- `auto_group(project_path, task_ids) -> str | None` — the four-case spin-up
  rule. Returns the group name if one was assigned, else `None`.

An unknown task id in any `task_ids` argument is a `ValueError` naming it, the
same contract `Api.hand_off` already has.

### Bridge methods on `Api`

- `group_tasks(project_name, task_ids, name)` → the group name used
- `ungroup_tasks(project_name, task_ids)`
- `rename_group(project_name, old, new)` → the new name
- `disband_group(project_name, name)`
- `set_group_bucket(project_name, name, bucket)`
- `reset_to_open(project_name, task_ids)` → the updated task dicts

`hand_off` gains one line: it calls `groups.auto_group` before handing the
selected tasks to `launcher.hand_off`. Its return value and prompt are
unchanged.

## Testing

`groups.py` is directly testable with `tmp_path` and the existing
`monkeypatch.setattr(registry, "CONFIG_DIR", ...)` fixture pattern. What must be
covered:

- `group` round-trips through frontmatter; a file with no `group:` key parses as
  `None`; a task saved with `group=None` emits `group: null`.
- `assign` creates a group, joins an existing one, pulls a joining task into the
  group's bucket, and leaves the bucket contiguous and renumbered from 0.
- The renumber is idempotent and repairs a deliberately interleaved fixture.
- `unique_name` dedupes case-insensitively.
- `rename` rewrites every member, refuses a colliding name, and allows a
  case-only change to its own name.
- `disband` and `remove` clear the field without disturbing order.
- `set_bucket` moves every member and renumbers both buckets.
- `auto_group`: all four cases, asserting explicitly that case four leaves both
  groups intact and that case two never touches a task outside the selection.
- `store.reset_to_open` clears `started` and sets `status` to `open`; a task
  that was never in progress is unaffected.
- `Api.hand_off` still marks the selected tasks in-progress and still produces
  the identical prompt after auto-grouping — the existing launcher test asserts
  the prompt, and a new one asserts grouping does not perturb it.
- `registry.load_settings` reads `group_limit`, falls back to a `wip_limit`-only
  file, and falls back to 5 with neither.

No JS test runner, per the project's standing decision. The manual checks below
are the frontend gate.

## Manual checks

Each is silent when broken, which is the bar `CLAUDE.md` sets for this list.

1. Drag one task onto the middle of another → a group forms and the name box is
   focused with the seeded text selected. Type a name, press Enter, reopen the
   app: the name persisted.
2. Drag a third task onto the group's header → it joins, and the name box does
   **not** re-open.
3. Drag a child out to a gap between top-level rows → it leaves the group and
   lands where it was dropped.
4. Change the group's bucket on the header → every member moves, and `git
   status` in a tracked project shows a frontmatter change and **no body diff**
   on each.
5. Tick three loose tasks and spin up → one group appears in IN PROGRESS with
   all three under one header, the banner counts it as **one**, and the text
   typed into the session is byte-identical to what the same three tasks
   produced before this feature.
6. `↩` on a group header → every member leaves IN PROGRESS and reappears in the
   bucket it was in before hand-off.
7. Rename a group to the name of another group → refused, with the box still
   focused and still holding what was typed.
8. With in-progress tasks in two projects, switch `currentProject` → both
   projects stay visible in IN PROGRESS under their own headings, and the
   banner's number equals the number of group blocks on screen.

## Deliberately not in this feature

- **Merging two groups.** Both by drag and on spin-up, it is refused rather than
  guessed. If it turns out to be wanted, it is an explicit gesture with an
  explicit choice of which name survives.
- **Nested groups.** One level, per the project's flat-over-nested rule and
  Griffin's standing rule that a parent/child relationship is shown by indenting
  the child exactly one level.
- **Groups spanning projects.** Ids and now names are per-project.
- **A group in the progress view.** Done tasks keep their `group`, so grouping
  the archive by it is available later; nothing renders it yet.
- **Reordering inside IN PROGRESS.** Drag is disabled there.
