// Group blocks — the one indented container, its header, and the drag that
// forms and dissolves them. A group is its name (see groups.py), so nothing
// here holds an id: a block is simply the tasks whose `group` strings match.
//
// No group entity crosses the bridge. get_state already returns every task
// with its `group` field, and a second representation would be a second source
// of truth.

// Blocks in render order, mirroring groups.py's renumber read-only: each group
// is keyed by its lowest member order, each loose task is a block of its own,
// and ties break on the lowest id. Members sort the same way inside.
function groupBlocks(tasks) {
  const blocks = new Map();
  for (const task of tasks) {
    const key = task.group ? `group:${task.group}` : `task:${task.id}`;
    if (!blocks.has(key)) blocks.set(key, { group: task.group || null, tasks: [] });
    blocks.get(key).tasks.push(task);
  }
  const ordered = [...blocks.values()];
  for (const block of ordered) {
    block.tasks.sort((a, b) => a.order - b.order || a.id - b.id);
    block.order = Math.min(...block.tasks.map(t => t.order));
    block.lowestId = Math.min(...block.tasks.map(t => t.id));
  }
  return ordered.sort((a, b) => a.order - b.order || a.lowestId - b.lowestId);
}

// The group's whole membership, both statuses, excluding the archive. This is
// the denominator in "2 of 5" — a group with some members in progress and some
// not renders in two places, and without the fraction that reads as a
// rendering fault rather than as the true state.
function groupMemberCount(project, name) {
  return state.tasks.filter(
    t => t.project === project && t.group === name && t.status !== 'done').length;
}

// --- Folding ------------------------------------------------------------
//
// A fold outlives the window: the set lives in session.json beside
// last_project, so what you folded away stays folded across a restart. The
// renderer owns the whole set and writes it back wholesale — there is no
// per-item add/remove call, so two folds cannot race into disagreeing halves
// of one list.

function collapsedView() {
  if (!state.collapsed) state.collapsed = { projects: [], groups: [] };
  return state.collapsed;
}

function isProjectCollapsed(project) {
  return collapsedView().projects.includes(project);
}

function isGroupCollapsed(project, name) {
  return collapsedView().groups.some(pair => pair[0] === project && pair[1] === name);
}

function persistCollapsed() {
  const view = collapsedView();
  return callApi('set_collapsed', view.projects, view.groups);
}

// A group that just lost its last member does not exist any more — a group IS
// its name, so nothing renders it and nothing can unfold it. Drop the entry,
// or the name comes back folded if it is ever used again. Called BEFORE the
// refresh, while state.tasks still counts the members on their way out.
//
// `leaving` is how many of them are going: 1 for a task dragged out of a
// group, all of them for a group completed from its header. Without it the
// count of what remains is compared against the wrong number, and every group
// larger than one member keeps its fold entry through being emptied.
async function forgetFoldIfEmptied(project, name, leaving = 1) {
  if (!name || groupMemberCount(project, name) > leaving) return;
  const folded = collapsedView().groups;
  const at = folded.findIndex(pair => pair[0] === project && pair[1] === name);
  if (at === -1) return;
  folded.splice(at, 1);
  await persistCollapsed();
}

// The same rule for a batch: completing tasks is the other way a group can be
// emptied, and the ids can span several groups at once (a selection is not
// obliged to sit in one). Counted per group, from state.tasks, so it must run
// BEFORE the completion — afterwards the members are gone and there is
// nothing left to tell an emptied group from a group that never had these
// tasks. Restore from Progress is what makes the leak visible: without this,
// a group completed and then restored comes back folded with nothing on
// screen to say why.
async function forgetFoldsEmptiedBy(project, ids) {
  const leaving = new Map();
  for (const task of state.tasks) {
    if (task.project !== project || !task.group || task.status === 'done') continue;
    if (!ids.includes(task.id)) continue;
    leaving.set(task.group, (leaving.get(task.group) || 0) + 1);
  }
  for (const [name, count] of leaving) await forgetFoldIfEmptied(project, name, count);
}

// Render from local state first and persist afterwards. A fold that waits for
// the round trip before it moves reads as a click that missed.
async function toggleProjectCollapsed(project) {
  const folded = collapsedView().projects;
  const at = folded.indexOf(project);
  if (at === -1) folded.push(project); else folded.splice(at, 1);
  render();
  await persistCollapsed();
}

async function toggleGroupCollapsed(project, name) {
  const folded = collapsedView().groups;
  const at = folded.findIndex(pair => pair[0] === project && pair[1] === name);
  if (at === -1) folded.push([project, name]); else folded.splice(at, 1);
  render();
  await persistCollapsed();
}

function caretButton(collapsed, onToggle) {
  const button = document.createElement('button');
  button.className = 'caret';
  button.textContent = collapsed ? '▸' : '▾';
  button.title = collapsed ? 'Expand' : 'Collapse';
  button.onclick = event => { event.stopPropagation(); onToggle(); };
  return button;
}

// A <select> or button inside draggable="true" can start a drag instead of
// doing its own job in Chromium — the dropdown never opens and nothing says
// why. Suspend the header's draggability while the pointer is on the control.
function releaseDragWhileUsing(control, header) {
  // Restore what the header WAS, not `true`. In the IN PROGRESS section the
  // header is deliberately not draggable — there is nothing to reorder — and
  // restoring a hard true would hand it a grab cursor and a drag ghost for a
  // gesture that can never do anything.
  const wasDraggable = header.draggable;
  const restore = () => { header.draggable = wasDraggable; };
  control.addEventListener('mousedown', () => { header.draggable = false; });
  control.addEventListener('mouseup', restore);
  control.addEventListener('mouseleave', restore);
}

function groupBlock(block, options = {}) {
  const { showBucket = true, showDisband = true, showReset = false,
          draggable = true, headerDraggable = draggable } = options;
  const project = block.tasks[0].project;
  const folded = isGroupCollapsed(project, block.group);

  const container = document.createElement('div');
  container.className = folded ? 'group collapsed' : 'group';
  container.dataset.group = block.group;
  container.dataset.project = project;

  const header = document.createElement('div');
  header.className = 'group-header';
  header.draggable = headerDraggable;

  const caret = caretButton(folded, () => toggleGroupCollapsed(project, block.group));

  const selectAll = document.createElement('input');
  selectAll.type = 'checkbox';
  selectAll.className = 'select-group';
  selectAll.title = 'Select the whole group';

  // block.group is an unvalidated string out of a hand-editable file, and this
  // markup runs with full window.pywebview.api access — textContent, never
  // innerHTML (invariant 5).
  const name = document.createElement('span');
  name.className = 'group-name';
  name.textContent = block.group;
  name.title = 'Click to rename';

  const total = groupMemberCount(project, block.group);
  const count = document.createElement('span');
  count.className = 'group-count';
  count.textContent = total === block.tasks.length
    ? `${total}` : `${block.tasks.length} of ${total}`;

  header.append(caret, selectAll, name, count);
  releaseDragWhileUsing(caret, header);
  releaseDragWhileUsing(selectAll, header);

  if (showBucket) {
    // The group owns the bucket. Moving it moves every member, which is what
    // makes "one group = one Claude session" true rather than aspirational.
    const picker = document.createElement('select');
    picker.className = 'bucket';
    BUCKETS.forEach(bucket => {
      const option = document.createElement('option');
      option.value = bucket;
      option.textContent = bucket;
      option.selected = bucket === block.tasks[0].bucket;
      picker.append(option);
    });
    picker.onchange = async event => {
      if (await callApi('set_group_bucket', project, block.group,
          event.target.value) === API_FAILED) return;
      await refresh();
    };
    header.append(picker);
    releaseDragWhileUsing(picker, header);
  }

  if (showReset) {
    const reset = document.createElement('button');
    reset.className = 'reset';
    reset.textContent = '↩';
    reset.title = 'None of this is actually in progress';
    reset.onclick = async () => {
      if (await callApi('reset_to_open', project,
          block.tasks.map(t => t.id)) === API_FAILED) return;
      await refresh();
    };
    header.append(reset);
    releaseDragWhileUsing(reset, header);
  }

  // Unconditional, not behind an option: rows have `done` in both bucket
  // sections and IN PROGRESS, so headers should too. Between the reset and
  // disband buttons — "change these tasks" actions adjacent, "unmake the
  // group" last.
  const done = document.createElement('button');
  done.className = 'done';
  done.textContent = 'done';
  done.title = 'Mark the whole group done';
  // block.tasks, not the group's full membership — what this header actually
  // drew. In IN PROGRESS a header can read "2 of 5"; done completes those 2
  // and leaves the other 3 in their bucket, same as the ↩ beside it.
  done.onclick = () =>
    completeTasksWithConfirm(project, block.tasks.map(task => task.id));
  header.append(done);
  releaseDragWhileUsing(done, header);

  if (showDisband) {
    // The undo for a mis-drag. Members stay exactly where they are.
    const disband = document.createElement('button');
    disband.className = 'group-disband';
    disband.textContent = '×';
    disband.title = 'Disband this group';
    disband.onclick = async () => {
      if (await callApi('disband_group', project, block.group) === API_FAILED) return;
      // The group is gone, so its fold entry can never match anything again.
      const folded = collapsedView().groups;
      const at = folded.findIndex(
        pair => pair[0] === project && pair[1] === block.group);
      if (at !== -1) { folded.splice(at, 1); await persistCollapsed(); }
      await refresh();
    };
    header.append(disband);
    releaseDragWhileUsing(disband, header);
  }

  const rows = block.tasks.map(task => taskRow(task, {
    showBucket: false, showReset, draggable,
  }));

  // One button to select the whole group, which is what makes spinning up a
  // session from a pre-made group two clicks. The header's own state is
  // derived from the members rather than remembered, so ticking the last row
  // by hand lights it up too.
  selectAll.onchange = () => {
    rows.forEach(row => { row.querySelector('.select').checked = selectAll.checked; });
    // Assigning .checked above does not fire a change event, so the delegated
    // listener in selection.js never sees a whole group being selected —
    // without this the count would silently stay stale.
    renderSelectionBar();
  };
  rows.forEach(row => row.querySelector('.select').addEventListener('change', () => {
    selectAll.checked = rows.every(other => other.querySelector('.select').checked);
  }));

  name.onclick = () => renameInPlace(name, project, block.group);

  // The rows go in even when folded, and CSS hides them. Removing them would
  // break three things that read the DOM: select-the-group would tick nothing,
  // selectedIds() would miss the members, and the drag's id list would hand
  // reorder_bucket a bucket with a hole in it — leaving the folded members on
  // stale order values that collide with the renumbered ones.
  container.append(header, ...rows);
  return container;
}

// Rename where the name already is, rather than in a dialog. Commits on Enter
// or blur; Escape and an empty value both put the old name back. A rejected
// name (callApi has already said why) keeps what was typed and the focus, so
// it can be fixed rather than retyped.
function renameInPlace(nameElement, project, current) {
  // A text box inside draggable="true" cannot be selected with the mouse in
  // Chromium — the drag starts instead. Suspend the header's own draggability
  // for as long as the box is open.
  const header = nameElement.closest('.group-header');
  const restoreDrag = () => { if (header) header.draggable = true; };
  if (header) header.draggable = false;

  const input = document.createElement('input');
  input.className = 'group-name-input';
  input.value = current;
  nameElement.replaceWith(input);
  input.focus();
  input.select();

  let committing = false;
  const commit = async () => {
    if (committing) return;
    const wanted = input.value.trim();
    if (!wanted || wanted === current) {
      input.replaceWith(nameElement);
      restoreDrag();
      return;
    }
    committing = true;
    if (await callApi('rename_group', project, current, wanted) === API_FAILED) {
      committing = false;
      input.focus();
      input.select();
      return;
    }
    // Carry the fold across the rename — the entry is keyed by name, so
    // without this a folded group springs open and reads as the rename having
    // reset something. Persisted before the refresh, which reloads the set.
    const folded = collapsedView().groups.find(
      pair => pair[0] === project && pair[1] === current);
    if (folded) { folded[1] = wanted; await persistCollapsed(); }
    await refresh();
  };

  input.onblur = commit;
  input.onkeydown = event => {
    if (event.key === 'Enter') { event.preventDefault(); input.blur(); }
    if (event.key === 'Escape') {
      input.onblur = null;
      input.replaceWith(nameElement);
      restoreDrag();
    }
  };
}

// --- Dragging: reorder, regroup, recategorise ---------------------------
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
//
// A drop resolves to a DESTINATION — {bucket, group, status} — applied by a
// single place_task/place_group call. Two gestures keep their own names
// because they are not placements: `pair` names a NEW group, and `sort`
// permutes one group's own slots. A refusal is null.
//
// WHERE a drop lands is read from GEOMETRY, not from `event.target`. Every
// section is a box: anywhere inside it means "this category", at the slot
// nearest the cursor. Every group is a nested box inside that one: anywhere
// inside it means "and in this group". Those are the two rectangles a user can
// actually see, so they are the two the rule is written against — an
// element-based rule kept disagreeing with them, because the padding of a box
// belongs to the box on screen and to nothing at all in the DOM.
//
// Reordering is the common gesture and grouping the rare one, so reordering is
// what everything defaults to and grouping has to be AIMED: it needs the
// cursor inside a band a third of a row tall, inset from both ends. This
// replaces an even split — the middle half of a row grouped, the outer
// quarters reordered — which made the rarer, more surprising outcome as easy
// to hit as the common one.
//
// The dragged element is excluded from every measurement. Including it would
// feed the preview back into the geometry that produced it: the live move
// slides the row under the cursor, which is what silently broke the drop
// before (see the note in wireDrag).

function clearDropAffordance(root) {
  root.querySelectorAll('.drop-into, .drop-zone').forEach(
    element => element.classList.remove('drop-into', 'drop-zone'));
}

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
function sectionPlacement(section) {
  const bucket = section.dataset.bucket || null;
  return { bucket, status: bucket ? 'open' : 'in-progress',
           canReorder: Boolean(bucket) };
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
// height, centred, and inset from both ends — "very clearly on top of that
// task" rather than merely nearest to it. Everything outside it reorders.
const PAIR_BAND = 1 / 3;
const PAIR_INSET = 12;

// A group keeps a few pixels of grip on the row already inside it, so that
// sorting within a group and overshooting the last member by a pixel does not
// throw the row out of the group. Leaving is still one deliberate drag clear
// of the box; only the twitch is absorbed.
const GROUP_STICKY = 8;

// The section the cursor is in. A section owns exactly its own rectangle, and
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
function sectionUnder(event) {
  const sections = [...document.querySelectorAll(
    '#task-list section[data-bucket], #task-list #in-progress')];
  if (!sections.length) return null;
  const pointerY = event.clientY;
  const inside = sections.find(candidate => {
    const box = candidate.getBoundingClientRect();
    return pointerY >= box.top && pointerY <= box.bottom;
  });
  if (inside) return inside;
  // Past the end of the list — the empty space below SOMEDAY is a great deal
  // of the window, and it belongs to the last section rather than to nothing.
  const last = sections[sections.length - 1];
  if (pointerY > last.getBoundingClientRect().bottom) return last;
  return sections.find(
    candidate => pointerY < candidate.getBoundingClientRect().top) || last;
}

// The blocks a container orders, minus the one being dragged. A top-level list
// is rows and group containers together — a group occupies one slot, which is
// what keeps its members contiguous (invariant 16).
function blocksIn(container, dragged, selector) {
  return [...container.children].filter(child =>
    child !== dragged && child.matches(selector));
}

// The slot the cursor is nearest: before the first block whose middle is below
// it, or the end. Midpoints rather than edges, so the answer changes as the
// cursor passes the middle of a row and not as it crosses a seam.
//
// Measured as if the dragged block were not in the flow. It IS in the flow —
// HTML5 drag leaves the element where it is, and the preview then moves it —
// so every block after it sits one row lower than it otherwise would. Leave
// that in and the preview decides its own next position: the row lands between
// two slots, displaces the one below it, and the next reading picks the other
// slot, so the list flips between them while the cursor holds still.
function slotFor(blocks, pointerY, dragged) {
  const displaced = dragged ? dragged.getBoundingClientRect().height : 0;
  const at = blocks.findIndex(block => {
    const box = block.getBoundingClientRect();
    const after = dragged
      && (dragged.compareDocumentPosition(block) & Node.DOCUMENT_POSITION_FOLLOWING);
    return pointerY < box.top + box.height / 2 - (after ? displaced : 0);
  });
  return at === -1 ? blocks.length : at;
}

function withinBox(element, event, grow = 0) {
  const box = element.getBoundingClientRect();
  return event.clientX >= box.left - grow && event.clientX <= box.right + grow
    && event.clientY >= box.top - grow && event.clientY <= box.bottom + grow;
}

// The group box the cursor is inside. The dragged row's OWN group is not
// excluded — that is how sorting within a group works — it just gets the extra
// grip.
function groupUnder(section, event, dragged) {
  const mine = groupOf(dragged);
  return [...section.querySelectorAll('.group')].find(container =>
    container !== dragged
    && withinBox(container, event,
                 container.dataset.group === mine ? GROUP_STICKY : 0)) || null;
}

// A loose top-level row the cursor is very clearly on top of — the one gesture
// here that makes a new group, so the one that has to be aimed.
function pairTarget(section, event, dragged, project) {
  return [...section.querySelectorAll('.task')].find(row => {
    if (row === dragged || row.dataset.project !== project) return false;
    if (row.parentElement.classList.contains('group')) return false;
    const box = row.getBoundingClientRect();
    const margin = box.height * (1 - PAIR_BAND) / 2;
    return event.clientY >= box.top + margin && event.clientY <= box.bottom - margin
      && event.clientX >= box.left + PAIR_INSET && event.clientX <= box.right - PAIR_INSET;
  }) || null;
}

function dropIntent(event, dragged, draggedIsGroup) {
  const section = sectionUnder(event);
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
    const target = pairTarget(section, event, dragged, project);
    if (target) return { kind: 'pair', over: target, element: target,
                         status: lands.status, section };
  }

  // 2. Inside a group's box. A group is one level deep, so a dragged group
  // never enters one — it reorders past it at the top level instead.
  const container = draggedIsGroup ? null : groupUnder(section, event, dragged);
  if (container && container.dataset.project === project) {
    const name = container.dataset.group;
    const members = blocksIn(container, dragged, '.task');
    const before = members[slotFor(members, event.clientY, dragged)] || null;
    // IN PROGRESS renders only part of a bucket, so it cannot renumber one.
    // Its members can still trade their own slots, which is what `sort` is.
    if (!lands.canReorder && name === groupOf(dragged)) {
      return { kind: 'sort', preview: { container, before }, into: container,
               section };
    }
    // A bucket section needs no `sort`: it draws the whole bucket, so the
    // ordered id list it hands place_task already positions the member.
    return { kind: 'place', bucket: null, group: name, status: lands.status,
             into: container, section, positioned: lands.canReorder,
             preview: lands.canReorder ? { container, before } : null };
  }

  // 3. Anywhere else in the box: this category, no group, nearest slot. The
  // headings, the padding, the gaps between blocks and the empty line all land
  // here — they are inside the rectangle the user is aiming at, so they behave
  // like it. This is what a grouped row dropped clear of its group's box rides
  // out on, which is why leaving a group needs no target of its own any more.
  if (!lands.canReorder) {
    // IN PROGRESS has no order anyone chose — its rows sort by project and
    // then group — so there is no slot to compute and nothing to preview. The
    // no-op check matters here for the same reason: without a position to
    // change, a loose running row dropped back in its own box means nothing,
    // and an outline would be promising something.
    const claim = placement({ bucket: null, group: null, status: lands.status },
                            dragged, draggedIsGroup);
    return claim && { ...claim, into: section, section };
  }
  const blocks = blocksIn(section, dragged, '.task, .group');
  return { kind: 'place', bucket: lands.bucket, group: null, status: lands.status,
           into: section, section, positioned: true,
           preview: { container: section, before: blocks[slotFor(blocks, event.clientY, dragged)] || null } };
}

function wireDrag() {
  const list = document.getElementById('task-list');
  let dragged = null;
  let draggedIsGroup = false;
  let draggedGroup = null;
  let draggedFrom = null;
  let intent = null;

  list.addEventListener('dragstart', event => {
    const header = event.target.closest('.group-header');
    dragged = header ? header.parentElement : event.target.closest('.task');
    draggedIsGroup = Boolean(header);
    const container = dragged ? dragged.closest('.group') : null;
    draggedGroup = container ? container.dataset.group : null;
    // The container it STARTED in — its group if it is in one, otherwise its
    // section. Read once and now: the preview moves the element, so asking
    // later would answer with wherever the last dragover put it. A dragged
    // group is not inside itself; its container is its section.
    const from = dragged
      ? dragged.closest('section[data-bucket], #in-progress') : null;
    draggedFrom = draggedIsGroup ? from : ((dragged && dragged.closest('.group')) || from);
    intent = null;
  });

  list.addEventListener('dragend', () => {
    clearDropAffordance(list);
    dragged = null;
    intent = null;
  });

  list.addEventListener('dragover', event => {
    event.preventDefault();
    if (!dragged) return;
    clearDropAffordance(list);
    intent = dropIntent(event, dragged, draggedIsGroup);
    if (!intent) return;
    // The live move IS the affordance for a reorder: the row is drawn where it
    // would land, indented into a group's rail or clear of it, which says more
    // than an outline could. `before` is measured with the dragged element
    // excluded, so inserting it cannot change the answer that put it there.
    if (intent.preview) {
      const { container, before } = intent.preview;
      // Only when it actually moves. dragover fires continuously, and an
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
  });

  list.addEventListener('drop', async event => {
    event.preventDefault();
    clearDropAffordance(list);
    const settled = intent;
    const row = dragged;
    const wasInGroup = draggedGroup;
    const wasGroup = draggedIsGroup;
    dragged = null;
    intent = null;
    if (!settled || !row) return;
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
      if (born === API_FAILED) return;
      // A group born in a section the dragged row did not come from has to be
      // placed as well as named — pairing a backlog task onto a running one
      // means both are running now. create_group already put them in the
      // target's bucket, so only the status can still be wrong. Two calls,
      // because naming a group and placing one are two ideas, and a failure
      // between them leaves a valid group that simply was not claimed.
      if (moved && moved.status !== settled.status
          && await callApi('place_group', project, born,
               { status: settled.status }) === API_FAILED) return;
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
      if (!container) return;
      const ids = [...container.querySelectorAll('.task')].map(
        element => Number(element.dataset.id));
      if (await callApi('reorder_group', project,
          container.dataset.group, ids) === API_FAILED) return;
      await refresh();
      return;
    }

    const destination = { bucket: settled.bucket, group: settled.group,
                          status: settled.status };
    // Read AFTER the live move, so the ids say what the user is looking at.
    // Members stay contiguous because a group's rows live inside its own
    // container, and folded rows are still in there (invariant 18) so the list
    // has no hole in it. Null for a section that cannot renumber a bucket.
    const ids = settled.positioned
      ? [...settled.section.querySelectorAll('.task')].map(
          element => Number(element.dataset.id))
      : null;
    const outcome = wasGroup
      ? await callApi('place_group', project, name, destination, ids)
      : await callApi('place_task', project, Number(row.dataset.id),
                      destination, ids);
    if (outcome === API_FAILED) return;
    // Before the refresh, while state.tasks still counts the member on its way
    // out — a group that just lost its last one does not exist any more, and
    // nothing would ever unfold its leftover entry.
    if (!wasGroup && settled.group !== wasInGroup) {
      await forgetFoldIfEmptied(project, wasInGroup);
    }
    await refresh();
  });
}

// Bound once, at load. Inside a render function this would stack a duplicate
// listener on every redraw; #task-list outlives all of them.
wireDrag();

// Open a freshly created group's name box, seeded and selected so the real
// name can be typed straight over it. Called only when a group is BORN, never
// when a task joins one — a suggested value is written once, into an untouched
// box (CLAUDE.md invariant 11).
function focusGroupName(project, name) {
  const container = [...document.querySelectorAll('.group')].find(
    element => element.dataset.project === project && element.dataset.group === name);
  if (container) container.querySelector('.group-name').click();
}
