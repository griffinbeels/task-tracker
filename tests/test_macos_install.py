"""Applications always follows the daily checkout, without replacing other apps."""
import json
import shutil

import pytest

from tools import install_macos_app
from tools.bootstrap import BootstrapError


@pytest.fixture
def daily(tmp_path, monkeypatch):
    source = tmp_path / "tracker ü"
    (source / ".git").mkdir(parents=True)
    console = tmp_path / "console"
    (console / ".git").mkdir(parents=True)
    bundle = source / "dist/Task Tracker.app"
    resources = bundle / "Contents/Resources"
    resources.mkdir(parents=True)
    (resources / "task-tracker.json").write_text(json.dumps({"source": str(source), "console": str(console)}))
    monkeypatch.setattr(install_macos_app.sys, "platform", "darwin")
    monkeypatch.setattr(install_macos_app, "primary_checkout", lambda path: source)
    return source, bundle, tmp_path / "Applications"


def test_dry_run_then_install_and_rebuild_follow_one_live_target(daily):
    source, bundle, applications = daily
    installed = install_macos_app.install(source, applications, dry_run=True)
    assert not applications.exists()
    assert installed == applications / "Task Tracker.app"
    install_macos_app.install(source, applications)
    assert installed.is_symlink() and installed.resolve() == bundle
    # A replacement bundle at the stable path is visible without reinstalling.
    shutil.rmtree(bundle)
    bundle.mkdir()
    (bundle / "new-version").write_text("updated")
    assert (installed / "new-version").read_text() == "updated"


def test_install_is_idempotent(daily):
    source, bundle, applications = daily
    first = install_macos_app.install(source, applications)
    assert install_macos_app.install(source, applications) == first
    assert first.resolve() == bundle


@pytest.mark.parametrize("foreign_kind", ["directory", "file", "broken-link"])
def test_foreign_app_is_never_replaced(daily, foreign_kind):
    source, _, applications = daily
    applications.mkdir()
    target = applications / "Task Tracker.app"
    if foreign_kind == "directory":
        target.mkdir()
    elif foreign_kind == "file":
        target.write_text("mine")
    else:
        target.symlink_to(applications / "missing")
    with pytest.raises(BootstrapError, match="already exists"):
        install_macos_app.install(source, applications)
    assert target.exists() or target.is_symlink()


def test_preview_cannot_be_installed_even_if_git_lookup_falls_back(daily):
    source, _, applications = daily
    (source / ".git").rmdir()
    (source / ".git").write_text("gitdir: linked-worktree")
    with pytest.raises(BootstrapError, match="primary checkout"):
        install_macos_app.install(source, applications)
    assert not applications.exists()


@pytest.mark.parametrize("override", ["source", "config_dir", "console"])
def test_bundle_cannot_keep_a_preview_dependency(daily, override):
    source, bundle, applications = daily
    manifest = bundle / "Contents/Resources/task-tracker.json"
    config = json.loads(manifest.read_text())
    preview = source / "preview"
    preview.mkdir()
    (preview / ".git").write_text("gitdir: linked-worktree")
    config[override] = str(preview)
    manifest.write_text(json.dumps(config))
    with pytest.raises(BootstrapError):
        install_macos_app.install(source, applications)
    assert not applications.exists()
