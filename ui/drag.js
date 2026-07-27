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
  // Where the preview picked the block up from. The live move in `dragover` is
  // a REAL DOM move, and nothing else ever undoes it — so a gesture that wrote
  // nothing used to leave the list showing a position that was never saved,
  // for as long as it took something else to force a render. The next rename,
  // edit or fold then put the row back, which reads as that unrelated edit
  // having reset the task's position. Nothing on screen may claim a place that
  // was not written.
  let startedAt = null;
  // Set the instant `drop` commits to acting. `dragend` fires immediately after
  // drop's synchronous part (and on its own when there was no drop at all —
  // released outside the list, or cancelled with Escape), so this flag is the
  // only thing that can tell those two endings apart from inside dragend.
  let wrote = false;

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

  list.addEventListener('dragstart', event => {
    const header = event.target.closest('.group-header');
    dragged = header ? header.parentElement : event.target.closest('.task');
    draggedIsGroup = Boolean(header);
    startedAt = dragged
      ? { element: dragged, parent: dragged.parentElement,
          before: dragged.nextSibling }
      : null;
    wrote = false;
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
    // The only signal a drag that never reached `drop` gives at all: released
    // outside #task-list — the header, the selection bar, past the window edge
    // — or cancelled with Escape. Nothing was written, so nothing may be left
    // looking moved.
    if (!wrote) undoPreview();
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
    // The destination refused this drop — a cross-project one, or a claim that
    // would change nothing. The preview moved the block for real on the way
    // here, so take it back: a refusal that leaves the row sitting where it was
    // never written is indistinguishable from a drop that worked.
    if (!settled || !row) { undoPreview(); return; }
    wrote = true;
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
      // wrong, but the preview has moved the row and dragend has already run
      // and declined to undo it (this path claimed the drop), so the list is
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
    // Read after the call above, deliberately: dragend has already fired by
    // now, and it leaves the preview alone once the drop has claimed it (see
    // `wrote`), so the DOM here still says where the user let go.
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
  });
}

// Bound once, at load. Inside a render function this would stack a duplicate
// listener on every redraw; #task-list outlives all of them.
wireDrag();
