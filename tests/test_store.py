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


LEGACY_FILE = (
    "---\n"
    "id: 3\n"
    "title: A task written before colours existed\n"
    "type: BUG\n"
    "bucket: now\n"
    "status: open\n"
    "order: 0\n"
    "created: 2026-07-25\n"
    "started: null\n"
    "done: null\n"
    "---\n"
    "\n"
    "body\n"
)


def make_task(task_id=1, **overrides):
    fields = dict(
        id=task_id, title="t", type="BUG", bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body="b",
    )
    fields.update(overrides)
    return store.Task(**fields)


def test_a_colour_survives_the_frontmatter_round_trip():
    task = make_task(42, color="purple")

    assert store.parse_task(store.render_task(task)).color == "purple"


def test_a_task_file_with_no_colour_gets_one_derived_from_its_id():
    # Every task written before this feature must have a colour from the first
    # launch — a row with no dot beside rows with dots reads as a broken render.
    assert store.parse_task(LEGACY_FILE).color == store.CLAUDE_COLORS[3]


def test_a_hand_edited_colour_that_is_not_a_claude_colour_is_replaced():
    # A task file is hand-editable, so `color:` is unvalidated text on a path
    # that ends in "type this into another process's console".
    text = LEGACY_FILE.replace("bucket: now", "color: chartreuse\nbucket: now")

    assert store.parse_task(text).color == store.CLAUDE_COLORS[3]


def test_an_empty_colour_is_treated_as_no_colour():
    text = LEGACY_FILE.replace("bucket: now", "color: ''\nbucket: now")

    assert store.parse_task(text).color == store.CLAUDE_COLORS[3]


def test_eight_consecutive_ids_get_eight_different_colours():
    colours = {make_task(task_id).color for task_id in range(1, 9)}

    assert len(colours) == 8


def test_every_derived_colour_is_one_claude_accepts():
    for task_id in range(0, 40):
        assert make_task(task_id).color in store.CLAUDE_COLORS


def test_create_task_takes_an_explicit_colour(tmp_path):
    store.create_task(tmp_path, "A", "body", "BUG", color="cyan")

    assert store.list_tasks(tmp_path)[0].color == "cyan"


def test_create_task_without_a_colour_derives_a_legal_one(tmp_path):
    task = store.create_task(tmp_path, "A", "body", "BUG")

    assert task.color in store.CLAUDE_COLORS


def test_a_legacy_task_keeps_its_derived_colour_once_it_is_saved(tmp_path):
    # Reads never write, but the next save for any reason makes the derived
    # value a real field.
    path = tmp_path / "legacy.md"
    path.write_text(LEGACY_FILE, encoding="utf-8", newline="\n")
    task = store.parse_task(path.read_text(encoding="utf-8"), path)
    derived = task.color

    store.save_task(task)

    assert f"color: {derived}" in path.read_text(encoding="utf-8")
def test_delete_task_removes_the_file(tmp_path):
    task = store.create_task(tmp_path, "Gone", "body", "BUG")
    path = task.path

    store.delete_task(task)

    assert not path.exists()
    assert store.list_tasks(tmp_path) == []


def test_delete_task_leaves_the_other_tasks_alone(tmp_path):
    keep = store.create_task(tmp_path, "Keep", "body", "BUG")
    doomed = store.create_task(tmp_path, "Doomed", "body", "BUG")

    store.delete_task(doomed)

    assert [t.id for t in store.list_tasks(tmp_path)] == [keep.id]


def test_delete_task_leaves_attachments_behind(tmp_path):
    # Attachments are deliberately never garbage-collected: reference counting
    # across hand-editable files is not worth the machinery. Deleting the task
    # that referenced one must not start doing it by the back door.
    task = store.create_task(tmp_path, "Has a screenshot", "body", "BUG")
    pixel = store.save_attachment(
        tmp_path,
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")

    store.delete_task(task)

    assert pixel.exists()


def test_delete_task_refuses_a_task_with_no_path():
    task = store.Task(id=1, title="Unsaved", type="BUG", bucket="now",
                      status="open", order=0, created="2026-07-25",
                      started=None, done=None, body="body")

    with pytest.raises(ValueError):
        store.delete_task(task)


def test_delete_task_tolerates_a_file_already_gone(tmp_path):
    task = store.create_task(tmp_path, "Gone twice", "body", "BUG")

    store.delete_task(task)
    store.delete_task(task)

    assert store.list_tasks(tmp_path) == []


def test_restore_task_moves_the_file_back_into_open(tmp_path):
    task = store.create_task(tmp_path, "Finished", "body", "BUG")
    store.complete_task(task)
    done_path = task.path
    assert done_path.parent.name == "done"

    store.restore_task(task)

    assert not done_path.exists()
    assert task.path.parent.name == "open"
    assert task.path.exists()


def test_restore_task_reopens_it_and_clears_the_done_date(tmp_path):
    task = store.create_task(tmp_path, "Finished", "body", "BUG")
    store.complete_task(task)

    store.restore_task(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert reloaded.status == "open"
    assert reloaded.done is None


def test_restore_task_lands_at_the_end_of_its_bucket(tmp_path):
    # The tasks it sat among moved on without it; reclaiming its old order
    # would re-insert it into the middle of a list the user has since changed.
    first = store.create_task(tmp_path, "First", "body", "BUG")
    store.complete_task(first)
    store.create_task(tmp_path, "Second", "body", "BUG")
    store.create_task(tmp_path, "Third", "body", "BUG")

    store.restore_task(first)

    by_title = {t.title: t for t in store.list_tasks(tmp_path)}
    assert by_title["First"].order > by_title["Third"].order


def test_restore_task_lands_last_even_when_the_bucket_has_a_hole(tmp_path):
    # The test above completes the bucket's only task, so the orders it
    # rebuilds are contiguous by construction and it never meets the case that
    # actually happens: the row's `done` button completes without renumbering,
    # so finishing a MIDDLE task leaves 0 and 2 with nothing at 1. Counting
    # siblings there returns 2 — an order a live task already holds — and the
    # restored task renders in the middle of the bucket it was promised the
    # end of.
    store.create_task(tmp_path, "First", "body", "BUG")
    middle = store.create_task(tmp_path, "Middle", "body", "BUG")
    store.create_task(tmp_path, "Last", "body", "BUG")
    store.complete_task(middle)

    store.restore_task(middle)

    live = store.list_tasks(tmp_path, include_done=False)
    orders = [task.order for task in live]
    assert len(set(orders)) == len(orders), "two tasks share an order"
    assert {task.title: task.order for task in live}["Middle"] == max(orders)


def test_restore_task_does_not_disturb_the_tasks_already_there(tmp_path):
    first = store.create_task(tmp_path, "First", "body", "BUG")
    store.complete_task(first)
    second = store.create_task(tmp_path, "Second", "body", "BUG")

    store.restore_task(first)

    reloaded = {t.title: t.order for t in store.list_tasks(tmp_path)}
    assert reloaded["Second"] == second.order


def test_restore_task_raises_without_a_path():
    task = store.Task(id=1, title="t", type="BUG", bucket="now", status="done",
                      order=0, created="2026-07-25", started=None,
                      done="2026-07-25", body="b")

    with pytest.raises(ValueError):
        store.restore_task(task)


def test_complete_then_restore_changes_nothing_but_status_and_done(tmp_path):
    # The whole point of the feature: a round trip is a round trip.
    task = store.create_task(tmp_path, "Round trip", "the body", "FEATURE",
                             bucket="someday", color="cyan")
    original = (task.id, task.title, task.body, task.type, task.color,
                task.group, task.bucket)

    store.complete_task(task)
    store.restore_task(task)

    reloaded = store.list_tasks(tmp_path)[0]
    assert (reloaded.id, reloaded.title, reloaded.body, reloaded.type,
            reloaded.color, reloaded.group, reloaded.bucket) == original
    assert reloaded.status == "open"
    assert reloaded.done is None
