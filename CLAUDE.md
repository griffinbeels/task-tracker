# Task Tracker — working notes for Claude

A single always-on-top window over markdown task files that live inside each
tracked project's own repo. It replaces a notepad, not Jira. Every design call
was made deliberately; the ones marked **invariant** were each learned by
shipping the bug first.

## Where the rest of this lives

This file is the map. The detail sits in `.claude/rules/`, split by what it is
about, and most of it carries a `paths:` header so it loads **only when a
matching file is read** rather than in every session. Two consequences worth
knowing before you go looking for something:

- If you are about to work on a file, open it first. The rule for it arrives
  with it. Asking about drag behaviour without reading `ui/drag.js` gets you
  this map and nothing else.
- You can always read a rule directly. They are ordinary markdown.

| Rule file | Loads when you read | Holds |
|---|---|---|
| `.claude/rules/storage.md` | `store.py`, `registry.py`, `groups.py`, `inbox.py`, `migrate.py`, `window_state.py` | Invariants 1, 7, 15, 16, 17, 20, 23, 26; what is on disk |
| `.claude/rules/handoff.md` | `launcher.py`, `ui/tasks.js`, `ui/selection.js` | Invariants 2, 8, 9, 10, 19, 22, 24, 25, 31; the shared module in full |
| `.claude/rules/bridge.md` | `app.py`, `ui/state.js` | Invariants 3, 4, 5, 6, 21; adding a bridge method |
| `.claude/rules/editor.md` | `ui/editor.js`, `ui/triage.js`, `ui/settings.js` | Invariants 11, 12, 13, 14, 30 |
| `.claude/rules/drag.md` | `ui/drag.js`, `ui/drag-geometry.js`, `ui/groups.js`, `ui/inprogress.js` | Invariants 18, 27, 28 — the largest body of detail here |
| `.claude/rules/ui-surfaces.md` | any `ui/*.js`, `ui/style.css`, `ui/index.html` | Invariant 29, the stacking ladder, the CSS comment trap, how to measure anything animated, the vendored editor |
| `.claude/rules/ui-checks.md` | any `ui/*.js`, `ui/style.css`, `ui/index.html` | The by-hand checks — hand them to the user when a UI task lands |
| `.claude/rules/tests.md` | `tests/*.py` | What is covered, and what is deliberately not |
| `.claude/rules/worktrees.md` | always | Parallel features |
| `docs/known-gaps.md` | on demand | Spec behaviours that were never built, and why. Read before proposing a feature |

**Specs, plans and prototypes are on disk but not in the repo.**
`docs/superpowers/` and `.planning/` are git-ignored: they are working notes
that quote conversations and carry absolute paths, and this is a public
repository. They remain the record of why things are the way they are — and one
of them is the reproduction asset for an open bug — so read them locally. This
file and `.claude/rules/` are the current documentation; the specs are history,
and where the two disagree, these win.

## Run and test

```powershell
run.bat                                          # launch (creates venv on first run)
& ".venv\Scripts\python.exe" -m pytest tests/ -q # 387 tests
```

- **PowerShell, not Bash.** The Bash tool on this machine cannot resolve
  `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`/`||` — chain with `;`
  or `if ($?) { }`.
- **Python 3.12**, created by `uv venv --python 3.12 .venv`. System Python is
  3.14 and breaks these packages. The venv has **no pip** — install with
  `uv pip install --python ".venv\Scripts\python.exe" <pkg>`.
- Dependencies are `pywebview`, `pyperclip`, `pyyaml` (+ `pytest`), and
  **`claude-console`** — the shared module below. Adding more needs a reason.
- **One command installs all of them**, and it names the shared module's
  checkout rather than reading it from `pyproject.toml`:
  `uv pip install --python ".venv\Scripts\python.exe" -e <claude-console> -e . pytest`.
  This machine's literal path is in `CLAUDE.local.md`, which is not tracked —
  a public repo cannot carry one machine's home directory, and no single path
  can serve both this checkout and a worktree four levels under it. Measured
  equivalent to the `[tool.uv.sources]` entry it replaces: `claude_console`
  still resolves into the source tree, still editable, still live.
- **Never run `app.py` from a subagent doing verification.** It opens a window
  and writes to the user's real `~/.task-tracker/`. Tests cover everything that
  can be covered without a window.

## The shared module: `claude_console`

**Opening a Claude session and typing into it is not this app's code any more.**
It lives in its own repo, one copy, shared with every project on this machine,
and it owns everything that would be true of a session opened on a git diff or
a form submission rather than on a task: spawning the session into whatever
this machine's default terminal is, resolving the pid to type into, writing to
the console's input buffer, the rebuilt environment, and `safe_line`/`cap`.

```python
session = claude_console.open_session(project_path, launch)
session.deliver(prompt=prompt, commands=commands)
```

It is installed **editable**, so there is no version and nothing to update — and
a breaking change there breaks this immediately. That direction is guarded from
the other side: this repo is listed in that repo's `consumers.json`, and a hook
there runs *this* suite on every edit to the shared package.

If you find yourself adding something to `launcher.py` that does not mention a
task, a group or a bucket, it belongs over there instead. The rest —
invariants 8, 9, 10, 22, 24 and 25, and why a session window is allowed to take
focus — is in `.claude/rules/handoff.md`.

## Architecture

Ten small Python modules and nine plain `<script>` files, plus one vendored
library and one shared machine-level package. No framework, no HTTP server, no
bundler.

| File | Owns |
|---|---|
| `store.py` | Task dataclass, markdown+frontmatter round-trip, `.tasks/` layout, CRUD — moving a task into `done/` and back out of it again — the colour vocabulary (`CLAUDE_COLORS`), and `write_text_atomic`, which every text file this app owns is written through |
| `registry.py` | `~/.task-tracker/projects.json`, `settings.json` and `session.json` |
| `inbox.py` | Raw untriaged notes in `~/.task-tracker/inbox/` |
| `migrate.py` | Type rename/delete sweep across every project |
| `groups.py` | Group membership: assign/create/rename/disband/move, reorder-within-a-group, the bucket renumber, the spin-up rule, and `place` — the whole destination a drop resolves to. A group **is** its name — no ids, no registry |
| `launcher.py` | Prompt assembly — the task's own file path, one per line (invariant 2) — clipboard, session naming, the `/color` command, and `Deliveries`. `build_prompt` is the single source of what gets typed, and both hand-off and the per-row copy button go through it, so the two can never drift. Opening the window and typing into it is `claude_console`'s |
| `claude_console` (shared) | Not in this repo. Spawning the session into this machine's default terminal, the pid to type into, typing into the console's input buffer, the rebuilt environment, and `safe_line`/`cap` |
| `singleton.py` | Single-instance lock on `127.0.0.1:8090`, with handover |
| `restart.py` | Spawning a replacement instance. Closes nothing itself — the replacement's `singleton.acquire()` does that, which is what saves the geometry |
| `window_state.py` | `window.json`, and the rule that geometry is only worth keeping if a monitor can show it. **Geometry and nothing else** |
| `app.py` | pywebview window + the `Api` bridge class. **Wiring only** |
| `ui/state.js` | `state`, `currentProject`, `refresh()`, `callApi()`, `API_FAILED`, the colour vocabulary, `localDate`, `asShown`, the Escape key that closes the topmost overlay, and `showToast` |
| `ui/zoom.js` | Text size, per region. `zoomAssignments()` is the single place a region is defined |
| `ui/tasks.js` | Task rows, buckets, search, cross-project, handoff, copy-as-prompt, the batch-name row, and `watchDelivery`. `handOff` is the **one** place a session is opened on tasks. It also owns `CLAUDE_ICON`, the single definition of the glyph |
| `ui/groups.js` | The group block and header, rename-in-place, select-the-group, and folding. What a group **is** |
| `ui/drag-geometry.js` | Where a drop lands, and nothing about how it looks. Takes a POINT against boxes frozen at lift, and answers with one destination. Reads no event at all, and a convention test says so |
| `ui/drag.js` | The gesture and its motion, and `flipBlocks`, the one FLIP every rearrangement in the app goes through |
| `ui/inprogress.js` | The IN PROGRESS section — drawn even when empty, because it is a drop target — its per-project split, folding, and the reset actions |
| `ui/selection.js` | The selection bar. It owns `selectedInOneProject()` and `aimedAt` — what a tick means to every button *outside* the bar |
| `ui/editor.js` | The one editor overlay: fields, chips, Toast UI, image paste |
| `ui/triage.js` | Inbox queue navigation — which note is current, and nothing else |
| `ui/settings.js` | Progress view, type editor, git-tracking toggle |
| `ui/vendor/` | Toast UI Editor 3.2.2, committed on purpose |

The nine scripts **share one global scope** and load in the order
`state.js`, `zoom.js`, `tasks.js`, `groups.js`, `inprogress.js`, `selection.js`,
`editor.js`, `triage.js`, `settings.js` (see `ui/index.html`, where the
vendored library loads first). A file with no `<script>` tag never runs and
every symbol it defines is undefined at the first call site that reaches for
it, which is silent and mid-render —
`test_every_ui_script_is_loaded_by_the_page` fails the build on one.
Functions defined in one are callable from
another at runtime — `triage.js` calls into `editor.js`, `editor.js` reads
`triage.js`'s queue, `state.js` calls `inprogress.js`'s
`inProgressGroupKeys()` despite loading three files earlier, and `tasks.js`'s
Spin up handler calls `selection.js`'s `selectedInOneProject()` from the file
before it — all of which works because every handler resolves its references
at call time, not at load. This split exists to keep
each file under ~300 lines — do not consolidate them, and do not introduce ES
modules or a build step.

**`ui/vendor/` is committed, not fetched, and the build matters** — see
`.claude/rules/ui-surfaces.md`, which carries why it must be
`toastui-editor-all.min.js` and what shipped when it was not.

If you find yourself writing business logic in `app.py`, it belongs in a backend
module instead.

## Invariants

Break one of these and the failure is silent. Each cost a bug. They are numbered
because things elsewhere cite them by number, and the numbering is kept as-is
across the split:

| Numbers | File |
|---|---|
| 1, 7, 15, 16, 17, 20, 23, 26 | `.claude/rules/storage.md` |
| 2, 8, 9, 10, 19, 22, 24, 25, 31 | `.claude/rules/handoff.md` |
| 3, 4, 5, 6, 21 | `.claude/rules/bridge.md` |
| 11, 12, 13, 14, 30 | `.claude/rules/editor.md` |
| 18, 27, 28 | `.claude/rules/drag.md` |
| 29 | `.claude/rules/ui-surfaces.md` |

**8, 9, 10, 22, 24 and 25 are enforced by code in `claude_console`, not here.**
They still bind this app — a hand-off that takes the keyboard is this app's bug
however it happened — but the file to open is over there, and that repo's own
CLAUDE.md carries the full measurements plus five more it learned since.

## Adding a feature

- **New bridge method** → `.claude/rules/bridge.md`.
- **New UI surface** → put it in whichever script owns that concern; add its
  `<script>` tag only if you create a new file. `.claude/rules/ui-surfaces.md`
  has the stacking ladder a new floating surface needs a rank in.
- **Anything that edits a task** goes through `openEditor()` — see
  `.claude/rules/editor.md`.
- **Never add a CDN reference.** A convention test enforces it.
- **A UI change cannot be signed off from its diff.** Claude must never run
  `app.py`, so "checked by running the app" means *the user* runs it. Hand them
  the relevant block of `.claude/rules/ui-checks.md` when the task lands, not at
  the end of the plan.
- **Before proposing a feature, read `docs/known-gaps.md`** — several obvious
  ideas were considered and declined, with reasons.
