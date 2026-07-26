import pytest

import store


def test_render_then_parse_preserves_every_field():
    original = store.Task(
        id=42,
        title="Replay audio desync after ~2 minutes",
        type="BUG",
        bucket="now",
        status="open",
        order=1,
        created="2026-07-25",
        started=None,
        done=None,
        body="Audio drifts out of sync.\n\nProbably the pts rebase.",
    )

    reparsed = store.parse_task(store.render_task(original))

    assert reparsed.id == 42
    assert reparsed.title == "Replay audio desync after ~2 minutes"
    assert reparsed.type == "BUG"
    assert reparsed.bucket == "now"
    assert reparsed.status == "open"
    assert reparsed.order == 1
    assert reparsed.created == "2026-07-25"
    assert reparsed.started is None
    assert reparsed.done is None


def test_body_survives_verbatim_including_yaml_lookalikes():
    tricky = 'key: value\n---\n"quoted" and `backticks`\n\n  indented\ttab'
    task = store.Task(
        id=1, title="t", type="BUG", bucket="now", status="open", order=0,
        created="2026-07-25", started=None, done=None, body=tricky,
    )

    assert store.parse_task(store.render_task(task)).body == tricky


def test_task_slug_is_filename_safe_and_bounded():
    assert store.task_slug("Replay audio desync after ~2 minutes!") == "replay-audio-desync-after-2-minutes"
    assert len(store.task_slug("x" * 200)) <= 50


def test_hand_edited_unquoted_dates_load_as_strings():
    text = (
        "---\n"
        "id: 7\ntitle: Hand edited\ntype: BUG\nbucket: now\nstatus: done\n"
        "order: 2\ncreated: 2026-07-25\nstarted: 2026-07-20\ndone: 2026-07-25\n"
        "---\n\nbody text"
    )

    task = store.parse_task(text)

    assert isinstance(task.created, str)
    assert isinstance(task.started, str)
    assert isinstance(task.done, str)
    assert task.started == "2026-07-20"
    assert task.done == "2026-07-25"


def test_blank_order_field_defaults_to_zero():
    text = (
        "---\n"
        "id: 7\ntitle: t\ntype: BUG\nbucket: now\nstatus: open\n"
        "order:\ncreated: 2026-07-25\nstarted:\ndone:\n"
        "---\n\nbody"
    )

    task = store.parse_task(text)

    assert task.order == 0
    assert task.started is None
    assert task.done is None


def test_ensure_tasks_dir_bootstraps_untracked(tmp_path):
    store.ensure_tasks_dir(tmp_path, tracked=False)

    assert (tmp_path / ".tasks" / "open").is_dir()
    assert (tmp_path / ".tasks" / "done").is_dir()
    assert (tmp_path / ".tasks" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_set_tracked_true_removes_the_gitignore(tmp_path):
    store.ensure_tasks_dir(tmp_path, tracked=False)

    store.set_tracked(tmp_path, True)
    assert not (tmp_path / ".tasks" / ".gitignore").exists()

    store.set_tracked(tmp_path, False)
    assert (tmp_path / ".tasks" / ".gitignore").read_text(encoding="utf-8") == "*\n"


def test_create_task_assigns_sequential_ids_and_writes_to_open(tmp_path):
    first = store.create_task(tmp_path, "First thing", "body one", "BUG")
    second = store.create_task(tmp_path, "Second thing", "body two", "FEATURE")

    assert first.id == 1
    assert second.id == 2
    assert second.path == tmp_path / ".tasks" / "open" / "0002-second-thing.md"
    assert second.path.exists()


def test_next_task_id_counts_done_tasks_so_ids_are_never_reused(tmp_path):
    task = store.create_task(tmp_path, "First thing", "body", "BUG")
    store.complete_task(task)

    assert store.next_task_id(tmp_path) == 2


def test_complete_task_moves_to_done_and_stamps_the_date(tmp_path):
    task = store.create_task(tmp_path, "Ship it", "body", "FEATURE")

    completed = store.complete_task(task)

    assert completed.status == "done"
    assert completed.done is not None
    assert completed.path == tmp_path / ".tasks" / "done" / "0001-ship-it.md"
    assert not (tmp_path / ".tasks" / "open" / "0001-ship-it.md").exists()


def test_list_tasks_can_exclude_the_done_archive(tmp_path):
    store.create_task(tmp_path, "Open one", "body", "BUG")
    store.complete_task(store.create_task(tmp_path, "Closed one", "body", "BUG"))

    assert len(store.list_tasks(tmp_path, include_done=True)) == 2
    assert [t.title for t in store.list_tasks(tmp_path, include_done=False)] == ["Open one"]


def test_reorder_bucket_rewrites_order_to_match_the_given_sequence(tmp_path):
    first = store.create_task(tmp_path, "A", "body", "BUG", bucket="now")
    second = store.create_task(tmp_path, "B", "body", "BUG", bucket="now")
    third = store.create_task(tmp_path, "C", "body", "BUG", bucket="next")

    store.reorder_bucket(tmp_path, "now", [second.id, first.id])

    by_id = {t.id: t for t in store.list_tasks(tmp_path)}
    assert by_id[second.id].order == 0
    assert by_id[first.id].order == 1
    assert by_id[third.id].order == 0


def test_create_task_rejects_an_unknown_bucket(tmp_path):
    with pytest.raises(ValueError):
        store.create_task(tmp_path, "A", "body", "BUG", bucket="urgent")


def test_task_files_are_written_with_lf_endings(tmp_path):
    task = store.create_task(tmp_path, "LF body", "line one\nline two", "BUG")

    assert b"\r" not in task.path.read_bytes()


def test_lf_body_round_trips_byte_exact(tmp_path):
    body = "line one\nline two\n\n  indented"
    task = store.create_task(tmp_path, "LF body", body, "BUG")

    assert store.list_tasks(tmp_path)[0].body == body


def test_crlf_body_normalises_to_lf_without_gaining_blank_lines(tmp_path):
    task = store.create_task(tmp_path, "CRLF body", "line one\r\nline two", "BUG")

    assert store.list_tasks(tmp_path)[0].body == "line one\nline two"


def test_gitignore_is_written_with_lf(tmp_path):
    store.ensure_tasks_dir(tmp_path, tracked=False)

    assert (tmp_path / ".tasks" / ".gitignore").read_bytes() == b"*\n"


def test_read_tasks_skips_an_unparseable_file_and_reports_it(tmp_path):
    store.create_task(tmp_path, "Good one", "body", "BUG")
    (tmp_path / ".tasks" / "open" / "scratch.md").write_text(
        "no frontmatter here", encoding="utf-8", newline="\n")

    tasks, unreadable = store.read_tasks(tmp_path)

    assert [t.title for t in tasks] == ["Good one"]
    assert len(unreadable) == 1
    assert "scratch.md" in unreadable[0]


def test_read_tasks_skips_a_file_missing_a_required_key(tmp_path):
    store.create_task(tmp_path, "Good one", "body", "BUG")
    (tmp_path / ".tasks" / "open" / "0002-broken.md").write_text(
        "---\ntitle: no id\ntype: BUG\nbucket: now\nstatus: open\ncreated: 2026-07-25\n---\n\nbody",
        encoding="utf-8", newline="\n")

    tasks, unreadable = store.read_tasks(tmp_path)

    assert len(tasks) == 1
    assert len(unreadable) == 1


def test_read_tasks_skips_a_file_with_malformed_yaml(tmp_path):
    store.create_task(tmp_path, "Good one", "body", "BUG")
    (tmp_path / ".tasks" / "open" / "0002-bad-yaml.md").write_text(
        '---\nid: 2\ntitle: "unclosed quote\ntype: BUG\nbucket: now\n'
        'status: open\ncreated: 2026-07-25\n---\n\nbody',
        encoding="utf-8", newline="\n")

    tasks, unreadable = store.read_tasks(tmp_path)

    assert [t.title for t in tasks] == ["Good one"]
    assert len(unreadable) == 1


def test_read_tasks_skips_a_file_whose_id_is_not_a_number(tmp_path):
    store.create_task(tmp_path, "Good one", "body", "BUG")
    (tmp_path / ".tasks" / "open" / "0003-bad-id.md").write_text(
        "---\nid: [1, 2]\ntitle: t\ntype: BUG\nbucket: now\n"
        "status: open\ncreated: 2026-07-25\n---\n\nbody",
        encoding="utf-8", newline="\n")

    tasks, unreadable = store.read_tasks(tmp_path)

    assert len(tasks) == 1
    assert len(unreadable) == 1


def test_complete_task_preserves_an_existing_completion_date(tmp_path):
    task = store.complete_task(store.create_task(tmp_path, "Ship it", "body", "FEATURE"))
    original = task.done
    task.done = "2026-03-14"
    store.save_task(task)

    recompleted = store.complete_task(store.list_tasks(tmp_path)[0])

    assert recompleted.done == "2026-03-14"
    assert original != "2026-03-14"


def test_group_round_trips_through_frontmatter(tmp_path):
    task = store.create_task(tmp_path, "Chips rewrite the row", "body", "BUG")
    task.group = "Editor polish"
    store.save_task(task)

    assert store.list_tasks(tmp_path)[0].group == "Editor polish"


def test_a_task_file_with_no_group_key_parses_as_ungrouped():
    # Every task file written before groups existed looks like this. None of
    # them may need a migration.
    text = (
        "---\n"
        "id: 1\n"
        "title: Older task\n"
        "type: BUG\n"
        "bucket: now\n"
        "status: open\n"
        "order: 0\n"
        "created: 2026-07-01\n"
        "started: null\n"
        "done: null\n"
        "---\n\n"
        "body\n"
    )

    assert store.parse_task(text).group is None


def test_an_ungrouped_task_writes_group_null(tmp_path):
    task = store.create_task(tmp_path, "Loose", "body", "BUG")

    assert "group: null" in task.path.read_text(encoding="utf-8")


def test_reset_to_open_clears_the_started_stamp(tmp_path):
    task = store.create_task(tmp_path, "Was handed off", "body", "BUG")
    task.status = "in-progress"
    task.started = "2026-07-20"
    store.save_task(task)

    store.reset_to_open(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.started is None


def test_reset_to_open_refuses_a_completed_task(tmp_path):
    task = store.complete_task(store.create_task(tmp_path, "Finished", "body", "BUG"))

    with pytest.raises(ValueError):
        store.reset_to_open(task)
