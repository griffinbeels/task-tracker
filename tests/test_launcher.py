import subprocess
from pathlib import Path

import pytest

import launcher
import store


def make_task(task_id, title, type, body, color=""):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
        color=color,
    )


class FakeSession:
    """Stands in for the Popen of a spawned session."""
    pid = 4242


@pytest.fixture
def spawned(monkeypatch):
    """Swallow the process spawn and record what would have been sent to it."""
    typed = {}
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeSession())
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

    assert captured["args"] == launcher.DEFAULT_LAUNCH
    assert captured["kwargs"]["cwd"] == Path("C:/repos/sm64_tracker")
    assert captured["kwargs"]["creationflags"] == launcher.NEW_CONSOLE


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

    assert captured["args"] == ["pwsh", "-c", "claude"]


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

    assert spawned["pid"] == FakeSession.pid
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_opens_a_bare_session(
        tmp_path, monkeypatch, spawned):
    copied = {}
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))

    prompt = launcher.hand_off(tmp_path, [])

    # A session in the right directory, and nothing else touched: no text
    # typed, and whatever the user had on their clipboard still there.
    assert prompt == ""
    assert spawned == {}
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

    assert captured["args"] == ["claude", "--dangerously-skip-permissions"]


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

    assert spawned == {}
