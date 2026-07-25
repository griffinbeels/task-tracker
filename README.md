# Task Tracker

An always-on-top window for tracking tasks across projects. Tasks are markdown
files inside each project's own repo; the app is a view over them.

## Run

    run.bat

That is the whole thing. It creates the venv and installs dependencies on first
run, so a fresh clone needs nothing on PATH but [uv](https://docs.astral.sh/uv/).

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
    uv pip install --python ".venv\Scripts\python.exe" pywebview pyperclip pyyaml
    & ".venv\Scripts\python.exe" app.py

## Handing tasks to Claude

Select tasks and hit **Spin up Claude**. A terminal opens in that project's
directory and your tasks are typed into its prompt box — one per line, as
`FEATURE: what you wrote` — and left there unsent, so you can edit or add to
them before hitting Enter. Nothing is appended to what you wrote.

The same text also goes to the clipboard, as the fallback for a session that
takes too long to come up. With no tasks selected the button still works: it
just opens a session in the current project with an empty prompt.

The session is launched with `--dangerously-skip-permissions`, and deliberately
does *not* inherit the environment of whatever started the tracker: variables
like `CLAUDE_CODE_CHILD_SESSION` are stripped and `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`
is set, so it is an ordinary top-level session with full transcript history and
memory. Without that it would silently run as a nested child and keep no history.

Override the command per project with a `launch` array in `projects.json` — for
example a project that needs a wrapper script or a different flag set.

## Layout

    ~/.task-tracker/projects.json   registered projects
    ~/.task-tracker/settings.json   WIP limit, staleness, task types
    ~/.task-tracker/inbox/          untriaged notes
    <project>/.tasks/open/          active tasks
    <project>/.tasks/done/          the archive, and the progress view's source

`.tasks/` is gitignored by default. Toggle per project in settings.

## Tests

    & ".venv\Scripts\python.exe" -m pytest -v
