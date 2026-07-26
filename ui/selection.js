// The selection bar: what is ticked, and the three things you can do to all
// of it. This file owns counting the selection, showing/hiding the bar, and
// the Done/Delete/Clear handlers below.

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

// One or two ticked tasks go through Done with no prompt — that mirrors the
// row button's own gesture, and redoing it by hand is cheap. At this size or
// above, Done asks first, in the same shape as Delete's dialog below.
const DONE_CONFIRM_THRESHOLD = 3;

// Both the selection bar and a group header (ui/groups.js) complete many
// tasks at once, and they must ask the same question and recover the same
// way. One function, so they cannot drift.
async function completeTasksWithConfirm(project, ids) {
  if (!ids.length) return;
  if (ids.length >= DONE_CONFIRM_THRESHOLD && !confirm(
      `Mark ${ids.length} tasks done? They move to .tasks/done/ and `
      + `the app has no way back.`)) return;
  // Refresh whether or not the call succeeded: complete_tasks (like
  // delete_tasks below) validates every id up front but then acts
  // file-by-file, so a failure partway through can still leave earlier tasks
  // moved to done/. Refreshing on the failure path too is what stops the
  // list drawing rows for tasks that already left this bucket.
  await callApi('complete_tasks', project, ids);
  await refresh();
}

document.getElementById('selection-done').onclick = async () => {
  const picked = selectedInOneProject();
  if (!picked) return;
  await completeTasksWithConfirm(picked.project, picked.ids);
};

document.getElementById('selection-delete').onclick = async () => {
  const picked = selectedInOneProject();
  if (!picked || !picked.ids.length) return;
  // confirm() has not been proven to render in this app's WebView2 host — if
  // it is suppressed it returns false and nothing is deleted, which is the
  // safe direction.
  const what = picked.ids.length === 1 ? 'this task' : `these ${picked.ids.length} tasks`;
  if (!confirm(`Delete ${what}? The markdown file is erased. This cannot be undone.`)) return;
  if (await callApi('delete_tasks', picked.project, picked.ids) === API_FAILED) {
    // Same reasoning as selection-done above: delete_tasks validates up front
    // but unlinks in a loop, so a failure partway through can leave earlier
    // files already gone. Refresh so the list stops drawing rows for files
    // that no longer exist — leaving them would let a click open the editor
    // on a missing path.
    await refresh();
    return;
  }
  await refresh();
};
