const BUCKETS = ['now', 'next', 'someday'];
let state = { projects: [], settings: {}, tasks: [], notes: [], unreadable: [] };
let currentProject = null;

function typeColor(name) {
  const found = (state.settings.types || []).find(t => t.name === name);
  return found ? found.color : '#8e8e8e';
}

// The eight legal Claude Code session colours, on the same Radix scale as the
// default type colours above — a dot and a type tag read as one system, not
// two competing palettes.
const CLAUDE_COLORS = {
  red: '#e5484d', blue: '#0090ff', green: '#30a46c', yellow: '#f5d90a',
  purple: '#8e4ec6', orange: '#f76b15', pink: '#d6409f', cyan: '#00a2c7',
};

// Mirrors typeColor's shape. Task.__post_init__ guarantees every task.color is
// one of the eight names above, so the fallback should never fire — it exists
// so an unrecognised name fails quietly instead of two lookup functions
// disagreeing on how to fail.
function colorHex(name) {
  return CLAUDE_COLORS[name] || '#8e8e8e';
}

// The "avoid colours already in use" heuristic for a freshly captured task —
// lives only here, never in the backend, because it is a suggestion the user
// can override, not a rule anything enforces. Counts each colour's use among
// the project's non-done tasks and picks at random among the names tied for
// fewest, so it spreads new tasks across the palette instead of always
// handing out the same one first.
function suggestColor(project) {
  const counts = Object.fromEntries(Object.keys(CLAUDE_COLORS).map(name => [name, 0]));
  state.tasks
    .filter(t => t.project === project && t.status !== 'done')
    .forEach(t => { if (Object.hasOwn(counts, t.color)) counts[t.color]++; });
  const lowest = Math.min(...Object.values(counts));
  const leastUsed = Object.keys(counts).filter(name => counts[name] === lowest);
  return leastUsed[Math.floor(Math.random() * leastUsed.length)];
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

// Soft banner over the user-configurable WIP limit (default 5, matching the
// user's stated ceiling of concurrent Claude windows). Never blocks an
// action — it exists so an overloaded backlog is visible, not to nag.
function renderWipWarning() {
  const active = state.tasks.filter(t => t.status === 'in-progress').length;
  const limit = state.settings.wip_limit || 5;
  const banner = document.getElementById('wip-warning');
  banner.hidden = active <= limit;
  banner.textContent = `${active} tasks in progress — over your limit of ${limit}`;
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
  picker.onchange = () => { currentProject = picker.value; render(); };
}

async function refresh() {
  try {
    state = await window.pywebview.api.get_state();
  } catch (error) {
    alert(`Could not load your tasks:\n\n${error}`);
    return;
  }
  if (!currentProject && state.projects.length) currentProject = state.projects[0].name;
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
  currentProject = name;
  await refresh();
};

window.addEventListener('pywebviewready', refresh);
