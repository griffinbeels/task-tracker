// The editor overlay: one Toast UI instance shared by every entry point that
// turns prose into a task. Capture and triage are wired up here; edit reuses
// the same overlay and openEditor() contract in a later task — do not add
// its behaviour here ahead of time.

// Built once, on first open, and reused. A new toastui.Editor per open leaks
// its ProseMirror instance into the DOM — nothing tears the old one down.
let toastEditor = null;
// The context the overlay is currently showing: mode plus the project/type/
// bucket chip selections. null until the first openEditor() call.
let editorContext = null;
// Which note/task identity the title box was last auto-filled for, and
// whether the user has since typed into it. Capture has no note/task id to
// key off — see the Symbol fallback in openEditor() below, which is what
// makes every capture open its own blank slate rather than inheriting the
// previous capture's title. Triage passes a real noteId, so a genuinely new
// identity resets titleIsUsers (a fresh note deserves its own suggestion),
// but an *unchanged* identity leaves titleIsUsers exactly as the user left
// it — "one keystroke marks the title yours for the life of that note"
// (design spec invariant 1). That matters because triage.js's Skip re-opens
// the very same note whenever it's the only one left in the queue, and that
// re-open must not clobber a title already typed.
let titleFilledFor = null;
let titleIsUsers = false;
// The markdown last handed to setMarkdown, and what Toast UI normalises it to
// immediately after. Task 5 (edit mode) compares a task's saved body against
// both to tell "the user changed it" apart from "Toast UI's own round-trip
// changed it" — captured here so the values exist from the first open.
let loadedBody = '';
let normalisedBody = '';

function chip(label, selected, onClick) {
  const button = document.createElement('button');
  button.className = 'chip' + (selected ? ' on' : '');
  button.textContent = label;
  button.onclick = onClick;
  return button;
}

function getEditor() {
  if (toastEditor) return toastEditor;
  toastEditor = new toastui.Editor({
    el: document.getElementById('editor-body'),
    initialEditType: 'wysiwyg',
    hideModeSwitch: true,
    theme: 'dark',
    height: '100%',
    // Trimmed to what a notepad needs — no tables, images or the raw-markdown
    // mode switch (hidden above), which this overlay has no use for.
    toolbarItems: [
      ['heading', 'bold', 'italic', 'strike'],
      ['ul', 'ol', 'task'],
      ['quote', 'code'],
    ],
  });
  return toastEditor;
}

// Clicking a chip must re-render only the chip rows. Earlier this logic lived
// inside renderTriage(), which also wrote the suggested title on every call —
// so picking a type after typing a title stomped it. Giving chip clicks their
// own render function that touches nothing else is what prevents that here.
function renderChips() {
  document.getElementById('editor-projects').replaceChildren(
    ...state.projects.map(p => chip(p.name, editorContext.project === p.name,
      () => { editorContext.project = p.name; renderChips(); })));
  document.getElementById('editor-types').replaceChildren(
    ...state.settings.types.map(t => chip(t.name, editorContext.type === t.name,
      () => { editorContext.type = t.name; renderChips(); })));
  document.getElementById('editor-buckets').replaceChildren(
    ...BUCKETS.map(b => chip(b, editorContext.bucket === b,
      () => { editorContext.bucket = b; renderChips(); })));
}

// Every action button always exists in the markup; this just shows the ones
// this mode uses and hides the rest, so the DOM never gets rebuilt per mode.
function showEditorActions(visibleIds) {
  ['editor-save', 'editor-later', 'editor-skip', 'editor-discard', 'editor-cancel']
    .forEach(id => { document.getElementById(id).hidden = !visibleIds.includes(id); });
}

// The single entry point. context is
// { mode, title, body, project, type, bucket, noteId, taskId }; mode is one
// of 'capture' | 'triage' | 'edit'. 'edit' is not wired to a caller yet.
function openEditor(context) {
  editorContext = {
    mode: context.mode,
    project: context.project || currentProject,
    type: context.type || (state.settings.types[0] || {}).name,
    bucket: context.bucket || 'now',
    noteId: context.noteId ?? null,
    taskId: context.taskId ?? null,
  };

  // Capture has no noteId/taskId, so without this a fresh Symbol() every
  // capture open would collapse to the same `null` identity every other
  // capture also uses — `titleFilledFor !== identity` would then be false
  // from the second capture on, and the title box would silently keep
  // whatever the previous capture left in it. A fresh Symbol per identity-
  // less open can never equal a previous (or future) titleFilledFor, so the
  // title always gets (re)written — which is exactly "every capture is its
  // own blank slate." Triage/edit pass real ids and keep the suggest-once
  // behaviour unchanged.
  const identity = editorContext.noteId ?? editorContext.taskId ?? Symbol('no-identity');
  // A changed identity means a different note/task is now current, so
  // whatever the box was "owned" for no longer applies — reset the flag so
  // this identity gets its own suggestion. Leaving titleIsUsers untouched
  // when the identity is unchanged is what makes ownership last "for the
  // life of that note" (see the comment on titleIsUsers above).
  if (titleFilledFor !== identity) {
    titleFilledFor = identity;
    titleIsUsers = false;
  }
  const titleInput = document.getElementById('editor-title');
  if (!titleIsUsers) {
    titleInput.value = context.title || '';
  }

  loadedBody = context.body || '';
  const editor = getEditor();
  editor.setMarkdown(loadedBody, true);
  normalisedBody = editor.getMarkdown();

  renderChips();

  if (editorContext.mode === 'capture') {
    showEditorActions(['editor-save', 'editor-later', 'editor-cancel']);
    document.getElementById('editor-progress').hidden = true;
  } else if (editorContext.mode === 'triage') {
    showEditorActions(['editor-save', 'editor-skip', 'editor-discard', 'editor-cancel']);
    const progress = document.getElementById('editor-progress');
    progress.hidden = false;
    // triageQueue/triageIndex live in triage.js, which loads after this file
    // but before any user gesture can reach this branch — same cross-file
    // global-scope pattern the rest of this project already relies on.
    progress.textContent = `note ${triageIndex + 1} / ${triageQueue.length}`;
  }

  document.getElementById('editor').hidden = false;
  editor.focus();
}

function closeEditor() {
  document.getElementById('editor').hidden = true;
}

document.getElementById('editor-title').addEventListener('input', () => { titleIsUsers = true; });

document.getElementById('editor-save').onclick = async () => {
  const title = document.getElementById('editor-title').value.trim();
  // A title and a resolved project/type are non-negotiable in every mode;
  // everything else has a default.
  if (!title || !editorContext.project || !editorContext.type) return;

  const body = getEditor().getMarkdown();

  if (editorContext.mode === 'triage') {
    const note = triageQueue[triageIndex];
    if (!note) return;
    // Pass the editor's current markdown, not the note's on-disk text — the
    // whole point of triaging in an editor is that a typo fix or an added
    // line survives to the task. file_note falls back to the note's own
    // text only when this argument is omitted.
    if (await callApi('file_note', note.id, editorContext.project, title,
        editorContext.type, editorContext.bucket, body) === API_FAILED) return;
    triageQueue.splice(triageIndex, 1);
    afterNoteRemoved();
    await refresh();
    return;
  }

  if (await callApi('create_task', editorContext.project, title, body,
      editorContext.type, editorContext.bucket) === API_FAILED) return;
  closeEditor();
  await refresh();
};

document.getElementById('editor-skip').onclick = () => {
  // Math.max guards a queue that hits zero the same instant this fires —
  // shouldn't happen since the button is hidden outside triage mode and the
  // overlay closes once the queue empties, but division by zero would be a
  // silent NaN index rather than a loud failure, so keep the guard.
  triageIndex = (triageIndex + 1) % Math.max(triageQueue.length, 1);
  openTriageNote();
};

document.getElementById('editor-discard').onclick = async () => {
  const note = triageQueue[triageIndex];
  if (!note) return;
  if (await callApi('delete_note', note.id) === API_FAILED) return;
  triageQueue.splice(triageIndex, 1);
  afterNoteRemoved();
  await refresh();
};

document.getElementById('editor-later').onclick = async () => {
  const body = getEditor().getMarkdown();
  // Ignores every chip on purpose — this is the zero-decision path capture
  // had before the editor existed. An empty note isn't worth a save_note call,
  // matching the old capture box's behaviour.
  if (body.trim()) {
    if (await callApi('save_note', body) === API_FAILED) return;
  }
  closeEditor();
  await refresh();
};

document.getElementById('editor-cancel').onclick = closeEditor;

document.getElementById('capture-button').onclick = () => openEditor({ mode: 'capture' });
