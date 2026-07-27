// The classic two-overlapping-sheets copy glyph, and the check it becomes for
// a moment after a successful copy. Both are static markup with no
// user-authored text anywhere in them, which is why setting them via innerHTML
// does not fall foul of invariant 5.
const COPY_ICON = `
  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
       stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <rect x="9" y="9" width="13" height="13" rx="2"></rect>
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
  </svg>`;
const COPIED_ICON = `
  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor"
       stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
    <polyline points="20 6 9 17 4 12"></polyline>
  </svg>`;
// The Claude character, measured off the source art rather than traced by eye:
// a 16x16 pixel grid, so at a 16px render every unit is exactly one CSS pixel
// and no edge lands mid-pixel. The silhouette is one closed outline — body,
// arm band and four legs traced as a single subpath, because two adjacent
// subpaths sharing an edge can leave an anti-aliasing seam — and the two eyes
// are separate subpaths that become holes under fill-rule="evenodd".
//
// Inline SVG rather than a bitmap for two reasons: it is static markup with no
// user-authored text in it, exactly like the two icons above, so innerHTML is
// safe here (invariant 5); and it has to stay sharp under the zoom feature,
// which a PNG would not.
const CLAUDE_ICON = `
  <svg viewBox="0 0 16 16" width="16" height="16" fill="currentColor">
    <path fill-rule="evenodd" d="M2 3H14V7H16V9H14V11H13V13H12V11H11V13H10V11H6V13H5V11H4V13H3V11H2V9H0V7H2Z
                                 M4 5H5V7H4Z M11 5H12V7H11Z"></path>
  </svg>`;

// Open only: an in-progress task lives in the IN PROGRESS section instead, and
// keeps its bucket untouched the whole time so it lands back where it came
// from when the session turns out not to have been real work after all.
// Without this filter every running task renders twice.
function tasksFor(project, bucket) {
  return state.tasks
    .filter(t => t.project === project && t.bucket === bucket && t.status === 'open')
    .sort((a, b) => a.order - b.order);
}

// options tune the row for the three places it appears. A grouped row has no
// bucket picker because its group header owns the bucket — a member that could
// drift into another bucket on its own would render in two places at once.
// showReset adds the "not actually in progress" control, which only means
// anything in the IN PROGRESS section.
function taskRow(task, options = {}) {
  const { showBucket = true, showReset = false, draggable = true } = options;
  const row = document.createElement('div');
  row.className = 'task';
  row.draggable = draggable;
  row.dataset.id = task.id;
  row.dataset.project = task.project;
  row.innerHTML = `
    <input type="checkbox" class="select">
    <span class="dot"></span>
    <span class="type"></span>
    <span class="title"></span>
    <button class="claude" title="Spin up Claude">${CLAUDE_ICON}</button>
    <button class="copy" title="Copy the task's file path">${COPY_ICON}</button>
    <button class="done" title="Mark done">done</button>`;
  // task.title and task.type are user-authored free text (store.py's Task.type
  // is a plain str with no validation) that can contain <, &, or quotes —
  // setting them via innerHTML would corrupt the markup, so set them as text
  // content on the already-built elements instead. The type's background
  // color is likewise unvalidated user text (registry.TaskType.color) — set
  // via .style.background rather than interpolated into the innerHTML above,
  // which would let it escape into markup with full pywebview.api access. The
  // dot's background is task.color, which is backend-validated rather than
  // free text, but it gets the same treatment for the same reason: nothing
  // derived from a hand-editable file goes into the template string.
  row.querySelector('.dot').style.background = colorHex(task.color);
  const typeTag = row.querySelector('.type');
  typeTag.style.background = typeColor(task.type);
  typeTag.textContent = task.type;
  const titleElement = row.querySelector('.title');
  titleElement.textContent = task.title;
  titleElement.title = 'Double-click to rename';
  titleElement.ondblclick = event => {
    event.stopPropagation();
    renameTaskInPlace(titleElement, task);
  };

  // Clicking the row opens it for editing. The row already contains a
  // checkbox, a bucket select and a done button, each with its own click
  // behaviour — event.target is the control itself when one of those is
  // clicked, so the closest() guard below must run first or ticking the
  // checkbox would also pop the editor open. Assigned via .onclick (not
  // addEventListener) so renderSearch/renderAllProjects can remove it with
  // a single `row.onclick = null` — see the comment where they disable
  // .select for why those two views must not open the editor at all.
  row.onclick = event => {
    if (event.target.closest('input, select, button')) return;
    // The title text is the rename target, so a click on it is not an "open".
    // Single-click-to-open and double-click-to-rename cannot share an element:
    // a double click fires two clicks first, so the editor would already be
    // open — over the row — by the time the second one arrived. Splitting the
    // two targets is what avoids that, and it needs no timer, so opening a
    // task stays instant. The title is sized to its own text (see .title in
    // style.css), so the space after a short one still opens the task, as do
    // the dot, the type tag and the rest of the row.
    if (event.target.closest('.title')) return;
    openEditor({
      mode: 'edit',
      taskId: task.id,
      project: task.project,
      title: task.title,
      body: task.body,
      type: task.type,
      bucket: task.bucket,
      // Carried so the editor can say that edits to a running task are
      // bookkeeping, and can offer the group as something to change.
      status: task.status,
      group: task.group,
      // Without this every edit re-suggests a colour and silently recolours
      // the task on save.
      color: task.color,
    });
  };

  if (showBucket) {
    const bucketPicker = document.createElement('select');
    bucketPicker.className = 'bucket';
    BUCKETS.forEach(name => {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      option.selected = name === task.bucket;
      bucketPicker.append(option);
    });
    bucketPicker.onchange = async event => {
      const target = event.target.value;
      // Land it at the end of the target bucket rather than keeping an order
      // that means nothing there.
      const order = state.tasks.filter(
        t => t.project === task.project && t.bucket === target && t.status !== 'done').length;
      if (await callApi('update_task', task.project, task.id,
          { bucket: target, order }) === API_FAILED) return;
      await refresh();
    };
    // Before the Claude button, which is the first of the three action
    // controls: start, copy, finish, left to right.
    row.querySelector('.claude').before(bucketPicker);
  }

  if (showReset) {
    // Retracting "in progress" is the way out of a session you abandoned.
    // Hover-revealed with opacity, never display, so the title beside it does
    // not shift sideways when the pointer arrives.
    const reset = document.createElement('button');
    reset.className = 'reset';
    reset.textContent = '↩';
    reset.title = 'Not actually in progress';
    reset.onclick = async () => {
      if (await callApi('reset_to_open', task.project, [task.id]) === API_FAILED) return;
      await refresh();
    };
    row.querySelector('.done').before(reset);
  }

  // Where the task lives: exactly what "Spin up Claude" would send, built by
  // the same backend function so the two cannot drift apart. A path rather than
  // the prose, because whatever reads it can open the file and get the markdown
  // as written (invariant 2). It takes task.project rather than currentProject,
  // so unlike selection and editing it stays correct in the search and
  // all-projects views, where a row can belong to any project (invariant 6).
  // Nothing is written — copying is not a commitment to start the task.
  const copyButton = row.querySelector('.copy');
  let revertIcon = null;
  copyButton.onclick = async () => {
    if (await callApi('copy_task_prompt', task.project, task.id) === API_FAILED) return;
    // The only confirmation there is. A clipboard write is otherwise entirely
    // invisible, and a toast in a 420px window costs more than it says.
    copyButton.innerHTML = COPIED_ICON;
    copyButton.classList.add('copied');
    clearTimeout(revertIcon);
    revertIcon = setTimeout(() => {
      copyButton.innerHTML = COPY_ICON;
      copyButton.classList.remove('copied');
    }, 1200);
  };

  // Start this task the way the header's Spin up would, without the round trip
  // through the checkbox — tick it, reach for the header, press the button,
  // untick. What it acts on is aimedAt's answer (ui/selection.js): this row on
  // its own, or the whole selection when this row is part of one. That is the
  // same rule the `done` two controls along obeys, and it is written once so
  // the two cannot answer the same click differently.
  row.querySelector('.claude').onclick = async () => {
    const aimed = aimedAt(task.project, [task.id]);
    if (!aimed) return;
    await handOff(aimed.project, aimed.ids, aimed.fromSelection);
  };

  row.querySelector('.done').onclick = async () => {
    // This row by default, and the whole selection when this row is part of
    // one — completeWithSelection (ui/selection.js) is where that rule lives,
    // because it is the same rule for the group header's `done`. Everything
    // else about completing (the confirm above three, clearing the fold entry
    // of a group this empties, refreshing even on failure) comes with it, so
    // no part of it is written twice.
    await completeWithSelection(task.project, [task.id]);
  };

  const age = daysSince(task.created);
  if (age >= (state.settings.stale_days || 90) && task.status !== 'done') {
    const marker = document.createElement('span');
    marker.className = 'age';
    marker.textContent = age >= 365 ? `${Math.floor(age / 365)}y` : `${Math.floor(age / 30)}mo`;
    row.append(marker);
  }
  return row;
}

// Rename where the name already is, without the editor overlay — the same
// gesture the group header uses one level up, and for the same reason:
// renaming is frequent enough to want a shortcut and small enough that a
// full-screen overlay is the wrong weight for it. Commits on Enter or blur;
// Escape and an empty value both put the old title back.
//
// Seeded from the TASK, never from the element's text. Search, the
// all-projects view and IN PROGRESS all decorate a foreign row's title with
// its project name, so reading the DOM would offer "sm64_tracker · Doc Pass"
// as the name to edit and then save that as the title.
//
// task.project, never currentProject (invariant 6): every one of those three
// views can show a row from a project other than the selected one.
function renameTaskInPlace(titleElement, task) {
  const row = titleElement.closest('.task');
  // A text box inside draggable="true" cannot be selected with the mouse in
  // Chromium — the drag starts instead. Same trap as renameInPlace.
  const wasDraggable = row.draggable;
  row.draggable = false;
  const restore = () => { row.draggable = wasDraggable; };

  const input = document.createElement('input');
  input.className = 'title-input';
  input.value = task.title;
  titleElement.replaceWith(input);
  input.focus();
  input.select();

  let committing = false;
  const commit = async () => {
    if (committing) return;
    const wanted = input.value.trim();
    if (!wanted || wanted === task.title) {
      input.replaceWith(titleElement);
      restore();
      return;
    }
    committing = true;
    if (await callApi('update_task', task.project, task.id,
        { title: wanted }) === API_FAILED) {
      // Keep what was typed and the focus, so a rejected name can be fixed
      // rather than retyped.
      committing = false;
      input.focus();
      input.select();
      return;
    }
    await refresh();
  };

  input.onblur = commit;
  // The row opens the editor on click, and Escape closes the topmost overlay.
  // Neither should hear anything that happens inside this box.
  input.onclick = event => event.stopPropagation();
  input.ondblclick = event => event.stopPropagation();
  input.onkeydown = event => {
    event.stopPropagation();
    if (event.key === 'Enter') { event.preventDefault(); input.blur(); }
    if (event.key === 'Escape') {
      input.onblur = null;
      input.replaceWith(titleElement);
      restore();
    }
  };
}

function bucketSection(bucket) {
  const section = document.createElement('section');
  section.dataset.bucket = bucket;
  // Every row in here belongs to the selected project, and the drag controller
  // compares a dragged row's own project against the destination's rather than
  // against currentProject (invariant 6). Stated on the section so that check
  // is one uniform comparison instead of a special case per kind of target.
  section.dataset.project = currentProject;
  section.innerHTML = `<h2>${bucket.toUpperCase()}</h2>`;
  // A loose task gets no container: drawing one around a single row would
  // claim a grouping that does not exist.
  groupBlocks(tasksFor(currentProject, bucket)).forEach(block => section.append(
    block.group ? groupBlock(block) : taskRow(block.tasks[0])));
  return section;
}

// wireDrag lives in groups.js and is bound once, to #task-list — not per
// section. Dragging is how groups are formed and dissolved, how a task changes
// bucket, and how it is claimed into or released from IN PROGRESS, and none of
// those can be answered by a listener that only sees one section.

function selectedIds() {
  return [...document.querySelectorAll('.task .select:checked')]
    .map(el => ({ project: el.closest('.task').dataset.project,
                  id: Number(el.closest('.task').dataset.id) }));
}

// Same shape as `selected` below in each caller, extracted so the row's
// visibility test (two-or-more, one project) is written exactly once. A
// single ticked task is already named by its own title — a box for it would
// be redundant chrome in a 420px window — and a mixed-project selection is
// spin-up's own problem to reject, not this row's: calling
// suggest_session_name with one project's name against another's ids would
// raise, so this simply declines to fetch rather than duplicating that check.
function nameableSelection() {
  const selected = selectedIds();
  const projects = new Set(selected.map(s => s.project));
  if (selected.length < 2 || projects.size > 1) return null;
  return { project: [...projects][0], ids: selected.map(s => s.id) };
}

// Hiding the row also empties it. The value outlives the selection it was
// typed for otherwise: switching project re-renders the task list, dropping
// every tick, so the row hides with the old project's name still in it — and
// ticking two tasks in the NEW project shows the row again carrying that name,
// which spin-up then uses. Every path that hides this row goes through here so
// there is one answer rather than one per branch.
function hideHandoffName() {
  document.getElementById('handoff-name').hidden = true;
  document.getElementById('handoff-name-input').value = '';
}

// The suggestion is fetched from the backend, never composed here, so the
// placeholder shows exactly what hand_off will do with a blank box — a
// second copy of the naming rule in JS would be free to drift from
// launcher.session_name (see Api.suggest_session_name's own docstring).
async function renderHandoffName() {
  const row = document.getElementById('handoff-name');
  const nameable = nameableSelection();
  if (!nameable) { hideHandoffName(); return; }
  const placeholder = await callApi('suggest_session_name', nameable.project, nameable.ids);
  // Selections change faster than a bridge round-trip. Compare the selection
  // this response was fetched for against the selection now, and drop the
  // response if the user ticked or unticked a box while it was in flight —
  // otherwise a slow response for an old selection could land after a fast
  // one for a newer selection and silently show the wrong suggestion.
  const stillNameable = nameableSelection();
  const sameSelection = stillNameable
    && stillNameable.project === nameable.project
    && stillNameable.ids.length === nameable.ids.length
    && stillNameable.ids.every((id, index) => id === nameable.ids[index]);
  if (!sameSelection) return;
  if (placeholder === API_FAILED) { hideHandoffName(); return; }
  // suggest_session_name legitimately returns "" for a selection it cannot
  // name (e.g. a blank first title) — a valid answer, not a failure, which is
  // why the check above compares against API_FAILED rather than truthiness
  // (invariant 4). It does mean there is no default to show, though, and a
  // labelled empty box explains nothing about what a blank one will do — it
  // reads as a broken render. Hide the row instead of inventing a hint for a
  // default that does not exist.
  if (!placeholder) { hideHandoffName(); return; }
  row.hidden = false;
  document.getElementById('handoff-name-input').placeholder = placeholder;
}

// Delegated rather than attached per-row: render() rebuilds the task list
// with replaceChildren on every redraw, which would detach a listener bound
// to an individual checkbox. Bound once here, at load — inside render()
// this would stack a duplicate listener on every call. Guarded on .select
// so a bucket-dropdown change (also a `change` event inside #task-list)
// does not retrigger this.
document.getElementById('task-list').addEventListener('change', event => {
  if (event.target.classList.contains('select')) renderHandoffName();
});

// Put back ticks a refresh threw away. Rows are matched by project and id and
// never by position: the task that just launched has moved to IN PROGRESS, and
// everything that was below it has shifted up.
//
// Matched by walking the rows rather than by building a selector, because a
// project name is user-authored text out of a hand-editable file — a quote or
// a bracket in one would break a selector string, which is invariant 5's
// concern wearing a different hat.
//
// It joins on NUL because that is the one character a project name cannot
// contain — and it is written `\0` rather than as the byte itself, which is
// what it was until this merge: a literal 0x00 makes this a *binary* file to
// every text tool, so `grep` answers "Binary file ui/tasks.js matches" instead
// of the line you asked for.
//
// A group header's own box is DERIVED here rather than remembered: a header
// whose every member is ticked is exactly what that box means, and leaving it
// empty under a fully ticked group is the same broken-render defect as leaving
// it ticked under an empty one.
function restoreTicks(picked) {
  if (!picked.length) return;
  const wanted = new Set(picked.map(({ project, id }) => `${project}\0${id}`));
  document.querySelectorAll('.task').forEach(row => {
    if (wanted.has(`${row.dataset.project}\0${row.dataset.id}`)) {
      row.querySelector('.select').checked = true;
    }
  });
  document.querySelectorAll('.group').forEach(container => {
    const boxes = [...container.querySelectorAll('.task .select')];
    const header = container.querySelector('.select-group');
    if (header && boxes.length) header.checked = boxes.every(box => box.checked);
  });
  // Assigning .checked fires no change event, so the two things that listen for
  // one have to be called by hand — the same reason the group header's own
  // select-all box calls them.
  renderSelectionBar();
  renderHandoffName();
}

// The one place a hand-off is performed. The header's Spin up and every row's
// Claude button both end here, so the batch name, the refresh and what becomes
// of the ticks cannot come out differently depending on which control was
// pressed — the same reasoning that puts build_prompt behind both the copy
// button and the hand-off on the Python side.
// test_only_one_call_site_hands_tasks_to_claude fails the build on a second
// callApi('hand_off', ...) anywhere in the UI.
//
// fromSelection answers "was the selection what launched", and both decisions
// below follow from that one answer. The name row is read only when it was: the
// row is hidden below two ticks and its value can be left over from a larger
// selection, so passing it to a single-task hand-off would name a side task
// after a batch that is still sitting there staged. And the ticks are restored
// only when it was NOT: refresh() rebuilds #task-list with replaceChildren, so
// every checkbox comes back a new, unchecked element, and a hand-off fired from
// an unticked row would otherwise silently clear a batch the user had spent
// time staging.
//
// The failure path needs no branch: it returns before refresh(), so nothing was
// re-rendered and there is nothing to put back.
async function handOff(project, ids, fromSelection) {
  const nameRow = document.getElementById('handoff-name');
  const nameInput = document.getElementById('handoff-name-input');
  const name = fromSelection && !nameRow.hidden ? nameInput.value.trim() : '';
  const keep = fromSelection ? [] : selectedIds();
  if (await callApi('hand_off', project, ids, name) === API_FAILED) return;
  // Not awaited: the typing happens in the session over the next seconds to
  // minutes, and the tracker has nothing to wait for.
  watchDelivery();
  // Otherwise the next batch inherits this one's name.
  nameInput.value = '';
  await refresh();
  restoreTicks(keep);
}

// Spinning up a session is one action with two buttons, and this is the action.
// Neither button is a variant of the other: they take the same selection, read
// the same name box and call the same bridge method, and the only difference is
// where the cursor has to travel to press one. A second copy of this body — even
// a faithful one — is how the toolbar and the bar would silently come to mean
// different things, which is exactly what happened to the drag controller
// before invariant 27.
async function handOffSelection() {
  // selectedInOneProject (selection.js) owns the per-project rule for every
  // caller: it falls back to currentProject when nothing is ticked, and
  // alerts and returns null on a mixed-project selection (invariant 6).
  //
  // Not aimedAt: this is not a row button, so there is no row to be inside or
  // outside the selection, and the "nothing ticked opens an empty session in
  // the current project" fallback is selectedInOneProject's rather than that
  // rule's. What it launches IS the selection, which is what it passes on.
  const picked = selectedInOneProject();
  if (!picked) return;
  await handOff(picked.project, picked.ids, true);
}

// The toolbar's, which is also the only way to open a session with NOTHING
// ticked: the bar does not exist then.
document.getElementById('spin-up').onclick = handOffSelection;
// The selection bar's, one line away so the two cannot drift. It sits directly
// under the Name row it reads.
document.getElementById('selection-spin-up').onclick = handOffSelection;

// How long to keep asking whether the hand-off finished. Comfortably past
// claude_console's own 180s wait for a prompt box plus its paste retries — the
// loop stops the moment nothing is in flight, so this is only the backstop for
// a delivery thread that never reports at all.
const DELIVERY_POLL_MS = 2000;
const DELIVERY_POLLS = 150;

// The bridge is call-and-return, so a hand-off that fails minutes later has no
// way to reach the page on its own — this is the frontend asking. It runs only
// while a spin-up is in flight and stops as soon as one is not, so there is no
// timer ticking the rest of the time.
async function watchDelivery() {
  for (let attempt = 0; attempt < DELIVERY_POLLS; attempt++) {
    await new Promise(done => setTimeout(done, DELIVERY_POLL_MS));
    const report = await callApi('delivery_report');
    if (report === API_FAILED) return;
    (report.notices || []).forEach(notice => showToast(notice));
    if (!report.pending) return;
  }
}

function matches(task, query) {
  const needle = query.toLowerCase();
  return task.title.toLowerCase().includes(needle)
      || asShown(task.body).toLowerCase().includes(needle);
}

function renderSearch(query) {
  // Search spans every project, exactly like the cross-project view — and
  // task ids are per-project (store.next_task_id counts within one
  // project's own files), so two projects routinely both have a "task 2".
  // Without disabling selection here, ticking a result from a project
  // other than currentProject would hand its id to hand_off(currentProject,
  // ids), which silently resolves it against currentProject's own tasks —
  // the wrong task gets marked in-progress and its body goes to Claude.
  const all = state.tasks.filter(t => matches(t, query));
  const hits = all.slice(0, 200);
  const list = document.getElementById('task-list');
  const rows = hits.map(task => {
    const row = taskRow(task);
    row.draggable = false;
    row.querySelector('.select').disabled = true;
    row.querySelector('.bucket').disabled = true;
    // Editing IS safe here, unlike selection: taskRow hands openEditor the
    // row's own project and every save routes through it, so a result from
    // another project opens the task it actually names.
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    if (task.status === 'done') {
      row.classList.add('archived');
      // This is an archived result from done/ — completing it again would
      // restamp task.done to today, silently moving it out of the progress
      // view's month it actually finished in (store.complete_task also
      // guards this, but removing the control here is the clearer fix).
      row.querySelector('.done').remove();
      // Same reason, the other direction: store.start_task refuses a completed
      // task, so this button could only ever raise.
      row.querySelector('.claude').remove();
    }
    return row;
  });
  if (all.length > hits.length) {
    const more = document.createElement('div');
    more.className = 'age';
    more.textContent = `showing first ${hits.length} of ${all.length} matches`;
    rows.push(more);
  }
  list.replaceChildren(...rows);
}

function renderAllProjects() {
  const rows = state.tasks
    .filter(t => t.bucket === 'now' && t.status !== 'done')
    .sort((a, b) => a.project.localeCompare(b.project) || a.order - b.order);
  const list = document.getElementById('task-list');
  list.replaceChildren(...rows.map(task => {
    const row = taskRow(task);
    row.draggable = false;
    row.querySelector('.select').disabled = true;
    row.querySelector('.bucket').disabled = true;
    // Editing IS safe here — see renderSearch.
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    return row;
  }));
}

function emptyHint(text) {
  const hint = document.createElement('p');
  hint.className = 'empty-hint';
  hint.textContent = text;
  return hint;
}

function render() {
  const list = document.getElementById('task-list');
  const query = document.getElementById('search').value.trim();
  if (!state.projects.length) {
    // Three bare bucket headings tell a first-time user nothing about why
    // the window is empty or what to do about it.
    list.replaceChildren(emptyHint(
      'No projects yet. Click + and point it at a project folder — its tasks '
      + 'live in that folder as markdown, alongside the code.'));
  } else if (query) {
    renderSearch(query);
  } else if (document.getElementById('all-projects').checked) {
    renderAllProjects();
  } else {
    // Always present, empty or not: it is a drop target now, and the first
    // task ever claimed has to have somewhere to land.
    list.replaceChildren(inProgressSection(), ...BUCKETS.map(bucketSection));
    const open = state.tasks.filter(
      t => t.project === currentProject && t.status !== 'done').length;
    if (!open) {
      list.append(emptyHint(
        'No tasks yet. Hit Capture to write one down — no fields, no decisions.'));
    }
  }
  renderGroupLimitWarning();
  renderSelectionBar();
  renderHandoffName();
  const unreadable = state.unreadable || [];
  const badFiles = document.getElementById('unreadable-warning');
  badFiles.hidden = unreadable.length === 0;
  badFiles.textContent =
    `${unreadable.length} task file(s) could not be read: ${unreadable.join(', ')}`;
  // Spin up Claude stays enabled with nothing ticked — that opens an empty
  // session in the current project — so it needs no syncing with the
  // selection. It is only useless with no projects at all, since then there
  // is no directory to open in.
  document.getElementById('spin-up').disabled = !state.projects.length;

  const inboxButton = document.getElementById('inbox-button');
  inboxButton.hidden = state.notes.length === 0;
  inboxButton.textContent = `Inbox ${state.notes.length}`;
  inboxButton.onclick = openTriage;
}

document.getElementById('search').oninput = render;
document.getElementById('all-projects').onchange = render;
