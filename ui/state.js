const BUCKETS = ['now', 'next', 'someday'];
let state = { projects: [], settings: {}, tasks: [], notes: [] };
let currentProject = null;

function typeColor(name) {
  const found = (state.settings.types || []).find(t => t.name === name);
  return found ? found.color : '#8e8e8e';
}

// Every pywebview.api call can reject (backend methods raise ValueError on
// bad input — e.g. add_project on a non-directory path or a duplicate name).
// Across the bridge that becomes a rejected promise; without a catch it's a
// silent unhandled rejection with no feedback to the user. Route call sites
// that a user can trigger with bad input through this instead of calling
// window.pywebview.api directly.
//
// Bridge methods that return nothing (e.g. delete_note) cross back as JS
// null on success, same as any other value — null can't double as a failure
// sentinel. Use this unique Symbol instead and compare call sites against
// it, never against null.
const API_FAILED = Symbol('api-failed');

async function callApi(name, ...args) {
  try {
    return await window.pywebview.api[name](...args);
  } catch (error) {
    alert(`${name} failed:\n\n${error}`);
    return API_FAILED;
  }
}

// Placeholder for Task 10's real WIP-limit banner (see
// docs/superpowers/plans/2026-07-25-task-tracker.md Task 10 Step 4). tasks.js's
// render() calls this unconditionally per the Task 8 brief, so without a stub
// here every refresh() throws ReferenceError until Task 10 lands and replaces
// this with the real implementation.
function renderWipWarning() {}

function renderProjectPicker() {
  const picker = document.getElementById('project-picker');
  picker.replaceChildren(...state.projects.map(p => {
    const option = document.createElement('option');
    option.value = p.name;
    option.textContent = p.name;
    option.selected = p.name === currentProject;
    return option;
  }));
  picker.onchange = () => { currentProject = picker.value; render(); };
}

async function refresh() {
  state = await window.pywebview.api.get_state();
  if (!currentProject && state.projects.length) currentProject = state.projects[0].name;
  renderProjectPicker();
  render();
}

document.getElementById('add-project').onclick = async () => {
  const path = prompt('Project folder path');
  if (!path) return;
  const name = prompt('Project name', path.split(/[\\/]/).filter(Boolean).pop());
  if (!name) return;
  if (await callApi('add_project', name, path) === API_FAILED) return;
  currentProject = name;
  await refresh();
};

window.addEventListener('pywebviewready', refresh);
