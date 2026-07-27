const BUCKETS = ['now', 'next', 'someday'];
// settings carries an empty `types` rather than being bare {}: this is what is
// on screen between load and the first refresh(), and the buttons are live for
// that whole window. Every reader of state.settings.types indexes or maps it
// immediately — `state.settings.types[0]` in openEditor, `.map` in renderChips
// — so a missing key threw on a fast click at a slow start, and Capture did
// nothing with no error the user could see. Shaping the placeholder like the
// real thing fixes every one of those readers at once, and an empty list is
// the truth at that moment anyway: nothing has been loaded yet.
let state = { projects: [], settings: { types: [] }, tasks: [], notes: [], unreadable: [] };
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

// A date-only string (YYYY-MM-DD) handed to `new Date()` is read as UTC
// midnight, but everything it is then compared against or rendered into is
// local. West of UTC that shifts the date a day earlier, which mislabels a
// month heading and ages a task by one day too many around the boundary.
// Building from local components instead makes an ISO date mean the same day
// it reads as.
//
// One helper rather than the rule written out at each site: this was fixed for
// the progress view's month headings and missed for the staleness marker, and
// two copies of a date rule is precisely how that happens.
function localDate(isoDate) {
  const [year, month, day] = String(isoDate).split('-').map(Number);
  return new Date(year, month - 1, day);
}

function daysSince(isoDate) {
  return Math.floor((Date.now() - localDate(isoDate).getTime()) / 86400000);
}

// A body as the editor draws it, for the places that read one as text rather
// than handing it back to the editor. Three things in a stored body are the
// editor's rather than the user's: escapes on any line that looks like a block
// construct, so a pasted "1. resize the text, then…" is stored as
// "1\. resize the text\, then…" and searching for what you can see matches
// nothing; a literal <br> where two presses of Enter left an empty paragraph;
// and a non-breaking space wherever a paste off a web page put one.
//
// Match-only: nothing here is ever written back. The editor is given the
// stored markdown untouched, because the escapes are what make it round-trip.
// This is the only copy of the rule. The hand-off used to carry a twin of it
// in launcher.py and no longer does: it sends the task file's path, so nothing
// converts a body on its way to a session (invariant 2).
function asShown(body) {
  return String(body)
    .replace(/(?<!\\)<br\s*\/?>/gi, '')
    .replace(/\u00a0/g, ' ')
    .replace(/\\([!-/:-@[-`{-~])/g, '$1');
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
  // After render, and on every refresh rather than only the first: this reads
  // both the stored sizes and the whole-window setting, and the settings
  // overlay's Save is a refresh() — so the header starting or stopping
  // scaling lands here without settings.js knowing anything about zoom.
  // syncZoom lives in zoom.js, which loads after this file; same
  // resolved-at-call-time cross-file pattern as inProgressGroupKeys() below.
  syncZoom();
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

// Escape closes whatever overlay is on top. Every overlay had a mouse-only
// exit, which in an always-on-top window you reach for dozens of times a day is
// the kind of friction that gets noticed once and then endured — so this is one
// handler over all three rather than a fix to whichever one was complained
// about.
//
// Topmost, not first-found: the editor is the one overlay that opens over
// another (a completed entry in Progress opens it with #progress still up, see
// the z-index note in style.css), so it must be offered the key first or
// Escape would close the panel underneath the one you are looking at. The order
// here is the paint order; an overlay added later belongs in it.
//
// Escape is Cancel, deliberately — the editor's own Cancel button discards
// unsaved edits too, and a key that meant something softer than the button next
// to it would be the surprising one. That is why it goes through
// cancelEditor() and not closeEditor(): Cancel asks before throwing away
// something written, so Escape has to ask on exactly the same terms or the two
// stop being the same action.
document.addEventListener('keydown', event => {
  if (event.key !== 'Escape' || event.defaultPrevented) return;
  const editor = document.getElementById('editor');
  if (!editor.hidden) { cancelEditor(); return; }
  for (const id of ['settings', 'progress']) {
    const overlay = document.getElementById(id);
    if (!overlay.hidden) { overlay.hidden = true; return; }
  }
});

window.addEventListener('pywebviewready', refresh);
