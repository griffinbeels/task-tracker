// Triage — the deliberate act where project/type/bucket get chosen before a
// note becomes a task. Capture, the zero-decision counterpart, now opens the
// shared editor overlay directly; see editor.js.

let triageQueue = [];
let triageIndex = 0;
let triagePick = { project: null, type: null, bucket: 'now' };
// Which note the title box was last filled for. renderTriage() runs on every
// chip click, so without this the suggested title overwrites whatever the user
// typed the moment they pick a type or bucket.
let triageTitleFilledFor = null;

function suggestedTitle(text) {
  const firstLine = text.split('\n')[0].trim();
  if (firstLine.length <= 80) return firstLine;
  // Cut on a word boundary — a title sliced mid-word reads as corruption.
  const cut = firstLine.slice(0, 80);
  const lastSpace = cut.lastIndexOf(' ');
  return (lastSpace > 40 ? cut.slice(0, lastSpace) : cut).trimEnd();
}

// chip() moved to editor.js — still called from here via the shared global
// scope every script in this project runs in.

function renderTriage() {
  const note = triageQueue[triageIndex];
  if (!note) { document.getElementById('triage').hidden = true; return; }
  document.getElementById('triage-progress').textContent =
    `note ${triageIndex + 1} / ${triageQueue.length}`;
  // note.text is arbitrary user prose that can contain <, &, quotes and
  // newlines — textContent/.value only, never innerHTML (see tasks.js).
  document.getElementById('triage-text').textContent = note.text;
  if (triageTitleFilledFor !== note.id) {
    document.getElementById('triage-title').value = suggestedTitle(note.text);
    triageTitleFilledFor = note.id;
  }

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
  if (notes === API_FAILED) return;
  triageQueue = notes;
  triageIndex = 0;
  triageTitleFilledFor = null;   // fresh pass — suggest a title again
  triagePick = {
    project: currentProject,
    type: (state.settings.types[0] || {}).name,
    bucket: 'now',
  };
  document.getElementById('triage').hidden = triageQueue.length === 0;
  renderTriage();
}

// After splicing a note out, the next note shifts into this same index —
// don't advance triageIndex, or every other note in the queue gets skipped.
// But if the note removed was the last one in the queue, that same index is
// now past the end (triageQueue[triageIndex] is undefined), which
// renderTriage reads as "queue empty" and hides the overlay even though
// earlier notes are still unfiled. Clamp back to the front of the queue
// instead — those earlier notes are all that's left to triage.
function afterNoteRemoved() {
  if (triageIndex >= triageQueue.length) triageIndex = 0;
  renderTriage();
}

document.getElementById('triage-file').onclick = async () => {
  const note = triageQueue[triageIndex];
  const title = document.getElementById('triage-title').value.trim();
  if (!note || !title || !triagePick.project || !triagePick.type) return;
  if (await callApi('file_note', note.id, triagePick.project, title,
      triagePick.type, triagePick.bucket) === API_FAILED) return;
  triageQueue.splice(triageIndex, 1);
  afterNoteRemoved();
  await refresh();
};

document.getElementById('triage-skip').onclick =
  () => { triageIndex = (triageIndex + 1) % Math.max(triageQueue.length, 1); renderTriage(); };

document.getElementById('triage-discard').onclick = async () => {
  const note = triageQueue[triageIndex];
  if (!note) return;
  if (await callApi('delete_note', note.id) === API_FAILED) return;
  triageQueue.splice(triageIndex, 1);
  afterNoteRemoved();
  await refresh();
};

document.getElementById('triage-close').onclick =
  () => { document.getElementById('triage').hidden = true; };
