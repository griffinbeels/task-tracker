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
  root.querySelectorAll('.drop-into, .drop-zone').forEach(
    element => element.classList.remove('drop-into', 'drop-zone'));
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
  // call clears the record.
  function undoPreview() {
    if (!startedAt) return;
    const { element, parent, before } = startedAt;
    startedAt = null;
    if (!element.isConnected || !parent.isConnected) return;
    parent.insertBefore(
      element, before && before.parentElement === parent ? before : null);
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
  let swallowClick = false;
  window.addEventListener('click', event => {
    if (!swallowClick) return;
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

    const box = element.getBoundingClientRect();
    const held = element.cloneNode(true);
    held.classList.add('held');
    held.style.width = box.width + 'px';
    layer.append(held);

    // `position: fixed` does NOT resolve against the viewport inside an element
    // carrying CSS `zoom`, and #drag-layer is a zoom region on purpose. Probe the
    // mapping instead of reasoning about it: two writes and two reads give the
    // origin and the scale together, and cannot be wrong about the engine.
    held.style.left = '0px';
    held.style.top = '0px';
    const at0 = held.getBoundingClientRect();
    held.style.left = '100px';
    held.style.top = '100px';
    const at100 = held.getBoundingClientRect();

    card = {
      held,
      origin: { x: at0.left, y: at0.top },
      scale: { x: (at100.left - at0.left) / 100, y: (at100.top - at0.top) / 100 },
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

  // Every ending, told which one it is. This is `dragend` and `drop` collapsed
  // into one function, which is why `wrote` is gone: the caller knows.
  async function finish(cancelled) {
    swallowClick = true;
    const settled = intent;
    const row = dragged;
    const wasInGroup = draggedGroup;
    const wasGroup = draggedIsGroup;
    if (card) { card.held.remove(); card = null; }
    if (row) row.classList.remove('dragging-source');
    document.body.classList.remove('dragging');
    clearDropAffordance(list);
    dragged = null;
    intent = null;
    // Nothing was written, so nothing may be left looking moved. The preview is a
    // REAL DOM move and this is the only thing that ever undoes it.
    if (cancelled || !settled || !row) { undoPreview(); return; }
    await commit(settled, row, wasInGroup, wasGroup);
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
    const { held, origin, scale, grabX, grabY, startX } = card;
    // Rail-locked: the card tracks vertically and never sideways, so it stays
    // over the column it came from and reads as the row itself lifted out of the
    // list rather than as a thing flying around near it.
    //
    // 1:1 with the pointer and with NO easing. This is the one thing in the whole
    // feature that must not be animated.
    const cardX = startX - grabX;
    const cardY = event.clientY - grabY;
    held.style.left = ((cardX - origin.x) / scale.x) + 'px';
    held.style.top = ((cardY - origin.y) / scale.y) + 'px';

    clearDropAffordance(list);
    intent = dropIntent(event, dragged, draggedIsGroup);
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
        container.insertBefore(dragged, before);
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
