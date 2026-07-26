# Restart from inside the window, and come back to the same project

*2026-07-25*

Editing the tracker's own source is routine — it is the project it most often
tracks. But a running window keeps the code it started with, so every change
means finding `run.bat` on disk and double-clicking it. Two things fix that: a
button in the header that relaunches the app, and a restart that puts you back
on the project you were looking at.

## What the button does

Pressing ↻ spawns a new `pythonw app.py` process and nothing else. The new
process calls `singleton.acquire()`, fails to bind port 8090, sends `SHUTDOWN`
to the running window, waits for the port, and takes over. The running window
destroys itself on that signal, which fires `closing`, which saves geometry.

This is the existing handover path — the same one that runs when you launch
`run.bat` over an open window. Nothing new is invented for shutdown, and three
properties fall out of reusing it:

- **Geometry survives**, because the normal close path runs.
- **A failed launch is not destructive.** If the new process dies before it
  reaches `acquire()` — an added dependency that `run.bat` would have installed
  is the realistic case — it never sends `SHUTDOWN`, so the old window stays
  open. The button appears to do nothing, which is a far better failure than a
  tracker that vanishes.
- **The old window does not close itself.** Closing first and spawning second
  would leave a gap where a crash in between loses the window entirely.

The button does not sync dependencies. `run.bat` runs `uv pip install` on every
launch; the button skips it, in exchange for no console window, no `pause` that
could hang invisibly, and an instant restart. Dependencies here are exactly
three and change roughly never. When one does change, `run.bat` is still the
answer, and the failure mode above makes that recoverable rather than confusing.

There is no confirmation dialog. One click always restarts, including with the
editor open — a half-written capture is lost, and that is the accepted cost of
keeping the gesture to a single click.

## Components

### `restart.py` (new)

Owns one thing: spawning a fresh copy of this app.

- **Interpreter**: the sibling `pythonw.exe` beside `sys.executable`, falling
  back to `sys.executable` itself. Launched from `run.bat`, `sys.executable` is
  already `pythonw.exe`; the sibling lookup covers a dev run started with
  `python app.py`, which would otherwise restart into a console window.
- **Arguments**: `[interpreter, <repo>/app.py]`, with `cwd` set to the repo
  root, both derived from `__file__` rather than from the current working
  directory.
- **No window, no focus**: `creationflags=CREATE_NO_WINDOW`, plus
  `launcher.unfocused_startup()`. Invariant 10 says any future spawn gets the
  same treatment, so this reuses that helper rather than copying its four lines.
  `CREATE_NO_WINDOW` alone would cover the pythonw case; the startupinfo is what
  covers the `python.exe` fallback.
- **The environment is inherited, not rebuilt.** Invariant 8 rebuilds the
  environment for a spawned *Claude session*, so that session looks like one
  opened by hand. The opposite is wanted here: a tracker replacing itself should
  be identical to the tracker it replaces, venv `PATH` included. Sessions the
  new tracker spawns are unaffected either way, because `spawn_claude` rebuilds
  through `login_environment()` regardless of what the tracker inherited. This
  reasoning belongs in the module docstring — without it the next reader sees
  invariant 8 being ignored.

`CREATE_NO_WINDOW` is read through `getattr`, matching `launcher.NEW_CONSOLE`,
so the module imports on a non-Windows machine.

### `app.py`

`Api.restart()` — one line, calling into `restart.py`. Wiring only. It returns
nothing; the renderer has nothing to wait for, since success means this process
is about to be destroyed from underneath it.

### Remembering the project

The selected project lives only in `currentProject` in `ui/state.js` and dies
with the window. It needs a home on disk.

**A new `~/.task-tracker/session.json`, holding one key.** `registry.py` gains
`last_project()` and `set_last_project(name)`, reached through a
`_session_file()` function rather than a module constant — tests monkeypatch
`CONFIG_DIR`, and binding it at import writes to the user's real home
(invariant 7).

Deliberately **not** a field on `Settings`: `Api.save_settings` rebuilds the
whole `Settings` object from the three fields the settings overlay sends, so a
`last_project` living there would be silently wiped every time those settings
were saved. A separate file has no such coupling, and the regression test for
it is "saving settings does not forget the project".

Written on change rather than on close, so it survives a crash or a kill.

- `Api.get_state()` returns `last_project` alongside the existing keys.
- `Api.set_last_project(name)` writes it.

### `ui/state.js`

- A `rememberProject(name)` helper sets `currentProject` and fires
  `set_last_project` through `callApi`. The picker's `onchange` and the
  add-project flow both route through it, so there is one place that decides
  what "the current project" means.
- `refresh()` resolves the default in this order: an existing `currentProject`
  (so a later refresh never re-picks), else `last_project` **if it still names a
  registered project**, else the first project. The middle guard matters —
  remove or rename the remembered project and an unguarded lookup selects
  nothing at all.

A stale `last_project` naming a removed project is left on disk rather than
corrected on read. It is overwritten by the next selection, and rewriting config
as a side effect of reading it is worse than a dead key.

### Header layout

The header is a single flex row: picker, `+`, Capture, inbox (usually hidden),
Progress, ⚙. At the default 420px window that is 396px of content and the row is
close to full; a sixth button overflows it.

- `<button id="restart-button" title="Restart Task Tracker">↻</button>`, placed
  immediately before ⚙ — both are app-level utilities and belong together at the
  end of the row.
- `#project-picker` becomes `flex: 1 1 auto` with a `min-width` floor instead of
  a hard `min-width: 150px`. It then takes the leftover space (more than 150px
  at the default width) and gives it back as the window narrows, rather than
  forcing buttons off the row.
- `header button { flex: none }`, so buttons keep their size and only the picker
  absorbs the change.
- ↻ and ⚙ share one square icon-button rule. Two utility icons of different
  widths sitting side by side read as a rendering error rather than a pair.

## Testing

- `tests/test_restart.py` — monkeypatch `subprocess.Popen` at the boundary and
  assert the argument vector, `cwd`, `CREATE_NO_WINDOW` and the presence of
  `startupinfo`. Never spawn a real process, and never call `app.main()`.
- `tests/test_registry.py` — `last_project()` is `None` with no file; it round
  trips; and it survives `save_settings`.
- `tests/test_app.py` — `get_state()` carries `last_project`;
  `set_last_project` persists.

No JS test runner exists, so three things are checked by hand:

1. Select a project that is not the first, press ↻ — the window reopens on that
   project, at the same size and position.
2. Close with the X, run `run.bat` — same project. (The button is not the only
   path that has to restore it.)
3. The header is one line at 420px with nothing squashed, and narrowing the
   window shrinks the picker rather than pushing ⚙ out of view.

## Not doing

- **No dependency sync.** Covered above.
- **No watchdog.** A restart whose replacement dies at import leaves the old
  window open and silent. Detecting that means the outgoing instance timing how
  long it takes to be asked to shut down, which is machinery for a case that
  only arises when someone adds a dependency.
- **Nothing else is remembered.** The search box, the all-projects toggle and
  scroll position all reset. Only the project is restored.
