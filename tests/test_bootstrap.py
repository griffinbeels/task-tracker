"""Startup contracts, without opening a tracker or touching personal settings."""
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools import bootstrap


def checkout(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "pyproject.toml").write_text('[project]\nname="claude-console"\n')
    return path


@pytest.mark.parametrize("name", ["claude-console", "claude_console"])
def test_dependency_discovery_uses_git_identity_at_any_worktree_depth(tmp_path, monkeypatch, name):
    primary = tmp_path / "projects ü" / "tracker"
    source = primary / "arbitrary" / "depth" / "feature"
    source.mkdir(parents=True)
    console = checkout(primary.parent / name)
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, str(primary / ".git") + "\n", "")

    monkeypatch.setattr(bootstrap.subprocess, "run", run)
    assert bootstrap.find_console(source, {}) == console.resolve()
    assert calls[0][1]["cwd"] == source
    assert "--git-common-dir" in calls[0][0]


def test_invalid_explicit_dependency_does_not_silently_fall_back(tmp_path):
    source = checkout(tmp_path / "tracker")
    checkout(tmp_path / "claude-console")
    with pytest.raises(bootstrap.BootstrapError, match="CLAUDE_CONSOLE_PATH"):
        bootstrap.find_console(source, {"CLAUDE_CONSOLE_PATH": str(tmp_path / "missing")})


def test_explicit_override_must_be_the_console_package_not_an_unrelated_project(tmp_path):
    unrelated = checkout(tmp_path / "other")
    (unrelated / "pyproject.toml").write_text('[project]\nname="another-package"\n')
    with pytest.raises(bootstrap.BootstrapError, match="CLAUDE_CONSOLE_PATH"):
        bootstrap.find_console(tmp_path, {"CLAUDE_CONSOLE_PATH": str(unrelated)})


def test_finder_sparse_path_still_finds_uv(tmp_path, monkeypatch):
    executable = tmp_path / ".local" / "bin" / "uv"
    executable.parent.mkdir(parents=True)
    executable.touch(mode=0o755)
    monkeypatch.setattr(bootstrap.shutil, "which", lambda *args, **kwargs: None)
    assert bootstrap.find_uv({}, tmp_path) == executable


def test_warm_start_is_offline_and_preserves_editable_checkout(tmp_path, monkeypatch):
    console = checkout(tmp_path / "console")
    monkeypatch.setattr(bootstrap, "find_console", lambda *args: console)
    monkeypatch.setattr(bootstrap, "find_uv", lambda *args: Path("uv"))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(bootstrap, "run", run)
    assert bootstrap.ensure_environment(tmp_path) == console
    assert all("install" not in command for command in calls)
    assert any("check" in command for command in calls)


def test_broken_offline_environment_reports_repair_and_never_launches(tmp_path, monkeypatch):
    console = checkout(tmp_path / "console")
    monkeypatch.setattr(bootstrap, "find_console", lambda *args: console)
    monkeypatch.setattr(bootstrap, "find_uv", lambda *args: Path("uv"))
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 1, "", "missing dependency; index unavailable")

    monkeypatch.setattr(bootstrap, "run", run)
    with pytest.raises(bootstrap.BootstrapError, match="run.command|run.bat"):
        bootstrap.ensure_environment(tmp_path)
    install = next(command for command in calls if "install" in command)
    assert list(map(str, install[-4:])) == ["-e", str(console), "-e", str(tmp_path)]
    assert not any("app.py" in command for command in calls)


def test_dependency_change_is_detected_even_when_old_installed_metadata_is_coherent(tmp_path, monkeypatch):
    source = checkout(tmp_path / "tracker")
    (source / "pyproject.toml").write_text('[project]\nname="task-tracker"\ndependencies=["new-library>=2"]\n')

    class Distribution:
        requires = ["old-library"]

        def read_text(self, name):
            return json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})

    monkeypatch.setattr(bootstrap.metadata, "distribution", lambda name: Distribution())
    with pytest.raises(bootstrap.BootstrapError, match="requirements changed"):
        bootstrap.check_editable("task-tracker", source)


def test_installed_editable_from_another_worktree_is_not_ready(tmp_path, monkeypatch):
    source = checkout(tmp_path / "wanted")
    other = checkout(tmp_path / "another")

    class Distribution:
        requires = []

        def read_text(self, name):
            return json.dumps({"url": other.as_uri(), "dir_info": {"editable": True}})

    monkeypatch.setattr(bootstrap.metadata, "distribution", lambda name: Distribution())
    with pytest.raises(bootstrap.BootstrapError, match="different checkout"):
        bootstrap.check_editable("task-tracker", source)


def test_requirement_metadata_quote_formatting_does_not_force_repair_forever(tmp_path, monkeypatch):
    source = checkout(tmp_path / "tracker café Ω")
    (source / "pyproject.toml").write_text('''[project]
name="task-tracker"
dependencies=["native-library; sys_platform == 'darwin'"]
''')

    class Distribution:
        requires = ['native-library; sys_platform == "darwin"']

        def read_text(self, name):
            return json.dumps({"url": source.as_uri(), "dir_info": {"editable": True}})

    monkeypatch.setattr(bootstrap.metadata, "distribution", lambda name: Distribution())
    bootstrap.check_editable("task-tracker", source)


def test_setup_launch_explicitly_forwards_isolation_through_launchservices(monkeypatch):
    monkeypatch.setenv("TASK_TRACKER_CONFIG_DIR", "/tmp/fixture ü")
    monkeypatch.setenv("TASK_TRACKER_PORT", "18234")
    monkeypatch.setenv("CLAUDE_CONSOLE_PATH", "/tmp/console ü")
    command = bootstrap.mac_open_command(Path("/tmp/Tracker Preview.app"))
    assert command[:2] == ["/usr/bin/open", "-n"]
    assert "TASK_TRACKER_CONFIG_DIR=/tmp/fixture ü" in command
    assert "TASK_TRACKER_PORT=18234" in command
    assert "CLAUDE_CONSOLE_PATH=/tmp/console ü" in command
    assert command[-1] == "/tmp/Tracker Preview.app"


def test_windows_bootstrap_suppresses_background_ui_with_python312_flags(monkeypatch):
    startup = SimpleNamespace(dwFlags=0, wShowWindow=None)
    monkeypatch.setattr(bootstrap.sys, "platform", "win32")
    monkeypatch.setattr(bootstrap.subprocess, "STARTUPINFO", lambda: startup, raising=False)
    monkeypatch.setattr(bootstrap.subprocess, "STARTF_USESHOWWINDOW", 1, raising=False)
    monkeypatch.setattr(bootstrap.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(bootstrap.subprocess, "SW_HIDE", 0, raising=False)
    # Python 3.12 does not re-export this Win32 flag from subprocess.
    monkeypatch.delattr(bootstrap.subprocess, "STARTF_FORCEOFFFEEDBACK", raising=False)
    captured = []
    monkeypatch.setattr(bootstrap.subprocess, "run", lambda args, **kwargs: captured.append(kwargs))
    bootstrap.run(["uv", "pip", "check"])
    assert captured[0]["creationflags"] == 0x08000000
    assert captured[0]["startupinfo"].dwFlags & 0x80
    assert captured[0]["startupinfo"].wShowWindow == 0


def test_mac_check_only_does_not_build_install_or_launch(monkeypatch):
    from tools import bootstrap
    calls = []
    monkeypatch.setattr(bootstrap, "ensure_environment", lambda *args, **kwargs: calls.append(kwargs) or bootstrap.REPO)
    # Build/install imports happen only on the mutation path. With those imports
    # unavailable this call still succeeds without invoking any subprocess.
    monkeypatch.setattr(bootstrap, "run", lambda *args, **kwargs: pytest.fail("check-only launched a process"))
    assert bootstrap.main(["--mac-app", "--check-only", "--install"]) == 0
    assert calls == [{"check_only": True}]
