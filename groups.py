"""Which tasks are handed to one Claude session, and the order that shows it.

A group **is** its name. Tasks in the same project whose `group` strings match
are one group; there is no id, no groups.json, and therefore nothing a
hand-edited task file can point at that does not exist. Creating a group is
naming one, and deleting the last member deletes the group with nothing left
over.

The price is that a name must be non-empty and unique within a project
(compared case-insensitively, so two names that read alike cannot quietly split
one group), and that a rename rewrites every member — the same sweep migrate.py
already does for a type rename.

Every function here leaves each bucket it touched satisfying the two rules the
renderer depends on: a group's members all sit in one bucket, and they are
contiguous in `order`.
"""

from pathlib import Path

import store


def _clean(name: str) -> str:
    cleaned = str(name).strip()
    if not cleaned:
        raise ValueError("a group name cannot be empty")
    return cleaned


def _live_tasks(project_path: Path) -> list[store.Task]:
    """Open and in-progress tasks — everything a group is drawn from.

    Completed tasks keep their `group` string in done/ so the archive stays
    meaningful, but they are not part of the group: finishing a member should
    shrink the block, not leave a row behind in it.
    """
    return store.list_tasks(project_path, include_done=False)


def _resolve(tasks: list[store.Task], task_ids) -> list[store.Task]:
    """Task objects for those ids, in the order given, or a ValueError.

    Takes an already-loaded list rather than reading again, so a caller never
    holds two objects for the same file and saves the stale one.
    """
    by_id = {task.id: task for task in tasks}
    wanted = [int(task_id) for task_id in task_ids]
    missing = [task_id for task_id in wanted if task_id not in by_id]
    if missing:
        raise ValueError(f"no such task in this project: {missing}")
    return [by_id[task_id] for task_id in wanted]


def renumber(project_path: Path, bucket: str) -> None:
    """Rewrite one bucket's `order` so every group is one contiguous run.

    Each group is a block keyed by its lowest member `order`; each ungrouped
    task is a block of its own. Blocks sort by that key, ties broken on the
    lowest member id, and members sort the same way within their block. The
    result is deterministic and idempotent, so this repairs a hand-edited file
    rather than arguing with it — and only writes the tasks whose order
    actually moved, which keeps `git status` quiet in a tracked project.
    """
    blocks: dict[tuple, list[store.Task]] = {}
    for task in _live_tasks(project_path):
        if task.bucket != bucket:
            continue
        key = ("group", task.group) if task.group else ("task", task.id)
        blocks.setdefault(key, []).append(task)

    def block_position(members: list[store.Task]) -> tuple[int, int]:
        return (min(t.order for t in members), min(t.id for t in members))

    position = 0
    for members in sorted(blocks.values(), key=block_position):
        for task in sorted(members, key=lambda t: (t.order, t.id)):
            if task.order != position:
                task.order = position
                store.save_task(task)
            position += 1


def assign(project_path: Path, task_ids, name: str) -> str:
    """Put these tasks in **that exact** group, creating it if it is new.

    Joining tasks take the group's bucket — read from its lowest-order existing
    member, before anything moves — and land at the end of it. A task already in
    the group keeps its position. When the group is new, its bucket is that of
    the first task given.

    Use create() when the name is a *suggestion* rather than an identity;
    passing a seed here would silently join whatever group already answers to
    it.
    """
    name = _clean(name)
    tasks = _live_tasks(project_path)
    joining = _resolve(tasks, task_ids)
    joining_ids = {task.id for task in joining}

    settled = [task for task in tasks
               if task.group == name and task.id not in joining_ids]
    if settled:
        bucket = min(settled, key=lambda t: (t.order, t.id)).bucket
        tail = max(task.order for task in settled) + 1
    else:
        bucket = joining[0].bucket
        tail = None

    touched = {bucket}
    for offset, task in enumerate(joining):
        touched.add(task.bucket)
        if tail is not None and task.group != name:
            task.order = tail + offset
        task.group = name
        task.bucket = bucket
        store.save_task(task)

    for one_bucket in touched:
        renumber(project_path, one_bucket)
    return name


def create(project_path: Path, task_ids, seed: str) -> str:
    """Put these tasks in a NEW group, seeded from `seed`. Returns the name used.

    Separate from assign() because the two gestures mean different things:
    dropping onto a task that is already grouped says "join that exact group",
    while dropping onto a loose one says "make a new group, called something
    like its title". One function doing both would swallow the task into an
    unrelated group whenever the seed happened to match its name.
    """
    return assign(project_path, task_ids, unique_name(project_path, seed))


def unique_name(project_path: Path, seed: str) -> str:
    """`seed` if no group answers to it, else `seed 2`, `seed 3`…"""
    seed = _clean(seed)
    taken = {task.group.casefold()
             for task in _live_tasks(project_path) if task.group}
    if seed.casefold() not in taken:
        return seed
    suffix = 2
    while f"{seed} {suffix}".casefold() in taken:
        suffix += 1
    return f"{seed} {suffix}"


def rename(project_path: Path, old: str, new: str) -> str:
    """Give a group a different name, rewriting every member.

    The name is the identity, so a collision would silently merge two groups
    and destroy one of the names — refused. Changing only the case of a group's
    own name is allowed, since that is the same group.
    """
    new = _clean(new)
    tasks = _live_tasks(project_path)
    members = [task for task in tasks if task.group == old]
    if not members:
        raise ValueError(f"no group named {old} in this project")
    if any(task.group and task.group != old
           and task.group.casefold() == new.casefold() for task in tasks):
        raise ValueError(f"a group named {new} already exists in this project")

    for task in members:
        task.group = new
        store.save_task(task)
    return new


def disband(project_path: Path, name: str) -> None:
    """Dissolve a group, leaving its members loose and where they were.

    The undo for a mis-drag. Members are already contiguous so the renumber is
    a no-op, which is why it is called unconditionally rather than reasoned
    about.
    """
    touched = set()
    for task in _live_tasks(project_path):
        if task.group != name:
            continue
        touched.add(task.bucket)
        task.group = None
        store.save_task(task)
    for one_bucket in touched:
        renumber(project_path, one_bucket)


def set_bucket(project_path: Path, name: str, bucket: str) -> None:
    """Move a whole group, which is the only way a member changes bucket.

    A group is one unit of work handed to one session; letting a single member
    drift into another bucket would make it render in two places at once. The
    group lands at the end of the target bucket, in its own internal order.
    """
    if bucket not in store.BUCKETS:
        raise ValueError(f"unknown bucket: {bucket}")
    tasks = _live_tasks(project_path)
    members = [task for task in tasks if task.group == name]
    if not members:
        raise ValueError(f"no group named {name} in this project")

    tail = max((task.order for task in tasks
                if task.bucket == bucket and task.group != name), default=-1) + 1
    touched = {bucket}
    for offset, task in enumerate(sorted(members, key=lambda t: (t.order, t.id))):
        touched.add(task.bucket)
        task.bucket = bucket
        task.order = tail + offset
        store.save_task(task)
    for one_bucket in touched:
        renumber(project_path, one_bucket)


def reorder_members(project_path: Path, name: str, ordered_ids) -> None:
    """Rearrange tasks WITHIN one group, leaving the rest of the bucket alone.

    store.reorder_bucket cannot do this job from the IN PROGRESS section: that
    view renders only part of a bucket, and reorder_bucket assigns position
    0..n-1 to whatever it is handed, so a partial list would stamp the group's
    members over whatever else occupied those positions.

    The rule instead is a permutation: the tasks named here trade the `order`
    slots they already occupy, in the sequence given. Everything else in the
    bucket keeps its slot — including members of this same group that the
    caller did not name, which is what makes a half-visible group (some members
    in progress, some not) safe to drag around.
    """
    tasks = _live_tasks(project_path)
    members = {task.id: task for task in tasks if task.group == name}
    if not members:
        raise ValueError(f"no group named {name} in this project")

    wanted = [int(task_id) for task_id in ordered_ids]
    strangers = [task_id for task_id in wanted if task_id not in members]
    if strangers:
        raise ValueError(f"not in {name}: {strangers}")

    # Read every slot before writing any of them; mid-loop the two sequences
    # overlap, and a slot read after a write would be the new value.
    slots = sorted(members[task_id].order for task_id in wanted)
    touched = set()
    for slot, task_id in zip(slots, wanted):
        task = members[task_id]
        task.order = slot
        touched.add(task.bucket)
        store.save_task(task)
    for one_bucket in touched:
        renumber(project_path, one_bucket)


def auto_group(project_path: Path, task_ids) -> str | None:
    """Record that these tasks were handed to one session — if that is unambiguous.

    Four cases, and the two that do nothing matter as much as the two that act:

    - One task, or none: a group of one needs no name.
    - None already grouped: a new group, named after the first task's title.
      `task_ids` arrives in list order, so that is the topmost ticked row.
    - Exactly one group represented: the loose ones join it. This is the common
      case — tick a whole group, add the loose task you just remembered.
    - Two or more groups represented: nothing. A group IS its name, so merging
      two of them destroys one, and that is a decision to make deliberately
      rather than a side effect of ticking two boxes.

    Never splits a group either: a partial selection out of one group leaves
    the rest of it exactly as it was.
    """
    tasks = _live_tasks(project_path)
    selected = _resolve(tasks, task_ids)
    if len(selected) < 2:
        return None

    represented = {task.group for task in selected if task.group}
    if len(represented) > 1:
        return None
    if not represented:
        return create(project_path, [task.id for task in selected], selected[0].title)

    name = represented.pop()
    loose = [task.id for task in selected if not task.group]
    if loose:
        assign(project_path, loose, name)
    return name


def remove(project_path: Path, task_ids) -> None:
    """Take exactly these tasks out of whatever group they are in."""
    tasks = _live_tasks(project_path)
    touched = set()
    for task in _resolve(tasks, task_ids):
        touched.add(task.bucket)
        task.group = None
        store.save_task(task)
    for one_bucket in touched:
        renumber(project_path, one_bucket)
