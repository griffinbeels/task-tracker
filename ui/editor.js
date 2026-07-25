// The editor overlay: one Toast UI instance shared by every entry point that
// turns prose into a task. Capture is the first entry point wired up here;
// triage and edit reuse the same overlay and openEditor() contract in later
// tasks — do not add their behaviour here ahead of time.

// Built once, on first open, and reused. A new toastui.Editor per open leaks
// its ProseMirror instance into the DOM — nothing tears the old one down.
let toastEditor = null;
// The context the overlay is currently showing: mode plus the project/type/
// bucket chip selections. null until the first openEditor() call.
let editorContext = null;
// Which note/task identity the title box was last auto-filled for, and
// whether the user has since typed into it. Mirrors ui/triage.js's
// triageTitleFilledFor: without tracking this, re-showing a suggested title
// for the same note/task would overwrite whatever the user already typed.
// Capture has no note/task id to key off — see the Symbol fallback in
// openEditor() below, which is what makes every capture open its own blank
// slate rather than inheriting the previous capture's title. titleIsUsers
// currently has no reader: nothing in capture mode re-suggests a title after
// opening, so nothing needs to check it yet. It's wired up (the `input`
// listener below sets it) so triage and edit, added next, have the
// mechanism already in place rather than reinventing it.
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
// of 'capture' | 'triage' | 'edit'. Only 'capture' is wired to a caller yet.
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
  const titleInput = document.getElementById('editor-title');
  if (titleFilledFor !== identity) {
    titleInput.value = context.title || '';
    titleFilledFor = identity;
  }
  titleIsUsers = false;

  loadedBody = context.body || '';
  const editor = getEditor();
  editor.setMarkdown(loadedBody, true);
  normalisedBody = editor.getMarkdown();

  renderChips();

  if (editorContext.mode === 'capture') {
    showEditorActions(['editor-save', 'editor-later', 'editor-cancel']);
    document.getElementById('editor-progress').hidden = true;
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
  // Same guard triage.js applies before file_note: a title and a resolved
  // project/type are non-negotiable, everything else has a default.
  if (!title || !editorContext.project || !editorContext.type) return;
  const body = getEditor().getMarkdown();
  if (await callApi('create_task', editorContext.project, title, body,
      editorContext.type, editorContext.bucket) === API_FAILED) return;
  closeEditor();
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
