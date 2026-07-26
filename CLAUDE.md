# Task Tracker — working notes for Claude

A single always-on-top window over markdown task files that live inside each
tracked project's own repo. It replaces a notepad, not Jira. Every design call
below was made deliberately; the ones marked **invariant** were each learned by
shipping the bug first.

## Run and test

```powershell
run.bat                                          # launch (creates venv on first run)
& ".venv\Scripts\python.exe" -m pytest tests/ -q # 179 tests
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

Twelve small Python modules and seven plain `<script>` files, plus one vendored
library. No framework, no HTTP server, no bundler.

| File | Owns |
|---|---|
| `store.py` | Task dataclass, markdown+frontmatter round-trip, `.tasks/` layout, CRUD |
| `registry.py` | `~/.task-tracker/projects.json`, `settings.json` and `session.json` |
| `inbox.py` | Raw untriaged notes in `~/.task-tracker/inbox/` |
| `migrate.py` | Type rename/delete sweep across every project |
| `groups.py` | Group membership: assign/create/rename/disband/move, reorder-within-a-group, the bucket renumber, and the spin-up rule. A group **is** its name — no ids, no registry |
| `launcher.py` | Verbatim prompt assembly, clipboard, Claude process spawn. `build_prompt` is the single source of the `TYPE: body` format — both hand-off and the per-row copy button go through it, so the two can never drift |
| `console_input.py` | Typing that prompt into the spawned session's console |
| `user_environment.py` | The environment Windows gives a freshly launched process |
| `singleton.py` | Single-instance lock on `127.0.0.1:8090`, with handover |
| `restart.py` | Spawning a replacement instance. Closes nothing itself — the replacement's `singleton.acquire()` does that, which is what saves the geometry |
| `window_state.py` | `window.json`, and the rule that geometry is only worth keeping if a monitor can show it |
| `app.py` | pywebview window + the `Api` bridge class. **Wiring only** |
| `ui/state.js` | `state`, `currentProject`, `rememberProject()`, `refresh()`, `callApi()`, `API_FAILED` |
| `ui/tasks.js` | Task rows, buckets, search, cross-project, handoff, copy-as-prompt |
| `ui/groups.js` | The group block and header, rename-in-place, select-the-group, and `wireDrag` |
| `ui/inprogress.js` | The IN PROGRESS section, its per-project split, folding, and the reset actions |
| `ui/editor.js` | The one editor overlay: fields, chips (project/type/when/group), Toast UI, image paste |
| `ui/triage.js` | Inbox queue navigation — which note is current, and nothing else |
| `ui/settings.js` | Progress view, type editor, git-tracking toggle |
| `ui/vendor/` | Toast UI Editor 3.2.2, committed on purpose — see below |

The seven scripts **share one global scope** and load in the order
`state.js`, `tasks.js`, `groups.js`, `inprogress.js`, `editor.js`, `triage.js`,
`settings.js` (see `ui/index.html`, where the vendored library loads first).
Functions defined in one are callable from another at runtime — `triage.js`
calls into `editor.js` and `editor.js` reads `triage.js`'s queue, and
`state.js` calls `inprogress.js`'s `inProgressGroupKeys()` despite loading
three files earlier, which all works because every handler resolves its
references at call time, not at load. This split exists to keep
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
   `user_environment.login_environment()` calls Win32 `CreateEnvironmentBlock`
   instead, which is how Windows builds the environment for a newly launched
   process. **Do not add a var to a strip-list** — the list belongs to
   upstream and grows; rebuilding makes tomorrow's addition absent by
   construction. Nothing is added back on top either: with no
   `CLAUDE_CODE_CHILD_SESSION` to override, `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`
   is redundant, and setting it would be one more difference from a
   hand-started session.

9. **Typed text is bracketed, and waits for the prompt box.** `console_input`
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
    Nothing needs the focus it would take — `console_input` writes to the
    console's input buffer, which does not require an active window. Any
    future spawn gets the same treatment.

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
    document-wide, and the drag's drop handler builds `reorder_bucket`'s id
    list from `section.querySelectorAll('.task')`. Drop the rows and that last
    one hands the backend a bucket with a hole in it, leaving the folded
    members on stale `order` values that collide with the renumbered ones.

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

## Data on disk

```
~/.task-tracker/projects.json   name -> path, tracked flag, launch override
~/.task-tracker/settings.json   group_limit (5), stale_days (90), task types
~/.task-tracker/session.json    last_project, and which groups/projects are folded
~/.task-tracker/inbox/          untriaged raw notes
~/.task-tracker/session.json    last_project — restored on every launch
~/.task-tracker/window.json     window geometry
<project>/.tasks/.gitignore     contains `*` — the folder is invisible to git
<project>/.tasks/open/          NNNN-slug.md
<project>/.tasks/done/          the archive, and the progress view's source
<project>/.tasks/attachments/   pasted screenshots, YYYY-MM-DD-HHMMSS.png
```

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
- **Tests:** `store.py`, `registry.py`, `inbox.py`, `migrate.py`, `launcher.py`,
  `groups.py` and `Api` methods are all directly testable. Use `tmp_path` and the
  `monkeypatch.setattr(registry, "CONFIG_DIR", ...)` fixture pattern from
  `tests/test_registry.py`. Mock at the boundary — `subprocess.Popen` and
  `launcher.pyperclip.copy` — never spawn a real process. The one exception is
  `tests/test_console_input.py`, which really does open a console for a second
  or two: typing into another process's console is OS behaviour, and a mock of
  it would only assert that the mock was called.
- **Deliberately untested:** `main()` and window geometry persistence. Driving a
  native window under pytest is not worth the machinery; this is a decision, not
  an oversight.
- **No JS test runner.** Frontend changes are checked by running the app. Two
  editor behaviours are worth checking by hand every time `ui/editor.js` is
  touched, because both are silent when broken: type a title then click a
  different type chip (the title must not change), and edit *only* a task's
  bucket in a tracked project then run `git status` (the `.md` file must show a
  frontmatter change and **no body diff**). In `ui/tasks.js`, check that
  hovering a row does not shift the title sideways (the hover-revealed controls
  must use `opacity`, never `display`) and that clicking the copy button does
  not also open the editor. Fold a group, tick the group's checkbox, and hit
  Spin up: the folded members must still go to the session. In `ui/groups.js`,
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
  than pushing ⚙ off the row.

## Known gaps

Three spec behaviours were never implemented, and the deferred findings from the
whole-branch review are filed as tasks in this repo's own `.tasks/open/` — open
the tracker, select this project, and they are the backlog. Highlights:

- Cross-project rows do not switch the project picker to the row's project.
  They do open the editor, which is project-safe (invariant 6).
- The editor cannot **create** a group, only join one that exists or leave the
  one it is in. Creating stays the drag gesture, so there is one set of naming
  rules rather than two.
- Triage chips are mouse-only; the spec called for single-key assignment.
- Nothing ever writes `## Outcome`; the progress view renders it but it can only
  arrive by hand-editing.
- **Two groups can never be merged**, by drag or on spin-up — both paths refuse
  rather than guess which name survives. If that becomes wanted it needs an
  explicit gesture with an explicit choice.
- **Groups are one level deep** and never span projects.
- Done tasks keep their `group`, but nothing renders it: the progress view
  still lists completed tasks flat.

Design specs: `docs/superpowers/specs/2026-07-25-task-tracker-design.md`,
`docs/superpowers/specs/2026-07-25-task-editor-design.md`,
`docs/superpowers/specs/2026-07-25-task-groups-design.md`
Implementation plans: `docs/superpowers/plans/2026-07-25-task-tracker.md`,
`docs/superpowers/plans/2026-07-25-task-editor.md`,
`docs/superpowers/plans/2026-07-25-task-groups.md`

**The specs and plans are historical records, not current documentation — the
code and these invariants are.** Three things in them are known-wrong and were
corrected during implementation: `file_note` had no way to receive an edited
body (so triage silently discarded prose edits); image references were
specified as bare `C:/...` paths and `as_posix()`, which are not URLs and never
render; and the tracker spec still describes the strip-list environment that
`user_environment.py` replaced. Invariants 8, 13 and 14 are the record of what
the code actually does.
