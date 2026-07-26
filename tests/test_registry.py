import json

import pytest

import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def test_settings_default_when_no_file_exists():
    settings = registry.load_settings()

    assert settings.group_limit == 5
    assert settings.stale_days == 90
    assert [t.name for t in settings.types] == ["BUG", "FEATURE", "ITERATION"]


def test_settings_round_trip(tmp_path):
    settings = registry.load_settings()
    settings.group_limit = 3
    settings.types.append(registry.TaskType("CHORE", "#8e8e8e"))
    registry.save_settings(settings)

    reloaded = registry.load_settings()
    assert reloaded.group_limit == 3
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


def test_corrupt_projects_json_falls_back_to_empty(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "projects.json").write_text("{not json", encoding="utf-8", newline="\n")

    assert registry.load_projects() == []


def test_an_old_settings_file_carries_its_wip_limit_over(tmp_path):
    # The limit used to count tasks and was called wip_limit. A user's existing
    # settings.json must keep their number rather than silently reverting to 5.
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"wip_limit": 3, "stale_days": 90, "types": []}),
        encoding="utf-8", newline="\n")

    assert registry.load_settings().group_limit == 3


def test_the_new_key_wins_over_the_old_one(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "settings.json").write_text(
        json.dumps({"group_limit": 7, "wip_limit": 3, "types": []}),
        encoding="utf-8", newline="\n")

    assert registry.load_settings().group_limit == 7


def test_saving_drops_the_old_key(tmp_path):
    registry.save_settings(registry.Settings(group_limit=4))

    raw = json.loads((registry.CONFIG_DIR / "settings.json").read_text(encoding="utf-8"))
    assert raw["group_limit"] == 4
    assert "wip_limit" not in raw


def test_unknown_keys_in_projects_json_are_ignored(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    raw = json.loads((registry.CONFIG_DIR / "projects.json").read_text(encoding="utf-8"))
    raw[0]["icon"] = "sparkle"
    (registry.CONFIG_DIR / "projects.json").write_text(
        json.dumps(raw), encoding="utf-8", newline="\n")

    projects = registry.load_projects()

    assert len(projects) == 1
    assert projects[0].name == "repo"


def test_nothing_is_selected_before_a_project_has_been_chosen(tmp_path):
    assert registry.last_project() is None


def test_the_selected_project_round_trips(tmp_path):
    registry.set_last_project("task_tracker")

    assert registry.last_project() == "task_tracker"


def test_saving_settings_does_not_forget_the_selected_project(tmp_path):
    # This is why the selection lives in its own file rather than on Settings:
    # Api.save_settings rebuilds the whole dataclass from the three fields the
    # settings overlay sends, so a field stored there would be silently wiped
    # every time those settings were saved.
    registry.set_last_project("task_tracker")

    registry.save_settings(registry.Settings(group_limit=4))

    assert registry.last_project() == "task_tracker"


def test_a_corrupt_session_file_selects_nothing(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "session.json").write_text(
        "{not json", encoding="utf-8", newline="\n")

    assert registry.last_project() is None
