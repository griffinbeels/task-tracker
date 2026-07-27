import subprocess
import sys
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

    assert spawned.kwargs["creationflags"] & restart.NO_WINDOW


def test_it_does_not_take_focus(spawned):
    """Invariant 10 — a window that activates itself swallows your keystrokes."""
    restart.spawn_replacement()

    startup = spawned.kwargs["startupinfo"]
    assert startup.dwFlags & subprocess.STARTF_USESHOWWINDOW
    assert startup.wShowWindow == claude_console.SW_SHOWNOACTIVATE
