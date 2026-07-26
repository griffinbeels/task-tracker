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
// Three zones over a row, unchanged: the middle half means "group these two",
// the outer quarters mean "reorder". Inside a group's container every position
// means "join this group", because a drop between two children would write an
// order interleaving a non-member into the group's contiguous run and the next
// renumber would silently eject it below the block.

function clearDropAffordance(root) {
  root.querySelectorAll('.drop-into, .drop-loose').forEach(
    element => element.classList.remove('drop-into', 'drop-loose'));
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
// a NOW member of group G be dropped on G's header inside IN PROGRESS — that
// claims it — while the same drop in its own section stays a no-op.
function placement(destination, dragged, isGroup, element) {
  const current = draggedState(dragged, isGroup);
  if (!current) return null;
  // A group drag never changes membership, so the destination's `group` is
  // not about it — place_group fills in the name. Comparing the two would
  // read every group drag as "become loose" and so never as a no-op, which
  // would light up the heading of the bucket the group is already in.
  const settled = (isGroup || destination.group === current.group)
    && destination.status === current.status
    && (destination.bucket === null || destination.bucket === current.bucket);
  return settled ? null : { kind: 'place', ...destination, element };
}

function dropIntent(event, dragged, draggedIsGroup) {
  const section = event.target.closest('section[data-bucket], #in-progress');
  if (!section) return null;
  const lands = sectionPlacement(section);
  const project = dragged.dataset.project;

  // The WHOLE IN PROGRESS box, not just its heading. It is drawn as a bordered
  // box with an invitation written inside it, so it has to behave like one —
  // the dead strip beside the heading and around the line was exactly the
  // "nothing happened" the box's own text promises against. The affordance is
  // the box itself for the same reason: a drop zone lights up as a zone.
  //
  // Bucket sections deliberately do NOT do this. A reorder drag crosses their
  // gaps constantly and there event.target is the section itself, so releasing
  // in one would quietly dissolve the grouping being rearranged. IN PROGRESS
  // has no top-level reorder at all, so it has no such gaps to cross.
  //
  // Only for something not already running, though. A running row inside a
  // group would otherwise be dissolved out of it by overshooting the last row
  // while sorting within it — a few pixels of padding away — and the project
  // heading is the aimable target for that on purpose.
  const wholeBox = () => {
    if (lands.canReorder) return null;
    const current = draggedState(dragged, draggedIsGroup);
    if (!current || current.status === 'in-progress') return null;
    return placement({ bucket: null, group: null, status: 'in-progress' },
                     dragged, draggedIsGroup, section);
  };

  // A bucket's heading: one target, one meaning — "belongs to this list, to no
  // group". The heading rather than the region, for the gaps reason above.
  const sectionTarget = event.target.closest('section > h2, .wip-empty');
  if (sectionTarget && sectionTarget.parentElement === section) {
    if (!lands.bucket) return wholeBox();
    // A bucket section shows one project, so it must match.
    if (section.dataset.project !== project) return null;
    return placement({ bucket: lands.bucket, group: null, status: lands.status },
                     dragged, draggedIsGroup, sectionTarget);
  }

  const projectHeading = event.target.closest('.project-heading');
  if (projectHeading) {
    if (projectHeading.parentElement.dataset.project !== project) return null;
    return placement({ bucket: lands.bucket, group: null, status: lands.status },
                     dragged, draggedIsGroup, projectHeading);
  }

  const header = event.target.closest('.group-header');
  if (header && header.parentElement !== dragged) {
    // Dropping a group onto a group does not merge them: a group IS its name,
    // so merging silently destroys one of the two names.
    if (draggedIsGroup) return null;
    if (header.parentElement.dataset.project !== project) return null;
    // No bucket named here: the group owns its own (invariant 16), so joining
    // is what sets it. That is what moves a someday task into now when it is
    // dropped onto a group living there.
    return placement({ bucket: null, group: header.parentElement.dataset.group,
                       status: lands.status }, dragged, draggedIsGroup, header);
  }

  const over = event.target.closest('.task');

  // Over the row being dragged — which is where the pointer ends up as soon as
  // the live move slides it under the cursor, and it is the whole of the "it
  // moved on screen and nothing was saved" bug. Returning null here left
  // `intent` empty at release, so `drop` returned before calling anything: the
  // DOM showed the row in its new section and the next render put it back,
  // because nothing had been written. There IS a destination — the row is
  // already sitting in it — so commit where it sits. `over` is deliberately
  // absent: there is nothing to insert relative to, only a position to keep.
  if (over && (over === dragged || dragged.contains(over))) {
    return lands.canReorder ? { kind: 'move', section } : wholeBox();
  }

  // One project at a time, in every context. Task ids are per-project and so
  // is a group name, so a cross-project drop has nothing coherent to mean.
  if (!over || over.dataset.project !== project) return wholeBox();

  const inGroup = over.parentElement.classList.contains('group')
    ? over.parentElement.dataset.group : null;
  // A group is one level deep. Never let a container land inside another.
  if (draggedIsGroup && inGroup) return null;

  const box = over.getBoundingClientRect();
  const offset = (event.clientY - box.top) / box.height;
  if (!draggedIsGroup && !inGroup && offset > 0.25 && offset < 0.75) {
    return { kind: 'pair', over, element: over, status: lands.status };
  }

  if (!lands.canReorder) {
    // IN PROGRESS. A loose row's edge has nothing to reorder — this list's
    // order is by project and group rather than anything anyone chose — so it
    // falls back to the box, like every other part of it that is not a row of
    // its own.
    if (!inGroup) return wholeBox();
    // Inside one group there IS a position to drop into. Its members share a
    // bucket and sit contiguously (invariant 16), so they can trade their own
    // slots without touching the rest of that bucket — which is the only
    // reason a section rendering part of a bucket can reorder anything.
    if (inGroup === groupOf(dragged)) return { kind: 'sort', over, after: offset > 0.5 };
    return placement({ bucket: null, group: inGroup, status: lands.status },
                     dragged, draggedIsGroup, over);
  }
  // A reorder. The row moves live and where it LANDED decides what it belongs
  // to — inside a container it joins, in a top-level gap it comes loose — so
  // no group is named here. The section is carried because the drop needs its
  // bucket and its id list, and by then the pointer may have left it.
  return { kind: 'move', over, after: offset > 0.5, section };
}

function wireDrag() {
  const list = document.getElementById('task-list');
  let dragged = null;
  let draggedIsGroup = false;
  let draggedGroup = null;
  let intent = null;

  list.addEventListener('dragstart', event => {
    const header = event.target.closest('.group-header');
    dragged = header ? header.parentElement : event.target.closest('.task');
    draggedIsGroup = Boolean(header);
    const container = dragged ? dragged.closest('.group') : null;
    draggedGroup = container ? container.dataset.group : null;
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
    if (intent.kind === 'move' || intent.kind === 'sort') {
      // No `over` means the pointer is on the dragged row itself: it is
      // already where it is going, so there is nothing to insert it against
      // and no affordance to draw — the row under the cursor IS the preview.
      if (intent.over) {
        intent.over.parentElement.insertBefore(
          dragged, intent.after ? intent.over.nextSibling : intent.over);
      }
    } else {
      // Two outcomes, two looks: solid means "becomes part of this", dashed
      // means "comes loose from what it was in". One outline for both would
      // make the gesture that dissolves a grouping look like the one that
      // makes it. Being claimed into IN PROGRESS is joining the running
      // region, so it is solid; being dropped back into a bucket is leaving
      // it, so it is dashed. A status change is not a third kind of outcome —
      // it is these same two, seen from the region that gained or lost a row.
      const joins = intent.kind === 'pair' || intent.group !== null
        || intent.status === 'in-progress';
      intent.element.classList.add(joins ? 'drop-into' : 'drop-loose');
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

    if (settled.kind === 'place') {
      const destination = { bucket: settled.bucket, group: settled.group,
                            status: settled.status };
      const outcome = wasGroup
        ? await callApi('place_group', project, name, destination)
        : await callApi('place_task', project, Number(row.dataset.id), destination);
      if (outcome === API_FAILED) return;
      // Before the refresh, while state.tasks still counts the member on its
      // way out — a group that just lost its last one does not exist any more,
      // and nothing would ever unfold its leftover entry.
      if (!wasGroup && settled.group !== wasInGroup) {
        await forgetFoldIfEmptied(project, wasInGroup);
      }
      await refresh();
      return;
    }

    // A reorder. Where the row landed decides what it belongs to, and which
    // section it landed in decides its bucket and its status — that is the
    // whole of dragging between now/next/someday. The DOM is the last writer
    // and rightly so: it is what the user just saw. Members stay contiguous
    // because a group's rows live inside its own container, and folded rows
    // are still in there (invariant 18) so the list has no hole in it.
    const lands = sectionPlacement(settled.section);
    const landed = wasGroup ? null : groupOf(row);
    const ids = [...settled.section.querySelectorAll('.task')].map(
      element => Number(element.dataset.id));
    const outcome = wasGroup
      ? await callApi('place_group', project, name,
          { bucket: lands.bucket, status: lands.status }, ids)
      : await callApi('place_task', project, Number(row.dataset.id),
          { bucket: lands.bucket, group: landed, status: lands.status }, ids);
    if (outcome === API_FAILED) return;
    if (!wasGroup && landed !== wasInGroup) {
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
