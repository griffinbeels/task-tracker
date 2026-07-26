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

  container.append(header, ...rows);
  return container;
}

// Rename where the name already is, rather than in a dialog. Commits on Enter
// or blur; Escape and an empty value both put the old name back. A rejected
// name (callApi has already said why) keeps what was typed and the focus, so
// it can be fixed rather than retyped.
function renameInPlace(nameElement, project, current) {
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
    if (!wanted || wanted === current) { input.replaceWith(nameElement); return; }
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
    if (event.key === 'Escape') { input.onblur = null; input.replaceWith(nameElement); }
  };
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
