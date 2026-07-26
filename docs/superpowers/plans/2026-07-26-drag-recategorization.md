# Drag Recategorization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a drag change a task's bucket, its group and whether it is running — in one gesture, across every section on screen.

**Architecture:** A drop resolves to a *destination* (`bucket`, `group`, `status`) plus a position. `groups.place` applies that destination in Python, where it can be tested; the frontend's job shrinks to naming one. `wireDrag` stops being six per-section controllers with six private `dragged` variables — the reason cross-section drops are silent no-ops today — and becomes one delegated controller on `#task-list`.

**Tech Stack:** Python 3.12 (`pyyaml`, `pywebview`, `pyperclip`, `pytest`), plain `<script>` JavaScript with no bundler, no JS test runner.

## Global Constraints

- **Spec:** `docs/superpowers/specs/2026-07-26-drag-recategorization-design.md`. Read it before Task 1.
- **Run tests from the worktree root, with a relative path:** `& ".venv\Scripts\python.exe" -m pytest tests/ -q`. PowerShell, not Bash — the Bash tool cannot resolve `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`; chain with `;` or `if ($?) { }`.
- **Baseline is 312 tests passing.** Any drop in that count is a regression, not a rewrite.
- **Never run `app.py`.** It opens a window on the user's desktop and writes to their real `~/.task-tracker/`. No test may put anything on screen.
- **Invariant 16 is the thing this feature can most easily break:** a group lives in one bucket and its members are contiguous in `order`. Every membership or bucket change ends with `groups.renumber` on **every bucket it touched** — source as well as destination.
- **Invariant 6:** never resolve a task id against `currentProject`. A row's project comes from its own `dataset.project`.
- **Invariant 5:** user-authored text (titles, group names, project names) never reaches `innerHTML`. Build elements and set `.textContent`.
- **Invariant 4:** the failure sentinel is `API_FAILED`, never `null`.
- **Invariant 3:** frontend bridge calls go through `callApi('name', ...)`.
- **Expected values in the test snippets below may be wrong.** They were reasoned about, not executed. If a test fails on an arithmetic expectation, check the constant against the real behaviour before changing working code to satisfy it — and say so in the commit.
- **Append tests at the END of the target file**, never into the last existing test. `tests/test_groups.py`, `tests/test_app.py` and `tests/test_store.py` are all bare-`def` pytest files (no `unittest.main()`), so plain `def test_x(tmp_path):` functions are the correct shape.

---

## File Structure

| File | Responsibility after this change |
|---|---|
| `store.py` | Adds `start_task` — the inverse of `reset_to_open`, beside it. The status vocabulary lives here. |
| `launcher.py` | `hand_off` stops inlining the three lines that start a task and calls `store.start_task`. |
| `groups.py` | Adds `place` — applies a destination to a list of tasks and leaves every touched bucket satisfying invariant 16. |
| `app.py` | Adds `Api.place_task` and `Api.place_group`. Type refusal only; domain checks stay in `groups.place`. |
| `ui/groups.js` | `wireDrag` becomes one delegated controller bound once to `#task-list`, and resolves a destination instead of a section-local intent. |
| `ui/tasks.js` | Stops calling `wireDrag`; stamps `section.dataset.project`; always renders the IN PROGRESS section. |
| `ui/inprogress.js` | Renders when empty; group headers become draggable. |
| `ui/style.css` | `drop-into` on headings; the empty-section line. |
| `CLAUDE.md` | The new invariant, and the by-hand checks that go to the user. |

---

### Task 1: `store.start_task`, and one definition of "started"

**Files:**
- Modify: `store.py` (add after `reset_to_open`, which ends at line 372)
- Modify: `launcher.py:415-419`
- Test: `tests/test_store.py` (append at end of file)

**Interfaces:**
- Produces: `store.start_task(task: Task) -> Task` — sets `status="in-progress"`, sets `started` to `_today()` only if it is currently unset, saves, returns the task. Raises `ValueError` on a completed task.
- Consumes: `store._today()` (line 115), `store.save_task`.

- [ ] **Step 1: Write the failing tests**

Append at the end of `tests/test_store.py`:

```python
def test_start_task_marks_it_in_progress_and_stamps_the_day(tmp_path):
    task = store.create_task(tmp_path, "A", "body", "BUG")

    started = store.start_task(task)

    assert started.status == "in-progress"
    assert started.started == store._today()
    assert store.list_tasks(tmp_path)[0].status == "in-progress"


def test_start_task_keeps_the_original_start_date(tmp_path):
    task = store.create_task(tmp_path, "A", "body", "BUG")
    task.started = "2020-01-01"

    started = store.start_task(task)

    # Re-claiming a task that was already begun must not restate when the work
    # started — the progress view is built on these dates.
    assert started.started == "2020-01-01"


def test_start_task_refuses_a_completed_task(tmp_path):
    task = store.create_task(tmp_path, "A", "body", "BUG")
    store.complete_task(task)

    with pytest.raises(ValueError):
        store.start_task(task)
```

- [ ] **Step 2: Run to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q -k start_task`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'start_task'`.

- [ ] **Step 3: Implement**

Add `start_task` immediately after `reset_to_open` in `store.py`. It is the mirror of that function and its docstring should say so: `reset_to_open` retracts the claim that work began and therefore clears `started`; this one makes the claim and stamps the day, but only when there is not already a day recorded — a task reset and re-started keeps the date it first began.

Refuse `status == "done"` for the same reason `reset_to_open` does: leaving the archive is `restore_task`'s job, and the progress view is built on `done/`'s dates.

- [ ] **Step 4: Run to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q`
Expected: PASS.

- [ ] **Step 5: Point `launcher.hand_off` at it**

`launcher.py:415-419` currently computes `today` itself and sets `status`/`started`/`save_task` inline for each task. Replace that loop body with a `store.start_task(task)` call and delete the now-unused `today` local. Check whether `datetime`/`timezone` are still used elsewhere in `launcher.py` before touching the imports — remove them only if nothing else needs them.

- [ ] **Step 6: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 315 passed. `tests/test_launcher.py` must be green without modification — the observable behaviour of `hand_off` is unchanged.

- [ ] **Step 7: Commit**

```bash
git add store.py launcher.py tests/test_store.py
git commit -m "feat: store.start_task, the inverse of reset_to_open"
```

---

### Task 2: `groups.place`

The core of the feature, and the only part where a silent invariant break is possible.

**Files:**
- Modify: `groups.py` (add after `remove`, at end of file)
- Test: `tests/test_groups.py` (append at end of file)

**Interfaces:**
- Consumes: `groups._live_tasks`, `groups._resolve`, `groups._clean`, `groups.renumber`, `store.BUCKETS`, `store.reorder_bucket`, `store.save_task`, `store.start_task` (Task 1), `store.reset_to_open`.
- Produces:

```python
def place(project_path, task_ids, *, bucket=None, group=None, status=None,
          ordered_ids=None) -> None
```

**Contract — write what must be true, and read the real API for how:**

- `bucket`: a member of `store.BUCKETS`, or `None` meaning "unchanged, or decided by the group being joined". Anything else raises `ValueError`.
- `status`: `"open"` or `"in-progress"`, or `None` meaning unchanged. `"done"` raises `ValueError` — completion is `complete_task`'s job.
- `group`: the group name these tasks end up in, or `None` meaning loose. Always explicit; a drop always lands either inside a group container or outside every one. Passed through `_clean` when not `None`.
- `ordered_ids`: the destination bucket's full ordered id list, or `None` meaning "land at the end".

**Rules, in this order:**

1. Validate `bucket` and `status` before touching anything.
2. Capture the source buckets of the moving tasks **before** anything moves — that set is what the final renumber repairs.
3. Resolve the target bucket: the explicit `bucket` if given; else the bucket of the lowest-order *settled* member of `group` (a member that is not itself moving); else unchanged (`moving[0].bucket`). **An explicit bucket wins over the group's** — that is what lets a group-header drag move every member into a new bucket, while a task joining a group is pulled into the group's bucket instead of keeping its own.
4. Compute the tail to land on: one past the highest `order` among the group's settled members if there are any, else one past the highest `order` in the target bucket excluding the movers.
5. Write each task **once**. Iterate the movers sorted by `(order, id)` so a group keeps its internal order, setting `group`, `bucket` and `tail + offset`, then persist through `store.start_task` / `store.reset_to_open` when the status actually changes, and `store.save_task` when it does not.
6. **Only write status when it differs.** `reset_to_open` clears `started`; applying `"open"` to an already-open task would erase a date a restored task legitimately holds.
7. `store.reorder_bucket(project_path, target, ordered_ids)` when `ordered_ids` is given.
8. `renumber` every bucket in the touched set, target included.

- [ ] **Step 1: Write the failing tests**

Append at the end of `tests/test_groups.py`. These use the file's existing `seed_bucket`, `orders` and `by_id` helpers.

```python
def test_place_moves_a_loose_task_to_another_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "someday")

    groups.place(tmp_path, [task.id], bucket="now")

    assert by_id(tmp_path)[task.id].bucket == "now"


def test_place_renumbers_the_bucket_it_left(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["A", "B", "C"], "now")

    groups.place(tmp_path, [second.id], bucket="next")

    # The hole B left behind is closed; C does not keep order 2.
    assert orders(tmp_path)[first.id] == 0
    assert orders(tmp_path)[third.id] == 1
    assert orders(tmp_path)[second.id] == 0


def test_place_pulls_a_joining_task_into_its_new_groups_bucket(tmp_path):
    here, = seed_bucket(tmp_path, ["In now"], "now")
    groups.assign(tmp_path, [here.id], "G")
    elsewhere, = seed_bucket(tmp_path, ["In someday"], "someday")

    groups.place(tmp_path, [elsewhere.id], group="G")

    assert by_id(tmp_path)[elsewhere.id].bucket == "now"
    assert by_id(tmp_path)[elsewhere.id].group == "G"


def test_an_explicit_bucket_beats_the_groups_own(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [one.id, two.id], group="G", bucket="someday")

    assert {t.bucket for t in store.list_tasks(tmp_path)} == {"someday"}


def test_place_keeps_a_moved_group_contiguous(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    stranger, = seed_bucket(tmp_path, ["Stranger"], "someday")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [one.id, two.id], group="G", bucket="someday")

    landed = orders(tmp_path)
    assert landed[stranger.id] == 0
    assert sorted([landed[one.id], landed[two.id]]) == [1, 2]


def test_place_takes_a_task_out_of_its_group(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [two.id], group=None, bucket="now")

    assert by_id(tmp_path)[two.id].group is None
    assert by_id(tmp_path)[one.id].group == "G"


def test_place_claims_a_task_as_in_progress(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "next")

    groups.place(tmp_path, [task.id], status="in-progress")

    landed = by_id(tmp_path)[task.id]
    assert landed.status == "in-progress"
    assert landed.started == store._today()
    # The bucket is untouched the whole time a task is in progress, so it
    # lands back where it came from when the session turns out not to be real.
    assert landed.bucket == "next"


def test_place_releases_an_in_progress_task_into_a_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "now")
    store.start_task(task)

    groups.place(tmp_path, [task.id], bucket="someday", status="open")

    landed = by_id(tmp_path)[task.id]
    assert landed.status == "open"
    assert landed.started is None
    assert landed.bucket == "someday"


def test_place_leaves_started_alone_when_the_status_does_not_change(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "now")
    task.started = "2020-01-01"
    store.save_task(task)

    groups.place(tmp_path, [task.id], bucket="next", status="open")

    # Already open — reset_to_open would have cleared a date this task holds.
    assert by_id(tmp_path)[task.id].started == "2020-01-01"


def test_place_applies_an_explicit_position(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["A", "B", "C"], "now")

    groups.place(tmp_path, [third.id], bucket="now",
                 ordered_ids=[third.id, first.id, second.id])

    assert orders(tmp_path) == {third.id: 0, first.id: 1, second.id: 2}


def test_place_refuses_an_unknown_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"])

    with pytest.raises(ValueError):
        groups.place(tmp_path, [task.id], bucket="urgent")


def test_place_refuses_done_as_a_status(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"])

    with pytest.raises(ValueError):
        groups.place(tmp_path, [task.id], status="done")
```

`tests/test_groups.py` already imports `groups` and `store`; confirm `pytest` is imported at the top (it is, line 1) before relying on `pytest.raises`.

- [ ] **Step 2: Run to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_groups.py -q -k place`
Expected: FAIL — `AttributeError: module 'groups' has no attribute 'place'`.

- [ ] **Step 3: Implement `place` in `groups.py`**

Add it after `remove`, at the end of the file. Follow the eight rules above. The docstring should carry the two rules a reader cannot infer: an explicit bucket beats the group's, and status is written only when it differs.

- [ ] **Step 4: Run to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_groups.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 327 passed.

- [ ] **Step 6: Commit**

```bash
git add groups.py tests/test_groups.py
git commit -m "feat: groups.place applies a drop's whole destination at once"
```

---

### Task 3: The two bridge methods

**Files:**
- Modify: `app.py` (add after `set_group_bucket`, which ends at line 363)
- Test: `tests/test_app.py` (append at end of file)

**Interfaces:**
- Consumes: `groups.place` (Task 2), `app._project`, `app._text`, `store.list_tasks`.
- Produces:
  - `Api.place_task(project_name, task_id, destination, ordered_ids=None) -> None`
  - `Api.place_group(project_name, name, destination, ordered_ids=None) -> None`
  - `destination` is a dict with any of the keys `bucket`, `group`, `status`. A missing key means `None` — unchanged.

**Contract:**

- Refuse a `destination` that is not a dict, and refuse any key outside `{"bucket", "group", "status"}` — a typo'd key would otherwise be silently ignored and the drop would half-apply. This follows `_text`'s precedent (invariant 23: the bridge refuses what a hand-edited file would have repaired, because here a bad value means the JS caller is broken).
- Each present value must be a string or `None`; run non-`None` values through `_text`.
- `place_group` resolves the group's members **by name, from disk**, so the frontend never sends a member list that could be stale. An unknown group raises.
- Domain validation (bucket in `BUCKETS`, status in the two legal ones) is `groups.place`'s job — do not duplicate it here.

- [ ] **Step 1: Write the failing tests**

Append at the end of `tests/test_app.py`. The file's `isolated_config` fixture is `autouse`, and `make_repo` is defined at the top.

```python
def test_place_task_moves_it_between_buckets(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG", "someday")

    app.Api().place_task("repo", task.id, {"bucket": "now"})

    assert store.list_tasks(repo)[0].bucket == "now"


def test_place_task_claims_a_task_as_in_progress(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    app.Api().place_task("repo", task.id, {"status": "in-progress"})

    assert store.list_tasks(repo)[0].status == "in-progress"


def test_place_task_rejects_an_unknown_destination_key(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().place_task("repo", task.id, {"bucketed": "now"})

    assert store.list_tasks(repo)[0].bucket == "now"


def test_place_task_rejects_a_destination_that_is_not_a_dict(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().place_task("repo", task.id, "now")


def test_place_task_rejects_an_unknown_bucket(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().place_task("repo", task.id, {"bucket": "urgent"})


def test_place_group_moves_every_member(tmp_path):
    repo = make_repo(tmp_path)
    one = store.create_task(repo, "One", "body", "BUG")
    two = store.create_task(repo, "Two", "body", "BUG")
    groups.assign(repo, [one.id, two.id], "G")

    app.Api().place_group("repo", "G", {"bucket": "someday"})

    assert {t.bucket for t in store.list_tasks(repo)} == {"someday"}


def test_place_group_claims_every_member(tmp_path):
    repo = make_repo(tmp_path)
    one = store.create_task(repo, "One", "body", "BUG")
    two = store.create_task(repo, "Two", "body", "BUG")
    groups.assign(repo, [one.id, two.id], "G")

    app.Api().place_group("repo", "G", {"status": "in-progress"})

    assert {t.status for t in store.list_tasks(repo)} == {"in-progress"}


def test_place_group_rejects_an_unknown_group(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().place_group("repo", "Nope", {"bucket": "now"})
```

- [ ] **Step 2: Run to verify they fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q -k place`
Expected: FAIL — `AttributeError: 'Api' object has no attribute 'place_task'`.

- [ ] **Step 3: Implement**

Add both methods after `set_group_bucket` in `app.py`, plus a small module-level helper beside `_text` that validates a destination dict and returns the three values. Keep `app.py` wiring-only: no placement logic here.

- [ ] **Step 4: Run to verify they pass**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py -q`
Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 335 passed.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: place_task and place_group bridge methods"
```

---

### Task 4: One drag controller instead of six

A behaviour-preserving refactor. Cross-section drops are **not** enabled here — this task only moves the wiring, so that the next task changes one thing at a time.

**Files:**
- Modify: `ui/groups.js:445-565` (`wireDrag`), and `ui/groups.js:390-440` (`dropIntent`)
- Modify: `ui/tasks.js:169-179` (`bucketSection`)
- Modify: `ui/inprogress.js:64` (the `wireDrag` call)

**Interfaces:**
- Produces: `wireDrag()` takes no arguments and binds once to `#task-list`. It must be called at the bottom of `ui/groups.js` at load, alongside the file's other top-level statements — not from a render function, which would stack a duplicate listener on every redraw.
- Produces: `bucketSection` sets `section.dataset.project = currentProject`.

**Contract:**

- `#task-list` is the common ancestor of every section and is never itself replaced — `render()` calls `replaceChildren` on it — so one listener there survives every redraw.
- The destination section is resolved at event time: `event.target.closest('section[data-bucket], #in-progress')`. No section ancestor means no drop; return early rather than assuming.
- `allowReorder` stops being a closure constant and becomes a property of the destination section: a section with a `data-bucket` can reorder, `#in-progress` cannot. Keep the existing reasoning — the IN PROGRESS list is ordered by project then group and its rows can sit in three different buckets, so there is no single bucket for `reorder_bucket` to renumber.
- The `drop` handler's final `reorder_bucket` currently reads `section.querySelectorAll('.task')` off the closure's section. It must now read the **destination** section's rows and pass the **destination** section's bucket.
- The search and all-projects views set `row.draggable = false` and render no sections, so a listener at this level is inert there. Do not add a guard for them; verify by reading `renderSearch`/`renderAllProjects`.
- Every existing gesture must still work: reorder within a bucket, pair two loose rows into a new group, join a group by its header or by dropping inside it, sort within a group, and drop on a heading to leave a group.

- [ ] **Step 1: Rewrite `wireDrag` to bind once to `#task-list`**

Change the signature to `wireDrag()`, resolve `#task-list` inside it, and thread the destination section through `dropIntent` instead of the `bucket`/`allowReorder` closure variables.

- [ ] **Step 2: Remove the per-section calls**

Delete `wireDrag(section, bucket)` from `bucketSection` (`ui/tasks.js`) and `wireDrag(section, null)` from `inProgressSection` (`ui/inprogress.js`). Update the comments that explain why each section wired its own — they now describe something that is not there.

- [ ] **Step 3: Stamp the project on each bucket section**

In `bucketSection`, set `section.dataset.project = currentProject`. This is what makes the project check one uniform comparison against the destination instead of a special case per section (invariant 6).

- [ ] **Step 4: Call it once at load**

Add the `wireDrag()` call at the bottom of `ui/groups.js`.

- [ ] **Step 5: Syntax-check**

Run: `node --check ui/groups.js; node --check ui/tasks.js; node --check ui/inprogress.js`
Expected: no output. There is no JS test runner in this repo — this is the only automated check available for these files, and it catches exactly one class of error. It is not a substitute for the by-hand checks in Task 7.

- [ ] **Step 6: Run the Python suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 335 passed. `tests/test_conventions.py` reads `ui/index.html` and the vendored assets; nothing here should move it, and a failure means a script tag or asset was disturbed.

- [ ] **Step 7: Commit**

```bash
git add ui/groups.js ui/tasks.js ui/inprogress.js
git commit -m "refactor: one drag controller on #task-list, not one per section"
```

---

### Task 5: Cross-section destinations

**Files:**
- Modify: `ui/groups.js` — `dropIntent`, `leaveIntent`, and the `drop` handler

**Interfaces:**
- Consumes: `callApi('place_task', project, id, destination, orderedIds)` and `callApi('place_group', project, name, destination, orderedIds)` from Task 3.
- Consumes: `forgetFoldIfEmptied(project, name, leaving)` — already in this file — which must still run **before** the refresh, while `state.tasks` still counts the departing member.

**Contract — the destination table from the spec:**

| Target | Destination | Position |
|---|---|---|
| A bucket's `<h2>` | `{bucket: that section's, group: null, status: 'open'}` | end |
| Top-level row edge in a bucket section | same | from the DOM |
| Middle of a loose top-level row, same section, both loose | **pair** — unchanged `create_group` gesture | — |
| A `.group-header` | `{group: its name, status: the destination section's}` | end |
| Inside a group's container | same as its header; or **sort** when already a member of that same group in that same section | — |
| `#in-progress > h2` | `{group: null, status: 'in-progress'}` | end |
| A `.project-heading` in IN PROGRESS | same, project must match | end |

- A destination section that is a bucket implies `status: 'open'`; `#in-progress` implies `status: 'in-progress'`. That is what makes dragging out of IN PROGRESS release the task, and dragging in claim it, without either being a special case.
- `bucket` is `null` for any drop into IN PROGRESS and for any drop onto a group header — in the first case the task keeps its bucket, in the second the group decides (`groups.place` rule 3).
- **A drop that changes nothing gets no affordance.** "Already a member" now means same group *and* same status, so a `now` member of group G can be dropped on G's header inside IN PROGRESS — that claims it — while dropping it on G's header in its own section stays a no-op.
- **Cross-project drops stay refused.** Compare the dragged row's `dataset.project` against the destination's — a bucket section now carries `dataset.project` (Task 4), a `.project-heading`'s is on its parent `.project-block`, and a group header's is on its `.group` container. `#in-progress > h2` accepts any project, because that section spans all of them.
- The two affordance classes keep their meanings and no third is added: `drop-into` (solid) is *becomes part of something*, which now includes being claimed into IN PROGRESS; `drop-loose` (dashed) is *leaves something*, which now includes being released back into a bucket.
- Positional drops read the destination section's `.task` ids back from the DOM after the live `insertBefore`. `insertBefore` already works across sections — the frontend gets cross-section precision for free. Heading drops pass no `ordered_ids` and land at the end.
- Folded rows stay in the DOM (invariant 18), so the id list a fold is inside still has no hole in it.

- [ ] **Step 1: Resolve a destination in `dropIntent`**

Rework `dropIntent` and `leaveIntent` to return a destination rather than a section-local intent kind. `pair` and `sort` stay as their own kinds — the first names a new group, the second is a permutation within one group — everything else collapses into one `place` kind carrying `{bucket, group, status}`.

- [ ] **Step 2: Make the bucket heading a target for a loose task**

`leaveIntent` currently returns `null` when the dragged row has no group, so dropping a loose task on a heading does nothing. It must now resolve to that section's bucket. This is also the only way into an **empty** bucket — there are no rows there to aim at.

- [ ] **Step 3: Collapse the drop handler's branches**

`join`, `leave` and `move` all become one `place_task` call. `pair` keeps its `create_group` call and its `focusGroupName` follow-up (only on birth — invariant 11). `sort` keeps `reorder_group`. A group-header drag calls `place_group`.

- [ ] **Step 4: Keep the fold bookkeeping**

A task leaving a group can empty it. `forgetFoldIfEmptied(project, wasInGroup)` must still run before `refresh()`, exactly as it does today, on every path where the dragged row had a group and no longer does.

- [ ] **Step 5: Syntax-check**

Run: `node --check ui/groups.js`
Expected: no output.

- [ ] **Step 6: Run the Python suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 335 passed.

- [ ] **Step 7: Commit**

```bash
git add ui/groups.js
git commit -m "feat: a drop resolves to a destination, across any section"
```

---

### Task 6: The empty IN PROGRESS section, and draggable running groups

**Files:**
- Modify: `ui/inprogress.js:22-66` (`inProgressSection`), `ui/inprogress.js:52-56` (the `groupBlock` options)
- Modify: `ui/tasks.js:358-359` (the `render()` branch that conditionally includes the section)
- Modify: `ui/style.css`

**Contract:**

- `inProgressSection()` stops returning `null` when nothing is running. Empty, it renders its heading (`IN PROGRESS · 0 GROUPS`) and one explained line: **"Nothing running. Drag a task here to claim it, or hit Spin up."** A blank strip reads as a broken render; an unexplained empty box is worse than the space it costs.
- `render()` stops branching on `running` and always includes the section. It is built only in the `else` branch, so search and all-projects are unaffected.
- The section's own `<h2>` is a drop target in its own right, not only the project headings — with nothing running there are no project headings, and the first task must still have somewhere to land.
- `groupBlock`'s `headerDraggable: false` becomes `true` in this section. The comment saying the header is not draggable "since there is nothing to reorder" is now wrong: there is something to do — move the group to a bucket, releasing every member. Rewrite it rather than deleting it.
- A header reading `2 of 5` moves **all five**: `place_group` resolves members by name, and invariant 16 forbids leaving three behind in another bucket. This deliberately differs from the `done` button beside it, which acts on the two it drew. Say so in a comment where the two sit together.
- CSS: `.drop-into` currently matches only `.task` and `.group-header`; extend it to `h2` and `.project-heading` so claiming into IN PROGRESS shows the solid outline. `.drop-loose` already matches `h2` and `.project-heading`.
- CSS: `.group-header[draggable="false"] { cursor: default; }` stops applying to running headers, which now get the grab cursor. That is correct — verify no other rule assumed they were static.

- [ ] **Step 1: Always render the section, with the empty line**

- [ ] **Step 2: Make the section heading a drop target** (the `dropIntent` half of this is Task 5; this step is only whatever markup or dataset it needs)

- [ ] **Step 3: Make running group headers draggable**

- [ ] **Step 4: Extend the affordance CSS**

- [ ] **Step 5: Syntax-check**

Run: `node --check ui/inprogress.js; node --check ui/tasks.js; node --check ui/groups.js`
Expected: no output.

- [ ] **Step 6: Run the Python suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: 335 passed.

- [ ] **Step 7: Commit**

```bash
git add ui/inprogress.js ui/tasks.js ui/style.css
git commit -m "feat: IN PROGRESS is always a drop target, and its groups drag"
```

---

### Task 7: Documentation, and the checks the user has to run

**Files:**
- Modify: `CLAUDE.md` — the architecture table, the invariants, the by-hand check list

**Contract:**

- The `groups.py` row gains `place`; the `store.py` row gains `start_task`; the `ui/groups.js` row says `wireDrag` is one delegated controller.
- A new invariant: **a drop resolves to one destination, applied by one call.** The failure it prevents is the silent one — a frontend that sequences status, then bucket, then group, then two reorders can leave a file half-moved when any step raises, and can break invariant 16 between two of them.
- Record that `wireDrag` binds once at load to `#task-list`, and why: a per-section controller closes over its own `dragged`, which is why every cross-section drop was a no-op.
- Add to Known gaps: IN PROGRESS still never reorders, and two groups still never merge.
- **The by-hand checks are handed to the user when this lands — not written into the plan as though they were performed.** A UI task cannot be signed off from its diff; that cost a Critical on 2026-07-26. The list to hand over:
  1. Drag a loose task from `someday` onto a group inside `now` — it joins and moves to `now`.
  2. Drag it back out onto the `SOMEDAY` heading — it leaves the group and lands in `someday`.
  3. Drag a task into IN PROGRESS — it turns in-progress and no Claude window opens.
  4. Drag it from IN PROGRESS onto `NEXT` — it resets and lands in `next`.
  5. With nothing running, the IN PROGRESS box shows its line and still accepts a drop.
  6. Drag a group header between buckets — every member moves; `git status` in a tracked project shows frontmatter changes and **no body diff**.
  7. Drag a running group back to a bucket — every member resets, including any that were not running.
  8. Fold a group, then drag a task into it — the folded members keep their order.
  9. Drop a row on another project's heading in IN PROGRESS — refused, no outline.
  10. Reorder within one bucket, pair two rows into a new group, and rename it — all unchanged from before.

- [ ] **Step 1: Update the architecture table and invariants**
- [ ] **Step 2: Update Known gaps**
- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: the destination a drop resolves to"
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: the destination model and `groups.place` → Task 2; `store.start_task` and the `launcher` dedup → Task 1; the two bridge methods → Task 3; one controller instead of six → Task 4; the drop-target table, the two affordances, cross-project refusal → Task 5; the empty section and draggable running groups → Task 6; docs and the hand-over checks → Task 7.

**Type consistency.** `groups.place(project_path, task_ids, *, bucket, group, status, ordered_ids)` is used with those exact keyword names in Tasks 2 and 3. `Api.place_task(project_name, task_id, destination, ordered_ids)` and `Api.place_group(project_name, name, destination, ordered_ids)` are called with that shape from Task 5. `store.start_task(task) -> Task` is consumed by Task 2's rule 5 and Task 1's launcher change.

**Test counts.** 312 baseline, +3 (Task 1) = 315, +12 (Task 2) = 327, +8 (Task 3) = 335. If a count comes out different, the tests are what to trust — update the plan's number rather than inventing a test to hit it.

**Known plan risk.** The test snippets' arithmetic — particularly `test_place_renumbers_the_bucket_it_left` and `test_place_keeps_a_moved_group_contiguous` — was reasoned about against `groups.renumber`'s documented behaviour, not executed. A failure there is more likely a wrong constant in this plan than a wrong implementation. Check before changing code.
