// Text size, per region — zoom.js.
//
// Two regions are sized independently: the editor overlay, and everything
// else. Which one a Ctrl+/- lands on is decided by one question — is the
// editor open — so there is no mode to be in and nothing to remember, and it
// is the same rule Escape already uses to pick an overlay.
//
// CSS `zoom`, not a font-size scale and not a transform, because it is the
// only one of the three that REFLOWS: text rewraps and rows re-stack at the
// new size rather than overflowing a box laid out for the old one. Measured in
// this window's engine before it was chosen (see the design doc, 2026-07-26):
// a full-screen `position: fixed` overlay keeps its own viewport size while
// its contents scale, and the document never grows a horizontal scrollbar.
//
// It also leaves the drag geometry (invariant 28) alone without a line of
// change: getBoundingClientRect() returns post-zoom pixels and event.clientX/Y
// are in that same space, so every rectangle the drag measures scales with the
// pointer it is compared against. What does NOT scale is
// getComputedStyle().fontSize, which keeps reporting the unzoomed number —
// anything wanting the effective size must measure a box.

// The range is stated here and in registry.py, the way store.CLAUDE_COLORS and
// state.js's copy of it already are: this clamps before calling, the bridge
// refuses after. Change one and change the other.
//
// 1.0 is a floor, not a default — "a minimum of 100% scale, as it is right
// now". 2.0 is where a 420px-wide window stops holding a readable line.
// Held as a whole number of steps rather than as a factor, so repeated
// presses cannot accumulate into 1.0000000000000002, and derived by division
// rather than multiplication, which 3 * 0.1 would not survive either.
const ZOOM_MIN = 1;
const ZOOM_MAX = 2;
const ZOOM_STEPS_PER_UNIT = 10;
const ZOOM_MAX_STEPS = (ZOOM_MAX - ZOOM_MIN) * ZOOM_STEPS_PER_UNIT;
const ZOOM_BADGE_MS = 900;

// How far each region is scaled, in steps. Seeded from session.json on every
// refresh, so a restart comes back the size it was left.
const zoomSteps = { app: 0, editor: 0 };

function zoomFactor(scope) {
  return ZOOM_MIN + zoomSteps[scope] / ZOOM_STEPS_PER_UNIT;
}

function zoomStepsFor(factor) {
  const steps = Math.round((Number(factor) - ZOOM_MIN) * ZOOM_STEPS_PER_UNIT);
  if (!Number.isFinite(steps)) return 0;
  return Math.min(Math.max(steps, 0), ZOOM_MAX_STEPS);
}

// Which region owns each element, and the one thing the setting changes.
//
// A list rather than a wrapper element: every entry is a top-level element
// that already exists, so nothing about the page's structure has to move for a
// region to gain a member — and an element joins a region by gaining a line
// here rather than by being relocated in the markup.
//
// Progress and Settings are in `app` unconditionally. They are lists of the
// same kind as the one behind them, and a "make the text bigger" that skipped
// two panels would read as those panels being unfinished. So the setting names
// exactly one difference — whether the header and toolbar come along — which
// is the only way a difference like this stays legible.
//
// Every element is listed on every call, in or out, because the scope it is
// NOT in has to be cleared: turning the setting off must put the header back
// to its own size rather than leaving it at whatever it was last scaled to.
function zoomAssignments() {
  const chrome = state.settings && state.settings.zoom_whole_window ? 'app' : null;
  return [
    ['editor', 'editor'],
    ['task-list', 'app'],
    ['selection-bar', 'app'],
    ['group-limit-warning', 'app'],
    ['unreadable-warning', 'app'],
    ['progress', 'app'],
    ['settings', 'app'],
    ['app-header', chrome],
    ['toolbar', chrome],
  ];
}

function applyZoom() {
  for (const [id, scope] of zoomAssignments()) {
    const element = document.getElementById(id);
    if (!element) continue;
    element.style.zoom = scope ? String(zoomFactor(scope)) : '';
  }
}

// Called from refresh() once state has arrived — which is also what re-reads
// the whole-window setting after the settings overlay saves it.
function syncZoom() {
  const stored = (state && state.zoom) || {};
  for (const scope of Object.keys(zoomSteps)) {
    zoomSteps[scope] = zoomStepsFor(stored[scope]);
  }
  applyZoom();
}

let zoomBadgeTimer = null;

// Zooming is its own evidence — everything gets bigger — with one exception:
// at either end of the ladder the key press changes nothing at all, and a key
// that silently does nothing is indistinguishable from a key that is broken.
// So the size is always reported, and the ends say why they are the ends.
function showZoomBadge(scope, refused) {
  const badge = document.getElementById('zoom-badge');
  const percent = `${Math.round(zoomFactor(scope) * 100)}%`;
  const limit = zoomSteps[scope] === 0 ? 'smallest' : 'largest';
  badge.textContent = refused ? `${percent} · ${limit}` : percent;
  badge.hidden = false;
  clearTimeout(zoomBadgeTimer);
  zoomBadgeTimer = setTimeout(() => { badge.hidden = true; }, ZOOM_BADGE_MS);
}

function setZoomSteps(scope, wanted) {
  const next = Math.min(Math.max(wanted, 0), ZOOM_MAX_STEPS);
  const refused = next === zoomSteps[scope];
  zoomSteps[scope] = next;
  applyZoom();
  showZoomBadge(scope, refused);
  // Nothing moved, so there is nothing to remember — and a write per refused
  // keypress is a file rewritten for no reason at the exact moment the user is
  // leaning on the key.
  if (!refused) callApi('set_zoom', scope, zoomFactor(scope));
}

// `+` needs Shift on a US layout, so Shift is permitted; Alt and Meta are not,
// so nothing here shadows a system chord. Both the character and the physical
// key are accepted: `event.key` is what a layout produces, `event.code` is
// what the numpad sends whatever the layout.
function zoomIntent(event) {
  if (!event.ctrlKey || event.altKey || event.metaKey) return null;
  if (event.key === '+' || event.key === '=' || event.code === 'NumpadAdd') return 'in';
  if (event.key === '-' || event.key === '_' || event.code === 'NumpadSubtract') return 'out';
  if (event.key === '0' || event.code === 'Numpad0') return 'reset';
  return null;
}

// On the document, not on either region: the key means "make what I am looking
// at bigger", and what the user is looking at is decided below rather than by
// whichever element happens to hold focus. Typing in the editor body and
// pressing Ctrl+ must still zoom the editor.
document.addEventListener('keydown', event => {
  const intent = zoomIntent(event);
  if (!intent) return;
  // preventDefault regardless of whether anything moves: at the ladder's end
  // the press is still ours, and letting it fall through would hand the host a
  // zoom key we have just told the user did nothing.
  event.preventDefault();
  const scope = document.getElementById('editor').hidden ? 'app' : 'editor';
  if (intent === 'reset') { setZoomSteps(scope, 0); return; }
  setZoomSteps(scope, zoomSteps[scope] + (intent === 'in' ? 1 : -1));
});
