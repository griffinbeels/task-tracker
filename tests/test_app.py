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


def test_update_task_rejects_a_colour_claude_does_not_accept(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG", color="cyan")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"color": "chartreuse"})

    assert store.list_tasks(repo)[0].color == "cyan"


def test_update_task_applies_a_valid_colour(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG", color="cyan")

    app.Api().update_task("repo", task.id, {"color": "purple"})

    assert store.list_tasks(repo)[0].color == "purple"


def test_create_task_takes_a_colour(tmp_path):
    make_repo(tmp_path)

    payload = app.Api().create_task("repo", "A", "body", "BUG", "now", "pink")

    assert payload["color"] == "pink"


def test_create_task_rejects_a_colour_claude_does_not_accept(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", "A", "body", "BUG", "now", "chartreuse")


def test_a_task_crosses_the_bridge_carrying_its_colour(tmp_path):
    repo = make_repo(tmp_path)
    store.create_task(repo, "A", "body", "BUG", color="orange")

    payload = app.Api().get_state()["tasks"][0]

    assert payload["color"] == "orange"


def test_hand_off_passes_the_name_it_was_given(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "A", "body", "BUG")
    second = store.create_task(repo, "B", "body", "BUG")
    captured = {}
    monkeypatch.setattr(
        app.launcher, "hand_off",
        lambda path, tasks, launch=None, name=None: captured.update(name=name) or "")

    app.Api().hand_off("repo", [first.id, second.id], "Editor polish")

    assert captured["name"] == "Editor polish"


def test_hand_off_without_a_name_passes_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")
    captured = {}
    monkeypatch.setattr(
        app.launcher, "hand_off",
        lambda path, tasks, launch=None, name=None: captured.update(name=name) or "")

    app.Api().hand_off("repo", [task.id])

    # Exactly "", not merely falsy: Api.hand_off defaults to "" and always
    # forwards a string, while launcher.hand_off's own default is None. A
    # truthiness assertion passes for both and so pins neither.
    assert captured["name"] == ""


def test_suggest_session_name_is_what_hand_off_would_use(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "Rename the spawned session", "b", "FEATURE")
    second = store.create_task(repo, "Colour it too", "b", "FEATURE")

    suggested = app.Api().suggest_session_name("repo", [first.id, second.id])

    assert suggested == "FEATURE: Rename the spawned session (+1)"


def test_suggest_session_name_raises_on_an_unknown_id(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().suggest_session_name("repo", [99])
