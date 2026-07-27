// Group blocks — the one indented container, its header, and folding. A group is
// its name (see groups.py), so nothing here holds an id: a block is simply the
// tasks whose `group` strings match.
//
// The drag that forms and dissolves them used to live here too, and was 571 of
// this file's 951 lines. It is drag.js (the gesture) and drag-geometry.js (where
// a drop lands) now. What stays is what a group IS.
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
  // Restore what the header WAS, not `true`. Every header is draggable today,
  // so the two agree — but they did not when IN PROGRESS could not reorder,
  // and a hard `true` would have handed that section's headers a grab cursor
  // and a drag ghost for a gesture that could never do anything. Reading the
  // old value costs nothing and cannot go stale the way a constant can.
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
  name.title = 'Double-click to rename';

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

  // The same control every row below carries, in the same place in the row —
  // right after the bucket picker — aimed at the block this header drew.
  // block.tasks and not the group's full membership, exactly like the `done`
  // further along: a header in IN PROGRESS can read "2 of 5", and those other
  // 3 are sitting in a bucket rather than in this session.
  //
  // Through aimedAt for the same reason `done` goes through
  // completeWithSelection (invariant 31): with the whole group ticked the
  // click is aimed at the selection, so the group launches together with
  // whatever else is ticked beside it. CLAUDE_ICON is static markup with no
  // user-authored text in it, which is what makes innerHTML safe here
  // (invariant 5) — block.group, one element along, is not, and is set as
  // textContent for exactly that reason.
  const claude = document.createElement('button');
  claude.className = 'claude';
  claude.title = 'Spin up Claude on this group';
  claude.innerHTML = CLAUDE_ICON;
  claude.onclick = async () => {
    const aimed = aimedAt(project, block.tasks.map(task => task.id));
    if (!aimed) return;
    await handOff(aimed.project, aimed.ids, aimed.fromSelection);
  };
  header.append(claude);
  releaseDragWhileUsing(claude, header);

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
  //
  // Through completeWithSelection, so a header whose rows are all ticked
  // finishes the rest of the selection with them rather than stopping at its
  // own block — the same rule a task row's `done` follows, written once.
  done.onclick = () =>
    completeWithSelection(project, block.tasks.map(task => task.id));
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

  // Double-click, not click. A group header is a drag handle first — moving a
  // group between priorities is the frequent gesture and renaming one is rare
  // — and a single click that opens an editor makes the whole header hostile
  // to the thing it is mostly for. Same reasoning as the drag rules next door:
  // the common gesture is the default, the rare one is aimed.
  name.ondblclick = () => renameInPlace(name, project, block.group);

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

// Open a freshly created group's name box, seeded and selected so the real
// name can be typed straight over it. Called only when a group is BORN, never
// when a task joins one — a suggested value is written once, into an untouched
// box (CLAUDE.md invariant 11).
function focusGroupName(project, name) {
  const container = [...document.querySelectorAll('.group')].find(
    element => element.dataset.project === project && element.dataset.group === name);
  // Calls the thing directly rather than synthesising the gesture that reaches
  // it. This used to fire .click(), which stopped opening anything the moment
  // renaming moved to double-click — and it would have failed silently, since
  // a click on the name is now simply not an event anyone listens for.
  if (container) renameInPlace(container.querySelector('.group-name'), project, name);
}
