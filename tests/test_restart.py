import subprocess
import sys
import os
from pathlib import Path

import claude_console
import pytest

import restart


class FakeSpawn:
    """Records what would have been launched, and launches nothing."""

    def __init__(self):
        self.args = None
        self.kwargs = None

    def __call__(self, args, **kwargs):
        self.args, self.kwargs = args, kwargs
        return object()


@pytest.fixture
def spawned(monkeypatch):
    fake = FakeSpawn()
    monkeypatch.setattr(subprocess, "Popen", fake)
    monkeypatch.delenv("TASK_TRACKER_APP_BUNDLE", raising=False)
    return fake


def fake_install(tmp_path, *executables):
    """A Scripts directory holding the named interpreters."""
    for name in executables:
        (tmp_path / name).write_text("", encoding="utf-8")
    return tmp_path


def test_it_launches_this_projects_entry_point(spawned):
    restart.spawn_replacement()

    entry_point = Path(spawned.args[1])
    assert entry_point.name == "app.py"
    assert entry_point.parent == restart.APP_ROOT


def test_it_runs_from_the_project_root_whatever_the_working_directory_is(spawned):
    restart.spawn_replacement()

    assert Path(spawned.kwargs["cwd"]) == restart.APP_ROOT


def test_it_prefers_the_windowless_interpreter_beside_the_running_one(
        tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    scripts = fake_install(tmp_path, "python.exe", "pythonw.exe")
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))

    assert restart.interpreter() == str(scripts / "pythonw.exe")


def test_it_falls_back_to_the_running_interpreter_when_there_is_no_windowless_one(
        tmp_path, monkeypatch):
    scripts = fake_install(tmp_path, "python.exe")
    monkeypatch.setattr(sys, "executable", str(scripts / "python.exe"))

    assert restart.interpreter() == str(scripts / "python.exe")


def test_it_opens_no_console_window(spawned):
    restart.spawn_replacement()

    if sys.platform == "win32":
        assert spawned.kwargs["creationflags"] & restart.NO_WINDOW
    else:
        assert "creationflags" not in spawned.kwargs
        assert "startupinfo" not in spawned.kwargs
        assert spawned.kwargs["start_new_session"] is True


@pytest.mark.skipif(sys.platform != "win32", reason="Windows startup structure")
def test_it_does_not_take_focus(spawned):
    """Invariant 10 — a window that activates itself swallows your keystrokes."""
    restart.spawn_replacement()

    startup = spawned.kwargs["startupinfo"]
    assert startup.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startup.wShowWindow == claude_console.SW_SHOWNOACTIVATE


def test_mac_ignores_a_pythonw_filename(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    scripts = fake_install(tmp_path, "python", "pythonw.exe")
    monkeypatch.setattr(sys, "executable", str(scripts / "python"))
    assert restart.interpreter() == str(scripts / "python")


def test_mac_restarts_the_same_app_bundle_and_preserves_configuration(
        spawned, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "darwin")
    bundle = tmp_path / "Task Tracker Preview.app"
    bundle.mkdir()
    monkeypatch.setenv("TASK_TRACKER_APP_BUNDLE", str(bundle))
    monkeypatch.setenv("TASK_TRACKER_CONFIG_DIR", str(tmp_path / "data"))

    restart.spawn_replacement()

    assert spawned.args[:3] == ["/usr/bin/open", "-n", str(bundle)]
    # LaunchServices does not inherit open's environment. An explicit override
    # must therefore travel to the new application, not only the open process.
    assert "--env" in spawned.args
    assert f"TASK_TRACKER_CONFIG_DIR={tmp_path / 'data'}" in spawned.args


def test_windows_restart_keeps_its_windowless_process_flags(spawned, monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    startup = object()
    monkeypatch.setattr(claude_console, "unfocused_startup", lambda: startup)
    monkeypatch.setattr(restart, "NO_WINDOW", 0x08000000)

    restart.spawn_replacement()

    assert spawned.kwargs["creationflags"] == 0x08000000
    assert spawned.kwargs["startupinfo"] is startup
    assert "start_new_session" not in spawned.kwargs
