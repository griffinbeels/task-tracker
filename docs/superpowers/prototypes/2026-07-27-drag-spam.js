// Wave a card up and down 300 times and measure what runs away. NOT part of the
// test suite; nothing runs it. `node build-spam.js` then load spam.html the same
// way the drag harness beside it is loaded.
//
// It wraps window.scrollBy and Element.prototype.animate to answer two questions
// no end-state check can: is a runaway scroll OURS, and which element is being
// asked to travel hundreds of pixels. That is how autoscroll was identified as
// the cause of "all cards eventually disappear off the screen" — 29 scrollBy
// calls for 292px, against 0 once a dwell was required.
//
// The control that made it decisive: confine the wave to mid-window, where the
// autoscroll bands cannot be entered. Drift went 237px -> 0 and the largest
// stranded transform 338px -> 0, which named the cause without a hypothesis.
//
// End the wave in the MIDDLE. Parking the pointer in an edge band and then
// waiting is autoscroll working as intended, and it masks whether the wave itself
// scrolls.

// Wave a card up and down as fast as possible and measure what runs away.
// Records every animate() call so the flung element names itself.
const fs = require('fs');
const UI = 'C:/Users/griff/Desktop/code/task_tracker/ui';
const markup = fs.readFileSync(UI + '/index.html', 'utf8');
const body = markup.slice(markup.indexOf('<body>') + 6, markup.indexOf('</body>'));
const head = markup.slice(markup.indexOf('<head>') + 6, markup.indexOf('</head>'));
const STUB = fs.readFileSync(
  'C:/Users/griff/Desktop/code/task_tracker/docs/superpowers/prototypes/2026-07-27-drag-harness.js',
  'utf8').match(/const STUB = `([\s\S]*?)`;/)[1];

const SPAM = `
<pre id="results" style="position:fixed;left:0;top:0;width:100%;background:#000;color:#0f0;font:10px/1.35 Consolas;white-space:pre-wrap;z-index:99;margin:0;padding:4px">EMPTY</pre>
<script>
(async function () {
  const out = [];
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  function pt(type, x, y, target) {
    (target || window).dispatchEvent(new PointerEvent(type, {
      clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0,
      buttons: type === 'pointerup' ? 0 : 1,
      pointerId: 1, isPrimary: true, pointerType: 'mouse' }));
  }
  // No regex: the generator writes this through a template literal, where a
  // backslash is an escape and would not survive.
  const translateY = text => {
    if (typeof text !== 'string') return null;
    const head = 'translate(';
    if (!text.startsWith(head)) return null;
    const inner = text.slice(head.length, text.indexOf(')'));
    const parts = inner.split(',');
    return parts.length < 2 ? null : parseFloat(parts[1]);
  };
  const shift = element => {
    const t = getComputedStyle(element).transform;
    if (t === 'none') return 0;
    return new DOMMatrixReadOnly(t).m42;
  };
  const snapshot = () => {
    const rows = [...document.querySelectorAll('#task-list .task, #task-list .group')];
    return {
      scrollY: Math.round(window.scrollY),
      maxShift: Math.round(Math.max(0, ...rows.map(r => Math.abs(shift(r))))),
      firstTop: rows.length ? Math.round(rows[0].getBoundingClientRect().top) : 0,
      anims: document.getAnimations().length,
      rows: rows.length,
    };
  };

  // Every animate() call, with how far it asks for and whether its target sits
  // inside an ancestor that was already animating.
  // Is the scroll OURS? window.scrollBy is the only place the app scrolls.
  let scrollCalls = 0, scrollTotal = 0;
  const realScrollBy = window.scrollBy.bind(window);
  window.scrollBy = function (x, y) {
    scrollCalls++; scrollTotal += (typeof y === 'number' ? y : 0);
    return realScrollBy(x, y);
  };

  const calls = [];
  const realAnimate = Element.prototype.animate;
  Element.prototype.animate = function (frames, opts) {
    const first = Array.isArray(frames) ? frames[0] : frames;
    const dy = translateY(first && first.transform);
    if (dy !== null) {
      let node = this.parentElement, under = null;
      while (node && node.id !== 'task-list') {
        if (node.getAnimations && node.getAnimations().length) { under = node.className; break; }
        node = node.parentElement;
      }
      const label = this.querySelector && this.querySelector('.title');
      calls.push({ dy: Math.round(dy), who: (this.className || '').slice(0, 22),
                   title: label ? label.textContent.slice(0, 16) : '', under });
    }
    return realAnimate.call(this, frames, opts);
  };

  try {
    window.dispatchEvent(new Event('pywebviewready'));
    await sleep(350);
    const start = snapshot();
    out.push('BEFORE  ' + JSON.stringify(start));

    const row = document.querySelector('#task-list section[data-bucket="now"] > .task');
    const box = row.getBoundingClientRect();
    const x = box.left + 90;
    pt('pointerdown', x, box.top + box.height / 2, row);
    pt('pointermove', x + 6, box.top + box.height / 2);

    // Well inside the window, so the autoscroll bands are never entered and
    // cannot be the cause of any scroll that happens.
    const high = 12, low = document.documentElement.clientHeight - 12;
    for (let n = 0; n < 300; n++) pt('pointermove', x, n % 2 ? low : high);
    out.push('DURING  ' + JSON.stringify(snapshot()));
    // End in the MIDDLE. Parking the pointer in an edge band and then waiting is
    // autoscroll working as intended — holding at the edge is meant to scroll —
    // and it would mask whether the WAVE itself scrolls.
    pt('pointermove', x, Math.round(document.documentElement.clientHeight / 2));

    await sleep(900);
    out.push('SETTLED ' + JSON.stringify(snapshot()));
    pt('pointerup', x, low);
    await sleep(900);
    const end = snapshot();
    out.push('AFTER   ' + JSON.stringify(end));
    out.push('');
      out.push('window.scrollBy calls from the app: ' + scrollCalls
      + '   total requested: ' + Math.round(scrollTotal) + 'px');
    out.push('scrollY drift ' + start.scrollY + ' -> ' + end.scrollY
      + '   |   largest stranded transform ' + end.maxShift + 'px');
    out.push('');
    const big = calls.filter(c => Math.abs(c.dy) > 60);
    out.push('animate() calls asking for more than 60px: ' + big.length
      + ' of ' + calls.length);
    big.slice(0, 10).forEach(c => out.push('   dy=' + String(c.dy).padStart(5)
      + '  ' + c.who.padEnd(22) + ' "' + c.title + '"'
      + (c.under ? '   <<< INSIDE ANIMATING ' + c.under : '')));
    const worst = calls.reduce((a, c) => Math.abs(c.dy) > Math.abs(a.dy) ? c : a,
                              { dy: 0, who: '-', title: '', under: null });
    out.push('worst single delta: dy=' + worst.dy + '  ' + worst.who
      + ' "' + worst.title + '"' + (worst.under ? '  inside animating ' + worst.under : ''));
    out.push('calls whose target sat inside an animating ancestor: '
      + calls.filter(c => c.under).length + ' of ' + calls.length);
  } catch (error) {
    out.push('THREW  ' + error.message);
  }
  document.getElementById('results').textContent = out.join('\\n');
})();
</script>
`;

fs.writeFileSync('spam.html',
  '<!DOCTYPE html><html><head><base href="file:///' + UI + '/">'
  + head + '<title>spam</title></head><body>' + STUB + body + SPAM + '</body></html>');
console.log('spam.html written');
