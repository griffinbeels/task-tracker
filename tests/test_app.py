import pytest

import app
import registry
import restart
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


def test_update_task_rejects_a_non_integer_order(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"order": "abc"})


def test_update_task_rejects_a_non_string_title(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"title": 42})


def test_update_task_moves_a_task_between_buckets(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    app.Api().update_task("repo", task.id, {"bucket": "someday", "order": 0})

    assert store.list_tasks(repo)[0].bucket == "someday"


def test_hand_off_rejects_an_id_that_does_not_exist(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().hand_off("repo", [999])


def test_copy_task_prompt_copies_one_task_in_the_hand_off_format(tmp_path, monkeypatch):
    copied = {}
    monkeypatch.setattr(app.launcher.pyperclip, "copy",
                        lambda text: copied.update(text=text))
    repo = make_repo(tmp_path)
    store.create_task(repo, "First", "body one", "BUG")
    wanted = store.create_task(repo, "Second", "body two", "FEATURE")

    returned = app.Api().copy_task_prompt("repo", wanted.id)

    assert returned == "FEATURE: body two"
    assert copied["text"] == returned


def test_copy_task_prompt_leaves_the_task_open(tmp_path, monkeypatch):
    monkeypatch.setattr(app.launcher.pyperclip, "copy", lambda text: None)
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")

    app.Api().copy_task_prompt("repo", task.id)

    reloaded = store.list_tasks(repo)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_copy_task_prompt_rejects_an_id_that_does_not_exist(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().copy_task_prompt("repo", 999)


def test_pick_project_folder_returns_none_without_a_window():
    # No window means no native dialog to open — it must return cleanly rather
    # than indexing into an empty webview.windows.
    assert app.Api().pick_project_folder() is None


def test_corrupt_window_state_falls_back_to_defaults():
    app.WINDOW_STATE.parent.mkdir(parents=True, exist_ok=True)
    app.WINDOW_STATE.write_text("{not json", encoding="utf-8")

    state = app._load_window_state()

    assert state["width"] == 420
    assert state["on_top"] is True


def test_create_task_writes_a_task_and_returns_it_serialised(tmp_path):
    repo = make_repo(tmp_path)

    created = app.Api().create_task("repo", "Replay audio desync",
                                    "- drifts after **3s**", "BUG", "next")

    assert created["title"] == "Replay audio desync"
    assert created["bucket"] == "next"
    assert created["project"] == "repo"
    assert "path" not in created          # Path is not JSON-serialisable
    stored = store.list_tasks(repo)[0]
    assert stored.body == "- drifts after **3s**"


def test_create_task_rejects_an_unknown_bucket(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", "A", "body", "BUG", "urgent")


def test_create_task_rejects_a_non_string_title(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", 42, "body", "BUG", "now")


def test_file_note_rejects_a_non_string_body(tmp_path):
    repo = make_repo(tmp_path)
    note = app.Api().save_note("Audio drifts out of sync after ~2 minutes")

    with pytest.raises(ValueError):
        app.Api().file_note(note["id"], "repo", "Replay audio desync", "BUG", "now", body=42)


def test_save_attachment_returns_a_file_url_the_editor_can_render(tmp_path):
    import base64
    from pathlib import Path
    from urllib.request import url2pathname
    from urllib.parse import urlparse
    repo = make_repo(tmp_path)
    url = "data:image/png;base64," + base64.b64encode(b"pixels").decode()

    returned = app.Api().save_attachment("repo", url)

    # A bare `C:/repos/x/.tasks/attachments/a.png` cannot be rendered: in a URL
    # a leading `C:` parses as a *scheme*, so the browser never treats it as a
    # path and the image silently fails to load. It needs the file:// scheme to
    # be a URL at all. Backslashes stay out either way — one is an escape
    # character in a markdown link target.
    assert returned.startswith("file:///")
    assert "\\" not in returned
    assert Path(url2pathname(urlparse(returned).path)).read_bytes() == b"pixels"


def test_a_bucket_change_on_one_member_moves_the_whole_group(tmp_path):
    # The editor's "When" row edits one task, but a group lives in one bucket.
    # Enforced in update_task so every control that writes a bucket obeys it.
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [first.id, second.id], "Editor polish")

    app.Api().update_task("repo", first.id, {"bucket": "someday"})

    assert {t.bucket for t in store.list_tasks(repo)} == {"someday"}


def test_a_bucket_change_on_a_loose_task_moves_only_it(tmp_path):
    repo = make_repo(tmp_path)
    grouped = store.create_task(repo, "One", "body", "BUG")
    loose = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [grouped.id], "Editor polish")

    app.Api().update_task("repo", loose.id, {"bucket": "someday"})

    by_id = {t.id: t for t in store.list_tasks(repo)}
    assert by_id[loose.id].bucket == "someday"
    assert by_id[grouped.id].bucket == "now"


def test_an_order_aimed_at_a_group_member_cannot_split_the_group(tmp_path):
    # The group owns its own ordering. An `order` computed for a single task —
    # the editor sends one whenever the bucket changes — would otherwise wedge
    # a member away from its siblings.
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    third = store.create_task(repo, "Three", "body", "BUG")
    app.Api().group_tasks("repo", [first.id, third.id], "Editor polish")

    app.Api().update_task("repo", first.id, {"order": 99})

    grouped = sorted(t.order for t in store.list_tasks(repo) if t.group)
    assert grouped[1] - grouped[0] == 1
    assert {t.id for t in store.list_tasks(repo) if t.group} == {first.id, third.id}
    assert second.id not in {t.id for t in store.list_tasks(repo) if t.group}


def test_editing_a_completed_task_does_not_drag_its_old_group_around(tmp_path):
    # done/ keeps the group string so the archive stays meaningful, but a
    # completed task is not part of the group the renderer draws.
    repo = make_repo(tmp_path)
    finished = store.create_task(repo, "One", "body", "BUG")
    still_open = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [finished.id, still_open.id], "Editor polish")
    app.Api().complete_task("repo", finished.id)

    app.Api().update_task("repo", finished.id, {"bucket": "someday"})

    survivor = [t for t in store.list_tasks(repo) if t.id == still_open.id][0]
    assert survivor.bucket == "now"


def test_get_state_carries_the_collapsed_view(tmp_path):
    make_repo(tmp_path)
    app.Api().set_collapsed(["repo"], [["repo", "Editor polish"]])

    assert app.Api().get_state()["collapsed"] == {
        "projects": ["repo"],
        "groups": [["repo", "Editor polish"]],
    }


def test_set_collapsed_rejects_a_malformed_group_entry(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().set_collapsed([], [["repo"]])
    with pytest.raises(ValueError):
        app.Api().set_collapsed([], [["repo", 7]])

    assert app.Api().get_state()["collapsed"] == {"projects": [], "groups": []}


def test_create_group_dedupes_the_seed(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    third = store.create_task(repo, "Three", "body", "BUG")
    app.Api().group_tasks("repo", [first.id], "Editor polish")

    name = app.Api().create_group("repo", [second.id, third.id], "Editor polish")

    assert name == "Editor polish 2"


def test_rename_group_reports_a_collision(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [first.id], "Editor polish")
    app.Api().group_tasks("repo", [second.id], "Drag fixes")

    with pytest.raises(ValueError):
        app.Api().rename_group("repo", "Drag fixes", "Editor polish")


def test_set_group_bucket_rejects_an_unknown_bucket(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "One", "body", "BUG")
    app.Api().group_tasks("repo", [task.id], "G")

    with pytest.raises(ValueError):
        app.Api().set_group_bucket("repo", "G", "urgent")


def test_ungroup_tasks_leaves_the_rest_of_the_group(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [first.id, second.id], "G")

    app.Api().ungroup_tasks("repo", [second.id])

    by_id = {t.id: t for t in store.list_tasks(repo)}
    assert by_id[first.id].group == "G"
    assert by_id[second.id].group is None


def test_disband_group_loosens_every_member(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "One", "body", "BUG")
    second = store.create_task(repo, "Two", "body", "BUG")
    app.Api().group_tasks("repo", [first.id, second.id], "G")

    app.Api().disband_group("repo", "G")

    assert all(t.group is None for t in store.list_tasks(repo))


def test_reset_to_open_returns_the_updated_tasks(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "One", "body", "BUG")
    task.status = "in-progress"
    task.started = "2026-07-20"
    store.save_task(task)

    updated = app.Api().reset_to_open("repo", [task.id])

    assert updated[0]["status"] == "open"
    assert updated[0]["started"] is None
    assert updated[0]["project"] == "repo"
    # Task.path is a Path, which does not survive the bridge as JSON.
    assert "path" not in updated[0]


def test_get_state_has_no_last_project_before_one_is_chosen(tmp_path):
    make_repo(tmp_path)

    assert app.Api().get_state()["last_project"] is None


def test_get_state_carries_the_last_selected_project(tmp_path):
    make_repo(tmp_path)

    app.Api().set_last_project("repo")

    assert app.Api().get_state()["last_project"] == "repo"


def test_restart_spawns_a_replacement(monkeypatch):
    """The replacement closes this window itself, over the singleton port."""
    spawned = []
    monkeypatch.setattr(restart, "spawn_replacement", lambda: spawned.append(True))

    app.Api().restart()

    assert spawned == [True]
