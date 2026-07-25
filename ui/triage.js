// Capture and triage — the two overlays that replace the user's notepad.
//
// Capture asks for nothing: text goes in, it's saved verbatim, the overlay
// closes. Triage is the separate, deliberate act where project/type/bucket
// get chosen before a note becomes a task.

function openCapture() {
  document.getElementById('capture-text').value = '';
  document.getElementById('capture').hidden = false;
  document.getElementById('capture-text').focus();
}

document.getElementById('capture-button').onclick = openCapture;
document.getElementById('capture-cancel').onclick =
  () => { document.getElementById('capture').hidden = true; };
document.getElementById('capture-save').onclick = async () => {
  const text = document.getElementById('capture-text').value;
  // trim() here only decides whether an empty box counts as a note — the
  // text sent to save_note is the untrimmed textarea value.
  if (text.trim()) {
    if (await callApi('save_note', text) === null) return;
  }
  document.getElementById('capture').hidden = true;
  await refresh();
};

let triageQueue = [];
let triageIndex = 0;
let triagePick = { project: null, type: null, bucket: 'now' };

function chip(label, selected, onClick) {
  const button = document.createElement('button');
  button.className = 'chip' + (selected ? ' on' : '');
  button.textContent = label;
  button.onclick = onClick;
  return button;
}

function renderTriage() {
  const note = triageQueue[triageIndex];
  if (!note) { document.getElementById('triage').hidden = true; return; }
  document.getElementById('triage-progress').textContent =
    `note ${triageIndex + 1} / ${triageQueue.length}`;
  // note.text is arbitrary user prose that can contain <, &, quotes and
  // newlines — textContent/.value only, never innerHTML (see tasks.js).
  document.getElementById('triage-text').textContent = note.text;
  document.getElementById('triage-title').value =
    note.text.split('\n')[0].slice(0, 80);

  document.getElementById('triage-projects').replaceChildren(
    ...state.projects.map(p => chip(p.name, triagePick.project === p.name,
      () => { triagePick.project = p.name; renderTriage(); })));
  document.getElementById('triage-types').replaceChildren(
    ...state.settings.types.map(t => chip(t.name, triagePick.type === t.name,
      () => { triagePick.type = t.name; renderTriage(); })));
  document.getElementById('triage-buckets').replaceChildren(
    ...BUCKETS.map(b => chip(b, triagePick.bucket === b,
      () => { triagePick.bucket = b; renderTriage(); })));
}

async function openTriage() {
  const notes = await callApi('list_notes');
  if (notes === null) return;
  triageQueue = notes;
  triageIndex = 0;
  triagePick = {
    project: currentProject,
    type: (state.settings.types[0] || {}).name,
    bucket: 'now',
  };
  document.getElementById('triage').hidden = triageQueue.length === 0;
  renderTriage();
}

document.getElementById('triage-file').onclick = async () => {
  const note = triageQueue[triageIndex];
  const title = document.getElementById('triage-title').value.trim();
  if (!note || !title || !triagePick.project || !triagePick.type) return;
  if (await callApi('file_note', note.id, triagePick.project, title,
      triagePick.type, triagePick.bucket) === null) return;
  // The note that was just filed is spliced out, so the next note shifts
  // into this same index — don't also advance triageIndex or every other
  // note in the queue gets skipped.
  triageQueue.splice(triageIndex, 1);
  renderTriage();
  await refresh();
};

document.getElementById('triage-skip').onclick =
  () => { triageIndex = (triageIndex + 1) % Math.max(triageQueue.length, 1); renderTriage(); };

document.getElementById('triage-discard').onclick = async () => {
  const note = triageQueue[triageIndex];
  if (!note) return;
  if (await callApi('delete_note', note.id) === null) return;
  triageQueue.splice(triageIndex, 1);
  renderTriage();
  await refresh();
};

document.getElementById('triage-close').onclick =
  () => { document.getElementById('triage').hidden = true; };
