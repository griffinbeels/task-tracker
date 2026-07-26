import subprocess
from pathlib import Path

import pytest

import launcher
import store


def make_task(task_id, title, type, body):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
    )


class FakeSession:
    """Stands in for the Popen of a spawned session."""
    pid = 4242


@pytest.fixture
def spawned(monkeypatch):
    """Swallow the process spawn and record what would have been typed."""
    typed = {}
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeSession())
    monkeypatch.setattr(launcher.console_input, "paste_when_ready",
                        lambda pid, text: typed.update(pid=pid, text=text))
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

    assert spawned == {"pid": FakeSession.pid, "text": prompt}


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
