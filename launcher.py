"""Hand selected tasks to a visible Claude Code session."""

import re
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


# A tab label longer than this is unreadable, and it doubles as what keeps
# Claude Code inserting a pasted `/rename` argument literally rather than
# collapsing it into a `[Pasted text]` placeholder — a short line pastes as
# text, a long one pastes as an attachment.
SESSION_NAME_LIMIT = 60

# C0 and C1 control characters, including DEL. `str.split()` does not remove
# these — see _one_line for why a `/rename` argument must not carry one.
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _one_line(text: str) -> str:
    """Collapse whitespace and drop control characters, in that order.

    Everything this returns ends up inside a line that `console_input.submit`
    writes as `ESC[200~ … ESC[201~` and then presses Enter on, in a session
    spawned with `--dangerously-skip-permissions`. Titles and names come from a
    hand-editable YAML file, and a double-quoted scalar can express `\\e`
    directly — so a title containing `ESC[201~` would close the bracketed paste
    early, leaving whatever follows it outside the paste for that Enter to
    submit as a command of its own.

    Whitespace goes first because collapsing is what stops a raw newline
    submitting the line early; controls go second because `str.split()` removes
    `\\n`, `\\r` and `\\x1c`-`\\x1f` but leaves ESC, NUL, BEL and backspace
    untouched. Stripping rather than rejecting: a task with a strange title
    should still hand off, it just must not be able to submit a line.
    """
    return _CONTROL.sub("", " ".join(text.split()))


def _shared_group(tasks: list[store.Task]) -> str | None:
    """The group every one of these tasks belongs to, or None.

    "Every" is the whole point: a selection that mixes two groups, or a group
    with a loose task alongside it, has no single name that is true of all of
    it. Returns None for that, so the caller falls back to a title and a count.
    """
    groups = {task.group for task in tasks}
    if len(groups) == 1:
        only = groups.pop()
        return only or None
    return None


def session_name(tasks: list[store.Task], name: str | None = None) -> str:
    """The `/rename` argument for a session opened on these tasks, or "" for none.

    With no tasks there is nothing to name a session after, so this returns ""
    even when a name was given — an empty spin-up gets no `/rename` at all.

    Three sources, in order of how well each describes the window:

    1. A name typed into the batch row wins outright and carries no type
       prefix. It is only "given" if something survives `_one_line`, so `None`,
       blank strings and a string of nothing but control characters all fall
       through.
    2. A group shared by *every* selected task. Ticking a group's checkbox
       selects its members, and the group's name is what that window is for —
       the first member's title is an arbitrary one of several. A subset of a
       group still counts: the work belongs to the group either way. A
       selection spanning two groups, or mixing grouped with loose tasks, does
       not, because naming after one of them would claim the rest are not in
       the window.
    3. The first task's title, with `(+n-1)` for the others.

    A group name carries no count — it already denotes the whole set, and the
    selection may legitimately be a subset of it.

    Every piece of user text on this path — the name, the group, the title and
    the type that prefixes them — goes through `_one_line`, since all of them
    are typed into a line that then has Enter pressed on it. Composition is:
    build the `TYPE: ` prefix and the suffix first, and only truncate the label
    into whatever room is left between them — truncating the finished string
    instead would risk eating the count, which is the most informative part of
    it.
    """
    if not tasks:
        return ""

    if name is not None:
        given_name = _one_line(name)
        if given_name:
            return _cap(given_name)

    prefix = f"{_one_line(tasks[0].type)}: "
    group = _shared_group(tasks)
    suffix = "" if group else (f" (+{len(tasks) - 1})" if len(tasks) > 1 else "")
    # Cleaned before the room for it is measured, on every path, so nothing
    # removed later can shorten a line that was already capped to fit.
    title = _one_line(group or tasks[0].title)
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

    A limit below 1 has no room even for the ellipsis, so it yields nothing at
    all. Without that guard `limit == 0` reaches `text[:-1]` — dropping one
    character and appending an ellipsis, i.e. returning very nearly the whole
    string for a limit of zero. `session_name`'s own `room < 1` branch means no
    caller reaches it today; the next one passing a computed limit would.
    """
    if limit < 1:
        return ""
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


def hand_off(project_path: Path, tasks: list[store.Task],
             launch: list[str] | None = None, name: str | None = None) -> str:
    """Open a session in the project, rename and colour it, and hand over the tasks.

    Delivery order is commands first, prompt last and unsubmitted: a `/rename`
    or `/color` that fails to submit costs only itself, because the prompt was
    never made to depend on the commands succeeding, and it still arrives as
    editable text rather than being sent for you. The clipboard copy is the
    backup for a session that took too long to come up, and the reason typing
    is allowed to fail silently.

    With nothing selected this is simply "open Claude in this project" —
    nothing is typed, and the clipboard is left alone. The background thread
    still starts, because the one thing that session does need is a console
    font its logo renders in (`console_input.use_font`).
    """
    prompt = build_prompt(tasks)
    commands = setup_commands(tasks, name)
    session = spawn_claude(project_path, launch)
    if prompt:
        pyperclip.copy(prompt)
    console_input.deliver_when_ready(session.pid, commands, prompt)

    today = datetime.now(timezone.utc).date().isoformat()
    for task in tasks:
        task.status = "in-progress"
        task.started = task.started or today
        store.save_task(task)

    return prompt
