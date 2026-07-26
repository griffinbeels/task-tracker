// The selection bar: what is ticked, and the two things you can do to all of
// it. This file owns counting the selection and clearing it; Done and Delete
// are wired in a later task.

// The existing spin-up guard, extracted so both spin-up and the bar's own
// actions can share it. selectedIds() returns [{project, id}, ...] — collapse
// that to the single project involved, or refuse if it spans more than one.
function selectedInOneProject() {
  const selected = selectedIds();
  // Ids are per-project, so a mixed selection cannot be handed to one
  // session — and one session per working tree is the design anyway.
  const projects = new Set(selected.map(s => s.project));
  if (projects.size > 1) { alert('Select tasks from one project at a time.'); return null; }
  // Selecting nothing is a real request, not a mistake: open a session in the
  // project you are looking at and leave its prompt empty.
  const project = projects.size ? [...projects][0] : currentProject;
  if (!project) return null;
  return { project, ids: selected.map(s => s.id) };
}

function renderSelectionBar() {
  const count = selectedIds().length;
  document.getElementById('selection-bar').hidden = count === 0;
  document.getElementById('selection-count').textContent =
    count === 1 ? '1 selected' : `${count} selected`;
}

// Delegated so it survives render()'s list.replaceChildren(...), which throws
// away any listener bound to a row directly. #task-list also contains the
// per-row .bucket pickers and the group headers' own .select-group boxes,
// whose change events bubble through here too — the class guard is what
// keeps those from recounting a selection they are not part of.
document.getElementById('task-list').addEventListener('change', event => {
  if (event.target.classList.contains('select')) renderSelectionBar();
});

document.getElementById('selection-clear').onclick = () => {
  // Both halves are needed — a group header left ticked with no members
  // ticked reads as a broken render.
  document.querySelectorAll('.task .select:checked')
    .forEach(box => { box.checked = false; });
  document.querySelectorAll('.select-group:checked')
    .forEach(box => { box.checked = false; });
  renderSelectionBar();
};

document.getElementById('selection-done').onclick = async () => {
  const picked = selectedInOneProject();
  if (!picked || !picked.ids.length) return;
  if (await callApi('complete_tasks', picked.project, picked.ids) === API_FAILED) return;
  await refresh();
};

document.getElementById('selection-delete').onclick = async () => {
  const picked = selectedInOneProject();
  if (!picked || !picked.ids.length) return;
  // confirm() has not been proven to render in this app's WebView2 host — if
  // it is suppressed it returns false and nothing is deleted, which is the
  // safe direction.
  const what = picked.ids.length === 1 ? 'this task' : `these ${picked.ids.length} tasks`;
  if (!confirm(`Delete ${what}? The markdown file is erased. This cannot be undone.`)) return;
  if (await callApi('delete_tasks', picked.project, picked.ids) === API_FAILED) return;
  await refresh();
};
