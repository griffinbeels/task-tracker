// Drag harness — NOT part of the test suite, by decision (2026-07-27).
//
// An automated behavioural suite for the drag was offered and declined; this is
// the reversal path for that decision, and the record of what such a suite can
// see. Nothing runs it. `node build-app-harness.js` writes three HTML files,
// each of which loads the REAL ui/*.js against a stubbed `window.pywebview.api`
// and drives synthetic pointer events:
//
//   app-harness.html   70 assertions: the card, Reardon's aiming rule, the
//                      motion sampled mid-transition, the settle's ordering,
//                      leaving a group, enter and exit
//   app-scroll.html    autoscroll, in a window short enough to scroll
//   app-hold.html      frozen mid-drag, for a screenshot
//
// Run one with:
//   chrome.exe --headless=new --disable-gpu --allow-file-access-from-files \
//     --window-size=520,1200 --virtual-time-budget=40000 \
//     --user-data-dir=<ABSOLUTE windows path> --dump-dom <the html> > dump.html
// then read the <pre id="results"> out of the dump.
//
// It found six bugs in one session, every one invisible in a diff: a card that
// never appeared, 672px of tracking drift, a drop that also opened the editor,
// six document-wide queries that could not tell a clone from a row, a keyboard
// activation eaten by the click suppressor, and a displacement curve 35%
// travelled by its first painted frame.
//
// Two things about the environment, or it will accuse working code (both are
// also in ~/.claude/rules/spawned-processes.md): the virtual-time budget
// advances setTimeout but NOT the document timeline, so animations sit at t=0
// and must be driven via `animation.currentTime`; and a backtick anywhere inside
// the template literals below terminates one early, with a SyntaxError naming a
// random identifier from the following prose.
//
// The UI constant below points at a worktree that no longer exists. Repoint it
// at this checkout's `ui/` before running.

// Drive the REAL ui/*.js with a stubbed bridge and synthetic pointer events.
// Not the test suite that was declined — a one-off, in the scratchpad, so a UI
// change is not handed over on the strength of its diff.
const fs = require('fs');
const UI = 'C:/Users/griff/Desktop/code/task_tracker/.claude/worktrees/drag-animation/ui';

// NOTE, having cost four rounds: a backtick anywhere inside the STUB / TEST /
// SCROLL / HOLD template literals below — including inside a comment — terminates
// that literal early, and the SyntaxError then names whatever identifier happened
// to follow it. If this file fails to parse on an identifier that looks fine, grep
// for a backtick in a payload. A guard cannot help: the failure is at parse time,
// before any code in the file runs.

const markup = fs.readFileSync(UI + '/index.html', 'utf8');
const body = markup.slice(markup.indexOf('<body>') + 6, markup.indexOf('</body>'));
// The <link> tags live in <head>, and leaving them out is not a small omission:
// with no stylesheet EVERY assertion about position, visibility or opacity reads
// the browser default and looks like the rule failing to match. That cost a round
// here — .held reported `position: static` and the card was never styled at all.
const head = markup.slice(markup.indexOf('<head>') + 6, markup.indexOf('</head>'));

const STUB = `
<script>
// Every bridge method answers; get_state answers with a fixture. A Proxy rather
// than a list, so a method added later needs no change here.
const CALLS = [];
const TASKS = [
  { id: 1, project: 'demo', title: 'Stray line by the meatball button', type: 'bug',
    color: 'red', bucket: 'now', group: null, status: 'open', order: 0,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 2, project: 'demo', title: 'Focus ring on chips', type: 'feat',
    color: 'blue', bucket: 'now', group: 'Editor polish', status: 'open', order: 1,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 3, project: 'demo', title: 'Paste image at cursor', type: 'feat',
    color: 'cyan', bucket: 'now', group: 'Editor polish', status: 'open', order: 2,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 4, project: 'demo', title: 'Reorder IN PROGRESS', type: 'feat',
    color: 'green', bucket: 'now', group: null, status: 'open', order: 3,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 5, project: 'demo', title: 'Write the invariant', type: 'docs',
    color: 'purple', bucket: 'next', group: null, status: 'open', order: 0,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 6, project: 'demo', title: 'Fold survives rename', type: 'bug',
    color: 'yellow', bucket: 'next', group: null, status: 'open', order: 1,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 7, project: 'demo', title: 'Keyboard-only reorder', type: 'feat',
    color: 'orange', bucket: 'someday', group: null, status: 'open', order: 0,
    created: '2026-07-20', started: null, done: null, body: 'x' },
  { id: 8, project: 'demo', title: 'Only member', type: 'chore',
    color: 'pink', bucket: 'someday', group: 'Solo', status: 'open', order: 1,
    created: '2026-07-20', started: null, done: null, body: 'x' },
];
const STATE = {
  projects: [{ name: 'demo', path: 'C:/demo', tracked: false, launch: null }],
  settings: { group_limit: 5, stale_days: 90, zoom_whole_window: false,
              always_on_top: false,
              types: [{ name: 'bug', color: '#e5484d' }, { name: 'feat', color: '#0090ff' },
                      { name: 'docs', color: '#8e8e8e' }, { name: 'chore', color: '#f76b15' }] },
  tasks: TASKS, notes: [], unreadable: [], last_project: 'demo',
  collapsed: { projects: [], groups: [] }, zoom: { app: 1, editor: 1 },
  in_progress_order: [],
};
window.pywebview = { api: new Proxy({}, { get: (_, name) => (...args) => {
  CALLS.push({ name, args });
  if (name === 'get_state') return Promise.resolve(JSON.parse(JSON.stringify(STATE)));
  if (name === 'suggest_session_name') return Promise.resolve('');
  if (name === 'create_group') return Promise.resolve('Stray line by the meatball button');
  // Applied for real, so a render after it actually removes a block — which is the
  // only way an exit animation can be observed at all.
  if (name === 'complete_tasks') {
    const [project, ids] = args;
    TASKS.filter(each => each.project === project && ids.includes(each.id))
      .forEach(each => { each.status = 'done'; each.done = '2026-07-27'; });
  }
  return Promise.resolve(null);
} }) };
window.__CALLS = CALLS;
window.__TASKS = TASKS;
window.alert = message => { CALLS.push({ name: 'ALERT', args: [String(message)] }); };
</script>
`;

const TEST = `
<pre id="results" style="position:fixed;left:0;bottom:0;width:100%;background:#000;color:#0f0;font:11px/1.5 Consolas;white-space:pre-wrap;z-index:99;margin:0;padding:6px">EMPTY</pre>
<script>
(async function () {
  const out = [];
  const log = (name, ok, detail) =>
    out.push((ok ? 'PASS  ' : 'FAIL  ') + name + (detail ? '   [' + detail + ']' : ''));
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const idx = el => [...el.parentElement.children].indexOf(el);
  const rows = () => [...document.querySelectorAll('#task-list section[data-bucket="now"] > .task')];
  const held = () => document.querySelector('#drag-layer .held');
  function pt(type, x, y, target) {
    (target || window).dispatchEvent(new PointerEvent(type, {
      clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0,
      buttons: type === 'pointerup' ? 0 : 1,
      pointerId: 1, isPrimary: true, pointerType: 'mouse' }));
  }

  try {
    window.dispatchEvent(new Event('pywebviewready'));
    await sleep(400);
    log('S0  the app rendered', rows().length > 0, rows().length + ' loose NOW rows');
    log('S0b no bridge call failed', !window.__CALLS.some(c => c.name === 'ALERT'),
        JSON.stringify(window.__CALLS.filter(c => c.name === 'ALERT')));
    log('S0c no draggable attribute survives anywhere',
        document.querySelectorAll('[draggable]').length === 0,
        document.querySelectorAll('[draggable]').length + ' found');

    const row = rows()[0];
    const box = row.getBoundingClientRect();
    const grabX = 90, grabY = box.height - 2;   // grabbed LOW, the worst case
    const startX = box.left + grabX, startY = box.top + grabY;

    // ---- the threshold ----
    pt('pointerdown', startX, startY, row);
    pt('pointermove', startX + 2, startY);
    log('T1  a 2px move is a click, not a drag', held() === null);
    pt('pointermove', startX + 6, startY);
    log('T2  a 6px move lifts the card', Boolean(held()));

    // ---- the card ----
    const card = held();
    const style = getComputedStyle(card);
    log('T3  the card is fixed, opaque and in the drag layer',
        style.position === 'fixed' && style.opacity === '1'
        && card.parentElement.id === 'drag-layer',
        style.position + ' opacity ' + style.opacity + ' in #' + card.parentElement.id);
    log('T4  the card carries the row\\'s own text',
        card.querySelector('.title').textContent === row.querySelector('.title').textContent,
        JSON.stringify(card.querySelector('.title').textContent));
    log('T5  the source row is the gap',
        row.classList.contains('dragging-source')
        && getComputedStyle(row.querySelector('.title')).visibility === 'hidden');
    log('T6  the gap keeps its box, so nothing reflowed',
        Math.abs(row.getBoundingClientRect().height - box.height) < 0.5,
        row.getBoundingClientRect().height.toFixed(1) + ' vs ' + box.height.toFixed(1));
    log('T7  body is in the dragging state', document.body.classList.contains('dragging'));

    // ---- tracking, 1:1 and rail-locked ----
    let worstY = 0, worstX = 0;
    for (const dy of [30, 80, 140, 210]) {
      pt('pointermove', startX + 40, startY + dy);
      const at = held().getBoundingClientRect();
      worstY = Math.max(worstY, Math.abs(at.top - (startY + dy - grabY)));
      worstX = Math.max(worstX, Math.abs(at.left - box.left));
    }
    log('T8  the card tracks the pointer vertically with no lag', worstY < 2,
        'worst ' + worstY.toFixed(2) + 'px');
    log('T9  the card is rail-locked despite 40px of sideways pointer', worstX < 2,
        'worst ' + worstX.toFixed(2) + 'px');

    // ---- the drop writes, once, with the right shape ----
    // Aimed at NEXT's heading: the top of that bucket, ungrouped, and clear of
    // any row's middle third. Landing in a middle third is a PAIR, which is
    // correct behaviour and calls create_group instead — that cost a round here.
    const nextHead = document.querySelector('#task-list section[data-bucket="next"] h2');
    const nh = nextHead.getBoundingClientRect();
    pt('pointermove', nh.left + 90, nh.top + nh.height / 2);
    const before = window.__CALLS.length;
    pt('pointerup', nh.left + 90, nh.top + nh.height / 2);
    await sleep(400);
    const written = window.__CALLS.slice(before);
    const placed = written.filter(c => c.name === 'place_task');
    log('T10 the drop wrote exactly one placement', placed.length === 1,
        written.map(c => c.name).join(', ') || 'nothing');
    log('T11 it named the row\\'s own project and id',
        placed.length === 1 && placed[0].args[0] === 'demo' && placed[0].args[1] === 1,
        placed.length ? JSON.stringify(placed[0].args.slice(0, 3)) : 'n/a');
    log('T12 the card and the gap are both gone', held() === null
        && document.querySelectorAll('.dragging-source').length === 0);
    log('T13 the dragging state is cleared', !document.body.classList.contains('dragging'));

    // ---- the click a drag ends in must not open the editor ----
    const editor = document.getElementById('editor');
    const target = rows()[0];
    const tb = target.getBoundingClientRect();
    pt('pointerdown', tb.left + 90, tb.top + tb.height / 2, target);
    pt('pointermove', tb.left + 96, tb.top + tb.height / 2);
    pt('pointermove', tb.left + 96, tb.top + tb.height / 2 + 60);
    pt('pointerup', tb.left + 96, tb.top + tb.height / 2 + 60);
    target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }));
    await sleep(300);
    log('T14 the click a drag ends in does NOT open the editor', editor.hidden,
        editor.hidden ? 'closed' : 'OPEN — every drop would open it');

    // ---- but a real click still does ----
    const clickable = rows()[0];
    const cb = clickable.getBoundingClientRect();
    pt('pointerdown', cb.left + 90, cb.top + cb.height / 2, clickable);
    pt('pointerup', cb.left + 90, cb.top + cb.height / 2);
    clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, detail: 1 }));
    await sleep(300);
    log('T15 a click with no drag still opens the editor', !editor.hidden,
        editor.hidden ? 'stayed closed — click-to-edit is broken' : 'opened');
    if (!editor.hidden) document.getElementById('editor-cancel').click();
    await sleep(200);

    // ---- Escape mid-drag writes nothing ----
    const esc = rows()[0];
    const eb = esc.getBoundingClientRect();
    const whereWas = idx(esc);
    const callsBefore = window.__CALLS.length;
    pt('pointerdown', eb.left + 90, eb.top + eb.height / 2, esc);
    pt('pointermove', eb.left + 96, eb.top + eb.height / 2);
    pt('pointermove', eb.left + 96, eb.top + eb.height / 2 + 200);
    const movedTo = idx(esc);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(300);
    log('T16 the drag previewed somewhere else', movedTo !== whereWas,
        whereWas + ' -> ' + movedTo);
    log('T17 Escape puts it back and writes NOTHING',
        idx(esc) === whereWas && window.__CALLS.length === callsBefore,
        'index ' + idx(esc) + ', ' + (window.__CALLS.length - callsBefore) + ' calls');
    log('T18 Escape leaves no card behind', held() === null);

    // ================= Reardon's rule =================
    // NEXT holds two loose rows and no group, so nothing else competes and the
    // only question is when row 0 yields to row 1.
    const next = document.querySelector('#task-list section[data-bucket="next"]');
    const nextRows = () => [...next.querySelectorAll(':scope > .task')];
    const [rowP, rowQ] = nextRows();
    const pBox = rowP.getBoundingClientRect();
    const qTop = rowQ.getBoundingClientRect().top;
    // Grabbed two pixels above its OWN bottom edge — the worst case for a rule
    // that aims with the pointer, and an entirely ordinary way to pick a row up.
    const lowX = pBox.left + 90, lowY = pBox.bottom - 2;
    const grabLowY = pBox.height - 2;

    pt('pointerdown', lowX, lowY, rowP);
    pt('pointermove', lowX + 6, lowY);
    const twitched = idx(rowP);
    log('R1  a 6px SIDEWAYS twitch on a low grab reorders nothing',
        twitched === 1, 'index ' + twitched + ' (was 1)');

    let trigger = null;
    for (let step = 0; step <= 120 && trigger === null; step++) {
      pt('pointermove', lowX, lowY + step);
      if (idx(rowP) !== 1) trigger = lowY + step;
    }
    const centreAt = trigger === null ? null : trigger - grabLowY + pBox.height / 2;
    log('R2  it yields as the CARD\\'s centre reaches Q\\'s top edge',
        trigger !== null && Math.abs(centreAt - qTop) <= 2,
        trigger === null ? 'never triggered'
          : 'card centre ' + centreAt.toFixed(1) + ' vs Q.top ' + qTop.toFixed(1)
            + '  (off by ' + (centreAt - qTop).toFixed(1) + 'px)');

    // The threshold must not move: every reading below it index 1, above it 2.
    const low = [], high = [];
    for (let n = 0; n < 10; n++) {
      pt('pointermove', lowX, trigger - 0.5); low.push(idx(rowP));
      pt('pointermove', lowX, trigger + 0.5); high.push(idx(rowP));
    }
    log('R3  20 crossings at +/-0.5px never drift',
        low.every(v => v === 1) && high.every(v => v === 2),
        'below ' + [...new Set(low)].join('/') + '  above ' + [...new Set(high)].join('/'));

    // The freeze is doing work: carry the row into SOMEDAY, which shortens NEXT
    // and moves every box below it, and confirm the LIVE layout really did move
    // while the aim kept using the frozen one.
    const someday = document.querySelector('#task-list section[data-bucket="someday"]');
    const frozenSomedayTop = someday.getBoundingClientRect().top;
    pt('pointermove', lowX, frozenSomedayTop + 14 + grabLowY - pBox.height / 2);
    const liveSomedayTop = someday.getBoundingClientRect().top;
    log('R4  the live layout moved under the gesture',
        Math.abs(liveSomedayTop - frozenSomedayTop) > 2,
        'SOMEDAY top ' + frozenSomedayTop.toFixed(0) + ' -> ' + liveSomedayTop.toFixed(0));
    log('R4b and the row still previews in SOMEDAY, not where the box now is',
        rowP.closest('section') === someday,
        'landed in ' + (rowP.closest('section').dataset.bucket || 'in-progress'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(300);
    log('R5  Escape after all of that restores NEXT', idx(rowP) === 1,
        'index ' + idx(rowP));

    // ================= the motion =================
    // Sampled MID-transition, deliberately. Both end states of a displacement
    // already look right, which is exactly how a snap survives end-state-only
    // review — the only way to tell 200ms of sliding from an instant jump is to
    // look while it is happening.
    const translateY = element => {
      const matrix = new DOMMatrixReadOnly(getComputedStyle(element).transform);
      return matrix.m42;
    };
    const [fP, fQ] = nextRows();
    const fBox = fP.getBoundingClientRect();
    const fx = fBox.left + 90, fy = fBox.top + fBox.height / 2;
    const qBefore = fQ.getBoundingClientRect().top;

    const wasAt = idx(fP);
    pt('pointerdown', fx, fy, fP);
    pt('pointermove', fx + 6, fy);
    // Card centre in Q's BOTTOM third: past Q's top edge so Q must move, and clear
    // of the middle third, which pairs instead of reordering. Aiming at the middle
    // cost two rounds — it reports as "nothing animated", because a pair sets no
    // preview at all and every end-state assertion then passes trivially.
    pt('pointermove', fx, qBefore + fBox.height - 3);

    // Asserted FIRST, so a mis-aimed test can never look like a passing one.
    log('F0  the row actually reordered', idx(fP) !== wasAt,
        'index ' + wasAt + ' -> ' + idx(fP));
    const running = fQ.getAnimations();
    log('F1  the displaced row is ANIMATING, not snapped', running.length === 1,
        running.length + ' animations on it');
    const full = Math.abs(translateY(fQ));
    log('F2  and at t=0 it is offset by a whole row, not zero',
        full > fBox.height * 0.6, 'translateY ' + full.toFixed(1)
        + 'px vs row height ' + fBox.height.toFixed(1));

    // The animation's OWN clock, driven by hand. Chrome's virtual-time budget
    // advances setTimeout but not the document timeline, so sleeping and
    // re-reading the computed transform returns t=0 forever — which reads as the
    // animation being broken and is really the harness having no frames. Setting
    // currentTime samples the real interpolation deterministically, which is a
    // better test than waiting for a clock in any case.
    const animation = running[0];
    const wallClockAdvances = document.timeline.currentTime;
    animation.pause();
    animation.currentTime = 100;
    const halfway = Math.abs(translateY(fQ));
    log('F3  halfway through, it is BETWEEN the two positions',
        halfway > 0.5 && halfway < full - 0.5,
        'translateY ' + halfway.toFixed(1) + 'px, between 0 and ' + full.toFixed(1));
    animation.currentTime = 200;
    log('F4  at the end it lands exactly on its new place',
        Math.abs(translateY(fQ)) < 0.5, 'translateY ' + translateY(fQ).toFixed(2) + 'px');
    log('F4b the easing is not linear — 100ms of 200ms is past halfway',
        halfway < full * 0.5, halfway.toFixed(1) + 'px remaining of ' + full.toFixed(1)
        + ' (linear would be ' + (full / 2).toFixed(1) + ')');
    animation.finish();
    log('F5  the gap itself never animates — it IS the slot',
        fP.getAnimations().length === 0, fP.getAnimations().length + ' on the gap');

    // Reversing direction must produce a fresh animation back the other way.
    pt('pointermove', fx, fy);
    const reversing = fQ.getAnimations();
    const reverseFrom = reversing.length ? Math.abs(translateY(fQ)) : 0;
    log('F6  reversing mid-drag animates it back',
        reversing.length === 1 && reverseFrom > 0.5,
        reversing.length + ' animation, starts at ' + reverseFrom.toFixed(1) + 'px'
        + '  (timeline was ' + (wallClockAdvances === null ? 'null' : 'live') + ')');
    reversing.forEach(each => each.finish());

    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(400);
    log('F7  Escape leaves every transform cleared',
        Math.abs(translateY(fQ)) < 0.5 && Math.abs(translateY(fP)) < 0.5,
        'Q ' + translateY(fQ).toFixed(2) + '  P ' + translateY(fP).toFixed(2));
    log('F8  and the order is back', idx(fP) === 1, 'index ' + idx(fP));

    // ================= leaving a group =================
    const group = document.querySelector('#task-list section[data-bucket="now"] .group');
    const gMembers = [...group.querySelectorAll('.task')];
    const gBox = group.getBoundingClientRect();

    // The LAST member must not fall out of its own group on the first pixel. This
    // is the regression a tempting fix introduced: measuring the group as it will
    // be once the member has left puts bottom-minus-own-height ABOVE that
    // member's own centre, so it starts outside.
    const last = gMembers[gMembers.length - 1];
    const lBox = last.getBoundingClientRect();
    pt('pointerdown', lBox.left + 90, lBox.top + lBox.height / 2, last);
    pt('pointermove', lBox.left + 96, lBox.top + lBox.height / 2);
    log('G1  the last member does not leave its group on the first move',
        last.closest('.group') === group,
        'still in ' + (last.closest('.group') ? 'the group' : 'NOTHING'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(300);

    // And carrying a member clear of the block's bottom must REORDER, not pair
    // with whatever row is down there. That window was 4px wide before
    // GROUP_STICKY went; it is 13.3px now.
    const middle = [...group.querySelectorAll('.task')][0];
    const mBox = middle.getBoundingClientRect();
    pt('pointerdown', mBox.left + 90, mBox.top + mBox.height / 2, middle);
    pt('pointermove', mBox.left + 96, mBox.top + mBox.height / 2);
    // Card centre 4px below the group's real bottom edge: outside the group, and
    // inside the 13.3px of reorder that now precedes the next row's pair band.
    pt('pointermove', mBox.left + 90, gBox.bottom + 4);
    const left = middle.closest('.group') === null;
    const paired = document.querySelectorAll('#task-list .task.drop-into').length > 0;
    log('G2  4px past the group bottom is OUT of the group', left,
        left ? 'loose' : 'still in ' + middle.closest('.group').dataset.group);
    log('G3  and it reorders rather than pairing with the next row', !paired,
        paired ? 'a row is outlined for pairing' : 'no pair target');
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(300);
    log('G4  Escape puts it back in the group', middle.closest('.group') === group);

    // ================= the settle =================
    const loose = document.querySelector('#task-list section[data-bucket="now"] > .task');
    const sBox = loose.getBoundingClientRect();
    const sHead = document.querySelector(
      '#task-list section[data-bucket="someday"] h2').getBoundingClientRect();
    const callsAtRelease = window.__CALLS.length;
    pt('pointerdown', sBox.left + 90, sBox.top + sBox.height / 2, loose);
    pt('pointermove', sBox.left + 96, sBox.top + sBox.height / 2);
    pt('pointermove', sBox.left + 90, sHead.top + sHead.height / 2);
    pt('pointerup', sBox.left + 90, sHead.top + sHead.height / 2);

    // Synchronously after release: the card is in the air and the gap is still a
    // gap. Sequential, per Reardon — a placeholder collapsing while the thing that
    // fills it is still flying is the specific mistake he names.
    const flying = document.querySelector('#drag-layer .held');
    log('S1  the card is still in the air right after release', Boolean(flying),
        flying ? 'flying' : 'already gone — the drop cut instead of settling');
    log('S2  the gap is still open under it',
        document.querySelectorAll('#task-list .dragging-source').length === 1);
    const flight = flying ? flying.getAnimations() : [];
    log('S3  the flight is a transform animation', flight.length === 1,
        flight.length + ' animations on the card');
    log('S4  nothing has been WRITTEN yet — the write waits for the flight',
        window.__CALLS.length === callsAtRelease,
        (window.__CALLS.length - callsAtRelease) + ' calls so far');

    await sleep(700);
    log('S5  the card is gone and the gap has closed',
        document.querySelector('#drag-layer .held') === null
        && document.querySelectorAll('#task-list .dragging-source').length === 0);
    const wrote = window.__CALLS.slice(callsAtRelease).map(c => c.name);
    log('S6  and only THEN did it write', wrote.includes('place_task'),
        wrote.join(', ') || 'nothing');
    const landed = [...document.querySelectorAll('#task-list .task')].find(
      candidate => candidate.dataset.project === loose.dataset.project
        && candidate.dataset.id === loose.dataset.id);
    // The FLASH specifically, by what it animates rather than by a count: the
    // render's own FLIP may legitimately be running on this row at the same time
    // — it does here, because the stub does not apply writes, so the redraw puts
    // the row back where it was and that displacement is real and worth seeing.
    const flashing = landed ? landed.getAnimations().filter(each => {
      const frames = each.effect && each.effect.getKeyframes
        ? each.effect.getKeyframes() : [];
      return frames.some(frame => 'backgroundColor' in frame);
    }) : [];
    log('S7  the row that moved is flashing', flashing.length === 1,
        landed ? flashing.length + ' background animations of '
                 + landed.getAnimations().length + ' total' : 'row not found');

    // An abandoned drag flies home and must NOT flash: nothing moved.
    const back = document.querySelector('#task-list section[data-bucket="now"] > .task');
    const bBox = back.getBoundingClientRect();
    pt('pointerdown', bBox.left + 90, bBox.top + bBox.height / 2, back);
    pt('pointermove', bBox.left + 96, bBox.top + bBox.height / 2);
    pt('pointermove', bBox.left + 90, sHead.top + sHead.height / 2);
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    const homing = document.querySelector('#drag-layer .held');
    log('S8  an abandoned card flies home rather than vanishing', Boolean(homing));
    await sleep(700);
    log('S9  and leaves nothing behind and no flash',
        document.querySelector('#drag-layer .held') === null
        && back.getAnimations().length === 0,
        back.getAnimations().length + ' animations on the row');

    // ================= the render animates too =================
    // Folding is the cleanest driver: toggleGroupCollapsed changes local state and
    // calls render() synchronously, before it persists anything, so no bridge
    // round-trip stands between the click and the redraw.
    const foldGroup = document.querySelector('#task-list section[data-bucket="now"] .group');
    const below = [...document.querySelectorAll('#task-list section[data-bucket="now"] > *')]
      .filter(block => block.getBoundingClientRect().top > foldGroup.getBoundingClientRect().bottom);
    document.querySelectorAll('#task-list .task, #task-list .group')
      .forEach(each => each.getAnimations().forEach(a => a.cancel()));
    foldGroup.querySelector('.caret').click();
    await sleep(20);
    const movedByFold = [...document.querySelectorAll(
      '#task-list section[data-bucket="now"] > .task, #task-list section[data-bucket="now"] > .group')]
      .filter(block => block.getAnimations().length > 0);
    log('D1  folding a group animates what moves under it',
        below.length === 0 || movedByFold.length > 0,
        below.length + ' blocks were below it, ' + movedByFold.length + ' are animating');
    log('D2  the animation survived replaceChildren — matched by key, not identity',
        movedByFold.every(block => block.isConnected),
        movedByFold.length + ' animating blocks are all in the document');
    // Driven to completion rather than waited for: the document timeline does not
    // advance under Chrome's virtual-time budget, so these sit at t=0 with the full
    // offset applied and no amount of sleeping clears them. What this asserts is
    // the property that matters — the FLIP declares no fill, so finishing it
    // reverts the transform rather than stranding it.
    document.getAnimations().forEach(each => each.finish());
    const stuck = [...document.querySelectorAll('#task-list .task, #task-list .group')]
      .filter(block => Math.abs(translateY(block)) > 0.5)
      .map(block => (block.querySelector('.title') || block.querySelector('.group-name'))
        .textContent.slice(0, 22) + ' @' + translateY(block).toFixed(1)
        + ' anims=' + block.getAnimations().length);
    log('D3  and every transform is cleared afterwards', stuck.length === 0,
        stuck.join(' | ') || 'all clear');
    foldGroup.querySelector('.caret') && document
      .querySelector('#task-list section[data-bucket="now"] .group .caret').click();
    await sleep(400);

    // The guard: search re-renders on every keystroke, so it must NOT animate.
    document.querySelectorAll('#task-list .task, #task-list .group')
      .forEach(each => each.getAnimations().forEach(a => a.cancel()));
    const search = document.getElementById('search');
    search.value = 'e';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(20);
    log('D4  typing in the search box animates nothing',
        document.getAnimations().length === 0,
        document.getAnimations().length + ' animations running');
    search.value = '';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(20);
    log('D5  and coming back out of search animates nothing either',
        document.getAnimations().length === 0,
        document.getAnimations().length + ' animations running');

    // ================= the group about to be deleted =================
    search.value = '';
    search.dispatchEvent(new Event('input', { bubbles: true }));
    await sleep(300);
    const solo = [...document.querySelectorAll('#task-list .group')].find(
      each => each.dataset.group === 'Solo');
    const soloRow = solo.querySelector('.task');
    const srBox = soloRow.getBoundingClientRect();
    const nextBox = document.querySelector(
      '#task-list section[data-bucket="next"] h2').getBoundingClientRect();
    pt('pointerdown', srBox.left + 90, srBox.top + srBox.height / 2, soloRow);
    pt('pointermove', srBox.left + 96, srBox.top + srBox.height / 2);
    log('E1  its own group is NOT faded while the row is still inside it',
        !solo.classList.contains('emptying'));
    pt('pointermove', srBox.left + 90, nextBox.top + nextBox.height / 2);
    // The class, and then the fade DRIVEN to its end. Reading computed opacity
    // synchronously returns 1 — .group declares a transition on opacity, so the value
    // starts where it was and travels, which is the point of it. An end-state read
    // at t=0 sees the old state and reads as the rule not applying.
    const marked = solo.classList.contains('emptying');
    const fading = solo.getAnimations().length;
    solo.getAnimations().forEach(each => each.finish());
    const faded = Number(getComputedStyle(solo).opacity);
    log('E2  carrying the LAST member out fades the group it empties',
        marked && fading > 0 && faded < 1,
        'class=' + marked + ' transitions=' + fading + ' opacity settles to ' + faded);
    pt('pointermove', srBox.left + 90, srBox.top + srBox.height / 2);
    log('E3  moving back inside lifts the fade',
        !solo.classList.contains('emptying'));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(400);
    log('E4  and nothing is left faded after the drag',
        document.querySelectorAll('#task-list .emptying').length === 0);

    const pair2 = [...document.querySelectorAll('#task-list .group')].find(
      each => each.querySelectorAll('.task').length > 1);
    const pRow = pair2.querySelector('.task');
    const prBox = pRow.getBoundingClientRect();
    pt('pointerdown', prBox.left + 90, prBox.top + prBox.height / 2, pRow);
    pt('pointermove', prBox.left + 96, prBox.top + prBox.height / 2);
    pt('pointermove', prBox.left + 90, nextBox.top + nextBox.height / 2);
    log('E5  a group that SURVIVES a member leaving does not fade',
        !pair2.classList.contains('emptying'),
        pair2.querySelectorAll('.task').length + ' members drawn');
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(400);

    // ================= the easing starts from rest =================
    const easingRows = [...document.querySelectorAll(
      '#task-list section[data-bucket="next"] > .task')];
    const eP = easingRows[0], eQ = easingRows[1];
    const eBox = eP.getBoundingClientRect();
    const eqTop = eQ.getBoundingClientRect().top;
    document.getAnimations().forEach(each => each.cancel());
    pt('pointerdown', eBox.left + 90, eBox.top + eBox.height / 2, eP);
    pt('pointermove', eBox.left + 96, eBox.top + eBox.height / 2);
    pt('pointermove', eBox.left + 90, eqTop + eBox.height - 3);
    const slide = eQ.getAnimations()[0];
    if (!slide) { log('E6  a neighbour is displaced', false, 'nothing animating'); }
    else {
      const full = Math.abs(translateY(eQ));
      slide.pause();
      slide.currentTime = 16;
      const firstFrame = full - Math.abs(translateY(eQ));
      log('E6  by the first painted frame it has barely started moving',
          firstFrame / full < 0.10,
          'travelled ' + (100 * firstFrame / full).toFixed(0) + '% of ' + full.toFixed(0)
          + 'px at 16ms  (the old curve was 35%)');
      slide.currentTime = 100;
      const half = full - Math.abs(translateY(eQ));
      log('E7  and it is genuinely mid-flight halfway through',
          half / full > 0.3 && half / full < 0.95,
          'travelled ' + (100 * half / full).toFixed(0) + '% at 100ms');
      slide.finish();
    }
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    await sleep(400);

    // ================= arriving and leaving =================
    const doomedRow = document.querySelector('#task-list section[data-bucket="next"] > .task');
    const doomedId = Number(doomedRow.dataset.id);
    document.getAnimations().forEach(each => each.cancel());
    doomedRow.querySelector('.done').click();
    await sleep(400);
    const corpse = document.querySelector('#drag-layer .leaving');
    log('X1  a completed row leaves as itself, in the drag layer', Boolean(corpse),
        corpse ? 'one .leaving element' : 'it just vanished');
    if (corpse) {
      const fade = corpse.getAnimations();
      const style = getComputedStyle(corpse);
      log('X2  it is fading, fixed, and positioned where the row used to be',
          fade.length === 1 && style.position === 'fixed'
          && parseFloat(style.top) !== 0,
          fade.length + ' animations, ' + style.position + ' at top ' + style.top);
      log('X3  and it is not in the list any more',
          !corpse.closest('#task-list'),
          corpse.parentElement.id);
      document.getAnimations().forEach(each => each.finish());
      await sleep(50);
      log('X4  the corpse removes itself when the fade ends',
          document.querySelectorAll('#drag-layer .leaving').length === 0,
          document.querySelectorAll('#drag-layer .leaving').length + ' left behind');
    }
    log('X5  the row really is gone from the list',
        ![...document.querySelectorAll('#task-list .task')].some(
          each => Number(each.dataset.id) === doomedId));

    // Arriving: exactly what Restore does at the data level.
    document.getAnimations().forEach(each => each.cancel());
    window.__TASKS.find(each => each.id === doomedId).status = 'open';
    await refresh();
    await sleep(30);
    const returned = [...document.querySelectorAll('#task-list .task')].find(
      each => Number(each.dataset.id) === doomedId);
    log('X6  a row that arrives is back in the list', Boolean(returned));
    if (returned) {
      const entrance = returned.getAnimations();
      log('X7  and it fades in rather than appearing', entrance.length === 1,
          entrance.length + ' animations on it');
      const frames = entrance.length ? entrance[0].effect.getKeyframes() : [];
      log('X8  the entrance animates opacity, not height',
          frames.some(frame => 'opacity' in frame)
          && !frames.some(frame => 'height' in frame),
          Object.keys(frames[0] || {}).filter(k => k !== 'offset'
            && k !== 'computedOffset' && k !== 'easing').join(','));
    }
  } catch (error) {
    out.push('THREW  ' + error.message + '\\n' + error.stack);
  }
  document.getElementById('results').textContent = out.join('\\n');
})();
</script>
`;

// Autoscroll, in a window short enough that the document really scrolls. Its own
// file because every other test needs the whole list visible at once.
const SCROLL = `
<pre id="results" style="position:fixed;left:0;top:0;width:100%;background:#000;color:#0f0;font:11px/1.4 Consolas;white-space:pre-wrap;z-index:99;margin:0;padding:4px">EMPTY</pre>
<script>
(async function () {
  const out = [];
  const log = (name, ok, detail) =>
    out.push((ok ? 'PASS  ' : 'FAIL  ') + name + (detail ? '   [' + detail + ']' : ''));
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function pt(type, x, y, target) {
    (target || window).dispatchEvent(new PointerEvent(type, {
      clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0,
      buttons: type === 'pointerup' ? 0 : 1,
      pointerId: 1, isPrimary: true, pointerType: 'mouse' }));
  }
  try {
    window.dispatchEvent(new Event('pywebviewready'));
    await sleep(400);
    const scrollable = document.documentElement.scrollHeight
                     - document.documentElement.clientHeight;
    log('A0  the document is long enough to scroll', scrollable > 80,
        scrollable + 'px of scroll available');

    const row = document.querySelector('#task-list section[data-bucket="now"] > .task');
    const box = row.getBoundingClientRect();
    const holdX = box.left + 90, holdY = box.top + box.height / 2;
    pt('pointerdown', holdX, holdY, row);
    pt('pointermove', holdX + 6, holdY);

    // Hold near the bottom edge and stop moving — no further pointer events.
    const edgeY = document.documentElement.clientHeight - 10;
    pt('pointermove', holdX, edgeY);
    const before = window.scrollY;
    await sleep(500);
    const after = window.scrollY;
    log('A1  holding at the edge scrolls the window', after > before + 20,
        before + ' -> ' + after);

    // The card is fixed and the hand has not moved, so it must NOT have moved.
    const cardBox = document.querySelector('#drag-layer .held').getBoundingClientRect();
    log('A2  the card stayed under the unmoved pointer',
        Math.abs(cardBox.top + cardBox.height / 2 - edgeY) < cardBox.height,
        'card centre ' + (cardBox.top + cardBox.height / 2).toFixed(0) + ' vs pointer ' + edgeY);

    // The real question: after scrolling, does it still land where it is DRAWN?
    // Without the scroll-delta correction in fbox, every frozen box is stale by
    // however far the page travelled and the aim points at old geometry.
    const centreY = cardBox.top + cardBox.height / 2;
    const sections = [...document.querySelectorAll('#task-list section')];
    // Mirrors sectionUnder's own rule, including the clause that matters here:
    // the space past the last section belongs to it rather than to nothing. Body
    // has 88px of bottom padding for the selection bar, so a card held at the
    // window's bottom edge with the list scrolled to the end IS past every box —
    // asserting "some section contains it" fails on correct behaviour.
    const live = sections.find(s => {
      const b = s.getBoundingClientRect();
      return centreY >= b.top && centreY <= b.bottom;
    }) || (centreY > sections[sections.length - 1].getBoundingClientRect().bottom
             ? sections[sections.length - 1] : null);
    log('A3  it previews into the section the card is NOW over',
        Boolean(live) && row.closest('section') === live,
        'card is over ' + (live ? (live.dataset.bucket || 'in-progress') : 'nothing')
        + ', previewed into ' + (row.closest('section').dataset.bucket || 'in-progress'));

    pt('pointerup', holdX, edgeY);
    await sleep(300);
    const stopped = window.scrollY;
    await sleep(400);
    log('A4  the scroll timer stops with the drag', window.scrollY === stopped,
        stopped + ' -> ' + window.scrollY);
  } catch (error) {
    out.push('THREW  ' + error.message + '\\n' + error.stack);
  }
  document.getElementById('results').textContent = out.join('\\n');
})();
</script>
`;

fs.writeFileSync('app-scroll.html',
  '<!DOCTYPE html><html><head><base href="file:///' + UI + '/">'
  + head + '<title>scroll</title></head><body>'
  + STUB + body + SCROLL + '</body></html>');

// Freeze mid-drag and photograph it: both end states of a drag already look
// right, which is how a card that never appears survives every review.
const HOLD = `
<script>
(async function () {
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function pt(type, x, y, target) {
    (target || window).dispatchEvent(new PointerEvent(type, {
      clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0,
      buttons: 1, pointerId: 1, isPrimary: true, pointerType: 'mouse' }));
  }
  window.dispatchEvent(new Event('pywebviewready'));
  await sleep(400);
  const row = document.querySelector('#task-list section[data-bucket="now"] > .task');
  const box = row.getBoundingClientRect();
  const startX = box.left + 90, startY = box.top + box.height - 2;
  pt('pointerdown', startX, startY, row);
  pt('pointermove', startX + 6, startY);
  const someday = document.querySelector('#task-list section[data-bucket="someday"]');
  const sb = someday.getBoundingClientRect();
  const atY = sb.top + 16;
  pt('pointermove', startX, atY);
  // A crosshair exactly where the synthetic pointer is, so the picture shows
  // whether the card is under it rather than merely somewhere on screen.
  const mark = document.createElement('div');
  mark.style.cssText = 'position:fixed;z-index:99999;pointer-events:none;left:'
    + (startX - 9) + 'px;top:' + (atY - 9) + 'px;width:18px;height:18px;'
    + 'border:2px solid #ff3ba7;border-radius:50%;box-shadow:0 0 0 2px rgba(0,0,0,.6)';
  document.body.append(mark);
})();
</script>
`;

fs.writeFileSync('app-hold.html',
  '<!DOCTYPE html><html><head><base href="file:///' + UI + '/">'
  + head + '<title>hold</title></head><body>'
  + STUB + body + HOLD + '</body></html>');

fs.writeFileSync('app-harness.html',
  '<!DOCTYPE html><html><head><base href="file:///' + UI + '/">'
  + head
  + '<title>app harness</title></head><body>'
  + STUB + body + TEST + '</body></html>');
console.log('app-harness.html written,', body.length, 'chars of body,',
  head.length, 'chars of head (the stylesheet links)');
