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


def test_spawned_session_does_not_inherit_the_nested_session_marker(monkeypatch):
    captured = {}
    monkeypatch.setenv("CLAUDE_CODE_CHILD_SESSION", "1")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "abc-123")
    monkeypatch.setenv("CLAUDE_PID", "20380")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(kwargs))

    launcher.spawn_claude(Path("C:/repos/x"))

    environment = captured["env"]
    assert "CLAUDE_CODE_CHILD_SESSION" not in environment
    assert "CLAUDE_CODE_SESSION_ID" not in environment
    assert "CLAUDE_PID" not in environment
    assert environment["CLAUDE_CODE_FORCE_SESSION_PERSISTENCE"] == "1"


def test_spawned_session_keeps_the_rest_of_the_environment(monkeypatch):
    captured = {}
    monkeypatch.setenv("SOME_UNRELATED_VAR", "keep me")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(kwargs))

    launcher.spawn_claude(Path("C:/repos/x"))

    assert captured["env"]["SOME_UNRELATED_VAR"] == "keep me"
