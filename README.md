# Task Tracker

An always-on-top window for tracking tasks across projects. Tasks are markdown
files inside each project's own repo; the app is a view over them.

## Run

Use **run.bat** on Windows. On Mac, double-click **run.command** once to set
up Python and build **dist/Task Tracker.app**, then open that app from Finder
or keep it in the Dock. The app runs this checkout's current source, so ordinary
code edits need only a restart. Re-run `run.command` after moving the checkout
or changing packaging settings. The generated app depends on this checkout
and its local environment; it is not a standalone app to copy to another Mac.

Both launchers create a Python 3.12 environment and install dependencies on first
run. A fresh clone needs [uv](https://docs.astral.sh/uv/)
plus one sibling checkout. `claude-console`, the shared module that opens and
drives the handed-off Claude session, is installed from a checkout rather than
an index, so clone it next to this repo first (either folder name works, or set
`CLAUDE_CONSOLE_PATH` to wherever you put it):

    git clone https://github.com/griffinbeels/claude_console.git

The same task files and interface serve Windows and macOS. The first Mac port
is a preview; native launch, focus and terminal hand-off still need acceptance
on both desktops. See [platform support](docs/platform-support.md).

From a Git worktree, the Mac launcher creates **Task Tracker Preview.app** and
uses `.preview-data/` for its local settings with a separate instance port.
Add a temporary project to try it: task edits still write to whichever project
you select. Preview data stays local and is not automatically migrated.

Running it again while a window is already open shuts that one down — saving its
size and position — and takes over, so you always end up with exactly one window
running the current code. There is nothing to stop by hand: after changing the
code, just run it again.

Single-instance is enforced by binding `127.0.0.1:8090`. A port is an atomic
lock the OS releases when the process dies, so unlike a PID file there is no
stale lock to clear after a crash. If something *else* is holding that port, the
tracker says so and refuses to start rather than opening a second window.

To run it directly instead:

    uv venv --python 3.12 .venv
    uv pip install --python ".venv\Scripts\python.exe" -e ..\claude_console -e .
    & ".venv\Scripts\python.exe" app.py

On Mac, the equivalent interpreter is `.venv/bin/python` and the editable
console path can be written as `../claude_console`.

The checkout is passed as its own editable because `pyproject.toml` names
`claude-console` as a dependency but deliberately gives no path to it — an
absolute path would publish one machine's layout in a public repo, and a
relative one cannot serve both this checkout and a worktree checked out four
levels under it. `-e .` then pulls the rest from `pyproject.toml`.

## Writing a task

One editor, reached three ways: **Capture** for a new thought, the **Inbox**
button to work through untriaged notes, and clicking any task row to change it.
All three give you the same thing — a title, a rich-text body, and chips for
project, type and bucket.

The body is a real editor: bullets, numbered lists, checkboxes, bold, italic,
quotes and code, formatted as you type rather than as markdown you have to
read. It is still markdown on disk. **Command+V on Mac or Ctrl+V on Windows pastes a screenshot at
the cursor**, exactly where you put it — the image is written into the
project's `.tasks/attachments/` and the note keeps a link to it, so a session
you hand the task to can open the picture you were describing.

Capture asks nothing of you: type and hit **Later** and it goes to the inbox
undecided, the way it always did. The chips are there when you already know
where something belongs and want to file it in one gesture instead of two.

Two things it will not do, both on purpose. It never overwrites what you typed
— picking a type after writing a title leaves the title alone. And it never
rewrites a body you did not edit, so opening an old task to change its bucket
does not quietly reformat prose you wrote by hand.

## Handing tasks to Claude

Select tasks and press the **Claude button** — the little Claude face, in the
toolbar and again in the selection bar. A terminal opens in that project's
directory and each task's **file path** is typed into its prompt box — one
absolute path per line, and nothing else — left there unsent, so you can edit
or add to them before hitting Enter.

A pointer rather than a copy, because a session opened on the project can read
the task itself. The file carries what a prompt box never could: the type, the
group, the dates, any pasted screenshot's absolute path, and your prose still
formatted as the markdown you wrote it as, lists and numbering included.
Nothing converts a task body on the way out, so nothing can mangle it.

The same paths also go to the clipboard, as the fallback for a session that
takes too long to come up. With no tasks selected the button still works: it
just opens a session in the current project with an empty prompt.

The session is launched with `--dangerously-skip-permissions`, and its
environment is **rebuilt rather than inherited**. The tracker is usually
started from a Claude session, and Claude Code sets a batch of variables for
the processes it spawns; passing those on made the new session differ from one
you opened yourself in ways that were all silent — it rendered monochrome, its
git could not open an editor or ask for credentials, and it kept no transcript.
Windows rebuilds the login environment; Mac uses a login shell in Terminal.app
and removes the inherited Claude session variables. Mac may ask you to allow
automation of Terminal. Delivery waits for the prompt and checks the result;
permission, trust or readiness failures leave a visible clipboard fallback.
Trust dialogs remain for you to answer.

A deliberate hand-off may bring the new session forward. Background checks and
tracker restarts must not open stray consoles or type into the active window.

Override the command per project with a `launch` array in `projects.json` — for
example a project that needs a wrapper script or a different flag set.

## Layout

    ~/.task-tracker/projects.json   registered projects
    ~/.task-tracker/settings.json   group limit, staleness, task types
    ~/.task-tracker/inbox/          untriaged notes
    <project>/.tasks/open/          active tasks
    <project>/.tasks/done/          the archive, and the progress view's source
    <project>/.tasks/attachments/   pasted screenshots

`.tasks/` is gitignored by default, screenshots included — several of these
repos are public and a backlog is not meant to be published. Toggle per project
in settings.

The editor itself is vendored in `ui/vendor/` rather than loaded from a CDN, so
the app works with no network.

## Tests

    & ".venv\Scripts\python.exe" -m pytest -v

On Mac: `.venv/bin/python -m pytest -v`. On either platform, run
`node --test tests/test_shortcuts.js` and `node tools/check_js.cjs` as well.
The CI matrix runs the shared contracts on both systems. New features follow
the native boundaries and acceptance requirements in
[platform support](docs/platform-support.md).
