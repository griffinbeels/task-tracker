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
// Per-note triage state: which notes the user has typed a title for, and the
// colour each note is showing. Keyed by note id, because "one keystroke marks
// it yours for the life of that note" (design spec invariant 1) has to hold
// while the queue *cycles* — Skip walks round the queue, so a note is
// routinely re-opened with other notes visited in between.
//
// Both started life as a single "which note did I last fill" slot, which
// remembers exactly one note. With a queue of [A, B]: pick green on A, Skip to
// B, Skip back to A, and the slot says 'B', so A was read as a new note and
// got a fresh random roll — the pick silently gone. The title slot lost a
// typed title on the very same cycle. Two notes was enough for both.
//
// Only triage reads these. Type and bucket need nothing of the sort —
// openTriageNote() carries those forward unconditionally on every note change,
// on purpose, so a re-open shows the same value either way. Colour and title
// are the opposite: a genuinely new note must get its own suggestion, so
// identity has to be tracked rather than carried forward. openTriage() clears
// both, so a fresh pass starts fresh instead of inheriting the last pass's ids.
const titleIsUsers = new Set();  // note ids whose title box the user has typed in
const colorForNote = new Map();  // note id -> the colour that note is showing
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
// The group the task was in when it was opened, so the save can tell a real
// regroup from a no-op. null for an ungrouped task and for the two modes that
// create rather than edit.
let loadedGroup = null;

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
  const context = editorContext;
  const project = context && context.project;
  if (!project) return;
  const reader = new FileReader();
  reader.onload = async event => {
    const url = await callApi('save_attachment', project, event.target.result);
    if (url === API_FAILED) return;
    // Everything above this line is asynchronous — a FileReader and a bridge
    // round-trip — and the overlay is closable throughout. Insert only if the
    // editor is still showing the thing that was pasted into; otherwise the
    // reference lands in whatever task happens to be open now, which is both
    // the wrong body and a body the user never touched. The file on disk is
    // kept either way, on the same terms as every other orphan (attachments
    // are deliberately never garbage-collected — see store.save_attachment).
    // Identity, not equality: openEditor builds a fresh context object on every
    // open, so `!==` catches a different task, a different note, and the same
    // task reopened. Closing does not clear the context, so the overlay's own
    // visibility is the other half of the question.
    if (editorContext !== context || document.getElementById('editor').hidden) return;
    // The bytes are already in hand, so seed the display cache rather than
    // making showAttachments read straight back off the disk we just wrote.
    attachmentBytes.set(url, event.target.result);
    // A dropped file brings its own name, and that name goes straight into the
    // markdown link's alt text — where an unescaped `]` closes the bracket
    // early and breaks the link. `a]b.png` produced `![a]b](file:///…)`.
    // Pasted images have no name, so this only ever bites on drag-and-drop.
    insert(url, (blob.name || 'screenshot').replace(/[[\]]/g, ''));
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
      () => {
        editorContext.color = name;
        // Without this, a click here is invisible to the per-note map that
        // openEditor reads — a Skip back to this note would restore the stale
        // pre-click value and silently undo the pick.
        if (editorContext.mode === 'triage') colorForNote.set(editorContext.noteId, name);
        renderChips();
      })));
  renderGroupChips();
}

// Every group already in this project, from the tasks we are holding — there
// is no group entity to fetch, a group is just a name its members share.
function projectGroups(project) {
  return [...new Set(state.tasks
    .filter(t => t.project === project && t.group && t.status !== 'done')
    .map(t => t.group))].sort((a, b) => a.localeCompare(b));
}

function groupMembers(project, name) {
  return state.tasks.filter(
    t => t.project === project && t.group === name && t.status !== 'done');
}

// The group row, and the warning that the bucket above it is not this task's
// alone. Edit only: create_task and file_note take no group, and a group is
// something you put an existing task into.
//
// Picking a group also sets the When chips to that group's bucket, because
// joining one takes its bucket — leaving the old value showing would make the
// save move the whole group somewhere nobody asked for.
function renderGroupChips() {
  const field = document.getElementById('editor-group-field');
  const hint = document.getElementById('editor-bucket-hint');
  // Hidden for a completed task as well as outside edit mode. A done task
  // keeps its `group` string in done/ but is not part of the group any more
  // (invariant 15), so groups.assign/remove — which resolve ids against the
  // live tasks — raise "no such task" for it. The save regroups BEFORE
  // update_task and returns on the failure, so one chip click here would
  // discard the title, type, bucket, colour and body edits made beside it.
  field.hidden = editorContext.mode !== 'edit' || editorContext.status === 'done';
  if (field.hidden) { hint.hidden = true; return; }

  const project = editorContext.project;
  const join = name => {
    editorContext.group = name;
    if (name) {
      const anchor = groupMembers(project, name)
        .reduce((lowest, task) => (!lowest || task.order < lowest.order ? task : lowest), null);
      if (anchor) editorContext.bucket = anchor.bucket;
    }
    renderChips();
  };

  document.getElementById('editor-groups').replaceChildren(
    chip('none', !editorContext.group, () => join(null)),
    ...projectGroups(project).map(
      name => chip(name, editorContext.group === name, () => join(name))));

  hint.hidden = !editorContext.group;
  if (editorContext.group) {
    const members = groupMembers(project, editorContext.group);
    const size = members.some(t => t.id === editorContext.taskId)
      ? members.length : members.length + 1;
    hint.textContent =
      `When moves all ${size} in “${editorContext.group}” — a group is one bucket.`;
  }
}

// Every action button always exists in the markup; this just shows the ones
// this mode uses and hides the rest, so the DOM never gets rebuilt per mode.
function showEditorActions(visibleIds) {
  ['editor-save', 'editor-later', 'editor-skip', 'editor-discard', 'editor-restore', 'editor-cancel']
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
    status: context.status || 'open',
    group: context.group ?? null,
    // Placeholder — set below. Capture and edit reseed unconditionally, same
    // as every other member above; triage looks its note up in colorForNote
    // first (see its comment), so the two paths can't share this one line.
    color: null,
  };

  // Seeded once per open — a colour the user picks must survive picking a
  // different project afterwards, so nothing but a swatch click may write
  // this again (invariant 11's "one keystroke marks it yours", applied to a
  // click instead of a keystroke). Triage additionally keys the suggestion to
  // the note: a note already seen keeps the colour it has (suggested or
  // picked) however much of the queue was walked in between, and a note never
  // seen has no entry, so it gets its own fresh roll.
  if (editorContext.mode === 'triage') {
    if (!colorForNote.has(editorContext.noteId)) {
      colorForNote.set(editorContext.noteId,
        context.color || suggestColor(editorContext.project));
    }
    editorContext.color = colorForNote.get(editorContext.noteId);
  } else {
    editorContext.color = context.color || suggestColor(editorContext.project);
  }

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
    // A note nobody has typed a title for takes this open's suggestion; one
    // they have keeps what they typed, which is what makes "one keystroke
    // marks the title yours" last for the life of that note however far round
    // the queue Skip travels before coming back to it.
    if (!titleIsUsers.has(editorContext.noteId)) titleInput.value = context.title || '';
  } else {
    titleInput.value = context.title || '';
  }

  loadedBucket = editorContext.bucket;
  loadedGroup = editorContext.group;
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
    showEditorActions(editorContext.status === 'done'
      ? ['editor-save', 'editor-restore', 'editor-cancel']
      : ['editor-save', 'editor-cancel']);
    // A task with a Claude session already running against it can still be
    // renamed, retyped, rebucketed and regrouped — but none of that reaches
    // the session, which is worth saying rather than leaving to be discovered.
    const progress = document.getElementById('editor-progress');
    const running = editorContext.status === 'in-progress';
    progress.hidden = !running;
    if (running) progress.textContent = "In progress · edits here won't reach the session";
  }

  document.getElementById('editor').hidden = false;
  editor.focus();
}

function closeEditor() {
  document.getElementById('editor').hidden = true;
}

// Triage is the only mode that ever suppresses a title write, so it is the
// only mode with anything to record — and the claim is recorded against the
// note, so it lasts that note's life rather than until some other note is
// opened. Capture and edit reseed unconditionally and never read this.
document.getElementById('editor-title').addEventListener('input', () => {
  if (editorContext && editorContext.mode === 'triage') {
    titleIsUsers.add(editorContext.noteId);
  }
});

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
    // Refresh before opening the next note, not after: suggestColor counts
    // state.tasks, so opening first would suggest against a list that does not
    // yet contain the task just filed — and two notes filed in a row could be
    // handed the same colour, the one thing the least-used heuristic exists to
    // prevent. Safe in this order because refresh() → render() touches the
    // task list and the hand-off row, never the editor overlay, and
    // openTriageNote() reads editorContext, which survives it.
    await refresh();
    afterNoteRemoved();
    return;
  }

  if (editorContext.mode === 'edit') {
    // Regroup first. Joining a group takes that group's bucket, so the bucket
    // this task is judged against below has to be the one it ends up with —
    // otherwise update_task reads a bucket "change" that nobody asked for and
    // moves the new group somewhere else entirely.
    if (editorContext.group !== loadedGroup) {
      const regrouped = editorContext.group
        ? await callApi('group_tasks', editorContext.project,
                        [editorContext.taskId], editorContext.group)
        : await callApi('ungroup_tasks', editorContext.project, [editorContext.taskId]);
      if (regrouped === API_FAILED) return;
    }

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
    // tasks.js — the two controls do the same thing and must agree. A grouped
    // task ignores this: update_task drops `order` for one, because the group
    // owns its own ordering.
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

// Only ever visible in edit mode on a done task (showEditorActions above).
// refresh() must run before renderProgress(): the progress list is derived
// from state.tasks, and refresh() is what reloads it — redraw first and it
// filters state that still lists this task as done, so it draws the row it
// just removed.
document.getElementById('editor-restore').onclick = async () => {
  if (await callApi('restore_task', editorContext.project,
      editorContext.taskId) === API_FAILED) return;
  closeEditor();
  await refresh();
  renderProgress();
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
