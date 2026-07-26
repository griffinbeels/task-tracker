# The selection bar

**Goal:** When tasks are ticked, show a bar above the list with bulk Move, Done
and Delete — and give the app a way to delete a task, which it has never had.

**Status:** in progress (worktree feature/selection-bar)
**Dependency verdict:** Dependent on `feature/task-groups`

**Spec:** `docs/superpowers/specs/2026-07-25-selection-bar-design.md` (approved,
committed as `e46f691` before this branch existed).

**Planned touch-set:**
- files/modules: `ui/selection.js` *(new)*, `ui/tasks.js`, `ui/index.html`,
  `ui/style.css`, `app.py`, `store.py`, `tests/test_app.py`,
  `tests/test_store.py`, `CLAUDE.md`
- shared contracts touched: `Api` bridge surface (three new methods sharing a new
  `_tasks()` helper, with `hand_off` refactored onto it); `selectedIds()` and the
  `spin-up` handler in `ui/tasks.js`
- risky files: no binary or generated assets. `ui/tasks.js`, `app.py` and
  `store.py` are the god-files every feature in flight flows through.

**Collision notes:**

Three features are in flight in this repo at once:

| Branch | Where | State |
|---|---|---|
| `feature/task-groups` | the main checkout | actively being implemented, through Task 7 of 11 |
| `feature/session-identity` | `task_tracker-worktrees/session-identity` | spec only, idle |
| `feature/selection-bar` | this worktree | spec written, planning |

This branch is based on `feature/task-groups` at `6ea6523`, **not** on `main`.
That is deliberate: task-groups splits `ui/tasks.js` into `tasks.js` +
`groups.js` + `inprogress.js`, adds the `group` field to `store.py`, renames
`wip_limit` to `group_limit`, and rewrites the bridge. Branching from `main`
would mean writing this feature against a file layout that no longer exists and
resolving conflicts in five files by hand. Branching from its HEAD means writing
against the final shape.

The cost is coupling: this cannot land before task-groups does.

**Task 9 of the groups plan has not landed yet and matters here.** It adds the
IN PROGRESS section, whose rows are selectable *across projects* — which is
exactly why the spec routes every action through `selectedInOneProject()`
rather than reading `currentProject`. Merge `feature/task-groups` into this
branch once it completes, and before implementing anything that touches
selection semantics.

**Context:** Ticking a checkbox is currently invisible — nothing on screen
changes — and it feeds only `Spin up Claude`, so a forgotten selection silently
changes what the next hand-off sends. Separately, there is no delete anywhere in
the app: `complete_task` moves a file to `done/`, and nothing ever unlinks one,
so a task written by mistake can only be *finished*, which files it in the
progress view as work you did. One bar answers both.
