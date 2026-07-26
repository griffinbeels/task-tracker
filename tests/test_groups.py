import pytest

import groups
import store


def seed_bucket(repo, titles, bucket="now"):
    """One task per title, in order, all in one bucket."""
    return [store.create_task(repo, title, f"body of {title}", "BUG", bucket)
            for title in titles]


def orders(repo):
    """id -> order, for asserting the shape of a bucket in one line."""
    return {t.id: t.order for t in store.list_tasks(repo, include_done=False)}


def by_id(repo):
    return {t.id: t for t in store.list_tasks(repo, include_done=False)}


def test_assign_creates_a_group_from_two_loose_tasks(tmp_path):
    first, second = seed_bucket(tmp_path, ["Drops the title", "Rewrites the row"])

    name = groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    assert name == "Editor polish"
    assert {t.group for t in store.list_tasks(tmp_path)} == {"Editor polish"}


def test_assign_puts_a_joining_task_at_the_end_of_the_group(tmp_path):
    one, two, three, four = seed_bucket(tmp_path, ["One", "Two", "Three", "Four"])
    groups.assign(tmp_path, [two.id, four.id], "G")

    groups.assign(tmp_path, [three.id], "G")

    # Blocks are One (order 0) then G. Within G, the two originals keep their
    # relative order and Three lands behind them.
    assert orders(tmp_path) == {one.id: 0, two.id: 1, four.id: 2, three.id: 3}


def test_assign_pulls_a_joining_task_into_the_groups_bucket(tmp_path):
    here, = seed_bucket(tmp_path, ["In now"], "now")
    elsewhere, = seed_bucket(tmp_path, ["In someday"], "someday")
    groups.assign(tmp_path, [here.id], "G")

    groups.assign(tmp_path, [elsewhere.id], "G")

    assert by_id(tmp_path)[elsewhere.id].bucket == "now"


def test_a_new_group_takes_the_bucket_of_its_first_task(tmp_path):
    first, = seed_bucket(tmp_path, ["In someday"], "someday")
    second, = seed_bucket(tmp_path, ["In now"], "now")

    groups.assign(tmp_path, [first.id, second.id], "G")

    assert {t.bucket for t in store.list_tasks(tmp_path)} == {"someday"}


def test_the_renumber_makes_group_members_contiguous(tmp_path):
    one, two, three, four = seed_bucket(tmp_path, ["One", "Two", "Three", "Four"])
    # Interleave by hand, the way a hand-edited file could.
    for task in (two, four):
        task.group = "G"
        store.save_task(task)

    groups.renumber(tmp_path, "now")

    assert orders(tmp_path) == {one.id: 0, two.id: 1, four.id: 2, three.id: 3}


def test_the_renumber_is_idempotent(tmp_path):
    seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.renumber(tmp_path, "now")
    once = orders(tmp_path)

    groups.renumber(tmp_path, "now")

    assert orders(tmp_path) == once


def test_unique_name_leaves_a_free_name_alone(tmp_path):
    seed_bucket(tmp_path, ["One"])

    assert groups.unique_name(tmp_path, "Editor polish") == "Editor polish"


def test_unique_name_dedupes_case_insensitively(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id], "Editor polish")

    assert groups.unique_name(tmp_path, "editor POLISH") == "editor POLISH 2"


def test_unique_name_refuses_an_empty_seed(tmp_path):
    with pytest.raises(ValueError):
        groups.unique_name(tmp_path, "   ")


def test_create_never_joins_an_existing_group_with_the_same_seed(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id], "Editor polish")

    name = groups.create(tmp_path, [second.id, third.id], "Editor polish")

    assert name == "Editor polish 2"
    assert by_id(tmp_path)[first.id].group == "Editor polish"


def test_remove_clears_the_group_on_exactly_those_tasks(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id, second.id], "G")

    groups.remove(tmp_path, [second.id])

    tasks = by_id(tmp_path)
    assert tasks[first.id].group == "G"
    assert tasks[second.id].group is None


def test_an_unknown_task_id_is_rejected_by_name(tmp_path):
    with pytest.raises(ValueError) as caught:
        groups.assign(tmp_path, [999], "G")

    assert "999" in str(caught.value)


def test_rename_rewrites_every_member(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    groups.rename(tmp_path, "Editor polish", "Editor overhaul")

    assert {t.group for t in store.list_tasks(tmp_path)} == {"Editor overhaul"}


def test_rename_refuses_to_collide_with_another_group(tmp_path):
    first, second = seed_bucket(tmp_path, ["One", "Two"])
    groups.assign(tmp_path, [first.id], "Editor polish")
    groups.assign(tmp_path, [second.id], "Drag fixes")

    with pytest.raises(ValueError):
        groups.rename(tmp_path, "Drag fixes", "editor polish")

    assert by_id(tmp_path)[second.id].group == "Drag fixes"


def test_rename_allows_changing_only_the_case_of_its_own_name(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "editor polish")

    groups.rename(tmp_path, "editor polish", "Editor Polish")

    assert by_id(tmp_path)[first.id].group == "Editor Polish"


def test_rename_refuses_an_empty_name(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "G")

    with pytest.raises(ValueError):
        groups.rename(tmp_path, "G", "   ")


def test_rename_refuses_a_group_with_no_members(tmp_path):
    with pytest.raises(ValueError):
        groups.rename(tmp_path, "Never existed", "Something")


def test_disband_clears_the_field_and_leaves_the_order_alone(tmp_path):
    one, two, three = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [one.id, two.id], "G")
    before = orders(tmp_path)

    groups.disband(tmp_path, "G")

    assert all(t.group is None for t in store.list_tasks(tmp_path))
    assert orders(tmp_path) == before


def test_set_bucket_moves_every_member_to_the_end_of_the_target(tmp_path):
    resident, = seed_bucket(tmp_path, ["Already in next"], "next")
    first, second = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [first.id, second.id], "G")

    groups.set_bucket(tmp_path, "G", "next")

    tasks = by_id(tmp_path)
    assert {tasks[first.id].bucket, tasks[second.id].bucket} == {"next"}
    assert orders(tmp_path) == {resident.id: 0, first.id: 1, second.id: 2}


def test_set_bucket_rejects_an_unknown_bucket(tmp_path):
    first, = seed_bucket(tmp_path, ["One"])
    groups.assign(tmp_path, [first.id], "G")

    with pytest.raises(ValueError):
        groups.set_bucket(tmp_path, "G", "urgent")


def test_reorder_members_permutes_within_the_group(tmp_path):
    one, two, three, four = seed_bucket(tmp_path, ["One", "Two", "Three", "Four"])
    groups.assign(tmp_path, [two.id, three.id, four.id], "G")

    groups.reorder_members(tmp_path, "G", [four.id, two.id, three.id])

    # One keeps position 0; the group's own three slots are permuted inside it.
    assert orders(tmp_path) == {one.id: 0, four.id: 1, two.id: 2, three.id: 3}


def test_reorder_members_of_a_partly_visible_group_leaves_the_rest_put(tmp_path):
    # The IN PROGRESS section shows only a group's in-progress members, so the
    # id list it sends is a subset. Those tasks trade the slots they already
    # occupy; the members not on screen must not move.
    one, two, three, four = seed_bucket(tmp_path, ["One", "Two", "Three", "Four"])
    groups.assign(tmp_path, [one.id, two.id, three.id, four.id], "G")

    groups.reorder_members(tmp_path, "G", [three.id, one.id])

    assert orders(tmp_path) == {three.id: 0, two.id: 1, one.id: 2, four.id: 3}


def test_reorder_members_rejects_a_task_that_is_not_in_the_group(tmp_path):
    inside, outside = seed_bucket(tmp_path, ["In", "Out"])
    groups.assign(tmp_path, [inside.id], "G")

    with pytest.raises(ValueError):
        groups.reorder_members(tmp_path, "G", [inside.id, outside.id])


def test_reorder_members_rejects_a_group_with_no_members(tmp_path):
    with pytest.raises(ValueError):
        groups.reorder_members(tmp_path, "Never existed", [])


def test_auto_group_leaves_a_single_task_alone(tmp_path):
    only, = seed_bucket(tmp_path, ["One"])

    assert groups.auto_group(tmp_path, [only.id]) is None
    assert by_id(tmp_path)[only.id].group is None


def test_auto_group_names_a_new_group_after_the_first_task(tmp_path):
    first, second = seed_bucket(tmp_path, ["Drops the title", "Rewrites the row"])

    name = groups.auto_group(tmp_path, [first.id, second.id])

    assert name == "Drops the title"
    assert {t.group for t in store.list_tasks(tmp_path)} == {"Drops the title"}


def test_auto_group_never_touches_a_task_outside_the_selection(tmp_path):
    first, second, bystander = seed_bucket(tmp_path, ["One", "Two", "Three"])

    groups.auto_group(tmp_path, [first.id, second.id])

    assert by_id(tmp_path)[bystander.id].group is None


def test_auto_group_folds_loose_tasks_into_the_one_group_present(tmp_path):
    first, second, loose = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id, second.id], "Editor polish")

    name = groups.auto_group(tmp_path, [first.id, loose.id])

    assert name == "Editor polish"
    assert by_id(tmp_path)[loose.id].group == "Editor polish"


def test_auto_group_refuses_to_merge_two_named_groups(tmp_path):
    first, second, loose = seed_bucket(tmp_path, ["One", "Two", "Three"])
    groups.assign(tmp_path, [first.id], "Editor polish")
    groups.assign(tmp_path, [second.id], "Drag fixes")

    assert groups.auto_group(tmp_path, [first.id, second.id, loose.id]) is None

    tasks = by_id(tmp_path)
    assert tasks[first.id].group == "Editor polish"
    assert tasks[second.id].group == "Drag fixes"
    assert tasks[loose.id].group is None


def test_place_moves_a_loose_task_to_another_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "someday")

    groups.place(tmp_path, [task.id], bucket="now")

    assert by_id(tmp_path)[task.id].bucket == "now"


def test_place_renumbers_the_bucket_it_left(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["A", "B", "C"], "now")

    groups.place(tmp_path, [second.id], bucket="next")

    # The hole B left behind is closed; C does not keep order 2.
    assert orders(tmp_path)[first.id] == 0
    assert orders(tmp_path)[third.id] == 1
    assert orders(tmp_path)[second.id] == 0


def test_place_pulls_a_joining_task_into_its_new_groups_bucket(tmp_path):
    here, = seed_bucket(tmp_path, ["In now"], "now")
    groups.assign(tmp_path, [here.id], "G")
    elsewhere, = seed_bucket(tmp_path, ["In someday"], "someday")

    groups.place(tmp_path, [elsewhere.id], group="G")

    assert by_id(tmp_path)[elsewhere.id].bucket == "now"
    assert by_id(tmp_path)[elsewhere.id].group == "G"


def test_an_explicit_bucket_beats_the_groups_own(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [one.id, two.id], group="G", bucket="someday")

    assert {t.bucket for t in store.list_tasks(tmp_path)} == {"someday"}


def test_place_keeps_a_moved_group_contiguous(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    stranger, = seed_bucket(tmp_path, ["Stranger"], "someday")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [one.id, two.id], group="G", bucket="someday")

    landed = orders(tmp_path)
    assert landed[stranger.id] == 0
    assert sorted([landed[one.id], landed[two.id]]) == [1, 2]


def test_place_takes_a_task_out_of_its_group(tmp_path):
    one, two = seed_bucket(tmp_path, ["One", "Two"], "now")
    groups.assign(tmp_path, [one.id, two.id], "G")

    groups.place(tmp_path, [two.id], group=None, bucket="now")

    assert by_id(tmp_path)[two.id].group is None
    assert by_id(tmp_path)[one.id].group == "G"


def test_place_claims_a_task_as_in_progress(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "next")

    groups.place(tmp_path, [task.id], status="in-progress")

    landed = by_id(tmp_path)[task.id]
    assert landed.status == "in-progress"
    assert landed.started == store._today()
    # The bucket is untouched the whole time a task is in progress, so it
    # lands back where it came from when the session turns out not to be real.
    assert landed.bucket == "next"


def test_place_releases_an_in_progress_task_into_a_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "now")
    store.start_task(task)

    groups.place(tmp_path, [task.id], bucket="someday", status="open")

    landed = by_id(tmp_path)[task.id]
    assert landed.status == "open"
    assert landed.started is None
    assert landed.bucket == "someday"


def test_place_leaves_started_alone_when_the_status_does_not_change(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"], "now")
    task.started = "2020-01-01"
    store.save_task(task)

    groups.place(tmp_path, [task.id], bucket="next", status="open")

    # Already open — reset_to_open would have cleared a date this task holds.
    assert by_id(tmp_path)[task.id].started == "2020-01-01"


def test_place_applies_an_explicit_position(tmp_path):
    first, second, third = seed_bucket(tmp_path, ["A", "B", "C"], "now")

    groups.place(tmp_path, [third.id], bucket="now",
                 ordered_ids=[third.id, first.id, second.id])

    assert orders(tmp_path) == {third.id: 0, first.id: 1, second.id: 2}


def test_place_refuses_an_unknown_bucket(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"])

    with pytest.raises(ValueError):
        groups.place(tmp_path, [task.id], bucket="urgent")


def test_place_refuses_done_as_a_status(tmp_path):
    task, = seed_bucket(tmp_path, ["Alone"])

    with pytest.raises(ValueError):
        groups.place(tmp_path, [task.id], status="done")


def test_place_keeps_a_member_where_it_is_when_only_the_status_changes(tmp_path):
    one, two, three = seed_bucket(tmp_path, ["One", "Two", "Three"], "now")
    groups.assign(tmp_path, [one.id, two.id, three.id], "G")

    # Claiming the first member — dropping it on its own group's header inside
    # IN PROGRESS. It is already in G and already in now, so the only thing
    # that changes is the status; landing it at the end of its own group would
    # reorder a list nobody asked to reorder.
    groups.place(tmp_path, [one.id], group="G", status="in-progress")

    assert orders(tmp_path) == {one.id: 0, two.id: 1, three.id: 2}
    assert by_id(tmp_path)[one.id].status == "in-progress"


def test_place_releases_a_running_task_into_a_position(tmp_path):
    # The reported bug's backend half: a task dragged out of IN PROGRESS and
    # dropped between two rows of the bucket it already belonged to. Its bucket
    # never changed while it was running, so nothing about the destination
    # differs except the status and the position — which is exactly the case
    # where a "did anything change?" shortcut would decide to do nothing.
    first, second, third, running = seed_bucket(
        tmp_path, ["A", "B", "C", "D"], "now")
    store.start_task(running)

    groups.place(tmp_path, [running.id], bucket="now", group=None, status="open",
                 ordered_ids=[first.id, second.id, running.id, third.id])

    landed = by_id(tmp_path)[running.id]
    assert landed.status == "open"
    assert landed.started is None
    assert orders(tmp_path) == {first.id: 0, second.id: 1,
                                running.id: 2, third.id: 3}


def test_place_releases_a_running_task_into_a_different_bucket(tmp_path):
    first, second = seed_bucket(tmp_path, ["A", "B"], "now")
    running, = seed_bucket(tmp_path, ["D"], "someday")
    store.start_task(running)

    groups.place(tmp_path, [running.id], bucket="now", group=None, status="open",
                 ordered_ids=[first.id, running.id, second.id])

    landed = by_id(tmp_path)[running.id]
    assert landed.status == "open"
    assert landed.bucket == "now"
    assert orders(tmp_path) == {first.id: 0, running.id: 1, second.id: 2}
