---
paths:
  - "ui/drag.js"
  - "ui/drag-geometry.js"
  - "ui/groups.js"
  - "ui/inprogress.js"
---

# The drag gesture — where a drop lands, and how it moves

Invariants 18, 27 and 28. The largest single body of hard-won detail here.

18. **A folded block keeps its rows in the DOM; CSS hides them.** Three things
    read the rendered list rather than `state`: select-the-group ticks
    `.select` inside the container, `selectedIds()` collects checked rows
    document-wide, and the drag's drop handler builds the `ordered_ids` it
    hands `place_task` from the destination section's own
    `querySelectorAll('.task')`. Drop the rows and that last one hands the
    backend a bucket with a hole in it, leaving the folded members on stale
    `order` values that collide with the renumbered ones.

27. **`wireDrag` binds once, at load, to `#task-list`.** It was one controller
    per section until 2026-07-26, each closing over its own `dragged`, and
    that is exactly why no drop ever crossed a section: `dragstart` fired on
    the SOURCE section's listener while the `dragover`/`drop` that followed
    fired on the DESTINATION section's, where `dragged` was still `null`.
    `event.preventDefault()` runs before that guard, so the browser showed a
    drop cursor the whole way and the gesture looked legal while doing nothing
    at all — a silent failure that survived months of use.

    `#task-list` is the common ancestor of every section and is never itself
    replaced (`render()` calls `replaceChildren` on it), so one listener there
    survives every redraw and cannot stack duplicates. Never call `wireDrag`
    from a render function. The destination section is resolved at event time
    from `event.target.closest('section[data-bucket], #in-progress')`, and a
    section with no `data-bucket` is IN PROGRESS: it implies `in-progress`
    status and cannot reorder, a bucket section implies `open` and can. That
    one substitution is the whole of claiming and releasing — neither is a
    special case anywhere in the handler.

    **The events are pointer events, and there is one ending.** `pointerdown` on
    `#task-list`; `pointermove`, `pointerup` and `pointercancel` on **`window`**,
    because a drag that leaves the list must keep tracking and a release out
    there must still end it. Not `setPointerCapture`, which does the same job,
    throws when the pointer id is not active, and cannot be driven by a
    synthetic event. `dragend` and `drop` collapsed into one `finish(cancelled)`,
    which is why the `wrote` flag is gone: it existed only to tell an abandoned
    gesture from a claimed one from inside `dragend`, and the caller now knows.

    **A drag ends in a `click`, and the native API swallowed it for us.** Pointer
    events do not: without a capture-phase suppressor on `window`, every drop also
    opens the editor — and not necessarily on the row you dragged, because the
    preview has moved things and the click lands on whatever is under the pointer.
    The flag clears on use *and* on the next `pointerdown`, since a `pointerup`
    outside the document produces no click at all and a flag left standing would
    eat the next real one.

    **`#drag-layer` holds a CLONE of the row, and six document-wide queries could
    not tell it from a row.** Checkboxes, `data-project`, `data-id` and — for a
    group — its whole container, all copied. `selectedIds()` counted a second
    ticked task, `restoreTicks` ticked a box nothing can ever clear, Clear
    reported having cleared it, and `focusGroupName` — which runs immediately
    after a pair drop — could open the rename box inside a clone about to be
    deleted. Every query for `.task`, `.group`, `.select` or `.select-group` is
    scoped to `#task-list`, and
    `test_the_selection_is_read_from_the_list_only` fails the build on the
    seventh. **"The rows on screen" stopped being a synonym for "the rows in the
    list" the moment a decoration layer existed**, and five of those six queries
    predate it.

    **The old "pointer landing on the row it is dragging" hazard is GONE, not
    guarded.** `dropIntent` used to refuse a drop whose target was the dragged
    row itself, while the live `insertBefore` slid that row under the cursor — so
    the next event resolved to it, `intent` went null, and releasing there wrote
    nothing while the row sat visibly in its new section. It cannot happen now:
    the probe is the card's centre against boxes frozen at lift (invariant 28), so
    nothing the preview does to the DOM can feed back into the decision. Kept here
    because a future gesture that reintroduces live re-measurement inherits the
    whole failure mode, and it reads exactly like a backend fault.

    **The preview is a lie until something writes it, so a gesture that writes
    nothing takes it back.** `dragover`'s `insertBefore` is a REAL DOM move, and
    for months nothing ever undid it: release outside `#task-list` — the header,
    the selection bar, past the window edge — or press Escape, and only
    `dragend` fires, which cleared the outline and left the row sitting in its
    new place. Same for a `drop` whose `intent` is null, and for one whose
    `callApi` failed. The list then showed a position nobody saved for as long
    as it took something else to force a render, and the next rename or edit put
    it back — which reads as *that* edit having reset the task's position, and
    is what this was reported as (2026-07-26). Measured before and after in a
    headless copy of the real renderer: pre-fix, a `dragstart` + `dragover` +
    `dragend` with no drop left `[2,3,1]` on screen with zero bridge calls.
    `wireDrag` now records where the block was picked up, `dragend` restores it
    unless `drop` claimed the gesture first (`wrote`), and every failure path
    inside `drop` calls `refresh()` — a redraw is the only thing that can be
    right once a write may have half-landed. **`wrote` must be set before
    `drop`'s first `await`**: `dragend` fires immediately after drop's
    synchronous part, and it is the only thing that can tell an abandoned drag
    from a claimed one. **And `inProgressOrderFromDom` must keep being read
    while the preview is still in place** — it runs after an await, so it
    depends on dragend having left the DOM alone.

28. **Where a drop lands is read from geometry, not from `event.target` — and the
    point it is read at is the CARD's centre, against boxes frozen at lift.**

    Both halves are Reardon's rule (*"once the centre position of an item A goes
    over the edge of another item B, B moves out of the way"*), and neither is
    the mouse pointer. `dropIntent` takes a `probe` — `{x, y}` — rather than an
    event, which is what makes it provable: nothing in `ui/drag-geometry.js`
    can reach for `event.clientY` and quietly aim one decision with the mouse
    while every other one uses the card
    (`test_the_drag_geometry_never_reads_the_pointer_directly`).

    **The pointer was the wrong point, measurably.** Grab a row two pixels above
    its own bottom edge — an ordinary way to pick one up — and the pointer starts
    *below that row's own midpoint*, so the old threshold was already crossed: a
    6px **sideways** twitch reordered it, having moved down not at all. Where you
    grabbed a row decided whether it reordered instantly, and that is what
    "robotic" turned out to mean. With the card's centre it yields exactly as the
    card reaches the next row's edge — measured at **0.0px** off, driven
    headlessly against the real scripts.

    **Freezing is not an optimisation; the edge rule is unstable without it.**
    Re-measuring live means claiming a slot moves the very edge that decided it,
    so the forward and reverse triggers land on the same pixel and the row
    flickers between two slots under a still cursor. Frozen, each block has
    exactly one threshold for the whole gesture: 20 crossings at ±0.5px never
    drift. It buys two more things that were separately wrong. **The thing you
    are aiming at stops moving** — a row leaving NOW shortens NOW and lifts NEXT
    and SOMEDAY up underneath the cursor, measured at 30px of movement mid-drag
    while the aim correctly held. And **no rect can be read mid-animation**,
    which a rect is when a FLIP is running: a position nothing is at.

    `freeze()` includes `.project-block`, because IN PROGRESS holds its blocks a
    level down inside a wrapper per project — leaving it out freezes every box
    except the two that decide which project's list a running row belongs to. The
    cache is cleared in `finish`; left standing it answers the next drag with the
    last drag's thresholds, silently.

    **`slotFor` is a count, and the dead zone falls out of it.** How many frozen
    thresholds the centre has passed. A block that started BELOW yields at its
    **top** edge; one that started ABOVE yields at its **bottom**; a block in a
    list the drag did not start in yields at its **centre**, because an edge rule
    cannot express "index 0" there — the first block's top edge *is* the top of
    the list. The first two are each half a card-height from where you began, so
    a row never twitches out of its own slot. `slotFor`'s old `displaced`
    compensation is gone with the live measurement it compensated for, and
    `blocksIn` returns blocks in **frozen** order, since indexing the live
    children the preview has already permuted would make one cursor position mean
    a different slot every frame.

    Two rectangles decide everything, and they are the two the user can see. Every
    **section** is a box: anywhere inside it means "this category", at the slot
    the card has reached. Every **group** is a nested box inside one: anywhere
    inside it means "and in this group". Padding, headings, the gaps between
    blocks and the empty line are all inside the rectangle they look like they
    are inside, which an element-based rule could not say — the padding of a
    box belongs to the box on screen and to nothing at all in the DOM, so every
    one of those was a dead strip where a drop silently did nothing.

    This replaced a set of aimed targets: a heading meant "leave your group", a
    group header meant "join", and the region between blocks meant nothing on
    purpose, because releasing there might dissolve the grouping being
    rearranged. That caution is answered by the geometry rather than by
    refusing: inside the group's box you stay in it, outside it you leave, and
    both are visible before you let go. **Leaving a group therefore has no
    target of its own any more**, and neither does joining one.

    Three consequences worth keeping:

    - **Grouping is aimed, reordering is not.** Reorganising is the common
      gesture, so it is what everything defaults to; making a new group needs
      the card's centre inside a band a third of a row tall (`PAIR_BAND`). It
      used to be an even split — the middle half of a row grouped — which made
      the rarer and more surprising outcome exactly as easy to hit as the common
      one. **`PAIR_INSET` is gone**, and not because it was wrong: the card is
      rail-locked, so its centre's x never changes for a whole gesture and every
      horizontal test against a full-width row passes always. Keeping it would
      have meant reading the POINTER's x for this one decision — a decision made
      by something the card does not show, which is the disconnect this replaced.
      The band is vertical now, and that is the whole of "aimed".
    - **`GROUP_STICKY` is gone, and leaving a group is the gesture it was
      hurting.** It held 8px of grip on a group's own member so that sorting
      inside one and overshooting the last row by a pixel did not throw the row
      out. The freeze made it redundant *and* revealed it as harmful: dragging a
      row **out of** a group was reported as very difficult, the row being more
      likely to fall back into its original group or auto-combine with another
      task than to come out loose (2026-07-27).

      Redundant, because it existed to absorb a box edge that moved live; frozen,
      the card's centre must travel from the last member's top edge to the block's
      real bottom before it is outside at all, which is the same margin by
      construction. Harmful, because those 8px sat exactly where the next row's
      reorder zone begins — so of the 10px between leaving a group and entering a
      pair band, it spent 8. **The window in which leaving a group meant plain
      reordering was FOUR PIXELS.** With the sticky gone and `PAIR_BAND` at a
      quarter it is 13.3px, and a row is 75/25 reorder-to-pair.

      **One tempting fix was tried and rejected by arithmetic**, which is worth
      keeping because it will look right again. Measure the group as it will be
      once the member has left — its own height off the bottom, since removing a
      row shrinks the block from below — and a middle member's escape drops from
      53px to 15px. But for the **last** member of any group,
      `bottom − ownHeight` lands above that member's own centre, so the card
      begins outside its own group and the row leaves on the first pixel of
      movement. The full box already provides the dead zone the trim was reaching
      for.

      What that leaves: the travel out of a group is the distance to the block's
      bottom edge, so it grows with how far up the group you grabbed — 15px from
      the last member, ~135px from the first of five. That is deliberate. The row
      is visibly sorting down through the rail the whole way, which is honest
      about what is happening; the complaint was about the *outcome* at the end of
      that travel, not its length.
    - **Every measurement excludes the dragged element.** It stays in the flow —
      that is what reserves the gap — so the live preview displaces every block
      below it; feed that back in and the preview chooses its own next position,
      and the row flips between two slots while the cursor holds still. `slotFor`
      used to subtract the dragged block's height from every threshold below it to
      compensate. **That compensation is gone**, because there is nothing left to
      compensate for: the thresholds are frozen at lift, from a layout in which
      the block still sat in its own slot.
    - **A section owns exactly its own rectangle, and the margin between two
      belongs to the one BELOW.** `sectionUnder` used to take the *nearest*,
      which splits a margin down the middle and let a bordered box go on
      claiming about ten pixels past the edge it draws — and a drawn border
      reads as a hard edge, so a drop caught beyond it looks like the cursor
      being misread. The exception is the space past the last section, which is
      most of the window and belongs to it rather than to nothing.
    - **It is measured, never hit-tested — and measured ONCE.**
      `event.target.closest` answers with whatever element is under the pointer,
      and the dragged row is still in the flow — so it can name the section the
      row came FROM while the cursor is over a different one. The only
      `event.target` left in the whole gesture is `pointerdown`'s, which is
      finding out what you grabbed rather than where you are aiming.

    **A box is drawn for the container the drop moves the task INTO, and only
    when that is not the container it is already in.** One rule, and everything
    else falls out of it. A task's container is its group if it is in one, else
    its section — captured at `dragstart`, because the preview moves the
    element and asking later answers with wherever the last `dragover` put it.

    - Repositioning inside NOW draws no NOW box; sorting inside a group draws
      no group box. The preview row alone carries those, and it is the only
      news there — a box around where something already lives says nothing and
      competes with the position for attention.
    - Carrying a row out of its group into the same section's open space lights
      up NOW, because the group is what it was in and the section is what it is
      joining.
    - Nothing at all is drawn until the cursor leaves the box the task started
      in. That is not a separate rule; it is the same one.
    - There is no "you are leaving" look, because leaving is just entering
      something else. The row stepping out of the group's rail shows it.

    Pairing is the one exception: a new group has no container to enter yet, so
    the row it would pair with is always outlined.

    NOW, NEXT and SOMEDAY have no border of their own, so `.drop-zone` is the
    only time they are boxes at all. Its outline is inset (`outline-offset` is
    negative): a section is full width, and an outline drawn outside it reaches
    past the window and can add a horizontal scrollbar.

    **Exactly two elements ever carry `.drop-into`** — a `.task` being paired
    with, and a `.group` being joined — and the stylesheet names exactly those
    two. It used to name `.group-header` and three headings as well; the
    geometry rewrite moved the affordance to the whole container and left the
    old selectors behind, so joining a group drew nothing at all while the rule
    still looked populated. **A stale selector is invisible in both
    directions**, and no text-based test can see it:
    `test_every_class_the_ui_toggles_is_styled` passes on that file, because
    `.drop-into` is a substring of `.group-header.drop-into`. Keep the list
    minimal so a wrong one is obvious by reading.

    **IN PROGRESS is a bucket section with one difference, and adding a second
    one is a bug.** Every part of this — which box owns the cursor, the group
    boxes inside it, the slot nearest the cursor, the pair band, the outlines,
    the preview, reordering — is the same code reached the same way. The single
    difference is **where the order it writes is kept**: `sectionPlacement`
    reports `orders: 'bucket'` or `orders: 'wip'`, and that one word is the
    whole of it.

    It costs one function to hold that line, because IN PROGRESS keeps its
    blocks a level down inside a wrapper per project while a bucket section
    holds them directly. A bucket's `holder` is the section itself, so its
    heading and padding are inside it and a drop there lands at the top; IN
    PROGRESS's is the project wrapper, so the section's own heading, its 8px
    frame and the space below the last project were outside every wrapper and
    resolved to "claim a task that is already claimed" — a no-op, which is a
    refusal. Dragging a running task *up to the top of the list* overshoots into
    exactly that strip, so the commonest reorder there previewed as moved and
    wrote nothing. `ownRunningList` gives an already-running row its own
    project's wrapper whenever the cursor is inside the section but inside no
    wrapper at all, which restores the bucket behaviour verbatim. Two things
    deliberately still fall through to the claim: a cursor over ANOTHER
    project's wrapper, which is a box of its own and stays refused, and a task
    being claimed for the first time, which has no place in the list to position
    within and still lands at the end.

    A bucket's order is `Task.order`, in the task files. IN PROGRESS's cannot
    be, and that is not a shortcut — `order` is a *per-bucket* position, so two
    running tasks in different buckets both hold 0 legitimately and no sequence
    across them is expressible; `groups.renumber` restarts each bucket at 0 by
    design, so it would undo one on the next write anyway. It is also not the
    task files' business: the order of what is on screen right now is view
    state, so it lives in `session.json` beside the fold state (invariant 17
    said this file would hold the next piece of view state, and this is it),
    and reordering the running list therefore makes no diff in a tracked repo.

    That list ranks **blocks**, not rows — a group is one entry. Inside a
    group, the member order is the group's own and is the same list the bucket
    view draws, so it stays in the tasks and `reorder_group` stays the thing
    that changes it. The two views can then never disagree about it.

    This difference used to be `canReorder: false`, which suppressed the
    top-level position entirely — dragging within IN PROGRESS could only form
    groups, and reordering the running list was impossible. That read as the
    section being half-built rather than as a constraint, which is what a
    second difference always reads as.

    Anything else that behaves differently between the two is a defect, not a
    design. It has already happened twice — the section box existed only for IN
    PROGRESS, then existed for both in the JS while a broken CSS comment
    deleted the bucket rule — and both times it read as a missing feature
    rather than as a bug, because the elevated section looked deliberate.
    A new drag behaviour lands in both or in neither.

- **A decoration layer holding clones of rows breaks every document-wide query,
  and none of their authors did anything wrong.** `#drag-layer` holds a clone of
  the row being dragged — checkboxes, `data-project`, `data-id`, and for a group
  its whole container. Six queries for `.task` / `.group` / `.select` /
  `.select-group` then found one more of each than the list holds, with six
  separately silent consequences (a second ticked task in `selectedIds()`, a box
  `restoreTicks` ticks that nothing can clear, a `Clear` that reports success,
  a rename box opened inside a clone about to be deleted). Five of the six
  predate the layer: **"the rows on screen" was an exact synonym for "the rows in
  the list" until it was not.** They are all scoped to `#task-list` now, and
  `test_the_selection_is_read_from_the_list_only` fails the build on a seventh.
