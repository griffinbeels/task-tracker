# Task Tracker — working notes for Claude

A single always-on-top window over markdown task files that live inside each
tracked project's own repo. It replaces a notepad, not Jira. Every design call
below was made deliberately; the ones marked **invariant** were each learned by
shipping the bug first.

## Run and test

```powershell
run.bat                                          # launch (creates venv on first run)
& ".venv\Scripts\python.exe" -m pytest tests/ -q # 323 tests
```

- **PowerShell, not Bash.** The Bash tool on this machine cannot resolve
  `.venv\Scripts\python.exe`. PowerShell 5.1 has no `&&`/`||` — chain with `;`
  or `if ($?) { }`.
- **Python 3.12**, created by `uv venv --python 3.12 .venv`. System Python is
  3.14 and breaks these packages. The venv has **no pip** — install with
  `uv pip install --python ".venv\Scripts\python.exe" <pkg>`.
- Dependencies are `pywebview`, `pyperclip`, `pyyaml` (+ `pytest`), and
  **`claude-console`** — the shared module below. Adding more needs a reason.
- **One command installs all of them**, because they are declared in
  `pyproject.toml` and `claude-console` has a `[tool.uv.sources]` path entry:
  `uv pip install --python ".venv\Scripts\python.exe" -e . pytest`.
- **Never run `app.py` from a subagent doing verification.** It opens a window
  and writes to the user's real `~/.task-tracker/`. Tests cover everything that
  can be covered without a window.

## The shared module: `claude_console`

**Opening a Claude session and typing into it is not this app's code any more.**
It lives at `C:\Users\griff\Desktop\code\claude-console`, one copy, shared with
every project on this machine, and it owns everything that would be true of a
session opened on a git diff or a form submission rather than on a task:
spawning through `conhost.exe`, the focus watchdog, resolving the real `claude`
pid inside the host, writing to the console's input buffer, the console font
and icon, the rebuilt environment, and `safe_line`/`cap`.

```python
session = claude_console.open_session(project_path, launch)
session.deliver(prompt=prompt, commands=commands)
```

Three things about it that matter here:

- **It is installed editable, so there is no version and nothing to update.**
  `site-packages` holds a `.pth` and a path finder pointing at that source
  tree, not a copy — an edit there (including a brand-new file) is live in the
  next process here. The other half of the same coin: **a breaking change there
  breaks this immediately.** That direction is guarded from the other side —
  this repo is listed in `claude-console/consumers.json`, and a PostToolUse
  hook there runs *this* suite on every edit to the shared package, blocking
  if it goes red. Nothing is needed here to participate; if this checkout ever
  moves, update that file's `path`.
- **`open_session` starts the focus watchdog itself.** `hand_off` used to, and
  that is exactly why it moved: a second consumer could simply not call it, and
  the failure is a window that steals focus two spawns in ten (invariant 10) —
  which nobody reads as a missing call.
- **The convention guard travelled with the code.** `claude-console` has its
  own `tests/test_conventions.py`. This repo's copy now has an *empty*
  allowlist, which is the assertion: nothing here opens a console at all.

If you find yourself adding something to `launcher.py` that does not mention a
task, a group or a bucket, it belongs over there instead.

## Architecture

Ten small Python modules and eight plain `<script>` files, plus one vendored
library and one shared machine-level package. No framework, no HTTP server, no
bundler.

| File | Owns |
|---|---|
| `store.py` | Task dataclass, markdown+frontmatter round-trip, `.tasks/` layout, CRUD — moving a task into `done/` and back out of it again — the colour vocabulary (`CLAUDE_COLORS`), and `write_text_atomic`, which every text file this app owns is written through |
| `registry.py` | `~/.task-tracker/projects.json`, `settings.json` and `session.json` |
| `inbox.py` | Raw untriaged notes in `~/.task-tracker/inbox/` |
| `migrate.py` | Type rename/delete sweep across every project |
| `groups.py` | Group membership: assign/create/rename/disband/move, reorder-within-a-group, the bucket renumber, the spin-up rule, and `place` — the whole destination a drop resolves to. A group **is** its name — no ids, no registry |
| `launcher.py` | Verbatim prompt assembly, clipboard, session naming and the `/rename`/`/color` command list — everything a hand-off is that is shaped by `store.Task`. A session is named after, in order: the batch row's typed name, the group every selected task shares, then the first task's title with a count. `build_prompt` is the single source of the `TYPE: body` format — both hand-off and the per-row copy button go through it, so the two can never drift. Opening the window and typing into it is `claude_console`'s |
| `claude_console` (shared) | Not in this repo. Spawning through `conhost.exe` so the window is never the machine default terminal's to draw, the focus watchdog, the pid inside the host, typing into the console's input buffer, the font and icon it renders in, the rebuilt environment, and `safe_line`/`cap` |
| `singleton.py` | Single-instance lock on `127.0.0.1:8090`, with handover |
| `restart.py` | Spawning a replacement instance. Closes nothing itself — the replacement's `singleton.acquire()` does that, which is what saves the geometry |
| `window_state.py` | `window.json`, and the rule that geometry is only worth keeping if a monitor can show it |
| `app.py` | pywebview window + the `Api` bridge class. **Wiring only** |
| `ui/state.js` | `state`, `currentProject`, `rememberProject()`, `refresh()`, `callApi()`, `API_FAILED`, the colour vocabulary (`CLAUDE_COLORS`) and `suggestColor`, `localDate` (the one place a date-only string is turned into a Date), and the Escape key that closes the topmost overlay |
| `ui/tasks.js` | Task rows, buckets, search, cross-project, handoff, copy-as-prompt, the batch-name row |
| `ui/groups.js` | The group block and header, rename-in-place, select-the-group, and `wireDrag` — one delegated drag controller for the whole list, which resolves every drop to a destination |
| `ui/inprogress.js` | The IN PROGRESS section — drawn even when empty, because it is a drop target — its per-project split, folding, and the reset actions |
| `ui/selection.js` | The selection bar: what is ticked, and the two things you can do to all of it. It owns `selectedInOneProject()`, the one place the per-project rule lives |
| `ui/editor.js` | The one editor overlay: fields, chips (project/type/when/group/colour), Toast UI, image paste |
| `ui/triage.js` | Inbox queue navigation — which note is current, and nothing else |
| `ui/settings.js` | Progress view — a completed task opens in the editor from here — type editor, git-tracking toggle |
| `ui/vendor/` | Toast UI Editor 3.2.2, committed on purpose — see below |

The seven scripts **share one global scope** and load in the order
`state.js`, `tasks.js`, `groups.js`, `inprogress.js`, `selection.js`,
`editor.js`, `triage.js`, `settings.js` (see `ui/index.html`, where the
vendored library loads first). Functions defined in one are callable from
another at runtime — `triage.js` calls into `editor.js`, `editor.js` reads
`triage.js`'s queue, `state.js` calls `inprogress.js`'s
`inProgressGroupKeys()` despite loading three files earlier, and `tasks.js`'s
Spin up handler calls `selection.js`'s `selectedInOneProject()` from the file
before it — all of which works because every handler resolves its references
at call time, not at load. This split exists to keep
each file under ~300 lines — do not consolidate them, and do not introduce ES
modules or a build step.

**`ui/vendor/` is committed, not fetched.** The UI is served from `file://` and
has to work with no network, so the editor is vendored rather than loaded from
a CDN. `tests/test_conventions.py` fails the build if the assets go missing or
if a CDN URL appears in `index.html`.

**It must be `toastui-editor-all.min.js`, never `toastui-editor.min.js`.** The
core build is not standalone: it declares all eight `prosemirror-*` modules as
*external*, and its UMD wrapper has no global names for them, so the browser
branch reads `e.toastui.Editor = t(e[void 0], e[void 0], …)` and hands the
editor `undefined` for every dependency. `window.toastui` still exists, so
nothing looks broken until `new toastui.Editor()` throws — and then Capture and
click-to-edit both silently do nothing, because both go through `openEditor`.
That shipped, and the size-and-not-a-404 convention test passed the whole time:
a file can be the right size, be genuinely downloaded, and still be the wrong
build. `-all` inlines the dependencies (`define([], t)`, factory called with no
arguments) and is the build the library's own script-tag documentation uses.
`test_the_vendored_editor_bundle_is_self_contained` now pins this.

The library's last release was February 2023 — it will not receive fixes, which
is a reason to keep it pinned and vendored rather than a reason to keep it
current.

If you find yourself writing business logic in `app.py`, it belongs in a backend
module instead.

## Invariants

Break one of these and the failure is silent. Each cost a bug.

**8, 9, 10, 22, 24 and 25 are now enforced by code in `claude_console`, not
here.** They still bind this app — a hand-off that takes the keyboard is this
app's bug however it happened — but the file to open is over there, and that
repo's own CLAUDE.md carries the full measurements plus five more it learned
since. Numbering is kept as-is because things elsewhere cite these by number.

1. **Every `write_text` passes `newline="\n"`.** Windows otherwise translates
   `\n` to `\r\n`; a body containing `\r\n` then gains a blank line on every
   save. Reads deliberately use universal newlines so hand-edited CRLF files
   still parse — net behaviour is "line endings normalise to LF".

   **In practice that means going through `store.write_text_atomic`**, which is
   how every text file this app owns is now written — task files,
   `projects.json`, `settings.json`, `session.json`, `window.json`, inbox
   notes. It passes the newline for you, and it writes a sibling `.tmp` and
   `os.replace`s it over the target, so a crash cannot leave a file truncated
   to nothing: a plain `write_text` is a truncate followed by a write, and this
   machine has taken a bugcheck mid-session before. It also unlinks the temp
   file when the write raises — `.tasks/open/` is globbed for `*.md` and a
   surviving `0007-x.md.tmp` would read as a second copy of the task. A new
   writer that reaches for `write_text` directly is the way to reintroduce
   both problems at once.

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

7. **Reach `registry.CONFIG_DIR` through the module at call time.** Tests
   monkeypatch it; binding it into a module-level constant at import captures
   the real home directory and makes the suite write to the user's actual
   config. `_projects_file()` / `_settings_file()` / `inbox_dir()` are functions
   for this reason, and so is `window_state._state_file()`. There is no
   exception: `app.WINDOW_STATE` used to be one, and it was never as safe as its
   note claimed — `tests/test_app.py` does import `app.py`, and only a
   `monkeypatch.setattr(app, "WINDOW_STATE", ...)` in its fixture kept the suite
   off the real `~/.task-tracker/`.

8. **A spawned session's environment is rebuilt, never filtered.** `Popen`
   inherits the tracker's environment, and the tracker is normally started
   *from* a Claude session — which sets a batch of variables for the processes
   it spawns. Inheriting them made the handed-off session differ from one
   opened by hand in ways that were all silent: `NO_COLOR=1` rendered it
   monochrome, `GIT_EDITOR=true` and `GIT_TERMINAL_PROMPT=0` left its git
   unable to open an editor or ask for credentials, and
   `CLAUDE_CODE_CHILD_SESSION` turned transcript saving off.
   `claude_console.login_environment()` calls Win32 `CreateEnvironmentBlock`
   instead, which is how Windows builds the environment for a newly launched
   process. **Do not add a var to a strip-list** — the list belongs to
   upstream and grows; rebuilding makes tomorrow's addition absent by
   construction. Nothing is added back on top either: with no
   `CLAUDE_CODE_CHILD_SESSION` to override, `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`
   is redundant, and setting it would be one more difference from a
   hand-started session.

9. **Typed text is bracketed, and waits for the prompt box.**
   `claude_console.console_input`
   writes into the spawned session's console input buffer, which accepts input
   long before Claude is ready to read it. Unbracketed, the newline between two
   tasks reads as Enter and sends the first one alone; unwaited, the text is
   answered into whatever dialog is on screen — a folder Claude has not been
   trusted in opens on a question whose default is Enter. Both failures are
   silent, and both are why `paste()` polls for `READY_MARKERS` first. It is
   allowed to give up: the same text is on the clipboard.

10. **Nothing this app opens may take focus.** Hand-off is triggered mid-thought
    and mid-sentence; a console that activates itself swallows the next
    keystrokes into a session you were not looking at. `spawn_claude` passes
    `unfocused_startup()` (`STARTF_USESHOWWINDOW` + `SW_SHOWNOACTIVATE`).
    Nothing needs the focus it would take — `claude_console.console_input` writes to the
    console's input buffer, which does not require an active window. Any
    future spawn gets the same treatment.

    **`SW_SHOWNOACTIVATE` is not enough on Windows 11, and CREATE_NO_WINDOW is
    the only reliable answer.** Windows 11 delegates every *new* console to
    whatever is set as the default terminal application. When that is Windows
    Terminal — the default on this machine — the console request is brokered
    (`svchost` → `OpenConsole.exe`) and **Windows Terminal creates the window
    itself**, so the spawner's `STARTUPINFO` never reaches it: a full,
    activated Terminal window opens regardless of `wShowWindow`. Measured
    2026-07-25 by spawning the same child three ways from a console-less
    parent: plain and `CREATE_NEW_CONSOLE + SW_SHOWNOACTIVATE` each opened a
    `CASCADIA_HOSTING_WINDOW_CLASS` window; `CREATE_NO_WINDOW` opened nothing.
    A console created with `CREATE_NO_WINDOW` is still a real console —
    `AttachConsole`, `WriteConsoleInput` and the screen buffer all work — so
    anything that only needs to *reach* a console should use it.
    `spawn_claude` is the deliberate exception: its window is the point.

    **For that one window, the answer is to launch through `conhost.exe`.**
    A console the tracker asks for by name is not delegated, so it is a
    classic console whatever the default terminal is, and `SW_SHOWNOACTIVATE`
    reaches it again. Measured 2026-07-26 with the default terminal set to
    Windows Terminal, from a console-less parent: spawning the command
    directly moved the foreground to `CASCADIA_HOSTING_WINDOW_CLASS` inside
    400 ms and kept it; the same command through `conhost.exe` left the
    foreground untouched for the whole run. This pins **only** the tracker's
    own window — the user's terminal choice for everything else is theirs, and
    the tracker no longer depends on what it happens to be, which is what
    broke the day the setting changed underneath it.

    The cost is one more hop: `Popen` now names the host, and `AttachConsole`
    refuses a host's pid, so `claude_console.session_pid` resolves conhost's child
    before anything is typed. Get that wrong and the rename, the colour, the
    prompt and the font all fail at once and all silently.

    **Asking is still not a guarantee, so the ask is checked.** Even through
    conhost, two spawns in ten took the foreground anyway (measured
    2026-07-26 over ten), apparently depending on how promptly whatever was in
    front was answering messages — a flake, which is worse than a rule,
    because it survives testing. `claude_console.hold_focus` records the foreground
    *before* the spawn and hands it back if this session's console turns out
    to be holding it. It hands back only to that window, only when the thief
    is this console, and only once inside 1.5 s: deliberately clicking the new
    session is a human gesture and keeps its focus — what gets reversed is
    focus nobody asked for.

11. **A suggested value is written once, into an untouched field.** The title
    suggested from a note's first line is filled when that note first becomes
    current and never again; one keystroke marks the box yours for the life of
    that note. Capture has no note to key off, so an identity-less open takes a
    fresh `Symbol` — which can never equal a previous or future
    `titleFilledFor`, so every capture starts blank instead of inheriting the
    last one's title. Both halves shipped as bugs first.

12. **Choosing a chip re-renders chips and nothing else.** `renderChips()`
    touches the three chip rows and nothing else, and every chip's `onclick`
    calls exactly that. The bug this replaced was a single render function that
    also rewrote the title, so picking a type after typing a title silently
    discarded it. Never route a chip click through a broader render.

13. **A body is written only when it changed — and "changed" is measured
    against the editor's own baseline, not the file.** Toast UI normalises
    markdown on every round-trip, so `setMarkdown(body)` then `getMarkdown()`
    can differ from what went in with nobody typing anything. Comparing against
    the loaded text would therefore report "changed" for every hand-written
    task and silently reformat prose no one touched. `openEditor` records
    `normalisedBody` — what this load's round-trip produced from the untouched
    content — and the save path omits `body` from the update entirely when the
    two match, so the file keeps its original bytes.

14. **Attachment paths come from the backend and are `file://` URLs.** The
    renderer never builds a path. `Api.save_attachment` returns `as_uri()`, not
    `as_posix()`: a bare `C:/repos/x/a.png` is not a URL — the leading `C:`
    parses as a *scheme*, so the browser never resolves it as a path and the
    image silently fails to load. The design spec called for the bare form and
    was wrong about this. The absolute form is also what lets a handed-off
    Claude session open the screenshot the body refers to.

15. **A group is its name.** There is no group id and no registry file, so a
    name must be non-empty and unique within a project, compared
    **case-insensitively** — otherwise "Editor polish" and "editor polish"
    quietly become two blocks the user reads as one. `groups.assign` joins
    *that exact* name and `groups.create` dedupes a *seed* into a fresh one;
    passing a seed to `assign` swallows the task into whatever group already
    answers to it. Renaming to a name another group holds, and merging two
    groups on spin-up, are both refused rather than guessed: a merge destroys
    one of the two names, and the name is the only identity a group has.

16. **A group lives in one bucket, and its members are contiguous in `order`.**
    Every membership change ends with `groups.renumber` on every bucket it
    touched — skip it and the group renders as two blocks with other rows
    wedged between them. The group header owns the bucket picker for the same
    reason; a member that could move on its own would render in two places at
    once. `Api.update_task` enforces both for anything that edits a single
    task: a bucket change on a member moves the whole group via
    `groups.set_bucket`, and an `order` aimed at a member is ignored. That
    lives in the bridge rather than in the editor so every writer inherits it,
    and it is skipped for a completed task, which keeps its `group` string in
    done/ but is not part of the group any more (invariant 15). The renderer is deliberately forgiving of a hand-edited file: a
    group's bucket and position come from its **lowest-order member**, and
    every member draws inside that block whatever its own `bucket:` line says.

17. **`session.json` is read-modify-write.** It holds `last_project` and the
    fold state, and it will hold the next piece of view state too. Replacing
    the file to set one key drops the others — `set_last_project` did exactly
    that, so a project switch would have silently unfolded everything. Go
    through `registry._update_session`.

18. **A folded block keeps its rows in the DOM; CSS hides them.** Three things
    read the rendered list rather than `state`: select-the-group ticks
    `.select` inside the container, `selectedIds()` collects checked rows
    document-wide, and the drag's drop handler builds the `ordered_ids` it
    hands `place_task` from the destination section's own
    `querySelectorAll('.task')`. Drop the rows and that last one hands the
    backend a bucket with a hole in it, leaving the folded members on stale
    `order` values that collide with the renumbered ones.

19. **`auto_group` runs after `launcher.hand_off`, never before.**
    `launcher.hand_off` saves the `Task` objects `Api.hand_off` handed it, so
    grouping first would rewrite those same files and leave those objects
    stale — the save would then silently discard the group. Going second also
    means a session that failed to start leaves nothing grouped, which is the
    same guarantee the spawn failure path already gives for `status` and
    `started`.
20. **Window geometry is only trusted if a monitor can show it.** While a
    window is minimized Windows parks it at a sentinel rectangle — measured
    here as -32000,-32000 at 237x39 — and that is what pywebview reports for
    `window.x/y/width/height`. Saving it is unrecoverable rather than merely
    wrong: the next launch opens somewhere the user cannot reach, so they
    cannot move it anywhere better, and closing re-saves the same value
    forever. The only exit is deleting a JSON file nobody knows exists.
    `window_state.on_screen` is therefore checked on **both** sides of the
    trip: `save` keeps the previous position instead of overwriting it with the
    sentinel, and `load` discards a rectangle that overlaps no screen, which is
    what repairs a `window.json` that is already poisoned. The load-side check
    also covers a window left on a monitor that has since been unplugged —
    different cause, identical symptom. Overlapping a screen by any amount
    passes, and a negative coordinate is normal, not suspicious: a monitor to
    the left of the primary starts at a negative x.

21. **The selected project is reconciled against the project list on every
    refresh.** `projects.json` is hand-editable and `refresh()` re-reads it, so
    the selection can go stale after it is made, not just before. When
    `currentProject` names a project that is no longer registered, no
    `<option>` matches and the browser silently selects the first one — the
    picker then shows one project while the list below renders another, which
    reads as the tasks having been lost. The check is the same one that
    restores `last_project` at launch; it just runs unconditionally rather than
    only when `currentProject` is unset.

22. **Commands are submitted before the prompt is typed.**
    `claude_console.console_input.deliver`
    calls `submit()` — which presses Enter — for every `/rename`/`/color` line
    first, and only then `paste()`s the prompt, which never presses Enter. Get
    the order backwards and a command's Enter would land on top of the
    still-unsubmitted task text, submitting the user's prose as a chat message
    instead of leaving it editable — silently breaking invariant 2. Ordered
    this way instead, a command that fails to submit costs only itself: the
    remaining commands are abandoned, but the prompt is attempted regardless,
    so a hand-off whose `/rename` was too slow to land still ends exactly
    where a hand-off without this feature always has — task text sitting
    editable in the box. Invariant 24 is what makes each of those writes
    actually land as its own event.

23. **`Task.color` is always one of the eight `CLAUDE_COLORS` — parsing repairs
    it, the bridge refuses to.** `Task.__post_init__` replaces a missing,
    empty, or hand-edited-into-garbage colour with `CLAUDE_COLORS[id % 8]`, so
    nothing downstream — the `/color` argument, the renderer's hex lookup —
    ever has to defend against a bad value. `Api.update_task` and
    `Api.create_task` do the opposite on purpose: an out-of-range colour there
    means the JS caller sent something wrong, not that a file was hand-edited,
    so they raise instead of silently repairing it — repairing it there would
    hide the bug that produced it.

24. **Nothing is written to a session's console until the prompt box shows the
    last thing that was.** Two writes a session reads in one pass are not two
    events to it. `WriteConsoleInput` only queues records; whether they arrive
    as one read depends on when the session next drains the buffer, which is
    the session's business and not the writer's. Measured against a live one:
    with the whole hand-off written back to back, a `\r` sitting between two
    bracketed pastes is read as *part of the paste* — `/rename …` and
    `/color green` merged onto a single line, both Enters vanished, and the
    task prose landed on the end of that line. So `submit` writes the line,
    waits for it to appear in `prompt_box`, writes `\r`, and waits for it to
    leave again. Only a wait on the screen proves anything: a `time.sleep`
    measures the writer, not the reader, which is why the 0.5 s
    `SETTLE_SECONDS` this replaced could not fix it — no constant can, since a
    session busy with its own startup reads when it reads. (The condition-based
    version is also *faster*: 0.42 s for two commands and a prompt, against
    1.0 s of unconditional sleeping.) A command that times out has its text
    still sitting in the box, so `deliver` calls `clear` before pasting the
    prompt onto it — **Ctrl+U**, the one keystroke measured to empty the box.
    Escape, the obvious guess, does nothing to a typed line at all.

25. **The spawned console is put on a font that has the glyphs Claude Code
    paints.** Pinning the host (invariant 10) means the tracker's window is
    always a classic console, and conhost's renderer font-links *some* missing
    glyphs but not the quadrant block elements `U+2596`–`U+259F` — which is
    exactly what Claude Code's logo is drawn from, and Consolas (what
    `__DefaultTTFont__` resolves to) has none of them. So the session opened
    on a row of boxes with the code point printed inside.
    `claude_console.console_input.use_font` puts the console on **Cascadia Mono**, which
    ships with Windows 11 and has all eight, using the attach the module
    already performs — no registry, nothing machine-wide, and the size stays
    whatever the console had. It reads the face back and reverts if it did not
    take: an unknown face is not refused, conhost just picks something of its
    own, which on a machine without this font would be a downgrade rather than
    a fix. Setting it late is fine — the console repaints its whole buffer —
    so it runs first in `deliver`, before the wait for a prompt box, which is
    also why a hand-off with nothing selected still starts that thread.

    Two things were measured and did **not** work, so nobody spends the
    afternoon again: `HKCU\Console\UseDx` at 1 and 2 (conhost's DirectWrite
    renderer) changed the rendering not at all, and `⎿` (`U+23BF`, the
    tool-result elbow, on every tool call) still draws as a box — under
    Consolas too, so the font change costs nothing there. No monospace font on
    the machine has both that and the quadrants; Windows Terminal renders it
    only because it falls back per glyph, and a WT-hosted window is the one
    thing invariant 10 rules out. If the elbow ever matters enough, the lever
    is a wider-coverage font, not a different host.

26. **A drop resolves to one destination, applied by one call.** A drag can
    change a task's bucket, its group and whether it is running, all in one
    gesture — and the states between those three changes are ones no rule
    permits. A task that has changed bucket but not yet left its group is a
    member sitting in the wrong bucket, which is invariant 16 broken; a
    sequence of `update_task` → `group_tasks` → `reorder_bucket` passes
    through that state on disk every time, and leaves it there if any step
    raises. `groups.place` applies the triple `{bucket, group, status}` with
    one write per task and renumbers **both** the source and destination
    buckets, so the intermediate state never exists. `Api.place_task` and
    `Api.place_group` are its only callers.

    Two rules inside it that a reader cannot infer. **An explicit bucket beats
    the group's**, which is what lets a group header dragged into `next` carry
    every member while a lone task dropped into that same group is instead
    pulled into the group's bucket — without the precedence, one of those two
    has to become a special case somewhere else. And **status is written only
    when it differs**: `store.reset_to_open` clears `started`, so releasing a
    half-running group would otherwise erase the start dates of the members
    that were never running. A task already in the destination group *and*
    bucket also keeps its `order`, or claiming one member would shunt it to
    the end of its own group.

27. **`wireDrag` binds once, at load, to `#task-list`.** It was one controller
    per section until 2026-07-26, each closing over its own `dragged`, and
    that is exactly why no drop ever crossed a section: `dragstart` fired on
    the SOURCE section's listener while the `dragover`/`drop` that followed
    fired on the DESTINATION section's, where `dragged` was still `null`.
    `event.preventDefault()` runs before that guard, so the browser showed a
    drop cursor the whole way and the gesture looked legal while doing nothing
    at all — a silent failure that survived months of use.

    `#task-list` is the common ancestor of every section and is never itself
    replaced (`render()` calls `replaceChildren` on it), so one listener there
    survives every redraw and cannot stack duplicates. Never call `wireDrag`
    from a render function. The destination section is resolved at event time
    from `event.target.closest('section[data-bucket], #in-progress')`, and a
    section with no `data-bucket` is IN PROGRESS: it implies `in-progress`
    status and cannot reorder, a bucket section implies `open` and can. That
    one substitution is the whole of claiming and releasing — neither is a
    special case anywhere in the handler.

    **A drag that reorders live must handle the pointer landing on the row it
    is dragging.** `dropIntent` refuses a drop whose target is the dragged row
    itself — an unchanged guard from when the only gesture was reordering — but
    the live `insertBefore` slides that row *under the cursor*, so the next
    `dragover` resolves to it and `intent` goes null. Release there and `drop`
    returns before calling anything: the row is visibly in its new section and
    nothing was written, so the next render silently puts it back. This shipped
    on 2026-07-26 and reads exactly like a backend failure — the tests for the
    placement it never reached were green the whole time. The fix is that the
    row already being in its destination IS the drop: commit where it sits,
    with no `over` to insert against. Any future gesture that moves the dragged
    element during `dragover` inherits this.

    **The preview is a lie until something writes it, so a gesture that writes
    nothing takes it back.** `dragover`'s `insertBefore` is a REAL DOM move, and
    for months nothing ever undid it: release outside `#task-list` — the header,
    the selection bar, past the window edge — or press Escape, and only
    `dragend` fires, which cleared the outline and left the row sitting in its
    new place. Same for a `drop` whose `intent` is null, and for one whose
    `callApi` failed. The list then showed a position nobody saved for as long
    as it took something else to force a render, and the next rename or edit put
    it back — which reads as *that* edit having reset the task's position, and
    is what this was reported as (2026-07-26). Measured before and after in a
    headless copy of the real renderer: pre-fix, a `dragstart` + `dragover` +
    `dragend` with no drop left `[2,3,1]` on screen with zero bridge calls.
    `wireDrag` now records where the block was picked up, `dragend` restores it
    unless `drop` claimed the gesture first (`wrote`), and every failure path
    inside `drop` calls `refresh()` — a redraw is the only thing that can be
    right once a write may have half-landed. **`wrote` must be set before
    `drop`'s first `await`**: `dragend` fires immediately after drop's
    synchronous part, and it is the only thing that can tell an abandoned drag
    from a claimed one. **And `inProgressOrderFromDom` must keep being read
    while the preview is still in place** — it runs after an await, so it
    depends on dragend having left the DOM alone.

28. **Where a drop lands is read from geometry, not from `event.target`.** Two
    rectangles decide everything, and they are the two the user can see. Every
    **section** is a box: anywhere inside it means "this category", at the slot
    nearest the cursor. Every **group** is a nested box inside one: anywhere
    inside it means "and in this group". Padding, headings, the gaps between
    blocks and the empty line are all inside the rectangle they look like they
    are inside, which an element-based rule could not say — the padding of a
    box belongs to the box on screen and to nothing at all in the DOM, so every
    one of those was a dead strip where a drop silently did nothing.

    This replaced a set of aimed targets: a heading meant "leave your group", a
    group header meant "join", and the region between blocks meant nothing on
    purpose, because releasing there might dissolve the grouping being
    rearranged. That caution is answered by the geometry rather than by
    refusing: inside the group's box you stay in it, outside it you leave, and
    both are visible before you let go. **Leaving a group therefore has no
    target of its own any more**, and neither does joining one.

    Three consequences worth keeping:

    - **Grouping is aimed, reordering is not.** Reorganising is the common
      gesture, so it is what everything defaults to; making a new group needs
      the cursor inside a band a third of a row tall, inset from both ends
      (`PAIR_BAND`, `PAIR_INSET`). It used to be an even split — the middle
      half of a row grouped — which made the rarer and more surprising outcome
      exactly as easy to hit as the common one.
    - **A group keeps `GROUP_STICKY` pixels of grip on its own member.**
      Without it, sorting inside a group and overshooting the last row by one
      pixel throws the row out of the group. Leaving still costs one deliberate
      drag clear of the box; only the twitch is absorbed.
    - **Every measurement excludes the dragged element, and `slotFor`
      discounts its height.** The element stays in the flow during an HTML5
      drag, so the live preview displaces every block below it — feed that back
      in and the preview chooses its own next position, and the row flips
      between two slots while the cursor holds still.
    - **A section owns exactly its own rectangle, and the margin between two
      belongs to the one BELOW.** `sectionUnder` used to take the *nearest*,
      which splits a margin down the middle and let a bordered box go on
      claiming about ten pixels past the edge it draws — and a drawn border
      reads as a hard edge, so a drop caught beyond it looks like the cursor
      being misread. The exception is the space past the last section, which is
      most of the window and belongs to it rather than to nothing.
    - **It is measured, never hit-tested.** `event.target.closest` answers with
      whatever element is under the pointer, and the dragged row is still in
      the flow — so it can name the section the row came FROM while the cursor
      is over a different one.

    **A box is drawn for the container the drop moves the task INTO, and only
    when that is not the container it is already in.** One rule, and everything
    else falls out of it. A task's container is its group if it is in one, else
    its section — captured at `dragstart`, because the preview moves the
    element and asking later answers with wherever the last `dragover` put it.

    - Repositioning inside NOW draws no NOW box; sorting inside a group draws
      no group box. The preview row alone carries those, and it is the only
      news there — a box around where something already lives says nothing and
      competes with the position for attention.
    - Carrying a row out of its group into the same section's open space lights
      up NOW, because the group is what it was in and the section is what it is
      joining.
    - Nothing at all is drawn until the cursor leaves the box the task started
      in. That is not a separate rule; it is the same one.
    - There is no "you are leaving" look, because leaving is just entering
      something else. The row stepping out of the group's rail shows it.

    Pairing is the one exception: a new group has no container to enter yet, so
    the row it would pair with is always outlined.

    NOW, NEXT and SOMEDAY have no border of their own, so `.drop-zone` is the
    only time they are boxes at all. Its outline is inset (`outline-offset` is
    negative): a section is full width, and an outline drawn outside it reaches
    past the window and can add a horizontal scrollbar.

    **Exactly two elements ever carry `.drop-into`** — a `.task` being paired
    with, and a `.group` being joined — and the stylesheet names exactly those
    two. It used to name `.group-header` and three headings as well; the
    geometry rewrite moved the affordance to the whole container and left the
    old selectors behind, so joining a group drew nothing at all while the rule
    still looked populated. **A stale selector is invisible in both
    directions**, and no text-based test can see it:
    `test_every_class_the_ui_toggles_is_styled` passes on that file, because
    `.drop-into` is a substring of `.group-header.drop-into`. Keep the list
    minimal so a wrong one is obvious by reading.

    **IN PROGRESS is a bucket section with one difference, and adding a second
    one is a bug.** Every part of this — which box owns the cursor, the group
    boxes inside it, the slot nearest the cursor, the pair band, the outlines,
    the preview, reordering — is the same code reached the same way. The single
    difference is **where the order it writes is kept**: `sectionPlacement`
    reports `orders: 'bucket'` or `orders: 'wip'`, and that one word is the
    whole of it.

    It costs one function to hold that line, because IN PROGRESS keeps its
    blocks a level down inside a wrapper per project while a bucket section
    holds them directly. A bucket's `holder` is the section itself, so its
    heading and padding are inside it and a drop there lands at the top; IN
    PROGRESS's is the project wrapper, so the section's own heading, its 8px
    frame and the space below the last project were outside every wrapper and
    resolved to "claim a task that is already claimed" — a no-op, which is a
    refusal. Dragging a running task *up to the top of the list* overshoots into
    exactly that strip, so the commonest reorder there previewed as moved and
    wrote nothing. `ownRunningList` gives an already-running row its own
    project's wrapper whenever the cursor is inside the section but inside no
    wrapper at all, which restores the bucket behaviour verbatim. Two things
    deliberately still fall through to the claim: a cursor over ANOTHER
    project's wrapper, which is a box of its own and stays refused, and a task
    being claimed for the first time, which has no place in the list to position
    within and still lands at the end.

    A bucket's order is `Task.order`, in the task files. IN PROGRESS's cannot
    be, and that is not a shortcut — `order` is a *per-bucket* position, so two
    running tasks in different buckets both hold 0 legitimately and no sequence
    across them is expressible; `groups.renumber` restarts each bucket at 0 by
    design, so it would undo one on the next write anyway. It is also not the
    task files' business: the order of what is on screen right now is view
    state, so it lives in `session.json` beside the fold state (invariant 17
    said this file would hold the next piece of view state, and this is it),
    and reordering the running list therefore makes no diff in a tracked repo.

    That list ranks **blocks**, not rows — a group is one entry. Inside a
    group, the member order is the group's own and is the same list the bucket
    view draws, so it stays in the tasks and `reorder_group` stays the thing
    that changes it. The two views can then never disagree about it.

    This difference used to be `canReorder: false`, which suppressed the
    top-level position entirely — dragging within IN PROGRESS could only form
    groups, and reordering the running list was impossible. That read as the
    section being half-built rather than as a constraint, which is what a
    second difference always reads as.

    Anything else that behaves differently between the two is a defect, not a
    design. It has already happened twice — the section box existed only for IN
    PROGRESS, then existed for both in the JS while a broken CSS comment
    deleted the bucket rule — and both times it read as a missing feature
    rather than as a bug, because the elevated section looked deliberate.
    A new drag behaviour lands in both or in neither.

## Data on disk

```
~/.task-tracker/projects.json   name -> path, tracked flag, launch override
~/.task-tracker/settings.json   group_limit (5), stale_days (90), task types
~/.task-tracker/session.json    last_project, which groups/projects are folded,
                                and the order of the IN PROGRESS list
~/.task-tracker/inbox/          untriaged raw notes
~/.task-tracker/session.json    last_project — restored on every launch
~/.task-tracker/window.json     window geometry
<project>/.tasks/.gitignore     contains `*` — the folder is invisible to git
<project>/.tasks/open/          NNNN-slug.md
<project>/.tasks/done/          the archive, and the progress view's source
<project>/.tasks/attachments/   pasted screenshots, YYYY-MM-DD-HHMMSS.png
```

A task file's frontmatter carries `id`, `title`, `type`, `color`, `bucket`,
`group`, `status`, `order`, `created`, `started`, `done` — `render_task`'s
`meta` dict is the single source of that key order, and `parse_task` is the
only reader of it.

`.tasks/` is **untracked by default** because several tracked repos are public
and committing would publish raw backlog prose. A per-project `tracked` flag
flips it (settings → the tracked checkboxes), which deletes that `.gitignore`.
Attachments live under the same `.gitignore` on the same terms, which is why
`store.save_attachment` calls `ensure_tasks_dir` before writing: creating the
directory tree without that file would publish a pasted screenshot on the next
commit.

Attachments are **never garbage-collected** — deleting a task leaves its images
behind. Reference counting across hand-editable files is not worth the
machinery here. Their absolute paths also make a task file **non-portable**
between machines, which only matters for a tracked project cloned elsewhere:
the images arrive, the paths do not resolve.

`store.next_task_id` is `max(ids, default=0) + 1` over open and done combined.
Before the selection bar, nothing ever removed a task, so ids only went up for
a project's whole life. `delete_tasks` unlinks files outright, so deleting the
newest task frees its id — the next task created can land on the same number.
Nothing breaks (ids are still unique among live tasks, and only ever meaningful
paired with a project — invariant 6), but a tracked repo's git history can now
show two unrelated tasks under one id at different points in time.

## Adding a feature

- **New bridge method:** add it to `Api` in `app.py` (translate JS args → backend
  call → JSON-safe return; run `Task` objects through `_task_dict`, which strips
  the non-serialisable `Path`), then call it from JS via `callApi`.
- **New UI surface:** put it in whichever of the seven scripts owns that concern;
  add its `<script>` tag only if you create a new file.
- **Anything that edits a task** goes through `openEditor()` in `ui/editor.js`
  rather than a new overlay. It is one component with three entry points —
  capture, triage, and clicking a row — precisely so the no-clobber rules
  (invariants 11–13) hold in all three rather than being reimplemented and
  half-forgotten in each.
- **Never add a CDN reference.** The editor is vendored so the app works
  offline; a convention test enforces it.
- **Extend a CSS comment BEFORE its closing `*/`, never after.** Prose written
  after the marker is not a comment: CSS reads from there to the next `{` as
  one selector, fails to parse it, and **silently discards the entire rule that
  follows**. That deleted `section.drop-zone` on 2026-07-26 — the JS added the
  class, the rule sat in the file looking correct in the diff, and no bucket
  section ever drew its drop box. It happened twice the same day.
  `test_the_stylesheet_has_no_stray_comment_markers` now fails the build on an
  unbalanced marker in either direction.
- **Tests:** `store.py`, `registry.py`, `inbox.py`, `migrate.py`, `launcher.py`,
  `groups.py` and `Api` methods are all directly testable. Use `tmp_path` and the
  `monkeypatch.setattr(registry, "CONFIG_DIR", ...)` fixture pattern from
  `tests/test_registry.py`. Mock at the boundary — `claude_console.open_session`
  and `launcher.pyperclip.copy` — never spawn a real process. `open_session` is
  the seam for anything touching a hand-off; `test_launcher.py` stubbed
  `subprocess.Popen` before the extraction, which meant every task-shaped
  assertion also carried Win32 scaffolding it had no opinion about.
  **No test here opens a console at all any more**, and
  `test_nothing_in_this_repo_may_open_a_console_window` has an empty allowlist
  saying so. The one test that genuinely does — typing into another process's
  console is OS behaviour, and a mock of it would only assert that the mock was
  called — moved to `claude-console` along with its windowless probe and the
  guard that keeps it windowless. The suite runs while someone else is at the
  keyboard: **no test may put anything on screen.**
- **Deliberately untested:** `main()`, window geometry persistence, and the
  `import claude_console` guard at the top of `app.py`. Driving a native window
  under pytest is not worth the machinery; this is a decision, not an oversight.
  The import guard is the same call in a different disguise — exercising it
  means letting a `MessageBoxW` reach the screen, which is the one thing the
  suite may never do.
- **No JS test runner, and the by-hand checks have no agent to run them.**
  Claude must never run `app.py` — it opens a window on the user's desktop and
  writes to their real `~/.task-tracker/` — so "checked by running the app"
  means *the user* runs it. A UI task therefore cannot be signed off from its
  diff, and reading the diff is not a weaker version of the check, it is a
  different thing that cannot see the same class of defect.
  This cost a Critical on 2026-07-26. Three UI tasks were marked "review clean"
  on the strength of their diffs; the editor was opening *behind* the Progress
  overlay the whole time — no `z-index` existed anywhere in `ui/style.css`, and
  two full-screen opaque overlays paint in DOM order. The restore feature was
  completely unreachable in the running app, and the four by-hand checks that
  would have caught it in one second were written into the list below as though
  they had been performed. Hand the checks to the user when the UI task lands,
  not at the end of the plan.
- Frontend changes are checked by running the app. Two
  editor behaviours are worth checking by hand every time `ui/editor.js` is
  touched, because both are silent when broken: type a title then click a
  different type chip (the title must not change), and edit *only* a task's
  bucket in a tracked project then run `git status` (the `.md` file must show a
  frontmatter change and **no body diff**). In `ui/tasks.js`, check that
  hovering a row does not shift the title sideways (the hover-revealed controls
  must use `opacity`, never `display`) and that clicking the copy button does
  not also open the editor. Five for inline rename, which splits one row
  between two gestures: double-click a task's title — it becomes a box, Enter
  commits and Escape puts the old title back; single-click that same title must
  do **nothing**, while the dot, the type tag and the space after a short title
  all still open the editor; dragging a row by its title must still work;
  rename a row in the **search** view, where a title is drawn as `project ·
  title` — the box must contain the bare title, or the decoration gets saved as
  the name; and rename in a tracked project, then `git status` — a frontmatter
  change and **no body diff**. In `ui/selection.js`, check that ticking a group
  header's select-all box updates the bar's count (assigning `.checked` on the
  member rows does not fire a `change` event, so the count silently goes stale
  without the explicit call this depends on) and that `Clear` empties the
  header box along with every row's — a header left ticked with no members
  ticked reads as a broken render. Fold a group, tick the group's checkbox, and hit
  Spin up: the folded members must still go to the session. Four more for the
  bar's own position, which is a floating overlay rather than a row: tick a box
  and **nothing above it may move** — the list must stay exactly where it was
  while the bar slides up from the bottom edge, and untick must slide it back
  down rather than blink it away. Scroll a list long enough to scroll all the
  way to the bottom with two tasks ticked (which shows the taller two-row bar):
  the last task must still be readable above the bar. Tick a task, then open
  Progress or the editor: the bar must be **behind** the overlay, not floating
  on top of it. And clear the last tick: the count must not flash `0 selected`
  on its way out. In `ui/groups.js`,
  four more: drop a grouped row on a bucket's heading, or on a project heading
  in IN PROGRESS, and it must leave its group — that heading is the only
  drag-out target, because the gaps a reorder crosses are not aimable and
  releasing in one must never dissolve a grouping by accident. And three more:
  drag a task onto the
  middle of another and the new group's name box must open focused with its
  seeded text selected; drag a third onto that group and it must **not** reopen
  (invariant 11); and after moving a group between buckets, `git status` in a
  tracked project must show a frontmatter change and **no body diff** on every
  member. For the header, select a project that is not the first and press ↻:
  the window must come back on *that* project, at the same size and position,
  and `run.bat` must restore it too — the selection is restored on every launch,
  not just the button's. Narrow the window and the picker must shrink rather
  than pushing ⚙ off the row. For the group block's `done` button and the
  tree's type scale: a group of 2 → `done` completes both with no prompt and
  the block disappears; a group of 5 → `done` asks first, and Cancel leaves
  all five untouched; in IN PROGRESS, a header reading `2 of 5` → `done`
  completes those 2 while the other 3 stay in their bucket and the group
  survives; a group header's checkbox must line up exactly with a top-level
  task row's; dragging a group by its header must still work, and pressing
  `done` must not start a drag. Renaming is a **double-click on the name
  itself**: a single click anywhere on the header — including the empty stretch
  between the name and the count, which used to be part of the name's own box —
  must start a drag instead. And a group born from a drag must still open its
  name box focused, which no longer goes through a synthesised click. And for restore: open a completed task from
  Progress and close without changing anything — `git status` in a tracked
  project shows no diff at all; edit its body and save — the change lands and
  the file stays in `done/`; press Restore — it leaves the progress list and
  reappears at the bottom of its original bucket; and the editor's Restore
  action is absent when editing an open task.

  For the settings panel, five — every one of them silent when broken, which is
  why they are written down rather than trusted to be noticed. Add a type, then
  rename or delete a *different* one: the row you added must still be there
  afterwards (`refresh()` replaces `state`, and the pending row used to live in
  it). Add a type, press Close, reopen settings and press Save: it must **not**
  be created. Add a type, pick a colour for it, then delete another pending
  row: the colour must survive the re-render. Delete a type no task uses: it
  must ask first. And empty the Group limit box and press Save: it must refuse
  rather than store a 0 that every reader then treats as 5. For the tracked
  checkboxes, the failure path is the one worth seeing: delete a project's
  `.tasks/` folder outside the app, then tick its box — the alert appears
  *and* the box goes back to where it was, because a box left ticked over an
  untracked project is the claim you would act on right before committing.

  And Escape, in all three overlays: it must close the editor, the settings
  panel and the progress view. Open a completed task from Progress so the
  editor sits on top of it, then press Escape once — the editor must close and
  Progress must still be there.

  For drag recategorization, ten — the whole feature is gesture, so none of it
  can be seen in a diff. Drag a loose task from `someday` onto a group inside
  `now`: it joins and moves to `now`. Drag it back out onto the `SOMEDAY`
  heading: it leaves the group and lands in `someday`. Drag a task into IN
  PROGRESS: it turns in-progress and **no Claude window opens**. Drag it from
  there onto `NEXT`: it resets and lands in `next`. With nothing running at
  all, the IN PROGRESS box still shows its line and still takes a drop. Drag a
  group header between buckets: every member moves, and `git status` in a
  tracked project shows frontmatter changes and **no body diff**. Drag a
  running group back to a bucket: every member resets, including any that were
  not running. Fold a group and drag a task into it: the folded members keep
  their order (invariant 18). Drop a row on *another* project's heading in IN
  PROGRESS: refused, with no outline at all. And the gestures that already
  existed must be untouched — reorder within one bucket, pair two rows into a
  new group whose name box opens focused, and rename it.

  And four for reordering IN PROGRESS, which is view state rather than task
  data and so has a different set of ways to be wrong. Drag a running task up
  or down its project's list: it must preview as it moves and stay where it was
  dropped. Do that in a tracked project and run `git status`: there must be
  **no diff at all** — nothing about the task changed, only what session.json
  remembers. Press ↻: the order must survive the restart. And claim a new task
  into IN PROGRESS: it must land at the END of that project's list, never
  silently in the middle of it.

  And five for the preview never outliving the gesture that drew it — the whole
  set is "nothing on screen may claim a place that was not written", and every
  one of them is silent, because a row left in the wrong place looks exactly
  like a row that moved. Start dragging a task, carry it a few rows, and let go
  **outside the list** — on the header, on the Spin up button, past the window
  edge: it must snap back where it started, not sit in its new place. Same drag,
  cancelled with **Escape** mid-drag: same. Both again in IN PROGRESS, which is
  where this was noticed. Then the confirmation that the snap-back is not
  overzealous: reorder a bucket properly and the row must STAY where it was
  dropped, with no flicker back to its old slot on the way. And the strip this
  opened up — drag a running task onto **the IN PROGRESS heading itself**, or
  into the padding around the box: it must land at the top of its own project's
  list and survive a ↻, rather than looking moved and reverting on the next
  edit. Dropping on ANOTHER project's rows is still refused, and must still
  leave the dragged row where it started.

  Two of those ten failed on first use and are the ones worth repeating after
  any change to `wireDrag`, because both looked like they had worked. Drop a
  task anywhere in the IN PROGRESS box — the padding beside the heading, the
  blank strip around the line, not only on the text — and the whole box must
  outline. And drag a running task into the *middle* of a bucket rather than
  onto its heading, then fold something to force a re-render: the task must
  still be where you put it. It moved on screen and was never written, which
  no amount of reading the diff would have shown.

  Six more for the geometry (invariant 28), which has no aimed targets left to
  lean on. Hold the cursor still on a seam between two rows: the preview must
  settle on one slot and stay there, not flicker between two. Drag slowly down
  a bucket that contains a group — the row must step into the group's rail
  while inside its box and back out below it, and where it is drawn is where it
  must land. Sort a row inside a group and overshoot the last member by a
  pixel: it must stay in the group. Drag it a clear centimetre below the group:
  it must leave. Drop on a bucket's `NOW`/`NEXT`/`SOMEDAY` heading: it must
  land at the top of that bucket, ungrouped, since a heading is now just the
  top of the box. And drag a row over another row's *edge* rather than its
  centre — it must reorder, never group; grouping must need the middle third.

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
- **Each worktree needs its own `.venv`** (`uv venv --python 3.12 .venv`, then
  `uv pip install --python ".venv\Scripts\python.exe" -e . pytest`). There is
  no shared one. That one command covers `claude-console` too: it is a declared
  dependency with a `[tool.uv.sources]` path entry, so `-e .` resolves it —
  **verified**, including from a worktree, which is why that path is absolute.
  A relative one cannot serve both this checkout and a worktree four levels
  under it, since the same `pyproject.toml` is checked out into both.
- **Run the suite from the worktree root**, always with a relative path:
  `Set-Location <worktree>; & ".venv\Scripts\python.exe" -m pytest tests/ -q`.
  Pointing pytest at another checkout's `tests/` imports *this* tree's modules
  against *that* tree's tests and reports a wall of assertion failures that
  reads exactly like the branch being broken.

Three things went wrong on 2026-07-25, building three features in parallel.
Each is cheap to avoid and expensive to diagnose:

1. **The primary checkout drifted onto a feature branch.** `run.bat` then
   launched an app built from files that did not contain the feature under
   test, for an hour, while `main` had it the whole time. If the app behaves
   as though a merged feature is absent, check `git rev-parse --abbrev-ref
   HEAD` in the folder you launched from *before* debugging the feature.
2. **A worktree follows its branch's ref; its files do not.** A merge worktree
   created at one commit had HEAD resolving to a newer one minutes later,
   because a sibling advanced the branch — while its working files were still
   the old ones. `git log --oneline -1` immediately before merging.
3. **Renames cross branches badly.** A branch cut before `#wip-warning` became
   `#group-limit-warning` carried a call to a function that no longer existed.
   There is no JS test runner here, so nothing failed — it would simply have
   thrown at runtime. After merging any UI branch, grep for the old name and
   run `node --check ui/*.js`.

## Known gaps

Three spec behaviours were never implemented, and the deferred findings from the
whole-branch review are filed as tasks in this repo's own `.tasks/open/` — open
the tracker, select this project, and they are the backlog. Highlights:

- Cross-project rows do not switch the project picker to the row's project.
  They do open the editor, which is project-safe (invariant 6). **Decided, not
  deferred** (2026-07-26): the spec's jump-to-project predates the editor being
  able to open a foreign row at all, and building it now would mean *removing*
  editing from that view to make room for a click that does less. If both are
  ever wanted they need two distinct targets on the row, not one click doing
  whichever seems more useful.
- The editor cannot **create** a group, only join one that exists or leave the
  one it is in. Creating stays the drag gesture, so there is one set of naming
  rules rather than two.
- Triage chips are mouse-only; the spec called for single-key assignment. **Not
  a gap to close as specified** — triage now runs through the shared editor,
  where the body holds focus and typing goes into prose, so bare `b`/`f`/`i`
  keys would collide with writing. It needs a modifier scheme or a focus rule,
  which is a design decision nobody has made.
- No control *writes* `## Outcome` — but one is no longer needed to get one.
  Clicking a completed entry in the progress view opens it in the editor
  (`renderProgress`, `ui/settings.js`), so the heading can be typed into the
  body there and the view renders it on the next open. What is missing is
  discoverability, not the path. The spec's answer — prompt for a one-liner
  when marking a task done — was **considered and declined on 2026-07-26**: it
  puts a dialog in front of the most common action in the app to serve the
  rarest one. If this is ever picked up, the shape to build is a field in the
  editor for a done task, beside Restore.
- **Restore is singular.** `store.restore_task` and `Api.restore_task` mirror
  `complete_task` exactly, one task at a time; nothing restores a whole batch
  out of `done/` the way the selection bar and a group header complete one.
- **Two groups can never be merged**, by drag or on spin-up — both paths refuse
  rather than guess which name survives. If that becomes wanted it needs an
  explicit gesture with an explicit choice.
- **Groups are one level deep** and never span projects.
- **IN PROGRESS reorders, but its order is not the tasks'.** It ranks blocks in
  `session.json` (see invariant 28), because `Task.order` is a per-bucket
  position and running tasks can sit in three different buckets. The
  consequence worth knowing: that order is view state, so it is per-machine and
  invisible to git, unlike every other thing a drag changes.
- **A group header drag moves every member**, including any the header did not
  draw — a header in IN PROGRESS can read `2 of 5`. A group lives in one
  bucket (invariant 16), so there is no such thing as moving part of one. This
  deliberately differs from the `done` button beside it, which acts on the
  rows it drew.
- **Dragging into IN PROGRESS does not spawn a session.** It flips the status
  and nothing else. The ↩ on every running row is exactly the inverse, so the
  two read as one control, and a drag is far too easy to misfire for a gesture
  that opens a console and types into it.
- Done tasks keep their `group`, but nothing renders it: the progress view
  still lists completed tasks flat.

Session identity (naming and colouring a handed-off window, see
`docs/superpowers/specs/2026-07-25-session-identity-design.md`) **was verified
against a live session on 2026-07-25** — the gap that used to sit here is gone.
A bracketed `/rename` and `/color` are read as commands, not as chat text; the
`\r` written after them is read as Enter; and the prompt is left editable
afterwards. What that verification *found* is invariant 24: the failure was
never in how the line is written, it was in writing the next thing before the
session had read the last one. It ships with one gap of its own:

- **`#handoff-name` is a placeholder for a component that does not exist yet.**
  When the selection-bar design
  (`docs/superpowers/specs/2026-07-25-selection-bar-design.md`) lands, this row
  moves into `#selection-bar` as a second line and `#handoff-name` disappears,
  and `Api._selected_tasks` collapses into that design's planned `Api._tasks`
  — the two do the same id-to-task lookup under names chosen only to keep them
  from colliding before that merge happens.

Design specs: `docs/superpowers/specs/2026-07-25-task-tracker-design.md`,
`docs/superpowers/specs/2026-07-25-task-editor-design.md`,
`docs/superpowers/specs/2026-07-25-task-groups-design.md`
Implementation plans: `docs/superpowers/plans/2026-07-25-task-tracker.md`,
`docs/superpowers/plans/2026-07-25-task-editor.md`,
`docs/superpowers/plans/2026-07-25-task-groups.md`

**The specs and plans are historical records, not current documentation — the
code and these invariants are.** Seven things in them are known-wrong and were
corrected during implementation. `2026-07-25-selection-bar-design.md:137` says
"The bar needs `#selection-bar[hidden] { display: none }`", and its plan
(`2026-07-25-selection-bar.md:392`) lays the bar out in the flow with a
`margin-bottom`. Both describe the bug: in the flow the bar shoved every task
down as it appeared, and `display: none` cannot animate. The bar is now
`position: fixed` against the bottom edge and its `[hidden]` rule deliberately
keeps `display: flex` — copying either line back is the way to reintroduce the
jump and kill the slide at once. `2026-07-26-drag-recategorization-design.md`
says under "Deliberately not in scope" that **IN PROGRESS still never
reorders** — it does, and the design of how is invariant 28, not that file:
the section learned to reorder the same day, once its order moved to
`session.json` where a per-bucket `Task.order` could not express it. `2026-07-25-restore-and-group-block.md:169`
still shows `task.order = len(siblings)` for a restored task; that is only "the
end" of a contiguous run, and `Api.complete_task` does not renumber, so it
hands a restored task an order another task already holds. The code uses
`max(order) + 1` plus a `groups.renumber`. The other four: `file_note` had no way to receive an edited
body (so triage silently discarded prose edits); image references were
specified as bare `C:/...` paths and `as_posix()`, which are not URLs and never
render; the tracker spec still describes the strip-list environment that
`claude_console.environment` replaced; and its console-probe snippet
(`2026-07-25-task-tracker-design.md:224`) still reads
`creationflags=subprocess.CREATE_NEW_CONSOLE`, which opens a Windows Terminal
window on every test run — copying that line back in is the one way to
reintroduce the flash, and two tests now fail the build if anything does:
`test_nothing_in_this_repo_may_open_a_console_window` here, and
`test_nothing_but_the_session_itself_may_open_a_console_window` in
`claude-console`, which is where the probe now lives. Invariants 8, 13 and 14
are the record of what the code actually does.

Those specs also predate the extraction: everything they say about spawning a
console, typing into it, or rebuilding an environment now describes
`claude_console`, not a file in this repo.
