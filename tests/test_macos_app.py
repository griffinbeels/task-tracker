"""Packaging identity and entry-point contracts; no native window is opened."""
import json
from pathlib import Path

import pytest

from tools import build_macos_app, macos_entry


def test_worktree_bundle_cannot_overwrite_daily_app(tmp_path, monkeypatch):
    primary = tmp_path / "tracker"
    feature = primary / "any" / "nested" / "feature ü"
    monkeypatch.setattr(build_macos_app, "primary_checkout", lambda path: primary)
    preview = build_macos_app.bundle_settings(feature)
    daily = build_macos_app.bundle_settings(primary)
    assert preview["path"].parent == feature / "dist"
    assert daily["path"].parent == primary / "dist"
    assert preview["identifier"] != daily["identifier"]
    assert "Preview" in preview["name"]


def test_linked_worktree_keeps_preview_identity_even_without_git(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text("gitdir: somewhere\n")
    monkeypatch.setattr(build_macos_app, "primary_checkout", lambda path: path)
    settings = build_macos_app.bundle_settings(tmp_path)
    assert "Preview" in settings["name"]
    # App and direct source launch use one config-derived lock identity.
    assert "port" not in settings
    import singleton
    monkeypatch.delenv("TASK_TRACKER_PORT", raising=False)
    monkeypatch.setenv("TASK_TRACKER_CONFIG_DIR", settings["config_dir"])
    assert singleton.configured_port() != 8090
    assert Path(settings["config_dir"]).is_relative_to(tmp_path)


def test_app_preflight_failure_reports_error_before_app_code(tmp_path, monkeypatch):
    monkeypatch.setattr(macos_entry, "source_checkout", lambda: tmp_path)
    errors = []
    monkeypatch.setattr(macos_entry, "report_error", lambda source, text: errors.append(text))
    monkeypatch.setattr(macos_entry, "ensure_environment", lambda source: (_ for _ in ()).throw(RuntimeError("repair required")))
    monkeypatch.setattr(macos_entry.runpy, "run_path", lambda *args, **kwargs: pytest.fail("app ran after failed preflight"))
    assert macos_entry.main() == 1
    assert "repair required" in errors[0]


def test_alias_entry_runs_intended_live_source_and_passes_bundle_to_restart(tmp_path, monkeypatch):
    source = tmp_path / "worktree ü"
    source.mkdir()
    bundle = source / "dist" / "Task Tracker Preview.app"
    monkeypatch.setattr(macos_entry, "source_checkout", lambda: source)
    monkeypatch.setattr(macos_entry, "ensure_environment", lambda path: source / "console")
    monkeypatch.setattr(macos_entry, "app_bundle", lambda: bundle)
    monkeypatch.setattr(macos_entry.os, "chdir", lambda path: None)
    monkeypatch.setenv("CLAUDE_CONSOLE_PATH", "unused")
    calls = []
    monkeypatch.setattr(macos_entry.runpy, "run_path", lambda *args, **kwargs: calls.append((args, kwargs)))
    assert macos_entry.main() == 0
    assert calls == [((str(source / "app.py"),), {"run_name": "__main__"})]
    assert macos_entry.os.environ["TASK_TRACKER_APP_BUNDLE"] == str(bundle)


def test_packager_uses_alias_mode_and_local_venv(tmp_path):
    settings = {"name": "Task Tracker", "identifier": "local.tasktracker", "path": tmp_path / "dist" / "Task Tracker.app"}
    setup = build_macos_app.setup_source(tmp_path, settings)
    assert "alias" in setup
    assert "argv_emulation" in setup and "False" in setup
    assert str(tmp_path / "tools" / "macos_entry.py") in setup
    assert "LSUIElement" not in setup
    assert "NSAppleEventsUsageDescription" in setup


def test_bundle_preflight_only_cannot_reach_native_errors_or_app_code(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(macos_entry, "source_checkout", lambda: tmp_path)
    monkeypatch.setattr(macos_entry, "app_bundle", lambda: None)
    monkeypatch.setattr(macos_entry, "ensure_environment", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("missing package")))
    monkeypatch.setattr(macos_entry, "report_error", lambda *args: pytest.fail("native error opened"))
    monkeypatch.setattr(macos_entry.runpy, "run_path", lambda *args, **kwargs: pytest.fail("app code ran"))
    assert macos_entry.main(check_only=True) == 1
    assert "missing package" in capsys.readouterr().err
