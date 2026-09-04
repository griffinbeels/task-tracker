"""Read-only lookup into the product pipeline that lives beside a project's tasks.

A separate system tracks each feature's stage in its own file,
`.tasks/features/<NNNN>-<slug>/pipeline.md`, where `<NNNN>` is the task id
zero-padded to 4 digits. That file's own tooling is the only writer of it —
this module only ever reads it, the same way store.py treats a hand-editable
task file: broadly, and forgiving of anything it cannot parse, because a
malformed or half-written pipeline.md must cost one missing chip, never the
whole task list.
"""

import re
from pathlib import Path

import yaml

_FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)


def _feature_dir(project_path: Path, task_id: int) -> Path | None:
    """The one folder named after this task id, or None if it has none.

    Globbed rather than joined directly: the folder name carries a slug after
    the id (`0124-product-design-pipeline`) that this module has no way to
    know in advance. Sorted so two folders that somehow share a prefix (never
    expected, never enforced) resolve to the same one every time rather than
    whichever the filesystem happens to list first.
    """
    root = Path(project_path) / ".tasks" / "features"
    matches = sorted(root.glob(f"{task_id:04d}-*"))
    return matches[0] if matches else None


def lookup(project_path: Path, task_id: int) -> dict | None:
    """This task's pipeline stage, or None if it is not in the pipeline at all.

    Returns {"stage": str, "lane": str | None} — with a "retrospective" key
    added only when that file exists alongside pipeline.md, since most tasks
    never reach one. Never raises: a missing feature folder, a missing
    pipeline.md, unparsable YAML, or a frontmatter with no `stage` line are
    all the same answer from a task row's point of view — there is nothing to
    show — and get_state must not blank the whole task list over one
    external file it does not own.
    """
    directory = _feature_dir(project_path, task_id)
    if directory is None:
        return None
    pipeline_file = directory / "pipeline.md"
    try:
        text = pipeline_file.read_text(encoding="utf-8")
    except OSError:
        return None
    match = _FRONTMATTER.match(text)
    if match is None:
        return None
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None
    stage = meta.get("stage")
    if not stage:
        return None
    result = {
        "stage": str(stage),
        "lane": str(meta["lane"]) if meta.get("lane") else None,
    }
    retrospective = directory / "retrospective.html"
    if retrospective.is_file():
        result["retrospective"] = str(retrospective)
    return result
