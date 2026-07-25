# Task Tracker

An always-on-top window for tracking tasks across projects. Tasks are markdown
files inside each project's own repo; the app is a view over them.

## Run

    uv venv --python 3.12 .venv
    uv pip install --python ".venv\Scripts\python.exe" pywebview pyperclip pyyaml
    & ".venv\Scripts\python.exe" app.py

## Layout

    ~/.task-tracker/projects.json   registered projects
    ~/.task-tracker/settings.json   WIP limit, staleness, task types
    ~/.task-tracker/inbox/          untriaged notes
    <project>/.tasks/open/          active tasks
    <project>/.tasks/done/          the archive, and the progress view's source

`.tasks/` is gitignored by default. Toggle per project in settings.

## Tests

    & ".venv\Scripts\python.exe" -m pytest -v
