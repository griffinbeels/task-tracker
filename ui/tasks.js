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
  row.innerHTML = `
    <input type="checkbox" class="select">
    <span class="type" style="background:${typeColor(task.type)}"></span>
    <span class="title"></span>
    <button class="done" title="Mark done">done</button>`;
  // task.title and task.type are user-authored free text (store.py's Task.type
  // is a plain str with no validation) that can contain <, &, or quotes —
  // setting them via innerHTML would corrupt the markup, so set them as text
  // content on the already-built elements instead.
  row.querySelector('.type').textContent = task.type;
  row.querySelector('.title').textContent = task.title;
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
    .map(el => Number(el.closest('.task').dataset.id));
}

document.getElementById('task-list').addEventListener('change', () => {
  document.getElementById('spin-up').disabled = selectedIds().length === 0;
});

document.getElementById('spin-up').onclick = async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  if (await callApi('hand_off', currentProject, ids) === API_FAILED) return;
  await refresh();
};

function matches(task, query) {
  const needle = query.toLowerCase();
  return task.title.toLowerCase().includes(needle)
      || task.body.toLowerCase().includes(needle);
}

function renderSearch(query) {
  const hits = state.tasks.filter(t => matches(t, query)).slice(0, 200);
  const list = document.getElementById('task-list');
  list.replaceChildren(...hits.map(task => {
    const row = taskRow(task);
    row.draggable = false;
    row.querySelector('.title').textContent = `${task.project} · ${task.title}`;
    if (task.status === 'done') row.classList.add('archived');
    return row;
  }));
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
