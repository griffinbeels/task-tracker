// Where a drop lands — drag-geometry.js.
//
// This file answers one question and draws nothing: given a point, what does
// releasing there mean? `dropIntent` is the answer and every other function
// here serves it.
//
// WHERE a drop lands is read from GEOMETRY, not from `event.target`. Every
// section is a box: anywhere inside it means "this category", at the slot the
// card has reached. Every group is a nested box inside that one: anywhere inside
// it means "and in this group". Those are the two rectangles a user can actually
// see, so they are the two the rule is written against — an element-based rule
// kept disagreeing with them, because the padding of a box belongs to the box on
// screen and to nothing at all in the DOM.
//
// `event.target.closest` would also answer with whatever element happens to be
// under the pointer, and the dragged row is still in the flow — so it can name
// the section the row came FROM while the cursor is over a different one.
//
// TWO THINGS DECIDE EVERYTHING HERE, and neither is the mouse pointer.
//
// The POINT is the card's centre, handed in as `probe`. Where you grabbed the row
// stops mattering, and the list answers to the thing you can see rather than to a
// pointer that may be twenty pixels off one end of it.
//
// The BOXES are frozen at lift (`freeze` below). Reardon's rule needs that: an
// edge that moves as you cross it is not a threshold.
//
// Nothing in this file reads an event, and a convention test says so — otherwise
// one decision quietly goes back to aiming with the mouse while every other one
// uses the card, which is a disagreement no reviewer would see.

function groupOf(element) {
  const container = element.closest('.group');
  return container ? container.dataset.group : null;
}

function taskOf(row) {
  return state.tasks.find(task => task.project === row.dataset.project
    && task.id === Number(row.dataset.id));
}

// What the dragged thing is right now, read from state rather than the DOM: a
// row carries display decoration (nameForeignRows rewrites foreign titles) and
// never carries its own status at all.
function draggedState(dragged, isGroup) {
  if (!isGroup) {
    const task = taskOf(dragged);
    return task && { group: task.group || null, status: task.status,
                     bucket: task.bucket };
  }
  const members = state.tasks.filter(task =>
    task.project === dragged.dataset.project
    && task.group === dragged.dataset.group && task.status !== 'done');
  if (!members.length) return null;
  // A group can be half-running — that is what a header reading "2 of 5"
  // means. It only counts as already-somewhere when every member agrees, so
  // dragging the running half back to a bucket still resolves to a real
  // change rather than being refused as a no-op.
  const agreed = members.every(member => member.status === members[0].status);
  return { group: dragged.dataset.group, bucket: members[0].bucket,
           status: agreed ? members[0].status : null };
}

// What a section does to whatever lands in it. A bucket section places tasks
// as open and at a position; IN PROGRESS places them as running with no
// position — its rows sort by project then group, and they can sit in three
// different buckets, so there is no one bucket for reorder_bucket to renumber.
// What a section does to whatever lands in it, and where its order is kept.
// Both sections reorder; they write to different places, because they are
// ordering different things. A bucket's order is `Task.order` and belongs to
// the tasks. IN PROGRESS's cannot be — `order` is per-bucket, so two running
// tasks in different buckets both hold 0 — so it is view state in
// session.json, and it ranks BLOCKS rather than rows (a group's own member
// order is shared with the bucket view and stays there).
function sectionPlacement(section) {
  const bucket = section.dataset.bucket || null;
  return bucket
    ? { bucket, status: 'open', orders: 'bucket' }
    : { bucket: null, status: 'in-progress', orders: 'wip' };
}

// IN PROGRESS splits its list by project, so its blocks live one level down.
// Geometry, like everything else here — the project a drop belongs to is the
// wrapper whose box holds the cursor, and it must be the dragged row's own.
function projectBlockUnder(section, probe, project) {
  return [...section.querySelectorAll('.project-block')].find(
    holder => holder.dataset.project === project && withinBox(holder, probe)) || null;
}

// Inside IN PROGRESS but inside no project block at all: the section's own
// heading, its 8px frame of padding, the space below the last project. A
// section is a box and everything in it aims at that box (invariant 28), so a
// row ALREADY in this list keeps its place in its own project's list at the
// slot nearest the cursor — dropping on the heading means the top, exactly as
// it does on a bucket's NOW/NEXT/SOMEDAY.
//
// Without this those strips resolved to "claim a task that is already claimed",
// which is a no-op, which is a refusal — so the commonest reorder there is
// (drag a running task up to the top, overshooting into the heading) previewed
// as moved and wrote nothing.
//
// Two things deliberately still fall through to the claim: a cursor over
// ANOTHER project's block, which is a box of its own and stays refused, and a
// task being claimed for the first time, which has no place in the list yet to
// position within and so still lands at the end.
function ownRunningList(section, probe, dragged, isGroup) {
  const blocks = [...section.querySelectorAll('.project-block')];
  if (blocks.some(holder => withinBox(holder, probe))) return null;
  const current = draggedState(dragged, isGroup);
  if (!current || current.status !== 'in-progress') return null;
  return blocks.find(
    holder => holder.dataset.project === dragged.dataset.project) || null;
}

// A destination that would change nothing gets no affordance — the outline is
// a promise that something will happen. Positional drops never come through
// here: moving a row inside its own bucket changes none of these three fields
// and is still a real drop.
//
// "Already there" means the same group AND the same status, which is what lets
// a NOW member of group G be dropped into G's box inside IN PROGRESS — that
// claims it — while the same drop in its own section stays a no-op.
function placement(destination, dragged, isGroup) {
  const current = draggedState(dragged, isGroup);
  if (!current) return null;
  // A group drag never changes membership, so the destination's `group` is
  // not about it — place_group fills in the name. Comparing the two would
  // read every group drag as "become loose" and so never as a no-op, which
  // would light up the box the group is already in.
  const settled = (isGroup || destination.group === current.group)
    && destination.status === current.status
    && (destination.bucket === null || destination.bucket === current.bucket);
  return settled ? null : { kind: 'place', ...destination };
}

// Grouping must be aimed; reordering must not. The band is a third of a row's
// height, centred — "very clearly on top of that task" rather than merely
// nearest to it. Everything outside it reorders.
//
// It used to be inset from both ends as well (`PAIR_INSET`, 12px). That constant
// is gone, and not because it was wrong: the card is rail-locked now, so its
// centre's x never changes for the whole gesture, and every horizontal test
// against a full-width row passes always. Keeping it would have meant reading the
// POINTER's x for this one decision — a decision made by something the card does
// not show, which is exactly the disconnect this design removes. So the band is
// vertical, and one third of a row is the whole of "aimed".
const PAIR_BAND = 1 / 3;

// A group keeps a few pixels of grip on the row already inside it, so that
// sorting within a group and overshooting the last member by a pixel does not
// throw the row out of the group. Leaving is still one deliberate drag clear
// of the box; only the twitch is absorbed.
const GROUP_STICKY = 8;

// --- The frozen layout ---------------------------------------------------
//
// Every box in the list, measured ONCE at lift and never again. Everything below
// reads `fbox`, so the whole rule set is evaluated against a layout that cannot
// move while the gesture is happening.
//
// This is not an optimisation. Reardon's rule — "once the centre position of an
// item A goes over the edge of another item B, B moves out of the way" — is
// UNSTABLE against a live layout: claiming a slot moves the very edge that
// decided it, so the forward and reverse triggers land on the same pixel and the
// row flickers between two slots under a still cursor. Frozen, each block has
// exactly one threshold for the whole gesture, and it cannot be crossed twice.
//
// It buys two more things that were separately wrong before. The thing you are
// aiming at stops moving: a row leaving NOW shortens NOW and lifts NEXT and
// SOMEDAY up underneath the cursor mid-gesture. And no rect can be read while
// something is animating — a rect read mid-transition is a position nothing is
// at, which is what Phase 2's FLIP would otherwise feed straight back in here.
//
// `.project-block` is in the set because IN PROGRESS holds its blocks a level
// down inside a wrapper per project, and `projectBlockUnder` and `ownRunningList`
// both measure those wrappers. Leaving it out would freeze every box except the
// two that decide which project's list a running row belongs to.
let frozen = null;
// Where the page was scrolled to when it froze. A frozen box is in VIEWPORT
// coordinates, and the probe is built from `event.clientY` which is too — so the
// moment the page scrolls under the gesture, every cached box is stale by exactly
// the scroll delta and every threshold is that far out of place. Autoscroll makes
// that happen on purpose, several times a second.
//
// Re-freezing on scroll would be the other answer and it is the wrong one: it
// would hand each block a new threshold mid-gesture, which is the instability the
// freeze exists to remove. One number, corrected on read, keeps a single
// threshold per block for the whole drag no matter how far the list travels.
let frozenAtScrollY = 0;

function freeze() {
  frozen = new Map();
  frozenAtScrollY = window.scrollY;
  for (const element of document.querySelectorAll(
      '#task-list section, #task-list .project-block, #task-list .group, #task-list .task')) {
    frozen.set(element, element.getBoundingClientRect());
  }
}

function clearFrozen() {
  frozen = null;
}

// The box to decide against: frozen if this gesture froze one, live otherwise.
// The fallback is not a nicety — a block created since the lift (nothing does
// that today) has no frozen box, and answering with its live one is better than
// answering with undefined.
function fbox(element) {
  const cached = frozen && frozen.get(element);
  if (!cached) return element.getBoundingClientRect();
  const drift = window.scrollY - frozenAtScrollY;
  if (!drift) return cached;
  return new DOMRect(cached.x, cached.y - drift, cached.width, cached.height);
}

// The section the probe is in. A section owns exactly its own rectangle, and
// the margin between two of them belongs to the one BELOW.
//
// Not "the nearest", which is what this was: nearest splits the margin down
// the middle, so a box with a visible border went on claiming about ten pixels
// past the edge it draws — and a border reads as a hard edge, so a drop caught
// beyond it looks like the app misreading the cursor. Handing the whole gap
// downwards makes the rule one you can see: inside the outline or not.
//
// Measured rather than hit-tested. `event.target.closest` would answer with
// whatever element happens to be under the pointer, and the dragged row is
// still in the flow — so it could name the section the row came FROM while the
// cursor is over another one.
function sectionUnder(probe) {
  const sections = [...document.querySelectorAll(
    '#task-list section[data-bucket], #task-list #in-progress')];
  if (!sections.length) return null;
  const inside = sections.find(candidate => {
    const box = fbox(candidate);
    return probe.y >= box.top && probe.y <= box.bottom;
  });
  if (inside) return inside;
  // Past the end of the list — the empty space below SOMEDAY is a great deal
  // of the window, and it belongs to the last section rather than to nothing.
  const last = sections[sections.length - 1];
  if (probe.y > fbox(last).bottom) return last;
  return sections.find(candidate => probe.y < fbox(candidate).top) || last;
}

// The blocks a container orders, minus the one being dragged. A top-level list
// is rows and group containers together — a group occupies one slot, which is
// what keeps its members contiguous (invariant 16).
//
// Returned in FROZEN order, not live DOM order. `slotFor`'s thresholds are
// relative to the dragged block's own frozen position, so the list they index
// into has to be the one they were computed against — the preview has already
// permuted the live children, and indexing that would make the same cursor
// position mean a different slot every frame.
function blocksIn(container, dragged, selector) {
  const live = [...container.children].filter(child =>
    child !== dragged && child.matches(selector));
  if (!frozen) return live;
  return live.sort((first, second) => fbox(first).top - fbox(second).top);
}

// The slot the dragged block belongs in, by Reardon's rule: "once the centre
// position of an item A goes over the edge of another item B, B moves out of the
// way." One frozen threshold per block, and the slot is simply how many of them
// the centre has passed.
//
// WHICH edge depends on where the block started relative to the dragged one, and
// that is not arbitrary — it is what produces the dead zone. A block that was
// BELOW yields when your centre reaches its top; a block that was ABOVE yields
// when your centre reaches its bottom. Both are exactly half a card-height from
// where you started, so the row never twitches out of its own slot, and every
// threshold after that is a hard edge you can see.
//
// In a list the dragged block was never in there is no gap and no before/after,
// so the threshold is the block's CENTRE — the ordinary insertion rule. An edge
// rule cannot express "index 0" there: the first block's top edge IS the top of
// the list, so it reads as already passed the moment you arrive.
//
// This replaced a midpoint rule fed the POINTER's y, with the dragged block's own
// height subtracted back out of every threshold below it. Both halves were wrong
// in the same direction: grab a row two pixels above its own bottom edge and the
// pointer starts BELOW that row's midpoint, so the threshold was already crossed
// and a 6px sideways twitch reordered it before it had moved down at all
// (measured 2026-07-26). Where you grabbed a row decided whether it reordered
// instantly, which is what "robotic" turned out to mean.
function slotFor(blocks, centreY, dragged, container) {
  const home = Boolean(frozen) && frozen.has(dragged)
    && dragged.parentElement === container;
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

function withinBox(element, probe, grow = 0) {
  const box = fbox(element);
  return probe.x >= box.left - grow && probe.x <= box.right + grow
    && probe.y >= box.top - grow && probe.y <= box.bottom + grow;
}

// The group box the probe is inside. The dragged row's OWN group is not
// excluded — that is how sorting within a group works — it just gets the extra
// grip.
function groupUnder(section, probe, dragged) {
  const mine = groupOf(dragged);
  return [...section.querySelectorAll('.group')].find(container =>
    container !== dragged
    && withinBox(container, probe,
                 container.dataset.group === mine ? GROUP_STICKY : 0)) || null;
}

// A loose top-level row the card is very clearly on top of — the one gesture
// here that makes a new group, so the one that has to be aimed. Vertical only
// now: see PAIR_BAND for why the horizontal inset went.
function pairTarget(section, probe, dragged, project) {
  return [...section.querySelectorAll('.task')].find(row => {
    if (row === dragged || row.dataset.project !== project) return false;
    if (row.parentElement.classList.contains('group')) return false;
    const box = fbox(row);
    const margin = box.height * (1 - PAIR_BAND) / 2;
    return probe.y >= box.top + margin && probe.y <= box.bottom - margin;
  }) || null;
}

// A drop resolves to a DESTINATION — {bucket, group, status} — applied by a
// single place_task/place_group call. Two gestures keep their own names because
// they are not placements: `pair` names a NEW group, and `sort` permutes one
// group's own slots. A refusal is null.
// `probe` is a point — {x, y} in viewport pixels — and is the CARD's centre, not
// the pointer. Taking a point rather than an event is what makes that provable:
// nothing in this file can reach for `event.clientY` and quietly aim one decision
// with the mouse while every other one uses the card
// (test_the_drag_geometry_never_reads_the_pointer_directly).
function dropIntent(probe, dragged, draggedIsGroup) {
  const section = sectionUnder(probe);
  if (!section) return null;
  const lands = sectionPlacement(section);
  const project = dragged.dataset.project;

  // One project at a time. Ids are per-project and so is a group name, so a
  // cross-project drop has nothing coherent to mean. A bucket section shows
  // one project and says so; IN PROGRESS spans every project, and takes each
  // row on its own terms.
  if (lands.bucket && section.dataset.project !== project) return null;

  // 1. Grouping — the aimed gesture, so it is tried first and refuses easily.
  if (!draggedIsGroup) {
    const target = pairTarget(section, probe, dragged, project);
    if (target) return { kind: 'pair', over: target, element: target,
                         status: lands.status, section };
  }

  // 2. Inside a group's box. A group is one level deep, so a dragged group
  // never enters one — it reorders past it at the top level instead.
  const container = draggedIsGroup ? null : groupUnder(section, probe, dragged);
  if (container && container.dataset.project === project) {
    const name = container.dataset.group;
    const members = blocksIn(container, dragged, '.task');
    const before = members[slotFor(members, probe.y, dragged, container)] || null;
    // A group's own member order lives in `Task.order` and is the same list the
    // bucket view draws, so reordering inside one is always that — never the
    // WIP order, which ranks whole blocks. IN PROGRESS renders only part of a
    // bucket, so it trades the slots its members already hold rather than
    // renumbering a bucket it cannot see; a bucket section draws the whole
    // bucket, so its ordered id list positions the member directly.
    if (lands.orders === 'wip' && name === groupOf(dragged)) {
      return { kind: 'sort', preview: { container, before }, into: container,
               section };
    }
    return { kind: 'place', bucket: null, group: name, status: lands.status,
             into: container, section, positioned: lands.orders,
             preview: { container, before } };
  }

  // 3. Anywhere else in the box: this category, no group, nearest slot. The
  // headings, the padding, the gaps between blocks and the empty line all land
  // here — they are inside the rectangle the user is aiming at, so they behave
  // like it. This is what a grouped row dropped clear of its group's box rides
  // out on, which is why leaving a group needs no target of its own any more.
  // IN PROGRESS holds its blocks inside a wrapper per project. With the cursor
  // over one, the drop has a position in that project's list like anywhere
  // else; over the box but not over any wrapper — the section's own heading,
  // its padding, the empty line, the space below the last project — a row that
  // is already running keeps its position in its OWN project's list
  // (ownRunningList), and only a row with no place in that list yet falls
  // through to the claim below, which lands at the end.
  const holder = lands.orders === 'wip'
    ? (projectBlockUnder(section, probe, project)
       || ownRunningList(section, probe, dragged, draggedIsGroup))
    : section;
  if (!holder) {
    const claim = placement({ bucket: null, group: null, status: lands.status },
                            dragged, draggedIsGroup);
    return claim && { ...claim, into: section, section };
  }
  const blocks = blocksIn(holder, dragged, '.task, .group');
  return { kind: 'place', bucket: lands.bucket, group: null, status: lands.status,
           into: section, section, positioned: lands.orders,
           preview: { container: holder,
                      before: blocks[slotFor(blocks, probe.y, dragged, holder)] || null } };
}
