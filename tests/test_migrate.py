import shutil

import pytest

import migrate
import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


def make_project(tmp_path, name):
    repo = tmp_path / name
    repo.mkdir()
    registry.add_project(name, str(repo))
    return repo


def test_rename_rewrites_open_and_done_across_every_project(tmp_path):
    first = make_project(tmp_path, "alpha")
    second = make_project(tmp_path, "beta")
    store.create_task(first, "A", "body", "FEATURE")
    store.complete_task(store.create_task(first, "B", "body", "FEATURE"))
    store.create_task(second, "C", "body", "FEATURE")
    store.create_task(second, "D", "body", "BUG")

    result = migrate.rename_type("FEATURE", "FEAT")

    assert result.changed == 3
    assert result.skipped == []
    assert {t.type for t in store.list_tasks(first)} == {"FEAT"}
    assert {t.type for t in store.list_tasks(second)} == {"FEAT", "BUG"}


def test_rename_updates_the_settings_type_list(tmp_path):
    make_project(tmp_path, "alpha")

    migrate.rename_type("FEATURE", "FEAT")

    assert [t.name for t in registry.load_settings().types] == ["BUG", "FEAT", "ITERATION"]


def test_rename_preserves_the_task_body_verbatim(tmp_path):
    repo = make_project(tmp_path, "alpha")
    tricky = 'line one\n---\n"quoted" and `backticks`'
    store.create_task(repo, "A", tricky, "FEATURE")

    migrate.rename_type("FEATURE", "FEAT")

    assert store.list_tasks(repo)[0].body == tricky


def test_delete_reassigns_tasks_then_removes_the_type(tmp_path):
    repo = make_project(tmp_path, "alpha")
    store.create_task(repo, "A", "body", "ITERATION")

    result = migrate.delete_type("ITERATION", "FEATURE")

    assert result.changed == 1
    assert store.list_tasks(repo)[0].type == "FEATURE"
    assert [t.name for t in registry.load_settings().types] == ["BUG", "FEATURE"]


def test_delete_rejects_a_replacement_that_does_not_exist(tmp_path):
    make_project(tmp_path, "alpha")

    with pytest.raises(ValueError):
        migrate.delete_type("ITERATION", "NONSENSE")


def test_unreachable_project_is_skipped_not_fatal(tmp_path):
    reachable = make_project(tmp_path, "alpha")
    missing = tmp_path / "gone"
    missing.mkdir()
    registry.add_project("beta", str(missing))
    store.create_task(reachable, "A", "body", "FEATURE")
    shutil.rmtree(missing)

    result = migrate.rename_type("FEATURE", "FEAT")

    assert result.changed == 1
    assert result.skipped == ["beta"]


def test_project_without_a_tasks_dir_is_swept_not_skipped(tmp_path):
    reachable = make_project(tmp_path, "alpha")
    bare = make_project(tmp_path, "beta")
    store.create_task(reachable, "A", "body", "FEATURE")
    shutil.rmtree(bare / ".tasks")

    result = migrate.rename_type("FEATURE", "FEAT")

    assert result.skipped == []
    assert result.changed == 1


def test_count_tasks_with_type_spans_projects_and_archives(tmp_path):
    first = make_project(tmp_path, "alpha")
    second = make_project(tmp_path, "beta")
    store.create_task(first, "A", "body", "BUG")
    store.complete_task(store.create_task(second, "B", "body", "BUG"))

    assert migrate.count_tasks_with_type("BUG") == 2
