# Parallel features (worktrees)

## Parallel features (worktrees)

`main` is the only long-lived branch and the **primary checkout stays on it**.
Features are built in worktrees that branch from local `main` HEAD and merge
back. Sequential solo work can commit straight to `main`.

- **Worktrees live at `.claude/worktrees/<slug>` on `feature/<slug>`**, inside
  the repo and git-ignored. `/start-feature` creates them; `/wrap-feature`
  verifies, merges to `main`, and removes them.
- **Branch from local `main` HEAD, never from `origin`** — origin is usually
  stale, and never from another feature branch unless the work genuinely
  depends on it.
- **Each worktree needs its own `.venv`**, and the install must name the
  `claude-console` checkout — `pyproject.toml` deliberately does not, so `-e .`
  alone resolves nothing and uv reports the whole requirement set unsatisfiable:

  ```powershell
  uv venv --python 3.12 .venv
  uv pip install --python ".venv\Scripts\python.exe" -e <claude-console> -e . pytest
  ```

  There is no shared venv. This is exactly what a `[tool.uv.sources]` entry used
  to do for free, and why it cannot come back: one absolute path publishes a home
  directory in a public repo, and a relative one cannot serve both this checkout
  and a worktree four levels under it, since the same `pyproject.toml` is checked
  out into both. `run.bat` finds the checkout on its own — beside the repo, or
  four levels up from a worktree — so a worktree that only ever runs `run.bat`
  needs nothing typed here.
- **Run the suite from the worktree root**, always with a relative path:
  `Set-Location <worktree>; & ".venv\Scripts\python.exe" -m pytest tests/ -q`.
  Pointing pytest at another checkout's `tests/` imports *this* tree's modules
  against *that* tree's tests and reports a wall of assertion failures that
  reads exactly like the branch being broken.

Three things went wrong on 2026-07-25, building three features in parallel.
Each is cheap to avoid and expensive to diagnose:

- **The primary checkout drifted onto a feature branch.** `run.bat` then
   launched an app built from files that did not contain the feature under
   test, for an hour, while `main` had it the whole time. If the app behaves
   as though a merged feature is absent, check `git rev-parse --abbrev-ref
   HEAD` in the folder you launched from *before* debugging the feature.
- **A worktree follows its branch's ref; its files do not.** A merge worktree
   created at one commit had HEAD resolving to a newer one minutes later,
   because a sibling advanced the branch — while its working files were still
   the old ones. `git log --oneline -1` immediately before merging.
- **Renames cross branches badly.** A branch cut before `#wip-warning` became
   `#group-limit-warning` carried a call to a function that no longer existed.
   There is no JS test runner here, so nothing failed — it would simply have
   thrown at runtime. After merging any UI branch, grep for the old name and
   run `node --check ui/*.js`.

   **Two thirds of that is now the build's job.** A renamed *bridge* method is
   caught by `test_every_bridge_call_names_a_method_that_exists`, and a missing
   element id by `test_every_element_id_the_scripts_ask_for_exists` — both fail
   on a merge that half-lands a rename. What no test can see is a **JS function**
   renamed on one branch and still called from another: nothing here parses the
   shared global scope, and `node --check` only reads syntax. That is the grep
   that still has to happen by hand.
