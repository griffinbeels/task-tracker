// The editor overlay: one Toast UI instance shared by every entry point that
// turns prose into a task. Capture and triage open it from this file; edit
// opens it from tasks.js's row click handler. All three share the one
// openEditor() contract below.

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
// immediately after. Edit mode compares a task's saved body against both to
// tell "the user changed it" apart from "Toast UI's own round-trip changed
// it" — see the editor-save handler's 'edit' branch below.
let loadedBody = '';
let normalisedBody = '';
// The bucket the task was in when it was opened, so edit mode can tell a real
// move from a save that left the bucket alone. A move needs a new `order` —
// see the save handler.
let loadedBucket = null;

function chip(label, selected, onClick, color) {
  const button = document.createElement('button');
  button.className = 'chip' + (selected ? ' on' : '');
  button.textContent = label;
  button.onclick = onClick;
  // A selected type wears its own colour, the same one the task list tags rows
  // with — so the chip you picked and the row you'll see afterwards are
  // recognisably the same thing. Set via .style, never interpolated into
  // markup: a type's colour is unvalidated text from a hand-editable file
  // (invariant 5).
  if (selected && color) {
    button.style.background = color;
    button.style.color = '#fff';
  }
  return button;
}

// A swatch, unlike a chip, wears its colour whether or not it is selected —
// the circle itself is the choice, not a label. That means selection cannot
// reuse "fill it in" the way .chip.on does (it is already filled), so a ring
// plays the same role instead: a difference you see, not one you have to
// look for. Named via a title attribute rather than a text label, so the
// choice is still hoverable and readable by assistive tech.
function swatch(name, selected, onClick) {
  const button = document.createElement('button');
  button.className = 'swatch' + (selected ? ' on' : '');
  button.style.background = colorHex(name);
  button.title = name;
  button.onclick = onClick;
  return button;
}

// Bytes for each attachment path we have already read, so re-rendering does not
// re-read from disk. Keyed by the `file://` URL that lives in the body.
const attachmentBytes = new Map();

// The body on disk stores a path; a path is what a handed-off Claude session can
// open. But the browser refuses to load a `file://` subresource into a `file://`
// document, so a `file://` src renders as a broken glyph with its alt text —
// which is exactly what shipped. `data:` is exempt for <img>, so the bytes are
// swapped in *on the DOM node only*. The ProseMirror document keeps the path,
// which is what makes it impossible for a data URL to reach disk: nothing here
// touches the markdown.
//
// Re-runs on every change because ProseMirror rebuilds the img from the
// document's own attributes, putting the file:// src back each time.
async function showAttachments() {
  const images = [...document.querySelectorAll('#editor-body img')];
  for (const image of images) {
    const source = image.getAttribute('src') || '';
    if (!source.startsWith('file:')) continue;
    if (!attachmentBytes.has(source)) {
      const project = editorContext && editorContext.project;
      if (!project) continue;
      const data = await callApi('read_attachment', project, source);
      if (data === API_FAILED) continue;
      attachmentBytes.set(source, data);
    }
    // Remember the path before overwriting src — the click handler needs the
    // real file, and a data URL cannot be handed to the OS image viewer.
    image.dataset.attachment = source;
    image.setAttribute('src', attachmentBytes.get(source));
  }
}

// Clicking a thumbnail opens the real file in whatever views images on this
// machine: full size with zoom and pan for free, rather than a lightbox built
// into a 420px window.
document.getElementById('editor-body').addEventListener('click', event => {
  const image = event.target.closest('img');
  if (!image || !image.dataset.attachment) return;
  event.preventDefault();
  callApi('open_attachment', editorContext.project, image.dataset.attachment);
});

function getEditor() {
  if (toastEditor) return toastEditor;
  toastEditor = new toastui.Editor({
    el: document.getElementById('editor-body'),
    initialEditType: 'wysiwyg',
    hideModeSwitch: true,
    theme: 'dark',
    height: '100%',
    // Trimmed to what a notepad needs — no tables, and no raw-markdown mode
    // switch (hidden above), which this overlay has no use for. Images are
    // absent deliberately: they arrive by Ctrl+V, not by hunting a toolbar.
    toolbarItems: [
      ['heading', 'bold', 'italic', 'strike'],
      ['ul', 'ol', 'task'],
      ['quote', 'code'],
    ],
    hooks: { addImageBlobHook: savePastedImage },
  });
  toastEditor.on('change', showAttachments);
  return toastEditor;
}

// Fires for both paste and drop, with the image itself and a callback that
// inserts a reference. Toast UI's default hook inlines the whole image as a
// base64 data URL, which would bury a note's prose under a quarter-megabyte
// of it and hand that to Claude verbatim — so this replaces it with a file on
// disk and a link to it.
//
// Position is not something this passes: the editor inserts at its own current
// selection, which is what makes the image land where the caret was rather
// than at the end. Not calling `insert` at all is how a failure is reported —
// a link to an image that was never written is worse than no image, and
// callApi has already told the user what went wrong.
function savePastedImage(blob, insert) {
  const project = editorContext && editorContext.project;
  if (!project) return;
  const reader = new FileReader();
  reader.onload = async event => {
    const url = await callApi('save_attachment', project, event.target.result);
    if (url === API_FAILED) return;
    // The bytes are already in hand, so seed the display cache rather than
    // making showAttachments read straight back off the disk we just wrote.
    attachmentBytes.set(url, event.target.result);
    insert(url, blob.name || 'screenshot');
  };
  reader.readAsDataURL(blob);
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
      () => { editorContext.type = t.name; renderChips(); }, t.color)));
  document.getElementById('editor-buckets').replaceChildren(
    ...BUCKETS.map(b => chip(b, editorContext.bucket === b,
      () => { editorContext.bucket = b; renderChips(); })));
  document.getElementById('editor-colors').replaceChildren(
    ...Object.keys(CLAUDE_COLORS).map(name => swatch(name, editorContext.color === name,
      () => { editorContext.color = name; renderChips(); })));
}

// Every action button always exists in the markup; this just shows the ones
// this mode uses and hides the rest, so the DOM never gets rebuilt per mode.
function showEditorActions(visibleIds) {
  ['editor-save', 'editor-later', 'editor-skip', 'editor-discard', 'editor-cancel']
    .forEach(id => { document.getElementById(id).hidden = !visibleIds.includes(id); });
}

// The single entry point. context is
// { mode, title, body, project, type, bucket, color, noteId, taskId }; mode is
// one of 'capture' | 'triage' | 'edit'.
function openEditor(context) {
  editorContext = {
    mode: context.mode,
    project: context.project || currentProject,
    type: context.type || (state.settings.types[0] || {}).name,
    bucket: context.bucket || 'now',
    noteId: context.noteId ?? null,
    taskId: context.taskId ?? null,
    // Seeded once per open, same as every other member here — a colour the
    // user picks must survive picking a different project afterwards, so
    // nothing but a swatch click may write this again (invariant 11's "one
    // keystroke marks it yours", applied to a click instead of a keystroke).
    color: context.color || suggestColor(context.project || currentProject),
  };

  // Suppressing a title write is only ever right for a *guessed* title, and
  // triage is the only mode that has one — it derives a suggestion from the
  // note's first line, which must not stomp what you have typed over it.
  //
  // The other two modes carry an authoritative value and must write it every
  // single time. Capture's is the empty string: every capture is a blank
  // slate. Edit's is the task's own persisted title. Letting either be
  // suppressed is how this mechanism produced three separate bugs — the last
  // being that cancelling a title edit and re-opening the same task left the
  // abandoned text in the box, and saving then wrote it to disk over the real
  // title. Note ids and task ids are also drawn from different spaces, and
  // task ids repeat across projects (invariant 6), so an identity shared
  // between modes could collide outright.
  const titleInput = document.getElementById('editor-title');
  if (editorContext.mode === 'triage') {
    // A changed note means the previous note's ownership no longer applies,
    // so it gets its own suggestion; an unchanged one keeps it, which is what
    // makes "one keystroke marks the title yours" last for the life of a note
    // across a Skip that cycles back round to it.
    if (titleFilledFor !== editorContext.noteId) {
      titleFilledFor = editorContext.noteId;
      titleIsUsers = false;
    }
    if (!titleIsUsers) titleInput.value = context.title || '';
  } else {
    titleInput.value = context.title || '';
    titleFilledFor = null;
    titleIsUsers = false;
  }

  loadedBucket = editorContext.bucket;
  loadedBody = context.body || '';
  const editor = getEditor();
  editor.setMarkdown(loadedBody, true);
  normalisedBody = editor.getMarkdown();
  showAttachments();

  renderChips();
  // A task cannot change project — ids are per-project, so a move would mean
  // minting a new one (a documented non-goal). Hiding the chip row rather
  // than disabling it keeps edit mode from suggesting a choice that doesn't
  // exist; capture and triage always need it, so reset it visible on every
  // open rather than only ever setting it hidden.
  // Hide the whole field, label included — hiding only the chip row would
  // leave a "Project" label captioning nothing.
  document.getElementById('editor-project-field').hidden = editorContext.mode === 'edit';
  // "File" is what you do to something that isn't a task yet. Editing one is a
  // save, and a button that names the wrong action is wrong however correct
  // the code behind it is. Set on every open so the label can't stick from
  // whichever mode ran last.
  document.getElementById('editor-save').textContent =
    editorContext.mode === 'edit' ? 'Save' : 'File';

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
  } else if (editorContext.mode === 'edit') {
    showEditorActions(['editor-save', 'editor-cancel']);
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
  // A title and a resolved project/type are non-negotiable in every mode;
  // everything else has a default. Say so rather than doing nothing — a
  // button that silently declines to work reads as broken, and the missing
  // title is not obvious when the body is full of prose.
  if (!title) {
    document.getElementById('editor-title').focus();
    alert('Give it a title first — it is what you will see in the list.');
    return;
  }
  if (!editorContext.project || !editorContext.type) {
    alert('Pick a project and a type first.');
    return;
  }

  const body = getEditor().getMarkdown();

  if (editorContext.mode === 'triage') {
    const note = triageQueue[triageIndex];
    if (!note) return;
    // Pass the editor's current markdown, not the note's on-disk text — the
    // whole point of triaging in an editor is that a typo fix or an added
    // line survives to the task. file_note falls back to the note's own
    // text only when this argument is omitted.
    if (await callApi('file_note', note.id, editorContext.project, title,
        editorContext.type, editorContext.bucket, body, editorContext.color) === API_FAILED) return;
    triageQueue.splice(triageIndex, 1);
    afterNoteRemoved();
    await refresh();
    return;
  }

  if (editorContext.mode === 'edit') {
    // Toast UI normalises markdown on every round-trip (list markers,
    // wrapping, blank lines) even when the user typed nothing — comparing
    // `body` against loadedBody would therefore read as "changed" for every
    // hand-written task and silently reformat prose no one touched.
    // normalisedBody is what THIS load's round-trip produced from the
    // untouched content, so matching it means genuinely untouched: write
    // loadedBody back unchanged, byte for byte. A mismatch means the user
    // really edited, so send what the editor has now.
    // color is a chip selection, not prose — invariant 13's write-only-when-
    // changed treatment exists for the body because Toast UI renormalises
    // markdown on every round-trip; a colour has no such round-trip drift, so
    // it goes in unconditionally like title/type/bucket, never gated on body's
    // changed check above.
    const fields = { title, type: editorContext.type, bucket: editorContext.bucket, color: editorContext.color };
    if (body !== normalisedBody) fields.body = body;
    // Moving buckets without a new order carries the old bucket's position
    // across, which drops the task at an arbitrary point in the target list.
    // Land it at the end, exactly as the row's own bucket picker does in
    // tasks.js — the two controls do the same thing and must agree.
    if (editorContext.bucket !== loadedBucket) {
      fields.order = state.tasks.filter(
        task => task.project === editorContext.project
          && task.bucket === editorContext.bucket
          && task.status !== 'done').length;
    }
    if (await callApi('update_task', editorContext.project, editorContext.taskId, fields)
        === API_FAILED) return;
    closeEditor();
    await refresh();
    return;
  }

  if (await callApi('create_task', editorContext.project, title, body,
      editorContext.type, editorContext.bucket, editorContext.color) === API_FAILED) return;
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
