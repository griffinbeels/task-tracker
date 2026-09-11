---
paths:
  - "tools/bootstrap.py"
  - "tools/build_macos_app.py"
  - "tools/install_macos_app.py"
  - "tools/macos_entry.py"
  - "restart.py"
---
# Chain: the checkout executed by the Mac app

- **Value:** the tracker and console source directories used by an app launch.
- **Source truth:** the primary checkouts, resolved from Git's common directory.
- **Sink:** the task window opened from Applications and by its restart action.
- **One clock:** none; a restart loads current source from disk.

| # | hop | value is true here as | module | probe (reads it) | inject (forces it) | when the hop is broken, the probe shows | when the probe itself is broken, it shows |
|---|-----|-----------------------|--------|------------------|--------------------|------------------------------------------|--------------------------------------------|
| 1 | Resolve | primary tracker and console paths | `tools/bootstrap.py` | readiness/import probe | set `CLAUDE_CONSOLE_PATH` in an isolated test | missing or wrong editable dependency | nonzero preflight result |
| 2 | Build | alias source and bundle configuration | `tools/build_macos_app.py` | read `Contents/Resources/task-tracker.json` | build a worktree preview | unexpected source, console or preview configuration | missing/invalid JSON |
| 3 | Install | Applications link to primary `dist` | `tools/install_macos_app.py` | installer `--dry-run`, resolve symlink | install into a temporary Applications directory in tests | preview/foreign target rejected | nonzero result, no filesystem changes |
| 4 | Launch | source used by the actual bundle executable | `tools/macos_entry.py` | bundle executable `--check-only` | fixture bundle configuration | source mismatch or dependency error | no JSON / nonzero exit |
| 5 | Restart | bundle path forwarded through LaunchServices | `restart.py` | inspect mocked restart argv and native replacement window | fixture `TASK_TRACKER_APP_BUNDLE` | wrong bundle or duplicate preview data identity | mock never reaches restart seam |

## Counterfactual recipe

Run the actual bundle executable with `--check-only` before opening a window.
Compare its source and console with the primary checkouts. Rebuild from primary
and repeat: a stale launcher becomes correct at hop 2, while a stale editable
dependency needs repair at hop 1. Use temporary Applications paths to exercise
installation; worktree installation must fail without changing the daily app.

## Failure catalogue

- 2026-09-10, hop 2: a bundle-specific preview port differed from the source
  launcher's config-derived port. The builder now leaves one config-derived lock
  identity to `singleton.py`; the packaging regression pins that boundary.
- 2026-09-10, hop 5: LaunchServices does not reliably inherit `Popen` environment
  overrides. Shared launch and restart commands explicitly forward configuration,
  port and console variables with `open --env`; tests inspect the argv.
