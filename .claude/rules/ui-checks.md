---
paths:
  - "ui/*.js"
  - "ui/style.css"
  - "ui/index.html"
---

# The by-hand checks — what only a running window can answer

Hand these to the user when a UI task lands, not at the end of the plan.

- **No JS test runner, and the by-hand checks have no agent to run them.**
  Claude must never run `app.py` — it opens a window on the user's desktop and
  writes to their real `~/.task-tracker/` — so "checked by running the app"
  means *the user* runs it. A UI task therefore cannot be signed off from its
  diff, and reading the diff is not a weaker version of the check, it is a
  different thing that cannot see the same class of defect.
  This cost a Critical on 2026-07-26. Three UI tasks were marked "review clean"
  on the strength of their diffs; the editor was opening *behind* the Progress
  overlay the whole time — no `z-index` existed anywhere in `ui/style.css`, and
  two full-screen opaque overlays paint in DOM order. The restore feature was
  completely unreachable in the running app, and the four by-hand checks that
  would have caught it in one second were written into the list below as though
  they had been performed. Hand the checks to the user when the UI task lands,
  not at the end of the plan.
- Frontend changes are checked by running the app. Two
  editor behaviours are worth checking by hand every time `ui/editor.js` is
  touched, because both are silent when broken: type a title then click a
  different type chip (the title must not change), and edit *only* a task's
  bucket in a tracked project then run `git status` (the `.md` file must show a
  frontmatter change and **no body diff**). In `ui/tasks.js`, check that
  hovering a row does not shift the title sideways (the hover-revealed controls
  must use `opacity`, never `display`) and that clicking the copy button does
  not also open the editor. One more, for the hand-off being a pointer
  (invariant 2): paste a numbered list into Capture, save it, then press the
  row's copy button — the clipboard must hold **the task file's absolute
  path** and nothing else, and opening that path must show the task you just
  wrote. Then search for a phrase from a numbered line containing a comma:
  the row must come back. That one is `asShown`, not the hand-off — search is
  now the only place the editor's escapes still have to be undone. Five for inline rename, which splits one row
  between two gestures: double-click a task's title — it becomes a box, Enter
  commits and Escape puts the old title back; single-click that same title must
  do **nothing**, while the dot, the type tag and the space after a short title
  all still open the editor; dragging a row by its title must still work;
  rename a row in the **search** view, where a title is drawn as `project ·
  title` — the box must contain the bare title, or the decoration gets saved as
  the name; and rename in a tracked project, then `git status` — a frontmatter
  change and **no body diff**. In `ui/selection.js`, check that ticking a group
  header's select-all box updates the bar's count (assigning `.checked` on the
  member rows does not fire a `change` event, so the count silently goes stale
  without the explicit call this depends on) and that `Clear` empties the
  header box along with every row's — a header left ticked with no members
  ticked reads as a broken render. Fold a group, tick the group's checkbox, and
  press the toolbar's Claude button: the folded members must still go to the
  session.

  And four for the hand-off itself, which is the whole of what changed on
  2026-07-26 and none of which a diff can show. Spin up a batch: the window
  must open **already carrying its name** — in the title bar and above the
  prompt box — with no `/rename` line in the transcript, and the tasks must
  arrive in the box. Spin up into a project Claude has never been opened in:
  the trust dialog appears, and answering it even a minute later must still
  leave the tasks in the box, because the wait is now three minutes rather
  than forty-five seconds. Spin up several batches at once — the gesture that
  makes every window slow — and every one of them must end up with its tasks.
  And the failure path, which is worth seeing once: with the tracker open,
  spin up and then close the Claude window before it finishes starting; the
  tracker must slide a notice down from the top saying the text is on the
  clipboard, nothing on the page may move as it arrives, and clicking it must
  slide it back up rather than blink it away. `%LOCALAPPDATA%\claude_console\delivery.log`
  should then hold that hand-off's steps and the screen it gave up on.

  Three for
  `completeWithSelection`, which makes every `done` in the app one control:
  tick four tasks and press the `done` on any one of those four rows — all
  four complete, with the same confirm the bar asks. Tick those four and press
  `done` on a *fifth*, unticked row — only that row completes and the four
  stay ticked. Tick a whole group with its header box plus one loose task, and
  press the header's own `done` — all of them go, not just the group.

  Four for **the bar's own Claude button**, which is the toolbar's button in
  reach of the cursor that just ticked the boxes — the same
  `handOffSelection`, so what is being checked is the wiring and the fit, not
  the hand-off. Tick two tasks and press it: one session opens with both, and
  the bar slides away as it goes — that departure is the only confirmation
  there is, and a bar left sitting there with its ticks intact means the
  refresh did not happen. Type a name into the bar's Name row and press the
  bar's button rather than the toolbar's: the session must come up under that
  name, since both read the same box. Tick tasks from two different projects in
  IN PROGRESS and press it: the same `Select tasks from one project at a time.`
  alert the toolbar gives, and **no window opens**. And narrow the window until
  the header starts to crowd: the bar must still be **one row**, with none of
  Done/Delete/Clear wrapping its own label onto a second line.

  **That check used to pin a number and the number is now unreliable, which is
  worth more than the number was.** It read "measured to fit down to 343px
  against the header's own 352px floor". Re-measured on 2026-07-27 after the
  label became a glyph: the bar holds to **326px**. But the same sweep run
  against the OLD labelled markup says **406px**, not 343 — so whatever ruler
  produced 343 is not the one used here, and the two figures must not be
  compared. What the sweep does establish, under one ruler, is the direction
  and the size of it: dropping the label bought the bar ~80px of headroom. The
  method, if it is ever re-run: a `.actions` row of the real markup inside a
  container of *window width − 24* (the bar is `left: 12px; right: 12px`),
  stepping 1px at a time, calling it wrapped when the bar's height exceeds one
  28px control inside its 5px padding and 1px border. The header cannot be
  swept the same way — `header` is a flex row with no `flex-wrap`, so it
  overflows rather than wrapping and its height never changes.

  Three more for **nothing showing through the bar**, which is the stacking
  ladder in "Adding a feature" seen from the front. Scroll a list long enough
  that a `NOW`/`NEXT`/`SOMEDAY` heading, a group header and a bucket dropdown
  each pass *behind* the ticked bar: none of them may be visible through it,
  and the dropdown in particular must not draw over Done or Delete. Then press
  **Done** at the moment a dropdown is behind that exact spot: the press must
  reach Done, never the dropdown — hit-testing follows painting, so this is the
  same bug wearing different clothes. And the half that must not regress: tick
  a task and open Progress or the editor, which must still cover the bar
  completely.

  And seven for the row's **Claude button**, which shares that same rule
  (invariant 31) and is the other half of it. With nothing ticked, click a
  row's Claude face: a session opens on that task alone, named after it, and
  the row moves to IN PROGRESS. Tick four and click the face on **one of those
  four**: one session opens with all four, named exactly as Spin up names it —
  and with a batch name typed in the name row, the session takes that name.
  Tick four and click the face on a **fifth, unticked** row: only that row
  launches and **the four stay ticked**, with the bar still reading `4
  selected` — this is the one that a refresh silently undoes if the restore is
  lost. Do that again with the four ticked via a group header's box: the header
  box must come back ticked too, not only its members. Click the face on a row
  already in IN PROGRESS: a session opens and `git status` in a tracked project
  must show no new `started` date. Click the face and the editor must **not**
  also open, and hovering must not shift the title sideways. In the search
  view, an archived result must have no face at all, while a live result from
  another project must have one that launches *that* project's task. The row is
  one control wider than it was, so a long title now wraps a word earlier —
  that is by design (`.title` has no ellipsis on purpose), not a regression.

  And four for the **group header's** Claude button, which carries the same
  rule one level up. With nothing ticked, press it: one session opens on every
  row that header drew, named after the **group** rather than after a member
  (`launcher._shared_group` does that, and only when every task shares one).
  Tick the whole group with its header box plus one loose task elsewhere, then
  press it: all of them go, not just the group. In IN PROGRESS, on a header
  reading `2 of 5`: it must launch those 2 and leave the other 3 in their
  bucket — the same set its `done` acts on, and deliberately not the set a
  header *drag* moves. And pressing it must not start a drag, while dragging
  the header by its name must still work.

  Four more for the
  bar's own position, which is a floating overlay rather than a row: tick a box
  and **nothing above it may move** — the list must stay exactly where it was
  while the bar slides up from the bottom edge, and untick must slide it back
  down rather than blink it away. Scroll a list long enough to scroll all the
  way to the bottom with two tasks ticked (which shows the taller two-row bar):
  the last task must still be readable above the bar. Tick a task, then open
  Progress or the editor: the bar must be **behind** the overlay, not floating
  on top of it. And clear the last tick: the count must not flash `0 selected`
  on its way out. In `ui/groups.js`,
  four more: drop a grouped row on a bucket's heading, or on a project heading
  in IN PROGRESS, and it must leave its group — that heading is the only
  drag-out target, because the gaps a reorder crosses are not aimable and
  releasing in one must never dissolve a grouping by accident. And three more:
  drag a task onto the
  middle of another and the new group's name box must open focused with its
  seeded text selected; drag a third onto that group and it must **not** reopen
  (invariant 11); and after moving a group between buckets, `git status` in a
  tracked project must show a frontmatter change and **no body diff** on every
  member. For the header, select a project that is not the first and press ↻:
  the window must come back on *that* project, at the same size and position,
  and `run.bat` must restore it too — the selection is restored on every launch,
  not just the button's. Narrow the window and the picker must shrink rather
  than pushing ⚙ off the row. For the group block's `done` button and the
  tree's type scale: a group of 2 → `done` completes both with no prompt and
  the block disappears; a group of 5 → `done` asks first, and Cancel leaves
  all five untouched; in IN PROGRESS, a header reading `2 of 5` → `done`
  completes those 2 while the other 3 stay in their bucket and the group
  survives; a group header's checkbox must line up exactly with a top-level
  task row's; dragging a group by its header must still work, and pressing
  `done` must not start a drag. Renaming is a **double-click on the name
  itself**: a single click anywhere on the header — including the empty stretch
  between the name and the count, which used to be part of the name's own box —
  must start a drag instead. And a group born from a drag must still open its
  name box focused, which no longer goes through a synthesised click. And for restore: open a completed task from
  Progress and close without changing anything — `git status` in a tracked
  project shows no diff at all; edit its body and save — the change lands and
  the file stays in `done/`; press Restore — it leaves the progress list and
  reappears at the bottom of its original bucket; and the editor's Restore
  action is absent when editing an open task.

  For the settings panel, five — every one of them silent when broken, which is
  why they are written down rather than trusted to be noticed. Add a type, then
  rename or delete a *different* one: the row you added must still be there
  afterwards (`refresh()` replaces `state`, and the pending row used to live in
  it). Add a type, press Close, reopen settings and press Save: it must **not**
  be created. Add a type, pick a colour for it, then delete another pending
  row: the colour must survive the re-render. Delete a type no task uses: it
  must ask first. And empty the Group limit box and press Save: it must refuse
  rather than store a 0 that every reader then treats as 5. For the tracked
  checkboxes, the failure path is the one worth seeing: delete a project's
  `.tasks/` folder outside the app, then tick its box — the alert appears
  *and* the box goes back to where it was, because a box left ticked over an
  untracked project is the claim you would act on right before committing.

  And five for **"Keep this window in front of everything else"**, which is the
  one setting whose effect is entirely outside the window — no test can see the
  frame the OS draws, and pywebview's `set_on_top` is the single window
  operation its WinForms backend does not marshal onto the UI thread, so
  "the write happened" and "the window moved" are genuinely different claims
  here. Launch with it unticked and click another window: the tracker must go
  behind it. Tick it and press Save: it must come to the front **immediately**,
  with no restart — this is the whole point of `_apply_on_top`, and a value
  that only takes effect next launch reads as the checkbox being broken. Untick
  and Save: another window must be able to cover it again, immediately. Press ↻
  with it ticked, and again with it unticked: the state must survive the
  restart both ways, since the replacement reads `settings.json` rather than
  inheriting anything. And move and resize the window, close it, relaunch: the
  geometry must still come back — `on_top` left `window.json` in the same
  change, and the file is written key by key, so a mistake there would silently
  take the position with it.

  And Escape, in all three overlays: it must close the editor, the settings
  panel and the progress view. Open a completed task from Progress so the
  editor sits on top of it, then press Escape once — the editor must close and
  Progress must still be there.

  For drag recategorization, ten — the whole feature is gesture, so none of it
  can be seen in a diff. Drag a loose task from `someday` onto a group inside
  `now`: it joins and moves to `now`. Drag it back out onto the `SOMEDAY`
  heading: it leaves the group and lands in `someday`. Drag a task into IN
  PROGRESS: it turns in-progress and **no Claude window opens**. Drag it from
  there onto `NEXT`: it resets and lands in `next`. With nothing running at
  all, the IN PROGRESS box still shows its line and still takes a drop. Drag a
  group header between buckets: every member moves, and `git status` in a
  tracked project shows frontmatter changes and **no body diff**. Drag a
  running group back to a bucket: every member resets, including any that were
  not running. Fold a group and drag a task into it: the folded members keep
  their order (invariant 18). Drop a row on *another* project's heading in IN
  PROGRESS: refused, with no outline at all. And the gestures that already
  existed must be untouched — reorder within one bucket, pair two rows into a
  new group whose name box opens focused, and rename it.

  And four for reordering IN PROGRESS, which is view state rather than task
  data and so has a different set of ways to be wrong. Drag a running task up
  or down its project's list: it must preview as it moves and stay where it was
  dropped. Do that in a tracked project and run `git status`: there must be
  **no diff at all** — nothing about the task changed, only what session.json
  remembers. Press ↻: the order must survive the restart. And claim a new task
  into IN PROGRESS: it must land at the END of that project's list, never
  silently in the middle of it.

  And five for the preview never outliving the gesture that drew it — the whole
  set is "nothing on screen may claim a place that was not written", and every
  one of them is silent, because a row left in the wrong place looks exactly
  like a row that moved. Start dragging a task, carry it a few rows, and let go
  **outside the list** — on the header, on the toolbar's Claude button, past the
  window edge: it must snap back where it started, not sit in its new place. Same drag,
  cancelled with **Escape** mid-drag: same. Both again in IN PROGRESS, which is
  where this was noticed. Then the confirmation that the snap-back is not
  overzealous: reorder a bucket properly and the row must STAY where it was
  dropped, with no flicker back to its old slot on the way. And the strip this
  opened up — drag a running task onto **the IN PROGRESS heading itself**, or
  into the padding around the box: it must land at the top of its own project's
  list and survive a ↻, rather than looking moved and reverting on the next
  edit. Dropping on ANOTHER project's rows is still refused, and must still
  leave the dragged row where it started.

  Two of those ten failed on first use and are the ones worth repeating after
  any change to `wireDrag`, because both looked like they had worked. Drop a
  task anywhere in the IN PROGRESS box — the padding beside the heading, the
  blank strip around the line, not only on the text — and the whole box must
  outline. And drag a running task into the *middle* of a bucket rather than
  onto its heading, then fold something to force a re-render: the task must
  still be where you put it. It moved on screen and was never written, which
  no amount of reading the diff would have shown.

  Six more for the geometry (invariant 28), which has no aimed targets left to
  lean on. Hold the cursor still on a seam between two rows: the preview must
  settle on one slot and stay there, not flicker between two. Drag slowly down
  a bucket that contains a group — the row must step into the group's rail
  while inside its box and back out below it, and where it is drawn is where it
  must land. Sort a row inside a group and overshoot the last member by a
  pixel: it must stay in the group. Drag it a clear centimetre below the group:
  it must leave. Drop on a bucket's `NOW`/`NEXT`/`SOMEDAY` heading: it must
  land at the top of that bucket, ungrouped, since a heading is now just the
  top of the box. And drag a row over another row's *edge* rather than its
  centre — it must reorder, never group; grouping must need the middle third.

  And fifteen for zoom and keyboard reach, which are entirely keyboard and so
  cannot be read out of a diff at all. The ladder and the ends were driven in a
  headless browser against the real scripts and the real vendored editor, so
  what is left here is what only a real window can answer — rendering, caret
  placement, and whether the layout survives.

  **Zoom.** Ctrl+`+` on the list: the rows grow, the header does not (the
  default). Ctrl+`-` back down, then once more at 100%: nothing moves and the
  pill says `100% · smallest` rather than nothing at all. Ctrl+`0` from 180%:
  straight back. Open Capture and Ctrl+`+`: the editor grows and the list
  behind it does not; close it and the list is still its own size. Press ↻:
  both sizes come back. Tick "Scale the header and toolbar too", Ctrl+`+` to
  200%, and narrow the window: the header must still be **one row** and the
  page must not grow a horizontal scrollbar — this is the case the setting
  exists for, and the reason it is off by default. Untick it: the header must
  return to its own size rather than staying big. Zoom the list to 200%, then
  drag a task between buckets and into a group: it must land where it is
  drawn, since the whole geometry (invariant 28) is now being measured at a
  different scale. Zoom the editor and click into the middle of a paragraph:
  the caret must land where clicked — ProseMirror positions from
  `elementFromPoint`, and that is the one thing about `zoom` no measurement
  outside a real window settles. Paste a screenshot into a zoomed editor and
  click it: the full-size viewer still opens.

  **Keyboard.** In Capture, type a body and press Shift+Tab: focus lands in the
  title box **and you can see that it did** — an invisible ring is the same
  defect as no ring. Shift+Tab again to Submit, again to Later, again to
  Cancel, again to wrap back into the body with the caret in it. Enter on each
  button must fire it. In triage the ring must include Skip and Discard; on a
  done task opened from Progress it must include Restore. And in the body,
  indenting a list item with Tab must still work — only Shift+Tab was taken.
  Then Enter **in the title box**, which is the fast path the ring exists to
  reach: type a body, Shift+Tab to the title, type a name, press Enter — the
  task is filed exactly as the button files it. With the title empty it must
  raise the same "give it a title" alert rather than doing nothing, and in
  triage it must file the note and move to the next one. Enter in the **body**
  must still make a new line.

  **The editor toolbar.** Narrow the window, or zoom the editor, until the `…`
  overflow button appears: there must be **no stray light line just right of
  it**. It is not a divider and not an element at all — it is the icon sprite
  sheet bleeding its next cell, and `ui/style.css` clips 2px off `more` for it.
  Hover `…` as well: the highlight must not look cut off on that side.

  **Cancel.** Capture, type one character, Escape: it asks. Capture, type
  nothing, Escape: it closes. Open an existing task and Escape immediately: it
  closes with no question. Open one, change only its colour, Escape: it asks.
  Open one, change nothing, press Save: it must still save with **no body
  diff** in a tracked project — the invariant 13 check, repeated because this
  feature reads the same baseline.

  And eighteen for the drag being a pointer gesture with motion, which is the
  whole of `ui/drag.js` and `ui/drag-geometry.js` and none of which a diff can
  show. **Drag has no automated behavioural coverage, by decision (2026-07-27)**
  — a headless harness driving the real scripts was offered and declined, and
  the prototype at `docs/superpowers/prototypes/2026-07-26-drag-feel.html` and
  the harness generator beside it (`2026-07-27-drag-harness.js`, which nothing
  runs) are the reversal path if that is ever revisited — the harness is what
  found six of this feature's bugs, and its header says how to run it. Three
  convention tests guard part of it and are named where they apply below.

  **One known bug is open and is not worth re-deriving.** A row displaced by a
  drag twitches the wrong way for 1–2 frames before animating correctly. It is
  filed as a UX task; the reproduction asset is
  `docs/superpowers/prototypes/2026-07-26-drag-feel.html`, whose drag does not have
  it — compare against that rather than reasoning from the code. Five attempts
  failed and none of their theories are recorded here on purpose. The harness
  never reproduced it, so it is a safety net rather than a detector; what this
  needs is a per-frame dump inside the running app.

  **The card.** Grab any row and move: **exactly one** of it on screen, fully
  opaque, under the cursor, with a dashed outline where it came from, and no
  sideways drift. Zoom the list to 200% and drag: the card must be the same size
  as its gap — it is a clone in a zoom region, and a mismatch there is the whole
  reason `#drag-layer` is one.

  **The aiming rule (invariant 28).** Grab a row **2px above its own bottom
  edge** and twitch 6px sideways: nothing reorders. Move down slowly: it yields
  as the *card* reaches the next row's edge, not before. Hold still on a
  threshold: it settles on one slot and stays. Drag out of NOW into SOMEDAY:
  **NEXT and SOMEDAY must not move under the cursor.** Drag a row over another's
  edge → reorders; over its middle quarter → pairs, name box focused.

  **Leaving a group**, which took two rounds to get right. Drag a member of a
  two-member group clear of the block: it comes out loose and **stays** loose —
  not snapping back, not pairing with the row below. Then drag the remaining
  member out: the group must **fade** as soon as the card is clear of it, and
  come back if you move back in. With two members left it must NOT fade, because
  the group survives.

  **The motion.** Drag a row quickly past two or three others: the displaced
  rows must **begin to move**, not hop and then slide. Reverse direction
  mid-drag: they reverse from where they are. Drop: the card flies to its slot,
  *then* the gap closes, *then* the row flashes — in that order, not together.
  Drop and immediately start a second drag inside the settle: the second card is
  the row you grabbed, not the previous one.

  **Every other rearrangement, which now shares that motion.** Change a bucket
  with the `<select>`; fold and unfold a group; press `done` (the row dissolves
  in place while the rows below slide up, as one motion); complete a whole group
  from its header (the block goes as one thing, not row by row); Restore from
  Progress. Then the guard: **type in the search box — nothing may animate, on
  any keystroke**, and nothing may animate coming back out of it either.

  **Autoscroll and the endings.** Make a list long enough to scroll and drag to
  the window's bottom edge: it scrolls, and the row lands where it is drawn.
  Release on the header, past the window edge, and with Escape: the card flies
  home each time, the row does **not** flash, and nothing is written.

  **The gestures the pointer rewrite could silently break**, all of which the
  `draggable` attribute used to carry: single-click a row (editor opens);
  double-click a title, and a group name (each renames); select text in a rename
  box with the mouse (selects, does not drag); open a row's bucket `<select>`;
  click the checkbox, the Claude button, copy and `done` (each does its own job,
  none starts a drag); drag in the **search** view (must not drag, and must show
  no grab cursor). And one that has nothing to do with dragging: after
  cancelling a drag with Escape, **press Enter on a focused button** — it must
  fire. The click-suppressor is armed at that moment and only a `pointerdown`
  disarms it, so a keyboard activation is the thing it can wrongly eat.
