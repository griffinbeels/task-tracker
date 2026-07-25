import pytest

import app
import registry
import store


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(app, "WINDOW_STATE", tmp_path / "config" / "window.json")


def make_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    registry.add_project("repo", str(repo))
    return repo


def test_update_task_rejects_an_unknown_bucket(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"bucket": "urgent"})

    assert store.list_tasks(repo)[0].bucket == "now"


def test_update_task_rejects_an_unknown_status(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"status": "blocked"})

    assert store.list_tasks(repo)[0].status == "open"


def test_update_task_applies_a_valid_bucket_change(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    app.Api().update_task("repo", task.id, {"bucket": "someday"})

    assert store.list_tasks(repo)[0].bucket == "someday"


def test_corrupt_window_state_falls_back_to_defaults():
    app.WINDOW_STATE.parent.mkdir(parents=True, exist_ok=True)
    app.WINDOW_STATE.write_text("{not json", encoding="utf-8")

    state = app._load_window_state()

    assert state["width"] == 420
    assert state["on_top"] is True
