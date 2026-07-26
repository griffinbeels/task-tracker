// Triage — the deliberate act where project/type/bucket get chosen before a
// note becomes a task. The shared editor overlay in editor.js renders the
// note and drives File/Skip/Discard (see its editor-save/-skip/-discard
// handlers); this file answers only "which note in the queue am I on."

let triageQueue = [];
let triageIndex = 0;

function suggestedTitle(text) {
  const firstLine = text.split('\n')[0].trim();
  if (firstLine.length <= 80) return firstLine;
  // Cut on a word boundary — a title sliced mid-word reads as corruption.
  const cut = firstLine.slice(0, 80);
  const lastSpace = cut.lastIndexOf(' ');
  return (lastSpace > 40 ? cut.slice(0, lastSpace) : cut).trimEnd();
}

// Opens the editor for whatever note is now at triageIndex, carrying the
// previous note's project/type/bucket picks forward from editorContext (see
// editor.js) so a run of similar notes is fast — only the title and body are
// specific to this note. Closes the overlay once the queue is empty.
function openTriageNote() {
  const note = triageQueue[triageIndex];
  if (!note) { closeEditor(); return; }
  openEditor({
    mode: 'triage',
    title: suggestedTitle(note.text),
    body: note.text,
    project: editorContext && editorContext.project,
    type: editorContext && editorContext.type,
    bucket: editorContext && editorContext.bucket,
    noteId: note.id,
  });
}

async function openTriage() {
  const notes = await callApi('list_notes');
  if (notes === API_FAILED) return;
  triageQueue = notes;
  triageIndex = 0;
  // Carrying picks forward is meant to speed up a run of similar notes within
  // one pass — not to inherit whatever the last thing you edited happened to
  // be. A fresh pass starts from the defaults, so clear the context the notes
  // would otherwise read their starting point from.
  editorContext = null;
  openTriageNote();
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
  openTriageNote();
}
