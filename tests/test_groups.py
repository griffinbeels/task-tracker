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
