# Task Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One editor overlay — reached from Capture, from the inbox, and by
clicking a task row — that writes rich text, holds pasted screenshots inline,
and never overwrites something the user typed.

**Architecture:** A fifth frontend script, `ui/editor.js`, owns the overlay and
a vendored Toast UI Editor instance in WYSIWYG-only mode. `ui/triage.js` shrinks
to queue navigation. The on-disk data model does not change — title and body,
no new frontmatter key — so every existing task file opens without migration.
The backend gains two bridge methods and one storage function.

**Tech Stack:** Python 3.12, pywebview, pytest. Toast UI Editor 3.2.2 vendored
as plain `<script>`/`<link>` — no bundler, no package manager, no new Python
dependency.

**Spec:** `docs/superpowers/specs/2026-07-25-task-editor-design.md`

## Global Constraints

Every task's requirements implicitly include this section.

- **PowerShell, not Bash.** The Bash tool on this machine cannot resolve
  `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`/`||` — chain with `;`
  or `if ($?) { }`.
- **Run tests with** `& ".venv\Scripts\python.exe" -m pytest tests/ -q`.
  Baseline before this plan starts: **87 passing.**
- **Never run `app.py`.** It opens a window and writes to the user's real
  `~/.task-tracker/`. Frontend work is verified by the user running `run.bat`.
- **No new Python dependencies.** They stay exactly `pywebview`, `pyperclip`,
  `pyyaml` (+ `pytest`).
- **Every `write_text` passes `newline="\n"`** (invariant 1). A convention test
  enforces this and will fail the build if you forget.
- **Bytes are written with `write_bytes`**, which has no newline translation —
  the convention test only inspects `write_text` calls, so an image written
  with `write_text` would corrupt silently *and* pass the test.
- **Frontend bridge calls go through `callApi('name', ...)`** (invariant 3) and
  are compared against **`API_FAILED`, never `null`** (invariant 4). A
  convention test enforces the second one.
- **User-authored text never reaches `innerHTML`** (invariant 5). Build
  elements, set `.textContent`. The editor's rendered body is the single
  documented exception, and only because Toast UI sanitises it.
- **Reach `registry.CONFIG_DIR` through the module at call time** (invariant 7).
- **Task ids are per-project integers** (invariant 6). Views that span projects
  disable selection, and must not open the editor either.
- Keep each `ui/*.js` file under ~300 lines. Do not introduce ES modules.

**On the code in this plan:** test code is written to be exact — if an expected
value looks wrong, it may well be wrong, so flag it rather than bending working
code to fit it. Implementation snippets outside tests are illustrative unless
marked otherwise; **read the real API rather than trusting a signature written
here.** This applies especially to Toast UI, which is a third-party library
this plan has not executed against.

---

## File Structure

| File | Responsibility |
|---|---|
| `store.py` | + `attachments_dir()`, `save_attachment()` — where images live and how they are written |
| `app.py` | + `Api.create_task()`, `Api.save_attachment()` — bridge only, no logic |
| `ui/vendor/` | **New.** Vendored Toast UI Editor 3.2.2 assets |
| `ui/editor.js` | **New.** The overlay: fields, chips, Toast UI instance, image paste, save |
| `ui/triage.js` | Shrinks to queue navigation — current note, skip, discard, `2/7` |
| `ui/tasks.js` | Task rows become clickable |
| `ui/index.html` | Editor markup, vendored asset tags, `editor.js` tag |
| `ui/style.css` | Editor layout, and a dark surface for Toast UI |
| `tests/test_attachments.py` | **New.** Attachment storage |
| `tests/test_app.py` | + the two new bridge methods |
| `tests/test_conventions.py` | + the vendored assets are really present |

---

## Task 1: Backend surface for the editor

Two things the editor needs that no bridge method currently provides: creating
a task directly (today a task can only be born by filing an inbox note), and
persisting a pasted image.

**Files:**
- Modify: `store.py` (append after `create_task`)
- Modify: `app.py` (new methods on `Api`)
- Test: `tests/test_attachments.py` (create), `tests/test_app.py` (append)

**Interfaces:**
- Consumes: `store.create_task`, `store.tasks_dir`, `app._task_dict`,
  `app._project` — all already exist.
- Produces:
  - `store.attachments_dir(project_path: Path) -> Path`
  - `store.save_attachment(project_path: Path, data_url: str) -> Path`
  - `Api.create_task(project_name, title, body, type, bucket) -> dict`
  - `Api.save_attachment(project_name, data_url) -> str` (absolute, forward
    slashes)

- [ ] **Step 1: Write the failing tests for attachment storage**

Create `tests/test_attachments.py`:

```python
import base64

import pytest

import store

PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake pixels"
PNG_DATA_URL = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


def test_an_attachment_lands_under_the_project_and_holds_the_real_bytes(tmp_path):
    path = store.save_attachment(tmp_path, PNG_DATA_URL)

    assert path.parent == tmp_path / ".tasks" / "attachments"
    assert path.suffix == ".png"
    assert path.read_bytes() == PNG_BYTES


def test_two_attachments_in_the_same_second_get_distinct_names(tmp_path):
    first = store.save_attachment(tmp_path, PNG_DATA_URL)
    second = store.save_attachment(tmp_path, PNG_DATA_URL)

    assert first != second
    assert first.read_bytes() == second.read_bytes() == PNG_BYTES


def test_the_attachments_directory_is_created_on_demand(tmp_path):
    # A project registered before this feature existed has no attachments/.
    assert not (tmp_path / ".tasks" / "attachments").exists()

    store.save_attachment(tmp_path, PNG_DATA_URL)

    assert (tmp_path / ".tasks" / "attachments").is_dir()


def test_a_jpeg_keeps_its_own_extension(tmp_path):
    url = "data:image/jpeg;base64," + base64.b64encode(b"jpeg bytes").decode()

    assert store.save_attachment(tmp_path, url).suffix == ".jpg"


@pytest.mark.parametrize("bad", [
    "not a data url at all",
    "data:image/png,notbase64encoded",        # missing the ;base64 marker
    "data:text/plain;base64,aGVsbG8=",        # not an image
    "data:image/png;base64,!!!not base64!!!",
])
def test_a_malformed_data_url_raises_rather_than_writing_a_file(tmp_path, bad):
    with pytest.raises(ValueError):
        store.save_attachment(tmp_path, bad)

    attachments = tmp_path / ".tasks" / "attachments"
    assert not attachments.exists() or not list(attachments.iterdir())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_attachments.py -q`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'save_attachment'`

- [ ] **Step 3: Implement attachment storage in `store.py`**

Append after `create_task`. Requirements this must satisfy:

- `attachments_dir(project_path)` returns `tasks_dir(project_path) / "attachments"`.
- `save_attachment` accepts only `data:<mime>;base64,<payload>` where `<mime>`
  starts with `image/`. Anything else raises `ValueError` — including a valid
  data URL of a non-image type, and a payload that is not valid base64.
- Decode with `base64.b64decode(payload, validate=True)`. Without
  `validate=True` the decoder silently discards characters outside the base64
  alphabet, so `!!!not base64!!!` would produce garbage bytes instead of
  raising, and the malformed-input test would fail on the file being written.
- Extension comes from a small explicit map — `image/png` → `.png`,
  `image/jpeg` → `.jpg`, `image/gif` → `.gif`, `image/webp` → `.webp`. An
  unmapped image type raises rather than guessing; a file the editor cannot
  render is worse than a clear error at paste time.
- The name is a UTC timestamp, `%Y-%m-%d-%H%M%S`, with a `-1`, `-2`… suffix on
  collision. This mirrors `inbox.save_note`, which solves the same problem —
  read it and follow it rather than inventing a second scheme.
- Create the directory with `mkdir(parents=True, exist_ok=True)` before writing.
- Write with **`write_bytes`**, never `write_text`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_attachments.py -q`
Expected: PASS (8 tests — the parametrised one counts as 4)

- [ ] **Step 5: Write the failing tests for the two bridge methods**

Append to `tests/test_app.py`. The `isolated_config` fixture and `make_repo`
helper at the top of that file already exist — use them, do not redefine them.

```python
def test_create_task_writes_a_task_and_returns_it_serialised(tmp_path):
    repo = make_repo(tmp_path)

    created = app.Api().create_task("repo", "Replay audio desync",
                                    "- drifts after **3s**", "BUG", "next")

    assert created["title"] == "Replay audio desync"
    assert created["bucket"] == "next"
    assert created["project"] == "repo"
    assert "path" not in created          # Path is not JSON-serialisable
    stored = store.list_tasks(repo)[0]
    assert stored.body == "- drifts after **3s**"


def test_create_task_rejects_an_unknown_bucket(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", "A", "body", "BUG", "urgent")


def test_create_task_rejects_a_non_string_title(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", 42, "body", "BUG", "now")


def test_save_attachment_returns_an_absolute_forward_slash_path(tmp_path):
    import base64
    repo = make_repo(tmp_path)
    url = "data:image/png;base64," + base64.b64encode(b"pixels").decode()

    returned = app.Api().save_attachment("repo", url)

    # Forward slashes because a backslash is an escape character in a markdown
    # link target; absolute so the editor can render it from file:// and the
    # handed-off session can open it from the project root.
    assert "\\" not in returned
    assert returned.startswith(repo.as_posix())
    from pathlib import Path
    assert Path(returned).read_bytes() == b"pixels"
```

- [ ] **Step 6: Run them to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q`
Expected: FAIL — `AttributeError: 'Api' object has no attribute 'create_task'`

- [ ] **Step 7: Implement both bridge methods in `app.py`**

Add to `Api`, next to `update_task`. Both are translation only — no logic
(`app.py` is wiring; business logic belongs in a backend module).

- `create_task` validates exactly the way `update_task` does: bucket must be in
  `store.BUCKETS`, and `title`, `body`, `type` must each be `str`. Reuse that
  shape rather than inventing a second validation style. Return
  `_task_dict(task, project_name)`.
- `save_attachment` resolves the project with `_project(name)` — a
  module-level function in `app.py`, not a method, which every existing `Api`
  method calls bare. Calls
  `store.save_attachment(Path(project.path), data_url)`, and returns
  `path.as_posix()`. `as_posix()` is what produces forward slashes on Windows;
  `str(path)` produces backslashes and would break the markdown link.

- [ ] **Step 8: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — 87 baseline + 8 attachment + 4 bridge = **99**

- [ ] **Step 9: Commit**

```powershell
git add store.py app.py tests/test_attachments.py tests/test_app.py
git commit -m "feat: let the backend create a task directly and store a pasted image"
```

---

## Task 2: Vendor Toast UI Editor 3.2.2

**Files:**
- Create: `ui/vendor/toastui-editor.min.js`, `ui/vendor/toastui-editor.min.css`,
  `ui/vendor/toastui-editor-dark.css`
- Modify: `ui/index.html`
- Test: `tests/test_conventions.py` (append)

**Interfaces:**
- Produces: `window.toastui.Editor` available to every `ui/*.js` script.

**Why vendored and not CDN:** pywebview serves the UI from `file://` and the
app has to work with no network. **Why 3.2.2:** it is the current latest,
published 2023-02-17. **Why not `-all`:** that bundle is 534KB and adds chart
and UML plugins this project will never use; the core bundle is 342KB.

- [ ] **Step 1: Download the three assets**

Verified present at these exact URLs (HTTP 200, sizes as shown):

```powershell
New-Item -ItemType Directory -Force ui\vendor
$base = "https://uicdn.toast.com/editor/3.2.2"
Invoke-WebRequest "$base/toastui-editor.min.js"       -OutFile ui\vendor\toastui-editor.min.js
Invoke-WebRequest "$base/toastui-editor.min.css"      -OutFile ui\vendor\toastui-editor.min.css
Invoke-WebRequest "$base/theme/toastui-editor-dark.css" -OutFile ui\vendor\toastui-editor-dark.css
```

Expected sizes: js ≈ 349,749 bytes, css ≈ 165,438 bytes. The dark theme is
small. If a download lands far under these, it fetched an error page — check
before continuing.

- [ ] **Step 2: Pin the vendoring with a convention test**

Append to `tests/test_conventions.py`. This is the same class of test as the
two already in that file: a mistake that is invisible at the call site. A
half-finished vendor step leaves the app loading a 404 as JavaScript, which
fails only when the user opens the editor.

These are regression guards, not red-then-green tests — they should pass the
moment step 1 succeeded. If either fails now, step 1 did not complete; fix the
download rather than the test.

```python
VENDOR = REPO / "ui" / "vendor"


def test_the_vendored_editor_assets_are_present_and_not_error_pages():
    expected = {
        "toastui-editor.min.js": 300_000,
        "toastui-editor.min.css": 100_000,
        "toastui-editor-dark.css": 1_000,
    }
    problems = []
    for name, floor in expected.items():
        path = VENDOR / name
        if not path.exists():
            problems.append(f"{name} is missing")
        elif path.stat().st_size < floor:
            problems.append(f"{name} is {path.stat().st_size} bytes, expected >{floor}")

    assert not problems, (
        "The editor is vendored, not loaded from a CDN, because the UI is "
        "served from file:// and must work offline. A truncated or missing "
        "asset fails only when a user opens the editor: " + "; ".join(problems)
    )


def test_the_editor_assets_are_loaded_from_vendor_not_a_cdn():
    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")

    assert "uicdn.toast.com" not in markup and "cdn.jsdelivr.net" not in markup, (
        "A CDN reference makes the app require a network connection to edit a "
        "task. Load the vendored copies in ui/vendor/ instead."
    )
```

- [ ] **Step 3: Run it**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_conventions.py -q`
Expected: PASS — 4 tests (the 2 existing plus the 2 new).

- [ ] **Step 4: Wire the assets into `ui/index.html`**

`<head>` currently holds a single `<link rel="stylesheet" href="style.css">`.
Put both vendor stylesheets **above** it, so the app's own rules override the
library's rather than the other way round:

```html
<link rel="stylesheet" href="vendor/toastui-editor.min.css">
<link rel="stylesheet" href="vendor/toastui-editor-dark.css">
<link rel="stylesheet" href="style.css">
```

The script goes at the **end of `<body>`, before `state.js`**. Toast UI's own
issue tracker documents that placing its script in `<head>` breaks it.

```html
<script src="vendor/toastui-editor.min.js"></script>
```

- [ ] **Step 5: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102** (100 + 2 convention tests)

- [ ] **Step 6: Commit**

```powershell
git add ui/vendor ui/index.html tests/test_conventions.py
git commit -m "build: vendor Toast UI Editor 3.2.2 for offline use"
```

- [ ] **Step 7: Hand back for a visual check**

The user runs `run.bat`. Nothing should look different yet — this step is
confirming the vendored CSS has not disturbed the existing layout. Report what
to look at: the header row, the toolbar row, and the three bucket headings.

---

## Task 3: The editor overlay and the capture path

**Files:**
- Create: `ui/editor.js`
- Modify: `ui/index.html` (editor markup, `<script src="editor.js">`),
  `ui/style.css`, `ui/triage.js` (Capture opens the editor instead of the old box)

**Interfaces:**
- Consumes: `callApi`, `API_FAILED`, `refresh`, `state`, `currentProject`,
  `BUCKETS`, `chip()` (currently defined in `triage.js` — move it to
  `editor.js` and let `triage.js` use it from the shared global scope),
  `Api.create_task`, `Api.save_note`.
- Produces:
  - `openEditor(context)` — the single entry point. `context` is
    `{ mode, title, body, project, type, bucket, noteId, taskId }`. `mode` is
    one of `'capture' | 'triage' | 'edit'`.
  - `closeEditor()`

`editor.js` loads after `tasks.js` and before `triage.js` in `index.html`.

- [ ] **Step 1: Add the editor markup to `ui/index.html`**

Replace the existing `#capture` overlay. The `#triage` overlay stays for now —
Task 4 removes it.

```html
<div id="editor" class="overlay" hidden>
  <div id="editor-progress"></div>
  <input id="editor-title" placeholder="Title">
  <div id="editor-body"></div>
  <div id="editor-projects" class="chips"></div>
  <div id="editor-types" class="chips"></div>
  <div id="editor-buckets" class="chips"></div>
  <div class="actions">
    <button id="editor-save">File</button>
    <button id="editor-later">Later</button>
    <button id="editor-skip">Skip</button>
    <button id="editor-discard">Discard</button>
    <button id="editor-cancel">Cancel</button>
  </div>
</div>
```

Every button exists in the markup always; `openEditor` shows and hides them per
mode. That keeps the DOM stable and avoids rebuilding the action row.

- [ ] **Step 2: Style the overlay in `ui/style.css`**

Requirements, not a stylesheet to copy:

- `#editor-body` must `flex: 1` and own the remaining height, with the Toast UI
  container filling it. Toast UI sizes itself to its container only if the
  container has a resolved height — a `flex: 1` child of the existing
  `.overlay` (which is already `display: flex; flex-direction: column`) gives
  it one.
- The app is `color-scheme: dark`. Toast UI's dark theme applies when the
  editor is constructed with `theme: 'dark'` **and** the dark stylesheet is
  loaded. Both are required; either alone leaves a white box in a dark window.
- Do not let the overlay scroll. `.overlay` is `position: fixed; inset: 0`, so
  the editor body scrolling internally is correct and the page scrolling is a
  bug.

- [ ] **Step 3: Write `ui/editor.js`**

This file has no automated test — there is no JS runner in this project, by
standing decision. Its correctness rests on the contracts below and on the
user running the app. Write it to these rules:

**Construction.** Build one Toast UI instance lazily on first open and reuse
it; constructing per-open leaks ProseMirror instances into the DOM. Options to
pass — read the vendored API to confirm names before relying on them:
`el` (the `#editor-body` element), `initialEditType: 'wysiwyg'`,
`hideModeSwitch: true`, `theme: 'dark'`, `height: '100%'`, and a `toolbarItems`
list trimmed to what a notepad needs (headings, bold, italic, strike, ul, ol,
task, quote, code). Toast UI depends on `dompurify` directly, so its rendered
HTML is sanitised — **confirm this is on by default in the vendored build**
before treating invariant 5 as satisfied.

**The no-clobber rules.** These are the point of the file.

1. A suggested title is written **once per note**, and only while the box is
   untouched. Keep a module-level `titleFilledFor` holding the id the title was
   last auto-filled for — `triage.js` already does exactly this, at
   `triageTitleFilledFor`; carry the mechanism over rather than reinventing it.
   Additionally, an `input` listener on `#editor-title` sets a `titleIsUsers`
   flag; once set, no suggestion may overwrite the box for that note.
2. **Clicking a chip re-renders chips only.** Write a `renderChips()` that
   touches `#editor-projects`, `#editor-types` and `#editor-buckets` and
   nothing else, and have every chip's `onclick` call *that*, never a function
   that also sets `#editor-title.value` or calls `setMarkdown`. This is the
   direct cause of the reported bug.
3. Record `loadedBody` (the exact markdown handed to `setMarkdown`) and, right
   after setting it, `normalisedBody = editor.getMarkdown()`. Task 5 uses both.
   Capture them here so the mechanism exists from the start.

**Capture mode.** `openEditor({ mode: 'capture' })`: empty title, empty body,
`project = currentProject`, `type = state.settings.types[0].name`,
`bucket = 'now'`. Show File / Later / Cancel; hide Skip / Discard. Hide
`#editor-progress`.

- **File** requires a non-empty title and a chosen project and type — the same
  guard `triage.js` applies today. Call
  `callApi('create_task', project, title, body, type, bucket)`, compare against
  `API_FAILED`, then `closeEditor()` and `await refresh()`.
- **Later** ignores every chip and calls `callApi('save_note', body)` with the
  raw markdown, exactly as the old capture box did — this is the
  zero-decision path and it must stay one gesture. Skip the call entirely if
  the body is only whitespace, matching the current behaviour.
- **Cancel** closes without writing anything.

**Wiring.** `document.getElementById('capture-button').onclick` now calls
`openEditor({ mode: 'capture' })`. Delete the old `openCapture`, the
`#capture-save` and `#capture-cancel` handlers, and the `#capture` markup.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102**. No Python changed; this confirms nothing regressed.

- [ ] **Step 5: Commit**

```powershell
git add ui/editor.js ui/index.html ui/style.css ui/triage.js
git commit -m "feat: capture a task and file it in one gesture"
```

- [ ] **Step 6: Hand back for a visual check**

The user runs `run.bat` and checks, specifically:
- Capture opens the editor with the cursor in the body.
- Typing `- one`, Enter, `- two` produces a real bullet list, and `**bold**`
  renders bold.
- **Type a title, then click a different type chip. The title must not
  change.** This is the reported bug; it is the one thing that must be checked
  by hand every time this file is touched.
- Nothing scrolls the page, and the editor is dark.

---

## Task 4: The triage path

Fold the inbox queue into the same editor. `triage.js` keeps only the parts
that answer "which note am I on".

**Files:**
- Modify: `ui/triage.js`, `ui/editor.js`, `ui/index.html` (delete `#triage`)

**Interfaces:**
- Consumes: `openEditor`, `Api.list_notes`, `Api.file_note`, `Api.delete_note`.
- Produces: `openTriage()` (kept, now opening the editor), `triageQueue`,
  `triageIndex`.

- [ ] **Step 1: Reduce `ui/triage.js` to queue navigation**

Keep: `triageQueue`, `triageIndex`, `openTriage`, `afterNoteRemoved`, and
`suggestedTitle`. Delete: `renderTriage`, the three chip renderers, the
`#triage-*` button handlers, `chip()` (it moved to `editor.js` in Task 3), and
`triagePick`.

**Preserve `afterNoteRemoved`'s comment and its clamp exactly.** It encodes a
bug that was already fixed once: after splicing out the last note in the queue,
`triageIndex` is past the end, which reads as "queue empty" and hides the
overlay while earlier notes are still unfiled. It clamps back to 0. Do not
simplify it.

`openTriage()` now: fetch notes, set the queue, then
`openEditor({ mode: 'triage' })` for the note at `triageIndex`.

- [ ] **Step 2: Add triage mode to `ui/editor.js`**

`openEditor({ mode: 'triage' })` loads the current note: body = note text,
title = `suggestedTitle(note.text)` subject to no-clobber rule 1, project/type/
bucket carried over from the previous note in the pass so a run of similar
notes is fast. Show File / Skip / Discard / Close; hide Later. Show
`#editor-progress` reading `note 2 / 7`.

- **File** calls `callApi('file_note', note.id, project, title, type, bucket)`,
  then splices the note out and calls `afterNoteRemoved()`, then `refresh()`.
- **Skip** advances `triageIndex` modulo the queue length and re-opens.
- **Discard** calls `delete_note`, splices, `afterNoteRemoved()`, `refresh()`.
- When the queue empties, close the overlay.

Reopening the editor for the next note **resets the title-ownership flag**,
because "once per note" is per note — otherwise note 2 inherits note 1's
"the user typed this" state and never gets a suggestion.

- [ ] **Step 3: Delete the `#triage` overlay from `ui/index.html`**

Remove the whole `<div id="triage">` block. Leave the `#inbox-button` in the
header — `tasks.js` still wires it to `openTriage`.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102**

- [ ] **Step 5: Commit**

```powershell
git add ui/triage.js ui/editor.js ui/index.html
git commit -m "feat: triage a note in the same editor that captured it"
```

- [ ] **Step 6: Hand back for a visual check**

Capture two notes with **Later**, then open the inbox. Check the counter reads
`note 1 / 2`, that File advances to the next note, that Skip cycles, and that
filing the *last* note in the queue leaves the earlier one on screen rather
than closing the overlay.

---

## Task 5: The edit path and the unchanged-body rule

**Files:**
- Modify: `ui/tasks.js`, `ui/editor.js`

**Interfaces:**
- Consumes: `openEditor`, `Api.update_task`.

- [ ] **Step 1: Make task rows open the editor**

In `taskRow()` in `ui/tasks.js`, add a click handler on the row that calls
`openEditor({ mode: 'edit', taskId, project, ... })`.

**It must not fire when the click was on a control.** The row already contains a
checkbox, a `<select>`, and a done button. Guard with
`if (event.target.closest('input, select, button')) return;` before opening.
Without it, ticking the checkbox also opens the editor.

**It must not fire in the cross-project or search views.** `renderSearch` and
`renderAllProjects` both already disable selection because ids are ambiguous
across projects (invariant 6) — the same reasoning forbids editing there.
Remove the handler in both, next to where they set `.select.disabled = true`.

- [ ] **Step 2: Add edit mode to `ui/editor.js`**

Loads the task's title, body, type and bucket. Show Save / Cancel; hide File /
Later / Skip / Discard. **No project chips** — a task cannot change project,
because ids are per-project and a move means minting a new id (a documented
non-goal).

- [ ] **Step 3: Implement the unchanged-body rule**

This is the load-bearing part of the task and it is not obvious.

A WYSIWYG editor normalises markdown. That means `setMarkdown(body)` followed
immediately by `getMarkdown()` can return something *different from what went
in* with no user edit at all — `*` becomes `-`, wrapping changes, blank lines
collapse. Comparing `getMarkdown()` against the loaded body would therefore
report "changed" for every task whose file was hand-written, and quietly
reformat prose the user never touched.

The rule that actually works, using the two values Task 3 captured:

```
current = editor.getMarkdown()
if current === normalisedBody:   send loadedBody   // untouched: original bytes
else:                            send current      // genuinely edited
```

`normalisedBody` is what the editor produced from the untouched content, so
comparing against *it* detects real edits. Writing `loadedBody` back in the
untouched case means the file is byte-identical to before.

Then send only the changed fields to `update_task` — title, type, bucket, and
body only when it differs from `loadedBody`.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102**

- [ ] **Step 5: Commit**

```powershell
git add ui/tasks.js ui/editor.js
git commit -m "feat: click a task to edit it, without reformatting what you did not touch"
```

- [ ] **Step 6: Hand back for a check that needs the shell**

This one cannot be seen in the UI. Have the user, in the repo of a tracked
project:

```powershell
git -C <project> status --short   # note the state
```

Then in the app: open a task written before this feature, change **only its
bucket**, save. Then re-run `git status`. **The task's `.md` file must not
appear as modified in its body** — only the `bucket:` line in its frontmatter
may differ. If the body was reformatted, rule 3 is not working.

---

## Task 6: Inline screenshots

**Files:**
- Modify: `ui/editor.js`

**Interfaces:**
- Consumes: `Api.save_attachment` (Task 1).

- [ ] **Step 1: Wire `addImageBlobHook`**

Add `hooks: { addImageBlobHook: ... }` to the Toast UI options. The hook
receives the pasted or dropped image blob and a callback used to hand back the
URL to insert. **Read the vendored API for the exact signature** — the
getting-started guide does not document it, and this plan has not executed
against it.

The flow:
1. Read the blob as a data URL with `FileReader.readAsDataURL`. It is
   asynchronous — the hook must not call the callback before it resolves.
2. `callApi('save_attachment', project, dataUrl)`. Compare against
   `API_FAILED`.
3. On success, call the hook's callback with the returned path so the editor
   inserts the reference **at the current selection** — which is what makes the
   image land where the caret was, rather than at the end.
4. On failure, do not call the callback and do not insert anything. `callApi`
   has already alerted. A broken image link is worse than no image.

The project is the editor's current project. In `edit` and `triage` mode that
is fixed; in `capture` mode it is whichever project chip is selected, so read
it at paste time, not at open time.

- [ ] **Step 2: Verify what the editor actually inserted**

The reference must be an absolute forward-slash path, e.g.
`![](C:/Users/griff/Desktop/code/foo/.tasks/attachments/2026-07-25-143012.png)`.
Toast UI may percent-encode or otherwise rewrite the URL it was handed. If it
does, and the result no longer opens, that is a real finding — report it rather
than working around it, because the hand-off contract depends on Claude being
able to read that path.

- [ ] **Step 3: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102**

- [ ] **Step 4: Commit**

```powershell
git add ui/editor.js
git commit -m "feat: paste a screenshot straight into a task, where the caret is"
```

- [ ] **Step 5: Hand back for a visual check**

Copy a screenshot to the clipboard. In the editor, type `here is why:`, press
Ctrl+V, then type `and then it drifts`. Check that the image appears **between
the two pieces of text**, not at the end. Then confirm the file exists under
`<project>/.tasks/attachments/`, close and reopen the task, and confirm the
image still renders.

---

## Task 7: Document the system

The invariants established across Tasks 3–6 are each silent when broken, which
is exactly what `CLAUDE.md`'s invariant list is for.

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Update the architecture table and module count**

`CLAUDE.md` currently says "Nine small Python modules and four plain `<script>`
files". It is now **five** scripts. Add rows for `ui/editor.js` and
`ui/vendor/`, and correct `ui/triage.js`'s description to "inbox queue
navigation". Update the load-order paragraph, which names the four scripts
explicitly.

- [ ] **Step 2: Add the new invariants**

Append invariants 11–14, in the voice of the existing ones — what breaks, and
the bug that taught it:

11. A suggested value is written once, into an untouched field.
12. Choosing a chip re-renders chips and nothing else.
13. A body is written only when it changed — compare against the editor's
    *normalised* baseline, not the loaded text, and write the original bytes
    back when unchanged.
14. Attachment paths are produced by the backend and never constructed in JS.

- [ ] **Step 3: Update "Adding a feature" and "Data on disk"**

Add `<project>/.tasks/attachments/` to the on-disk layout block. Note in
"Adding a feature" that `ui/vendor/` is vendored deliberately and must not be
replaced with a CDN reference, and that a convention test enforces it.

- [ ] **Step 4: Update `README.md`** with the editor, in one short paragraph.

- [ ] **Step 5: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS — **102**

- [ ] **Step 6: Commit**

```powershell
git add CLAUDE.md README.md
git commit -m "docs: record the editor's invariants and the vendored dependency"
```

---

## Deferred, deliberately

Named here so they are decisions rather than oversights:

- **Attachments are never garbage-collected.** Deleting a task leaves its
  images on disk.
- **Absolute image paths are not portable.** A tracked project cloned to
  another machine will have the images but the wrong paths.
- **Opening a plain-text inbox note converts it to markdown.** Acceptable —
  triage is the moment you are editing it anyway.
- **Toast UI Editor 3.2.2 was last published 2023-02-17.** It is vendored, so
  it cannot change under the app, but it will not receive fixes either.
