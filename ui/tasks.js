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
    <button class="copy" title="Copy as a prompt">${COPY_ICON}</button>
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
  row.querySelector('.title').textContent = task.title;

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
    row.querySelector('.copy').before(bucketPicker);
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

  // The whole task, as the text you would have typed to start it: exactly what
  // "Spin up Claude" would send, built by the same backend function so the two
  // cannot drift apart. It takes task.project rather than currentProject, so
  // unlike selection and editing it stays correct in the search and
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

  row.querySelector('.done').onclick = async () => {
    // The third way a group can be emptied — a one-member group finished from
    // its own row — and the same reason the other two clear the fold entry
    // first: nothing renders a group with no members, so the entry would sit
    // there until the name is used again and then fold it.
    await forgetFoldIfEmptied(task.project, task.group);
    await callApi('complete_task', task.project, task.id);
    await refresh();
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

function bucketSection(bucket) {
  const section = document.createElement('section');
  section.dataset.bucket = bucket;
  section.innerHTML = `<h2>${bucket.toUpperCase()}</h2>`;
  // A loose task gets no container: drawing one around a single row would
  // claim a grouping that does not exist.
  groupBlocks(tasksFor(currentProject, bucket)).forEach(block => section.append(
    block.group ? groupBlock(block) : taskRow(block.tasks[0])));
  wireDrag(section, bucket);
  return section;
}

// wireDrag lives in groups.js — dragging is now how groups are formed and
// dissolved, not only how rows are ordered.

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

document.getElementById('spin-up').onclick = async () => {
  // selectedInOneProject (selection.js) owns the per-project rule for every
  // caller: it falls back to currentProject when nothing is ticked, and
  // alerts and returns null on a mixed-project selection (invariant 6).
  const picked = selectedInOneProject();
  if (!picked) return;
  const nameRow = document.getElementById('handoff-name');
  const nameInput = document.getElementById('handoff-name-input');
  // Below two selections the row is hidden and its value may be stale from
  // an earlier, larger selection — passing it here would silently name a
  // single-task session after a batch that was since abandoned.
  const name = nameRow.hidden ? '' : nameInput.value.trim();
  if (await callApi('hand_off', picked.project, picked.ids, name) === API_FAILED) return;
  // Otherwise the next batch inherits this one's name.
  nameInput.value = '';
  await refresh();
};

function matches(task, query) {
  const needle = query.toLowerCase();
  return task.title.toLowerCase().includes(needle)
      || task.body.toLowerCase().includes(needle);
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
    const running = inProgressSection();
    list.replaceChildren(...(running ? [running] : []), ...BUCKETS.map(bucketSection));
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
