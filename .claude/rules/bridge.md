---
paths:
  - "app.py"
  - "ui/state.js"
  - "tests/test_app.py"
---

# The bridge — app.py and the calls that cross it

Invariants 3, 4, 5, 6 and 21.

3. **Frontend bridge calls go through `callApi('name', ...)`** in `state.js`,
   never `window.pywebview.api.*` directly. `get_state` inside `refresh()` is the
   one documented exception, and it has its own `try/catch`.

4. **The failure sentinel is `API_FAILED` (a Symbol), never `null`.** Bridge
   methods that return nothing come back as JS `null` on *success*, so `null`
   cannot mean failure. Any guard comparing against `null` is a bug. Watch for
   falsy-but-valid returns too: `count_tasks_with_type` legitimately returns `0`.

5. **User-authored text never reaches `innerHTML`.** Titles, type names, type
   colours and **group names** are all unvalidated strings from hand-editable
   files, and this markup runs with full `window.pywebview.api` access. Build
   elements and set `.textContent` / `.style.background`.

6. **Never resolve a task id against `currentProject`.** Task ids are
   per-project integers — every project has a task 1 — so an id is only
   meaningful paired with its project. A row's project comes from its own
   `dataset.project`, which `taskRow` sets for exactly this reason;
   `selectedIds()` carries it, `spin-up` derives its target project from the
   selection rather than from `currentProject`, and `openEditor` takes
   `context.project` and routes every save, attachment read and image write
   through `editorContext.project`. Because all three obey it, **any row from
   any project opens the editor** — search, all-projects and IN PROGRESS
   alike. Selection is the narrower case: IN PROGRESS allows it because it is
   split by project heading, while search and the all-projects view disable it,
   since there a row's project is not visible as a grouping and a mixed tick is
   easy to make by accident.

21. **The selected project is reconciled against the project list on every
    refresh.** `projects.json` is hand-editable and `refresh()` re-reads it, so
    the selection can go stale after it is made, not just before. When
    `currentProject` names a project that is no longer registered, no
    `<option>` matches and the browser silently selects the first one — the
    picker then shows one project while the list below renders another, which
    reads as the tasks having been lost. The check is the same one that
    restores `last_project` at launch; it just runs unconditionally rather than
    only when `currentProject` is unset.

- **New bridge method:** add it to `Api` in `app.py` (translate JS args → backend
  call → JSON-safe return; run `Task` objects through `_task_dict`, which strips
  the non-serialisable `Path`), then call it from JS via `callApi`.
