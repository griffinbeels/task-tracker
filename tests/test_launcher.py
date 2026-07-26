import subprocess
from pathlib import Path

import pytest

import launcher
import store


def make_task(task_id, title, type, body, color="", group=None):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
        color=color, group=group,
    )


class FakeSession:
    """Stands in for the Popen of the console host a session is spawned in."""
    pid = 4242


# The session inside that host — conhost's child, and the pid anything typing
# into the window has to attach to.
CLIENT_PID = 9999


@pytest.fixture
def spawned(monkeypatch):
    """Swallow the process spawn and record what would have been sent to it."""
    typed = {}
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeSession())
    monkeypatch.setattr(launcher, "_children_of", lambda pid: [CLIENT_PID])
    # Left running, this attaches to a console — and attaching means leaving
    # pytest's own. The one test that wants it puts its own recorder here.
    monkeypatch.setattr(launcher, "hold_focus_in_background",
                        lambda previous, session: None)
    monkeypatch.setattr(
        launcher.console_input, "deliver_when_ready",
        lambda pid, commands, text: typed.update(
            pid=pid, commands=commands, text=text))
    return typed


def test_prompt_contains_each_body_verbatim():
    tricky = 'audio drifts\n---\n"quoted" and `backticks`\n\n  indented'
    prompt = launcher.build_prompt([make_task(42, "Replay audio desync", "BUG", tricky)])

    assert tricky in prompt
    assert prompt.startswith("BUG: ")


def test_prompt_gives_each_task_its_own_line_in_the_given_order():
    prompt = launcher.build_prompt([
        make_task(1, "First", "BUG", "body one"),
        make_task(2, "Second", "FEATURE", "body two"),
    ])

    assert prompt == "BUG: body one\nFEATURE: body two"


def test_prompt_format_is_exactly_type_colon_body():
    prompt = launcher.build_prompt([make_task(1, "Only", "BUG", "just this")])

    assert prompt == "BUG: just this"


def test_a_trailing_newline_does_not_become_a_blank_line_between_tasks():
    # Bodies read off disk end with the file's own newline, which would
    # otherwise double every separator.
    prompt = launcher.build_prompt([
        make_task(1, "First", "BUG", "body one\n"),
        make_task(2, "Second", "FEATURE", "body two\n"),
    ])

    assert prompt == "BUG: body one\nFEATURE: body two"


def test_nothing_selected_is_an_empty_prompt():
    assert launcher.build_prompt([]) == ""


def test_a_task_with_no_body_falls_back_to_its_title():
    # `BUG: ` on its own says nothing. The title is the only text the task has,
    # so it is what gets handed over — still verbatim, just a different field.
    prompt = launcher.build_prompt([make_task(1, "Replay audio desync", "BUG", "")])

    assert prompt == "BUG: Replay audio desync"


def test_a_whitespace_only_body_counts_as_no_body():
    prompt = launcher.build_prompt([make_task(1, "Replay audio desync", "BUG", "  \n\n")])

    assert prompt == "BUG: Replay audio desync"


def test_copy_prompt_puts_the_hand_off_text_on_the_clipboard(monkeypatch):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))
    task = make_task(1, "Replay audio desync", "BUG", "drifts after 3s")

    returned = launcher.copy_prompt([task])

    assert copied["text"] == "BUG: drifts after 3s"
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


def test_spawn_uses_a_new_console_in_the_project_directory(monkeypatch):
    captured = {}

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    launcher.spawn_claude(Path("C:/repos/sm64_tracker"))

    assert captured["args"] == [launcher.CONSOLE_HOST] + launcher.DEFAULT_LAUNCH
    assert captured["kwargs"]["cwd"] == Path("C:/repos/sm64_tracker")
    assert captured["kwargs"]["creationflags"] == launcher.NEW_CONSOLE


def test_the_session_is_launched_through_a_console_host_this_app_controls():
    """Otherwise the window belongs to whatever the machine's default terminal is.

    Windows delegates every new console to that setting. When it names Windows
    Terminal, WT creates the window and `SW_SHOWNOACTIVATE` is discarded, so
    the hand-off takes the keyboard — measured 2026-07-26, foreground moved
    within 400 ms and stayed. Going through conhost.exe opts out of the
    delegation and leaves the user's own terminal choice alone.
    """
    assert launcher.CONSOLE_HOST == "conhost.exe"


def test_the_typist_is_given_the_process_inside_the_console(monkeypatch):
    # AttachConsole refuses a console host's own pid, and every consumer of it
    # fails quietly — so the wrong pid here costs the rename, the colour, the
    # prompt and the font, with nothing said.
    monkeypatch.setattr(launcher, "_children_of", lambda pid: [CLIENT_PID])

    assert launcher.session_pid(FakeSession()) == CLIENT_PID


def test_a_console_that_never_starts_a_session_falls_back_to_the_host(monkeypatch):
    # Quietly, like everything else on this path: the window is open and the
    # prompt is on the clipboard, which is the whole fallback contract.
    monkeypatch.setattr(launcher, "_children_of", lambda pid: [])

    assert launcher.session_pid(FakeSession(), timeout=0) == FakeSession.pid


CONSOLE_WINDOW = 55


def watching(monkeypatch, foreground, window=CONSOLE_WINDOW):
    """A hand-off whose console window is `window` and foreground `foreground`."""
    handed = []
    monkeypatch.setattr(launcher.console_input, "console_window",
                        lambda pid: window)
    monkeypatch.setattr(launcher, "foreground_window", lambda: foreground)
    monkeypatch.setattr(launcher, "_activate", handed.append)
    return handed


def test_the_keyboard_is_handed_back_if_the_new_console_takes_it(monkeypatch):
    # Asking for an unactivated window is not a guarantee: measured 2026-07-26,
    # two spawns in ten took the foreground anyway. Invariant 10 says nothing
    # this app opens may take focus, so the ask is checked and undone.
    handed = watching(monkeypatch, foreground=CONSOLE_WINDOW)

    assert launcher.hold_focus(11, CLIENT_PID, seconds=0.05) is True
    assert handed == [11]


def test_a_window_the_user_moved_to_themselves_is_left_alone(monkeypatch):
    # Only this session's console counts as a thief. Someone who clicked away
    # to something else in the meantime keeps what they clicked on.
    handed = watching(monkeypatch, foreground=77)

    assert launcher.hold_focus(11, CLIENT_PID, seconds=0.05) is False
    assert handed == []


def test_nothing_is_handed_back_before_the_console_has_a_window(monkeypatch):
    handed = watching(monkeypatch, foreground=CONSOLE_WINDOW, window=0)

    assert launcher.hold_focus(11, CLIENT_PID, seconds=0.05) is False
    assert handed == []


def test_hand_off_watches_the_window_that_had_focus_before_the_spawn(
        tmp_path, monkeypatch, spawned):
    # Captured before, because after the spawn the window holding the keyboard
    # may already be the one we would be handing it back from.
    watched = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    monkeypatch.setattr(launcher, "foreground_window", lambda: 4321)
    monkeypatch.setattr(launcher, "hold_focus_in_background",
                        lambda previous, session: watched.update(
                            previous=previous, session=session))

    launcher.hand_off(tmp_path, [])

    assert watched == {"previous": 4321, "session": CLIENT_PID}


def test_the_new_console_opens_without_taking_focus(monkeypatch):
    # A hand-off is triggered mid-thought and mid-sentence. A console that
    # activates itself eats the next keystrokes and drops them into the new
    # session, so the window is asked to show without becoming active.
    captured = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(kwargs))

    launcher.spawn_claude(Path("C:/repos/x"))

    startup = captured["startupinfo"]
    assert startup.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startup.wShowWindow == launcher.SW_SHOWNOACTIVATE


def test_spawn_honours_a_per_project_launch_override(monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(args=args))

    launcher.spawn_claude(Path("C:/repos/x"), launch=["pwsh", "-c", "claude"])

    assert captured["args"] == [launcher.CONSOLE_HOST, "pwsh", "-c", "claude"]


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
    assert "drifts" in prompt


def test_hand_off_types_the_prompt_into_the_session_it_opened(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    # The session inside the console, not the console host that Popen named.
    assert spawned["pid"] == CLIENT_PID
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_opens_a_bare_session(
        tmp_path, monkeypatch, spawned):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))

    prompt = launcher.hand_off(tmp_path, [])

    # A session in the right directory, and nothing else touched: no text
    # typed, and whatever the user had on their clipboard still there. The
    # background thread still starts — with nothing to type it is there for
    # the console font alone, which this session needs as much as any other.
    assert prompt == ""
    assert spawned == {"pid": CLIENT_PID, "commands": [], "text": ""}
    assert copied == {}


def test_hand_off_leaves_tasks_untouched_when_the_session_cannot_start(tmp_path, monkeypatch):
    def exploding_popen(args, **kwargs):
        raise FileNotFoundError("claude is not on PATH")

    monkeypatch.setattr(subprocess, "Popen", exploding_popen)
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    with pytest.raises(FileNotFoundError):
        launcher.hand_off(tmp_path, [task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_spawn_skips_permission_prompts_by_default(monkeypatch):
    captured = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(args=args))

    launcher.spawn_claude(Path("C:/repos/x"))

    assert captured["args"] == [launcher.CONSOLE_HOST, "claude",
                                "--dangerously-skip-permissions"]


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

    assert prompt == "BUG: body one\nFEATURE: body two"
    assert {t.group for t in store.list_tasks(repo)} == {"First"}
    assert {t.status for t in store.list_tasks(repo)} == {"in-progress"}


# What the spawned session's environment must look like is tested in
# tests/test_user_environment.py — it is now rebuilt from Windows rather than
# filtered out of this process's own environment.


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
    task = make_task(1, f"Fix it{launcher.console_input.PASTE_END}/exit", "FEATURE", "b")

    name = launcher.session_name([task])

    assert launcher.console_input.PASTE_END not in name
    assert "\x1b" not in name
    assert name == "FEATURE: Fix it[201~/exit"


def test_a_given_name_is_stripped_of_control_characters_too():
    # The given-name path returns before the title path is ever reached, so it
    # needs its own defence rather than inheriting the title's.
    task = make_task(1, "Short", "FEATURE", "b")

    name = launcher.session_name([task], f"Editor\x1b polish{launcher.console_input.PASTE_END}")

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


def test_capping_to_no_room_at_all_yields_nothing():
    # text[:limit - 1] with limit 0 is text[:-1] — very nearly the whole
    # string, for a limit of zero. Unreachable from session_name today; the
    # next caller passing a computed limit is who this is for.
    assert launcher._cap("Rename the spawned session", 0) == ""


def test_a_long_title_is_capped_but_the_count_survives():
    tasks = [make_task(1, "R" * 200, "FEATURE", "b"),
             make_task(2, "Second", "FEATURE", "b"),
             make_task(3, "Third", "FEATURE", "b")]

    name = launcher.session_name(tasks)

    assert len(name) <= launcher.SESSION_NAME_LIMIT
    assert name.startswith("FEATURE: ")
    assert name.endswith(" (+2)")


def test_a_long_given_name_is_capped_too():
    task = make_task(1, "Short", "FEATURE", "b")

    name = launcher.session_name([task], "E" * 200)

    assert len(name) <= launcher.SESSION_NAME_LIMIT


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

    assert len(launcher.session_name([task])) <= launcher.SESSION_NAME_LIMIT


def test_session_color_is_the_first_selected_task_s():
    tasks = [make_task(1, "First", "FEATURE", "b", color="purple"),
             make_task(2, "Second", "FEATURE", "b", color="red")]

    assert launcher.session_color(tasks) == "purple"


def test_nothing_selected_has_no_colour():
    assert launcher.session_color([]) is None


def test_setup_commands_renames_then_colours():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b",
                     color="purple")

    assert launcher.setup_commands([task]) == [
        "/rename FEATURE: Rename the spawned session",
        "/color purple",
    ]


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

    assert len(name) == launcher.SESSION_NAME_LIMIT
    assert name.startswith("TTT")


def test_hand_off_renames_and_colours_the_session_it_opened(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG",
                             color="purple")

    launcher.hand_off(tmp_path, [task])

    assert spawned["commands"] == ["/rename BUG: Replay audio desync",
                                   "/color purple"]


def test_hand_off_uses_the_name_it_was_given(tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    first = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")
    second = store.create_task(tmp_path, "Chips rewrite the row", "x", "BUG")

    launcher.hand_off(tmp_path, [first, second], name="Editor polish")

    assert spawned["commands"][0] == "/rename Editor polish"


def test_the_commands_are_sent_before_the_prompt_is_typed(
        tmp_path, monkeypatch, spawned):
    # Ordering is the whole safety argument: if both commands fail, the session
    # still ends up where it lands today — task text sitting editable.
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    assert spawned["commands"][0].startswith("/rename ")
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_sends_no_commands(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)

    launcher.hand_off(tmp_path, [])

    assert spawned["commands"] == []
    assert spawned["text"] == ""
