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

## Writing a task

One editor, reached three ways: **Capture** for a new thought, the **Inbox**
button to work through untriaged notes, and clicking any task row to change it.
All three give you the same thing — a title, a rich-text body, and chips for
project, type and bucket.

The body is a real editor: bullets, numbered lists, checkboxes, bold, italic,
quotes and code, formatted as you type rather than as markdown you have to
read. It is still markdown on disk. **Ctrl+V pastes a screenshot straight in at
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

Select tasks and hit **Spin up Claude**. A terminal opens in that project's
directory and your tasks are typed into its prompt box — one per line, as
`FEATURE: what you wrote` — and left there unsent, so you can edit or add to
them before hitting Enter. Nothing is appended to what you wrote.

The same text also goes to the clipboard, as the fallback for a session that
takes too long to come up. With no tasks selected the button still works: it
just opens a session in the current project with an empty prompt.

The session is launched with `--dangerously-skip-permissions`, and its
environment is **rebuilt rather than inherited**. The tracker is usually
started from a Claude session, and Claude Code sets a batch of variables for
the processes it spawns; passing those on made the new session differ from one
you opened yourself in ways that were all silent — it rendered monochrome, its
git could not open an editor or ask for credentials, and it kept no transcript.
Windows is asked for the environment it would give a freshly launched process,
so the session is indistinguishable from one you started by hand in a terminal.

It also opens without taking focus. Hand-off happens mid-sentence, and a window
that activates itself swallows whatever you type next.

Override the command per project with a `launch` array in `projects.json` — for
example a project that needs a wrapper script or a different flag set.

## Layout

    ~/.task-tracker/projects.json   registered projects
    ~/.task-tracker/settings.json   WIP limit, staleness, task types
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
