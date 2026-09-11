# Windows and macOS support

Both platforms use the same Python task model, markdown storage, bridge and
HTML/CSS/JavaScript interface. A feature is a shared behavior change by default.
Platform-specific code belongs at a native boundary, not in separate task flows.

## Ownership

| Responsibility | Owner |
|---|---|
| Task storage, grouping, inbox, settings and progress | Existing Python modules |
| Task interface and editor | Shared files under `ui/` |
| Native file/URL opening, startup dialogs and shortcut names | `desktop.py` |
| Tracker replacement process | `restart.py` |
| Runtime/dependency discovery and readiness | `tools/bootstrap.py` |
| Mac source-backed application bundle | `tools/build_macos_app.py` |
| Opening and delivering to Claude sessions | Shared `claude-console` package |

Keep `app.py` as wiring. Do not add Win32 calls, AppleScript or terminal typing
to task/group/storage modules. Native opening still receives only the targets
validated by the bridge and storage layer. User text travels as an argument,
not interpolated executable code.

Python 3.12 is the shared runtime selected by both source launchers. Use one
dependency definition in `pyproject.toml`; OS markers describe actual native
dependencies. `claude-console` remains editable from a separate checkout.
Changes to that shared package must pass its tests and tracker consumer tests.

## Expected differences

- macOS uses Command for paste/edit/zoom and native window decorations; Windows
  uses Control. The actions and stored values are shared.
- Mac opens a source-backed `.app`; Windows uses `run.bat` and `pythonw.exe`.
- Mac Claude sessions use Terminal.app; Windows uses its existing terminal
  integration. Both leave the task paths editable and unsent. Automation
  permission and live delivery on Mac must be checked in the actual terminal.
- Registration, window geometry, zoom and folds are local to each computer.
  A port does not synchronize task folders. Existing absolute attachment links
  are not portable between computer paths; do not rewrite task prose as part
  of a native integration change.

Always-on-top remains off by default. Relaunch must keep a single window,
save visible geometry, and preserve in-flight user Claude sessions. A failed
replacement preflight must leave the current tracker available.

## Test and review requirements

`.github/workflows/tests.yml` runs the same contracts on Windows and macOS,
with real platform dependencies. It records the two source revisions. The
workflow's `console_ref` input supports a paired shared-launcher change.
Neither platform job is allowed to fail silently. Repository administrators
must select both **Tests (windows-latest)** and **Tests (macos-latest)** as
required checks; committing workflow YAML does not configure branch protection.

Do not skip shared tests just because they fail on the other OS. Mock native
side effects at the module boundary. Keep native-only structure checks marked
for the OS that actually owns them, and test the shared contract everywhere.
Convention scans use paths relative to their owning checkout so nested worker
trees cannot pollute results or make the scan empty.

On each feature, record the applicable native evidence: first launch/relaunch,
window placement/topmost, file opening, screenshot paste, keyboard focus and
Claude delivery. Headless browser checks verify page behavior but cannot prove
Cocoa/WebView2 or desktop focus. Automated tests must not open user windows,
type into live terminals or write real tracker data.

For a preview, set `TASK_TRACKER_CONFIG_DIR` to a separate directory. The
singleton port is then derived from that directory unless `TASK_TRACKER_PORT`
is explicitly supplied. Generated worktree launchers do this automatically.
Preserve any preview data the user creates before removing its checkout.

## Verification status of the first Mac port

This branch is a prototype. Local Mac unit tests, isolated terminal relay
tests and browser evidence are recorded with its private feature notes.
Actual Terminal.app/Claude delivery, Finder/Dock behavior and Windows native
regression checks remain separate acceptance steps. Do not turn a passing mock
or the existence of a CI file into a claim that those steps have run.
