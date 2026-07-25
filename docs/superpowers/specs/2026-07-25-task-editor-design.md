# Task Editor — Design

**Date:** 2026-07-25
**Status:** Draft, pending review
**Supersedes:** the capture/triage sections of
`2026-07-25-task-tracker-design.md` (see *Amendment* below)

One editor, reached three ways, replacing the capture box and the triage
overlay. It writes rich text, holds screenshots inline, and never overwrites
something you typed.

## Problem

Five complaints, one cause: there is no place to *edit a task*.

- Capture asks for nothing, which means every note costs a second pass through
  triage even when you already knew where it belonged.
- A filed task is immutable through the UI. Its title, type and prose can only
  be changed by hand-editing the markdown file.
- Notes are plain text. Prose written as a bulleted list reads back as a wall
  of hyphens.
- A screenshot cannot be attached at all, so "here is why this is broken" has
  to be described instead of shown.
- Changing a type or bucket mid-triage discarded the title you had typed.

The first four are missing surface. The fifth is a bug, and it is the reason
this document treats *not losing user input* as an invariant rather than a
feature.

## Amendment to the original design

The original spec's first principle reads "**Capture is zero-decision.** No
field is required to write a thought down. Structure is added later,
deliberately." That principle survives, but its implementation was too strict:
it made deciding *impossible* at capture time, not merely optional.

Amended: **capture requires no decision, but permits every decision.** Project,
type and bucket arrive prefilled with defaults that are correct most of the
time. Accept them and it is one gesture. Ignore them and press *Later* and the
note goes to the inbox undecided, exactly as before. Nothing became mandatory.

## Non-goals

- **Changing a task's project.** Ids are per-project integers (invariant 6), so
  a move means minting a new id and rewriting cross-references. Project chips
  therefore appear only when the task does not exist yet.
- **A markdown source view.** The editor is WYSIWYG-only. Hand-editing the
  `.md` file remains the escape hatch, as it is today.
- **Garbage-collecting attachments.** Deleting a task leaves its images on
  disk. Reference counting across hand-editable files is not worth the
  machinery for a single-user notepad.
- **A JS test runner.** Unchanged project decision; the editor is verified by
  running the app.

## Approach

### Library: Toast UI Editor, vendored

Requirements it has to satisfy: WYSIWYG (no visible markdown), inline images,
markdown in and markdown out, loadable from a plain `<script>` tag with no
bundler, and usable offline.

`@toast-ui/editor` meets all five. Verified against its docs:
`initialEditType: 'wysiwyg'` with `hideModeSwitch: true` gives a WYSIWYG-only
surface; `getMarkdown()` / `setMarkdown()` are the round-trip; and
`hooks.addImageBlobHook` exists specifically for pasted and dropped images.

Vendor `toastui-editor.min.js` and `toastui-editor.min.css` into `ui/vendor/`.
**Not the CDN** — pywebview loads the UI from `file://` and the app has to work
with no network. **Not `-all`** — that bundle adds chart and UML plugins this
project will never use.

The implementer should read the current API rather than trusting a signature
written here; in particular `addImageBlobHook`'s exact callback shape is not
documented in the getting-started guide and must be read from the API
reference or the vendored source.

**Rejected: OverType.** It is a real `<textarea>` under a styled layer, so it
never rewrites a byte — which would make the clobbering bug structurally
impossible rather than merely fixed, at a tenth the size. It cannot render
images by construction ("variable-height images would break the character
alignment between textarea and preview"). Inline screenshots are a headline
requirement, so it loses. Recorded here because if screenshots are ever cut,
this decision should be revisited rather than rediscovered.

### Cost accepted

A WYSIWYG editor normalises markdown on save: `*` becomes `-`, blank lines
collapse, wrapping changes. This was accepted knowingly, and it is bounded by
the write rule in *Invariants* below — a body is written only when it changed,
so normalisation can only ever touch text just edited.

## Architecture

One new script. No backend module gains a new responsibility; `app.py` gains
one bridge method.

| File | Change |
|---|---|
| `ui/editor.js` | **New.** The editor overlay: fields, chips, the Toast UI instance, image paste. ~200 lines |
| `ui/triage.js` | Shrinks to queue navigation only — which note is current, skip, discard, `2/7` |
| `ui/index.html` | Editor markup, vendored `<script>`/`<link>`, new `<script src="editor.js">` |
| `ui/tasks.js` | Task rows become clickable, opening the editor |
| `ui/vendor/` | **New.** Vendored Toast UI js + css |
| `store.py` | `attachments_dir()`, and writing an image to it |
| `app.py` | One bridge method, `save_attachment` |

`editor.js` loads after `tasks.js` and before `triage.js` — `triage.js` calls
into it, `tasks.js` is called back by it. All five scripts continue to share
one global scope; no ES modules, no build step.

### Data model — unchanged

Title and body, as today. **No new frontmatter key.** Bodies remain markdown
text, so every existing task file opens in the new editor without migration,
and a task hand-written before this change is still valid.

The only new thing on disk is a directory:

```
<project>/.tasks/attachments/2026-07-25-143012.png
```

It sits under `.tasks/`, whose `.gitignore` contains `*`, so attachments are
ignored by default on the same terms as tasks. A project with the `tracked`
flag set commits them along with everything else.

### The three entry points

| Entry | Editor opens with | Buttons |
|---|---|---|
| **Capture** | Empty body, cursor in it. Project = current, type = first configured, bucket = `now` | **File** creates the task · **Later** saves the raw text to the inbox · Cancel |
| **Inbox** | Note text as body, title suggested from its first line, queue position `2/7` | **File** · Skip · Discard · Close |
| **Task row click** | That task's title, body, type and bucket | **Save** · Cancel |

Project chips render only for Capture and Inbox. A task row opened from the
cross-project or search views does not open the editor at all — those views
already disable selection because ids there are ambiguous (invariant 6), and
the same reasoning applies to editing.

### Screenshots

`addImageBlobHook` fires for both paste and drop, receives the image blob, and
hands back a URL for the editor to insert. Position comes from the editor's own
selection, not from anything this code passes: the reference lands wherever the
caret was when you pasted, which is what "in that exact position" requires.
Verify this holds for drop as well as paste — a drop may land at the pointer
rather than the caret, and if so the pointer is the correct target anyway.

Flow: hook receives the blob → JS reads it as a data URL → bridge call
`save_attachment(project_name, data_url)` → `store` writes the decoded bytes to
`<project>/.tasks/attachments/<UTC timestamp>.<ext>` → the absolute path comes
back → the editor inserts the image reference there.

**The reference is stored as an absolute, forward-slash path:**

```
![](C:/Users/griff/Desktop/code/foo/.tasks/attachments/2026-07-25-143012.png)
```

Forward slashes because backslashes are escape characters in markdown link
targets. Absolute for two reasons that both matter more than tidiness:

1. It renders directly in an editor served from `file://` in a different
   directory, with no path rewriting on load or save. A relative path would
   have to be transformed for display and transformed back before writing —
   two chances to corrupt a body that is supposed to be verbatim.
2. On hand-off, Claude receives a path it can open. `TYPE: <body>` carrying
   `![](C:/…/screenshot.png)` means "here is why this is broken" arrives as
   something readable, not as a description of something readable.

**Cost:** task files stop being portable between machines. This only bites on a
project with `tracked` set that is cloned elsewhere, where the images will be
present but the paths wrong. Accepted; the app is a single-user notepad.

Name collisions within the same second get a numeric suffix, matching how
`inbox.save_note` already disambiguates.

## Invariants

Additions to the project's existing list. Each exists because breaking it is
silent.

1. **A suggested value is written once, and only into an untouched field.**
   The title suggested from a note's first line is filled when that note first
   becomes current and never again. One keystroke in the box marks it yours for
   the life of that note.

2. **Choosing a chip re-renders chips and nothing else.** Project, type and
   bucket selection must not re-render the title or body. This is the direct
   cause of the reported bug: a full re-render on every chip click, with the
   field values rebuilt from the source note.

3. **A body is written only when it changed.** Compare the editor's
   `getMarkdown()` against the body as loaded; if equal, leave the file's body
   bytes untouched. Without this, opening a hand-written task and flipping its
   type would silently reformat prose the user never edited — which is the
   normalisation cost escaping its bounds.

4. **Attachment writes go through the backend.** The renderer never touches the
   filesystem. Paths are returned by the bridge, never constructed in JS, so
   there is one place that knows where attachments live.

Existing invariants that constrain this work:

- **Invariant 2 (bodies verbatim)** still holds for hand-off: `build_prompt`
  emits `TYPE: body` and is not changed by this work.
- **Invariant 5 (no user text in `innerHTML`)** still governs the task list,
  which keeps building rows with `textContent`. The editor is the sole place
  markdown becomes HTML. **Confirm at implementation that Toast UI's XSS
  sanitisation is enabled** — task bodies are hand-editable files rendered in a
  page with full `window.pywebview.api` access.
- **Invariant 3 (`callApi`)** and **invariant 4 (`API_FAILED`)** apply to
  `save_attachment` like any other bridge call.

## Error handling

- **`save_attachment` fails** (unwritable directory, malformed data URL): the
  bridge raises, `callApi` alerts, and no reference is inserted. The body is
  not modified — a broken image link is worse than no image.
- **A referenced image is missing** when a task is reopened: the editor shows a
  broken image. Deliberate. Silently stripping the reference would delete
  something the user wrote.
- **Toast UI fails to load**: the editor overlay is unusable and the app is
  effectively broken. Vendoring rather than CDN-loading is what makes this a
  packaging error caught on first run, not an intermittent network failure.
- **An inbox note is plain text** and opening it in a WYSIWYG editor converts
  it to markdown. Accepted: triage is the moment you are editing it anyway.

## Testing

Backend, directly testable with `tmp_path` and the existing
`monkeypatch.setattr(registry, "CONFIG_DIR", ...)` pattern:

- An attachment lands under `<project>/.tasks/attachments/` and the returned
  path points at real bytes matching the input.
- Two attachments written in the same second get distinct names.
- A malformed data URL raises rather than writing a truncated file.
- `save_attachment` on a project with no `.tasks/` creates it.

Frontend: no runner, per the standing project decision. Verified by running the
app, checking specifically that flipping a type chip after typing a title
leaves both the title and the body untouched — that is the regression this
document exists to prevent.

## Open questions

None blocking. Two to settle during implementation by reading the real API,
not by guessing:

1. `addImageBlobHook`'s exact callback signature and how the resulting URL and
   alt text are handed back.
2. Whether Toast UI's sanitiser is on by default in the vendored version, and
   what it strips.
