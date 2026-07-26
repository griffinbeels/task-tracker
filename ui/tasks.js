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

function tasksFor(project, bucket) {
  return state.tasks
    .filter(t => t.project === project && t.bucket === bucket && t.status !== 'done')
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
  // which would let it escape into markup with full pywebview.api access.
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

function wireDrag(section, bucket) {
  let dragged = null;
  section.addEventListener('dragstart', e => { dragged = e.target.closest('.task'); });
  section.addEventListener('dragover', e => {
    e.preventDefault();
    const over = e.target.closest('.task');
    if (!over || over === dragged || !dragged) return;
    const after = over.getBoundingClientRect().top + over.offsetHeight / 2 < e.clientY;
    section.insertBefore(dragged, after ? over.nextSibling : over);
  });
  section.addEventListener('drop', async () => {
    const ids = [...section.querySelectorAll('.task')].map(el => Number(el.dataset.id));
    await callApi('reorder_bucket', currentProject, bucket, ids);
    await refresh();
  });
}

function selectedIds() {
  return [...document.querySelectorAll('.task .select:checked')]
    .map(el => ({ project: el.closest('.task').dataset.project,
                  id: Number(el.closest('.task').dataset.id) }));
}

document.getElementById('spin-up').onclick = async () => {
  const selected = selectedIds();
  // Ids are per-project, so a mixed selection cannot be handed to one
  // session — and one session per working tree is the design anyway.
  const projects = new Set(selected.map(s => s.project));
  if (projects.size > 1) { alert('Select tasks from one project at a time.'); return; }
  // Selecting nothing is a real request, not a mistake: open a session in the
  // project you are looking at and leave its prompt empty.
  const project = projects.size ? [...projects][0] : currentProject;
  if (!project) return;
  if (await callApi('hand_off', project, selected.map(s => s.id)) === API_FAILED) return;
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
    // Same ambiguous-id hazard as selection above — editing here would open
    // whichever project's task 1 happens to be currentProject's, not the one
    // this row actually names.
    row.onclick = null;
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
    // Same ambiguous-id hazard as selection above — editing here would open
    // whichever project's task 1 happens to be currentProject's, not the one
    // this row actually names.
    row.onclick = null;
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
    list.replaceChildren(...BUCKETS.map(bucketSection));
    const open = state.tasks.filter(
      t => t.project === currentProject && t.status !== 'done').length;
    if (!open) {
      list.append(emptyHint(
        'No tasks yet. Hit Capture to write one down — no fields, no decisions.'));
    }
  }
  renderWipWarning();
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
