// The selection bar: what is ticked, and the three things you can do to all
// of it. This file owns counting the selection, showing/hiding the bar, and
// the Done/Delete/Clear handlers below.
//
// It also owns what a tick MEANS to the buttons outside the bar: every one of
// them resolves what it acts on through aimedAt here, so a `done` and a Claude
// button pressed on the same row aim at the same tasks.

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
  // The bar slides out rather than disappearing (see #selection-bar in
  // style.css), so it is on screen for the length of that slide after the last
  // box is unticked. Writing "0 selected" into it at that moment would be the
  // only frame of the animation anyone actually reads. Leaving the last count
  // alone means it leaves saying what it was — which is true, and which is
  // also what it says while sliding out under a Clear.
  if (count) document.getElementById('selection-count').textContent =
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
  // Here rather than in either caller: the group header's `done` completes a
  // whole group in one click and the bar's Done can do the same to a ticked
  // one, so the rule that a vanished group must not keep its fold entry
  // belongs to the function they share — the same reason this function exists
  // at all. After the confirm, so declining leaves the fold alone.
  await forgetFoldsEmptiedBy(project, ids);
  // Refresh whether or not the call succeeded: complete_tasks (like
  // delete_tasks below) validates every id up front but then acts
  // file-by-file, so a failure partway through can still leave earlier tasks
  // moved to done/. Refreshing on the failure path too is what stops the
  // list drawing rows for tasks that already left this bucket.
  await callApi('complete_tasks', project, ids);
  await refresh();
}

// What a button OUTSIDE the bar acts on, and the rule that makes every one of
// them the same control. A button names some tasks — one row, or the rows a
// group header drew — and normally means exactly those. But when every task it
// names is ticked, the click is aimed at a selection the user has visibly
// made: the bar is on screen saying "4 selected", and acting on 1 of those 4
// reads as the ticks having been ignored rather than as a narrower gesture. So
// it resolves to the selection instead.
//
// An unticked row is untouched by this: a button on a row nobody picked out
// means that row, whatever else is selected elsewhere. That is the whole
// distinction, and it is the one the checkbox already draws.
//
// `fromSelection` is the answer to "was the selection what this acts on", and
// it is here rather than in each caller because more than bookkeeping hangs off
// it: the hand-off reads the batch-name row only when it is true, and restores
// the ticks a refresh threw away only when it is false. Two flags would be free
// to disagree; one cannot.
//
// null means refused — nothing named, or a selection the user has just been
// alerted spans two projects.
function aimedAt(project, ids) {
  if (!ids.length) return null;
  const tickedHere = new Set(selectedIds()
    .filter(picked => picked.project === project)
    .map(picked => picked.id));
  if (!ids.every(id => tickedHere.has(id))) {
    return { project, ids, fromSelection: false };
  }
  // Refused here exactly as it is at the bar — selectedInOneProject alerts and
  // returns null — rather than quietly acting on this project's half of a
  // selection the user can see spans two. IN PROGRESS is where that selection
  // is possible (invariant 6), and it is where these buttons sit beside rows
  // from several projects at once.
  const selection = selectedInOneProject();
  if (!selection) return null;
  return { ...selection, fromSelection: true };
}

// Every `done` button in the app ends here — a task row's and a group header's
// — and it is one of two callers of the rule above; the Claude button on a row
// is the other. Everything else about completing (the confirm above three,
// clearing the fold entry of a group this empties, refreshing even on failure)
// belongs to completeTasksWithConfirm, which the bar's own Done calls too, so
// no part of it is written twice.
async function completeWithSelection(project, ids) {
  const aimed = aimedAt(project, ids);
  if (!aimed) return;
  await completeTasksWithConfirm(aimed.project, aimed.ids);
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
