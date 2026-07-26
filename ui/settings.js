// Progress view, type editor, and per-project git tracking — settings.js.
//
// Types are user-editable, not a fixed taxonomy: a rename or delete
// migrates every task file across every project (including done/) so no
// task is ever left with a stale type string. The confirm/prompt dialogs
// below exist so the user always sees how many files are about to be
// rewritten before it happens, and delete_type always needs a replacement
// so a task can never end up orphaned.

function monthLabel(isoDate) {
  // isoDate is a date-only string (YYYY-MM-DD). Parsing it with `new Date()`
  // treats it as UTC midnight, and toLocaleDateString renders in local time
  // — west of UTC that shifts the 1st of a month back to the last day of the
  // previous month, mislabeling the heading. Build the date from local
  // year/month/day components instead so the label always matches the date
  // that produced it.
  const [year, month, day] = isoDate.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('en', { month: 'long', year: 'numeric' });
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

// --- Settings overlay: group limit, stale threshold, type editor, tracked toggle ---

function reportSkipped(result) {
  if (result && result.skipped && result.skipped.length) {
    alert(`Could not reach: ${result.skipped.join(', ')}. ` +
          `Tasks in those projects keep the old type.`);
  }
}

function renderTypeEditor() {
  const editor = document.getElementById('type-editor');
  editor.replaceChildren(...state.settings.types.map(type => {
    // Record each persisted type's original name once, so Save can diff the
    // submitted list against what's on disk and know which rows to migrate.
    if (!type.pending && type.original === undefined) type.original = type.name;
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

    nameInput.onchange = event => {
      const next = event.target.value.trim();
      if (!next || next === type.name) return;
      // Record intent only. Save diffs against `original` and issues the
      // migration — two writers to settings.json race, and the loser leaves
      // settings and task files disagreeing, orphaning every task of the type.
      type.name = next;
    };

    deleteButton.onclick = async () => {
      if (state.settings.types.some(t => t.original !== undefined && t.original !== t.name)) {
        alert('Save your type name changes before deleting a type.');
        return;
      }
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
  state.settings.types.push({ name: 'NEW', color: '#8e8e8e', pending: true });
  renderTypeEditor();
};

document.getElementById('settings-button').onclick = () => {
  document.getElementById('group-limit').value = state.settings.group_limit;
  document.getElementById('stale-days').value = state.settings.stale_days;
  renderTypeEditor();
  renderTrackedEditor();
  document.getElementById('settings').hidden = false;
};

document.getElementById('settings-save').onclick = async () => {
  const rows = [...document.querySelectorAll('.type-row')];
  const types = rows.map(row => ({
    name: row.querySelector('.type-name').value.trim(),
    color: row.querySelector('.type-color').value,
  }));
  if (types.some(t => !t.name)) { alert('Type names cannot be empty.'); return; }
  const names = types.map(t => t.name);
  if (new Set(names).size !== names.length) { alert('Type names must be unique.'); return; }

  // Migrate renamed types first, one at a time, so task files and settings
  // can never disagree. Each rename rewrites every affected task file across
  // every project including done/.
  for (let index = 0; index < rows.length; index++) {
    const original = state.settings.types[index] && state.settings.types[index].original;
    if (!original || original === types[index].name) continue;
    const count = await callApi('count_tasks_with_type', original);
    if (count === API_FAILED) return;
    if (count && !confirm(`Rename ${original} to ${types[index].name} on ${count} task(s)?`)) return;
    const result = await callApi('rename_type', original, types[index].name);
    if (result === API_FAILED) return;
    reportSkipped(result);
  }

  const payload = {
    group_limit: Number(document.getElementById('group-limit').value),
    stale_days: Number(document.getElementById('stale-days').value),
    types,
  };
  if (await callApi('save_settings', payload) === API_FAILED) return;
  document.getElementById('settings').hidden = true;
  await refresh();
};

document.getElementById('settings-close').onclick =
  () => { document.getElementById('settings').hidden = true; };
