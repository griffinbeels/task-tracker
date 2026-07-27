---
paths:
  - "ui/*.js"
  - "ui/style.css"
  - "ui/index.html"
---

# UI surfaces — stacking, CSS, zoom, and animation

Invariant 29, the floating-surface ladder, and how to measure anything animated.

29. **Zoom is a table of which elements each region owns, and every element is
    assigned on every apply — in or out.** `zoomAssignments()` in `ui/zoom.js`
    is the whole definition of a region. An element the current settings put
    *outside* a region must have its `zoom` **cleared**, not merely skipped:
    skipping is why turning "scale the header too" back off would otherwise
    leave the header stranded at whatever it was last scaled to, looking like
    a setting that only works in one direction.

    Which region a key press hits is one question — is the editor open — the
    same rule Escape uses to pick an overlay. There is no mode.

    **CSS `zoom`, because it is the only mechanism that reflows.** A transform
    scales a box laid out for the old size; a font-size scale misses padding,
    borders and images. Three things about it were measured (2026-07-26) and
    none are knowable by reasoning:

    - A `position: fixed; inset: 0` overlay under `zoom` keeps its own
      viewport size while its contents scale — Chromium divides a zoomed
      element's containing block by the zoom. So the overlays need no wrapper,
      and the document never grows a horizontal scrollbar.

      The corollary bit later: **a fixed child of a zoomed element does not take
      `left`/`top` in viewport pixels.** `#drag-layer` is a zoom region on purpose
      — the card is a clone of a row and must be the size that row is now — so
      placing the card at a viewport coordinate needs the mapping. `begin` in
      `ui/drag.js` **probes** it rather than reasoning about it: write `0`, read
      the box, write `100`, read again. That yields the origin and the scale
      together, in two lines, and cannot be wrong about the engine. Reasoning
      about `zoom` has been wrong here before (invariant 25's whole second half),
      which is why the probe is the pattern and not the fallback.
    - `getBoundingClientRect()` returns **post-zoom** pixels, and
      `event.clientX/Y` are in that same space — which is the entire reason
      invariant 28's drag geometry needed no change. A future measurement that
      mixes a zoomed rect with an unzoomed length is the way to break it.
    - `getComputedStyle().fontSize` reports the **unzoomed** value. Anything
      wanting the effective size must measure a box, never ask for a length.

    The level is view state and lives in `session.json`; the header/toolbar
    toggle is a preference and lives on `Settings`. A level stored on
    `Settings` would be wiped by every settings save, exactly as
    `last_project` would have been (invariant 17's reasoning, one file over).

- **New UI surface:** put it in whichever of the seven scripts owns that concern;
  add its `<script>` tag only if you create a new file.
- **Never add a CDN reference.** The editor is vendored so the app works
  offline; a convention test enforces it.
- **A new floating surface needs a rank in the ladder, not a place in the
  markup.** `ui/style.css` ranks exactly five things and the order is the whole
  design: `#selection-bar` 1, `#drag-layer` 2, `.overlay` 3, `#editor` 4,
  `#zoom-badge` 5. The bar covers the task list, the card you are dragging
  covers the bar (you can drag across it), any overlay covers the card, the
  editor covers the other overlays (it opens on top of Progress), and the zoom
  readout covers everything because it reports on the editor's own size.

  **A new rung in the middle moves everything above it, and that is the correct
  outcome rather than a nuisance.** `#drag-layer` needed to sit between the bar
  and the overlays; there is no integer between 1 and 2, and
  `test_the_floating_surfaces_are_ranked_in_one_order` rejects equal ranks
  because a tie falls back to the DOM order this whole ladder exists to stop
  deciding. So the three above it each moved up by one. Renumbering is cheap and
  the test proves it landed; squeezing a surface in on a tie is what is not.

  **The trap is that DOM order stops deciding the moment anything makes a
  stacking context.** The bar carried no rank for months on the reasoning that
  it sits *before* the overlays in `index.html` and so loses to them in DOM
  order — true, and not the whole rule. Among elements that all resolve to
  `z-index: auto`, tree order breaks the tie, and `#task-list` comes **after**
  the bar. So anything in the list that makes a stacking context of its own
  paints on top of an opaque bar: `opacity` below 1 makes one, and 28 rules in
  that file set one — `h2` (the NOW/NEXT/SOMEDAY headings) at `.5`, `.bucket`
  at `.5` — as does `position: relative`, which `.group-header` and
  `.project-heading` both carry. Measured 2026-07-26 in a headless copy of the
  real page: a heading, a bucket select and a group header each owned their
  pixel over the bar, while a plain `.task` — which makes no stacking context —
  did not. **`zoom` is not part of it**: identical results at no zoom, 100% and
  120%, so `zoomAssignments()` is not implicated however much it looks like it.

  It reads as the bar being see-through and it is not — the fill is
  `rgb(30, 30, 30)` at `opacity: 1`, measured. Reaching for a stronger
  background is the fix that cannot work, because the text is painted *after*
  the fill. And because hit-testing follows painting, the same defect ate
  clicks: a `.bucket` select drifting under the bar answered a press aimed at
  Done. `test_the_floating_surfaces_are_ranked_in_one_order` fails the build on
  a missing rank or an out-of-order one. What it cannot catch: a new
  full-window overlay that carries neither the `.overlay` class nor a rank of
  its own — invisible under the bar, exactly like the editor-under-Progress bug
  that put `#editor`'s rank there in the first place.
- **Extend a CSS comment BEFORE its closing `*/`, never after.** Prose written
  after the marker is not a comment: CSS reads from there to the next `{` as
  one selector, fails to parse it, and **silently discards the entire rule that
  follows**. That deleted `section.drop-zone` on 2026-07-26 — the JS added the
  class, the rule sat in the file looking correct in the diff, and no bucket
  section ever drew its drop box. It happened twice the same day.
  `test_the_stylesheet_has_no_stray_comment_markers` now fails the build on an
  unbalanced marker in either direction.
- **Anything animated has to be measured MID-flight, and its curve judged at
  16ms.** Four separate lessons from the drag animation, each of which had
  correct code looking broken or broken code looking correct.

  **A rect read while a transform is running is a position nothing is at.**
  FLIP computes deltas from rects, so an in-flight neighbour makes the next
  delta phantom. `flipBlocks` cancels every in-flight animation *before* its
  second measurement for exactly this reason. The drag geometry is immune by a
  different route — it reads boxes frozen at lift (invariant 28) — and that is
  not a coincidence, it is the same problem solved once per concern.

  **An end-state read at t=0 sees the OLD state, and reads as the rule not
  applying.** `getComputedStyle(element).opacity` right after adding a class
  that fades it returns the value it is fading *from*, because a `transition`
  means the value travels. Cost a round accusing a working `.emptying` rule.
  Drive the animation (`animation.currentTime = …`, or `.finish()`) instead of
  sleeping and looking.

  **Judge a displacement curve at 16ms, not by watching it.** A curve chosen by
  eye is chosen from its middle, because the first painted frame is over before
  the eye reports anything. `cubic-bezier(.2,.9,.2,1)` felt firm in a prototype
  and was **35% travelled by the first frame** — a 10px hop on a 30px row, which
  is what got reported as the row glitching upwards instead of simply starting
  to move. `y1 = 0` is zero initial velocity; that is what "starts moving" means
  as a number.

  **A newly created WAAPI animation DOES apply its from-keyframe while pending,
  so it never paints one frame at its end position.** Measured on a standalone
  control and on the real FLIP: `pending === true`, `startTime === null`, and the
  computed transform is already the from-value. Recorded because it is a clean and
  wrong explanation for "it flashes the wrong way and then animates", and it cost
  a round (2026-07-27). `fill: 'backwards'` is not the fix for that symptom
  because there is nothing to fix.

  **A `fill: 'forwards'` WAAPI animation outranks the inline style for the
  property it animates, for as long as it exists.** So a later measurement that
  clears `transform` still reads the animation's value back. The drag card's lift
  is a CSS *transition* rather than `element.animate(…, {fill: 'forwards'})` so
  that there is one source of truth for `transform` — and the settle's own probe
  can therefore trust what it reads.

## The vendored editor

**`ui/vendor/` is committed, not fetched.** The UI is served from `file://` and
has to work with no network, so the editor is vendored rather than loaded from
a CDN. `tests/test_conventions.py` fails the build if the assets go missing or
if a CDN URL appears in `index.html`.

**It must be `toastui-editor-all.min.js`, never `toastui-editor.min.js`.** The
core build is not standalone: it declares all eight `prosemirror-*` modules as
*external*, and its UMD wrapper has no global names for them, so the browser
branch reads `e.toastui.Editor = t(e[void 0], e[void 0], …)` and hands the
editor `undefined` for every dependency. `window.toastui` still exists, so
nothing looks broken until `new toastui.Editor()` throws — and then Capture and
click-to-edit both silently do nothing, because both go through `openEditor`.
That shipped, and the size-and-not-a-404 convention test passed the whole time:
a file can be the right size, be genuinely downloaded, and still be the wrong
build. `-all` inlines the dependencies (`define([], t)`, factory called with no
arguments) and is the build the library's own script-tag documentation uses.
`test_the_vendored_editor_bundle_is_self_contained` now pins this.

The library's last release was February 2023 — it will not receive fixes, which
is a reason to keep it pinned and vendored rather than a reason to keep it
current.
