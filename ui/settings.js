// Progress view, type editor, and per-project git tracking — settings.js.
//
// Types are user-editable, not a fixed taxonomy: a rename or delete
// migrates every task file across every project (including done/) so no
// task is ever left with a stale type string. The confirm/prompt dialogs
// below exist so the user always sees how many files are about to be
// rewritten before it happens, and delete_type always needs a replacement
// so a task can never end up orphaned.

function monthLabel(isoDate) {
  // localDate (state.js) is why this reads a date-only string through a helper
  // rather than `new Date(iso)`: the latter is UTC midnight rendered in local
  // time, which west of UTC files the 1st of a month under the previous one.
  return localDate(isoDate).toLocaleDateString('en', { month: 'long', year: 'numeric' });
}

// Extracted so a restore can redraw this list without reopening the whole
// overlay — the button handler below and the editor's restore handler
// (ui/editor.js) both call this directly.
function renderProgress() {
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
    // Opens the same overlay a task row does — this field list is copied
    // from taskRow's openEditor call (ui/tasks.js) so the two cannot drift.
    // status is what tells the editor to offer Restore for a done task.
    entry.onclick = () => openEditor({
      mode: 'edit',
      taskId: task.id,
      project: task.project,
      title: task.title,
      body: task.body,
      type: task.type,
      bucket: task.bucket,
      status: task.status,
      group: task.group,
      color: task.color,
    });
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
}

document.getElementById('progress-button').onclick = () => {
  renderProgress();
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

// Types added with "Add type" but not yet saved. Deliberately NOT pushed into
// state.settings.types, which is what they used to be: that array is replaced
// wholesale by every refresh(), so a rename or delete elsewhere in this panel
// silently swallowed a row the user had just typed — and it equally survived
// Close, so a type you cancelled got created by the next Save. Held here
// instead, the two answers fall out of where the data lives: refresh cannot
// reach it, and Close is the one thing that clears it.
let pendingTypes = [];

function renderTypeEditor() {
  const editor = document.getElementById('type-editor');
  // Persisted rows first, then unsaved ones — Save reads the rows back by
  // position and pairs each against state.settings.types[index], so anything
  // with no counterpart there is a row to create rather than migrate.
  const rows = [...state.settings.types, ...pendingTypes];
  editor.replaceChildren(...rows.map((type, index) => {
    const isPending = index >= state.settings.types.length;
    // Record each persisted type's original name once, so Save can diff the
    // submitted list against what's on disk and know which rows to migrate.
    if (!isPending && type.original === undefined) type.original = type.name;
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

    // Colour needs writing back for the same reason the name does, even though
    // Save reads both straight off the DOM: anything that re-renders this list
    // — deleting another row, most obviously — rebuilds every input from the
    // objects, and a pick that was never written back reverts to the stored
    // value with nothing said. Unsaved rows have no stored value to revert to,
    // so on those it goes all the way back to the default grey.
    colorInput.onchange = event => { type.color = event.target.value; };

    deleteButton.onclick = async () => {
      // An unsaved row exists nowhere but this panel, so there is nothing to
      // migrate and nothing to confirm — dropping it is the whole operation,
      // and asking the backend to delete a type it has never heard of would
      // only raise.
      if (isPending) {
        pendingTypes.splice(index - state.settings.types.length, 1);
        renderTypeEditor();
        return;
      }
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
      // A type with no tasks used to delete on the single click that asked for
      // it. Nothing here is undoable and the button sits inches from the name
      // box, so the empty case gets a confirm too — it is just a shorter
      // question, since there is nothing to reassign.
      } else if (!confirm(`Delete the type ${type.name}? No tasks use it.`)) {
        return;
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
      // Put the box back if the write did not land. This is the one control in
      // the app whose display is a claim about git, and a box left ticked over
      // a project whose .tasks/ is still gitignored is the claim you act on
      // right before committing. callApi has already said what went wrong;
      // what it cannot do is un-flip the checkbox the browser flipped before
      // the handler ever ran.
      const wanted = event.target.checked;
      if (await callApi('set_project_tracked', project.name, wanted) === API_FAILED) {
        event.target.checked = !wanted;
        return;
      }
      await refresh();
    };

    return row;
  }));
}

document.getElementById('add-type').onclick = () => {
  pendingTypes.push({ name: 'NEW', color: '#8e8e8e' });
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

  // Both inputs are type="number" min="1", and an emptied one reads back as
  // Number('') === 0. Stored, that 0 then comes back out through `x || 5` at
  // every reader — so the file says 0, the app behaves as 5, and nothing on
  // screen ever admits the two disagree. Refusing it here is what keeps the
  // stored value and the effective one the same number.
  const numbers = [
    { key: 'group_limit', input: 'group-limit', label: 'Group limit' },
    { key: 'stale_days', input: 'stale-days', label: 'Stale after (days)' },
  ];
  const settings = {};
  for (const { key, input, label } of numbers) {
    const value = Number(document.getElementById(input).value);
    if (!Number.isInteger(value) || value < 1) {
      alert(`${label} must be a whole number of 1 or more.`);
      return;
    }
    settings[key] = value;
  }

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

  if (await callApi('save_settings', { ...settings, types }) === API_FAILED) return;
  pendingTypes = [];
  document.getElementById('settings').hidden = true;
  await refresh();
};

document.getElementById('settings-close').onclick = () => {
  // Cancel means cancel. Anything typed into "Add type" and not saved is
  // dropped here — leaving it would let the next Save create a type this
  // click declined.
  pendingTypes = [];
  document.getElementById('settings').hidden = true;
};
