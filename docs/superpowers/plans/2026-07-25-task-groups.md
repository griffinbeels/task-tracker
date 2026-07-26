# Task Groups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a *group* of tasks the unit this app counts, displays and hands to one Claude session — and make in-progress work visible and reversible.

**Architecture:** One nullable `group` string in each task's frontmatter is the entire data model; a group *is* its name, so there is no id, no registry file, and nothing that can dangle. A new `groups.py` owns every membership operation and the bucket renumber that keeps members contiguous. The frontend derives group blocks from the `group` field on tasks it already receives — no group entity crosses the bridge.

**Tech Stack:** Python 3.12, pywebview, pyyaml, pytest. Plain `<script>` files, no bundler, no framework, no JS test runner.

Spec: `docs/superpowers/specs/2026-07-25-task-groups-design.md`. Read it before Task 1 — this plan implements it and does not restate its reasoning.

## Global Constraints

- **Run tests with** `& ".venv\Scripts\python.exe" -m pytest tests/ -q` from `C:\Users\griff\Desktop\code\task_tracker`. PowerShell, not Bash — the Bash tool cannot resolve `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`; chain with `;`.
- **Never run `app.py`.** It opens a window and writes to the user's real `~/.task-tracker/`. Every frontend step in this plan is verified by the coordinator running the app by hand, never by an implementer.
- **Every `Path.write_text` passes `newline="\n"`.** `tests/test_conventions.py` globs `*.py` and fails the build otherwise.
- **Frontend bridge calls go through `callApi('name', ...)`**, and results are compared against `API_FAILED`, never `null`. A convention test globs `ui/*.js` and enforces the second half.
- **User-authored text never reaches `innerHTML`.** Task titles, type names and *group names* are unvalidated strings from hand-editable files. Build elements, set `.textContent`.
- **Task bodies are verbatim.** Nothing in this feature may alter `launcher.build_prompt` or what it emits.
- **Dependencies stay exactly** `pywebview`, `pyperclip`, `pyyaml`, `pytest`. No new packages.
- **Assume the constants in this plan may be wrong.** Expected values in tests were reasoned about, not executed. If an assertion disagrees with working code, say so and check the real behaviour — do not bend the implementation to satisfy a number written here.
- **This plan was written against `c4e3f09`.** The suite was 122 tests at that commit. Another session has been committing to this repo in parallel; re-read any file before modifying it rather than trusting a line number quoted here.

---

### Task 1: The `group` field, and `reset_to_open`

**Files:**
- Modify: `store.py` — `Task` dataclass, `render_task`, `parse_task`, and a new `reset_to_open` beside `complete_task`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `store.Task.group: str | None` (default `None`); `store.reset_to_open(task: Task) -> Task`.

`group` must be declared **after** `body` and **before** `path`, because it carries a default and `body` does not. `render_task` emits it between `bucket` and `status`. `parse_task` reads it with `.get`, mapping a missing key, `null`, and `""` all to `None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
def test_group_round_trips_through_frontmatter(tmp_path):
    task = store.create_task(tmp_path, "Chips rewrite the row", "body", "BUG")
    task.group = "Editor polish"
    store.save_task(task)

    assert store.list_tasks(tmp_path)[0].group == "Editor polish"


def test_a_task_file_with_no_group_key_parses_as_ungrouped(tmp_path):
    # Every task file written before this feature looks like this. None of
    # them may need a migration.
    text = (
        "---\n"
        "id: 1\n"
        "title: Older task\n"
        "type: BUG\n"
        "bucket: now\n"
        "status: open\n"
        "order: 0\n"
        "created: 2026-07-01\n"
        "started: null\n"
        "done: null\n"
        "---\n\n"
        "body\n"
    )

    assert store.parse_task(text).group is None


def test_an_ungrouped_task_writes_group_null(tmp_path):
    task = store.create_task(tmp_path, "Loose", "body", "BUG")

    assert "group: null" in task.path.read_text(encoding="utf-8")


def test_reset_to_open_clears_the_started_stamp(tmp_path):
    task = store.create_task(tmp_path, "Was handed off", "body", "BUG")
    task.status = "in-progress"
    task.started = "2026-07-20"
    store.save_task(task)

    store.reset_to_open(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_reset_to_open_refuses_a_completed_task(tmp_path):
    task = store.create_task(tmp_path, "Finished", "body", "BUG")
    store.complete_task(task)

    with pytest.raises(ValueError):
        store.reset_to_open(task)
```

`tests/test_store.py` may not import `pytest` yet — add the import if it is missing.

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q`
Expected: the three `group` tests fail on an unexpected keyword or a missing attribute; the two `reset_to_open` tests fail with `AttributeError: module 'store' has no attribute 'reset_to_open'`.

- [ ] **Step 3: Implement**

Three edits to `store.py`:

1. Add `group: str | None = None` to `Task`, positioned after `body` and before `path`.
2. In `render_task`'s `meta` dict, add `"group": task.group` between `"bucket"` and `"status"`.
3. In `parse_task`, add `group=str(meta["group"]) if meta.get("group") else None` to the `Task(...)` construction.

Then add `reset_to_open` directly below `complete_task`. It is the inverse of that function for a task that never actually started: set `status` to `"open"`, set `started` to `None`, save, return the task. Raise `ValueError` when the task's status is already `"done"` — undoing a completion needs a file move back out of `done/`, which this feature does not do.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass. Every pre-existing test constructs `Task` without `group`, which the default keeps valid; `tests/test_migrate.py` should stay green because `_sweep` parses, edits `type`, and saves, so the new field round-trips for free.

- [ ] **Step 5: Commit**

```
git add store.py tests/test_store.py
git commit -m "feat: give a task an optional group, and a way out of in-progress"
```

---

### Task 2: `groups.py` — the renumber, `unique_name`, `assign`, `create`, `remove`

**Files:**
- Create: `groups.py`
- Test: `tests/test_groups.py` (create)

**Interfaces:**
- Consumes: `store.Task.group`, `store.list_tasks`, `store.save_task`, `store.BUCKETS`.
- Produces:
  - `groups.unique_name(project_path, seed) -> str`
  - `groups.assign(project_path, task_ids, name) -> str` — join-or-create that exact name
  - `groups.create(project_path, task_ids, seed) -> str` — dedupe the seed, then assign; returns the name used
  - `groups.remove(project_path, task_ids) -> None`
  - `groups.renumber(project_path, bucket) -> None`

**Why `assign` and `create` are two functions:** dropping onto a *grouped* task means "join that exact group", and dropping onto a *loose* task means "make a new group, seeded from its title". If one function did both, a seed that happened to match an existing group name would silently drop the task into an unrelated group.

**The renumber, precisely.** Over the project's non-done tasks in one bucket: build one block per group name, keyed by its lowest member `order`, and one block per ungrouped task, keyed by its own `order`. Sort blocks by key, breaking ties on the lowest member `id`. Sort members within a block by `order`, ties on `id`. Flatten and assign `order` `0, 1, 2, …`. It is deterministic, idempotent, and repairs a hand-edited file rather than arguing with it.

**Landing at the end of a group.** Before renumbering, `assign` sets each newly-joining task's `order` above the group's current maximum, so the within-block sort puts newcomers last. A task already in the group keeps its position.

**Bucket.** Joining tasks take the group's bucket, read from its lowest-order existing member *before* the join. For a brand-new group, the bucket is that of the first task in `task_ids`. Renumber every bucket touched — the one joined and any a task left.

An unknown task id is a `ValueError` naming it. An empty or whitespace-only name is a `ValueError`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_groups.py`:

```python
import pytest

import groups
import store


def seed_bucket(repo, titles, bucket="now"):
    """One task per title, in order, all in one bucket."""
    return [store.create_task(repo, title, f"body of {title}", "BUG", bucket)
            for title in titles]


def orders(repo):
    """id -> order, for asserting the shape of a bucket in one line."""
    return {t.id: t.order for t in store.list_tasks(repo, include_done=False)}


def by_id(repo):
    return {t.id: t for t in store.list_tasks(repo, include_done=False)}


def test_assign_creates_a_group_from_two_loose_tasks(tmp_path):
    first, second = seed_bucket(tmp_path, ["Drops the title", "Rewrites the row"])

    name = groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    assert name == "Editor polish"
    assert {t.group for t in store.list_tasks(tmp_path)} == {"Editor polish"}


def test_assign_puts_a_joining_task_at_the_end_of_the_group(tmp_path):
    one, two, three, four = seed_bucket(
        tmp_path, ["One", "Two", "Three", "Four"])
    groups.assign(tmp_path, [two.id, four.id], "G")

    groups.assign(tmp_path, [three.id], "G")

    # Blocks are One (order 0) then G. Within G, the two originals keep their
    # relative order and Three lands behind them.
    assert orders(tmp_path) == {one.id: 0, two.id: 1, four.id: 2, three.id: 3}


def test_assign_pulls_a_joining_task_into_the_groups_bucket(tmp_path):
    here, = seed_bucket(tmp_path, ["In now"], "now")
    elsewhere, = seed_bucket(tmp_path, ["In someday"], "someday")
    groups.assign(tmp_path, [here.id], "G")

    groups.assign(tmp_path, [elsewhere.id], "G")

    assert by_id(tmp_path)[elsewhere.id].bucket == "now"


def test_a_new_group_takes_the_bucket_of_its_first_task(tmp_path):
    first, = seed_bucket(tmp_path, ["In someday"], "someday")
    second, = seed_bucket(tmp_path, ["In now"], "now")

    groups.assign(tmp_path, [first.id, second.id], "G")

    assert {t.bucket for t in store.list_tasks(tmp_path)} == {"someday"}


def test_the_renumber_makes_group_members_contiguous(tmp_path):
    one, two, three, four = seed_bucket(tmp_path, ["One", "Two", "Three", "Four"])
    # Interleave by hand, the way a hand-edited file could.
    for task, group in ((two, "G"), (four, "G")):
        task.group = group
        store.save_task(task)

    groups.renumber(tmp_path, "now")

    assert orders(tmp_path) == {one.id: 0, two.id: 1, four.id: 2, three.id: 3}


def test_the_renumber_is_idempotent(tmp_path):
    seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.renumber(tmp_path, "now")
    once = orders(tmp_path)

    groups.renumber(tmp_path, "now")

    assert orders(tmp_path) == once


def test_unique_name_leaves_a_free_name_alone(tmp_path):
    seed_bucket(tmp_path, ["One"])

    assert groups.unique_name(tmp_path, "Editor polish") == "Editor polish"


def test_unique_name_dedupes_case_insensitively(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id], "Editor polish")

    assert groups.unique_name(tmp_path, "editor POLISH") == "editor POLISH 2"


def test_unique_name_refuses_an_empty_seed(tmp_path):
    with pytest.raises(ValueError):
        groups.unique_name(tmp_path, "   ")


def test_create_never_joins_an_existing_group_with_the_same_seed(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id], "Editor polish")

    name = groups.create(tmp_path, [second.id, third.id], "Editor polish")

    assert name == "Editor polish 2"
    assert by_id(tmp_path)[first.id].group == "Editor polish"


def test_remove_clears_the_group_on_exactly_those_tasks(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id, second.id], "G")

    groups.remove(tmp_path, [second.id])

    tasks = by_id(tmp_path)
    assert tasks[first.id].group == "G"
    assert tasks[second.id].group is None


def test_an_unknown_task_id_is_rejected_by_name(tmp_path):
    with pytest.raises(ValueError) as caught:
        groups.assign(tmp_path, [999], "G")

    assert "999" in str(caught.value)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_groups.py -q`
Expected: collection fails with `ModuleNotFoundError: No module named 'groups'`.

- [ ] **Step 3: Implement `groups.py`**

Module docstring: what a group is (a name shared by tasks in one project) and why there is no id.

Write the five public functions plus whatever private helpers they need, to the contracts above. Notes that will save a round trip:

- Comparison for `unique_name` and for "does this group exist" is `str.casefold()`, not `.lower()`.
- `unique_name` strips the seed, raises on empty, then appends `" 2"`, `" 3"`… until free.
- `assign` reads the group's existing members *before* mutating anything, so the bucket it copies is the pre-join one.
- Every write goes through `store.save_task`, which already passes `newline="\n"`.
- `renumber` reads with `include_done=False` — a completed task keeps its `group` string but is not part of the block (spec invariant 5).

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add groups.py tests/test_groups.py
git commit -m "feat: group membership, with a renumber that keeps members contiguous"
```

---

### Task 3: `rename`, `disband`, `set_bucket`

**Files:**
- Modify: `groups.py`
- Test: `tests/test_groups.py`

**Interfaces:**
- Consumes: everything from Task 2.
- Produces:
  - `groups.rename(project_path, old, new) -> str`
  - `groups.disband(project_path, name) -> None`
  - `groups.set_bucket(project_path, name, bucket) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_groups.py`:

```python
def test_rename_rewrites_every_member(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    groups.rename(tmp_path, "Editor polish", "Editor overhaul")

    assert {t.group for t in store.list_tasks(tmp_path)} == {"Editor overhaul"}


def test_rename_refuses_to_collide_with_another_group(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id], "Editor polish")
    groups.assign(tmp_path, [second.id], "Drag fixes")

    with pytest.raises(ValueError):
        groups.rename(tmp_path, "Drag fixes", "editor polish")

    assert by_id(tmp_path)[second.id].group == "Drag fixes"


def test_rename_allows_changing_only_the_case_of_its_own_name(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "editor polish")

    groups.rename(tmp_path, "editor polish", "Editor Polish")

    assert by_id(tmp_path)[first.id].group == "Editor Polish"


def test_rename_refuses_an_empty_name(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "G")

    with pytest.raises(ValueError):
        groups.rename(tmp_path, "G", "   ")


def test_rename_refuses_a_group_with_no_members(tmp_path):
    with pytest.raises(ValueError):
        groups.rename(tmp_path, "Never existed", "Something")


def test_disband_clears_the_field_and_leaves_the_order_alone(tmp_path):
    one, two, three = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [one.id, two.id], "G")
    before = orders(tmp_path)

    groups.disband(tmp_path, "G")

    assert all(t.group is None for t in store.list_tasks(tmp_path))
    assert orders(tmp_path) == before


def test_set_bucket_moves_every_member_to_the_end_of_the_target(tmp_path):
    resident, = seed_bucket(tmp_path, ["Already in next"], "next")
    first, second = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [first.id, second.id], "G")

    groups.set_bucket(tmp_path, "G", "next")

    tasks = by_id(tmp_path)
    assert {tasks[first.id].bucket, tasks[second.id].bucket} == {"next"}
    assert orders(tmp_path) == {resident.id: 0, first.id: 1, second.id: 2}


def test_set_bucket_rejects_an_unknown_bucket(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "G")

    with pytest.raises(ValueError):
        groups.set_bucket(tmp_path, "G", "urgent")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_groups.py -q`
Expected: eight failures, each `AttributeError` on the missing function.

- [ ] **Step 3: Implement**

- `rename` validates in this order: `old` has at least one member, `new` is non-empty after stripping, and `new` does not casefold-match a *different* existing group. Then rewrite every member. Membership does not change, so no renumber is needed.
- `disband` clears `group` on every member. Members are already contiguous, so a renumber is a no-op — call it anyway rather than reasoning about when it is safe to skip.
- `set_bucket` validates against `store.BUCKETS`, sets every member's `bucket`, pushes their `order` above the target bucket's current maximum so they land at the end, then renumbers the old bucket and the new one.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add groups.py tests/test_groups.py
git commit -m "feat: rename, disband and move a group"
```

---

### Task 4: `auto_group` — the spin-up rule

**Files:**
- Modify: `groups.py`
- Test: `tests/test_groups.py`

**Interfaces:**
- Consumes: `groups.assign`, `groups.create`.
- Produces: `groups.auto_group(project_path, task_ids) -> str | None`.

The four cases, from the spec. `task_ids` arrives in list order — the topmost ticked row first — and case two names the group after the **first** one's title.

| Selection | Result |
|---|---|
| 0 or 1 task | `None`, nothing written |
| 2+, none already grouped | `create(...)` seeded from the first task's title |
| 2+, spanning exactly one group | the ungrouped ones `assign` into it; returns that name |
| 2+, spanning two or more groups | `None`, nothing written |

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_groups.py`:

```python
def test_auto_group_leaves_a_single_task_alone(tmp_path):
    only, = seed_bucket(tmp_path, ["One"])

    assert groups.auto_group(tmp_path, [only.id]) is None
    assert by_id(tmp_path)[only.id].group is None


def test_auto_group_names_a_new_group_after_the_first_task(tmp_path):
    first, second = seed_bucket(tmp_path, ["Drops the title", "Rewrites the row"])

    name = groups.auto_group(tmp_path, [first.id, second.id])

    assert name == "Drops the title"
    assert {t.group for t in store.list_tasks(tmp_path)} == {"Drops the title"}


def test_auto_group_never_touches_a_task_outside_the_selection(tmp_path):
    first, second, bystander = seed_bucket(tmp_path, ["One", "Two", "Three"])

    groups.auto_group(tmp_path, [first.id, second.id])

    assert by_id(tmp_path)[bystander.id].group is None


def test_auto_group_folds_loose_tasks_into_the_one_group_present(tmp_path):
    first, second, loose = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    name = groups.auto_group(tmp_path, [first.id, loose.id])

    assert name == "Editor polish"
    assert by_id(tmp_path)[loose.id].group == "Editor polish"


def test_auto_group_refuses_to_merge_two_named_groups(tmp_path):
    first, second, loose = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id], "Editor polish")
    groups.assign(tmp_path, [second.id], "Drag fixes")

    assert groups.auto_group(tmp_path, [first.id, second.id, loose.id]) is None

    tasks = by_id(tmp_path)
    assert tasks[first.id].group == "Editor polish"
    assert tasks[second.id].group == "Drag fixes"
    assert tasks[loose.id].group is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_groups.py -q`
Expected: five failures on the missing `auto_group`.

- [ ] **Step 3: Implement**

Resolve the ids (raising on an unknown one, as the other functions do), then apply the table. The docstring must carry the *reason* for case four: silently merging two named groups destroys one of the names, and a name is the only identity a group has.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```
git add groups.py tests/test_groups.py
git commit -m "feat: handing several tasks to one session records them as a group"
```

---

### Task 5: `group_limit` replaces `wip_limit`

**Files:**
- Modify: `registry.py` — `Settings`, `load_settings`
- Modify: `app.py:176-183` — `Api.save_settings` reads `payload["group_limit"]`
- Test: `tests/test_registry.py` (two existing tests reference `wip_limit` and must be updated, not deleted)

**Interfaces:**
- Consumes: nothing.
- Produces: `registry.Settings.group_limit: int = 5`.

The UI half of this lands in Task 10. This task is the storage rename and its read-side fallback, so an existing `~/.task-tracker/settings.json` written before today keeps the user's number.

- [ ] **Step 1: Write the failing tests**

In `tests/test_registry.py`, change `test_settings_default_when_no_file_exists` to assert `settings.group_limit == 5` and `test_settings_round_trip` to set and re-read `group_limit`. Then append:

```python
def test_an_old_settings_file_carries_its_wip_limit_over(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"wip_limit": 3, "stale_days": 90, "types": []}),
        encoding="utf-8", newline="\n")

    assert registry.load_settings().group_limit == 3


def test_the_new_key_wins_over_the_old_one(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"group_limit": 7, "wip_limit": 3, "types": []}),
        encoding="utf-8", newline="\n")

    assert registry.load_settings().group_limit == 7


def test_saving_drops_the_old_key(tmp_path):
    registry.save_settings(registry.Settings(group_limit=4))

    raw = json.loads((registry.CONFIG_DIR / "settings.json").read_text(encoding="utf-8"))
    assert raw["group_limit"] == 4
    assert "wip_limit" not in raw
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_registry.py -q`
Expected: failures on `Settings` having no `group_limit`.

- [ ] **Step 3: Implement**

Rename the `Settings` field to `group_limit`. In `load_settings`, read `raw.get("group_limit", raw.get("wip_limit", defaults.group_limit))`. In `app.Api.save_settings`, read `payload["group_limit"]`. Nothing writes `wip_limit` any more, so it disappears from the file on the next save.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass. `tests/test_app.py` has a `save_settings` test — if it sends `wip_limit`, update its payload.

- [ ] **Step 5: Commit**

```
git add registry.py app.py tests/test_registry.py tests/test_app.py
git commit -m "feat: the limit is named for what it counts"
```

---

### Task 6: The bridge

**Files:**
- Modify: `app.py` — six new `Api` methods, and `hand_off`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: everything in `groups.py`, `store.reset_to_open`.
- Produces, on `Api`:
  - `group_tasks(project_name, task_ids, name) -> str`
  - `create_group(project_name, task_ids, seed) -> str`
  - `ungroup_tasks(project_name, task_ids) -> None`
  - `rename_group(project_name, old, new) -> str`
  - `disband_group(project_name, name) -> None`
  - `set_group_bucket(project_name, name, bucket) -> None`
  - `reset_to_open(project_name, task_ids) -> list[dict]`

Each translates JS args to a backend call and back — `app.py` is wiring only, and the spin-up rule already lives in `groups.py` so it can be tested without spawning a process.

**`hand_off` ordering is load-bearing.** `groups.auto_group` must run **after** `launcher.hand_off` returns, not before. `launcher.hand_off` writes `status` and `started` onto the `Task` objects it was handed; if `auto_group` had already rewritten those same files, those in-memory objects would be stale and saving them would silently discard the grouping. Running afterwards means `auto_group` re-reads from disk and there is nothing to clobber — and a spawn that fails leaves nothing grouped, which matches the existing guarantee that a failed spawn leaves tasks untouched.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_create_group_dedupes_the_seed(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    third = store.create_task(repo, "Three", "body", "BUG")
    app.Api().group_tasks("repo", [first.id], "Editor polish")

    name = app.Api().create_group("repo", [second.id, third.id], "Editor polish")

    assert name == "Editor polish 2"


def test_rename_group_reports_a_collision(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [first.id], "Editor polish")
    app.Api().group_tasks("repo", [second.id], "Drag fixes")

    with pytest.raises(ValueError):
        app.Api().rename_group("repo", "Drag fixes", "Editor polish")


def test_set_group_bucket_rejects_an_unknown_bucket(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "One", "body", "BUG")
    app.Api().group_tasks("repo", [task.id], "G")

    with pytest.raises(ValueError):
        app.Api().set_group_bucket("repo", "G", "urgent")


def test_reset_to_open_returns_the_updated_tasks(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "One", "body", "BUG")
    task.status = "in-progress"
    task.started = "2026-07-20"
    store.save_task(task)

    updated = app.Api().reset_to_open("repo", [task.id])

    assert updated[0]["status"] == "open"
    assert updated[0]["started"] is None
    assert updated[0]["project"] == "repo"
    assert "path" not in updated[0]
```

And in `tests/test_launcher.py`, a test that the prompt survives auto-grouping. It needs the `spawned` fixture already in that file, plus `app` and `registry` imports:

```python
def test_grouping_on_hand_off_does_not_change_what_is_typed(
        tmp_path, monkeypatch, spawned):
    import app
    import registry

    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    first = store.create_task(repo, "First", "body one", "BUG")
    second = store.create_task(repo, "Second", "body two", "FEATURE")

    prompt = app.Api().hand_off("repo", [first.id, second.id])

    assert prompt == "BUG: body one\nFEATURE: body two"
    assert {t.group for t in store.list_tasks(repo)} == {"First"}
    assert {t.status for t in store.list_tasks(repo)} == {"in-progress"}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py tests/test_launcher.py -q`
Expected: `AttributeError` on each missing `Api` method, and the launcher test failing on the group assertion.

- [ ] **Step 3: Implement**

Add the seven methods, following the shape of the existing ones: resolve the project with `_project`, coerce ids with `int(...)`, validate types the way `update_task` does, and run any returned `Task` through `_task_dict`. Then add the single `groups.auto_group(...)` call to `hand_off`, positioned after `launcher.hand_off` returns and before the prompt is returned.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass, including the pre-existing `test_hand_off_leaves_tasks_untouched_when_the_session_cannot_start`.

- [ ] **Step 5: Commit**

```
git add app.py tests/test_app.py tests/test_launcher.py
git commit -m "feat: expose group operations to the renderer"
```

---

### Task 7: Group blocks in the bucket sections

**Files:**
- Create: `ui/groups.js`
- Modify: `ui/index.html` — add `<script src="groups.js"></script>` after `tasks.js`
- Modify: `ui/tasks.js` — `taskRow` takes options; `bucketSection` renders blocks
- Modify: `ui/style.css` — the group container, rail and header

**Interfaces:**
- Consumes: `state`, `currentProject`, `callApi`, `API_FAILED`, `refresh`, `typeColor`, `taskRow`.
- Produces, in `ui/groups.js`:
  - `groupBlocks(tasks) -> [{ group: string|null, tasks: [...] }]` — ordered blocks, members sorted by `order`
  - `groupMemberCount(project, name) -> number` — non-done members, both statuses, for the `N of M` fraction
  - `groupBlock(block, options) -> HTMLElement` — a rendered group container
- And in `ui/tasks.js`: `taskRow(task, options = {})`, where options are `{ showBucket = true, showReset = false, draggable = true }`.

**No JS test runner.** Verification for this task is the manual check in Step 4, run by the coordinator. Implementers must not launch `app.py`.

- [ ] **Step 1: Give `taskRow` its options**

`ui/tasks.js` is 285 lines as of `c4e3f09` (the copy-as-prompt row button), which is why the group rendering goes in a new file rather than in there.

`taskRow(task, options = {})`. When `showBucket` is false, do not build the bucket `<select>` at all — note it is currently inserted with `row.querySelector('.copy').before(bucketPicker)`, so skipping construction also skips that insertion; do not leave a `.before()` call reaching for an element that may not be there. When `draggable` is false, set `row.draggable = false`. `showReset` is consumed in Task 9 — accept it now and ignore it, so Task 9 touches one file instead of two.

Leave the copy button on every row in every configuration. It takes `task.project` rather than `currentProject`, so it is already correct for the cross-project rows Task 9 introduces.

Callers change: `renderSearch` and `renderAllProjects` can pass `{ draggable: false }` instead of setting the property afterwards, but they must keep disabling `.select` and nulling `onclick` — the id-ambiguity guard is unrelated to this refactor and must not be lost.

- [ ] **Step 2: Write `groupBlocks` and `groupBlock` in `ui/groups.js`**

`groupBlocks` mirrors `groups.py`'s renumber, read-only: bucket the input by `group`, key each block by its lowest member `order` (ungrouped tasks are their own block), sort blocks by key with lowest member `id` breaking ties, sort members within a block the same way.

`groupBlock` builds a `<div class="group">` containing a header and one `taskRow` per member, each with `{ showBucket: false }` — the header owns the bucket. The header carries, in this order:

1. a select-all `<input type="checkbox" class="select-group">`
2. the group name, as a `<span class="group-name">` — **`.textContent`, never `innerHTML`**; group names are unvalidated strings from hand-editable files and this markup runs with full `window.pywebview.api` access
3. a count: `N` when every member is in the same status bucket as this block, `N of M` when `groupMemberCount` disagrees with the number of rows rendered here
4. the bucket `<select>`, which calls `set_group_bucket`
5. a `×` button that calls `disband_group`

Select-all sets every member row's checkbox to its own new state. Its own checked state is derived on render: checked only when every member is ticked.

Clicking the name replaces the span with an `<input>` holding the current name, focused, text selected. Enter or blur commits via `rename_group`; Escape reverts. An empty value reverts. On a rejected rename `callApi` already alerts, so the handler's job is only to keep the input focused with what was typed rather than reverting.

- [ ] **Step 3: Render blocks from `bucketSection`, and style them**

`bucketSection` currently appends a `taskRow` per task. It now appends `groupBlock(block)` for a block with a group and `taskRow(task)` for an ungrouped one — a loose task gets no container, because drawing one around a single row would claim a grouping that does not exist.

CSS to add (starting values — adjust by eye against the running app):

```css
.group { border-left: 2px solid rgba(127,127,127,.28); border-radius: 0 5px 5px 0;
         margin: 2px 0; }
.group > .task { margin-left: 14px; }
.group-header { display: flex; align-items: center; gap: 6px; padding: 4px 6px; }
.group-name { flex: 1; font-weight: 600; cursor: text; }
.group-name-input { flex: 1; font: inherit; font-weight: 600; }
.group-count { font-size: 10px; opacity: .45; }
.group-disband { opacity: 0; font-size: 10px; }
.group-header:hover .group-disband { opacity: .6; }
```

The 14px indent is the one level of indentation a parent/child relationship gets in this codebase. Do not nest further — groups are one level deep by design.

- [ ] **Step 4: Manual check (coordinator runs this, not an implementer)**

Run `run.bat`. In a project with three or more open tasks:

1. Every existing task still renders, in its old order, with its bucket dropdown.
2. Hand-edit one task file to add `group: Test group`, add the same to a second, and reopen. Both appear in one container with a left rail, indented one level, with the name and count in the header and **no** bucket dropdown on the child rows.
3. Tick the header checkbox — both rows tick. Untick one row — the header unticks.
4. Click the name, type a new one, press Enter, reopen the app: the new name persisted to both files.
5. Change the header's bucket — both rows move together.
6. Click `×` — both rows become loose and stay where they were.
7. Type a title in Capture, then click a different type chip: the title must not change. (Standing regression check whenever the editor's neighbours move.)

- [ ] **Step 5: Commit**

```
git add ui/groups.js ui/tasks.js ui/index.html ui/style.css
git commit -m "feat: render a group as one indented block with its own header"
```

---

### Task 8: The three-zone drag

**Files:**
- Modify: `ui/groups.js` — the drag engine
- Modify: `ui/tasks.js` — remove `wireDrag`, call the new one
- Modify: `ui/style.css` — the two drop affordances

**Interfaces:**
- Consumes: `groupBlock`, `callApi`, `refresh`.
- Produces: `wireDrag(section, bucket)` — same signature `bucketSection` already calls, new behaviour.

The zones, from the spec:

| Where the pointer is | Intent |
|---|---|
| top or bottom quarter of a **top-level** row | reorder |
| middle half of a top-level row | group with that row |
| anywhere over a group header, or between two of its child rows | join that group |
| a gap between top-level blocks, dragging from inside a group | leave the group |

The current implementation moves the dragged element live during `dragover` and reads DOM order on `drop`. That still works for reorder, and must **not** be used for the grouping zones: on a grouping drop the DOM has not moved the row next to its new group, so sending DOM order would write the old positions. The backend's renumber places it instead.

- [ ] **Step 1: Rewrite `wireDrag`**

On `dragover`, compute the intent, then show exactly one affordance: `.drop-into` on the target element for a grouping intent, or the live DOM move already in place for a reorder intent. Clear the affordance on `dragleave` and on `drop`.

On `drop`, by intent:

- **reorder, dragged row was ungrouped** → `reorder_bucket(currentProject, bucket, domIds)`, then `refresh()`.
- **reorder, dragged row was in a group** (dropped into a top-level gap) → `ungroup_tasks(currentProject, [id])`, then `reorder_bucket(...)` with the DOM ids, then `refresh()`. `reorder_bucket` runs last and wins, which is right: the DOM is what the user just saw.
- **group with a loose target** → `create_group(currentProject, [targetId, draggedId], targetTitle)`, then `refresh()`. Both ids, and the target first — the target's title is the seed and its position anchors the new block. Then focus the new group's name box with its text selected. Get the name from `create_group`'s return value, not from the seed you sent; it may have been deduped.
- **group with a target that is already in a group, or a drop on a group header** → `group_tasks(currentProject, [draggedId], targetGroupName)`, then `refresh()`. **Do not** focus the name box — the group already exists and its name is not a suggestion (spec: this is `CLAUDE.md` invariant 11 applied to a new field).

Guard the no-ops: dropping a row on itself, and dropping a row onto the group it is already in.

- [ ] **Step 2: Style the affordances**

```css
.task.drop-into, .group-header.drop-into {
  outline: 2px solid rgba(48,164,108,.75); outline-offset: -2px; border-radius: 5px; }
```

An outline rather than a background: the row already changes background on hover, and a second background change would read as the same state.

- [ ] **Step 3: Manual check (coordinator)**

Run `run.bat`, in a project with four or more open tasks in one bucket:

1. Drag one task onto the **middle** of another → a group forms containing both, and the name box is focused with the seeded text selected. Type a name, press Enter.
2. Reopen the app — the name and both members persisted.
3. Drag a third task onto the group's header → it joins, lands at the bottom of the group, and the name box does **not** re-open.
4. Drag a task onto the **top edge** of another → it reorders, no group forms.
5. Drag a child out of the group into a gap between two top-level rows → it leaves the group and lands where it was dropped.
6. Drag a task onto a group whose name would collide with an existing group's, by first making two groups seeded from same-titled tasks → the second gets ` 2` appended.
7. `git status` in a tracked project after any of the above → frontmatter changes only, **no body diff**.

- [ ] **Step 4: Commit**

```
git add ui/groups.js ui/tasks.js ui/style.css
git commit -m "feat: drop a task onto another to group them, drag it out to leave"
```

---

### Task 9: The IN PROGRESS section

**Files:**
- Create: `ui/inprogress.js`
- Modify: `ui/index.html` — `<script src="inprogress.js"></script>` after `groups.js`
- Modify: `ui/tasks.js` — `tasksFor` excludes in-progress; `render` prepends the section
- Modify: `ui/style.css`

**Interfaces:**
- Consumes: `state`, `currentProject`, `groupBlocks`, `taskRow`, `callApi`, `refresh`.
- Produces: `inProgressSection() -> HTMLElement | null` — `null` when nothing is in progress.

Structure: a section headed `IN PROGRESS · N GROUPS`, then one sub-heading per project that has in-progress tasks, then that project's blocks. In-progress tasks leave their bucket sections entirely, so nothing appears twice.

- [ ] **Step 1: Exclude in-progress tasks from the buckets**

`tasksFor` currently filters `t.status !== 'done'`. It becomes `t.status === 'open'`. This is the change that makes the section the only place in-progress work appears — without it every row renders twice.

- [ ] **Step 2: Build the section**

For each project with in-progress tasks, in `state.projects` order, emit a `<div class="project-heading">` with the project name as `.textContent`, then `groupBlocks` over that project's in-progress tasks. Grouped blocks render through `groupBlock`; ungrouped tasks render as bare rows.

Every row here is built with `{ showBucket: false, showReset: true, draggable: false }`. `showReset` adds a `↩` button, revealed on hover exactly as `.done` already is, that calls `reset_to_open(row.dataset.project, [row.dataset.id])` and refreshes. Reordering a running session means nothing, hence no drag.

Group headers in this section differ from the bucket-section ones: **no bucket dropdown and no `×`**, and the `↩` resets every member at once. Pass this through `groupBlock`'s `options` rather than forking the component — one component, two configurations, is what keeps the select-all and rename behaviour identical in both.

Row-click-to-edit stays disabled for rows whose `dataset.project` is not `currentProject`; resolving an id against the wrong project is the hazard `CLAUDE.md` invariant 6 exists for. Selection stays **enabled** for every row: `selectedIds()` already carries each row's own project and `spin-up` derives its target from the selection, rejecting only mixed-project ones.

The `N of M` count comes from `groupMemberCount` and is what stops the same group name appearing here and in a bucket below reading as a rendering fault.

- [ ] **Step 3: Prepend it in `render`, and style it**

In `render`, in the branch that builds bucket sections, put `inProgressSection()` before `BUCKETS.map(bucketSection)`, skipping it when it returns `null`. It is not rendered in the search or all-projects views.

```css
#in-progress { border: 1px solid rgba(48,164,108,.35); border-radius: 6px;
               padding: 2px 6px 6px; margin-bottom: 10px; }
#in-progress h2 { color: #4cc38a; opacity: .85; }
.project-heading { font-size: 10px; letter-spacing: .08em; opacity: .45;
                   margin: 8px 0 2px; }
.reset { opacity: 0; font-size: 10px; }
.task:hover .reset, .group-header:hover .reset { opacity: .6; }
```

- [ ] **Step 4: Manual check (coordinator)**

Run `run.bat`. You currently have ~13 tasks in progress across projects, which is the fixture.

1. The section appears above NOW, headed with a group count, split by project heading.
2. Every in-progress task is visible somewhere in it, and **none** of them still appears in `now`/`next`/`someday`.
3. `↩` on a single row → it leaves the section and reappears in the bucket it was in before hand-off, with `started: null` in its file.
4. `↩` on a group header → every member does the same.
5. Switch `currentProject` → both projects' in-progress work stays visible.
6. Tick a row from a project other than the current one and hit Spin up Claude → a session opens in **that** project.
7. Click a row from another project → nothing opens.

- [ ] **Step 5: Commit**

```
git add ui/inprogress.js ui/tasks.js ui/index.html ui/style.css
git commit -m "feat: show what is in progress, and let it stop being in progress"
```

---

### Task 10: The banner counts groups

**Files:**
- Modify: `ui/state.js:39-45` — `renderWipWarning`
- Modify: `ui/settings.js` — read and send `group_limit`
- Modify: `ui/index.html:63` — the settings input and its label
- Modify: `ui/style.css:25` — the `#wip-limit` selector

**Interfaces:**
- Consumes: `state.settings.group_limit` (Task 5), `state.tasks`.
- Produces: nothing new.

- [ ] **Step 1: Count groups, not tasks**

`renderWipWarning` counts **distinct `project + group` pairs** among in-progress tasks; an in-progress task with no group counts as one on its own. Build the key so an ungrouped task can never collide with a group name or with another project — `${project}\u0000${group ?? id}` or equivalent.

Banner text: `${count} groups in progress — over your limit of ${limit}`, with `limit` read from `state.settings.group_limit`. Keep `|| 5` as the fallback for a state object that predates the rename. Say `1 group` rather than `1 groups` when the count is one — the banner only shows above the limit, so this is reachable only with a limit of zero, but the check is one expression.

- [ ] **Step 2: Rename the setting in the UI**

`index.html`: the input id becomes `group-limit` and the label reads `Group limit`, with a hint element under it: *"Tasks handed to one Claude session count as one group."* The number is otherwise correct and unexplained, which reads as a bug.

`settings.js`: `document.getElementById('group-limit')` in both the open handler and the save payload, sending `group_limit`.

`style.css`: `#wip-limit, #stale-days` becomes `#group-limit, #stale-days`. Add a hint style:

```css
.setting-hint { font-size: 10px; opacity: .45; margin: -4px 0 4px 0; }
```

- [ ] **Step 3: Manual check (coordinator)**

1. With the ~13 in-progress tasks grouped into fewer groups by Task 9's work, the banner's number equals the number of group blocks visible in the IN PROGRESS section.
2. Group three in-progress tasks together → the number drops by two.
3. Open Settings → it reads **Group limit**, shows the value carried over from the old `wip_limit`, and explains itself. Change it, save, reopen: it persisted, and `~/.task-tracker/settings.json` has `group_limit` and no `wip_limit`.

- [ ] **Step 4: Commit**

```
git add ui/state.js ui/settings.js ui/index.html ui/style.css
git commit -m "feat: the banner counts Claude sessions, not tasks"
```

---

### Task 11: Update the working notes

**Files:**
- Modify: `CLAUDE.md` — the module table, the invariants, the manual-check list, known gaps
- Modify: `README.md` — the settings line at `README.md:81`

**Interfaces:**
- Consumes: the finished feature.
- Produces: documentation that matches the code.

This is not optional tidying. `CLAUDE.md` is loaded into every session in this repo; a stale invariant there is worse than no invariant.

- [ ] **Step 1: The module table**

Add `groups.py`, `ui/groups.js` and `ui/inprogress.js` with one-line ownership descriptions. Update the sentence that says "Nine small Python modules and five plain `<script>` files" and the paragraph naming the script load order — it is now `state`, `tasks`, `groups`, `inprogress`, `editor`, `triage`, `settings`.

- [ ] **Step 2: Reword invariant 6**

It currently reads that any view spanning projects must disable selection. That is now false — the IN PROGRESS section spans projects and allows selection. Rewrite it to what it has always protected: **never resolve a task id against `currentProject`; a row's project comes from its own `dataset.project`.** Note that search and the all-projects view still disable selection, because there a row's project is not visible in the layout, and that IN PROGRESS still disables row-click-to-edit for foreign rows.

- [ ] **Step 3: Add the group invariants**

Three new numbered invariants, each stating what breaks silently:

- A group **is** its name — there is no id and no registry, so a name must be non-empty and unique per project, compared case-insensitively.
- A group lives in one bucket and its members are contiguous in `order`; every membership change ends with `groups.renumber` on every bucket it touched. Skipping it leaves a group that renders as two blocks.
- The renderer derives a group's bucket and position from its **lowest-order member** and draws every member there regardless of that member's own `bucket` field, because task files are hand-editable.

- [ ] **Step 4: The manual-check list and known gaps**

`CLAUDE.md` lists two editor behaviours worth checking by hand whenever `ui/editor.js` is touched. Add the equivalent for groups, since neither is caught by a test: drag a task onto another and confirm the name box is focused **and** that dragging a third onto the group does not re-open it; and confirm `git status` shows a frontmatter-only diff after a group move.

Under "Known gaps", record what the spec put out of scope: merging two groups is refused rather than guessed, in both the drag and spin-up paths; groups are one level deep; nothing renders a group in the progress view even though done tasks keep their `group`.

Update `README.md:81`'s settings line from "WIP limit" to the group limit.

- [ ] **Step 5: Run the whole suite one last time and commit**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: all pass.

```
git add CLAUDE.md README.md
git commit -m "docs: record what a group is and what it guarantees"
```

---

## After the last task

Run the whole suite, then the manual checks from Tasks 7–10 in one pass on the real app — they were each written to catch a failure that is silent, and several of them only interact once every piece is in place. Task 9's check 2 (nothing renders twice) and Task 10's check 1 (the banner equals what is on screen) are the two that prove the original bug is actually gone.
