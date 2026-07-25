// Progress view, type editor, and per-project git tracking — settings.js.
//
// Types are user-editable, not a fixed taxonomy: a rename or delete
// migrates every task file across every project (including done/) so no
// task is ever left with a stale type string. The confirm/prompt dialogs
// below exist so the user always sees how many files are about to be
// rewritten before it happens, and delete_type always needs a replacement
// so a task can never end up orphaned.

function monthLabel(isoDate) {
  return new Date(isoDate).toLocaleDateString('en', { month: 'long', year: 'numeric' });
}

document.getElementById('progress-button').onclick = () => {
  const done = state.tasks
    .filter(t => t.project === currentProject && t.status === 'done' && t.done)
    .sort((a, b) => b.done.localeCompare(a.done));

  const body = document.getElementById('progress-body');
  body.replaceChildren();
  let month = null;
  for (const task of done) {
    const label = monthLabel(task.done);
    if (label !== month) {
      month = label;
      const heading = document.createElement('h2');
      heading.textContent = label;
      body.append(heading);
    }
    const entry = document.createElement('div');
    entry.className = 'entry';
    // task.title is user-authored free text — build the row as elements and
    // set textContent, same rule tasks.js/triage.js follow for the same
    // reason (title can contain <, &, quotes).
    const type = document.createElement('span');
    type.className = 'type';
    type.style.background = typeColor(task.type);
    type.textContent = task.type;
    const title = document.createElement('span');
    title.textContent = task.title;
    entry.append(type, title);
    body.append(entry);

    const outcome = task.body.split(/^## Outcome$/m)[1];
    if (outcome && outcome.trim()) {
      const note = document.createElement('div');
      note.className = 'outcome';
      note.textContent = outcome.trim();
      body.append(note);
    }
  }
  if (!done.length) body.textContent = 'Nothing completed yet.';
  document.getElementById('progress').hidden = false;
};

document.getElementById('progress-close').onclick =
  () => { document.getElementById('progress').hidden = true; };

// --- Settings overlay: WIP limit, stale threshold, type editor, tracked toggle ---

function reportSkipped(result) {
  if (result && result.skipped && result.skipped.length) {
    alert(`Could not reach: ${result.skipped.join(', ')}. ` +
          `Tasks in those projects keep the old type.`);
  }
}

function renderTypeEditor() {
  const editor = document.getElementById('type-editor');
  editor.replaceChildren(...state.settings.types.map(type => {
    const row = document.createElement('div');
    row.className = 'type-row';

    // type.name and type.color are user-authored free text (registry.TaskType
    // has no validation) — build the inputs as elements and set .value in JS
    // rather than interpolating into innerHTML.
    const nameInput = document.createElement('input');
    nameInput.className = 'type-name';
    nameInput.value = type.name;

    const colorInput = document.createElement('input');
    colorInput.className = 'type-color';
    colorInput.type = 'color';
    colorInput.value = type.color;

    const deleteButton = document.createElement('button');
    deleteButton.className = 'type-delete';
    deleteButton.textContent = 'delete';

    row.append(nameInput, colorInput, deleteButton);

    nameInput.onchange = async event => {
      const next = event.target.value.trim();
      if (!next || next === type.name) return;
      const count = await callApi('count_tasks_with_type', type.name);
      if (count === API_FAILED) return;
      // count is a real int and 0 is a legitimate result (no tasks use this
      // type) — only ask for confirmation when there's something at stake.
      if (count && !confirm(`Rename ${type.name} to ${next} on ${count} task(s)?`)) {
        event.target.value = type.name;
        return;
      }
      const result = await callApi('rename_type', type.name, next);
      if (result === API_FAILED) return;
      reportSkipped(result);
      await refresh();
      renderTypeEditor();
    };

    deleteButton.onclick = async () => {
      const count = await callApi('count_tasks_with_type', type.name);
      if (count === API_FAILED) return;
      const others = state.settings.types.filter(t => t.name !== type.name);
      if (!others.length) { alert('At least one type is required.'); return; }
      let replacement = others[0].name;
      if (count) {
        replacement = prompt(
          `${count} task(s) use ${type.name}. Reassign them to which type?\n` +
          others.map(t => t.name).join(', '), replacement);
        if (!replacement) return;
      }
      const result = await callApi('delete_type', type.name, replacement);
      if (result === API_FAILED) return;
      reportSkipped(result);
      await refresh();
      renderTypeEditor();
    };

    return row;
  }));
}

function renderTrackedEditor() {
  const editor = document.getElementById('tracked-editor');
  editor.replaceChildren(...state.projects.map(project => {
    const row = document.createElement('label');
    row.className = 'tracked-row';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = !!project.tracked;

    row.append(checkbox, document.createTextNode(`commit ${project.name}/.tasks to git`));

    checkbox.onchange = async event => {
      if (await callApi('set_project_tracked', project.name, event.target.checked) === API_FAILED) return;
      await refresh();
    };

    return row;
  }));
}

document.getElementById('add-type').onclick = () => {
  state.settings.types.push({ name: 'NEW', color: '#8e8e8e' });
  renderTypeEditor();
};

document.getElementById('settings-button').onclick = () => {
  document.getElementById('wip-limit').value = state.settings.wip_limit;
  document.getElementById('stale-days').value = state.settings.stale_days;
  renderTypeEditor();
  renderTrackedEditor();
  document.getElementById('settings').hidden = false;
};

document.getElementById('settings-save').onclick = async () => {
  const payload = {
    wip_limit: Number(document.getElementById('wip-limit').value),
    stale_days: Number(document.getElementById('stale-days').value),
    types: [...document.querySelectorAll('.type-row')].map(row => ({
      name: row.querySelector('.type-name').value.trim(),
      color: row.querySelector('.type-color').value,
    })),
  };
  if (await callApi('save_settings', payload) === API_FAILED) return;
  document.getElementById('settings').hidden = true;
  await refresh();
};

document.getElementById('settings-close').onclick =
  () => { document.getElementById('settings').hidden = true; };
