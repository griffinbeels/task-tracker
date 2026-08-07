"""Guards on what this repository publishes, and on the split documentation.

This is a public repository. Two of the things it must never carry — a task
backlog and a home directory — were previously kept out by nothing at all: the
task folder was clean because nobody had ticked the tracked box for this project
yet, and the home path in pyproject.toml had simply not been noticed. Prose
cannot hold either line, so these tests do.

The rest guard the split. CLAUDE.md is a map to `.claude/rules/`, and most of
those load only when a matching file is read. A glob that matches nothing is a
rule that silently never loads, which reads exactly like the rule not existing —
the same shape as a stale CSS selector, and just as invisible.
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RULES = REPO / ".claude" / "rules"
ROOT_DOC = REPO / "CLAUDE.md"

# The root is a map, not the documentation. It stops being one gradually, so the
# ceiling is a test rather than an intention. Anthropic's own guidance is under
# 200 lines; this leaves a little room above the current 182.
ROOT_DOC_CEILING = 250

# Working notes: kept on disk, never published. They quote conversations, name
# other projects on this machine, and carry absolute paths.
UNPUBLISHED_TREES = ("docs/superpowers/", ".planning/")

# A user's home directory, in either slash convention, plus the POSIX shapes for
# completeness. This file is excluded from its own sweep below — a scanner that
# matches its own pattern is a scanner that always fails.
_HOME_PATH = re.compile(
    r"(?:[A-Za-z]:[\\/]+Users[\\/]+|/home/|/Users/)(?!<)[A-Za-z0-9._-]+")


def _tracked_files() -> list[str]:
    """What git would publish. Not the working tree — that includes the backlog."""
    result = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", check=True)
    return [line for line in result.stdout.splitlines() if line]


def test_no_tracked_file_carries_a_home_directory_path():
    offenders = []
    for relative in _tracked_files():
        if relative == f"tests/{Path(__file__).name}":
            continue
        path = REPO / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary asset; a path would not be meaningful in one
        for number, line in enumerate(text.splitlines(), start=1):
            if _HOME_PATH.search(line):
                offenders.append(f"{relative}:{number}: {line.strip()}")

    assert not offenders, (
        "a home directory path is committed to a public repository — put the "
        "literal in CLAUDE.local.md, which is ignored, and refer to it:\n  "
        + "\n  ".join(offenders))


# Repositories this one may legitimately name: its own, and the shared module it
# depends on, which is published as a dependency anyway.
NAMEABLE = {"task_tracker", "task-tracker", "claude-console", "claude_console"}


def _sibling_projects() -> set[str]:
    """Other checkouts beside this one, discovered rather than listed.

    A hardcoded denylist would have to spell the names out, and this file is
    published — the guard would leak exactly what it exists to keep out, which
    is what the first version of it did. Reading the neighbours off disk keeps
    the names out of the repo and picks up a project created tomorrow with no
    edit here.

    Only directories that are git repositories count. "Another project" means a
    checkout, and matching on any folder name would fail every file that says
    `docs` the moment a folder called docs appeared next door.
    """
    try:
        neighbours = list(REPO.parent.iterdir())
    except OSError:
        return set()
    return {
        directory.name
        for directory in neighbours
        if directory.is_dir()
        and (directory / ".git").exists()
        and directory.name not in NAMEABLE
        and len(directory.name) >= 4
    }


def test_no_tracked_file_names_another_project_on_this_machine():
    """Machine-dependent on purpose: it can only see the neighbours it has.

    That makes it a real check here, where the neighbours are the projects whose
    names kept turning up as example values, and a no-op on a machine that has
    only cloned this one — which is the right way round for a privacy guard.
    """
    projects = _sibling_projects()
    if not projects:
        return

    offenders = []
    for relative in _tracked_files():
        if relative == f"tests/{Path(__file__).name}":
            continue
        try:
            text = (REPO / relative).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            for project in projects:
                if project in line:
                    offenders.append(f"{relative}:{number}: {line.strip()[:90]}")

    assert not offenders, (
        "another checkout on this machine is named in a public repository — use "
        "a neutral example instead:\n  " + "\n  ".join(offenders))


def test_the_task_backlog_is_never_tracked():
    """The app can flip this repo to tracked, and that would publish the backlog.

    `.tasks/.gitignore` holding `*` is what stops it, and store.ensure_tasks_dir
    writes that file. Ticking the tracked box for a project deletes it — which is
    the right behaviour for a project whose backlog is meant to be shared, and
    would be a mistake for this one.
    """
    tracked = [name for name in _tracked_files() if name.startswith(".tasks/")]
    assert not tracked, (
        "this project's own task files are staged for publication:\n  "
        + "\n  ".join(tracked))

    tasks = REPO / ".tasks"
    if tasks.exists():
        ignore = tasks / ".gitignore"
        assert ignore.exists(), ".tasks/ exists without the .gitignore that hides it"
        assert ignore.read_text(encoding="utf-8").strip() == "*", (
            ".tasks/.gitignore no longer hides everything under it")


def test_the_working_notes_stay_out_of_the_repo():
    for tree in UNPUBLISHED_TREES:
        tracked = [name for name in _tracked_files() if name.startswith(tree)]
        assert not tracked, (
            f"{tree} is git-ignored but these are still in the index — "
            f"`git rm -r --cached {tree}` (the files stay on disk):\n  "
            + "\n  ".join(tracked))


def _rule_globs(rule: Path) -> list[str]:
    """The `paths:` patterns of one rule, or [] when it loads unconditionally."""
    text = rule.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return []
    frontmatter = text.split("---\n", 2)[1]
    return re.findall(r'^\s*-\s*"([^"]+)"', frontmatter, flags=re.MULTILINE)


def test_every_rule_glob_matches_a_file_that_exists():
    """A glob matching nothing is a rule that can never load.

    Measured against Claude Code 2.1.220: a `paths:` rule loads with
    `load_reason: path_glob_match` when a matching file is read, and never
    otherwise. So a pattern left behind by a rename takes its whole rule out of
    every session, silently and in both directions — nothing warns, and the file
    still looks populated.
    """
    unmatched = []
    for rule in sorted(RULES.glob("*.md")):
        for pattern in _rule_globs(rule):
            if not list(REPO.glob(pattern)):
                unmatched.append(f"{rule.name}: {pattern!r} matches nothing")

    assert not unmatched, "\n  ".join(["stale globs:"] + unmatched)


def test_every_rule_file_is_named_in_the_root_map():
    """The root is the only place that says a rule exists. An unlisted rule is
    findable only by accident, and a listed-but-deleted one sends a reader to a
    file that is not there."""
    root = ROOT_DOC.read_text(encoding="utf-8")
    on_disk = {rule.name for rule in RULES.glob("*.md")}
    listed = set(re.findall(r"\.claude/rules/([A-Za-z0-9._-]+\.md)", root))

    assert on_disk == listed, (
        f"rules on disk but not in CLAUDE.md: {sorted(on_disk - listed)}; "
        f"named in CLAUDE.md but not on disk: {sorted(listed - on_disk)}")


def test_every_invariant_number_lives_in_exactly_one_rule():
    """Numbering survived the split because things cite invariants by number.

    Two rules claiming one number, or a number vanishing entirely, are both
    silent: a reader following a citation lands somewhere plausible either way.
    """
    heading = re.compile(r"^(\d+)\. \*\*", flags=re.MULTILINE)
    owners: dict[int, list[str]] = {}
    for rule in sorted(RULES.glob("*.md")):
        for number in heading.findall(rule.read_text(encoding="utf-8")):
            owners.setdefault(int(number), []).append(rule.name)

    duplicated = {n: files for n, files in owners.items() if len(files) > 1}
    assert not duplicated, f"invariants claimed by more than one rule: {duplicated}"

    expected = set(range(1, 32))
    assert set(owners) == expected, (
        f"missing invariants: {sorted(expected - set(owners))}; "
        f"unexpected: {sorted(set(owners) - expected)}")


def test_the_launcher_supplies_every_dependency_pyproject_cannot_resolve():
    """pyproject.toml names claude-console but gives no path to it, so whoever
    installs has to supply one. run.bat is the only installer a user touches.

    This coupling broke the moment [tool.uv.sources] came out: `uv pip install
    -e .` on a fresh venv reports the entire requirement set unsatisfiable,
    because claude-console is on no index. An existing venv hides it — the
    package is already there — so the failure only appears on a fresh clone or
    after deleting .venv, which is the worst time to find it.
    """
    # A table header is a line, not a substring: the comment that explains why
    # the table is absent necessarily names it, and matching that would make
    # this test impossible to satisfy.
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8").splitlines()
    assert not [line for line in pyproject
                if line.strip().startswith("[tool.uv.sources]")], (
        "a [tool.uv.sources] entry is back; it can only name a path, and every "
        "form of that is wrong here — see the comment in pyproject.toml")

    launcher = (REPO / "run.bat").read_text(encoding="utf-8")
    assert "claude-console" in launcher, (
        "run.bat must locate the claude-console checkout, since pyproject.toml "
        "no longer names one")
    # Comments are not commands, and the same trap as above applies: a comment
    # explaining why an install form was rejected has to quote that form.
    install = [line for line in launcher.splitlines()
               if "uv pip install" in line and not line.strip().startswith("REM")]
    assert install, "run.bat no longer installs anything"
    assert all("-e \"%CONSOLE%\"" in line for line in install), (
        "run.bat's install must pass the claude-console checkout as its own "
        f"editable, or a fresh venv cannot resolve it:\n  " + "\n  ".join(install))


def test_the_launcher_still_opens_the_tracker_when_the_index_is_unreachable():
    """Being offline is not a reason to refuse to open a tracker that already
    runs. The index is where UPDATES come from here, not a precondition.

    On 2026-08-03 a stale DNS answer sent pypi.org to the router, which served
    its own certificate; the install step failed, and run.bat exited rather
    than launching a venv that had every dependency installed and working.

    So the install's failure branch must ask whether the venv is already
    coherent — `uv pip check`, which needs no network and no build, measured at
    exit 0 in 1ms with the index pointed at a dead host — and may give up only
    when that check itself names something missing.
    """
    # Commands only. Every comment here quotes the command it explains, and
    # reading those back made an earlier version of this test vacuous: deleting
    # the readiness check left the sentence describing it, and the guard passed.
    lines = [line if not line.strip().startswith("REM") else ""
             for line in (REPO / "run.bat").read_text(encoding="utf-8").splitlines()]

    install = next(i for i, line in enumerate(lines) if "uv pip install" in line)
    readiness = next((i for i, line in enumerate(lines[install:], install)
                      if "uv pip check" in line), None)
    assert readiness is not None, (
        "run.bat's install step has no offline fallback, so an unreachable "
        "index strands a venv that could have run")

    give_up = next(i for i, line in enumerate(lines[install:], install)
                   if "exit /b" in line)
    assert readiness < give_up, (
        "run.bat gives up on an unreachable index before asking whether the "
        f"venv can already run — readiness check at line {readiness + 1}, "
        f"exit at line {give_up + 1}")


def test_the_launcher_keeps_its_crlf_line_endings():
    """run.bat jumps past that fallback with `goto`, and cmd seeks a label by
    BYTE OFFSET assuming CRLF — in an LF copy it resumes mid-line and runs
    garbage ("'tlocal' is not recognized"). Nothing about the file looks wrong
    when this breaks, and .gitattributes pins it so a clone cannot undo it.

    The flat shape the `goto` buys is load-bearing too: nesting the fallback
    inside the failure block instead swallows `exit /b 1`, so the launcher
    reports success on the one path where nothing can run (measured 2026-08-03).
    """
    raw = (REPO / "run.bat").read_bytes()
    bare_lf = raw.count(b"\n") - raw.count(b"\r\n")
    assert bare_lf == 0, (
        f"run.bat has {bare_lf} LF-only line endings; cmd needs CRLF to land "
        "its `goto` on a line boundary")


def test_the_root_map_stays_a_map():
    lines = ROOT_DOC.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= ROOT_DOC_CEILING, (
        f"CLAUDE.md is {len(lines)} lines, over its {ROOT_DOC_CEILING}-line "
        "ceiling — it loads in every session in this repo. Move the detail into "
        "a path-scoped rule under .claude/rules/ and link it from the table.")
