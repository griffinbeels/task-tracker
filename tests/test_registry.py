import pytest

import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def test_settings_default_when_no_file_exists():
    settings = registry.load_settings()

    assert settings.wip_limit == 5
    assert settings.stale_days == 90
    assert [t.name for t in settings.types] == ["BUG", "FEATURE", "ITERATION"]


def test_settings_round_trip(tmp_path):
    settings = registry.load_settings()
    settings.wip_limit = 3
    settings.types.append(registry.TaskType("CHORE", "#8e8e8e"))
    registry.save_settings(settings)

    reloaded = registry.load_settings()
    assert reloaded.wip_limit == 3
    assert [t.name for t in reloaded.types] == ["BUG", "FEATURE", "ITERATION", "CHORE"]


def test_add_project_creates_tasks_dir_untracked(tmp_path):
    repo = tmp_path / "sm64_tracker"
    repo.mkdir()

    project = registry.add_project("sm64_tracker", str(repo))

    assert project.tracked is False
    assert (repo / ".tasks" / "open").is_dir()
    assert (repo / ".tasks" / ".gitignore").exists()


def test_add_project_rejects_a_duplicate_name(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))

    with pytest.raises(ValueError):
        registry.add_project("repo", str(repo))


def test_set_project_tracked_flips_the_gitignore(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))

    registry.set_project_tracked("repo", True)
    assert not (repo / ".tasks" / ".gitignore").exists()
    assert registry.load_projects()[0].tracked is True

    registry.set_project_tracked("repo", False)
    assert (repo / ".tasks" / ".gitignore").exists()


def test_remove_project_leaves_the_task_files_on_disk(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    store.create_task(repo, "Keep me", "body", "BUG")

    registry.remove_project("repo")

    assert registry.load_projects() == []
    assert (repo / ".tasks" / "open" / "0001-keep-me.md").exists()


def test_add_project_rejects_a_path_that_is_not_a_directory(tmp_path):
    missing = tmp_path / "typo"

    with pytest.raises(ValueError):
        registry.add_project("typo", str(missing))

    assert not missing.exists()
    assert registry.load_projects() == []


def test_config_files_are_written_with_lf_endings(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))

    assert b"\r" not in (registry.CONFIG_DIR / "projects.json").read_bytes()
