// Execute the real shortcut functions without creating a browser window.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function page(platform) {
  const context = vm.createContext({
    document: { addEventListener() {}, getElementById() { return {}; } },
    window: { addEventListener() {} },
    setTimeout() {}, clearTimeout() {},
  });
  for (const name of ['state.js', 'zoom.js']) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../ui', name), 'utf8'), context);
  }
  vm.runInContext(`state.shortcuts = ${JSON.stringify(platform)}`, context);
  return event => vm.runInContext(`zoomIntent(${JSON.stringify(event)})`, context);
}

test('Mac Command controls zoom while Control and other system chords stay free', () => {
  const intent = page({ modifier: 'meta', label: 'Command' });
  assert.equal(intent({ key: '+', metaKey: true }), 'in');
  assert.equal(intent({ key: '-', metaKey: true }), 'out');
  assert.equal(intent({ key: '0', metaKey: true }), 'reset');
  assert.equal(intent({ key: '+', ctrlKey: true }), null);
  assert.equal(intent({ key: '+', metaKey: true, altKey: true }), null);
  assert.equal(intent({ key: '+', metaKey: true, ctrlKey: true }), null);
});

test('Windows keeps Control zoom and leaves Windows-key chords free', () => {
  const intent = page({ modifier: 'ctrl', label: 'Ctrl' });
  assert.equal(intent({ key: '=', ctrlKey: true, shiftKey: true }), 'in');
  assert.equal(intent({ code: 'NumpadSubtract', ctrlKey: true }), 'out');
  assert.equal(intent({ code: 'Numpad0', ctrlKey: true }), 'reset');
  assert.equal(intent({ key: '+', metaKey: true }), null);
  assert.equal(intent({ key: '+', ctrlKey: true, metaKey: true }), null);
  assert.equal(intent({ key: '+', ctrlKey: true, altKey: true }), null);
});
