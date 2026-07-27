// The drag gesture — drag.js.
//
// Everything about a drag that is not "where does this land": the pointer
// handling, what you hold, the gap it leaves, the preview, and the three ways a
// drag can end. Where it lands is drag-geometry.js.
//
// ONE controller for the whole list, bound once at load to #task-list. It used
// to be one per section, each closing over its own `dragged`, and that is
// exactly why no drop ever crossed a section: `dragstart` fired on the SOURCE
// section's listener, while the `dragover`/`drop` that followed fired on the
// DESTINATION section's, where `dragged` was still null. preventDefault() ran
// before that guard, so the browser showed a drop cursor the whole way and
// every cross-section gesture looked legal while doing nothing at all.
//
// #task-list is the common ancestor of every section and is never itself
// replaced — render() calls replaceChildren on it — so one listener here
// survives every redraw and cannot stack duplicates. Same reasoning as the
// delegated `change` listener in tasks.js.

function clearDropAffordance(root) {
  root.querySelectorAll('.drop-into, .drop-zone, .emptying').forEach(
    element => element.classList.remove('drop-into', 'drop-zone', 'emptying'));
}

// A group about to cease existing, shown ceasing to exist.
//
// A group IS its name and nothing else (invariant 15), so the last member leaving
// deletes it — but the preview does not say so. The row steps out of the rail and
// the header stays behind looking like a group that still has somewhere to put
// things, which reads as "you have not got out yet". Reported as the reason
// leaving a group was hard: *"I need visual confirmation that I've managed to
// trigger a position that would indeed get rid of the group"* (2026-07-27).
//
// This is the same rule as the drop boxes one level up — draw the consequence of
// the position you are in — applied to the one consequence that is a deletion
// rather than a move. It fires only when the group really is down to this one
// member: with two left, the group survives and fading it would be a lie.
function previewEmptyingGroup(intent, dragged, wasInGroup, isGroup) {
  if (!wasInGroup || isGroup || !intent) return;
  // `sort` permutes a group's own slots, so it never leaves. `pair` always does —
  // it makes a NEW group. Everything else says where it is going.
  const leaving = intent.kind === 'pair' || intent.group !== wasInGroup;
  if (!leaving) return;
  const project = dragged.dataset.project;
  if (groupMemberCount(project, wasInGroup) !== 1) return;
  const container = [...document.querySelectorAll('#task-list .group')].find(
    each => each.dataset.project === project && each.dataset.group === wasInGroup);
  if (container) container.classList.add('emptying');
}

// The whole IN PROGRESS list as [project, block key] pairs, straight off the
// rendered DOM. Wholesale, like the fold state: the renderer owns the list, so
// two partial writes cannot race into disagreeing halves of it — and reading
// every project rather than the one that changed is what makes that true.
//
// Blocks, not rows. A group is one entry; the order of its members is the
// group's own and lives in the tasks, shared with the bucket view.
function inProgressOrderFromDom(section) {
  const entries = [];
  for (const holder of section.querySelectorAll('.project-block')) {
    for (const child of holder.children) {
      if (child.classList.contains('group')) {
        entries.push([holder.dataset.project, `group:${child.dataset.group}`]);
      } else if (child.classList.contains('task')) {
        entries.push([holder.dataset.project, `task:${child.dataset.id}`]);
      }
    }
  }
  return entries;
}

// --- FLIP: the one animation every rearrangement goes through -------------
//
// How long a displaced block takes to get out of the way, and on what curve. The
// settle borrows the same easing, so a drop and the rows it displaces move as one
// gesture rather than as two things happening near each other.
//
// **The curve starts from rest, and that is the whole point of this constant.**
// It was `cubic-bezier(.2, .9, .2, 1)` — chosen against the prototype for feeling
// firm — and it was reported as *"the task cards that move underneath the card I'm
// moving glitch upwards… it jumps a bit. It should just start moving towards its
// new destination"* (2026-07-27).
//
// That reading was exact, and the arithmetic says why. Progress of a 200ms
// displacement by the FIRST painted frame (16ms):
//
//     (.2, .9, .2, 1)   35%      <- a 10px hop on a 30px row, then a slide
//     (.4, 0,  .2, 1)    2%      <- starts moving
//
// A control point with y=0.9 at x=0.2 is an initial slope of 4.5: the animation is
// a third of the way through before anything is drawn, so the first frame IS the
// jump. y1=0 is zero initial velocity, which is what "starts moving" means as a
// number. The end is unchanged — both decelerate into place.
//
// The lesson generalises past this constant: a curve picked by watching a
// prototype is picked from its MIDDLE, because the first frame is over before the
// eye reports anything. Judge a displacement curve by its value at 16ms.
const DISPLACE_MS = 200;
const DISPLACE_EASE = 'cubic-bezier(.4, 0, .2, 1)';
const FLIPPABLE = '.project-block, .group, .task';

// First, Last, Invert, Play. Measure, let `mutate` rearrange things, measure
// again, then animate each block from where it was to where it now is. The layout
// is never fought: every block is already where it belongs and the transform is
// pure decoration on top, which is why an interrupted one can simply be dropped.
//
// ONE function for two callers, with exactly one difference between them:
// **how a block is recognised across the mutation.** A drag moves elements, so
// they are their own identity. A render calls replaceChildren, so the elements are
// destroyed and rebuilt and identity is a key (`keyOf`). Everything else — the
// easing, the nesting rule, the cancel-before-measuring rule — is shared, because
// two copies of it would be two things to keep in step.
//
// Three details, each measured in the prototype rather than reasoned about:
//
// `before` is read WITH any in-flight transform included, which is what makes a
// direction change reverse the motion from where the block actually is rather than
// finishing the old one and then coming back.
//
// Every in-flight animation is cancelled BEFORE the second measurement. A rect
// read while a transform is running is a position nothing is at, so the deltas
// would be computed against phantom layout. (The drop geometry is immune to this
// by a different route — it reads boxes frozen at lift — but this has to know
// where things really are.)
//
// A block whose ancestor is also animating is skipped, or the two transforms
// compound and the inner one lands where neither intended. Document order
// guarantees the ancestor is seen first.
function flipBlocks(mutate, identify) {
  const list = document.getElementById('task-list');
  // The ELEMENT is kept beside its rectangle, not just the rectangle. A block a
  // render removes is detached rather than destroyed, so this map is the only
  // remaining reference to it — which is what lets it be given an exit instead of
  // being cloned for one.
  const before = new Map([...list.querySelectorAll(FLIPPABLE)].map(
    element => [identify(element), { element, rect: element.getBoundingClientRect() }]));
  mutate();
  const settled = [...list.querySelectorAll(FLIPPABLE)];
  for (const element of settled) {
    element.getAnimations().forEach(animation => animation.cancel());
  }
  // EVERY block that moved animates, including the dragged one — the gap.
  //
  // The gap used to be excluded, on the reasoning that it is the slot the card
  // has claimed and so belongs at its new index the instant the decision is made.
  // That confused the decision with the drawing, and it was the jump: a slot
  // change swaps TWO things, and the neighbour glided while the gap — a visible
  // dashed box exactly the size of a row — teleported. One object moving smoothly
  // beside another moving instantly reads as the second one glitching, in both
  // directions, on every trigger. Reported twice (2026-07-27).
  //
  // Animating it costs nothing in correctness: it is already at the new index in
  // the DOM, which is what the drop writes and what `inProgressOrderFromDom`
  // reads. Only its paint is deferred. And it cannot feed back into the geometry,
  // because the geometry reads boxes frozen at lift and never a live rect — which
  // is exactly what the freeze bought.
  const animated = [];
  const arrived = [];
  for (const element of settled) {
    if (animated.some(done => done.contains(element))) continue;
    const was = before.get(identify(element));
    if (!was) { arrived.push(element); continue; }
    const now = element.getBoundingClientRect();
    const dx = was.rect.left - now.left, dy = was.rect.top - now.top;
    if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;
    element.animate(
      [{ transform: 'translate(' + dx + 'px,' + dy + 'px)' }, { transform: 'none' }],
      { duration: DISPLACE_MS, easing: DISPLACE_EASE });
    animated.push(element);
  }
  const present = new Set(settled.map(identify));
  const gone = [...before.entries()]
    .filter(([key]) => !present.has(key))
    .map(([, snapshot]) => snapshot);
  return { arrived, gone };
}

// Where a fixed child of #drag-layer has to be told to sit, given where it should
// APPEAR. The layer is a zoom region on purpose — the card is a clone of a row and
// must be the size that row is now — and `position: fixed` inside a zoomed element
// does not take viewport pixels. Probed rather than reasoned about: write 0, read,
// write 100, read. Two lines, and it cannot be wrong about the engine.
//
// One implementation, used by the card that follows the pointer and by the corpse
// of a row that has just been completed. Two copies of a coordinate mapping is two
// chances to get a sign wrong.
function layerMapping(element) {
  element.style.left = '0px';
  element.style.top = '0px';
  const at0 = element.getBoundingClientRect();
  element.style.left = '100px';
  element.style.top = '100px';
  const at100 = element.getBoundingClientRect();
  return {
    origin: { x: at0.left, y: at0.top },
    scale: { x: (at100.left - at0.left) / 100 || 1,
             y: (at100.top - at0.top) / 100 || 1 },
  };
}

function placeInLayer(element, mapping, x, y) {
  element.style.left = ((x - mapping.origin.x) / mapping.scale.x) + 'px';
  element.style.top = ((y - mapping.origin.y) / mapping.scale.y) + 'px';
}

// What a block IS across a render, when the element itself will not survive one.
//
// The discriminators are load-bearing: a group named "7" and task 7 in the same
// project would otherwise collide on one key, and a group is a container while a
// task is a row, so the wrong one would animate. NUL separates the parts for the
// same reason `restoreTicks` uses it — a project name may contain anything.
function keyOf(element) {
  if (element.classList.contains('task')) {
    return element.dataset.project + '\0t\0' + element.dataset.id;
  }
  if (element.classList.contains('group')) {
    return element.dataset.project + '\0g\0' + element.dataset.group;
  }
  return element.dataset.project + '\0p';
}

// Animate a whole redraw: every block that existed before and after slides from
// where it was to where the new render put it. This is what makes the bucket
// picker, folding, completing, restoring and deleting animate without any of them
// knowing anything about animation — they call render(), as they always did.
//
// No exclusion for a drop's settling row. It does not need one: the settle is
// awaited before the write, so by the time this runs the card is gone and the row
// is already in its final slot, which is a zero delta. The one case where it does
// move is a pair — both rows gain a group container and step into its rail — and
// that is a change worth seeing.
function flipRender(mutate) {
  const { arrived, gone } = flipBlocks(mutate, keyOf);

  // A block that has LEFT. It is detached but not destroyed, so it goes back on
  // screen in the drag layer at the rectangle it used to occupy and dissolves
  // there, while the FLIP above closes the space it left. Same duration and same
  // easing as that slide, so the two read as one gesture rather than as a
  // disappearance next to a shuffle.
  //
  // Not a height collapse: the rows below are already moving up under their own
  // animation, and shrinking the corpse as well would say the space closed twice.
  //
  // Outermost only. Completing the last member of a group removes the row AND the
  // group, and resurrecting both would show the row twice — once on its own and
  // once inside its own container.
  const buried = [];
  for (const { element, rect } of gone) {
    if (buried.some(done => done.contains(element))) continue;
    buried.push(element);
    element.classList.add('leaving');
    element.style.width = rect.width + 'px';
    document.getElementById('drag-layer').append(element);
    placeInLayer(element, layerMapping(element), rect.left, rect.top);
    element.animate([{ opacity: 1 }, { opacity: 0 }],
                    { duration: DISPLACE_MS, easing: DISPLACE_EASE })
      .finished.then(() => element.remove(), () => element.remove());
  }

  // A block that has ARRIVED. It already occupies its space — the rows below it
  // have been pushed down and are animating there — so this is opacity and a few
  // pixels of travel, not a height. Animating height as well would move everything
  // below it a second time, against the FLIP that is already moving them.
  const born = [];
  for (const element of arrived) {
    if (born.some(done => done.contains(element))) continue;
    born.push(element);
    element.animate(
      [{ opacity: 0, transform: 'translateY(-4px)' }, { opacity: 1, transform: 'none' }],
      { duration: DISPLACE_MS, easing: DISPLACE_EASE });
  }
}

function wireDrag() {
  const list = document.getElementById('task-list');
  let dragged = null;
  let draggedIsGroup = false;
  let draggedGroup = null;
  let draggedFrom = null;
  let intent = null;
  // Where the preview picked the block up from. The live move in `pointermove` is
  // a REAL DOM move, and nothing else ever undoes it — so a gesture that wrote
  // nothing used to leave the list showing a position that was never saved,
  // for as long as it took something else to force a render. The next rename,
  // edit or fold then put the row back, which reads as that unrelated edit
  // having reset the task's position. Nothing on screen may claim a place that
  // was not written.
  let startedAt = null;
  // The card, and the numbers that place it. Null except during a drag.
  let card = null;
  // A press that has not yet moved far enough to be a drag. Below the threshold
  // the gesture is a click, and that is what keeps click-to-open-the-editor and
  // double-click-to-rename working on the same pixels a drag starts from.
  let press = null;
  const THRESHOLD = 4;

  // `wrote` used to live here, because `dragend` fired immediately after drop's
  // synchronous part and was the only thing that could tell an abandoned gesture
  // from a claimed one. There is one ending function now and it is told which
  // kind it is, so the flag has nothing left to disambiguate.

  // Put the block back where the drag found it. Cheap to call twice: the first
  // call clears the record. Through `flip`, so an abandoned drag slides home
  // rather than jumping — the row was never written, and a jump reads exactly
  // like something having been written and then undone.
  function undoPreview() {
    if (!startedAt) return;
    const { element, parent, before } = startedAt;
    startedAt = null;
    if (!element.isConnected || !parent.isConnected) return;
    flipBlocks(() => parent.insertBefore(
      element, before && before.parentElement === parent ? before : null), each => each);
  }

  // A drag ends in a `click`, and the native API used to swallow it for us.
  // Pointer events do not: pointerdown/pointerup on a row is a click as far as
  // the browser is concerned, so without this every single drop would also open
  // the editor — and not necessarily on the row you dragged, since the preview
  // has moved things and the click lands on whatever is under the pointer.
  //
  // Capture phase on `window`, so it runs before the row's own onclick. Cleared
  // on the next pointerdown as well as on use, because a pointerup outside the
  // document produces no click at all and a flag left standing would eat the next
  // legitimate one.
  //
  // `detail` is what stops it eating a click it did not cause. A click that came
  // from a pointer carries its click count there; one synthesised by the keyboard
  // — Enter or Space on a focused button, which the editor's focus ring made a
  // supported way to work — or by `element.click()` carries 0. Without the check,
  // cancelling a drag with Escape armed this flag and the NEXT keyboard activation
  // anywhere in the window silently did nothing, because no pointerdown had come
  // along to disarm it. Found by a harness clicking a fold caret programmatically
  // and getting no fold.
  let swallowClick = false;
  window.addEventListener('click', event => {
    if (!swallowClick || event.detail === 0) return;
    swallowClick = false;
    event.stopPropagation();
    event.preventDefault();
  }, true);

  // A press on a row, remembered but not yet acted on.
  list.addEventListener('pointerdown', event => {
    swallowClick = false;
    if (event.button !== 0) return;
    // A control does its own job. This ONE guard replaced
    // releaseDragWhileUsing's eight per-control registrations, and unlike them it
    // covers every control added later — the eighth arrived with the Claude
    // button. The two rename boxes are here for the same reason: selecting text
    // with the mouse inside `draggable="true"` started a drag instead, which is
    // what the two `draggable = false` dances in the rename paths existed for.
    if (event.target.closest('input, select, button, .title-input, .group-name-input')) return;
    const header = event.target.closest('.group-header');
    const element = header ? header.parentElement : event.target.closest('.task');
    if (!element) return;
    // The permission the two undraggable views set (search, all projects), and
    // the same class the grab cursor hangs off.
    if ((header || element).classList.contains('nodrag')) return;
    press = { element, isGroup: Boolean(header), x: event.clientX, y: event.clientY };
  });

  // Lift: build the card, turn the row into the gap, and record where it was.
  function begin(event) {
    const { element, isGroup } = press;
    const layer = document.getElementById('drag-layer');
    // Flush anything a previous drop left mid-flight. Nothing does yet — the
    // settle arrives in a later task — but a stale card holds a stale gap, and
    // `.held` would then resolve to the wrong element and track nothing.
    layer.replaceChildren();
    list.querySelectorAll('.dragging-source').forEach(
      stale => stale.classList.remove('dragging-source'));

    // FIRST, before the card is appended or the gap class is added: these are the
    // only boxes measured at rest for the whole gesture, and everything in
    // drag-geometry.js decides against them.
    freeze();

    const box = element.getBoundingClientRect();
    const held = element.cloneNode(true);
    held.classList.add('held');
    held.style.width = box.width + 'px';
    layer.append(held);

    // `position: fixed` does NOT resolve against the viewport inside an element
    // carrying CSS `zoom`, and #drag-layer is a zoom region on purpose. The mapping
    // is probed rather than reasoned about — see layerMapping, which the exit
    // animation shares.
    const mapping = layerMapping(held);

    card = {
      held,
      mapping,
      size: { w: box.width, h: box.height },
      grabX: press.x - box.left, grabY: press.y - box.top,
      startX: press.x,
    };
    held.style.transformOrigin = card.grabX + 'px ' + card.grabY + 'px';

    dragged = element;
    draggedIsGroup = isGroup;
    startedAt = { element, parent: element.parentElement, before: element.nextSibling };
    const container = element.closest('.group');
    draggedGroup = container ? container.dataset.group : null;
    // The container it STARTED in — its group if it is in one, otherwise its
    // section. Read once and now: the preview moves the element, so asking later
    // would answer with wherever the last move put it. A dragged group is not
    // inside itself; its container is its section.
    const from = element.closest('section[data-bucket], #in-progress');
    draggedFrom = isGroup ? from : (container || from);
    intent = null;

    element.classList.add('dragging-source');
    document.body.classList.add('dragging');
    move(event);

    // The lift, as a CSS transition rather than element.animate(fill:'forwards').
    // A forwards-filling WAAPI animation outranks the inline style for the
    // property it animates for as long as it exists, so a later measurement that
    // clears the transform would still read the lift's scale back. A transition
    // writes the inline style, so there is one source of truth for `transform`.
    held.style.transform = 'scale(1)';
    requestAnimationFrame(() => {
      if (card && card.held === held) held.style.transform = 'scale(1.05)';
    });
  }

  // Scrolling the window when the pointer reaches its edge. Native DnD did this
  // for free; pointer events do not, and a list long enough to scroll is
  // otherwise a list you cannot drag out of.
  //
  // The DOCUMENT scrolls — `body` carries the padding and there is no inner
  // scroll container — so this is `window.scrollBy` against the viewport edges,
  // ramped by how close the pointer is rather than switched on at a line.
  //
  // Driven by the POINTER, not by the probe: this is about reaching the edge of
  // the window with your hand, which is a different question from where the drop
  // lands. `fbox` corrects the frozen boxes for whatever this scrolls past.
  const EDGE = 46, SPEED = 12;
  let scrollTimer = null;
  function autoscroll(pointerY) {
    const height = document.documentElement.clientHeight;
    const above = pointerY, below = height - pointerY;
    const delta = above < EDGE ? -SPEED * (1 - Math.max(above, 0) / EDGE)
                : below < EDGE ? SPEED * (1 - Math.max(below, 0) / EDGE) : 0;
    clearInterval(scrollTimer);
    scrollTimer = null;
    if (!delta) return;
    scrollTimer = setInterval(() => {
      window.scrollBy(0, delta);
      // Re-aim from the SAME pointer position. Holding still at the edge fires no
      // pointermove, so without this the list slides past underneath while the
      // preview stays where the last real event left it — the row lands wherever
      // it was aimed several hundred pixels ago. The card itself does not move,
      // and must not: the hand has not moved.
      if (card) move(card.lastPointer);
    }, 16);
  }

  const SETTLE_MS = 160;
  const FLASH_MS = 700;
  const FLASH_EASE = 'cubic-bezier(.25, .1, .25, 1)';

  // The card flies from your hand to the slot it claimed, and only THEN does the
  // gap stop being a gap. Sequential, not simultaneous: a placeholder collapsing
  // while the thing that fills it is still in the air is what jitters, and it is
  // the specific mistake Reardon's essay names.
  //
  // Resolves either way, and cannot hang: a settle interrupted by the next drag
  // has its animation cancelled, and a frame budget that eats `onfinish` still
  // leaves the gap open forever without the timeout.
  function settleCard(held, row) {
    const done = () => {
      held.remove();
      if (row) row.classList.remove('dragging-source');
    };
    if (!row || !row.isConnected) { done(); return Promise.resolve(); }

    // Measured with the lift transform OFF. The flight ends at `scale(1)`, so its
    // translate applies to the UNSCALED box — read the scaled rect instead and the
    // card lands short by however much the lift grew it. The transition is
    // suspended for the read so the probe cannot animate anything itself.
    const lift = held.style.transform;
    held.style.transition = 'none';
    held.style.transform = 'none';
    const rest = held.getBoundingClientRect();
    held.style.transform = lift;
    // The gap animates now, so it may be mid-flight — and a rect read then is a
    // position nothing is at. Its animation is FINISHED rather than cancelled:
    // finishing lands it at its real slot, which is exactly the target wanted.
    row.getAnimations().forEach(each => each.finish());
    const target = row.getBoundingClientRect();

    // transform, never left/top: those are layout properties, cannot be
    // composited, and would put the flight on the main thread beside a FLIP that
    // is not.
    const flight = held.animate(
      [{ transform: lift },
       { transform: 'translate(' + (target.left - rest.left) + 'px,'
                                 + (target.top - rest.top) + 'px) scale(1)' }],
      { duration: SETTLE_MS, easing: DISPLACE_EASE, fill: 'forwards' });
    return new Promise(resolve => {
      const land = () => { done(); resolve(); };
      flight.onfinish = land;
      flight.oncancel = land;
      setTimeout(() => { if (held.isConnected) land(); }, SETTLE_MS + 120);
    });
  }

  // What just moved, lit up once. The row is looked up AFTER the commit, because
  // `refresh()` rebuilds #task-list with replaceChildren and the element that was
  // dragged is gone by then — flashing it would animate a detached node.
  //
  // Matched by dataset rather than by a built selector, the same way
  // focusGroupName does: a group name is unvalidated user text out of a
  // hand-editable file, so there is no selector to escape wrongly.
  //
  // backgroundColor, not the `background` shorthand, which does not interpolate.
  // It outranks `.task:hover` for its 700ms, and that is right — the flash is the
  // news, not the hover.
  function flash(project, id, groupName) {
    const element = [...document.querySelectorAll(
      groupName ? '#task-list .group' : '#task-list .task')].find(
      candidate => candidate.dataset.project === project
        && (groupName ? candidate.dataset.group === groupName
                      : Number(candidate.dataset.id) === id));
    if (!element) return;
    element.animate([{ backgroundColor: 'rgba(48, 164, 108, .34)' },
                     { backgroundColor: 'rgba(48, 164, 108, 0)' }],
                    { duration: FLASH_MS, easing: FLASH_EASE });
  }

  // Every ending, told which one it is. This is `dragend` and `drop` collapsed
  // into one function, which is why `wrote` is gone: the caller knows.
  async function finish(cancelled) {
    swallowClick = true;
    // Unconditionally, and before anything that can throw or await: a scroll timer
    // left running keeps scrolling the page after the drag is over, which reads as
    // the window having taken over.
    clearInterval(scrollTimer);
    scrollTimer = null;
    const settled = intent;
    const row = dragged;
    const wasInGroup = draggedGroup;
    const wasGroup = draggedIsGroup;
    const held = card ? card.held : null;
    card = null;
    document.body.classList.remove('dragging');
    clearDropAffordance(list);
    // The frozen layout belongs to one gesture. Left standing it would answer the
    // NEXT drag's geometry with this drag's boxes, which is a whole list of
    // thresholds in the wrong places and no error anywhere.
    clearFrozen();
    dragged = null;
    intent = null;

    // Nothing was written, so nothing may be left looking moved. The preview is a
    // REAL DOM move and this is the only thing that ever undoes it. FIRST, before
    // the card flies anywhere: an abandoned card flies back to where the row
    // started, and that is only where the row IS once the preview is undone.
    const abandoned = cancelled || !settled || !row;
    if (abandoned) undoPreview();

    // Awaited before the write, which is what makes the order deterministic rather
    // than a race. `commit` calls `refresh()`, and a redraw landing mid-flight
    // draws the row at its destination while a card is still flying towards it —
    // two of the same task on screen, which is the thing this whole change
    // removed. 160ms is nothing against a local file write.
    if (held) await settleCard(held, row);
    if (abandoned) return;

    await commit(settled, row, wasInGroup, wasGroup);
    // After the commit, so it can find the row `refresh()` drew. Not for a pair:
    // that opens its new group's name box focused, and a flash under an open text
    // box is noise competing with the one thing asking for attention.
    if (settled.kind !== 'pair') {
      flash(row.dataset.project, Number(row.dataset.id),
            wasGroup ? row.dataset.group : null);
    }
  }

  window.addEventListener('pointermove', event => {
    if (card) { move(event); return; }
    if (!press) return;
    if (Math.hypot(event.clientX - press.x, event.clientY - press.y) < THRESHOLD) return;
    begin(event);
  });
  // On `window`, not on #task-list, and deliberately not via setPointerCapture: a
  // drag that leaves the list must keep tracking and a release out there must
  // still end it — the header, the selection bar, past the window edge. Capture
  // would do the same job and throws when the pointer id is not active, which
  // also makes the whole gesture impossible to drive with a synthetic event.
  window.addEventListener('pointerup', () => { press = null; if (card) finish(false); });
  window.addEventListener('pointercancel', () => { press = null; if (card) finish(true); });
  window.addEventListener('keydown', event => {
    if (event.key !== 'Escape' || !card) return;
    event.preventDefault();
    press = null;
    finish(true);
  });

  function move(event) {
    const { held, mapping, grabX, grabY, startX, size } = card;
    // Kept so the autoscroll tick can re-aim without a pointer event of its own.
    card.lastPointer = { clientX: event.clientX, clientY: event.clientY };
    // Rail-locked: the card tracks vertically and never sideways, so it stays
    // over the column it came from and reads as the row itself lifted out of the
    // list rather than as a thing flying around near it.
    //
    // 1:1 with the pointer and with NO easing. This is the one thing in the whole
    // feature that must not be animated.
    const cardX = startX - grabX;
    const cardY = event.clientY - grabY;
    placeInLayer(held, mapping, cardX, cardY);

    // The card's CENTRE is what decides where this lands — Reardon's rule, and the
    // only place in the app that turns a pointer position into an aim point. It is
    // built here and nowhere else, which is what lets drag-geometry.js contain no
    // reference to an event at all.
    //
    // `size` is the card's own box, so a group dragged as a whole block aims from
    // the middle of the block. If a future variant carries only a header, the aim
    // point follows the visible card rather than the gap, which is the half the
    // user can see.
    const probe = { x: cardX + size.w / 2, y: cardY + size.h / 2 };

    autoscroll(event.clientY);
    clearDropAffordance(list);
    intent = dropIntent(probe, dragged, draggedIsGroup);
    if (!intent) return;
    // The live move IS the affordance for a reorder: the row is drawn where it
    // would land, indented into a group's rail or clear of it, which says more
    // than an outline could. `before` is measured with the dragged element
    // excluded, so inserting it cannot change the answer that put it there.
    if (intent.preview) {
      const { container, before } = intent.preview;
      // Only when it actually moves. pointermove fires every frame, and an
      // insertBefore that changes nothing still invalidates layout for every
      // rect read on the next one.
      if (dragged.parentElement !== container || dragged.nextSibling !== before) {
        flipBlocks(() => container.insertBefore(dragged, before), element => element);
      }
    }
    // ONE rule: draw the container this drop would move the task INTO, and
    // only when that is not the container it is already in. A box around where
    // something already lives says nothing, and it competes with the one thing
    // that is news — the exact position. So repositioning inside NOW draws no
    // NOW box and sorting inside a group draws no group box; the preview row
    // alone carries those. Carry the row out of its group into the same
    // section's open space and NOW lights up, because the group is what it was
    // in and the section is what it is joining.
    //
    // It falls out of this that nothing at all is drawn until the cursor
    // leaves the box the task started in — there is no separate rule for that,
    // and there is no "you are leaving" look. Leaving is just entering
    // something else, and the row stepping out of the group's rail shows it.
    if (intent.kind === 'pair') {
      // The exception, because a new group has no container to enter yet and
      // nothing else on screen would say which two rows are pairing.
      intent.element.classList.add('drop-into');
    } else if (intent.into && intent.into !== draggedFrom) {
      // A section reads as the category it is; a group reads as a thing to
      // join. Same rule, two weights.
      intent.into.classList.add(
        intent.into === intent.section ? 'drop-zone' : 'drop-into');
    }
    // After the boxes, because it is the same idea: draw what this position would
    // do. The one consequence that is a deletion rather than a move.
    previewEmptyingGroup(intent, dragged, draggedGroup, draggedIsGroup);
  }

  // What a drop actually writes. Reached only from `finish`, and only for a
  // gesture that resolved to something — the refusals and the cancellations are
  // handled there, where the preview is taken back.
  async function commit(settled, row, wasInGroup, wasGroup) {
    // The row's OWN project, never currentProject. In a bucket section the two
    // are the same; in IN PROGRESS, which spans projects, they are not — and
    // dropIntent has already refused any drop across two of them.
    const project = row.dataset.project;
    const name = wasGroup ? row.dataset.group : null;

    if (settled.kind === 'pair') {
      // The target's title seeds the name, and the target comes first so the
      // new block sits where it already was. Read the title from state rather
      // than the row, which may carry display decoration.
      const targetId = Number(settled.over.dataset.id);
      const target = state.tasks.find(
        task => task.project === project && task.id === targetId);
      // Read before the call: state is still what it was when the drag began,
      // which is what "where this row came from" means.
      const moved = taskOf(row);
      const born = await callApi('create_group', project,
        [targetId, Number(row.dataset.id)], target ? target.title : 'New group');
      // Redraw rather than return bare. callApi has already said what went
      // wrong, but the preview has moved the row and `finish` left it there —
      // this path claimed the gesture — so the list is
      // showing a pairing that does not exist. A refresh is the only thing that
      // can be right here — it draws whatever actually landed on disk, which
      // for a half-failed pair is not something the DOM could work out. Same at
      // every failure below.
      if (born === API_FAILED) { await refresh(); return; }
      // A group born in a section the dragged row did not come from has to be
      // placed as well as named — pairing a backlog task onto a running one
      // means both are running now. create_group already put them in the
      // target's bucket, so only the status can still be wrong. Two calls,
      // because naming a group and placing one are two ideas, and a failure
      // between them leaves a valid group that simply was not claimed.
      if (moved && moved.status !== settled.status
          && await callApi('place_group', project, born,
               { status: settled.status }) === API_FAILED) { await refresh(); return; }
      await refresh();
      // Only on birth. A task joining an existing group must not reopen it —
      // that name is an identity by then, not a suggestion (invariant 11).
      focusGroupName(project, born);
      return;
    }

    if (settled.kind === 'sort') {
      // Only the rows inside this one container, and only this group's name:
      // reorder_group permutes the slots these tasks already hold, so a
      // section showing part of a bucket — or part of a group — can reorder
      // without stamping over anything it cannot see.
      const container = row.closest('.group');
      if (!container) { undoPreview(); return; }
      const ids = [...container.querySelectorAll('.task')].map(
        element => Number(element.dataset.id));
      if (await callApi('reorder_group', project,
          container.dataset.group, ids) === API_FAILED) { await refresh(); return; }
      await refresh();
      return;
    }

    const destination = { bucket: settled.bucket, group: settled.group,
                          status: settled.status };
    // Read AFTER the live move, so what gets written is what the user is
    // looking at. Members stay contiguous because a group's rows live inside
    // its own container, and folded rows are still in there (invariant 18) so
    // the list has no hole in it. Only a BUCKET's order lives in the tasks;
    // IN PROGRESS's is view state and is written separately below.
    const ids = settled.positioned === 'bucket'
      ? [...settled.section.querySelectorAll('.task')].map(
          element => Number(element.dataset.id))
      : null;
    // A pure reposition within IN PROGRESS changes nothing about the task
    // itself — same bucket, same group, still running — so it writes no task
    // file at all, only the view state. Without this check every nudge of the
    // running list would rewrite a `.md` file to identical content.
    const current = wasGroup ? draggedState(row, true) : taskOf(row);
    const changed = !current || settled.status !== current.status
      || (!wasGroup && settled.group !== current.group);
    if (changed || ids) {
      const outcome = wasGroup
        ? await callApi('place_group', project, name, destination, ids)
        : await callApi('place_task', project, Number(row.dataset.id),
                        destination, ids);
      if (outcome === API_FAILED) { await refresh(); return; }
    }
    // Read after the call above, deliberately. `finish` leaves the preview in
    // place for a claimed gesture — it only takes it back on a refusal or a
    // cancellation — so the DOM here still says where the user let go. This used
    // to be a statement about `dragend` having already fired and honoured
    // `wrote`; one ending function makes it a statement about one branch.
    if (settled.positioned === 'wip' && await callApi('set_in_progress_order',
        inProgressOrderFromDom(settled.section)) === API_FAILED) {
      await refresh();
      return;
    }
    // Before the refresh, while state.tasks still counts the member on its way
    // out — a group that just lost its last one does not exist any more, and
    // nothing would ever unfold its leftover entry.
    if (!wasGroup && settled.group !== wasInGroup) {
      await forgetFoldIfEmptied(project, wasInGroup);
    }
    await refresh();
  }
}

// Bound once, at load. Inside a render function this would stack a duplicate
// listener on every redraw; #task-list outlives all of them — and the pointer
// listeners are on `window`, which outlives everything.
wireDrag();
