const BUCKETS = ['now', 'next', 'someday'];
let state = { projects: [], settings: {}, tasks: [], notes: [], unreadable: [] };
let currentProject = null;

function typeColor(name) {
  const found = (state.settings.types || []).find(t => t.name === name);
  return found ? found.color : '#8e8e8e';
}

function daysSince(isoDate) {
  return Math.floor((Date.now() - new Date(isoDate).getTime()) / 86400000);
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

// Soft banner over the user-configurable group limit (default 5, matching the
// user's stated ceiling of concurrent Claude windows). Never blocks an
// action — it exists so an overloaded backlog is visible, not to nag.
//
// It counts GROUPS, not tasks: ten tasks handed to one session are one Claude
// window, which is what the limit is really about. The count comes from
// inProgressGroupKeys() in inprogress.js — the same function the IN PROGRESS
// section counts its heading with — so the number here can never disagree with
// what is on screen. That disagreement was the original bug: a banner summing
// every project sat above a list showing one.
function renderGroupLimitWarning() {
  const active = inProgressGroupKeys().size;
  const limit = state.settings.group_limit || 5;
  const banner = document.getElementById('group-limit-warning');
  banner.hidden = active <= limit;
  banner.textContent = `${active} ${active === 1 ? 'group' : 'groups'} in progress `
    + `— over your limit of ${limit}`;
}

// One place decides what "the current project" means, because the selection
// now outlives the window: it is written to disk on every change rather than
// at close, so a crash or a restart cannot lose it. Every path that changes
// the project goes through here.
function rememberProject(name) {
  currentProject = name;
  callApi('set_last_project', name);
}

function renderProjectPicker() {
  const picker = document.getElementById('project-picker');
  // With no projects the select has no options, so it collapses to a stub
  // that says nothing about why it is empty. Say it instead.
  if (!state.projects.length) {
    const empty = document.createElement('option');
    empty.textContent = 'No projects yet';
    empty.disabled = true;
    empty.selected = true;
    picker.replaceChildren(empty);
    picker.disabled = true;
    return;
  }
  picker.disabled = false;
  picker.replaceChildren(...state.projects.map(p => {
    const option = document.createElement('option');
    option.value = p.name;
    option.textContent = p.name;
    option.selected = p.name === currentProject;
    return option;
  }));
  picker.onchange = () => { rememberProject(picker.value); render(); };
}

async function refresh() {
  try {
    state = await window.pywebview.api.get_state();
  } catch (error) {
    alert(`Could not load your tasks:\n\n${error}`);
    return;
  }
  // Restore the project the last window was left on, so restarting — by this
  // app's own button or by run.bat — comes back to what you were doing. The
  // "still registered" check is what stops a removed or renamed project from
  // selecting nothing at all. A stale name is left on disk rather than
  // corrected here: the next selection overwrites it, and rewriting config as
  // a side effect of reading it is worse than a dead key.
  //
  // The same check runs on EVERY refresh, not just the first, because the
  // selection can go stale after it is made: projects.json is hand-editable
  // and every refresh re-reads it. With currentProject naming a project that
  // is no longer registered, no <option> matches, so the browser silently
  // selects the first — and the list below then renders a different project
  // from the one the picker is showing, which reads as the tasks being gone.
  if (!state.projects.some(p => p.name === currentProject)) {
    const remembered = state.projects.some(p => p.name === state.last_project);
    currentProject = remembered ? state.last_project : (state.projects[0]?.name ?? null);
  }
  renderProjectPicker();
  render();
}

document.getElementById('add-project').onclick = async () => {
  const path = await callApi('pick_project_folder');
  if (path === API_FAILED || !path) return;

  // Name it after the folder. Only ask when that name is taken — one dialog
  // for the normal case, since registering a project should be one gesture.
  let name = path.split(/[\\/]/).filter(Boolean).pop();
  if (state.projects.some(p => p.name === name)) {
    name = prompt(`A project named "${name}" is already registered. Name this one:`, name);
    if (!name) return;
  }
  if (await callApi('add_project', name, path) === API_FAILED) return;
  rememberProject(name);
  await refresh();
};

// Relaunch from source, for the changes a running window is still missing.
// The new instance shuts this one down over the singleton port as it comes up,
// which is also what saves the window geometry — so there is nothing to do here
// but ask, and nothing to wait for afterwards.
document.getElementById('restart-button').onclick = () => callApi('restart');

window.addEventListener('pywebviewready', refresh);
