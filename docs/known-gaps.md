# Known gaps

## Known gaps

Three spec behaviours were never implemented, and the deferred findings from the
whole-branch review are filed as tasks in this repo's own `.tasks/open/` — open
the tracker, select this project, and they are the backlog. Highlights:

- Cross-project rows do not switch the project picker to the row's project.
  They do open the editor, which is project-safe (invariant 6). **Decided, not
  deferred** (2026-07-26): the spec's jump-to-project predates the editor being
  able to open a foreign row at all, and building it now would mean *removing*
  editing from that view to make room for a click that does less. If both are
  ever wanted they need two distinct targets on the row, not one click doing
  whichever seems more useful.
- The editor cannot **create** a group, only join one that exists or leave the
  one it is in. Creating stays the drag gesture, so there is one set of naming
  rules rather than two.
- Triage chips are mouse-only; the spec called for single-key assignment. **Not
  a gap to close as specified** — triage now runs through the shared editor,
  where the body holds focus and typing goes into prose, so bare `b`/`f`/`i`
  keys would collide with writing. It needs a modifier scheme or a focus rule,
  which is a design decision nobody has made.
- No control *writes* `## Outcome` — but one is no longer needed to get one.
  Clicking a completed entry in the progress view opens it in the editor
  (`renderProgress`, `ui/settings.js`), so the heading can be typed into the
  body there and the view renders it on the next open. What is missing is
  discoverability, not the path. The spec's answer — prompt for a one-liner
  when marking a task done — was **considered and declined on 2026-07-26**: it
  puts a dialog in front of the most common action in the app to serve the
  rarest one. If this is ever picked up, the shape to build is a field in the
  editor for a done task, beside Restore.
- **Restore is singular.** `store.restore_task` mirrors `store.complete_task`
  exactly, one task at a time, and `Api.restore_task` is the only bridge method
  of the pair left: completing has no singular one any more, because every
  `done` in the app now goes through `Api.complete_tasks` (a batch of one is a
  batch). Nothing restores a whole batch out of `done/` the way the selection
  bar, a group header and a task row all complete one.
- **Two groups can never be merged**, by drag or on spin-up — both paths refuse
  rather than guess which name survives. If that becomes wanted it needs an
  explicit gesture with an explicit choice.
- **Groups are one level deep** and never span projects.
- **IN PROGRESS reorders, but its order is not the tasks'.** It ranks blocks in
  `session.json` (see invariant 28), because `Task.order` is a per-bucket
  position and running tasks can sit in three different buckets. The
  consequence worth knowing: that order is view state, so it is per-machine and
  invisible to git, unlike every other thing a drag changes.
- **A group header drag moves every member**, including any the header did not
  draw — a header in IN PROGRESS can read `2 of 5`. A group lives in one
  bucket (invariant 16), so there is no such thing as moving part of one. This
  deliberately differs from the `done` button beside it, which acts on the
  rows it drew.
- **Dragging into IN PROGRESS does not spawn a session.** It flips the status
  and nothing else. The ↩ on every running row is exactly the inverse, so the
  two read as one control, and a drag is far too easy to misfire for a gesture
  that opens a console and types into it.
- Done tasks keep their `group`, but nothing renders it: the progress view
  still lists completed tasks flat.
- **Shift+Tab no longer outdents a list item in the editor body.** That is the
  price of the focus ring (invariant 30's neighbour in `ui/editor.js`): Tab
  belongs to Toast UI's list indent, so the only key left that can escape the
  body is Shift+Tab, and a capture-phase listener takes it before ProseMirror
  sees it. Backspace at the start of the item still outdents.
- **The chips are still mouse-only**, now with a visible focus ring if plain
  Tab reaches them. The Shift+Tab ring deliberately skips them — three
  projects, three types, three buckets and eight colours is about twenty stops
  between the title and Cancel. If they are ever wanted from the keyboard the
  shape is one stop per chip *row* with ←/→ inside it, which is a second
  interaction idiom and a decision nobody has made.
- **Zoom is per-machine and invisible to git**, like the IN PROGRESS order and
  for the same reason: it is view state in `session.json`.

Session identity (naming and colouring a handed-off window, see
`docs/superpowers/specs/2026-07-25-session-identity-design.md`) **was verified
against a live session on 2026-07-25** — the gap that used to sit here is gone.
A bracketed `/rename` and `/color` are read as commands, not as chat text; the
`\r` written after them is read as Enter; and the prompt is left editable
afterwards. What that verification *found* is invariant 24: the failure was
never in how the line is written, it was in writing the next thing before the
session had read the last one. The one gap it shipped with is closed:

- **The batch-name row landed where that design said it would.** It is the
  second row of `#selection-bar` now, and `Api._selected_tasks` collapsed into
  `Api._tasks`. The id stayed `#handoff-name` rather than disappearing, because
  the row still belongs to the hand-off rather than to the bar: both of the
  standalone Claude buttons read it through `handOffSelection` in
  `ui/tasks.js`.

Design specs: `docs/superpowers/specs/2026-07-25-task-tracker-design.md`,
`docs/superpowers/specs/2026-07-25-task-editor-design.md`,
`docs/superpowers/specs/2026-07-25-task-groups-design.md`
Implementation plans: `docs/superpowers/plans/2026-07-25-task-tracker.md`,
`docs/superpowers/plans/2026-07-25-task-editor.md`,
`docs/superpowers/plans/2026-07-25-task-groups.md`

**The specs and plans are historical records, not current documentation — the
code and these invariants are.** Eight things in them are known-wrong and were
corrected during implementation. Two of them say a hand-off types `TYPE: body`
— `2026-07-25-copy-as-prompt-design.md:84` ("`copy_prompt` copies exactly
`TYPE: body`") and `2026-07-25-task-editor-design.md:207`. It does not, since
2026-07-27: it types the task file's path and the session reads the file
(invariant 2). The same two lines are still live on `feature/bar-spin-up` and
`feature/row-claude-button`; neither branch touches `launcher.py`, so a merge
cannot bring the old `build_prompt` back, but a careless CLAUDE.md conflict
resolution can bring the old row-83 description back. `2026-07-25-selection-bar-design.md:137` says
"The bar needs `#selection-bar[hidden] { display: none }`", and its plan
(`2026-07-25-selection-bar.md:392`) lays the bar out in the flow with a
`margin-bottom`. Both describe the bug: in the flow the bar shoved every task
down as it appeared, and `display: none` cannot animate. The bar is now
`position: fixed` against the bottom edge and its `[hidden]` rule deliberately
keeps `display: flex` — copying either line back is the way to reintroduce the
jump and kill the slide at once. `2026-07-26-drag-recategorization-design.md`
says under "Deliberately not in scope" that **IN PROGRESS still never
reorders** — it does, and the design of how is invariant 28, not that file:
the section learned to reorder the same day, once its order moved to
`session.json` where a per-bucket `Task.order` could not express it. `2026-07-25-restore-and-group-block.md:169`
still shows `task.order = len(siblings)` for a restored task; that is only "the
end" of a contiguous run, and `Api.complete_task` does not renumber, so it
hands a restored task an order another task already holds. The code uses
`max(order) + 1` plus a `groups.renumber`. The other four: `file_note` had no way to receive an edited
body (so triage silently discarded prose edits); image references were
specified as bare `C:/...` paths and `as_posix()`, which are not URLs and never
render; the tracker spec still describes the strip-list environment that
`claude_console.environment` replaced; and its console-probe snippet
(`2026-07-25-task-tracker-design.md:224`) still reads
`creationflags=subprocess.CREATE_NEW_CONSOLE`, which opens a Windows Terminal
window on every test run — copying that line back in is the one way to
reintroduce the flash, and two tests now fail the build if anything does:
`test_nothing_in_this_repo_may_open_a_console_window` here, and
`test_nothing_but_the_session_itself_may_open_a_console_window` in
`claude-console`, which is where the probe now lives. Invariants 8, 13 and 14
are the record of what the code actually does.

Those specs also predate the extraction: everything they say about spawning a
console, typing into it, or rebuilding an environment now describes
`claude_console`, not a file in this repo.
