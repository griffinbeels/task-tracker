// Check every script with the same command on Windows and macOS.
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const ui = path.join(__dirname, '..', 'ui');
for (const file of fs.readdirSync(ui).filter(name => name.endsWith('.js'))) {
  const checked = spawnSync(process.execPath, ['--check', path.join(ui, file)], {
    stdio: 'inherit', windowsHide: true,
  });
  if (checked.error) throw checked.error;
  if (checked.status !== 0) process.exit(checked.status || 1);
}
