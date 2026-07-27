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


def test_collapsed_view_defaults_to_nothing_folded(tmp_path):
    assert registry.collapsed_view() == {"projects": [], "groups": []}


def test_collapsed_view_round_trips(tmp_path):
    registry.set_collapsed_view(["sm64_tracker"], [["task_tracker", "Editor polish"]])

    assert registry.collapsed_view() == {
        "projects": ["sm64_tracker"],
        "groups": [["task_tracker", "Editor polish"]],
    }


def test_writing_the_collapsed_view_keeps_the_last_project(tmp_path):
    # session.json holds both, and set_last_project used to replace the whole
    # file — so the fold state would have been wiped on every project switch.
    registry.set_last_project("task_tracker")

    registry.set_collapsed_view(["sm64_tracker"], [])

    assert registry.last_project() == "task_tracker"


def test_writing_the_last_project_keeps_the_collapsed_view(tmp_path):
    registry.set_collapsed_view(["sm64_tracker"], [])

    registry.set_last_project("task_tracker")

    assert registry.collapsed_view()["projects"] == ["sm64_tracker"]


def test_a_hand_edited_collapsed_view_is_filtered_not_trusted(tmp_path):
    # session.json is hand-editable and these values reach the renderer, which
    # indexes each group entry by position.
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "session.json").write_text(json.dumps({
        "collapsed": {
            "projects": ["ok", 7, None],
            "groups": [["p", "g"], "nope", ["only-one"], [1, 2]],
        },
    }), encoding="utf-8", newline="\n")

    assert registry.collapsed_view() == {"projects": ["ok"], "groups": [["p", "g"]]}


def test_a_collapsed_view_of_the_wrong_shape_folds_nothing(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "session.json").write_text(
        json.dumps({"collapsed": {"projects": "sm64_tracker"}}),
        encoding="utf-8", newline="\n")

    # A bare string is iterable; without a list check every character would
    # come back as a collapsed project name.
    assert registry.collapsed_view() == {"projects": [], "groups": []}


def test_a_corrupt_session_file_folds_nothing_and_loses_no_data(tmp_path):
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "session.json").write_text(
        "{not json", encoding="utf-8", newline="\n")

    assert registry.collapsed_view() == {"projects": [], "groups": []}
    assert registry.last_project() is None


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


def write_settings(raw: str) -> None:
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "settings.json").write_text(
        raw, encoding="utf-8", newline="\n")


@pytest.mark.parametrize("raw", ["null", "[]", '"hello"', "42"])
def test_settings_of_the_wrong_shape_fall_back_to_defaults(raw):
    # A corrupt file was already handled; valid JSON of the wrong SHAPE was
    # not. Each of these parses fine and then answers .get with an
    # AttributeError — out of load_settings, which get_state calls for the
    # window as a whole, so one stray character here blanked the app.
    write_settings(raw)

    settings = registry.load_settings()

    assert settings.group_limit == 5
    assert [t.name for t in settings.types] == ["BUG", "FEATURE", "ITERATION"]


def test_a_malformed_type_row_costs_that_row_and_not_the_app():
    # Same judgement store.read_tasks already makes about a malformed task
    # file: skip the row, keep the app. TaskType(**t) raised on every one of
    # these shapes.
    write_settings(json.dumps({"types": [
        {"name": "BUG", "color": "#e5484d"},
        "not an object",
        {"name": "MISSING COLOUR"},
        {"name": "EXTRA", "color": "#111111", "unknown_key": 1},
        {"name": 7, "color": "#222222"},
    ]}))

    settings = registry.load_settings()

    assert [t.name for t in settings.types] == ["BUG", "EXTRA"]


def test_a_types_list_that_survives_nothing_falls_back_to_the_defaults():
    # An empty result is indistinguishable from "no types configured", and a
    # task tracker with no types cannot file anything.
    write_settings(json.dumps({"types": ["nonsense", 5]}))

    assert [t.name for t in registry.load_settings().types] == [
        "BUG", "FEATURE", "ITERATION"]


@pytest.mark.parametrize("stored", [0, -1, "five", None, True])
def test_a_count_below_one_reads_as_the_default(stored):
    # Readers on the JS side fall back through `x || 5`, so a stored 0 behaves
    # as 5 while the file claims 0 — the stored value and the effective one
    # disagreeing with nothing on screen admitting it. Resolved on the way in.
    # True is in the list because bool is an int in Python, and a `group_limit:
    # true` would otherwise sail through as a limit of 1.
    write_settings(json.dumps({"group_limit": stored, "stale_days": stored}))

    settings = registry.load_settings()

    assert settings.group_limit == 5
    assert settings.stale_days == 90


def test_in_progress_order_defaults_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)

    assert registry.in_progress_order() == []


def test_in_progress_order_round_trips(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)

    registry.set_in_progress_order([["repo", "group:Editor polish"], ["repo", "task:7"]])

    assert registry.in_progress_order() == [
        ["repo", "group:Editor polish"], ["repo", "task:7"]]


def test_in_progress_order_survives_a_project_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    registry.set_in_progress_order([["repo", "task:1"]])

    # session.json is read-modify-write (invariant 17): setting one key must
    # not drop the others, which is what would silently reset the running list.
    registry.set_last_project("other")

    assert registry.in_progress_order() == [["repo", "task:1"]]
    assert registry.last_project() == "other"


def test_a_hand_edited_in_progress_order_is_filtered(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    (tmp_path).mkdir(parents=True, exist_ok=True)
    (tmp_path / "session.json").write_text(
        '{"in_progress_order": ["repo", ["repo", "task:1"], ["repo"], [1, 2]]}',
        encoding="utf-8", newline="\n")

    # The renderer indexes these by position, so a bare string where a pair
    # belongs would iterate as characters. Only the well-formed pair survives.
    assert registry.in_progress_order() == [["repo", "task:1"]]


def test_zoom_starts_at_full_size_in_both_scopes(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)

    assert registry.zoom_view() == {"app": 1.0, "editor": 1.0}


def test_zoom_round_trips_per_scope(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)

    registry.set_zoom("editor", 1.4)

    # One scope moving must not move the other: the list and the editor are
    # sized independently, which is the whole point of there being two.
    assert registry.zoom_view() == {"app": 1.0, "editor": 1.4}


def test_zoom_survives_a_project_switch(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    registry.set_zoom("app", 1.6)

    # session.json is read-modify-write (invariant 17).
    registry.set_last_project("other")

    assert registry.zoom_view()["app"] == 1.6
    assert registry.last_project() == "other"


def test_setting_one_zoom_scope_keeps_the_other(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    registry.set_zoom("app", 1.3)

    registry.set_zoom("editor", 1.9)

    assert registry.zoom_view() == {"app": 1.3, "editor": 1.9}


@pytest.mark.parametrize("stored, expected", [
    ({"app": 0.2}, 1.0),        # below the floor the user asked for
    ({"app": 9}, 2.0),          # above the ceiling
    ({"app": "1.5"}, 1.0),      # a string, not a number
    ({"app": None}, 1.0),
    ({"app": True}, 1.0),       # bool is an int in Python
    ({}, 1.0),                  # key absent entirely
])
def test_a_hand_edited_zoom_is_repaired_not_trusted(tmp_path, monkeypatch, stored, expected):
    # session.json is hand-editable, and this value scales the whole window —
    # a zoom of 40 is a window with one word in it and no way back except
    # editing the file nobody knows exists. Repaired on the way out
    # (invariant 23's parsing half); Api.set_zoom refuses instead.
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    (tmp_path / "session.json").write_text(
        json.dumps({"zoom": stored}), encoding="utf-8", newline="\n")

    assert registry.zoom_view()["app"] == expected
    assert registry.zoom_view()["editor"] == 1.0


@pytest.mark.parametrize("raw", ['{"zoom": "big"}', '{"zoom": [1, 2]}', "{not json"])
def test_a_zoom_of_the_wrong_shape_leaves_the_window_at_full_size(tmp_path, monkeypatch, raw):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path)
    (tmp_path / "session.json").write_text(raw, encoding="utf-8", newline="\n")

    assert registry.zoom_view() == {"app": 1.0, "editor": 1.0}


def test_the_header_scales_with_the_list_only_when_asked():
    assert registry.load_settings().zoom_whole_window is False


def test_zoom_whole_window_round_trips():
    settings = registry.load_settings()
    settings.zoom_whole_window = True
    registry.save_settings(settings)

    assert registry.load_settings().zoom_whole_window is True


@pytest.mark.parametrize("stored", ["yes", 1, None, []])
def test_a_hand_edited_zoom_whole_window_is_not_trusted(stored):
    # settings.json is hand-editable and this flag decides which elements get
    # scaled; anything but a real bool means the file was edited, and "off" is
    # the answer that cannot surprise anyone.
    write_settings(json.dumps({"zoom_whole_window": stored}))

    assert registry.load_settings().zoom_whole_window is False
