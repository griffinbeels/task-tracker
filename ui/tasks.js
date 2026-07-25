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

function render() {
  const list = document.getElementById('task-list');
  list.replaceChildren(...BUCKETS.map(bucketSection));
  renderWipWarning();

  const inboxButton = document.getElementById('inbox-button');
  inboxButton.hidden = state.notes.length === 0;
  inboxButton.textContent = `Inbox ${state.notes.length}`;
  inboxButton.onclick = openTriage;
}
