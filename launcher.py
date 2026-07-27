"""Hand selected tasks to a visible Claude Code session.

Everything about *opening* that session and typing into it lives in
`claude_console`, a machine-level module shared with the other projects here.
What is left in this file is the part shaped by `store.Task`: what a prompt
made of tasks reads like, what a window full of them should be called, and the
order a hand-off does things in.

The division is worth stating, because the next person adding something here
has to pick a side. If it would be true of a session opened on a git diff or a
form submission, it belongs in `claude_console`. If it mentions a task, a
group, or a bucket, it belongs here.
"""

import threading
from pathlib import Path

import claude_console
import pyperclip

import store

# What a hand-off says when the text never reached the session. The clipboard
# copy is the whole reason typing is allowed to fail quietly, and until this
# existed nobody was ever told the fallback had become the only copy — an
# empty prompt box looked exactly like a hand-off that worked.
CLIPBOARD_NOTICE = ("Couldn't type the tasks into the Claude window — "
                    "they're on your clipboard, press Ctrl+V.")


def build_prompt(tasks: list[store.Task]) -> str:
    """Where each task lives, one absolute path per line, and nothing else.

    A session opened on a task can *read* the task, so the hand-off is a
    pointer rather than a copy. The file it points at is the whole of what
    used to be flattened into the prompt box — the prose, and also the type,
    the group, the dates and any pasted screenshot's absolute path, still
    formatted as the markdown it was written as.

    That ends a class of bug rather than fixing one. A prompt box takes plain
    text, so everything the editor stores that is *notation* had to be undone
    on the way out: the escapes Toast UI puts on any line that looks like a
    block construct, the literal `<br>` it writes where two presses of Enter
    left an empty paragraph, the non-breaking spaces a web-page paste leaves
    behind — each one invisible in the editor and glaring in the session, each
    one found by the user rather than by a test. None of them can happen to a
    path. Bullets and numbering arrive as the list they are for the same
    reason: nothing converts them.

    **Absolute**, though the session's own directory is the project. The same
    string goes on the clipboard, where the destination is unknown — and a
    relative path is not wrong somewhere else, it silently means a different
    file. This is invariant 14's reasoning, one directory up: it is also what
    lets a session opened anywhere resolve it.

    A task with no path cannot be handed over at all, which is `store.save_task`'s
    rule and is raised the same way. Nothing in the app can reach it: every
    task the bridge selects was read off disk.
    """
    for task in tasks:
        if task.path is None:
            raise ValueError("task has no path")
    return "\n".join(str(task.path) for task in tasks)


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
       prefix. It is only "given" if something survives `safe_line`, so `None`,
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
    the type that prefixes them — goes through `claude_console.safe_line`,
    since all of them are typed into a line that then has Enter pressed on it.
    That lives in the shared module rather than here because it is a
    precondition of `submit`, not a fact about tasks: any consumer building a
    slash command out of text it did not author needs it, and one that
    re-derives it gets it subtly wrong.

    Composition is: build the `TYPE: ` prefix and the suffix first, and only
    truncate the label into whatever room is left between them — truncating the
    finished string instead would risk eating the count, which is the most
    informative part of it.
    """
    if not tasks:
        return ""

    if name is not None:
        given_name = claude_console.safe_line(name)
        if given_name:
            return claude_console.cap(given_name)

    prefix = f"{claude_console.safe_line(tasks[0].type)}: "
    group = _shared_group(tasks)
    suffix = "" if group else (f" (+{len(tasks) - 1})" if len(tasks) > 1 else "")
    # Cleaned before the room for it is measured, on every path, so nothing
    # removed later can shorten a line that was already capped to fit.
    title = claude_console.safe_line(group or tasks[0].title)
    if not title:
        return ""

    room = claude_console.SESSION_NAME_LIMIT - len(prefix) - len(suffix)
    if room < 1:
        # The type name alone already fills the budget. There is no sane way
        # to fit any of the title in, so give up on the prefix/suffix split
        # and cap the whole composed string instead of producing a negative
        # slice.
        return claude_console.cap(f"{prefix}{title}{suffix}")
    return f"{prefix}{claude_console.cap(title, room)}{suffix}"


def session_color(tasks: list[store.Task]) -> str | None:
    """The colour to `/color` a session after, taken from the first task selected.

    `None` with nothing selected — there is no task to take a colour from, and
    `None` (not a `CLAUDE_COLORS` member) is what tells `setup_commands` to
    omit the `/color` line entirely.
    """
    return tasks[0].color if tasks else None


def setup_commands(tasks: list[store.Task]) -> list[str]:
    """The `/color` line to submit after a session comes up, if there is one.

    `/rename` used to lead this list and no longer appears in it at all: a
    session's name now travels on the launch itself, as `claude -n <name>`, so
    it is applied by the process drawing the window instead of being typed in
    afterwards. Nothing about naming can be lost to a slow start any more, and
    the delivery is one command shorter — which matters, because every typed
    command is two screen round-trips standing between a window opening and
    the tasks arriving in it. `claude_console.open_session` takes the name; the
    only thing left to type is the colour, which has no launch flag.
    """
    color = session_color(tasks)
    return [f"/color {color}"] if color else []


def hand_off(project_path: Path, tasks: list[store.Task],
             launch: list[str] | None = None, name: str | None = None,
             on_finish=None) -> str:
    """Open a session in the project, name and colour it, and hand over the tasks.

    `on_finish` is handed a `Delivery` when the typing is over, on the
    delivery's own thread. It is the only way to learn that the prompt never
    arrived — see `Deliveries`, which is what the tracker passes here.

    The name goes on the launch and the colour is typed, which is the whole of
    what changed on 2026-07-26: naming a window cannot fail any more, and the
    one remaining command still costs only itself if it does. The prompt is
    pasted regardless and left unsubmitted, so it arrives as editable text
    rather than being sent for you.

    The clipboard copy is the backup for a session that took too long to come
    up, and the reason typing is allowed to fail quietly. `claude_console`
    expects every consumer to provide one — this is the tracker's, and
    `on_finish` is how the user finds out it is the only copy.

    With nothing selected this is simply "open Claude in this project" —
    nothing is typed and the clipboard is left alone, so `deliver` has nothing
    to do and reports a delivery with nothing in it.
    """
    prompt = build_prompt(tasks)
    session = claude_console.open_session(project_path, launch,
                                          name=session_name(tasks, name))
    if prompt:
        pyperclip.copy(prompt)
    session.deliver(prompt=prompt, commands=setup_commands(tasks),
                    on_finish=on_finish)

    for task in tasks:
        store.start_task(task)

    return prompt


class Deliveries:
    """What finished hand-offs still have to say, until the frontend asks.

    Typing into a session happens on a daemon thread, sometimes a minute after
    the call that started it returned — so when it fails there is nobody left
    to tell. The text is on the clipboard, which is why failing quietly is
    allowed at all, and until this existed nobody was ever told that the
    fallback had become the only copy: an empty prompt box looks exactly like
    a hand-off that worked, which is how "sometimes the prompt gets eaten"
    went unreported for as long as it did.

    Only a prompt that never arrived is worth saying out loud. A `/color` that
    failed to submit costs the window its colour and nothing else, and a
    dialog about it would be noise on every slow start.

    Locked because `finished` runs on the delivery thread while `drain` runs
    on whichever thread the bridge call arrives on.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._in_flight = 0
        self._notices = []

    def started(self) -> None:
        with self._lock:
            self._in_flight += 1

    def abandoned(self) -> None:
        """A hand-off that raised before anything could be delivered.

        Without it the count never comes back down, and the frontend polls a
        delivery that will never report for as long as the window is open.
        """
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)

    def finished(self, delivery) -> None:
        with self._lock:
            self._in_flight = max(0, self._in_flight - 1)
            if delivery.had_prompt and not delivery.prompt_typed:
                self._notices.append(CLIPBOARD_NOTICE)

    def drain(self) -> dict:
        """Anything to say, and whether it is worth asking again."""
        with self._lock:
            notices, self._notices = self._notices, []
            return {"pending": self._in_flight > 0, "notices": notices}
