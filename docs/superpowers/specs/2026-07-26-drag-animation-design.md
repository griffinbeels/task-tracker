# Drag animation — design

**Status:** approved 2026-07-26, feel validated against a working prototype.

Dragging a task works and reads as robotic. Two separate faults, and only one of
them is animation:

1. **There is no card in your hand.** The native HTML5 drag API paints a
   translucent OS bitmap at the cursor while the real row stays in the list at
   full opacity. There are two of it on screen and neither is the thing you are
   moving.
2. **Everything snaps.** Neighbours jump between positions with no motion, and
   the drop's `refresh()` cuts the whole list to its new state.

A third fault surfaced while prototyping, and it is the one that made the
gesture feel *wrong* rather than merely unanimated: **the drop is aimed with the
mouse pointer and decided against thresholds that move while you cross them.**
Fixing 1 and 2 without fixing 3 produces a smooth gesture that still lands
somewhere you did not aim.

---

## Prior Art

**Canonical name(s):** sortable list · drag-and-drop reorder · FLIP animation ·
drag preview / drag overlay · placeholder vs. drop indicator · pointer-events
DnD vs. native HTML5 DnD.

**Landscape.** Every distinct approach the sweep surfaced, kept whole so any of
them can be resurrected:

| Approach | Mechanic | Real example |
|---|---|---|
| **Native HTML5 DnD** | `draggable="true"`, OS paints a bitmap snapshot of the element at the cursor | what this app does today |
| **Native DnD + custom preview** | `setCustomNativeDragPreview` renders a real DOM node into the drag bitmap | Atlassian Pragmatic drag and drop (2024) |
| **Native DnD, ghost suppressed** | transparent 1×1 `setDragImage`, then position the real element from `dragover` coords | common pre-2020 workaround |
| **Pointer-events clone** | a styleable clone follows the pointer; the original becomes the gap | SortableJS `forceFallback`, iOS home-screen lift |
| **Pointer-events, transform siblings** | nothing reorders; the item and its neighbours get transforms, order commits on drop | dnd-kit `verticalListSortingStrategy` |
| **Out-of-flow + placeholder** | item removed from flow, a placeholder holds the space, others shift by transform | react-beautiful-dnd / @hello-pangea/dnd |
| **Drop indicator line** | no gap at all; a 2px line with a terminal shows where it will land | Notion, VS Code explorer, Atlassian's current guidance |
| **Container background wash** | dropping *into* something is a background change, not a line | Atlassian, for multi-target droppables |
| **Gap-opening** | the list physically opens where the item will land | Trello, iOS, this app's `.drop-zone` today |

**Dominant pattern(s).** For a *vertical list with nested containers*: a
pointer-events drag, a styleable element under the cursor, the source position
reserved as a gap, and neighbours displaced by transform with an interruptible
transition. Native DnD survives only where the platform integration is the point
(file drops, cross-window) — neither applies here.

**The motion rules, and they are unanimous across all three fetched sources:**

- **The held item follows the pointer 1:1 with no easing.** Easing the held
  item's position *is* the disconnect. It is the one thing that must not animate.
- Everything else animates. Neighbour displacement ~200ms; container background
  350ms `cubic-bezier(0.15, 1.0, 0.3, 1.0)`; a flash on the moved item 700ms
  `cubic-bezier(0.25, 0.1, 0.25, 1.0)`; drop snap ~100ms.
- **Sequential, never simultaneous.** The item flies to its slot *first*, and
  only then does the placeholder collapse. Both at once is what jitters.
- **CSS transitions, not CSS animations** — transitions are interruptible, so
  reversing direction mid-drag reverses the motion from where it actually is.
- **Dimensions must be captured at rest.** A rect read mid-animation is a
  position nothing is at.
- Reshuffling triggers on the **centre** of the dragged item crossing a target
  **edge**, not on first contact.
- Lift = elevation via shadow and a small scale. Atlassian: **do not rotate.**

**The rule this design is built on**, quoted from Reardon:

> A list is dragged over when the centre position of a dragging item goes over
> one of the boundaries of the list. A resting drag item will move out of the way
> of a dragging item when the centre position of the dragging item goes over the
> edge of the resting item. Put another way: once the centre position of an item
> (A) goes over the edge of another item (B), B moves out of the way.

**Verdict on our starting idea.** "Animate between positions" was necessary and
insufficient. The measured defect was in the *rule*, not the motion — see
Measurements below.

**Known gotchas practitioners report**, all three of which were reproduced in
the prototype:

- FLIP fired on every pointer event restarts animations continuously. Only
  animate when the slot index actually changes.
- A rect read while a FLIP is running poisons the next slot decision.
- The "flip-flop": moving the dragged element under the cursor changes what the
  cursor is over. (This app already documents it as invariant 27.)

**Sources actually fetched and read:**
[Beautiful interactions — Alex Reardon](https://medium.com/@alexandereardon/beautiful-interactions-8f67502ccf73) ·
[Atlassian Pragmatic drag and drop — design guidelines](https://atlassian.design/components/pragmatic-drag-and-drop/design-guidelines) ·
[Smart Interface Design Patterns — Drag-and-Drop UX](https://smart-interface-design-patterns.com/articles/drag-and-drop-ux/).
dnd-kit's transform-siblings model is from a search summary plus internal
knowledge, **not** a fetched page — treat it as landscape, not as citation.

**Divergences, and why.** We keep a real DOM `insertBefore` for the preview
rather than dnd-kit's transform-only model. The app drags across four sections,
N per-project wrappers and M group containers, and `insertBefore` already
resolves every one of those cases correctly under invariants 16, 18, 26, 27 and
28. Computing cross-container sibling transforms analytically would re-derive all
of it. We take Reardon's *rule* without his *mechanism*, which is possible
because the rule only needs frozen geometry — see below.

---

## Measurements

Taken against a working prototype driven by synthetic pointer events, not
reasoned about. The prototype lives at
`.superpowers/brainstorm/862-1785127584/content/drag-feel-v3.html`.

**Today's rule reorders a row before you have moved it downwards at all.** Grab
a row 2px above its own bottom edge — an ordinary way to pick one up — and move
6px *sideways*, zero pixels down:

```
aim = centre    stayed at index 0
aim = cursor    REORDERED on the first move
```

The cause: the pointer starts *below the row's own midpoint* when you grab low,
so `slotByCursor`'s threshold is already crossed. **Where you grab a row decides
whether it reorders instantly.** No amount of animation tuning addresses this.

**Reardon's rule lands on the edge to 0.3px.** Stepping the pointer 1px at a
time until the order changed: card centre 557.8 against the next row's frozen
top at 557.6.

**Frozen thresholds cannot oscillate.** 24 crossings at ±0.5px around the
trigger: every reading below it was index 0, every reading above it was index 1,
no drift.

**The held card tracks the pointer with 0.00px of drift** across four positions.

---

## The design

### The engine

Native HTML5 DnD is removed. `pointerdown` on `#task-list`; `pointermove`,
`pointerup` and `pointercancel` on `window`.

`window`, not `setPointerCapture`: a drag that leaves the list must keep
tracking and a release out there must still end it, and capture throws when the
pointer id is not active — which also makes it impossible to drive with a
synthetic event.

A drag starts only after the pointer has moved **4px**. Below that the gesture
is a click, which is what preserves click-to-open-the-editor and
double-click-to-rename. A `pointerdown` whose target `closest('input, select,
button')` matches starts nothing — which **replaces `releaseDragWhileUsing`
entirely**, along with both rename functions' `draggable = false` dances. Those
existed only to work around Chromium refusing to let you select text or open a
`<select>` inside `draggable="true"`.

### The five things on screen during a drag

1. **The card** — a `cloneNode(true)` of the dragged element, `position: fixed`,
   `pointer-events: none`, fully opaque, `scale(1.05)`, no rotation, in a new
   `#drag-layer`. It is **rail-locked**: it tracks the pointer vertically and
   never moves sideways, so it stays exactly over the column it came from and
   reads as the row itself lifted out of the list. Position is set through
   `left`/`top` with **no transition on either**; only `transform` transitions.
2. **The gap** — the original element, still in the flow. Its box is therefore
   exactly the right size by construction, with no placeholder to keep in sync.
   It is painted as a dashed outline with its contents `visibility: hidden`.
3. **The neighbours** — displaced by a real `insertBefore` and animated with
   FLIP over **200ms** `cubic-bezier(.2, .9, .2, 1)`.
4. **The container box** — `.drop-zone` on a section, `.drop-into` on a group.
   Invariant 28's rule is unchanged: exactly one box, drawn only for a container
   being *entered*.
5. **The pair outline** — `.drop-into` on the row a new group would form with.
   Unchanged.

### Reardon's rule, as arithmetic

Two changes to how a drop is decided.

**The probe is the card's centre**, not the pointer. Where you grabbed the row
stops mattering, and the list responds to the thing you can see.

**Every box is measured once, at lift, and never again** (`freeze()`). This is
not an optimisation — the edge rule is *unstable* without it. Reordering live
moves the very edge that decided the reorder, so the forward and reverse
triggers land on the same pixel and the row flickers between two slots under a
still cursor. Frozen, each block has exactly one threshold for the whole
gesture.

Freezing buys two more things:

- **The thing you are aiming at stops moving.** Today a row leaving NOW shortens
  NOW and lifts NEXT and SOMEDAY up underneath the cursor mid-gesture.
- **No rect can be read mid-animation**, which is the gotcha above.

The slot is then a count, and `slotFor`'s `displaced` compensation disappears:

```
slot = the number of blocks whose threshold the card's centre has passed
```

| The block | Its threshold |
|---|---|
| in the list the drag started in, and originally **below** the dragged block | its **top** edge |
| in that list, originally **above** | its **bottom** edge |
| in any **other** list | its **centre** |

The first two produce the dead zone for free: both are exactly half a
card-height from where you started, so the row never twitches out of its own
slot. The third is not an inconsistency — a foreign list has no gap and no
before/after, and an edge rule cannot express "index 0" there, because the first
block's top edge *is* the top of the list and so reads as already passed the
moment you arrive.

Because the probe is the frozen dragged block's own position, the candidate list
must be **sorted by frozen order**, not by live DOM order — the preview has
already permuted the live children, which would make the index mean something
different every frame.

### The endings

A drag has exactly three, and every one of them must leave the screen showing
something that was written.

- **Drop.** The card flies from the pointer to its slot over **160ms**
  (`transform: translate(...)`, never `left`/`top` — layout properties cannot be
  composited). *Then* the gap stops being a gap. *Then* the row flashes for
  **700ms**. Sequential, per Reardon.

  The flight is measured with the lift transform switched **off**: its keyframes
  end at `scale(1)`, so the translate applies to the unscaled box, and reading
  the scaled rect instead lands the card short by however much the lift grew it.
  Measured in the prototype.

  The lift is a **CSS transition**, not `element.animate(..., {fill: 'forwards'})`
  — a forwards-filling WAAPI animation outranks the inline style for the property
  it animates, for as long as it exists, so the settle's own probe would read the
  lift's scale back even after clearing the transform. One `transition`
  declaration on the card, naming `transform` only.

  The flash animates **`backgroundColor`**, not the `background` shorthand. It
  will outrank `.task:hover` for its 700ms, which is correct — the flash is the
  news, not the hover.
- **Abandon** — released outside the list, Escape, or `pointercancel`. The
  preview is undone with a FLIP so the row slides home rather than jumping, and
  the card flies back to where it was picked up.
- **Failure** — any `callApi` returning `API_FAILED`. `refresh()`, unchanged:
  a redraw is the only thing that can be right once a write may have
  half-landed.

**A settle in progress is flushed when a new drag starts**, per Reardon's own
guidance ("animations must be flushed, accepting minor snapping, to preserve
interactivity"). Unflushed, the previous card is still in the DOM holding its
gap, and the new drag's `.held` lookup resolves to the wrong element — measured.

### FLIP across `render()`

One wrapper around `render()`, so the drop's `refresh()`, the bucket picker,
folding, completing and restoring all animate through one mechanism rather than
the drag having a private one.

Rects are captured before `replaceChildren` and matched after by key —
`project:id` for a `.task`, `project:group` for a `.group`, `project` for a
`.project-block`. **Only moves animate in Phase 1 and 2**; a block that appears
or disappears cuts. Phase 3 adds enter and exit.

Nesting is the trap: a `.group` and its member `.task` both animating compound
their transforms. An element whose ancestor is already animating is skipped.

### Constants

| Name | Value | Why |
|---|---|---|
| `DRAG_THRESHOLD` | 4px | below it the gesture is a click |
| `LIFT_SCALE` | 1.05 | chosen against the prototype |
| `LIFT_MS` | 130 | |
| `DISPLACE_MS` | 200 | Reardon/Atlassian range, chosen against the prototype |
| `DISPLACE_EASE` | ~~`cubic-bezier(.2, .9, .2, 1)`~~ → **`cubic-bezier(.4, 0, .2, 1)`** | **changed during implementation.** The first curve is **35% travelled by the first painted frame** — a 10px hop on a 30px row, reported as *"it glitches upwards, it should just start moving"*. `y1 = 0` is zero initial velocity |
| `SETTLE_MS` | 160 | |
| `FLASH_MS` | 700 | Atlassian's published value |
| `FLASH_EASE` | `cubic-bezier(.25, .1, .25, 1)` | Atlassian's published value |
| `AUTOSCROLL_EDGE` | 46px | |
| `AUTOSCROLL_MAX` | 12px/frame | ramped by proximity to the edge |
| `PAIR_BAND` | ~~1/3~~ → **1/4** | **changed during implementation** — see below |
| ~~`GROUP_STICKY`~~ | **removed** | **changed during implementation** — see below |
| ~~`PAIR_INSET`~~ | **removed** | see below |

**Three rows above changed after this spec was written, and the reason is one
measurement.** Leaving a group and reordering past the next row were separated by
**four pixels**: `GROUP_STICKY`'s 8px sat exactly on top of the next row's 10px
reorder zone. Reported as *"very difficult to drag an element OUT OF A GROUP…
more likely to fall back into its original group or auto-combine with another
task"* (2026-07-27). The sticky is deleted — the freeze had already made it
redundant, since the card's centre must travel from the last member's top edge to
the block's real bottom before it is outside at all — and `PAIR_BAND` went to a
quarter, which makes a row 75/25 reorder-to-pair and the window 13.3px.

A fourth change was tried and **rejected by arithmetic**: measuring a group as it
will be once the member has left (its own height off the bottom) cut a middle
member's escape from 53px to 15px, but for the **last** member of any group
`bottom − ownHeight` lands above that member's own centre, so the card starts
outside its own group and the row leaves on the first pixel of movement.

A fifth thing this spec did not anticipate: **the last member leaving deletes the
group, and the preview did not say so.** `.group.emptying` fades the container
while the position you are in is the one that ends it — the same "draw the
consequence" rule as the drop boxes, applied to the one consequence that is a
deletion. Invariant 28 is the current record for all of this.

---

## Consequences that are not obvious

### `PAIR_INSET` becomes dead, and is removed

With the card rail-locked, its centre's **x never changes for the whole drag**.
Every horizontal test — `PAIR_INSET`, and `withinBox`'s x bounds against
full-width sections and groups — therefore always passes. The geometry becomes
purely vertical.

The alternative is to keep using the *pointer's* x for the pair inset alone,
and that is exactly the disconnect this work removes: a decision made by
something the card does not show. So `PAIR_INSET` goes, and pairing is aimed by
`PAIR_BAND` alone — the middle third of a row's height. **Invariant 28's
"inset from both ends" clause must be rewritten**, not quietly left in place.

### Autoscroll has to be built

Native DnD scrolls near the container edge for free; pointer events do not. The
app has no inner scroll container — `body` has the padding and the document
scrolls — so this is `window.scrollBy` when the pointer is within
`AUTOSCROLL_EDGE` of the viewport's top or bottom, ramped by proximity.

### The drag layer is a zoom region, and the card needs a scale divisor

`ui/zoom.js` applies CSS `zoom` to `#task-list` itself, so a card outside it
would not scale with the list it came from and would be visibly the wrong size
against its own gap. `#drag-layer` is therefore a new top-level element with a
line in `zoomAssignments()` — which is how that file's own comment says an
element joins a region.

It must be *outside* `#task-list` rather than inside it, because the drop path
reads `section.querySelectorAll('.task')` and `flip()` sweeps `.task, .group`; a
clone inside the list would be counted by both.

### The card needs a rung on the stacking ladder, and there is no room for it

`ui/style.css` now carries an explicit ladder — task list at `auto`,
`#selection-bar: 1`, `.overlay: 2`, `#editor: 3`, `#zoom-badge: 4` — and
`tests/test_conventions.py::test_the_floating_surfaces_are_ranked_in_one_order`
asserts those ranks are **strictly increasing**, with equal ranks rejected
because "equal ranks fall back to DOM order".

The card must beat the selection bar (you can drag over it) and lose to every
overlay. There is no integer between 1 and 2, and a tie is exactly what that test
forbids. So the ladder shifts up by one:

| Surface | Was | Becomes |
|---|---|---|
| `#selection-bar` | 1 | 1 |
| **`#drag-layer`** | — | **2** |
| `.overlay` | 2 | 3 |
| `#editor` | 3 | 4 |
| `#zoom-badge` | 4 | 5 |

`STACKING_ORDER` in the test gains `#drag-layer` between `#selection-bar` and
`.overlay`. Do **not** give the card its rank by placing it late in the markup —
that file's own comment says a new surface "needs a rank, not a place in the
markup", and the test is there because the markup answer was tried and failed.

`#zoom-badge`'s `pointer-events: none` is documented as load-bearing because "the
drop handler asks `event.target` what it landed on". That stops being true: the
only `event.target` read left is on `pointerdown`, and `pointermove` measures
rather than hit-tests. Leave the declaration — it is still correct, and the badge
must not eat a `pointerdown` — but the comment's reasoning needs updating so it
does not outlive the thing it describes.

A `position: fixed` child of a zoomed element does not resolve `left`/`top`
against the viewport. **Do not reason about the factor — probe it**, once per
lift, and assert the result:

```
left: 0px    → measure viewport x  → origin
left: 100px  → measure viewport x  → scale = (x - origin) / 100
to place the card's visual left at V:  left = (V - origin) / scale
```

The probe yields the offset and the factor together, and it cannot be wrong
about the engine. Verify `scale` equals `zoomFactor('app')` at 100% and 200%; if
it does not, the probe is right and this paragraph is wrong.

### A group taller than the window — open edge case

`groupTransit = full`: a dragged group carries every row. A five-member group at
1.05× is a tall card, and a large enough group exceeds the window height.
Atlassian's guidance is to collapse a large item into a summary; the prototype
offered that and it was rejected in favour of the whole block, which reads as
more physical.

**Not solved here, deliberately.** If it bites, the shape is a `max-height` on
the card with the overflow faded out — the block stays recognisable and the gap
stays full-size, so nothing about the drop changes. Flagged rather than built.

---

## Invariants this changes

- **27 (`wireDrag` binds once to `#task-list`)** — still true, but the events
  change: `pointerdown` on the list, the rest on `window`. The clause about
  `dropIntent` refusing a drop onto the dragged row itself, and about the live
  `insertBefore` sliding the row under the cursor, **no longer applies**: the
  probe is the card's centre in a frozen coordinate system, so what the preview
  does to the DOM cannot feed back into the decision. That whole failure mode is
  gone rather than guarded.
- **28 (geometry, not hit-testing)** — the principle survives and gets stronger:
  it is now measured *once*, so the rectangles cannot move under the gesture. The
  probe point changes from the pointer to the card's centre; the thresholds change
  from midpoints to edges; `PAIR_INSET` is removed; `slotFor`'s `displaced`
  compensation is removed. **`sectionUnder`'s "the margin between two sections
  belongs to the one below" rule is unchanged** and must stay — it is about which
  box owns a strip, not about when a block yields.
- **29 (zoom)** — unchanged in substance, with one addition: a `position: fixed`
  element inside a zoomed region needs the probed divisor above. The existing
  note that `getBoundingClientRect()` and `event.clientX/Y` share one post-zoom
  space is what still makes the geometry need no change.
- **New invariant** — *nothing on screen may claim a place that was not written,
  and no rect may be read while something is animating.* The first half exists
  already inside invariant 27; the second half is new and is what the frozen
  cache enforces.

### `draggable` is gone, so "this view cannot drag" needs a new flag

The `draggable` attribute is removed everywhere — keeping it would leave native
DnD live alongside the new gesture. But three places rely on it today as a
*permission*, not as plumbing, and dropping it silently would re-enable dragging
where it is deliberately off:

- `renderSearch` and `renderAllProjects` set `row.draggable = false`, because a
  row there can belong to any project and the view gives no grouping to drop
  into.
- `taskRow`'s `draggable` option and `groupBlock`'s `draggable` /
  `headerDraggable` options thread the same permission down.

Replaced by a class — `.task.nodrag`, `.group-header.nodrag` — that
`pointerdown` checks before setting `press`. **`cursor: grab` moves onto the same
condition**, which also fixes a pre-existing wrongness: search rows advertise a
grab cursor today for a gesture that has never worked there.

`.group-header[draggable="false"] { cursor: default }` becomes dead and is
removed with it.

## Files

Measured against `main` at `c635b17` (2026-07-26, after the Claude-button work
landed): `ui/groups.js` is **951 lines**, its drag section runs 371–941, and
`focusGroupName` follows at 943. So **571 lines** move before a single line of the
frozen cache, the card, FLIP or autoscroll is written. One new file lands near
800, which is worse than what it replaces.

So the recommendation is **two** new files, each with one reason to change. This
is a refinement of the approved split, not a different decision — flagged here
because it is a deviation from what was agreed and is the kind of thing this
review gate exists for.

| File | Change |
|---|---|
| `ui/drag-geometry.js` | **new**, ~330 lines. Where a drop lands, and nothing about how it looks: `freeze`/`fbox`/`rect`, `sectionUnder`, `groupUnder`, `pairTarget`, `slotFor` and its two rules, `blocksIn`, `projectBlockUnder`, `ownRunningList`, `sectionPlacement`, `placement`, `draggedState`, `dropIntent`, `groupOf`, `taskOf` |
| `ui/drag.js` | **new**, ~370 lines. The gesture and its motion: `pointerdown`/`move`/`up`/`cancel`, the held card and its probe, the gap, `clearDropAffordance`, `flip`, autoscroll, the three endings, `inProgressOrderFromDom`, `wireDrag` |
| `ui/groups.js` | 951 → **~380 lines** (1–370 plus `focusGroupName`). Keeps what a group *is*: `groupBlocks`, `groupMemberCount`, the seven folding functions, `groupBlock`, `renameInPlace`, `focusGroupName` — and loses `releaseDragWhileUsing` along with all **eight** of its call sites |
| `ui/index.html` | two `<script>` tags after `groups.js`; `<div id="drag-layer">` after `<main id="task-list">` — its rank does the work, not its position |
| `ui/zoom.js` | one line in `zoomAssignments()`: `['drag-layer', 'app']` |
| `ui/style.css` | `.held`, the three gap styles, `#drag-layer`, `.nodrag`; the four-rung ladder shift; remove `.group-header[draggable="false"]`; update `#zoom-badge`'s comment |
| `ui/tasks.js` | 616 lines. `taskRow` loses `row.draggable` for `.nodrag`; `renameTaskInPlace` loses its `draggable` juggling; `renderSearch`/`renderAllProjects` set the class |
| `ui/state.js` | `render()` gains the FLIP wrapper |
| `tests/test_conventions.py` | one line: `#drag-layer` into `STACKING_ORDER` |

**Three existing convention tests are the only automated coverage this work
gets**, and all three are worth knowing about because each catches a mistake the
by-hand checks would miss:

- `test_every_ui_script_is_loaded_by_the_page` (line 329) — a `.js` file with no
  `<script>` tag. Exactly the mistake two new files invite.
- `test_every_class_the_ui_toggles_is_styled` (line 269) — `.held`, `.nodrag` and
  the three `gap-*` classes must actually be styled. Note its known blind spot,
  recorded in invariant 28: it passes on a *stale* selector, because `.drop-into`
  is a substring of `.group-header.drop-into`. Keep the new selector lists
  minimal enough that a wrong one is obvious by reading.
- `test_the_floating_surfaces_are_ranked_in_one_order` (line 416) — the ladder
  above, strictly increasing.

None of them can see whether the card follows the cursor, whether a threshold
moves, or whether a neighbour is animating.

**A new row control landed while this spec was being written.** Every `.task` now
carries a `.claude` button beside `.copy` and `.done`, and the group header
carries one too — which is why `releaseDragWhileUsing` has eight call sites rather
than six. Nothing in this design changes for it: the guard is
`closest('input, select, button')` on `pointerdown`, which covers every control
present today and every one added later. That generality is the point — the
per-control registration it replaces is what needed a line per button.

Nothing in `store.py`, `groups.py`, `app.py` or any bridge method changes. **The
drop path is untouched**: the preview is still a real DOM move, so
`section.querySelectorAll('.task')` and `inProgressOrderFromDom` still read the
order the user is looking at, and invariant 18's reliance on folded rows being
present in the DOM still holds.

## Verification

**Decided 2026-07-26: no automated coverage.** A headless-Chrome harness driving
the real `ui/*.js` with synthetic pointer events was offered and declined; drag
stays on by-hand checks, as it is today.

The cost is stated so it is not a surprise later. That harness found, in one
session: a card that never appeared, 672px of tracking drift, a slot decision
poisoned by a mid-flight rect, a stranded clone after a fast second drag, and a
false green in its own suite. **Every one was invisible in a diff**, and this
work adds a class of defect — wrong *during* the transition, correct at both ends
— that end-state review structurally cannot see. The prototype and its harness
are kept under `.superpowers/brainstorm/` so the decision is reversible without
rebuilding them.

The by-hand checks go into CLAUDE.md beside the existing drag list. Each is
written so it can only be answered by doing it:

**The card.** Grab a row anywhere and move: exactly **one** of it on screen, at
full opacity, under the cursor, with a dashed gap where it came from. Grab a row
2px above its own bottom edge and twitch 6px sideways: **nothing reorders.**
Grab the same row and move down slowly: it yields as the *card* reaches the next
row's edge, not before. Hold the cursor still on a threshold: the preview
settles on one slot and stays.

**The motion.** Drag out of NOW into SOMEDAY: NEXT and SOMEDAY must **not** move
under the cursor. Reverse direction mid-drag: the displaced rows reverse from
where they are, not after finishing. Drop: the card flies to its slot, *then*
the gap closes, *then* the row flashes once.

**The endings.** Release on the header, past the window edge, and with Escape:
the row snaps home each time and nothing is written. Drop properly: it stays,
with no flicker back. Drop and immediately start a second drag inside the
settle: the second card is the row you grabbed, not the previous one.

**The rest of the gesture, unchanged.** Every one of the ~41 existing by-hand
drag checks in CLAUDE.md still applies and must be re-run — in particular:
dragging into IN PROGRESS opens no Claude window; a group header carries every
member with a frontmatter-only diff; dropping on another project's heading in IN
PROGRESS is refused; a folded group keeps its member order; reordering IN
PROGRESS produces **no git diff at all**; and a task dropped into the middle of a
bucket is still there after a fold forces a re-render.

**Zoom.** Zoom the list to 200% and drag between buckets and into a group: the
card must be the same size as its gap, and land where it is drawn.

**Selection and rename, which the threshold decides.** Single-click a row: the
editor opens. Double-click a title: it renames. Double-click a group name: it
renames. Tick a checkbox and use the bucket `<select>`: neither starts a drag.
Select text in a rename box with the mouse: it selects rather than dragging.

## Deliberately not in scope

- **Keyboard reorder.** Named as a gap in CLAUDE.md already; a real feature with
  its own design, not a rider on this one.
- **Multi-row drag.** The selection bar exists and does not drag.
- **`prefers-reduced-motion`.** One line if ever wanted; nothing on this machine
  sets it.
- **Merging two groups by drag.** Still refused, unchanged.
- **Enter/exit animation** in Phase 1 and 2 — see Phase 3.

## Phasing

1. **The gesture.** Pointer events, the card, the gap, the frozen geometry and
   Reardon's rule, autoscroll, the three endings. `ui/drag.js` split out. No
   FLIP yet — the preview snaps, exactly as today, so this phase is provably
   about the *rule* and can be judged on its own.
2. **The motion.** FLIP on neighbour displacement, the settle, the flash, and
   the `render()` wrapper.
3. **Enter and exit.** A completed row collapses out; a restored row fades in.
   Last on purpose: it is the only part that can be dropped without touching
   anything above it.
