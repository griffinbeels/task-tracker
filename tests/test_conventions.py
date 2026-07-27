"""Conventions a reviewer would otherwise have to catch by eye.

Each of these shipped as a real bug before it became a test, and each one is
invisible at the call site — the code looks correct either way.
"""

import ast
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MODULES = sorted(REPO.glob("*.py"))
UI_SCRIPTS = sorted((REPO / "ui").glob("*.js"))

# `.claude` holds the feature worktrees (`.claude/worktrees/<slug>`), which are
# whole other checkouts of this repo at other commits. Scanning them makes this
# suite's result depend on what a *sibling* branch happens to contain — a branch
# cut before a convention landed fails it, in a checkout that is itself clean.
# That is not hypothetical: emptying the allowlist below turned every worktree
# still carrying the old `launcher.py` into an offender.
IGNORED_TREES = {".venv", ".git", "node_modules", ".tasks", ".claude"}
PYTHON_SOURCES = sorted(
    path for path in REPO.rglob("*.py")
    if not IGNORED_TREES.intersection(path.parts)
)


def _write_text_calls(module: Path):
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "write_text"):
            yield node


def test_every_write_text_suppresses_newline_translation():
    offenders = [
        f"{module.name}:{call.lineno}"
        for module in MODULES
        for call in _write_text_calls(module)
        if not any(keyword.arg == "newline" for keyword in call.keywords)
    ]

    assert not offenders, (
        "Path.write_text defaults to newline=None, which rewrites \\n as \\r\\n on "
        "Windows. A task body containing \\r\\n then gains a blank line on every "
        'save. Pass newline="\\n" at: ' + ", ".join(offenders)
    )


def test_no_bridge_result_is_compared_against_null():
    offenders = []
    for script in UI_SCRIPTS:
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"callApi\(.*(===|!==)\s*null", line):
                offenders.append(f"{script.name}:{number}")

    assert not offenders, (
        "Bridge methods that return nothing come back as JS null on SUCCESS, so "
        "null cannot double as the failure sentinel — comparing against it makes "
        "a successful call look failed. Compare against API_FAILED at: "
        + ", ".join(offenders)
    )


VENDOR = REPO / "ui" / "vendor"


def test_the_vendored_editor_bundle_is_self_contained():
    """It must be the `-all` build, which inlines its dependencies.

    The core `toastui-editor.min.js` declares all eight prosemirror-* modules
    as *external*, and its UMD wrapper has no global names for them — the
    browser branch reads `e.toastui.Editor = t(e[void 0], e[void 0], ...)`,
    handing the editor `undefined` for every dependency. `window.toastui`
    exists, so nothing looks wrong until `new toastui.Editor()` throws, at
    which point Capture and click-to-edit both silently do nothing.

    That shipped. The size-and-not-a-404 check below passed the whole time,
    because a file can be the right size, be real, and still be the wrong
    build. This asserts the property that actually matters.
    """
    bundle = (VENDOR / "toastui-editor-all.min.js").read_text(
        encoding="utf-8", errors="ignore")

    unbundled = [name for name in ("prosemirror-state", "prosemirror-view",
                                   "prosemirror-model")
                 if f'require("{name}")' in bundle]

    assert not unbundled, (
        "This bundle expects the page to supply modules it does not contain: "
        + ", ".join(unbundled)
        + ". Vendor toastui-editor-all.min.js, which inlines them."
    )
    assert "e[void 0]" not in bundle, (
        "The UMD wrapper is passing `undefined` for its external dependencies, "
        "which means this is the core build, not the standalone one."
    )


def test_the_vendored_editor_assets_are_present_and_not_error_pages():
    expected = {
        "toastui-editor-all.min.js": 400_000,
        "toastui-editor.min.css": 100_000,
        "toastui-editor-dark.css": 1_000,
    }
    problems = []
    for name, floor in expected.items():
        path = VENDOR / name
        if not path.exists():
            problems.append(f"{name} is missing")
        elif path.stat().st_size < floor:
            problems.append(f"{name} is {path.stat().st_size} bytes, expected >{floor}")

    assert not problems, (
        "The editor is vendored, not loaded from a CDN, because the UI is "
        "served from file:// and must work offline. A truncated or missing "
        "asset fails only when a user opens the editor: " + "; ".join(problems)
    )


_ELEMENT_ID = re.compile(r"""getElementById\(\s*(['"])([^'"]+)\1\s*\)""")
_MARKUP_ID = re.compile(r'id="([^"]+)"')
_ASSIGNED_ID = re.compile(r"""\.id\s*=\s*(['"])([^'"]+)\1""")


def test_every_element_id_the_scripts_ask_for_exists():
    """A renamed id is silent, and a merge is where it bites.

    getElementById returns null for an id nothing defines; the first property
    access on that null throws mid-render, which leaves the window blank with
    no error anyone sees. There is no JS test runner here, so nothing else
    catches it.

    The case that motivated this: `#wip-warning` was renamed to
    `#group-limit-warning` on main while `feature/selection-bar` and
    `feature/session-identity` both still carried
    `getElementById('wip-warning')` in ui/state.js. Those are separate regions
    of separate files, so the text merge is clean and the suite stays green —
    the app just stops drawing (2026-07-25).
    """
    defined = set(_MARKUP_ID.findall(
        (REPO / "ui" / "index.html").read_text(encoding="utf-8")))
    sources = {script: script.read_text(encoding="utf-8") for script in UI_SCRIPTS}
    # Elements the scripts build themselves are legitimate lookup targets and
    # never appear in the markup — #in-progress is one.
    for text in sources.values():
        defined |= {match.group(2) for match in _ASSIGNED_ID.finditer(text)}

    missing = sorted(
        f"{script.name}:{text[:match.start()].count(chr(10)) + 1} {match.group(2)}"
        for script, text in sources.items()
        for match in _ELEMENT_ID.finditer(text)
        if match.group(2) not in defined
    )

    assert not missing, (
        "These ids are asked for by a script and defined by neither index.html "
        "nor any script. getElementById returns null and the next property "
        "access throws inside a render, emptying the window: " + ", ".join(missing)
    )


# Nothing in this repo may open a console window any more, and the empty
# allowlist is the point. `launcher.py` and `test_launcher.py` used to be the
# two exceptions, because `launcher.py` spawned the handed-off session and that
# console IS the feature. Both moved to `claude_console`, which carries its own
# copy of this guard — a guard left behind when the code it covers moves out
# still passes, and covers nothing.
#
# This file names the flags in order to find them, so it cannot scan itself.
MAY_OPEN_A_CONSOLE_WINDOW = {Path(__file__).name}

# Every spelling that reaches CreateProcess asking for a new console: the
# subprocess constant, and the alias `claude_console.session` gives it, since a
# copied line is the likeliest way either comes back.
CONSOLE_WINDOW_FLAGS = {"CREATE_NEW_CONSOLE", "NEW_CONSOLE"}


def _new_console_references(module: Path):
    """Line numbers where `module` names a new-console flag, in any spelling.

    Parsed rather than grepped so that prose about the flag — the comments in
    `_console_probe.py` explaining why it was removed — does not count as a use
    of it. String constants DO count: `getattr(subprocess, "CREATE_NEW_CONSOLE",
    0)` is how `launcher.py` spells it, and a copy of that line is the likeliest
    way this comes back.
    """
    tree = ast.parse(module.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        named = (isinstance(node, ast.Attribute) and node.attr in CONSOLE_WINDOW_FLAGS
                 or isinstance(node, ast.Name) and node.id in CONSOLE_WINDOW_FLAGS
                 or isinstance(node, ast.Constant) and node.value in CONSOLE_WINDOW_FLAGS)
        if named:
            yield node.lineno


def test_nothing_in_this_repo_may_open_a_console_window():
    """A test that puts a window on screen is a bug in the test.

    Windows 11 delegates every *new* console to whatever is set as the default
    terminal application. When that is Windows Terminal, WT creates the window
    itself, so the spawner's STARTUPINFO never reaches it and
    `SW_SHOWNOACTIVATE` is silently discarded — a full, activated Terminal
    window opens for as long as the child lives.

    `tests/_console_probe.py` used CREATE_NEW_CONSOLE, so every run of this
    suite flashed one over whatever the user was typing into. That is most of
    what "random windows keep popping up while Claude works" turned out to be
    (2026-07-25). CREATE_NO_WINDOW still creates a *real* console —
    AttachConsole, WriteConsoleInput and the screen buffer all work against it
    — so nothing that merely needs to reach a console needs to show one.

    The allowlist is empty now that the hand-off's own console lives in
    `claude_console`. That repo carries its own copy of this test rather than
    relying on this one, because this one scans `REPO.rglob("*.py")` — the
    moment the code moved out, it left this guard's reach entirely, and a guard
    that covers nothing still passes.
    """
    offenders = [
        f"{module.relative_to(REPO).as_posix()}:{lineno}"
        for module in PYTHON_SOURCES
        if module.name not in MAY_OPEN_A_CONSOLE_WINDOW
        for lineno in _new_console_references(module)
    ]

    assert not offenders, (
        "CREATE_NEW_CONSOLE opens a Windows Terminal window that no flag can "
        "soften, over whatever the user is doing. Use CREATE_NO_WINDOW — it is "
        "still a real console — at: " + ", ".join(offenders)
    )


def test_the_editor_assets_are_loaded_from_vendor_not_a_cdn():
    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")

    assert "uicdn.toast.com" not in markup and "cdn.jsdelivr.net" not in markup, (
        "A CDN reference makes the app require a network connection to edit a "
        "task. Load the vendored copies in ui/vendor/ instead."
    )


def test_the_stylesheet_has_no_stray_comment_markers():
    """An unbalanced comment silently DELETES the rule after it.

    Twice on 2026-07-26 a comment was extended by writing the new prose after
    its closing `*/` instead of before it. CSS then reads everything from there
    to the next `{` as one selector, cannot parse it, and drops the whole rule
    — so `section.drop-zone` was never defined and no bucket section ever drew
    its drop box. Nothing errors, nothing logs, and the JS that adds the class
    looks correct in the diff.

    Strip every well-formed comment and no marker should survive. A leftover
    `*/` is prose that escaped its comment; a leftover `/*` is one never
    closed, which eats every rule until the next `*/`.
    """
    css = (REPO / "ui" / "style.css").read_text(encoding="utf-8")
    stripped = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)

    for marker in ("*/", "/*"):
        assert marker not in stripped, (
            f"Unbalanced CSS comment: a stray {marker} in ui/style.css. The "
            f"rule following it is silently discarded by the browser — extend "
            f"a comment BEFORE its closing marker, not after it."
        )


def test_every_class_the_ui_toggles_is_styled():
    """A class added by JS that the stylesheet never mentions does nothing.

    Deliberately the weakest of the three checks, and worth knowing exactly how
    weak: it catches a class name absent from ui/style.css entirely, and
    nothing else. It would NOT have caught the bug that prompted it — the
    geometry rewrite moved the join affordance from `.group-header` to the
    whole `.group` container and left the old selector behind, and
    `.drop-into` is still a substring of `.group-header.drop-into`, so this
    passes on that file. Deciding an existing selector applies to the element
    it is written against needs the DOM, and no text check substitutes for it.

    What it does earn: adding a state class and forgetting the rule outright is
    a real and easy mistake, and it is silent. The stray-comment test above
    covers a rule the browser discards; the by-hand list in CLAUDE.md covers
    the rest, because that is the only thing that actually runs the app.

    Only `classList.add` is checked, not `className =`. These are the state
    classes, toggled far from the markup that defines the element.
    """
    css = (REPO / "ui" / "style.css").read_text(encoding="utf-8")
    for script in UI_SCRIPTS:
        source = script.read_text(encoding="utf-8")
        # The whole argument list, so a class chosen by a ternary is seen too.
        for call in re.findall(r"classList\.add\(([^)]*)\)", source, re.DOTALL):
            for name in re.findall(r"['\"]([A-Za-z][\w-]*)['\"]", call):
                assert f".{name}" in css, (
                    f"{script.name} adds the class '{name}', which ui/style.css "
                    f"never styles. It will silently do nothing."
                )


def test_the_overflow_button_still_clips_its_sprite():
    """Without the clip, a sliver of the NEXT icon draws off the `…` button.

    The toolbar icons are one 466x146 sprite sheet placed by
    background-position-x. `more` is the 32px cell at -412px and another icon
    begins at 444px with no gutter between them, so at a fractional device
    scale the sampler blends that neighbour into the button's own right-hand
    columns. Only `more` shows it: every icon bleeds identically, but the rest
    are followed by another button rather than by empty toolbar.

    Pinned because losing it is silent and expensive. It draws only at some
    device scales, on one button, and only once the window is narrow enough to
    collapse the toolbar — and it reads so exactly like a stranded group
    divider that it was diagnosed as one three times before a dump of the real
    window's DOM showed there was no element there at all (2026-07-26). The
    rule is also one line in a file two branches were editing at once, and it
    was already lost to a revert once.
    """
    css = (REPO / "ui" / "style.css").read_text(encoding="utf-8")
    rule = re.search(r"\.toastui-editor-toolbar-icons\.more\s*\{([^}]*)\}", css)

    assert rule and "clip-path" in rule.group(1), (
        "ui/style.css must clip the `more` toolbar button, or the sprite sheet "
        "bleeds its next cell down the button's right edge and draws what "
        "looks like a stray divider."
    )


def test_every_ui_script_is_loaded_by_the_page():
    """A new .js file with no <script> tag is dead code that looks alive.

    There is no bundler and no module graph — the eight scripts share one
    global scope purely because index.html lists them, so a file nobody lists
    simply never runs. Every symbol it defines is then undefined at the call
    site, which throws inside whichever handler reaches for it first: the same
    silent, mid-render failure `test_every_element_id_the_scripts_ask_for_exists`
    exists for, arrived at from the other direction.

    "Add its `<script>` tag only if you create a new file" is a documented step
    in CLAUDE.md, which is exactly the kind of step that gets missed.
    """
    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")
    loaded = set(re.findall(r'<script src="([^"]+)"', markup))

    unloaded = sorted(script.name for script in UI_SCRIPTS
                      if script.name not in loaded)

    assert not unloaded, (
        "These files are in ui/ and never loaded by index.html, so nothing "
        "they define exists at runtime: " + ", ".join(unloaded)
    )
