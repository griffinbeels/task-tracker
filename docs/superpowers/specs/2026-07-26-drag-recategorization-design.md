# Drag recategorization — design

**Date:** 2026-07-26
**Status:** approved, ready to implement

Dragging a task should be able to change **where it sits**, **what it belongs
to**, and **whether it is running** — in one gesture, across every section on
screen. Today it can only do the middle one, and only inside the section the
drag started in.

## The defect this starts from

`wireDrag(section, bucket)` (`ui/groups.js:445`) is wired **once per section** —
`bucketSection()` calls it for each of now/next/someday, `inProgressSection()`
calls it for IN PROGRESS. Each call closes over its own `dragged` variable.

HTML5 drag events do not cross siblings. A drag begun in `someday` fires
`dragstart` on `someday`'s listener only; the `dragover`/`drop` that follow fire
on the *destination* section's listener, where `dragged` is still `null` and the
handler returns immediately. `event.preventDefault()` runs first, so the browser
shows a drop cursor the whole way — the gesture looks legal and does nothing.

Every cross-section drop is therefore a silent no-op. That is the entire gap;
nothing about the backend prevents any of this.

## What a drop means

A drop resolves to a **destination**, which is exactly three fields plus a
position:

| Field | Values | Meaning |
|---|---|---|
| `bucket` | `now` / `next` / `someday` / `null` | Where it lives when not running. `null` = unchanged, or decided by the group it joins. |
| `group` | a name / `null` | The group it ends up in. Always explicit — a drop always lands either inside a group container or outside every one. |
| `status` | `open` / `in-progress` / `null` | `null` = unchanged. |

Position is the destination bucket's **full ordered id list, read back from the
DOM** after the live reorder — or omitted, meaning "land at the end".

That triple is the whole feature. Every gesture below is a different way of
naming one.

## Drop targets, and what each resolves to

Read against the dragged row's own project — never `currentProject`
(invariant 6). A destination whose project differs from the dragged row's is
refused with no affordance.

| Target | Destination |
|---|---|
| A bucket's `<h2>` | `{bucket: that, group: null, status: open}`, at the end |
| Top-level gap / row edge in a bucket section | `{bucket: that, group: null, status: open}`, positioned |
| Middle of a loose top-level row | **pair** — create a new group from the two (unchanged gesture) |
| A `.group-header` | `{bucket: null, group: its name, status: the section's}` |
| Inside a group's container | same as its header; or a **sort** within the group when it is already a member of that same group in that same section |
| `#in-progress > h2` | `{bucket: null, group: null, status: in-progress}`, at the end |
| A `.project-heading` in IN PROGRESS | same, and the project must match |

Two rules resolve the overlaps:

1. **An explicit bucket wins; otherwise the group decides.** Dropping a
   `someday` task into a group whose members are in `now` moves it to `now` —
   invariant 16 says a group lives in one bucket, so joining is what sets it.
   Dragging a group *header* into `next` passes an explicit bucket, and that
   moves every member.
2. **A drop that changes nothing gets no affordance.** "Already a member" now
   means same group *and* same status, so a `now` member of group G can still be
   dropped on G's header in IN PROGRESS — that claims it — while dropping it on
   G's header in its own section stays a no-op.

### The two look-alike affordances stay two

`drop-into` (solid green) means *becomes part of something*; `drop-loose`
(dashed) means *leaves something*. Claiming a task into IN PROGRESS is joining
the running region, so it takes the solid outline; dropping one back into a
bucket is leaving it, so it takes the dashed one. No third look is introduced —
a status change is not a third kind of outcome, it is the same two seen from the
region that gained or lost the row.

### Whole groups drag too, both directions

A group header dragged between buckets moves every member (what its bucket
picker already does). Dragged into IN PROGRESS it claims all of them. And the IN
PROGRESS group header becomes draggable — today it is deliberately not, because
that section cannot reorder — so a running group can be dropped back into a
bucket and released in one gesture.

A header reading `2 of 5` moves **all five**. That differs from the `done`
button beside it, which acts on the two it drew, and the difference is the
point: `done` completes tasks, a drag moves the *group*, and invariant 16
forbids leaving three members behind in another bucket.

## Backend: one call per drop

The drop handler is already the most intricate code in the app, and this feature
multiplies its branches by two new axes. There is no JS test runner in this repo
(deliberate — CLAUDE.md), so anything left in JavaScript cannot be tested at
all. The placement rule therefore moves into Python.

### `groups.place(project_path, task_ids, *, bucket, group, status, ordered_ids)`

Applies a destination to a list of tasks and leaves every bucket it touched
satisfying invariant 16. One task for a row drag, every member for a group drag.

Order of operations, which matters:

1. Validate `bucket` against `store.BUCKETS` and `status` against
   `open`/`in-progress` — `done` is refused, since leaving the archive is
   `restore_task`'s job and the progress view is built on its dates.
2. Capture the source buckets before anything moves.
3. Resolve the target bucket: explicit `bucket`, else the settled members of
   `group`, else unchanged.
4. Write each task once — group, bucket and a provisional tail order, then
   `store.start_task` / `store.reset_to_open` / `store.save_task` depending on
   whether the status actually changed.
5. `store.reorder_bucket` with `ordered_ids`, when given.
6. `groups.renumber` every touched bucket — source *and* destination. The source
   is what repairs the hole the departing row left.

**Status is written only when it differs.** `reset_to_open` clears `started`,
so applying `open` to an already-open task would erase a date it legitimately
holds (a restored task keeps its `started`). Skipping the no-op write is what
keeps a group move from quietly rewriting three members' history.

### `store.start_task(task)`

The inverse of `reset_to_open`, beside it: sets `in-progress`, stamps
`started` if unset, refuses a completed task. `launcher.hand_off` currently
inlines these three lines and switches to calling this, so "what it means to
start a task" has one definition rather than two that can drift.

### `Api.place_task` / `Api.place_group`

`place_task(project, task_id, destination, ordered_ids=None)` and
`place_group(project, name, destination, ordered_ids=None)`. The bridge does
type refusal (a `destination` that is not a dict, an unknown key, a non-string
group name — following `_text`'s precedent); `groups.place` does the domain
checks. `place_group` resolves the group's members by name, so the frontend
never sends a member list that could be stale by the time it lands.

Two methods rather than one polymorphic one: "explicit over magical", and the
group case genuinely differs — its membership is fixed and read from disk.

## Frontend: one controller instead of six

`wireDrag` binds **once**, at load, to `#task-list` — the common ancestor of
every section — exactly as the delegated `change` listener in `ui/tasks.js:254`
already does. `render()` replaces that element's children, never the element, so
the listener survives every redraw and cannot stack duplicates.

- `bucketSection()` and `inProgressSection()` stop calling `wireDrag`.
- The destination's section comes from
  `event.target.closest('section[data-bucket], #in-progress')` at event time,
  instead of from a closure constant. No section ancestor → no drop.
- `bucketSection()` sets `section.dataset.project = currentProject`, so the
  project check is one uniform comparison against the destination rather than a
  special case per section.
- Search and all-projects views set `row.draggable = false` and render no
  sections, so a listener at this level is inert there.

## The empty IN PROGRESS section

`inProgressSection()` returns `null` when nothing is running, so there is
nothing on screen to drop the *first* task onto. It now always renders: heading,
plus one explained line when empty —

> Nothing running. Drag a task here to claim it, or hit Spin up.

Costs about two rows of vertical space in a 420px window at all times, and buys
a drop target that is always in the same place. The alternative — materialising
the section when a drag starts — shifts the whole list down under the pointer
mid-drag, moving the row being aimed at.

The section's own `<h2>` is a drop target in its own right, not just the project
headings. That is what makes the empty case work at all: with nothing running
there are no project headings, and a task must still have somewhere to land.

## Files

| File | Change |
|---|---|
| `store.py` | `start_task()`, beside `reset_to_open` |
| `launcher.py` | `hand_off` calls `store.start_task` instead of inlining it |
| `groups.py` | `place()` |
| `app.py` | `Api.place_task`, `Api.place_group` |
| `ui/groups.js` | `wireDrag` → one delegated controller; destination resolution |
| `ui/tasks.js` | drop the `wireDrag` call; `dataset.project`; always render WIP |
| `ui/inprogress.js` | always render; empty hint; draggable group header |
| `ui/style.css` | `drop-into` on headings; the empty line |
| `tests/` | `place`, `start_task`, and the two bridge methods |

## Testing

`groups.place` is where the risk lives and it is pure Python over `tmp_path` —
the existing `test_groups.py` fixtures (`seed_bucket`, `orders`, `by_id`) cover
it directly. What must be pinned:

- A loose task moves between buckets and both buckets renumber contiguously.
- A task joining a group takes the group's bucket, not the section it came from.
- An explicit bucket beats the group's, so a header drag moves every member.
- Claiming and releasing set and clear `started`, and a no-op status leaves
  `started` alone.
- A completed task is refused.
- Contiguity survives every one of the above (invariant 16).

The gestures themselves cannot be tested here — there is no JS runner, and per
CLAUDE.md a UI task cannot be signed off from its diff. The by-hand checks go to
the user when this lands, not at the end of the plan.

## Deliberately not in scope

- **Dropping into IN PROGRESS does not spawn a Claude session.** It flips the
  status and nothing else. The ↩ button already on every running row is exactly
  the inverse, so the two read as one control; and a drag is far too easy to
  misfire for a gesture that opens a console and types into it.
- **Cross-project drops stay refused.** Ids are per-project (invariant 6) and a
  group name is per-project, so a cross-project drop has nothing coherent to
  mean. IN PROGRESS spans projects, so a row from a project other than the
  selected one can be dropped only within its own project's heading.
- **Two groups still never merge**, by drag or otherwise.
- **IN PROGRESS still never reorders.** Its rows sort by project and group and
  can sit in three different buckets, so there is no single bucket for
  `reorder_bucket` to renumber. Sorting *within* one group there still works, as
  it does today.
