"""Hand selected tasks to a visible Claude Code session."""

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyperclip

import console_input
import store
import user_environment

NEW_CONSOLE = getattr(subprocess, "CREATE_NEW_CONSOLE", 0)

DEFAULT_LAUNCH = ["claude", "--dangerously-skip-permissions"]

# Show the new console, but do not make it the active window (SW_SHOWNOACTIVATE
# rather than the default SW_SHOWNORMAL). Hand-off is something you trigger and
# then carry on with: a window that grabs focus swallows whatever you type next
# and puts it into a session you were not looking at. Nothing here needs focus
# — console_input writes to the console's input buffer, which does not require
# the window to be active.
SW_SHOWNOACTIVATE = 4


def unfocused_startup() -> "subprocess.STARTUPINFO":
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = SW_SHOWNOACTIVATE
    return startup


def claude_environment() -> dict[str, str]:
    """The environment a session you opened by hand would have.

    Not this process's environment with the awkward parts removed — the
    tracker is usually started from a Claude session, and inheriting from it
    is the whole problem. See user_environment for why this is rebuilt rather
    than filtered.
    """
    return user_environment.login_environment()


def build_prompt(tasks: list[store.Task]) -> str:
    """One line per task: its type, then its body verbatim.

    This is what lands in the session's prompt box, so it reads as the notes
    themselves rather than as a document about them — `FEATURE: <the idea>`,
    one per line, nothing else added. Trailing blank lines are dropped so the
    join is exactly one newline between tasks; nothing else about a body is
    touched, and a body is never trimmed at the front or re-wrapped.

    A task with no body falls back to its title, because `FEATURE: ` on its own
    hands over nothing at all. That is still verbatim — it selects a different
    field of the task, it does not edit either one.
    """
    return "\n".join(f"{task.type}: {task.body.rstrip() or task.title}"
                     for task in tasks)


def copy_prompt(tasks: list[store.Task]) -> str:
    """Put the hand-off text on the clipboard, and change nothing else.

    Deliberately not a slice of hand_off(): no session is opened and no task is
    marked in-progress. Copying is a cheap gesture — the text might be going to
    an already-open session, a chat, or nowhere — so it commits you to nothing.
    Sharing build_prompt with hand_off is the point, though: the two ways of
    getting a task into Claude cannot then drift into two different formats.
    """
    prompt = build_prompt(tasks)
    pyperclip.copy(prompt)
    return prompt


def spawn_claude(project_path: Path,
                 launch: list[str] | None = None) -> subprocess.Popen:
    return subprocess.Popen(
        launch or DEFAULT_LAUNCH,
        cwd=Path(project_path),
        creationflags=NEW_CONSOLE,
        env=claude_environment(),
        startupinfo=unfocused_startup(),
    )


def hand_off(project_path: Path, tasks: list[store.Task],
             launch: list[str] | None = None) -> str:
    """Open a session in the project with the selected tasks in its prompt box.

    The text is typed into the new window rather than submitted for you: it
    arrives as an editable prompt, so you can add to it or think again before
    sending. The clipboard copy is the backup for a session that took too long
    to come up, and the reason typing is allowed to fail silently.

    With nothing selected this is simply "open Claude in this project" —
    nothing is typed, and the clipboard is left alone.
    """
    prompt = build_prompt(tasks)
    session = spawn_claude(project_path, launch)
    if prompt:
        pyperclip.copy(prompt)
        console_input.paste_when_ready(session.pid, prompt)

    today = datetime.now(timezone.utc).date().isoformat()
    for task in tasks:
        task.status = "in-progress"
        task.started = task.started or today
        store.save_task(task)

    return prompt


# A tab label longer than this is unreadable, and it doubles as what keeps
# Claude Code inserting a pasted `/rename` argument literally rather than
# collapsing it into a `[Pasted text]` placeholder — a short line pastes as
# text, a long one pastes as an attachment.
SESSION_NAME_LIMIT = 60


def session_name(tasks: list[store.Task], name: str | None = None) -> str:
    """The `/rename` argument for a session opened on these tasks, or "" for none.

    The name is a parameter rather than something derived from the tasks
    themselves — a sibling feature will eventually supply it from a task's
    group, and keeping it an argument here is what lets that land independently
    of this one. This function never reads `task.group`.

    With no tasks there is nothing to name a session after, so this returns ""
    even when a name was given — an empty spin-up gets no `/rename` at all.

    A given name wins outright and carries no type prefix; it is only "given"
    if something survives whitespace-collapsing, so `None` and blank strings
    both fall through to naming the first task. Composition on that fallback
    path is: build the `TYPE: ` prefix and the `(+n-1)` suffix first, and only
    truncate the title into whatever room is left between them — truncating
    the finished string instead would risk eating the count, which is the most
    informative part of it.
    """
    if not tasks:
        return ""

    if name is not None:
        collapsed_name = " ".join(name.split())
        if collapsed_name:
            return _cap(collapsed_name)

    prefix = f"{tasks[0].type}: "
    suffix = f" (+{len(tasks) - 1})" if len(tasks) > 1 else ""
    # Collapse whitespace before measuring room for the title: a task file is
    # hand-editable, and a raw newline inside a `/rename` argument would submit
    # the line early and leave the rest sitting in the prompt box as text.
    title = " ".join(tasks[0].title.split())
    if not title:
        return ""

    room = SESSION_NAME_LIMIT - len(prefix) - len(suffix)
    if room < 1:
        # The type name alone already fills the budget. There is no sane way
        # to fit any of the title in, so give up on the prefix/suffix split
        # and cap the whole composed string instead of producing a negative
        # slice.
        return _cap(f"{prefix}{title}{suffix}")
    return f"{prefix}{_cap(title, room)}{suffix}"


def _cap(text: str, limit: int = SESSION_NAME_LIMIT) -> str:
    """Truncate to `limit`, appending a single ellipsis so the result lands on it.

    A single `…` rather than three dots, so a capped string is exactly `limit`
    characters long instead of `limit + 2`.
    """
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"


def session_color(tasks: list[store.Task]) -> str | None:
    """The colour to `/color` a session after, taken from the first task selected.

    `None` with nothing selected — there is no task to take a colour from, and
    `None` (not a `CLAUDE_COLORS` member) is what tells `setup_commands` to
    omit the `/color` line entirely.
    """
    return tasks[0].color if tasks else None


def setup_commands(tasks: list[store.Task], name: str | None = None) -> list[str]:
    """The `/rename` and `/color` lines to submit after a session comes up.

    Rename first, then colour, matching the order a person doing this by hand
    would type them. Either line is omitted when its value is empty, so a task
    with no title still gets coloured, and an empty selection sends nothing.
    """
    commands = []

    name_line = session_name(tasks, name)
    if name_line:
        commands.append(f"/rename {name_line}")

    color = session_color(tasks)
    if color:
        commands.append(f"/color {color}")

    return commands
