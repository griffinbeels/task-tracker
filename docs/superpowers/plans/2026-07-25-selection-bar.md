# Selection Bar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When tasks are ticked, show a bar above the list carrying Done, Delete and Clear — and give the app the delete it has never had.

**Architecture:** One new frontend file, `ui/selection.js`, owns the bar and every action that reads the selection; `ui/tasks.js` keeps `selectedIds()` and hands its `spin-up` handler to a shared `selectedInOneProject()` helper. Two new bridge methods sit on a new `Api._tasks()` that three existing methods are refactored onto. `store.delete_task` is the only new backend primitive; bucket repair after a bulk removal is delegated to the existing `groups.renumber`.

**Tech Stack:** Python 3.12, pywebview, pyyaml, pyperclip, pytest. Plain `<script>` files sharing one global scope — no bundler, no framework, no JS test runner.

Spec: `docs/superpowers/specs/2026-07-25-selection-bar-design.md`. Read it before Task 1; this plan implements it and does not restate its reasoning.

## Global Constraints

- **Run tests with** `& ".venv\Scripts\python.exe" -m pytest tests/ -q` from the worktree root `C:\Users\griff\Desktop\code\task_tracker-worktrees\selection-bar`. PowerShell, not Bash — the Bash tool cannot resolve `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`; chain with `;` or `if ($?) { }`. The baseline before Task 1 is **162 passing**.
- **Never run `app.py`.** It opens a window and writes to the user's real `~/.task-tracker/`. Every frontend step here is verified by the coordinator running the app by hand, never by an implementer.
- **Every `Path.write_text` passes `newline="\n"`.** `tests/test_conventions.py` globs `*.py` and fails the build otherwise.
- **Frontend bridge calls go through `callApi('name', ...)`**, and results are compared against `API_FAILED`, never `null`. A convention test globs `ui/*.js` and enforces the second half. A count of `0` is a *valid* return — never test a bridge result for truthiness.
- **User-authored text never reaches `innerHTML`.** Build elements, set `.textContent`.
- **Dependencies stay exactly** `pywebview`, `pyperclip`, `pyyaml`, `pytest`. No new packages.
- **Do not touch `launcher.build_prompt`** or what it emits. Invariant 2 holds verbatim.
- **Assume the constants and line numbers in this plan may be wrong.** They were read off the tree at `6ea6523` but not executed. If an assertion disagrees with working code, say so and check the real behaviour — do not bend the implementation to satisfy a number written here.
- **This branch is based on `feature/task-groups`, not `main`.** Task 9 of the groups plan (the IN PROGRESS section, whose rows are selectable across projects) has not landed. Do not assume a selection is single-project; that is what `selectedInOneProject()` is for.

---

### Task 1: `store.delete_task`

**Files:**
- Modify: `store.py` — a new function directly after `complete_task`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `store.delete_task(task: store.Task) -> None`.

The only new backend primitive. It unlinks the task's file and nothing else — no
attachment cleanup (they are deliberately never garbage-collected), no renumber
(that is the caller's job, and `store.py` must not import `groups.py`, which
imports `store`).

It raises `ValueError("task has no path")` for a task with no path, matching
`save_task` and `complete_task` exactly. Use `unlink(missing_ok=True)`: a file
already gone means the wanted end state is already reached.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_delete_task_removes_the_file(tmp_path):
    task = store.create_task(tmp_path, "Gone", "body", "BUG")
    path = task.path

    store.delete_task(task)

    assert not path.exists()
    assert store.list_tasks(tmp_path) == []


def test_delete_task_leaves_the_other_tasks_alone(tmp_path):
    keep = store.create_task(tmp_path, "Keep", "body", "BUG")
    doomed = store.create_task(tmp_path, "Doomed", "body", "BUG")

    store.delete_task(doomed)

    assert [t.id for t in store.list_tasks(tmp_path)] == [keep.id]


def test_delete_task_leaves_attachments_behind(tmp_path):
    # Attachments are deliberately never garbage-collected: reference counting
    # across hand-editable files is not worth the machinery. Deleting the task
    # that referenced one must not start doing it by the back door.
    task = store.create_task(tmp_path, "Has a screenshot", "body", "BUG")
    pixel = store.save_attachment(
        tmp_path,
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

    store.delete_task(task)

    assert pixel.exists()


def test_delete_task_refuses_a_task_with_no_path():
    task = store.Task(id=1, title="Unsaved", type="BUG", bucket="now",
                      status="open", order=0, created="2026-07-25",
                      started=None, done=None, body="body")

    with pytest.raises(ValueError):
        store.delete_task(task)


def test_delete_task_tolerates_a_file_already_gone(tmp_path):
    task = store.create_task(tmp_path, "Gone twice", "body", "BUG")

    store.delete_task(task)
    store.delete_task(task)

    assert store.list_tasks(tmp_path) == []
```

The base64 above is a 1×1 PNG. `store.save_attachment` validates the data URL
strictly (`b64decode(..., validate=True)`), so it must be real base64 — if it
raises, take a working sample from `tests/test_attachments.py` instead of
patching the string.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q -k delete_task`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'delete_task'`.

- [ ] **Step 3: Implement it**

Add to `store.py` immediately after `complete_task`. Mirror `complete_task`'s
shape: guard on `task.path is None` with a raise, then act.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, 167 total (162 + 5).

- [ ] **Step 5: Commit**

```bash
git add store.py tests/test_store.py
git commit -m "feat: a task can be deleted, which it never could before"
```

---

### Task 2: `Api._tasks`, and the three call sites it replaces

**Files:**
- Modify: `app.py` — a new private helper beside `_find`, and `hand_off` / `reset_to_open` refactored onto it
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Api._tasks(project_name, task_ids) -> tuple[registry.Project, list[store.Task]]`.

`hand_off` and `reset_to_open` each carry the same four lines inline — build
`by_id` over `store.list_tasks`, collect `missing`, raise
`ValueError(f"no such task in {project_name}: {missing}")`, then index back out
in the order the ids arrived. Tasks 3's two new methods would make five copies.

`_tasks` is that block, plus one addition: it **deduplicates while preserving
order**, so a repeated id acts once. `groups._resolve` is the same idea one
layer down and is worth reading first, but it takes an already-loaded task list
and does not dedupe, so it is not directly reusable here.

This task changes no behaviour that any existing test asserts. The whole
existing suite staying green **is** the refactor's test; the new tests below
cover only the dedup, which is new.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_reset_to_open_acts_once_on_a_repeated_id(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")
    task.status = "in-progress"
    task.started = "2026-07-25"
    store.save_task(task)

    returned = app.Api().reset_to_open("repo", [task.id, task.id])

    assert len(returned) == 1
    assert store.list_tasks(repo)[0].status == "open"


def test_reset_to_open_still_raises_on_an_unknown_id(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().reset_to_open("repo", [999])
```

The first test's setup is the fragile part: it needs a task that is genuinely
`in-progress` before `reset_to_open` will do anything. Read `store.reset_to_open`
first and match whatever it actually requires — it refuses a *completed* task,
and may care whether `started` is set.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q -k reset_to_open`
Expected: the dedup test FAILS with `len(returned) == 2`. The unknown-id test
should already PASS — it documents behaviour the refactor must preserve.

- [ ] **Step 3: Add `_tasks` and move `reset_to_open` and `hand_off` onto it**

Put it directly after `_find`, whose shape and error style it mirrors. Keep
`hand_off`'s ordering comment about `groups.auto_group` running *after* the
hand-off — that comment documents a real bug and must survive the edit. Note
`hand_off` passes `wanted` (the raw int list) to `auto_group`; after the
refactor that list must come from the deduped tasks, not from `task_ids`.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, 169 total. Every pre-existing `hand_off` and `reset_to_open`
test must still pass untouched — if one needed editing, the refactor changed
behaviour and is wrong.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "refactor: one place that resolves many task ids, not three"
```

---

### Task 3: `Api.delete_tasks` and `Api.complete_tasks`

**Files:**
- Modify: `app.py` — two new bridge methods
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `store.delete_task` (Task 1), `Api._tasks` (Task 2), the existing `store.complete_task` and `groups.renumber`.
- Produces: `Api.delete_tasks(project_name, task_ids) -> int`, `Api.complete_tasks(project_name, task_ids) -> int`.

Both follow one shape: resolve via `_tasks`, record the set of buckets the tasks
came from **before** acting, act on each, then call
`groups.renumber(project_path, bucket)` for each recorded bucket, then return
the count.

The renumber is why the bucket set is collected first: after a delete the task
is gone, and after a complete its bucket still reads the same but it is no
longer a live task, so either way the source bucket has a hole in its `order`
run. `groups.renumber` is idempotent and writes only the tasks whose order
actually moved.

Returning a count rather than the task dicts is deliberate: the frontend calls
`refresh()` straight afterwards and re-reads everything anyway.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_delete_tasks_erases_every_file_and_returns_the_count(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "A", "body", "BUG")
    second = store.create_task(repo, "B", "body", "BUG")
    kept = store.create_task(repo, "C", "body", "BUG")

    deleted = app.Api().delete_tasks("repo", [first.id, second.id])

    assert deleted == 2
    assert [t.id for t in store.list_tasks(repo)] == [kept.id]


def test_delete_tasks_acts_once_on_a_repeated_id(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    assert app.Api().delete_tasks("repo", [task.id, task.id]) == 1
    assert store.list_tasks(repo) == []


def test_delete_tasks_raises_on_an_unknown_id_and_deletes_nothing(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().delete_tasks("repo", [task.id, 999])

    assert len(store.list_tasks(repo)) == 1


def test_delete_tasks_closes_the_hole_it_leaves_in_the_bucket(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "A", "body", "BUG")
    middle = store.create_task(repo, "B", "body", "BUG")
    last = store.create_task(repo, "C", "body", "BUG")
    assert [t.order for t in (first, middle, last)] == [0, 1, 2]

    app.Api().delete_tasks("repo", [middle.id])

    remaining = sorted(store.list_tasks(repo), key=lambda t: t.order)
    assert [t.order for t in remaining] == [0, 1]


def test_complete_tasks_moves_them_all_to_the_archive(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "A", "body", "BUG")
    second = store.create_task(repo, "B", "body", "BUG")

    assert app.Api().complete_tasks("repo", [first.id, second.id]) == 2

    assert store.list_tasks(repo, include_done=False) == []
    assert len(store.list_tasks(repo, include_done=True)) == 2
    assert all(t.status == "done" for t in store.list_tasks(repo))


def test_complete_tasks_raises_on_an_unknown_id(tmp_path):
    repo = make_repo(tmp_path)
    store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().complete_tasks("repo", [999])


def test_delete_tasks_leaves_another_project_alone(tmp_path):
    # Ids are per-project (invariant 6): every project has a task 1.
    repo = make_repo(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    registry.add_project("other", str(other))
    mine = store.create_task(repo, "Mine", "body", "BUG")
    theirs = store.create_task(other, "Theirs", "body", "BUG")
    assert mine.id == theirs.id

    app.Api().delete_tasks("repo", [mine.id])

    assert [t.title for t in store.list_tasks(other)] == ["Theirs"]
```

The `[0, 1, 2]` assertion in the renumber test is an assumption about
`store.create_task`'s ordering, stated as an assert so it fails loudly rather
than silently invalidating the test. If it is wrong, read `create_task` and fix
the expectation, not the implementation.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q -k "delete_tasks or complete_tasks"`
Expected: FAIL — `'Api' object has no attribute 'delete_tasks'`.

- [ ] **Step 3: Implement both methods**

Put them next to the existing `complete_task`. `app.py` is wiring only — these
two are a resolve, a loop, a renumber loop and a return, with no decisions in
them. Anything that needs a judgement belongs in `store.py` or `groups.py`.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, 176 total.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: delete and complete a whole selection at once"
```

---

### Task 4: The bar itself — markup, styles, and `ui/selection.js`

**Files:**
- Create: `ui/selection.js`
- Modify: `ui/index.html` — the bar's markup after `#toolbar`, and a `<script>` tag
- Modify: `ui/style.css` — the bar's three rules
- Modify: `ui/tasks.js` — `render()` calls `renderSelectionBar()`; `spin-up` moves onto `selectedInOneProject()`
- Modify: `ui/groups.js` — one line in `selectAll.onchange`

**Interfaces:**
- Consumes: `selectedIds()` and `render()` from `ui/tasks.js`; `callApi` / `API_FAILED` / `currentProject` from `ui/state.js`.
- Produces: `renderSelectionBar()`, `selectedInOneProject() -> { project, ids } | null`.

This task delivers a bar that appears, counts, and clears — but whose Done and
Delete buttons are not yet wired. That split is deliberate: a reviewer can accept
"the bar shows up and counts correctly" independently of "delete does the right
thing".

**Markup**, after the closing `</div>` of `#toolbar` and before `#wip-warning`:

```html
<div id="selection-bar" class="actions" hidden>
  <span id="selection-count"></span>
  <span class="spacer"></span>
  <button id="selection-done">Done</button>
  <button id="selection-delete" class="danger">Delete</button>
  <button id="selection-clear" class="quiet">Clear</button>
</div>
```

`class="actions"` is load-bearing — it supplies `display: flex`, the 6px gap,
the 28px control height, the `.danger` red hover and the `.quiet` treatment, all
already defined for the editor's own action row. The `<script src="selection.js">`
tag goes after `groups.js` and before `editor.js`.

**Styles.** Only three rules are needed; everything else comes from `.actions`:

```css
#selection-bar { margin-bottom: 8px; }
/* .actions sets display: flex, which a bare `hidden` attribute loses to on
   equal specificity — the same trap .overlay[hidden] and .chips[hidden]
   already document above. */
#selection-bar[hidden] { display: none; }
#selection-count { font-size: 11px; opacity: .6; }
```

**`renderSelectionBar()`** reads `selectedIds().length`, sets
`#selection-bar.hidden` to `count === 0`, and writes `1 selected` or
`N selected` into `#selection-count` as `textContent`.

**`selectedInOneProject()`** is the existing `spin-up` guard, extracted verbatim
including its two comments: build the set of projects in `selectedIds()`, alert
`'Select tasks from one project at a time.'` and return `null` on more than one,
fall back to `currentProject` when nothing is ticked, and return `null` if there
is no project at all. Returns `{ project, ids }` where `ids` is a plain array of
numbers.

**The change listener** is delegated, registered once at file scope:

```js
document.getElementById('task-list').addEventListener('change', event => {
  if (event.target.classList.contains('select')) renderSelectionBar();
});
```

Delegation is what makes it survive `list.replaceChildren(...)` on every render.
The class guard matters: `#task-list` also contains the per-row `.bucket`
pickers and the group headers' own `.select-group` boxes, whose change events
bubble through here too.

**`Clear`** unticks every `.task .select:checked` *and* every
`.select-group:checked`, then calls `renderSelectionBar()`. Both halves are
needed — a group header left ticked with no members ticked reads as a broken
render.

**`groups.js` needs one line.** Its `selectAll.onchange` sets `row.querySelector('.select').checked`
in JS, and assigning `.checked` does **not** fire a `change` event, so the
delegated listener never sees a whole group being selected. Add a
`renderSelectionBar()` call at the end of that handler. Its sibling handler —
the per-row listener that recomputes `selectAll.checked` — needs nothing, because
those are real user events that already bubble.

**`tasks.js` needs two changes.** `render()` calls `renderSelectionBar()` at the
end, beside the existing `renderWipWarning()`. And the `spin-up` handler becomes
a call to `selectedInOneProject()`, an early return on `null`, and the existing
`callApi('hand_off', ...)`. `tasks.js` loads *before* `selection.js`, which is
fine: the handler is assigned at load but resolves the helper when the button is
clicked.

- [ ] **Step 1: Write `ui/selection.js` with the helper, the renderer, the listener and Clear**

No test to fail first — there is no JS test runner in this project, by decision
(see CLAUDE.md). The verification step is Step 3.

- [ ] **Step 2: Add the markup, the script tag, the styles, and the `tasks.js` / `groups.js` edits**

- [ ] **Step 3: Verify by hand — the coordinator runs the app, not an implementer**

Run `run.bat`. Then, in order:

1. Tick one task. The bar appears reading `1 selected`; the list moves down; **no
   scrollbar appears on the page**.
2. Tick a second. It reads `2 selected`.
3. Untick both. The bar disappears.
4. Tick a group header's select-all. The count equals the number of rows in that
   group — this is the case the extra `groups.js` line exists for.
5. Click `Clear`. Every row box **and** the group header box clear, and the bar
   goes.
6. Type in the search box. The bar does not appear and nothing can be ticked.
7. Tick `All projects`. Same.
8. Tick two rows and press `Spin up Claude`. It behaves exactly as before the
   refactor.

- [ ] **Step 4: Commit**

```bash
git add ui/selection.js ui/index.html ui/style.css ui/tasks.js ui/groups.js
git commit -m "feat: ticking a task shows you that you ticked it"
```

---

### Task 5: Wire Done and Delete

**Files:**
- Modify: `ui/selection.js` — two handlers

**Interfaces:**
- Consumes: `Api.delete_tasks` / `Api.complete_tasks` (Task 3), `selectedInOneProject()` (Task 4).
- Produces: nothing further.

Both handlers have the same four moves: `selectedInOneProject()`, return early
on `null` **or an empty `ids`**, `callApi`, compare against `API_FAILED`,
`await refresh()`. The empty guard is belt-and-braces — the bar is hidden at
zero, so it should be unreachable.

Neither handler writes its own error message. A backend `ValueError` already
reaches the user as an alert through `callApi`.

`Delete` alone asks first:

```js
const what = picked.ids.length === 1 ? 'this task' : `these ${picked.ids.length} tasks`;
if (!confirm(`Delete ${what}? The markdown file is erased. This cannot be undone.`)) return;
```

`confirm()` has **not** been proven to render in this app's WebView2 host. If it
does not appear, it returns `false` and nothing is deleted — the safe direction.
The fallback is in the spec: a two-step button in the bar (`Delete` →
`Delete 3?`, reverting after a few seconds) and no dialog. Report which one
shipped.

- [ ] **Step 1: Write both handlers**

- [ ] **Step 2: Verify by hand — the coordinator runs the app**

Run `run.bat` against a **scratch project**, never a real one — this step
permanently erases task files.

1. Tick two tasks, press `Delete`, cancel the dialog. Both tasks are still there.
2. Tick them again, press `Delete`, confirm. Both `.md` files are gone from
   `.tasks/open/`, and the bar has disappeared.
3. Tick a task inside a group, delete it. The group's remaining rows are still
   one block, and their `order` values in the `.md` files are contiguous.
4. Delete every member of a group. The group is gone with nothing left over.
5. Tick two tasks, press `Done`. Both move to `.tasks/done/` and appear in the
   progress view.
6. Paste a screenshot into a task, then delete the task. The image is still in
   `.tasks/attachments/` — deliberately.

- [ ] **Step 3: Commit**

```bash
git add ui/selection.js
git commit -m "feat: finish or erase a whole selection from the bar"
```

---

### Task 6: The working notes

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing.

Four edits, no more:

1. The architecture table gains a `ui/selection.js` row — "The selection bar: what
   is ticked, and the two things you can do to all of it". Its `ui/tasks.js` row
   drops nothing, since `selectedIds()` stays there.
2. The prose under the table says "five scripts" and lists the load order. Both
   need updating for `groups.js` and `selection.js` — check whether the
   task-groups branch already fixed this before editing, and do not fix it twice.
3. The test count in "Run and test" goes to whatever `pytest -q` actually
   reports.
4. The "No JS test runner" paragraph gains the bar's two silent-when-broken
   checks: a group header's select-all must update the count, and `Clear` must
   clear the header box as well as the rows.

Do **not** add a new invariant. Nothing here has a silent failure mode that the
existing invariants 4 and 6 do not already cover.

- [ ] **Step 1: Make the edits**

- [ ] **Step 2: Run the suite one last time**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, and the number in `CLAUDE.md` matches what it printed.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: the selection bar, in the working notes"
```

---

## Before merging

`feature/task-groups` will have moved on — Tasks 8 through 11 of its plan were
still unlanded when this was written, and Task 9 adds an IN PROGRESS section
whose rows are selectable **across projects**. Merge it into this branch and
re-run the Task 4 and Task 5 hand-verification lists before this goes anywhere
near `main`. `selectedInOneProject()` is the single place that rule lives, so
that is where to look first if a cross-project selection misbehaves.
