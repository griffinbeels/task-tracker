# Restore, and the Group Block — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A completed task can be reopened and restored, and a group can be marked done from its header in a tree whose hierarchy reads correctly.

**Architecture:** Two specs, one plan, in a deliberate order. `restore_task` — the first thing in this codebase that ever moves a file *out* of `done/` — lands first, because tasks 4–5 add a button that completes a whole group at once and the undo should exist before the bulk action does. The remaining work is a shared confirm helper, one button, and CSS.

**Tech Stack:** Python 3.12, pywebview, pytest. Plain `<script>` files sharing one global scope — no bundler, no framework, no JS test runner.

## Global Constraints

- **Run tests with:** `& ".venv\Scripts\python.exe" -m pytest tests/ -q` **from the repo root**. PowerShell 5.1 has no `&&`/`||` — chain with `;`. Pointing pytest at another checkout's `tests/` imports the wrong modules and reports bogus failures.
- **Baseline is 285 tests passing** on `main`. Tasks 1–2 raise it; tasks 3–7 must leave it unchanged.
- **Never run `app.py`.** It opens a window and writes to the user's real `~/.task-tracker/`.
- Every `write_text` passes `newline="\n"` (invariant 1).
- Frontend bridge calls go through `callApi('name', ...)` (invariant 3).
- The failure sentinel is `API_FAILED`, a Symbol — never `null`, never truthiness (invariant 4).
- **User-authored text never reaches `innerHTML`** (invariant 5). Task titles, group names and type names are unvalidated strings from hand-editable files.
- A body is written only when it differs from the editor's own normalised baseline (invariant 13).
- **No JS test runner, and do not add one.** The gate for frontend tasks is `tests/test_conventions.py` plus the by-hand checks each task names.
- On Windows, multi-line commit messages go through `git commit -F <file>`.
- **The values in this plan may be wrong.** If an expected value contradicts the real API, say so and stop — do not bend working code to fit a number here.

## File Structure

| File | Change |
|---|---|
| `store.py` | `restore_task` — the inverse of `complete_task` |
| `app.py` | `Api.restore_task` |
| `ui/settings.js` | progress rendering extracted to a function; rows open the editor |
| `ui/editor.js` | a `Restore` action, shown only for a completed task |
| `ui/index.html` | the `Restore` button |
| `ui/selection.js` | `completeTasksWithConfirm`, extracted from the bar's Done |
| `ui/groups.js` | a `done` button on the group header |
| `ui/style.css` | the rail's 2px, and the type scale |
| `CLAUDE.md` | test count, the new manual checks |

Dependencies: 1 → 2 → 3, and 4 → 5. Task 6 is independent CSS. Task 7 is last.

---

### Task 1: `store.restore_task`

**Files:**
- Modify: `store.py` (beside `complete_task`, around :304)
- Test: `tests/test_store.py`

**Interfaces:**
- Produces: `store.restore_task(task: Task) -> Task`

**Design notes:**

Mirror `complete_task`, including how it recovers the project root
(`task.path.parent.parent.parent`). Three differences: it moves `done/` →
`open/`, it clears `done` instead of stamping it, and it assigns a new `order`.

`bucket` is untouched, because `complete_task` never touched it — a finished
task still remembers where it lived. It lands at the **end** of that bucket
rather than reclaiming its old `order`: the tasks it sat among have moved on
without it, and re-inserting it mid-list is a change nobody asked for.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_restore_task_moves_the_file_back_into_open(tmp_path):
    task = store.create_task(tmp_path, "Finished", "body", "BUG")
    store.complete_task(task)
    done_path = task.path
    assert done_path.parent.name == "done"

    store.restore_task(task)

    assert not done_path.exists()
    assert task.path.parent.name == "open"
    assert task.path.exists()


def test_restore_task_reopens_it_and_clears_the_done_date(tmp_path):
    task = store.create_task(tmp_path, "Finished", "body", "BUG")
    store.complete_task(task)

    store.restore_task(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.done is None


def test_restore_task_lands_at_the_end_of_its_bucket(tmp_path):
    # The tasks it sat among moved on without it; reclaiming its old order
    # would re-insert it into the middle of a list the user has since changed.
    first = store.create_task(tmp_path, "First", "body", "BUG")
    store.complete_task(first)
    store.create_task(tmp_path, "Second", "body", "BUG")
    store.create_task(tmp_path, "Third", "body", "BUG")

    store.restore_task(first)

    by_title = {t.title: t for t in store.list_tasks(tmp_path)}
    assert by_title["First"].order > by_title["Third"].order


def test_restore_task_does_not_disturb_the_tasks_already_there(tmp_path):
    first = store.create_task(tmp_path, "First", "body", "BUG")
    store.complete_task(first)
    second = store.create_task(tmp_path, "Second", "body", "BUG")

    store.restore_task(first)

    reloaded = {t.title: t.order for t in store.list_tasks(tmp_path)}
    assert reloaded["Second"] == second.order


def test_restore_task_raises_without_a_path():
    task = store.Task(id=1, title="t", type="BUG", bucket="now", status="done",
                      order=0, created="2026-07-25", started=None,
                      done="2026-07-25", body="b")

    with pytest.raises(ValueError):
        store.restore_task(task)


def test_complete_then_restore_changes_nothing_but_status_and_done(tmp_path):
    # The whole point of the feature: a round trip is a round trip.
    task = store.create_task(tmp_path, "Round trip", "the body", "FEATURE",
                             bucket="someday", color="cyan")
    original = (task.id, task.title, task.body, task.type, task.color,
                task.group, task.bucket)

    store.complete_task(task)
    store.restore_task(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert (reloaded.id, reloaded.title, reloaded.body, reloaded.type,
            reloaded.color, reloaded.group, reloaded.bucket) == original
    assert reloaded.status == "open"
    assert reloaded.done is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q -k restore`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'restore_task'`.

- [ ] **Step 3: Implement**

In `store.py`, directly below `complete_task`:

```python
def restore_task(task: Task) -> Task:
    """Move a completed task back into open/, at the end of its bucket.

    The inverse of complete_task. `bucket` is untouched because completion
    never touched it — the task still remembers where it lived, so it returns
    there. It lands last rather than reclaiming its old `order`: the tasks it
    sat among have moved on without it, and re-inserting it into the middle of
    a list the user has since reordered is a change nobody asked for.
    """
    if task.path is None:
        raise ValueError("task has no path")
    project_path = task.path.parent.parent.parent
    siblings = [t for t in list_tasks(project_path, include_done=False)
                if t.bucket == task.bucket]
    task.status = "open"
    task.done = None
    task.order = len(siblings)
    destination = tasks_dir(project_path) / "open" / task.path.name
    task.path.unlink(missing_ok=True)
    task.path = destination
    return save_task(task)
```

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, 285 → 291.

- [ ] **Step 5: Commit**

Subject: `feat: move a completed task back out of done/`

---

### Task 2: `Api.restore_task`

**Files:**
- Modify: `app.py` (beside `complete_task`, around :269)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `store.restore_task(task)` from Task 1.
- Produces: `Api.restore_task(project_name, task_id) -> dict`

**Design notes:**

Singular, matching `complete_task` — nothing restores in bulk, and the spec
says so deliberately. `_find` already lists `done/`, so it resolves a completed
task with no change.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_restore_task_returns_the_reopened_task(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "Finished", "body", "BUG")
    app.Api().complete_task("repo", task.id)

    payload = app.Api().restore_task("repo", task.id)

    assert payload["status"] == "open"
    assert payload["done"] is None
    assert payload["project"] == "repo"
    # Task.path is a Path, which does not survive the bridge as JSON.
    assert "path" not in payload


def test_a_restored_task_is_open_on_disk(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "Finished", "body", "BUG")
    app.Api().complete_task("repo", task.id)

    app.Api().restore_task("repo", task.id)

    assert store.list_tasks(repo)[0].status == "open"


def test_restore_task_raises_on_an_unknown_id(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().restore_task("repo", 99)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q -k restore`
Expected: FAIL — `AttributeError: 'Api' object has no attribute 'restore_task'`.

- [ ] **Step 3: Implement**

In `app.py`, directly below `complete_task`:

```python
    def restore_task(self, project_name, task_id):
        """Undo a completion — see store.restore_task for where it lands."""
        _, task = self._find(project_name, task_id)
        return _task_dict(store.restore_task(task), project_name)
```

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, 291 → 294.

- [ ] **Step 5: Commit**

Subject: `feat: expose restore across the bridge`

---

### Task 3: The progress view opens a completed task

**Files:**
- Modify: `ui/settings.js` (the `progress-button` handler at :21-61)
- Modify: `ui/editor.js` (`showEditorActions`, and a new handler)
- Modify: `ui/index.html` (the editor's `.actions` row at :75-82)
- Modify: `ui/style.css` (a cursor for the clickable row)

**Interfaces:**
- Consumes: `Api.restore_task` from Task 2.
- Produces: `renderProgress()` — a global in `ui/settings.js`, callable after a restore.

**Design notes:**

The progress body is currently built inside the click handler, so there is no
way to redraw it. Extract it to `renderProgress()`; the button handler becomes
`renderProgress(); document.getElementById('progress').hidden = false;`.

Rows open the editor exactly as a task row does — same overlay, no read-only
mode. `entry.onclick` calls `openEditor` with `mode: 'edit'` and the task's
fields, **including `status`**, which is what tells the editor to offer
Restore. Copy the field list from `taskRow`'s `openEditor({...})` call in
`ui/tasks.js` so the two cannot drift.

`showEditorActions` takes an explicit list, so add `'editor-restore'` to the
array it iterates and pass it in edit mode only when the task is done:

```js
} else if (editorContext.mode === 'edit') {
  showEditorActions(context.status === 'done'
    ? ['editor-save', 'editor-restore', 'editor-cancel']
    : ['editor-save', 'editor-cancel']);
```

**Order is load-bearing in the restore handler.** `refresh()` reloads
`state.tasks`, and the progress list is derived from it. Redraw before
refreshing and you filter state that still lists the task as `done`, so it
draws the row it just removed:

```js
document.getElementById('editor-restore').onclick = async () => {
  if (await callApi('restore_task', editorContext.project,
      editorContext.taskId) === API_FAILED) return;
  closeEditor();
  await refresh();
  renderProgress();
};
```

Markup, after `editor-save` in the `.actions` row:

```html
<button id="editor-restore">Restore</button>
```

CSS — the row must look clickable, and `.entry` currently does not:

```css
.entry { cursor: pointer; border-radius: 5px; }
.entry:hover { background: rgba(127, 127, 127, .12); }
```

- [ ] **Step 1: Implement**

The extraction, the `onclick`, the button, the `showEditorActions` change, the restore handler, the CSS.

- [ ] **Step 2: Check the conventions test**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS at 294, unchanged — no Python added.

- [ ] **Step 3: Syntax-check the scripts**

Run: `node --check ui/settings.js; node --check ui/editor.js`
Expected: no output from either.

- [ ] **Step 4: Verify by reading, and state each in your report**

1. `renderProgress()` is called from both the button handler and the restore handler.
2. The restore handler refreshes **before** redrawing, and you can say what breaks if reversed.
3. The `openEditor` call passes `status`, and its field list matches `taskRow`'s.
4. `Restore` is hidden in capture, triage, and edit-of-an-open-task.
5. No user-authored string reaches `innerHTML` in anything you touched.

- [ ] **Step 5: Commit**

Subject: `feat: open and restore a completed task from Progress`

---

### Task 4: One shared "complete many" path

**Files:**
- Modify: `ui/selection.js` (the `selection-done` handler at :52)

**Interfaces:**
- Produces: `completeTasksWithConfirm(project, ids)` — a global in `ui/selection.js`.

**Design notes:**

**This task changes no behaviour.** It extracts the selection bar's `Done` body
so Task 5 can reuse it rather than growing a second copy that prompts
differently or forgets the partial-failure refresh.

```js
// Both the selection bar and a group header complete many tasks at once, and
// they must ask the same question and recover the same way. One function, so
// they cannot drift.
async function completeTasksWithConfirm(project, ids) {
  if (!ids.length) return;
  if (ids.length >= DONE_CONFIRM_THRESHOLD && !confirm(
      `Mark ${ids.length} tasks done? They move to .tasks/done/ and `
      + `the app has no way back.`)) return;
  // Refresh whether or not the call succeeded: complete_tasks validates every
  // id up front but then acts file-by-file, so a failure partway through can
  // still leave earlier tasks moved to done/. Refreshing on the failure path
  // too is what stops the list drawing rows for tasks that already left.
  await callApi('complete_tasks', project, ids);
  await refresh();
}
```

**A reviewer will notice the `=== API_FAILED` comparison is gone, and should
check rather than assume.** It is behaviour-preserving: the original branched
on it and *both* branches ran `await refresh()`. The comparison existed only to
choose between two identical outcomes. `callApi` still reports the failure to
the user itself.

The `selection-done` handler becomes:

```js
document.getElementById('selection-done').onclick = async () => {
  const picked = selectedInOneProject();
  if (!picked) return;
  await completeTasksWithConfirm(picked.project, picked.ids);
};
```

Leave `selection-delete` alone — it has its own dialog and its own reasoning.

- [ ] **Step 1: Implement**

- [ ] **Step 2: Check the conventions test and syntax**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q; node --check ui/selection.js`
Expected: PASS at 294; no output from `node`.

- [ ] **Step 3: Check by hand — this is a refactor, so prove it did nothing**

1. Tick 2 tasks → `Done` completes both with no prompt.
2. Tick 3 → `Done` asks first; Cancel leaves all three.
3. `Delete` still asks its own question and still works.

- [ ] **Step 4: Commit**

Subject: `refactor: one place that completes many tasks at once`

---

### Task 5: A group can be marked done

**Files:**
- Modify: `ui/groups.js` (`groupBlock`, after the `showReset` block at :179-191)
- Modify: `ui/style.css` (the hover-reveal rule beside `.task:hover .done`)

**Interfaces:**
- Consumes: `completeTasksWithConfirm(project, ids)` from Task 4.

**Design notes:**

Between `↩` and `×`, so the two "change these tasks" actions are adjacent and
"unmake the group" stays last:

```js
  const done = document.createElement('button');
  done.className = 'done';
  done.textContent = 'done';
  done.title = 'Mark the whole group done';
  done.onclick = () =>
    completeTasksWithConfirm(project, block.tasks.map(task => task.id));
  header.append(done);
  releaseDragWhileUsing(done, header);
```

**`releaseDragWhileUsing` is not optional.** The header is draggable in bucket
sections, and without it a mousedown on the button starts a drag instead of a
click. Every other header control already calls it.

**Scope is `block.tasks` — what this header drew.** In IN PROGRESS a header can
read `2 of 5`; `done` completes those 2. That is what the `↩` beside it already
does, so the two header actions agree.

It is added unconditionally, not behind an option: rows have `done` in both
bucket sections and IN PROGRESS, so headers should too.

CSS — `.done` already defaults to `opacity: 0`; only the hover rule needs the
new selector:

```css
.task:hover .done, .group-header:hover .done { opacity: .6; }
```

- [ ] **Step 1: Implement**

- [ ] **Step 2: Check the conventions test and syntax**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q; node --check ui/groups.js`
Expected: PASS at 294; no output from `node`.

- [ ] **Step 3: Check by hand**

1. A group of 2 → `done` completes both with no prompt; the block disappears.
2. A group of 5 → `done` asks first; Cancel leaves all five.
3. In IN PROGRESS, a header reading `2 of 5` → `done` completes 2; the other 3 stay in their bucket, group intact.
4. Drag a group by its header — still works.
5. Press `done` — it does not start a drag.

- [ ] **Step 4: Commit**

Subject: `feat: mark a whole group done from its header`

---

### Task 6: The tree reads as a tree

**Files:**
- Modify: `ui/style.css` (`.group` at :144, `.project-heading` at :117, `.group-name` at :154, `.group-name-input` at :155)

**Design notes — the 2px, measured:**

```
.task          padding-left: calc(6px + var(--caret-gutter))  = 21px
.group-header  padding-left: calc(6px + var(--caret-gutter))  = 21px
.group         border-left: 2px      <-- a real box-model edge
```

A group header is a sibling of a top-level task row; both intend their checkbox
at 21px, and the border puts the group's at 23px. Replace the border with an
inset shadow, which paints identically and occupies no layout space:

```css
.group { box-shadow: inset 2px 0 0 rgba(127, 127, 127, .28);
         border-radius: 0 5px 5px 0; margin: 2px 0; }
```

Do **not** compensate with padding instead — that fixes the header and leaves
`.group > .task` members 2px off, trading a visible misalignment for a subtler
one.

**Design notes — the scale.** The label chain shrinks with depth; task titles
are content and sit outside it. Without that exemption, "smaller as you go
deeper" ends with the text you actually read being the smallest on screen.

| | from | to |
|---|---|---|
| `.project-heading` | `font-size: 10px; letter-spacing: .08em; opacity: .45` | `font-size: 12px; font-weight: 700; letter-spacing: .04em; opacity: .85` |
| `.group-name` | `font-weight: 600` (inherits 13px) | `font-size: 11px; font-weight: 600; opacity: .7` |
| `.group-name-input` | `font: inherit; font-weight: 600` | add `font-size: 11px` |
| `.title`, `h2` | — | unchanged |

`.group-name-input` needs the explicit size because `font: inherit` picks up
13px from the body — without it, renaming a group visibly resizes its own text
mid-edit.

Project names stay sentence case: `task_tracker` is a folder name and
uppercasing it would misrepresent what it is.

- [ ] **Step 1: Implement**

- [ ] **Step 2: Check the conventions test**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS at 294.

- [ ] **Step 3: Check by hand**

1. A group header's checkbox lines up **exactly** with a top-level task row's.
2. The group's left rail still draws, same colour and weight.
3. A project heading reads as more important than a group header inside it.
4. Renaming a group does not resize its text as the input appears.
5. The window gains no horizontal scrollbar at its default 420px.

- [ ] **Step 4: Commit**

Subject: `fix: align the group rail, and let a project outrank its groups`

---

### Task 7: Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update**

1. The test count in the Run-and-test block — read the real number from a fresh run.
2. `store.py`'s architecture row: it now moves tasks out of `done/` as well as in.
3. `ui/settings.js`'s row: the progress view opens a completed task.
4. The manual-check list: the five group-block checks from Tasks 5–6, and the four restore checks (open a completed task and change nothing → `git status` shows no diff; edit its body and save → the change lands and the file stays in `done/`; Restore → it leaves Progress and reappears at the bottom of its original bucket; the editor's Restore is absent for an open task).
5. Known gaps: note that restore is singular — nothing restores in bulk.

- [ ] **Step 2: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 3: Commit**

Subject: `docs: record restore, and the group block's manual checks`

---

## Notes for the implementer

- `.tasks/` is git-ignored in this repo, so a tracked project's task files never
  appear in `git status`. The "no body diff" checks refer to running `git
  status` inside a *tracked* project registered in the tracker, not this one.
- Both specs are in `docs/superpowers/specs/` dated 2026-07-25:
  `restoring-a-completed-task-design.md` and `group-block-hierarchy-design.md`.
  Read the one matching your task if a decision here looks arbitrary — the
  reasoning is there.
