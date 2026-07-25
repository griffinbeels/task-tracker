function tasksFor(project, bucket) {
  return state.tasks
    .filter(t => t.project === project && t.bucket === bucket && t.status !== 'done')
    .sort((a, b) => a.order - b.order);
}

function taskRow(task) {
  const row = document.createElement('div');
  row.className = 'task';
  row.draggable = true;
  row.dataset.id = task.id;
  row.dataset.project = task.project;
  row.innerHTML = `
    <input type="checkbox" class="select">
    <span class="type"></span>
    <span class="title"></span>
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
  row.querySelector('.done').before(bucketPicker);

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
  tasksFor(currentProject, bucket).forEach(t => section.append(taskRow(t)));
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

document.getElementById('task-list').addEventListener('change', () => {
  document.getElementById('spin-up').disabled = selectedIds().length === 0;
});

document.getElementById('spin-up').onclick = async () => {
  const selected = selectedIds();
  if (!selected.length) return;
  // Ids are per-project, so a mixed selection cannot be handed to one
  // session — and one session per working tree is the design anyway.
  const projects = new Set(selected.map(s => s.project));
  if (projects.size > 1) { alert('Select tasks from one project at a time.'); return; }
  if (await callApi('hand_off', [...projects][0], selected.map(s => s.id)) === API_FAILED) return;
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
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    return row;
  }));
}

function render() {
  const query = document.getElementById('search').value.trim();
  if (query) renderSearch(query);
  else if (document.getElementById('all-projects').checked) renderAllProjects();
  else document.getElementById('task-list')
        .replaceChildren(...BUCKETS.map(bucketSection));
  renderWipWarning();
  const unreadable = state.unreadable || [];
  const badFiles = document.getElementById('unreadable-warning');
  badFiles.hidden = unreadable.length === 0;
  badFiles.textContent =
    `${unreadable.length} task file(s) could not be read: ${unreadable.join(', ')}`;
  // Every branch above just replaced task-list with freshly built rows, so
  // no checkbox can be checked yet — keep spin-up in sync rather than
  // leaving it enabled from a selection that no longer exists in the DOM.
  document.getElementById('spin-up').disabled = selectedIds().length === 0;

  const inboxButton = document.getElementById('inbox-button');
  inboxButton.hidden = state.notes.length === 0;
  inboxButton.textContent = `Inbox ${state.notes.length}`;
  inboxButton.onclick = openTriage;
}

document.getElementById('search').oninput = render;
document.getElementById('all-projects').onchange = render;
