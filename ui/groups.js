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
// refresh, while state.tasks still counts the member on its way out.
async function forgetFoldIfEmptied(project, name) {
  if (!name || groupMemberCount(project, name) > 1) return;
  const folded = collapsedView().groups;
  const at = folded.findIndex(pair => pair[0] === project && pair[1] === name);
  if (at === -1) return;
  folded.splice(at, 1);
  await persistCollapsed();
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

// --- Dragging: reorder, form a group, join one, leave one ---------------
//
// Three zones instead of one. Over a top-level loose row, the middle half
// means "group these two" and the outer quarters mean "reorder". Inside a
// group's container — its header or between its child rows — every position
// means "join this group", because a drop between two children would otherwise
// write an order that interleaves a non-member into the group's contiguous run
// and the next renumber would silently eject it below the block.
//
// A reorder moves the DOM live and reads the result back on drop, so where a
// row LANDED is what decides its group: dropped inside a container it joins,
// dropped in a top-level gap it leaves. The two "onto" gestures move nothing —
// the backend places the task and refresh() redraws.

function clearDropAffordance(section) {
  // The section itself can carry the affordance — querySelectorAll never
  // returns the element it was called on, so clear it separately.
  section.classList.remove('drop-into', 'drop-loose');
  section.querySelectorAll('.drop-into, .drop-loose').forEach(
    element => element.classList.remove('drop-into', 'drop-loose'));
}

// Drop a grouped row on a HEADING — the bucket's name, or the project's name
// in IN PROGRESS — and it comes out of its group. One target, one meaning:
// "belongs to this list, to no group".
//
// The heading rather than the whole region, because the region is crossed by
// accident. A reorder drag passes through the gaps between blocks constantly,
// and there `event.target` is the section itself; releasing in one of those
// would have quietly dissolved the grouping the user was rearranging. A
// heading has to be aimed at.
//
// This is the only way out of the IN PROGRESS section, which has no reorder
// gaps at all, and the only way out of a bucket whose sole contents ARE the
// group — there is no top-level gap to drop into there either, so before this
// its members could not be separated by drag at all.
function leaveIntent(event, dragged, draggedIsGroup) {
  if (draggedIsGroup || !groupOf(dragged)) return null;

  const projectHeading = event.target.closest('.project-heading');
  if (projectHeading) {
    return projectHeading.parentElement.dataset.project === dragged.dataset.project
      ? { kind: 'leave', element: projectHeading } : null;
  }
  // A bucket section is single-project, so its own heading needs no check.
  const bucketHeading = event.target.closest('section[data-bucket] > h2');
  return bucketHeading ? { kind: 'leave', element: bucketHeading } : null;
}

function groupOf(element) {
  const container = element.closest('.group');
  return container ? container.dataset.group : null;
}

function dropIntent(event, dragged, draggedIsGroup, allowReorder) {
  const header = event.target.closest('.group-header');
  if (header && header.parentElement !== dragged) {
    // Dropping a group onto a group does not merge them: a group IS its name,
    // so merging silently destroys one of the two names.
    if (draggedIsGroup) return null;
    if (header.parentElement.dataset.project !== dragged.dataset.project) return null;
    // Already a member — rejoining would only shunt it to the end of its own
    // group, which is not what aiming at that header meant.
    if (header.parentElement.dataset.group === groupOf(dragged)) return null;
    return { kind: 'join', group: header.parentElement.dataset.group, element: header };
  }

  const over = event.target.closest('.task');
  // One project at a time, in every context. Task ids are per-project and so
  // is a group name, so a cross-project drop has nothing coherent to mean.
  if (!over || over === dragged || dragged.contains(over)
      || over.dataset.project !== dragged.dataset.project) {
    return leaveIntent(event, dragged, draggedIsGroup);
  }

  const inGroup = over.parentElement.classList.contains('group')
    ? over.parentElement.dataset.group : null;
  // A group is one level deep. Never let a container land inside another.
  if (draggedIsGroup && inGroup) return null;

  const box = over.getBoundingClientRect();
  const offset = (event.clientY - box.top) / box.height;
  if (!draggedIsGroup && !inGroup && offset > 0.25 && offset < 0.75) {
    return { kind: 'pair', over, element: over };
  }

  // Outside a bucket section there is no position to drop into: the IN
  // PROGRESS list is ordered by project and then by group, not by anything
  // the user chose, and its rows can sit in three different buckets — so
  // there is no single bucket for reorder_bucket to renumber. Drag there only
  // ever groups. Leaving a group is the editor's Group → none.
  if (!allowReorder) {
    // Over a loose row's edge: nothing to reorder, since this list's order is
    // by project and group rather than anything anyone chose. Leaving a group
    // is the project heading.
    if (!inGroup) return null;
    // Inside one group there IS a position to drop into. Its members share a
    // bucket and sit contiguously (invariant 16), so they can trade their own
    // slots without touching the rest of that bucket — which is the only
    // reason a section rendering part of a bucket can reorder anything at all.
    if (inGroup === groupOf(dragged)) return { kind: 'sort', over, after: offset > 0.5 };
    return { kind: 'join', group: inGroup, element: over };
  }
  return { kind: 'move', over, after: offset > 0.5 };
}

// `bucket` names the bucket this section reorders within, or null for a
// section that has no single one — see dropIntent, where null means "drag only
// ever groups here".
function wireDrag(section, bucket) {
  const allowReorder = bucket !== null;
  let dragged = null;
  let draggedIsGroup = false;
  let draggedGroup = null;
  let intent = null;

  section.addEventListener('dragstart', event => {
    const header = event.target.closest('.group-header');
    dragged = header ? header.parentElement : event.target.closest('.task');
    draggedIsGroup = Boolean(header);
    const container = dragged ? dragged.closest('.group') : null;
    draggedGroup = container ? container.dataset.group : null;
    intent = null;
  });

  section.addEventListener('dragend', () => {
    clearDropAffordance(section);
    dragged = null;
    intent = null;
  });

  section.addEventListener('dragover', event => {
    event.preventDefault();
    if (!dragged) return;
    clearDropAffordance(section);
    intent = dropIntent(event, dragged, draggedIsGroup, allowReorder);
    if (!intent) return;
    if (intent.kind === 'move' || intent.kind === 'sort') {
      intent.over.parentElement.insertBefore(
        dragged, intent.after ? intent.over.nextSibling : intent.over);
    } else {
      // Two outcomes, two looks: solid means "this will group", dashed means
      // "this will come loose". One outline for both would make the gesture
      // that dissolves a grouping look like the one that makes it.
      intent.element.classList.add(
        intent.kind === 'leave' ? 'drop-loose' : 'drop-into');
    }
  });

  section.addEventListener('drop', async event => {
    event.preventDefault();
    clearDropAffordance(section);
    const settled = intent;
    const row = dragged;
    const wasInGroup = draggedGroup;
    const wasGroup = draggedIsGroup;
    dragged = null;
    intent = null;
    if (!settled || !row) return;
    // The row's OWN project, never currentProject. In a bucket section the two
    // are the same; in IN PROGRESS, which spans projects, they are not — and
    // dropIntent has already refused any pairing across two of them.
    const project = row.dataset.project;

    if (settled.kind === 'pair') {
      // The target's title seeds the name, and the target comes first so the
      // new block sits where it already was. Read the title from state rather
      // than the row, which may carry display decoration.
      const targetId = Number(settled.over.dataset.id);
      const target = state.tasks.find(
        task => task.project === project && task.id === targetId);
      const name = await callApi('create_group', project,
        [targetId, Number(row.dataset.id)], target ? target.title : 'New group');
      if (name === API_FAILED) return;
      await refresh();
      // Only on birth. A task joining an existing group must not reopen it —
      // that name is an identity by then, not a suggestion.
      focusGroupName(project, name);
      return;
    }

    if (settled.kind === 'join') {
      if (await callApi('group_tasks', project,
          [Number(row.dataset.id)], settled.group) === API_FAILED) return;
      await refresh();
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

    if (settled.kind === 'leave') {
      if (await callApi('ungroup_tasks', project,
          [Number(row.dataset.id)]) === API_FAILED) return;
      await forgetFoldIfEmptied(project, wasInGroup);
      await refresh();
      return;
    }

    // A reorder. Where the row landed decides what it belongs to.
    if (!wasGroup) {
      const container = row.closest('.group');
      const landed = container ? container.dataset.group : null;
      if (landed !== wasInGroup) {
        const outcome = landed === null
          ? await callApi('ungroup_tasks', project, [Number(row.dataset.id)])
          : await callApi('group_tasks', project, [Number(row.dataset.id)], landed);
        if (outcome === API_FAILED) return;
        await forgetFoldIfEmptied(project, wasInGroup);
      }
    }
    // Last writer, and rightly so: the DOM is what the user just saw. Members
    // stay contiguous because a group's rows live inside its own container.
    const ids = [...section.querySelectorAll('.task')].map(el => Number(el.dataset.id));
    if (await callApi('reorder_bucket', project, bucket, ids) === API_FAILED) return;
    await refresh();
  });
}

// Open a freshly created group's name box, seeded and selected so the real
// name can be typed straight over it. Called only when a group is BORN, never
// when a task joins one — a suggested value is written once, into an untouched
// box (CLAUDE.md invariant 11).
function focusGroupName(project, name) {
  const container = [...document.querySelectorAll('.group')].find(
    element => element.dataset.project === project && element.dataset.group === name);
  if (container) container.querySelector('.group-name').click();
}
