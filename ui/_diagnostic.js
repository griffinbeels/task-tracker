// TEMPORARY — delete this file, its <script> tag, and Api.write_diagnostic
// once the editor toolbar's stray divider is understood.
//
// Ctrl+Shift+D with the editor open writes the toolbar's real markup and
// geometry to ~/.task-tracker/toolbar-dump.txt. It exists because Claude
// cannot run this app and a headless browser does not reach the state the real
// window reaches — the toolbar never re-collapses there, so the element that
// draws the line has never been seen, only guessed at from screenshots. Three
// guesses, three misses.

document.addEventListener('keydown', async event => {
  if (!event.ctrlKey || !event.shiftKey || event.key.toLowerCase() !== 'd') return;
  event.preventDefault();

  const bar = document.querySelector('#editor .toastui-editor-toolbar');
  if (!bar) { alert('Open Capture first, then press Ctrl+Shift+D again.'); return; }

  const lines = [];
  const barBox = bar.getBoundingClientRect();
  lines.push(`window ${innerWidth}x${innerHeight}  dpr ${devicePixelRatio}`);
  lines.push(`editor zoom ${document.getElementById('editor').style.zoom || '(none)'}`);
  lines.push(`toolbar ${Math.round(barBox.width)}x${Math.round(barBox.height)}`);
  lines.push('');
  lines.push('--- every element in the toolbar, in document order ---');
  lines.push('(x is relative to the toolbar; a 1px-wide box is the stray line)');
  lines.push('');

  const walk = (element, depth) => {
    for (const child of element.children) {
      const style = getComputedStyle(child);
      const box = child.getBoundingClientRect();
      lines.push([
        `${'  '.repeat(depth)}${child.getAttribute('class') || child.tagName}`.padEnd(56),
        `x=${Math.round(box.left - barBox.left)}`.padEnd(9),
        `w=${Math.round(box.width)}`.padEnd(7),
        `h=${Math.round(box.height)}`.padEnd(7),
        `display=${style.display}`.padEnd(20),
        `bg=${style.backgroundColor}`.padEnd(28),
        `inline-style=${JSON.stringify(child.getAttribute('style'))}`,
      ].join(''));
      walk(child, depth + 1);
    }
  };
  walk(bar, 0);

  lines.push('');
  lines.push('--- the markup ---');
  lines.push(bar.outerHTML);

  const where = await callApi('write_diagnostic', lines.join('\n'));
  alert(where === API_FAILED ? 'Could not write the dump.' : `Wrote:\n${where}`);
});
