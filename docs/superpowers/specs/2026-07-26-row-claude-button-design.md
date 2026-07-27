# A Claude button on every task row

**Date:** 2026-07-26
**Status:** approved, not yet implemented

## The problem

Starting work on one task costs three gestures: tick its box, move the cursor
to the header, press Spin up Claude. The tick is pure overhead — it exists to
tell the header button which task you meant, and you untick it (or let a
refresh clear it) immediately afterwards. For the commonest thing this app is
for, the control is in the wrong place.

## What it is

A small Claude-character button in every task row, in the hover-revealed
cluster beside the copy and `done` buttons:

```
[ ] ● FEATURE  Add Claude button to each task    [now ▾]  (C)  ⧉  done
                                                          ^^^
```

Clicking it opens a session exactly as Spin up Claude does — same prompt, same
`/rename`, same `/color`, same auto-grouping — and the tasks it sends are
marked in progress by the same code path.

## The rule for what it acts on

**A row-level button acts on the row it sits in, unless that row is ticked, in
which case the click is aimed at the visible selection and it acts on all of
it.**

This is not a new rule. It is the rule `completeWithSelection` already applies
to every `done` button in the app (`ui/selection.js`, landed 2026-07-26), and
the whole point of this design is that the Claude button is the *second*
caller of it rather than a second copy of it. Concretely:

| Ticked | Button clicked on | Launches |
|---|---|---|
| nothing | any row | that one task |
| N rows | one of those N | all N |
| N rows | a row outside the N | that one task; the N are untouched |

"Untouched" is meant literally, and it has a consequence worth stating because
it does not fall out for free: `refresh()` rebuilds `#task-list` with
`replaceChildren`, so every checkbox in it is a new, unchecked element. A
hand-off from an unticked row would therefore silently clear a batch the user
had spent time staging. **The ticks are restored exactly when they were not
what launched** — one rule, no per-caller special case. Restoring also re-ticks
a group header's own box when every member of that group came back ticked; a
group whose members are all ticked under an empty header box is the same
broken-render defect as the reverse, which the by-hand list already names.

Mixed-project selections are refused exactly where they already are: only the
"aimed at the selection" branch consults `selectedInOneProject()`, which alerts
and returns null (invariant 6). Launching a single unticked row never looks at
the selection at all, so a mixed set of ticks elsewhere cannot block it.

The batch-name row (`#handoff-name`) is read **only** when the selection was
what launched. It is hidden below two ticks, and passing its value to a
single-task hand-off would name a side task after a batch that is still sitting
there staged.

## Where the code goes

No backend change. `launcher.hand_off` already ends with `store.start_task` for
every task it sends, and `store.start_task` deliberately does not restamp
`started` on a task that already has one — so "marks it in progress" is
existing behaviour reached from a new button, including on a row that is
already in IN PROGRESS.

**`ui/selection.js`** — the acts-on rule, extracted from
`completeWithSelection` into one resolver both actions call:

```
aimedAt(project, ids) -> { project, ids, fromSelection } | null
```

`null` means refused (nothing named, or a mixed-project selection the user was
alerted about). `completeWithSelection` becomes a two-line caller of it.

**`ui/tasks.js`** — the icon constant, the button inside `taskRow`, and one
`handOff(project, ids, fromSelection)` holding the body currently inline in
`#spin-up`'s handler: read the name row, `callApi('hand_off', …)`, clear the
name box, refresh. `#spin-up` and every row button call it, so the two cannot
drift — the same reason `build_prompt` is shared by the copy button and the
hand-off on the Python side.

The row button's whole handler is then:

```
const aimed = aimedAt(task.project, [task.id]);
if (!aimed) return;
await handOff(aimed.project, aimed.ids, aimed.fromSelection);
```

`#spin-up` keeps its existing `selectedInOneProject()` call rather than going
through `aimedAt` — it is not a row button and has no row to be in or out of
the selection, and its "nothing ticked opens an empty session in the current
project" fallback is `selectedInOneProject`'s, not this rule's. It then calls
`handOff` with `fromSelection: true`, which is true by construction: what it
launches *is* the selection.

`fromSelection` answers one question, asked twice — was the selection what
launched? Both consequences follow from it: read the name row or don't, restore
the ticks afterwards or don't. Two flags would let them disagree.

On a failed `hand_off` the handler returns without refreshing, exactly as
`#spin-up` does today. Nothing was re-rendered, so the ticks were never cleared
and there is nothing to restore — the failure path needs no branch of its own.

**`ui/style.css`** — a `.claude` rule mirroring `.copy` exactly: `opacity: 0`
at rest, `.6` on row hover, `1` plus a background fill on its own hover, and
`pointer-events: none` on the `svg` so the click target is the `<button>`
(`taskRow`'s row-click handler ignores clicks whose target closes on
`input, select, button`, which is what keeps this from also opening the
editor).

Markup order in `taskRow` becomes checkbox, dot, type, title, bucket, **claude**,
copy, done — start, copy, finish, left to right. The bucket picker is currently
inserted with `.copy.before(...)`; it moves to `.claude.before(...)` so the
order holds.

## Where the button appears

Every row that can be started: buckets, groups, IN PROGRESS, search and the
all-projects view. It takes `task.project` from the row it was built for, never
`currentProject`, so it is correct in the two cross-project views where
selection is deliberately disabled (invariant 6) — there `aimedAt` always
resolves to the row itself.

**Removed from archived rows in search**, alongside the `done` button that is
already removed there: `store.start_task` refuses a completed task, so the
button would offer a click that raises.

The tooltip is `Spin up Claude` and nothing more. "Start this task" would be a
lie on a ticked row, where the click starts N.

## The icon

Measured from the source PNG rather than traced by eye — decoded with `zlib`
and `struct` (there is no Pillow in this venv) and its light/dark run
boundaries read off directly. The artwork is a **16×16 pixel grid**, drawn on a
40px cell with a 13px downward offset that is an artefact of the render, not
part of the design; snapping it to the grid moves every edge by at most 15/640
of the image and is what makes the icon crisp at small sizes.

```
col      0123456789012345
row  3   ..############..     body: cols 2–13, rows 3–10
row  4   ..############..
row  5   ..##.######.##..     eyes: cols 4 and 11, rows 5–6
row  6   ..##.######.##..
row  7   ################     arm band: full width, rows 7–8
row  8   ################
row  9   ..############..
row 10   ..############..
row 11   ...#.#....#.#...     legs: cols 3, 5, 10, 12, rows 11–12
row 12   ...#.#....#.#...
```

The measured edges it comes from, for anyone re-deriving it: body x 80–560 /
y 133–455; eyes x 160–200 and 440–480 / y 216–292; arm band x 0–640 /
y 292–375; legs x 120–160, 200–240, 400–440, 480–520 / y 455–533.

It ships as **one inline `<svg>` with a single `<path>` and
`fill-rule="evenodd"`** — the silhouette traced as one closed outline so no two
subpaths share an edge (adjacent subpaths can leave an anti-aliasing seam),
with the two eyes as separate subpaths that become holes:

```
viewBox="0 0 16 16"
d="M2 3H14V7H16V9H14V11H13V13H12V11H11V13H10V11H6V13H5V11H4V13H3V11H2V9H0V7H2Z
   M4 5H5V7H4Z M11 5H12V7H11Z"
```

Inline SVG rather than a committed PNG for two reasons: it is static markup
with no user-authored text in it, exactly like `COPY_ICON`, so invariant 5 is
untouched; and it scales with the `zoom` feature, which a bitmap would not.

Rendered at 16px each grid unit is exactly one CSS pixel. The artwork occupies
rows 3–13 of the 16-unit box, so it is already vertically centred and needs no
extra padding.

**The colour is `#D77757`**, sampled from the real terminal render (4998 pixels
of it against a `#0C0C0C` background) rather than taken from brand memory.

## The mechanism that keeps the two buttons one control

The rule above is the kind that decays silently: a third button gets added, its
author writes the obvious `callApi` directly, and the symptom is four tasks
ticked and one of them acted on — which reads as the ticks being ignored rather
than as a missing call.

`tests/test_conventions.py` already pins half of it —
`test_only_the_selection_owns_completing_tasks` fails the build if any UI
script outside `selection.js` names `completeTasksWithConfirm` or
`'complete_tasks'`. This adds the symmetric half:

- **`test_only_one_call_site_hands_tasks_to_claude`** — `callApi('hand_off'`
  must appear exactly once across the UI scripts. One call site means a new
  button has to reach the existing `handOff`, and therefore inherits the name
  row, the refresh, the tick restoration and `aimedAt` with it.

What neither test can see, stated so nobody mistakes green for proof: a caller
that reaches the right function with the wrong ids, a button that resolves its
targets itself and then calls the single site, and a button that does nothing
at all. They pin *where* the rule lives, not that a caller meant it.

## By-hand checks

There is no JS test runner here and Claude must never run `app.py`, so these
are the user's to perform and belong in `CLAUDE.md`'s list when this lands.

1. Nothing ticked, click a row's `(C)`: a session opens on that task, named
   after it, and the row moves to IN PROGRESS.
2. Tick four tasks, click `(C)` on **one of those four**: one session opens
   with all four, named as Spin up would name it. Same as pressing Spin up.
3. Tick four, type a batch name in the name row, click `(C)` on one of the
   four: the session takes the typed name.
4. Tick four, click `(C)` on a **fifth, unticked** row: only that row launches,
   and **the four stay ticked** with the bar still reading `4 selected`.
5. Repeat 4 with the four ticked via a group header's box: the header box must
   come back ticked too, not just its members.
6. Click `(C)` on a row already in IN PROGRESS: a session opens, and the task's
   `started` date does not change (check `git status` in a tracked project —
   frontmatter may show `status`, never a new `started`).
7. Hover a row: the title must not shift sideways as `(C)` appears — the same
   `opacity`-not-`display` check the copy button already has.
8. Click `(C)`: the editor must **not** also open.
9. In the search view, an archived (done) result must have no `(C)` at all; a
   live result from another project must have one, and clicking it must launch
   *that* project's task, not the selected project's task of the same id.
10. Zoom the list to 200% (Ctrl+`+`): the icon must stay sharp and the row must
    not reflow into two lines.

## Deliberately not in scope

- ~~No button on a group header.~~ **Added the same day, after the row button
  was tried in the running app.** It is the same control in the same place in
  the header — right after the bucket picker, on the column the rows' own
  buttons sit in — and it follows the same rule by calling the same `aimedAt`:
  with the group ticked, the click resolves to the whole selection, so the
  group launches alongside anything else ticked beside it.

  It names `block.tasks` — the rows this header actually drew — and not the
  group's full membership, which is exactly what the `done` two controls along
  does. The two disagree only for a header in IN PROGRESS reading `2 of 5`,
  where the other three are sitting in a bucket rather than in this session.
  (The group *drag* is the deliberate exception on the other side: a group
  lives in one bucket, so there is no such thing as moving part of one.)

  The session name comes out right for free: `launcher._shared_group` names a
  window after the group when every task in it shares one.
- **No confirmation dialog.** "Immediately" is the point, and the gesture is a
  deliberate click on a hover-revealed target rather than a drag that can
  misfire — which is exactly why dragging into IN PROGRESS still does not spawn
  a session.
- **No change to what a hand-off sends.** Prompt, naming, colouring and
  auto-grouping are `launcher.py`'s and stay untouched.
