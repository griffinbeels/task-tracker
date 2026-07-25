# Task Tracker — working notes for Claude

A single always-on-top window over markdown task files that live inside each
tracked project's own repo. It replaces a notepad, not Jira. Every design call
below was made deliberately; the ones marked **invariant** were each learned by
shipping the bug first.

## Run and test

```powershell
run.bat                                          # launch (creates venv on first run)
& ".venv\Scripts\python.exe" -m pytest tests/ -q # 81 tests
```

- **PowerShell, not Bash.** The Bash tool on this machine cannot resolve
  `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`/`||` — chain with `;`
  or `if ($?) { }`.
- **Python 3.12**, created by `uv venv --python 3.12 .venv`. System Python is
  3.14 and breaks these packages. The venv has **no pip** — install with
  `uv pip install --python ".venv\Scripts\python.exe" <pkg>`.
- Dependencies are exactly `pywebview`, `pyperclip`, `pyyaml` (+ `pytest`).
  Adding more needs a reason.
- **Never run `app.py` from a subagent doing verification.** It opens a window
  and writes to the user's real `~/.task-tracker/`. Tests cover everything that
  can be covered without a window.

## Architecture

Seven small Python modules and four plain `<script>` files. No framework, no HTTP
server, no bundler.

| File | Owns |
|---|---|
| `store.py` | Task dataclass, markdown+frontmatter round-trip, `.tasks/` layout, CRUD |
| `registry.py` | `~/.task-tracker/projects.json` and `settings.json` |
| `inbox.py` | Raw untriaged notes in `~/.task-tracker/inbox/` |
| `migrate.py` | Type rename/delete sweep across every project |
| `launcher.py` | Verbatim prompt assembly, clipboard, Claude process spawn |
| `console_input.py` | Typing that prompt into the spawned session's console |
| `singleton.py` | Single-instance lock on `127.0.0.1:8090`, with handover |
| `app.py` | pywebview window + the `Api` bridge class. **Wiring only** |
| `ui/state.js` | `state`, `currentProject`, `refresh()`, `callApi()`, `API_FAILED` |
| `ui/tasks.js` | Task list, buckets, drag, search, cross-project, handoff, WIP |
| `ui/triage.js` | Capture and triage overlays |
| `ui/settings.js` | Progress view, type editor, git-tracking toggle |

The four scripts **share one global scope** and load in the order
`state.js`, `tasks.js`, `triage.js`, `settings.js` (see `ui/index.html`).
Functions defined in one are callable from another at runtime. This split exists
to keep each file under ~300 lines — do not consolidate them, and do not
introduce ES modules or a build step.

If you find yourself writing business logic in `app.py`, it belongs in a backend
module instead.

## Invariants

Break one of these and the failure is silent. Each cost a bug.

1. **Every `write_text` passes `newline="\n"`.** Windows otherwise translates
   `\n` to `\r\n`; a body containing `\r\n` then gains a blank line on every
   save. Reads deliberately use universal newlines so hand-edited CRLF files
   still parse — net behaviour is "line endings normalise to LF".

2. **Task bodies are verbatim.** They are user prose that gets typed into a
   Claude session. Never strip, trim, normalise, re-wrap or append.
   `build_prompt` emits `TYPE: body`, one task per line, and nothing else — no
   instructions, no "mark this done when finished". The single exception is a
   body's *trailing* whitespace, dropped so that the newline between tasks is
   exactly one newline; a body is never touched at the front or in the middle.

3. **Frontend bridge calls go through `callApi('name', ...)`** in `state.js`,
   never `window.pywebview.api.*` directly. `get_state` inside `refresh()` is the
   one documented exception, and it has its own `try/catch`.

4. **The failure sentinel is `API_FAILED` (a Symbol), never `null`.** Bridge
   methods that return nothing come back as JS `null` on *success*, so `null`
   cannot mean failure. Any guard comparing against `null` is a bug. Watch for
   falsy-but-valid returns too: `count_tasks_with_type` legitimately returns `0`.

5. **User-authored text never reaches `innerHTML`.** Titles, type names and type
   colours are all unvalidated strings from hand-editable files, and this markup
   runs with full `window.pywebview.api` access. Build elements and set
   `.textContent` / `.style.background`.

6. **Task ids are per-project integers.** Every project has a task 1. An id is
   only meaningful paired with its project — `taskRow` carries
   `dataset.project` for exactly this reason. Any view spanning projects must
   disable selection.

7. **Reach `registry.CONFIG_DIR` through the module at call time.** Tests
   monkeypatch it; binding it into a module-level constant at import captures
   the real home directory and makes the suite write to the user's actual
   config. `_projects_file()` / `_settings_file()` / `inbox_dir()` are functions
   for this reason. (`app.WINDOW_STATE` is the sole exception, safe only because
   `app.py` is never imported by a test — do not copy that pattern.)

8. **Spawned Claude sessions get a sanitized environment.** `Popen` inherits the
   parent env, so `CLAUDE_CODE_CHILD_SESSION` would make the handed-off terminal
   a nested child with no transcript history. `launcher.claude_environment()`
   strips the session-identity vars and sets
   `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE=1`.

9. **Typed text is bracketed, and waits for the prompt box.** `console_input`
   writes into the spawned session's console input buffer, which accepts input
   long before Claude is ready to read it. Unbracketed, the newline between two
   tasks reads as Enter and sends the first one alone; unwaited, the text is
   answered into whatever dialog is on screen — a folder Claude has not been
   trusted in opens on a question whose default is Enter. Both failures are
   silent, and both are why `paste()` polls for `READY_MARKERS` first. It is
   allowed to give up: the same text is on the clipboard.

## Data on disk

```
~/.task-tracker/projects.json   name -> path, tracked flag, launch override
~/.task-tracker/settings.json   wip_limit (5), stale_days (90), task types
~/.task-tracker/inbox/          untriaged raw notes
~/.task-tracker/window.json     window geometry
<project>/.tasks/.gitignore     contains `*` — the folder is invisible to git
<project>/.tasks/open/          NNNN-slug.md
<project>/.tasks/done/          the archive, and the progress view's source
```

`.tasks/` is **untracked by default** because several tracked repos are public
and committing would publish raw backlog prose. A per-project `tracked` flag
flips it (settings → the tracked checkboxes), which deletes that `.gitignore`.

## Adding a feature

- **New bridge method:** add it to `Api` in `app.py` (translate JS args → backend
  call → JSON-safe return; run `Task` objects through `_task_dict`, which strips
  the non-serialisable `Path`), then call it from JS via `callApi`.
- **New UI surface:** put it in whichever of the four scripts owns that concern;
  add its `<script>` tag only if you create a new file.
- **Tests:** `store.py`, `registry.py`, `inbox.py`, `migrate.py`, `launcher.py`
  and `Api` methods are all directly testable. Use `tmp_path` and the
  `monkeypatch.setattr(registry, "CONFIG_DIR", ...)` fixture pattern from
  `tests/test_registry.py`. Mock at the boundary — `subprocess.Popen` and
  `launcher.pyperclip.copy` — never spawn a real process. The one exception is
  `tests/test_console_input.py`, which really does open a console for a second
  or two: typing into another process's console is OS behaviour, and a mock of
  it would only assert that the mock was called.
- **Deliberately untested:** `main()` and window geometry persistence. Driving a
  native window under pytest is not worth the machinery; this is a decision, not
  an oversight.
- **No JS test runner.** Frontend changes are checked by running the app.

## Known gaps

Three spec behaviours were never implemented, and the deferred findings from the
whole-branch review are filed as tasks in this repo's own `.tasks/open/` — open
the tracker, select this project, and they are the backlog. Highlights:

- Cross-project rows do not click through to their project.
- Triage chips are mouse-only; the spec called for single-key assignment.
- Nothing ever writes `## Outcome`; the progress view renders it but it can only
  arrive by hand-editing.

Design spec: `docs/superpowers/specs/2026-07-25-task-tracker-design.md`
Implementation plan: `docs/superpowers/plans/2026-07-25-task-tracker.md`
