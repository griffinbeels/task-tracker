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

// A <select> or button inside draggable="true" can start a drag instead of
// doing its own job in Chromium — the dropdown never opens and nothing says
// why. Suspend the header's draggability while the pointer is on the control.
function releaseDragWhileUsing(control, header) {
  control.addEventListener('mousedown', () => { header.draggable = false; });
  control.addEventListener('mouseup', () => { header.draggable = true; });
  control.addEventListener('mouseleave', () => { header.draggable = true; });
}

function groupBlock(block, options = {}) {
  const { showBucket = true, showDisband = true, showReset = false,
          draggable = true } = options;
  const project = block.tasks[0].project;

  const container = document.createElement('div');
  container.className = 'group';
  container.dataset.group = block.group;
  container.dataset.project = project;

  const header = document.createElement('div');
  header.className = 'group-header';
  header.draggable = draggable;

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

  header.append(selectAll, name, count);
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
  };
  rows.forEach(row => row.querySelector('.select').addEventListener('change', () => {
    selectAll.checked = rows.every(other => other.querySelector('.select').checked);
  }));

  name.onclick = () => renameInPlace(name, project, block.group);

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
  section.querySelectorAll('.drop-into').forEach(
    element => element.classList.remove('drop-into'));
}

function dropIntent(event, dragged, draggedIsGroup) {
  const header = event.target.closest('.group-header');
  if (header && header.parentElement !== dragged) {
    // Dropping a group onto a group does not merge them: a group IS its name,
    // so merging silently destroys one of the two names.
    if (draggedIsGroup) return null;
    return { kind: 'join', group: header.parentElement.dataset.group, element: header };
  }

  const over = event.target.closest('.task');
  if (!over || over === dragged || dragged.contains(over)) return null;

  const inGroup = over.parentElement.classList.contains('group')
    ? over.parentElement.dataset.group : null;
  // A group is one level deep. Never let a container land inside another.
  if (draggedIsGroup && inGroup) return null;

  const box = over.getBoundingClientRect();
  const offset = (event.clientY - box.top) / box.height;
  if (!draggedIsGroup && !inGroup && offset > 0.25 && offset < 0.75) {
    return { kind: 'pair', over, element: over };
  }
  return { kind: 'move', over, after: offset > 0.5 };
}

function wireDrag(section, bucket) {
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
    intent = dropIntent(event, dragged, draggedIsGroup);
    if (!intent) return;
    if (intent.kind === 'move') {
      intent.over.parentElement.insertBefore(
        dragged, intent.after ? intent.over.nextSibling : intent.over);
    } else {
      intent.element.classList.add('drop-into');
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

    if (settled.kind === 'pair') {
      // The target's title seeds the name, and the target comes first so the
      // new block sits where it already was. Read the title from state rather
      // than the row, which may carry display decoration.
      const targetId = Number(settled.over.dataset.id);
      const target = state.tasks.find(
        task => task.project === currentProject && task.id === targetId);
      const name = await callApi('create_group', currentProject,
        [targetId, Number(row.dataset.id)], target ? target.title : 'New group');
      if (name === API_FAILED) return;
      await refresh();
      // Only on birth. A task joining an existing group must not reopen it —
      // that name is an identity by then, not a suggestion.
      focusGroupName(currentProject, name);
      return;
    }

    if (settled.kind === 'join') {
      if (await callApi('group_tasks', currentProject,
          [Number(row.dataset.id)], settled.group) === API_FAILED) return;
      await refresh();
      return;
    }

    // A reorder. Where the row landed decides what it belongs to.
    if (!wasGroup) {
      const container = row.closest('.group');
      const landed = container ? container.dataset.group : null;
      if (landed !== wasInGroup) {
        const outcome = landed === null
          ? await callApi('ungroup_tasks', currentProject, [Number(row.dataset.id)])
          : await callApi('group_tasks', currentProject, [Number(row.dataset.id)], landed);
        if (outcome === API_FAILED) return;
      }
    }
    // Last writer, and rightly so: the DOM is what the user just saw. Members
    // stay contiguous because a group's rows live inside its own container.
    const ids = [...section.querySelectorAll('.task')].map(el => Number(el.dataset.id));
    if (await callApi('reorder_bucket', currentProject, bucket, ids) === API_FAILED) return;
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
