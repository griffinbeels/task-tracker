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


def test_prompt_contains_each_body_verbatim():
    tricky = 'audio drifts\n---\n"quoted" and `backticks`\n\n  indented'
    prompt = launcher.build_prompt([make_task(42, "Replay audio desync", "BUG", tricky)])

    assert tricky in prompt
    assert "## BUG 42 - Replay audio desync" in prompt


def test_prompt_joins_multiple_tasks_in_the_given_order():
    prompt = launcher.build_prompt([
        make_task(1, "First", "BUG", "body one"),
        make_task(2, "Second", "FEATURE", "body two"),
    ])

    assert prompt.index("body one") < prompt.index("## FEATURE 2 - Second")


def test_prompt_format_is_exactly_header_blank_line_body():
    prompt = launcher.build_prompt([make_task(1, "Only", "BUG", "just this")])

    assert prompt == "## BUG 1 - Only\n\njust this"


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


def test_hand_off_marks_tasks_in_progress_and_copies_the_prompt(tmp_path, monkeypatch):
    copied = {}
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kwargs: None)
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: copied.update(text=text))
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "in-progress"
    assert reloaded.started is not None
    assert copied["text"] == prompt
    assert "drifts" in prompt


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
