# Drag Animation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make dragging a task feel like moving the task — the real card in your
hand, neighbours that slide, and a drop that lands where you aimed.

**Architecture:** Native HTML5 DnD is replaced by pointer events. A `position:
fixed` clone is what you hold; the original stays in the flow as the gap. Where a
drop lands is decided by **the card's centre crossing frozen edges** (Reardon's
rule), not by the pointer crossing live midpoints. The preview remains a real DOM
`insertBefore`, so every existing placement invariant and the whole drop path are
untouched. Neighbours animate with FLIP.

**Tech Stack:** Plain ES2020 in `<script>` tags sharing one global scope. Web
Animations API (`element.animate`), CSS transitions, Pointer Events. No bundler,
no framework, no new dependency.

**Spec:** `docs/superpowers/specs/2026-07-26-drag-animation-design.md`
**Prototype:** `docs/superpowers/prototypes/2026-07-26-drag-feel.html` — a working
implementation of the whole rule, driven by synthetic pointer events and verified
23/23. **Every JavaScript snippet in this plan is lifted from it**, so none of
them is an unexecuted guess. Open it in a browser to feel any step before writing
it.

## Global Constraints

- **Worktree:** `.claude/worktrees/drag-animation` on `feature/drag-animation`,
  branched from `main` at `59bc68c`. Baseline: **383 passed**.
- **PowerShell, not Bash.** The Bash tool cannot resolve `.venv\Scripts\python.exe`.
  PowerShell 5.1 has no `&&`/`||` — chain with `;` or `if ($?) { }`. Never put
  `2>&1` on a native command: it wraps stderr in ErrorRecord and sets `$?` false
  on a successful exit.
- **Run the suite from the worktree root, with a relative path:**
  `Set-Location <worktree>; & ".venv\Scripts\python.exe" -m pytest tests/ -q`
- **Never run `app.py`.** It opens a window on the user's desktop and writes to
  their real `~/.task-tracker/`. No test may put anything on screen.
- **There is no JS test runner, and none is being added** (decided 2026-07-26).
  Every JS task's machine-checkable verification is exactly three things:
  `node --check ui/*.js`, the full Python suite, and the three convention tests
  named per task. **None of them can see whether the card follows the cursor.**
  So every JS task also carries a **HAND-OFF** block: the checks only the user
  can run. Give it to them *when that task lands*, not at the end of the plan —
  a UI task signed off from its diff cost a Critical on 2026-07-26.
- **A JS task has no RED phase.** Withholding the feature cannot make any
  existing test fail, because no test reads behaviour. Where a task *can* be
  driven test-first — Task 2 — it is, and the plan says so. Everywhere else the
  cycle is: change, `node --check`, suite, hand off.
- **Invariant 5:** user-authored text never reaches `innerHTML`. A `cloneNode` is
  safe — it copies nodes, not markup.
- **Invariant 3/4:** bridge calls go through `callApi`; the failure sentinel is
  `API_FAILED`, never `null`.
- **Extend a CSS comment BEFORE its closing `*/`.** Prose after the marker
  silently discards the entire following rule. `test_the_stylesheet_has_no_stray_comment_markers` guards it.
- **Commit messages:** imperative, and on Windows multi-line messages go through
  `git commit -F <file>` — PowerShell 5.1 splits embedded double quotes into
  pathspec errors.

---

# Phase 1 — the gesture and the rule

Ends with the drag *correct* and still snapping, so the rule can be judged
without motion confusing it.

---

### Task 1: Split the drag out of `ui/groups.js` — pure move, zero behaviour change

**Files:**
- Create: `ui/drag-geometry.js`
- Create: `ui/drag.js`
- Modify: `ui/groups.js` (951 → ~380 lines)
- Modify: `ui/index.html:146` (script tags)

**Interfaces:**
- Consumes: nothing.
- Produces: the same global function names as today, in new files. Nothing is
  renamed. Later tasks modify these in place.

Everything resolves at call time in this codebase, so load order does not matter
for cross-file calls — but the files must be *listed*, or every symbol in them is
undefined at the first call site (`test_every_ui_script_is_loaded_by_the_page`).

- [ ] **Step 1: Record the symbol inventory before touching anything**

```powershell
Set-Location "C:\Users\griff\Desktop\code\task_tracker\.claude\worktrees\drag-animation"
Select-String -Path ui\groups.js -Pattern '^(function|const|let) [A-Za-z_]+' |
  ForEach-Object { $_.Line } | Sort-Object | Out-File -Encoding utf8 ..\..\..\before-symbols.txt
Get-Content ..\..\..\before-symbols.txt | Measure-Object -Line
```

Keep this file. Step 6 asserts the same set exists afterwards, spread across
three files. A pure move that silently drops a function is the one failure mode
here, and it is invisible until a handler reaches for it at runtime.

- [ ] **Step 2: Move the geometry into `ui/drag-geometry.js`**

Cut these from `ui/groups.js`, in this order, keeping every comment with its
function:

| From | Symbol |
|---|---|
| 416 | `groupOf` |
| 421 | `taskOf` |
| 429 | `draggedState` |
| 459 | `sectionPlacement` |
| 469 | `projectBlockUnder` |
| 490 | `ownRunningList` |
| 507 | `placement` |
| 523–530 | `PAIR_BAND`, `PAIR_INSET`, `GROUP_STICKY` |
| 545 | `sectionUnder` |
| 566 | `blocksIn` |
| 581 | `slotFor` |
| 592 | `withinBox` |
| 601 | `groupUnder` |
| 632 | `pairTarget` |
| 643 | `dropIntent` |

- [ ] **Step 3: Move the gesture into `ui/drag.js`**

| From | Symbol |
|---|---|
| 411 | `clearDropAffordance` |
| 616 | `inProgressOrderFromDom` |
| 712–936 | `wireDrag` |
| 937 | the bare `wireDrag()` call — it stays at the bottom of the new file |

`ui/groups.js` keeps lines 1–370 and `focusGroupName` (943–950).

- [ ] **Step 4: Split the banner comment at 371–410 between the two files**

This is the one part that is not mechanical, and skipping it orphans half a
comment in the wrong file. Today's block covers four separate things. Route them:

- the "ONE controller bound once to `#task-list`" history and the
  `dragstart`/`dragover` cross-section bug → **`ui/drag.js`**, above `wireDrag`.
- "a drop resolves to a DESTINATION applied by a single call", the `pair`/`sort`
  naming, "a refusal is null" → **`ui/drag-geometry.js`**, above `dropIntent`.
- "WHERE a drop lands is read from GEOMETRY, not from `event.target`" and the two
  rectangles → **`ui/drag-geometry.js`**, at the top of the file.
- "reordering is the common gesture and grouping the rare one" → **`ui/drag-geometry.js`**,
  above `PAIR_BAND`, where the constants it explains live.

Each new file opens with a one-line statement of what it owns, matching the style
of `ui/zoom.js:1` and `ui/groups.js:1`.

- [ ] **Step 5: Add both script tags**

`ui/index.html`, immediately after `<script src="groups.js"></script>`:

```html
    <script src="drag-geometry.js"></script>
    <script src="drag.js"></script>
```

- [ ] **Step 6: Verify nothing was lost, and that both halves parse**

```powershell
node --check ui\drag-geometry.js; node --check ui\drag.js; node --check ui\groups.js
Select-String -Path ui\groups.js,ui\drag.js,ui\drag-geometry.js -Pattern '^(function|const|let) [A-Za-z_]+' |
  ForEach-Object { $_.Line } | Sort-Object | Out-File -Encoding utf8 ..\..\..\after-symbols.txt
Compare-Object (Get-Content ..\..\..\before-symbols.txt) (Get-Content ..\..\..\after-symbols.txt)
```

Expected: `node --check` silent three times, and `Compare-Object` prints
**nothing**. Any `<=` line is a symbol that vanished; any `=>` line is one that
was accidentally duplicated, which in a shared global scope means the later file
silently wins.

- [ ] **Step 7: Run the full suite**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: `383 passed`. `test_every_ui_script_is_loaded_by_the_page` and
`test_every_element_id_the_scripts_ask_for_exists` both pass over the new files.

- [ ] **Step 8: Commit**

```powershell
git add ui/drag-geometry.js ui/drag.js ui/groups.js ui/index.html
git commit -F <message file>
```

Message: `refactor: the drag moves out of groups.js into its own two files`

**HAND-OFF (user runs the app):** this task changes nothing a user can see, which
is the whole point — so the check is that *everything* still works. Reorder inside
a bucket. Drag a task into a group and back out. Pair two rows into a new group
and confirm its name box opens focused. Drag a group header between buckets. Drag
a task into IN PROGRESS and back out. Reorder within IN PROGRESS and press ↻ to
confirm the order survived. If any of these is broken, the split lost something
and Step 6 missed it.

---

### Task 2: `#drag-layer` and the stacking ladder — test-first

**Files:**
- Modify: `tests/test_conventions.py` (`STACKING_ORDER`)
- Modify: `ui/style.css` (four ranks)
- Modify: `ui/index.html` (the element)
- Modify: `ui/zoom.js:69-79` (`zoomAssignments`)

**Interfaces:**
- Produces: `<div id="drag-layer">`, rank 2, a member of the `app` zoom region.
  Task 3 appends the held card into it.

This is the one task in the plan with a real RED phase, because the contract is
enforced by a Python test.

- [ ] **Step 1: Add `#drag-layer` to `STACKING_ORDER`**

In `tests/test_conventions.py`, insert `"#drag-layer"` between `"#selection-bar"`
and `".overlay"`. Do not touch `test_the_floating_surfaces_are_ranked_in_one_order`
itself — the list is the contract, the assertions already say what must hold.

- [ ] **Step 2: Run it and watch it fail**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/test_conventions.py::test_the_floating_surfaces_are_ranked_in_one_order -q
```

Expected: FAIL, `These floating surfaces carry no z-index … #drag-layer`.

- [ ] **Step 3: Shift the ladder in `ui/style.css`**

There is no integer between `#selection-bar`'s 1 and `.overlay`'s 2, and the test
rejects equal ranks. So:

| Selector | Was | Becomes |
|---|---|---|
| `#selection-bar` (~485) | 1 | 1 — unchanged |
| `#drag-layer` | — | **2** |
| `.overlay` (319) | 2 | **3** |
| `#editor` (335) | 3 | **4** |
| `#zoom-badge` (~624) | 4 | **5** |

Add the `#drag-layer` rule:

```css
/* Rung 2. What you are holding mid-drag: a fixed clone of the row, which must
   paint over the list and over the selection bar — you can drag across it — and
   under every overlay. There is no integer between the bar's 1 and .overlay's 2,
   and equal ranks fall back to DOM order, which is the tie #editor's own rule
   exists to break — so the three rungs above this one each moved up by one.
   It is a zoom region (ui/zoom.js) so the card scales with the list it came
   from; a card at the list's old size against a gap at the new one reads as a
   rendering fault. */
#drag-layer { position: fixed; inset: 0; pointer-events: none; z-index: 2; }
```

`inset: 0` with `pointer-events: none`: the layer covers the window so a fixed
child can be placed anywhere in it, and it can never eat a `pointerdown`.

**Update `#selection-bar`'s comment**, which currently enumerates the whole
ladder in prose ("the bar beats the task list, every overlay beats the bar, the
editor beats the other overlays, and `#zoom-badge` beats all of it"). It must
name the card's rung too, or the file's own documentation of the ladder is wrong
one line above the ranks it describes. Extend it **before** the closing `*/`.

- [ ] **Step 4: Add the element and the zoom assignment**

`ui/index.html`, immediately after `<main id="task-list"></main>`:

```html
    <!-- What you are holding mid-drag. Outside #task-list on purpose: the drop
         path reads section.querySelectorAll('.task') and the FLIP sweeps
         .task, .group — a clone inside the list would be counted by both. Its
         RANK is what puts it above the selection bar (style.css), not its
         position here. -->
    <div id="drag-layer"></div>
```

`ui/zoom.js`, in `zoomAssignments()`, after `['task-list', 'app'],`:

```javascript
    ['drag-layer', 'app'],
```

- [ ] **Step 5: Run the tests to verify they pass**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: `383 passed`. `test_every_element_id_the_scripts_ask_for_exists`
tolerates an id no script asks for yet; Task 3 is what reads it.

- [ ] **Step 6: Commit**

Message: `feat: the drag layer takes rung 2, and the three above it move up`

**HAND-OFF:** open Progress, then open a completed task from it — the editor must
still appear *on top of* Progress, with Cancel reachable. Tick a task and open the
editor: the selection bar must be behind it. Press Ctrl+`+` — the zoom badge must
still be visible and on top. These three are what the ladder shift could break.

---

### Task 3: Pointer events, the card, and the gap

**Files:**
- Modify: `ui/drag.js` (`wireDrag`)
- Modify: `ui/tasks.js` (`taskRow`, `renameTaskInPlace`, `renderSearch`, `renderAllProjects`)
- Modify: `ui/groups.js` (delete `releaseDragWhileUsing` and its 8 call sites, `renameInPlace`)
- Modify: `ui/style.css`

**Interfaces:**
- Consumes: `#drag-layer` (Task 2).
- Produces: inside `wireDrag`, a `drag` object with `{element, isGroup, held,
  grabX, grabY, startX, fix, size, origin, from, intent, wrote}`. Task 4 adds the
  probe; Task 5 adds the endings; Task 6 adds FLIP.
- Produces: `.nodrag` as the "this view cannot drag" flag, replacing the
  `draggable` attribute.

Behaviour after this task: the card is in your hand and the gap opens, but the
preview still **snaps** and the drop still cuts. That is deliberate — Task 4
changes the rule, Phase 2 adds the motion.

- [ ] **Step 1: Replace `draggable` with `.nodrag`**

Three places set `draggable` as a *permission* today, and dropping the attribute
without replacing them re-enables dragging where it is deliberately off:

- `ui/tasks.js` `taskRow`: `row.draggable = draggable` → `if (!draggable) row.classList.add('nodrag')`.
- `ui/tasks.js` `renderSearch`, `renderAllProjects`: `row.draggable = false` →
  `row.classList.add('nodrag')`.
- `ui/groups.js` `groupBlock`: `header.draggable = headerDraggable` → the same
  class on the header.

Then delete outright:

- `ui/groups.js` `releaseDragWhileUsing` and all **eight** call sites (caret,
  select-group, bucket picker, claude, reset, done, disband — and the one in the
  group header added with the Claude button). Its whole purpose was that a
  `<select>` or button inside `draggable="true"` starts a drag in Chromium
  instead of doing its own job. With no `draggable` attribute there is nothing to
  suspend.
- `ui/tasks.js` `renameTaskInPlace`'s `wasDraggable`/`restore` juggling, and
  `ui/groups.js` `renameInPlace`'s `restoreDrag`. Same reason: a text box inside
  `draggable="true"` could not be selected with the mouse.
- `ui/style.css` `.group-header[draggable="false"] { cursor: default; }` — dead.

And move the grab cursor onto the new condition, which fixes a pre-existing
wrongness: search rows advertise `cursor: grab` today for a gesture that has
never worked there.

```css
.task.nodrag, .group-header.nodrag { cursor: default; }
```

- [ ] **Step 2: Style the card and the three gap looks**

```css
/* The card you hold. A cloneNode of the row, so every rule that draws a row
   draws this too — which is why it lives inside a zoom region and why it must
   not live inside #task-list.
   ONE transition declaration, and it names transform only: left and top carry
   the follow, and easing the POSITION is the disconnect this whole change
   exists to remove. */
.held { position: fixed; margin: 0 !important; border-radius: 5px;
        background: #232323; pointer-events: none; cursor: grabbing;
        box-shadow: 0 10px 26px rgba(0, 0, 0, .6),
                    0 1px 0 rgba(255, 255, 255, .06) inset;
        transition: transform 130ms cubic-bezier(0, 0, .2, 1); }

/* The gap. It is the ORIGINAL element, still in the flow, so its box is exactly
   the right size by construction and there is no placeholder to keep in sync.
   A dashed outline says the space is reserved rather than empty; outline claims
   no layout width, so showing it cannot nudge a neighbour. */
.dragging-source { background: rgba(127, 127, 127, .05); border-radius: 5px;
                   outline: 1px dashed rgba(127, 127, 127, .4);
                   outline-offset: -1px; }
.dragging-source > * { visibility: hidden; }
```

`.dragging-source > *` rather than `visibility: hidden` on the element itself:
the outline must still paint. For a dragged `.group` the children are the header
and the member rows, all of which hide, leaving the block's own dashed box.

- [ ] **Step 3: Rewrite `wireDrag`'s event wiring**

`pointerdown` on `#task-list`; `pointermove`, `pointerup` and `pointercancel` on
`window`. From the prototype:

```javascript
  const THRESHOLD = 4;
  let press = null, drag = null;

  list.addEventListener('pointerdown', event => {
    if (event.button !== 0) return;
    // A control does its own job. This one guard replaces
    // releaseDragWhileUsing's per-control registration, and it covers every
    // button added later — .claude arrived after this design was written.
    if (event.target.closest('input, select, button, .title-input, .group-name-input')) return;
    const header = event.target.closest('.group-header');
    const element = header ? header.parentElement : event.target.closest('.task');
    if (!element || (header || element).classList.contains('nodrag')) return;
    press = { element, isGroup: Boolean(header), x: event.clientX, y: event.clientY };
  });
```

`window`, not `setPointerCapture`: a drag that leaves the list must keep tracking
and a release out there must still end it — and capture throws when the pointer
id is not active, which is also what makes it impossible to drive with a
synthetic event.

```javascript
  window.addEventListener('pointermove', event => {
    if (drag) { move(event); return; }
    if (!press) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) < THRESHOLD) return;
    begin(event);
  });
  window.addEventListener('pointerup', () => { press = null; if (drag) finish(false); });
  window.addEventListener('pointercancel', () => { press = null; if (drag) finish(true); });
  window.addEventListener('keydown', event => {
    if (event.key === 'Escape' && drag) { press = null; finish(true); }
  });
```

The 4px threshold is what preserves click-to-open-the-editor and
double-click-to-rename. Below it the gesture is a click and `taskRow`'s existing
`onclick` handles it untouched.

Delete the `dragstart`, `dragover`, `dragend` and `drop` listeners. `dropIntent`,
`undoPreview`, `startedAt` and `wrote` all survive — Task 5 rewires them.

- [ ] **Step 4: Build the card in `begin()`**

Verbatim from the prototype, which is where the two non-obvious lines were
measured:

```javascript
  function begin(event) {
    const { element, isGroup } = press;
    const layer = document.getElementById('drag-layer');
    // A settle from the previous drop may still be running; flush it. Unflushed,
    // the previous card is still in the DOM holding its gap, so `.held` resolves
    // to the wrong element and the new card tracks nothing (measured).
    layer.replaceChildren();
    document.querySelectorAll('.dragging-source')
      .forEach(stale => stale.classList.remove('dragging-source'));

    const box = element.getBoundingClientRect();
    const held = element.cloneNode(true);
    held.classList.add('held');
    held.style.width = box.width + 'px';
    layer.append(held);

    // position: fixed does NOT resolve against the viewport inside a zoomed
    // element. Probe the mapping rather than reasoning about it: this yields the
    // offset and the scale together and cannot be wrong about the engine.
    held.style.left = '0px';  held.style.top = '0px';
    const at0 = held.getBoundingClientRect();
    held.style.left = '100px'; held.style.top = '100px';
    const at100 = held.getBoundingClientRect();
    const scale = { x: (at100.left - at0.left) / 100, y: (at100.top - at0.top) / 100 };
    const fix = { x: at0.left, y: at0.top };

    drag = { element, isGroup, held, fix, scale,
             size: { w: box.width, h: box.height },
             grabX: press.x - box.left, grabY: press.y - box.top,
             startX: press.x, startY: press.y,
             origin: { parent: element.parentElement, before: element.nextSibling },
             intent: null, wrote: false };
    held.style.transformOrigin = drag.grabX + 'px ' + drag.grabY + 'px';
    element.classList.add('dragging-source');
    document.body.classList.add('dragging');
    move(event);

    // The lift, as a CSS TRANSITION rather than element.animate(fill:'forwards').
    // A forwards-filling WAAPI animation outranks the inline style for the
    // property it animates for as long as it exists, so the settle's own probe
    // would read the lift's scale back even after clearing the transform.
    held.style.transform = 'scale(1)';
    requestAnimationFrame(() => {
      if (drag && drag.held === held) held.style.transform = 'scale(1.05)';
    });
  }
```

Verify the probe: `scale.x` and `scale.y` must equal `zoomFactor('app')`. Log both
once during development at 100% and 200% and confirm; if they disagree, the probe
is right and the spec's reasoning was wrong.

- [ ] **Step 5: Follow the pointer in `move()`**

```javascript
  function move(event) {
    const { held, grabX, grabY, fix, scale } = drag;
    // Rail-locked: vertical only, so the card stays over the column it came from
    // and reads as the row itself lifted out of the list.
    const cardX = drag.startX - grabX;
    const cardY = event.clientY - grabY;
    held.style.left = ((cardX - fix.x) / scale.x) + 'px';
    held.style.top = ((cardY - fix.y) / scale.y) + 'px';
    ...
  }
```

**No transition on `left` or `top`.** `.held`'s single `transition` declaration
names `transform` only, and it must stay that way.

- [ ] **Step 6: Keep the preview and the affordance exactly as they are**

For this task, `move()` still calls `dropIntent(event, element, isGroup)` with the
event, still does the `insertBefore`, and still adds `.drop-zone`/`.drop-into` by
the existing rule. Task 4 changes what is passed in. Nothing about invariant 28's
one-box rule changes in this task or any later one.

- [ ] **Step 7: `finish()` — minimal, no animation yet**

Remove the card, clear the gap class and `body.dragging`, then take the *existing*
drop body — every branch of it, `pair`/`sort`/`place`, unchanged — and run it. On
abandon, call the existing `undoPreview()`. Task 5 hardens this; Task 7 animates it.

- [ ] **Step 8: Add `user-select` suppression**

```css
body.dragging { user-select: none; cursor: grabbing; }
```

Without it, a pointer drag across text selects it, which is what the native API
suppressed for free.

- [ ] **Step 9: `node --check` and the full suite**

```powershell
node --check ui\drag.js; node --check ui\tasks.js; node --check ui\groups.js
& ".venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: silent, then `383 passed`. `test_every_class_the_ui_toggles_is_styled`
is the one that matters here — it checks `.held`, `.nodrag` and
`.dragging-source` are actually styled. **Know its blind spot** (recorded in
invariant 28): it passes on a *stale* selector, because a class name is matched as
a substring. It cannot tell you a rule stopped matching.

- [ ] **Step 10: Commit**

Message: `feat: the thing you drag is the card, not a translucent OS bitmap`

**HAND-OFF — the core of this task, and none of it is visible in a diff:**
Grab any row and move it. There must be **exactly one** of it on screen, fully
opaque, under your cursor, with a dashed outline where it came from. It must not
drift sideways as you move. Let go: it lands. Now the regressions this task can
cause, every one of them silent: single-click a row (editor opens), double-click a
title (renames), double-click a group name (renames), select text inside a rename
box with the mouse (selects, does not drag), open the bucket `<select>` on a row
(opens), click the checkbox, the Claude button, the copy button and `done` (each
does its own job and none starts a drag), and drag a row in the **search** view
(must not drag at all, and must show no grab cursor). Then zoom to 200% and drag:
the card must be the same size as its gap.

---

### Task 4: Reardon's rule — the card's centre against frozen edges

**Files:**
- Modify: `ui/drag-geometry.js` (every geometry primitive, `dropIntent`'s signature)
- Modify: `ui/drag.js` (`begin` freezes, `move` computes the probe, `finish` clears)

**Interfaces:**
- Produces: `freeze()`, `fbox(element)`, `slotByCentre(blocks, centreY, dragged,
  container)`.
- Produces: `dropIntent(probe, dragged, draggedIsGroup)` where `probe` is
  `{x, y}` in viewport pixels — **not** an event. Every geometry helper takes
  `probe` in place of `event`.
- Removes: `PAIR_INSET`, and `slotFor`'s `displaced` compensation.

This is the task that fixes the feel. The measurements are in the spec; the two
that decide the design: today's rule reorders a row grabbed near its bottom edge
on the very first 6px *sideways* move, and Reardon's rule lands on the edge to
0.3px.

- [ ] **Step 1: Change every geometry helper to take a probe, not an event**

Mechanical, and the point is what it makes provable: `sectionUnder`,
`withinBox`, `groupUnder`, `pairTarget`, `projectBlockUnder`, `ownRunningList`
and `dropIntent` all read only `.clientX`/`.clientY` off the event today. Replace
the parameter with `probe` and the reads with `probe.x`/`probe.y`.

Afterwards `ui/drag-geometry.js` must contain **no** `clientX` or `clientY` at
all — the probe is built in `ui/drag.js` and nowhere else. Step 8 pins that.

- [ ] **Step 2: Add the frozen cache**

```javascript
// Every box in the list, measured ONCE at lift and never again.
//
// Not an optimisation — the edge rule is UNSTABLE without it. Reordering live
// moves the very edge that decided the reorder, so the forward and reverse
// triggers land on the same pixel and the row flickers between two slots under a
// still cursor. Frozen, each block has exactly one threshold for the whole
// gesture. It also stops the thing you are aiming at from moving: today a row
// leaving NOW shortens NOW and lifts NEXT and SOMEDAY up under the cursor.
let frozen = null;

function freeze() {
  frozen = new Map();
  const list = document.getElementById('task-list');
  for (const element of list.querySelectorAll(
      'section, .project-block, .group, .task')) {
    frozen.set(element, element.getBoundingClientRect());
  }
}

function fbox(element) {
  return (frozen && frozen.get(element)) || element.getBoundingClientRect();
}
```

`.project-block` is in the set and is not in the prototype: IN PROGRESS holds its
blocks one level down inside a wrapper per project, and `projectBlockUnder` and
`ownRunningList` both measure those wrappers.

Then replace `getBoundingClientRect()` with `fbox()` in `sectionUnder`,
`withinBox`, `pairTarget` and `slotFor`. Leave it alone in `begin()`'s own
measurement of the dragged element — that runs before `freeze()` returns and is
about the card, not the geometry.

- [ ] **Step 3: Replace `slotFor` with the counting rule**

```javascript
// "Once the centre position of an item A goes over the edge of another item B, B
// moves out of the way." — Reardon. One frozen threshold per block, and the slot
// is simply how many of them the centre has passed.
//
// Which edge depends on where the block started relative to the dragged one, and
// that is not arbitrary — it is what produces the dead zone. A block that was
// BELOW yields when your centre reaches its top; a block that was ABOVE yields
// when your centre reaches its bottom. Both are half a card-height from where you
// started, so the row never twitches out of its own slot.
//
// In a list the dragged block was never in there is no gap and no before/after,
// so the threshold is the block's centre — the ordinary insertion rule. An edge
// rule cannot express "index 0" there: the first block's top edge IS the top of
// the list, so it reads as already passed the moment you arrive.
function slotFor(blocks, centreY, dragged, container) {
  const home = frozen && frozen.has(dragged) && dragged.parentElement === container;
  const mine = home ? fbox(dragged).top : null;
  let passed = 0;
  for (const block of blocks) {
    const box = fbox(block);
    const threshold = home ? (box.top >= mine ? box.top : box.bottom)
                           : box.top + box.height / 2;
    if (centreY >= threshold) passed++;
  }
  return passed;
}
```

`displaced` and the `compareDocumentPosition` check are **deleted**. They existed
to take the dragged element's own height back out of a live measurement; a frozen
threshold set has nothing to compensate for. Every `slotFor` call site gains the
container as a fourth argument — there are three, all inside `dropIntent`.

- [ ] **Step 4: Sort the candidate list by frozen order**

`blocksIn` returns live children, and the preview has already permuted them —
which would make the returned index mean something different every frame.

```javascript
function blocksIn(container, dragged, selector) {
  const live = [...container.children].filter(
    child => child !== dragged && child.matches(selector));
  if (!frozen) return live;
  return live.sort((a, b) => fbox(a).top - fbox(b).top);
}
```

- [ ] **Step 5: Remove `PAIR_INSET`**

With the card rail-locked, its centre's x never changes for the whole drag, so
`PAIR_INSET` and `withinBox`'s x bounds against full-width sections and groups
always pass. The geometry is purely vertical.

The alternative — keep using the *pointer's* x for the inset alone — is exactly
the disconnect this work removes: a decision made by something the card does not
show. Delete the constant and its use in `pairTarget`; pairing is aimed by
`PAIR_BAND` alone, the middle third of a row's height.

- [ ] **Step 6: Build the probe in `ui/drag.js`**

In `begin()`, call `freeze()` **first**, before the clone is appended or the gap
class is added — these are the only boxes measured at rest for the whole gesture.

In `move()`, after positioning the card:

```javascript
    // What decides everything: the middle of the card you are holding. Where you
    // grabbed the row stops mattering, and the list responds to the thing you can
    // see rather than to a pointer that may be 20px off one end of it.
    const probe = { x: cardX + size.w / 2, y: cardY + size.h / 2 };
    drag.intent = dropIntent(probe, element, isGroup);
```

`size` is the card's own box. For a dragged group that is the whole block, which
is what `groupTransit = full` means.

In `finish()`, `frozen = null`. Left behind it answers the next drag's geometry
with the last drag's layout. Export a `clearFrozen()` from `drag-geometry.js`
rather than reaching across files into the variable.

- [ ] **Step 7: Rewrite invariants 27, 28 and 29 in `CLAUDE.md`**

Not a documentation chore — three of those clauses are now false, and this repo's
invariants are its primary defence. Exactly what changes is enumerated in the
spec's "Invariants this changes" section. In particular: invariant 27's
"`dropIntent` refuses a drop whose target is the dragged row itself" paragraph
describes a failure mode that **cannot occur any more** and must be recorded as
gone, not as guarded; invariant 28 loses "inset from both ends" and `slotFor`'s
`displaced` note; and both gain the frozen cache. `sectionUnder`'s "the margin
between two sections belongs to the one below" rule is unchanged and must stay.

- [ ] **Step 8: Pin the probe boundary with a convention test**

A text-level convention test in the family the repo already has seventeen of —
**not** the headless harness that was declined.

```python
def test_the_drag_geometry_never_reads_the_pointer_directly():
    """The card's centre decides where a drop lands, not the mouse pointer.

    Those are different points, and the difference is the whole of the bug this
    replaced: the pointer sits wherever you happened to grab the row, so grabbing
    2px above a row's bottom edge reordered it on the first 6px sideways twitch,
    before it had moved down at all (measured 2026-07-26).

    The probe is built in ui/drag.js and passed in. A helper here that reaches for
    event.clientY instead would work, and would silently aim with the pointer
    again for whichever gesture it decides.
    """
    source = (REPO / "ui" / "drag-geometry.js").read_text(encoding="utf-8")
    assert "clientX" not in source and "clientY" not in source
```

- [ ] **Step 9: Run it, and confirm it has teeth**

```powershell
& ".venv\Scripts\python.exe" -m pytest tests/ -q
```

Expected: `384 passed`. Then prove the new test can fail: temporarily put
`event.clientY` in a comment in `ui/drag-geometry.js`, re-run, see it fail, remove
it. A test that cannot be made to fail asserts nothing, and this project has
already shipped five of those.

- [ ] **Step 10: Commit**

Message: `feat: a drop is aimed by the card's centre, against frozen edges`

**HAND-OFF — this is the task the whole feature is for:**
Grab a row **2px above its own bottom edge** and twitch 6px sideways: nothing
must reorder. Grab the same row and move down slowly: it must yield exactly as the
*card* reaches the next row's edge, not before. Hold the cursor still on a
threshold: the preview must settle on one slot and stay there, not flicker. Drag
out of NOW into SOMEDAY: **NEXT and SOMEDAY must not move under your cursor.**
Sort a row inside a group and overshoot the last member by a pixel: it stays in
the group. Drag it a clear centimetre below: it leaves. Drop on a
NOW/NEXT/SOMEDAY heading: top of that bucket, ungrouped. Drag a row over another
row's edge: reorders. Over its middle: pairs, and the name box opens focused.

---

### Task 5: Autoscroll, and the three endings

**Files:**
- Modify: `ui/drag.js`

**Interfaces:**
- Consumes: everything from Tasks 3 and 4.
- Produces: `finish(cancelled)` handling all three endings; `autoscroll(y)`.

- [ ] **Step 1: Autoscroll the document**

Native DnD scrolls near the edge for free; pointer events do not. The app has no
inner scroll container — `body` carries the padding and the *document* scrolls.

```javascript
  const EDGE = 46, SPEED = 12;
  let scrollTimer = null;
  function autoscroll(pointerY) {
    const height = document.documentElement.clientHeight;
    const up = pointerY, down = height - pointerY;
    const delta = up < EDGE ? -SPEED * (1 - up / EDGE)
                : down < EDGE ? SPEED * (1 - down / EDGE) : 0;
    clearInterval(scrollTimer);
    if (!delta) return;
    scrollTimer = setInterval(() => window.scrollBy(0, delta), 16);
  }
```

Called from `move()` with `event.clientY` — the *pointer*, not the probe: this is
about reaching the edge of the window with the mouse, not about where the drop
lands. `clearInterval(scrollTimer)` in `finish()`, unconditionally.

Scrolling changes every frozen box's viewport position. `freeze()` stores viewport
rects, so **after any scroll the cache is stale by the scroll delta.** Record
`window.scrollY` at freeze time and subtract the difference in `fbox`:

```javascript
function fbox(element) {
  const cached = frozen && frozen.get(element);
  if (!cached) return element.getBoundingClientRect();
  const drift = window.scrollY - frozenAtScrollY;
  return drift ? new DOMRect(cached.x, cached.y - drift, cached.width, cached.height)
               : cached;
}
```

The prototype scrolled an inner container and never hit this. It is the one place
this task genuinely goes beyond what was measured — verify it by autoscrolling to
the bottom of a long list mid-drag and confirming the row still lands where it is
drawn.

- [ ] **Step 2: The abandon ending**

Released outside the list, Escape, or `pointercancel`. `undoPreview()` puts the
block back where the drag found it — the existing function, unchanged.

`wrote` must be set before `finish`'s first `await`, exactly as today: it is the
only thing that can tell an abandoned gesture from a claimed one.

- [ ] **Step 3: The failure ending**

Every `callApi` returning `API_FAILED` inside the drop body calls `refresh()`.
Unchanged from today, and the reason is unchanged: a redraw is the only thing that
can be right once a write may have half-landed.

- [ ] **Step 4: The drop ending**

The whole existing drop body — `pair`, `sort`, `place`, the `ids` read off the
DOM, `set_in_progress_order`, `forgetFoldIfEmptied` — runs untouched. It reads the
DOM *after* the preview, which is why nothing about it changes: the preview is
still a real `insertBefore`, so `section.querySelectorAll('.task')` and
`inProgressOrderFromDom` still report the order the user is looking at, and
invariant 18's reliance on folded rows being present still holds.

- [ ] **Step 5: `node --check` and the suite**

Expected: silent, then `384 passed`.

- [ ] **Step 6: Commit**

Message: `feat: the drag scrolls at the window edge, and every ending is handled`

**HAND-OFF:** Release on the header, on the Spin up button, and past the window
edge: the row snaps home each time and nothing is written. Same drag cancelled
with Escape: same. Both again in IN PROGRESS. Then confirm the snap-back is not
overzealous: reorder a bucket properly and the row **stays**, with no flicker back
to its old slot. Make a list long enough to scroll, then drag a row to the bottom
edge of the window: it must scroll, and the row must land where it is drawn.
Finally re-run every one of the ~41 existing by-hand drag checks in CLAUDE.md —
in particular that dragging into IN PROGRESS opens no Claude window, that
reordering IN PROGRESS produces **no git diff at all**, that a group header drag
gives every member a frontmatter-only diff, and that a task dropped into the
middle of a bucket is still there after a fold forces a re-render.

---

# Phase 2 — the motion

---

### Task 6: FLIP the neighbours

**Files:**
- Modify: `ui/drag.js`

**Interfaces:**
- Produces: `flip(mutate, exclude)`; `rect(element)` — the rest-rect accessor.

- [ ] **Step 1: Add `flip`, verbatim from the prototype**

```javascript
  const DISPLACE_MS = 200;
  const DISPLACE_EASE = 'cubic-bezier(.2, .9, .2, 1)';

  function flip(mutate, exclude) {
    const list = document.getElementById('task-list');
    const before = new Map([...list.querySelectorAll('.task, .group')]
      .map(element => [element, element.getBoundingClientRect()]));
    mutate();

    // Cancel every in-flight FLIP BEFORE measuring. A rect read while a
    // transform is running is a position nothing is at.
    const settled = [...list.querySelectorAll('.task, .group')];
    for (const element of settled) element.getAnimations().forEach(a => a.cancel());
    for (const element of settled) element.__rest = element.getBoundingClientRect();

    const animated = [];
    for (const element of settled) {
      if (element === exclude || (exclude && exclude.contains(element))) continue;
      // Never nest transforms: a .group and its member .task both animating
      // compound, and the member ends up somewhere neither intended.
      if (animated.some(done => done.contains(element))) continue;
      const was = before.get(element);
      if (!was) continue;
      const dx = was.left - element.__rest.left, dy = was.top - element.__rest.top;
      if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
      element.animate([{ transform: `translate(${dx}px,${dy}px)` },
                       { transform: 'none' }],
                      { duration: DISPLACE_MS, easing: DISPLACE_EASE });
      animated.push(element);
    }
  }
```

`before` is read *with* in-flight transforms included, which is what makes a
mid-drag direction change reverse the motion from where it actually is rather than
finishing the old one first.

- [ ] **Step 2: Wrap the preview's `insertBefore` in it**

In `move()`, the existing guarded `insertBefore` becomes the `mutate` callback,
with the dragged element as `exclude`. The guard stays: `dragover`/`pointermove`
fires continuously and an `insertBefore` that changes nothing still invalidates
layout for every rect read on the next one.

- [ ] **Step 3: Wrap `undoPreview` in it too**

The abandon ending must slide the row home, not jump it.

- [ ] **Step 4: `node --check` and the suite**

Expected: silent, then `384 passed`.

- [ ] **Step 5: Commit**

Message: `feat: the rows a drag displaces slide out of its way`

**HAND-OFF:** Drag slowly down a bucket that contains a group: rows must slide
apart rather than jump, and the row must step into the group's rail while inside
its box and back out below it. Reverse direction mid-drag: the displaced rows must
reverse from where they are, not finish first and then come back. Hold still on a
seam: no flicker. Escape mid-drag: the row slides home rather than jumping.

---

### Task 7: The settle and the flash

**Files:**
- Modify: `ui/drag.js` (`finish`)

- [ ] **Step 1: Fly the card to its slot**

```javascript
  const SETTLE_MS = 160;
  // Measured with the lift transform OFF: the keyframes end at scale(1), so the
  // translate applies to the UNSCALED box, and reading the scaled rect instead
  // lands the card short by however much the lift grew it.
  const lift = held.style.transform;
  held.style.transition = 'none';
  held.style.transform = 'none';
  const rest = held.getBoundingClientRect();
  held.style.transform = lift;
  const target = rect(element);
  const dx = target.left - rest.left, dy = target.top - rest.top;
  const flight = held.animate(
    [{ transform: lift },
     { transform: `translate(${dx}px,${dy}px) scale(1)` }],
    { duration: SETTLE_MS, easing: DISPLACE_EASE, fill: 'forwards' });
```

`transform`, never `left`/`top`: layout properties cannot be composited, so the
flight would run on the main thread next to a composited FLIP.

- [ ] **Step 2: Close the gap AFTER the flight, never during it**

`flight.onfinish` removes the card and clears `.dragging-source`. Sequential, per
Reardon — both at once is what jitters. Add a
`setTimeout(..., SETTLE_MS + 120)` fallback that does the same cleanup if
`onfinish` is eaten by a cancelled animation: a dropped animation must never
strand the gap.

- [ ] **Step 3: Flash the row that moved**

```javascript
  const FLASH_MS = 700;
  element.animate([{ backgroundColor: 'rgba(48, 164, 108, .34)' },
                   { backgroundColor: 'rgba(48, 164, 108, 0)' }],
                  { duration: FLASH_MS, easing: 'cubic-bezier(.25, .1, .25, 1)' });
```

`backgroundColor`, not the `background` shorthand. It outranks `.task:hover` for
its 700ms, which is correct — the flash is the news, not the hover. Only on a real
drop, never on abandon: nothing moved.

- [ ] **Step 4: `node --check` and the suite**

Expected: silent, then `384 passed`.

- [ ] **Step 5: Commit**

Message: `feat: the card flies to its slot, then the gap closes, then it flashes`

**HAND-OFF:** Drop a row and watch the order: the card flies to its slot, *then*
the gap closes, *then* the row lights up once. Not simultaneously. Drop and
immediately start a second drag inside the settle: the second card must be the row
you just grabbed, not the previous one. Drop a row that does not move at all: it
must still settle cleanly rather than leaving a card behind.

---

### Task 8: FLIP across `render()`

**Files:**
- Modify: `ui/state.js` (`render`)
- Modify: `ui/drag.js` (export the keyed FLIP)

**Interfaces:**
- Produces: `flipRender(mutate)` — wraps a whole re-render, matching elements
  across `replaceChildren` by key.

- [ ] **Step 1: Key every block**

`replaceChildren` destroys the old elements, so FLIP cannot use identity. Read
keys off the dataset attributes that already exist:

- `.task` → `${dataset.project}:${dataset.id}`
- `.group` → `${dataset.project}:g:${dataset.group}`
- `.project-block` → `${dataset.project}:p`

The `:g:` and `:p` discriminators matter: a group named `7` in project `x` and
task 7 in project `x` would otherwise collide on `x:7`.

- [ ] **Step 2: Wrap `render()`**

Capture keyed rects before the mutate, match after, animate the moves. Skip an
element whose ancestor is also animating, exactly as `flip` does. **Only moves
animate** — a block that appears or disappears cuts. Task 9 adds those.

- [ ] **Step 3: Do not let it fight the drop's settle**

`finish()` calls `refresh()` → `render()`. The dragged row is in its final slot
already, so its keyed delta is zero and it will not animate — but assert it: pass
the settling element as an exclusion, the same way `flip` takes one.

- [ ] **Step 4: `node --check` and the suite**

Expected: silent, then `384 passed`.

- [ ] **Step 5: Commit**

Message: `feat: every render animates what moved, not only a drag`

**HAND-OFF:** Change a row's bucket with its `<select>`: it slides to the new
section. Fold and unfold a group: the rows below slide. Complete a task from a
group of two: the block's disappearance still cuts (Task 9), but everything below
it slides up. Restore a task from Progress: the rows below it slide down. Drop a
row and confirm there is no double-animation — one settle, not a settle plus a
re-render.

---

# Phase 3 — enter and exit

Last on purpose: the only part that can be dropped without touching anything
above it.

---

### Task 9: A completed row collapses out; a restored one fades in

**Files:**
- Modify: `ui/drag.js` (the keyed FLIP)
- Modify: `ui/style.css`

- [ ] **Step 1: Exit**

A removed element is gone from the new DOM, so animating it out needs a copy.
Clone it into `#drag-layer` at its old viewport rect, then animate `opacity` to 0
and `height` to 0 over 160ms and remove it. `#drag-layer` already has
`pointer-events: none`, so the corpse cannot be clicked.

- [ ] **Step 2: Enter**

A key present after but not before animates `opacity` 0 → 1 and
`translateY(-4px)` → 0 over 160ms. No height animation: the row already occupies
its space, and animating height would move everything below it a second time,
against the FLIP that is already moving them.

- [ ] **Step 3: `node --check` and the suite**

Expected: silent, then `384 passed`.

- [ ] **Step 4: Commit**

Message: `feat: rows fade in and collapse out instead of appearing and vanishing`

**HAND-OFF:** Press `done` on a row: it collapses out and the rows below slide up
in one gesture, not two. Restore from Progress: it fades in at the bottom of its
bucket. Delete two rows from the selection bar: both collapse. Complete a whole
group from its header: the block goes as one, not row by row.

---

### Task 10: Fold the new by-hand checks into `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

The existing drag list is where these belong — beside the ~41 already there, not
in a new section. Add the HAND-OFF blocks from Tasks 3 through 9, and record
under "Adding a feature" the two things this work learned that are not invariants:

- **A rect read while something is animating is a position nothing is at.** Cancel
  in-flight animations before measuring, or read the cached rest rect.
- **A `fill: 'forwards'` WAAPI animation outranks the inline style for the
  property it animates, for as long as it exists.** Use a CSS transition when the
  inline style must stay authoritative.

Also record the decision and its cost: drag has no automated behavioural coverage
by choice (2026-07-26), the prototype at
`docs/superpowers/prototypes/2026-07-26-drag-feel.html` is the reversal path, and
the three convention tests that *do* guard part of this are named in the spec.

- [ ] **Step 1: Write it, run the suite, commit**

Expected: `384 passed`. Message: `docs: what to check by hand after touching the drag`

---

## Self-Review

**Spec coverage.** Every section maps to a task: engine → 3; the five things on
screen → 3 (card, gap), 6 (neighbours), 3 (boxes, unchanged); Reardon's rule → 4;
the endings → 5, 7; FLIP across render → 8; constants → 3–7; `PAIR_INSET` →
4 Step 5; autoscroll → 5 Step 1; the drag layer and the ladder → 2; the zoom
divisor → 3 Step 4; `draggable` → `.nodrag` → 3 Step 1; invariants 27/28/29 → 4
Step 7; the file split → 1; verification → every HAND-OFF block plus 10.

**Two gaps found and closed while reviewing:** the frozen cache goes stale under
autoscroll — the prototype scrolled an inner container and never hit it, so Task 5
Step 1 now carries the scroll-delta correction and flags it as the one piece not
covered by a measurement. And `.project-block` was missing from `freeze()`'s
selector list, which would have left IN PROGRESS's per-project wrappers measuring
live while everything else was frozen.

**One spec item deliberately not planned:** a group taller than the window. The
spec flags it as an open edge case with a recommended shape; it is not a task
because nothing yet says it bites.

**Type consistency.** `fbox` and `rect` are two different accessors and both
survive on purpose — `fbox` is the frozen box for *deciding* a drop, `rect` is the
rest box for *animating*. Named differently in every task. `slotFor` keeps its
name and gains a fourth parameter; `dropIntent` keeps its name and its first
parameter changes from `event` to `probe`.

---

## Execution Handoff

Plan complete. Two execution options:

**1. Subagent-Driven (recommended)** — a fresh subagent per task, review between
tasks, fast iteration.

**2. Inline Execution** — tasks executed in this session with checkpoints.

One caveat specific to this plan: Tasks 3 through 7 each end in a HAND-OFF that
only the user can perform, and Task 4's is the one the whole feature is for. A
subagent cannot close its own task. Whichever path is chosen, the HAND-OFF goes
to the user **as that task lands**.
