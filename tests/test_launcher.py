"""What a hand-off made of tasks reads like, and what it does to them.

Opening the console, resolving the pid inside it, keeping it off the keyboard
and typing into it are `claude_console`'s, and are tested in that repo — see
its `tests/test_session.py` and `tests/test_console_input.py`. What is left
here is everything shaped by `store.Task`.

The seam this file mocks at is `claude_console.open_session`. These tests used
to stub `subprocess.Popen`, because that was the nearest seam available — which
meant every task-shaped assertion carried three lines of Win32 scaffolding it
had no opinion about.
"""

from pathlib import Path

import claude_console
import pytest

import launcher
import store


def make_task(task_id, title, type, body, color="", group=None, path=None):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
        color=color, group=group, path=path,
    )


# The pid claude_console reports for a session: the process inside the console
# host, not the host itself. Nothing here depends on how it was arrived at.
CLIENT_PID = 9999


class FakeSession:
    """What `open_session` hands back, with the delivery recorded rather than made."""

    def __init__(self, record):
        self.pid = CLIENT_PID
        self.host = None
        self._record = record

    def deliver(self, prompt="", commands=(), on_finish=None):
        self._record.update(pid=self.pid, text=prompt, commands=list(commands),
                            on_finish=on_finish)


@pytest.fixture
def spawned(monkeypatch):
    """Swallow the session open and record what would have been typed into it."""
    opened = {}

    def fake_open_session(cwd, launch=None, name=""):
        opened.update(cwd=cwd, launch=launch, name=name)
        return FakeSession(opened)

    monkeypatch.setattr(claude_console, "open_session", fake_open_session)
    return opened


def test_the_prompt_is_where_the_task_lives(tmp_path):
    task = store.create_task(tmp_path, "Replay audio desync", "drifts after 3s", "BUG")

    assert launcher.build_prompt([task]) == str(task.path)


def test_nothing_the_editor_stored_can_reach_the_session(tmp_path):
    """The whole point of a pointer: there is no text to mangle on the way.

    Each of these was its own bug in the prose prompt — escapes on a line that
    looks like a list, the `<br>` an empty paragraph serializes to, and a
    non-breaking space off a web-page paste. All three are still in the file,
    where they are markdown and are read as such.
    """
    body = "1\\. one\\, two\n\n<br>\nhello\u00a0world"
    task = store.create_task(tmp_path, "Replay audio desync", body, "BUG")

    prompt = launcher.build_prompt([task])

    assert prompt == str(task.path)
    assert "<br>" not in prompt
    assert "\u00a0" not in prompt
    assert "\\," not in prompt
    assert body in task.path.read_text(encoding="utf-8")


def test_each_task_gets_its_own_line_in_the_given_order(tmp_path):
    first = store.create_task(tmp_path, "First", "body one", "BUG")
    second = store.create_task(tmp_path, "Second", "body two", "FEATURE")

    assert launcher.build_prompt([first, second]) == f"{first.path}\n{second.path}"


def test_the_path_is_absolute_because_the_clipboard_can_go_anywhere(tmp_path):
    # A relative path is not wrong somewhere else; it means a different file.
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    written = Path(launcher.build_prompt([task]))

    assert written.is_absolute()
    assert written.exists()


def test_nothing_selected_is_an_empty_prompt():
    assert launcher.build_prompt([]) == ""


def test_a_task_with_no_path_cannot_be_handed_over():
    # `store.save_task`'s rule, raised the same way. Nothing in the app can
    # reach it — every task the bridge selects was read off disk — so this
    # pins that a hand-built Task fails loudly instead of typing "None".
    with pytest.raises(ValueError):
        launcher.build_prompt([make_task(1, "Replay audio desync", "BUG", "drifts")])


def test_copy_prompt_puts_the_hand_off_text_on_the_clipboard(tmp_path, monkeypatch):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))
    task = store.create_task(tmp_path, "Replay audio desync", "drifts after 3s", "BUG")

    returned = launcher.copy_prompt([task])

    assert copied["text"] == str(task.path)
    assert returned == copied["text"]


def test_copy_prompt_does_not_touch_the_task(tmp_path, monkeypatch):
    # Copying is not a commitment to work on something — unlike hand_off, it
    # leaves status and started exactly as they were.
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    launcher.copy_prompt([task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_hand_off_opens_the_session_in_the_project(tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)

    launcher.hand_off(tmp_path, [])

    assert spawned["cwd"] == tmp_path


def test_hand_off_passes_a_per_project_launch_override_straight_through(
        tmp_path, monkeypatch, spawned):
    # The tracker does not interpret this — how a launch argv becomes a window
    # is claude_console's business, and a project may legitimately name
    # something that is not `claude` at all.
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)

    launcher.hand_off(tmp_path, [], launch=["pwsh", "-c", "claude"])

    assert spawned["launch"] == ["pwsh", "-c", "claude"]


def test_hand_off_marks_tasks_in_progress_and_copies_the_prompt(
        tmp_path, monkeypatch, spawned):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "in-progress"
    assert reloaded.started is not None
    assert copied["text"] == prompt
    assert prompt == str(reloaded.path)


def test_hand_off_types_the_prompt_into_the_session_it_opened(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    # The session inside the console, not the console host it runs in.
    assert spawned["pid"] == CLIENT_PID
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_opens_a_bare_session(
        tmp_path, monkeypatch, spawned):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))

    prompt = launcher.hand_off(tmp_path, [])

    # A session in the right directory, and nothing else touched: no text
    # typed, and whatever the user had on their clipboard still there.
    # `deliver` is still called — with nothing to type it is there for the
    # console font and icon, which this session needs as much as any other.
    assert prompt == ""
    assert spawned["commands"] == []
    assert spawned["text"] == ""
    assert copied == {}


def test_hand_off_leaves_tasks_untouched_when_the_session_cannot_start(
        tmp_path, monkeypatch):
    # claude_console raises from the spawn itself and gives up quietly on
    # everything after it, so this is the one failure the tracker ever sees.
    def exploding_open(cwd, launch=None, name=""):
        raise FileNotFoundError("claude is not on PATH")

    monkeypatch.setattr(claude_console, "open_session", exploding_open)
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    with pytest.raises(FileNotFoundError):
        launcher.hand_off(tmp_path, [task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_grouping_on_hand_off_does_not_change_what_is_typed(
        tmp_path, monkeypatch, spawned):
    """Auto-grouping records intent; it must never touch the prompt.

    It also has to run AFTER launcher.hand_off returns. hand_off saves the Task
    objects it was handed, so grouping first would leave those objects stale
    and the save would silently discard the group.
    """
    import app
    import registry

    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    first = store.create_task(repo, "First", "body one", "BUG")
    second = store.create_task(repo, "Second", "body two", "FEATURE")

    prompt = app.Api().hand_off("repo", [first.id, second.id])

    assert prompt == f"{first.path}\n{second.path}"
    assert {t.group for t in store.list_tasks(repo)} == {"First"}
    assert {t.status for t in store.list_tasks(repo)} == {"in-progress"}


def test_session_name_is_the_type_then_the_title():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b")

    assert launcher.session_name([task]) == "FEATURE: Rename the spawned session"


def test_session_name_names_the_first_task_and_counts_the_others():
    tasks = [make_task(1, "Rename the spawned session", "FEATURE", "b"),
             make_task(2, "Colour it too", "FEATURE", "b"),
             make_task(3, "And a dot on the row", "BUG", "b")]

    assert launcher.session_name(tasks) == "FEATURE: Rename the spawned session (+2)"


def test_a_name_that_was_given_wins_and_carries_no_type_prefix():
    tasks = [make_task(1, "Rename the spawned session", "FEATURE", "b"),
             make_task(2, "Colour it too", "FEATURE", "b")]

    assert launcher.session_name(tasks, "Editor polish") == "Editor polish"


def test_a_whitespace_only_name_is_not_a_name():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b")

    assert launcher.session_name([task], "   ") == "FEATURE: Rename the spawned session"


def test_a_newline_in_a_title_never_reaches_the_command_line():
    # Unbracketed, a newline mid-line submits early and leaves the rest as a
    # stray prompt. Task files are hand-editable, so this is reachable.
    task = make_task(1, "Rename\nthe spawned\tsession", "FEATURE", "b")

    assert launcher.session_name([task]) == "FEATURE: Rename the spawned session"


def test_an_escape_in_a_title_never_reaches_the_command_line():
    # str.split() removes \n and \t but not ESC, NUL, BEL or backspace, and a
    # double-quoted YAML scalar in a hand-edited task file can express \e.
    task = make_task(1, "Rename\x1bthe \x00spawned\x07 session\x08", "FEATURE", "b")

    name = launcher.session_name([task])

    assert "\x1b" not in name
    assert name == "FEATURE: Renamethe spawned session"


def test_a_title_cannot_close_the_bracketed_paste_it_is_typed_inside():
    # The line goes out as PASTE_START + line + PASTE_END and is then followed
    # by its own \r. A title carrying an END marker would close the paste
    # early, putting everything after it outside the paste for that \r to
    # submit — into a session spawned with --dangerously-skip-permissions.
    #
    # The cleaning itself is claude_console.safe_line's, and is tested there.
    # What this pins is that the tracker actually routes a title through it —
    # the half that a move across a module boundary can silently drop.
    end = claude_console.console_input.PASTE_END
    task = make_task(1, f"Fix it{end}/exit", "FEATURE", "b")

    name = launcher.session_name([task])

    assert end not in name
    assert "\x1b" not in name
    assert name == "FEATURE: Fix it[201~/exit"


def test_a_given_name_is_stripped_of_control_characters_too():
    # The given-name path returns before the title path is ever reached, so it
    # needs its own defence rather than inheriting the title's.
    end = claude_console.console_input.PASTE_END
    task = make_task(1, "Short", "FEATURE", "b")

    name = launcher.session_name([task], f"Editor\x1b polish{end}")

    assert "\x1b" not in name
    assert name == "Editor polish[201~"


def test_a_name_of_nothing_but_control_characters_is_not_a_name():
    # Nothing survives the clean, so it is not "given" and the first task's
    # title names the session instead.
    task = make_task(1, "Rename the spawned session", "FEATURE", "b")

    assert launcher.session_name([task], "\x1b\x00") == "FEATURE: Rename the spawned session"


def test_a_control_character_in_a_type_name_is_stripped_as_well():
    # Type names are hand-editable settings and prefix the same submitted
    # line, so they are the same class of input as the title.
    task = make_task(1, "Replay audio desync", "B\x1bUG", "b")

    assert launcher.session_name([task]) == "BUG: Replay audio desync"


def test_a_long_title_is_capped_but_the_count_survives():
    tasks = [make_task(1, "R" * 200, "FEATURE", "b"),
             make_task(2, "Second", "FEATURE", "b"),
             make_task(3, "Third", "FEATURE", "b")]

    name = launcher.session_name(tasks)

    assert len(name) <= claude_console.SESSION_NAME_LIMIT
    assert name.startswith("FEATURE: ")
    assert name.endswith(" (+2)")


def test_a_long_given_name_is_capped_too():
    task = make_task(1, "Short", "FEATURE", "b")

    name = launcher.session_name([task], "E" * 200)

    assert len(name) <= claude_console.SESSION_NAME_LIMIT


def test_nothing_selected_has_no_name_even_if_one_was_typed():
    assert launcher.session_name([]) == ""
    assert launcher.session_name([], "Editor polish") == ""


def test_a_task_with_no_title_has_no_name():
    # "FEATURE: " on its own names nothing, so no /rename is sent at all.
    assert launcher.session_name([make_task(1, "  ", "FEATURE", "b")]) == ""


def test_a_selection_that_shares_a_group_is_named_after_the_group():
    # Ticking a group's checkbox selects its members. The group's name is what
    # that window is for; the first member's title is an arbitrary one of many.
    tasks = [make_task(1, "Chips rewrite the row", "BUG", "b", group="Editor polish"),
             make_task(2, "Title is discarded", "BUG", "b", group="Editor polish")]

    assert launcher.session_name(tasks) == "BUG: Editor polish"


def test_a_group_name_carries_no_count():
    # "(+2)" says "and some others"; a group name already denotes the whole set,
    # and the selection may legitimately be a subset of it.
    tasks = [make_task(1, "One", "BUG", "b", group="Editor polish"),
             make_task(2, "Two", "BUG", "b", group="Editor polish"),
             make_task(3, "Three", "BUG", "b", group="Editor polish")]

    assert launcher.session_name(tasks) == "BUG: Editor polish"


def test_one_task_from_a_group_still_names_the_group():
    # A group of one, or one member ticked by hand: the work still belongs to
    # that group, and the alternative is a rule that changes at n=2.
    task = make_task(1, "Chips rewrite the row", "BUG", "b", group="Editor polish")

    assert launcher.session_name([task]) == "BUG: Editor polish"


def test_a_selection_spanning_two_groups_falls_back_to_the_title():
    # Naming after one of them would claim the other is not in the window.
    tasks = [make_task(1, "Chips rewrite the row", "BUG", "b", group="Editor polish"),
             make_task(2, "Drag is jumpy", "BUG", "b", group="Drag fixes")]

    assert launcher.session_name(tasks) == "BUG: Chips rewrite the row (+1)"


def test_a_loose_task_among_grouped_ones_falls_back_to_the_title():
    tasks = [make_task(1, "Chips rewrite the row", "BUG", "b", group="Editor polish"),
             make_task(2, "Unfiled thought", "BUG", "b")]

    assert launcher.session_name(tasks) == "BUG: Chips rewrite the row (+1)"


def test_a_typed_name_still_beats_the_group():
    tasks = [make_task(1, "One", "BUG", "b", group="Editor polish"),
             make_task(2, "Two", "BUG", "b", group="Editor polish")]

    assert launcher.session_name(tasks, "Something else") == "Something else"


def test_a_group_name_is_cleaned_like_every_other_typed_line():
    # Group names are hand-editable frontmatter, on the same path that ends in
    # a submitted line — same treatment as titles and types.
    task = make_task(1, "One", "BUG", "b", group="Editor\npolish\x1b[201~")

    name = launcher.session_name([task])

    assert "\n" not in name and "\x1b" not in name
    assert name == "BUG: Editor polish[201~"


def test_a_long_group_name_is_capped():
    task = make_task(1, "One", "FEATURE", "b", group="G" * 200)

    assert len(launcher.session_name([task])) <= claude_console.SESSION_NAME_LIMIT


def test_session_color_is_the_first_selected_task_s():
    tasks = [make_task(1, "First", "FEATURE", "b", color="purple"),
             make_task(2, "Second", "FEATURE", "b", color="red")]

    assert launcher.session_color(tasks) == "purple"


def test_nothing_selected_has_no_colour():
    assert launcher.session_color([]) is None


def test_the_only_thing_still_typed_is_the_colour():
    """`/rename` is not in this list any more, and its absence is the fix.

    A name rides on the launch (`claude -n …`), where nothing can lose it. It
    used to be the first thing typed into the session — two screen round-trips
    before the tasks could be pasted, on a window that had just opened, which
    is precisely when a session is slowest to keep up. Colour has no launch
    flag, so it stays typed.
    """
    task = make_task(1, "Rename the spawned session", "FEATURE", "b",
                     color="purple")

    assert launcher.setup_commands([task]) == ["/color purple"]


def test_setup_commands_is_empty_with_nothing_selected():
    assert launcher.setup_commands([]) == []


def test_setup_commands_still_colours_a_task_that_cannot_be_named():
    task = make_task(1, "  ", "FEATURE", "b", color="cyan")

    assert launcher.setup_commands([task]) == ["/color cyan"]


def test_a_type_name_that_fills_the_whole_budget_still_yields_a_capped_name():
    # Type names come from user-editable settings, so a 60-character one is
    # reachable. The prefix/suffix split has no room to work with here, and
    # the fallback must not produce a negative slice.
    task = make_task(1, "Replay audio desync", "T" * 70, "b")

    name = launcher.session_name([task])

    assert len(name) == claude_console.SESSION_NAME_LIMIT
    assert name.startswith("TTT")


def test_hand_off_names_the_session_at_launch_and_colours_it_by_typing(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG",
                             color="purple")

    launcher.hand_off(tmp_path, [task])

    assert spawned["name"] == "BUG: Replay audio desync"
    assert spawned["commands"] == ["/color purple"]


def test_hand_off_uses_the_name_it_was_given(tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    first = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")
    second = store.create_task(tmp_path, "Chips rewrite the row", "x", "BUG")

    launcher.hand_off(tmp_path, [first, second], name="Editor polish")

    assert spawned["name"] == "Editor polish"
    # Whatever colour the first task defaulted to — the point here is the name.
    assert spawned["commands"][0].startswith("/color ")


def test_the_commands_are_handed_over_apart_from_the_prompt(
        tmp_path, monkeypatch, spawned):
    # Ordering is the whole safety argument: if both commands fail, the session
    # still ends up where it lands today — task text sitting editable. The
    # ordering is enforced inside claude_console.console_input.deliver and
    # tested there; what this pins is that the tracker hands them over as two
    # separate things rather than pasting a command and a prompt as one line.
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    assert spawned["commands"][0].startswith("/color ")
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_sends_no_commands(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)

    launcher.hand_off(tmp_path, [])

    assert spawned["commands"] == []
    assert spawned["text"] == ""
