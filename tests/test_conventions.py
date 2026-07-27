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


# The two buttons that open a Claude session on the ticked tasks: the toolbar's
# and the selection bar's. Named here rather than discovered, because the whole
# assertion is that a THIRD spelling of the same action does not appear.
SPIN_UP_BUTTON_IDS = ("spin-up", "selection-spin-up")


def _onclick_handler(text: str, element_id: str):
    """The bare function name assigned to `#element_id`'s onclick, or None.

    Deliberately refuses an inline arrow: `= async () => {` does not match, so
    a handler written out a second time reads as unwired rather than as a
    second opinion about what the button does.
    """
    match = re.search(
        rf"getElementById\('{re.escape(element_id)}'\)\.onclick\s*=\s*"
        r"([A-Za-z_$][\w$]*)\s*;",
        text)
    return match.group(1) if match else None


def test_both_spin_up_buttons_run_the_same_handler():
    """One action, two places to press it — or they drift, silently.

    The toolbar's button and the bar's take the same selection, read the same
    name box and call the same bridge method; the only difference is where the
    cursor has to travel. Copying the handler body under the second id is the
    obvious way to add the second button and is how the two come to mean
    different things — a fix or a guard added to one would simply not be in the
    other, and with no JS test runner here nothing would report it. The bug it
    would look like is the older one this app already shipped: `wireDrag` as one
    controller per section, where every drop across a boundary quietly did
    nothing (invariant 27).
    """
    text = (REPO / "ui" / "tasks.js").read_text(encoding="utf-8")
    handlers = {button: _onclick_handler(text, button)
                for button in SPIN_UP_BUTTON_IDS}

    unwired = sorted(button for button, handler in handlers.items() if handler is None)
    assert not unwired, (
        "These buttons have no named onclick handler in ui/tasks.js — either "
        "nothing wires them, which makes them dead controls the app still "
        "draws, or one was written as an inline function, which is a second "
        "copy of the hand-off: " + ", ".join(unwired)
    )

    assert len(set(handlers.values())) == 1, (
        "The toolbar's Claude button and the selection bar's must call the "
        "same function. They are one action with two positions, and two "
        f"handlers is two behaviours nobody is comparing: {handlers}"
    )


def _button_markup(text: str, element_id: str):
    """`(attributes, inner html)` for `<button id="element_id" …>…</button>`."""
    match = re.search(
        rf'<button\b([^>]*\bid="{re.escape(element_id)}"[^>]*)>(.*?)</button>',
        text, re.DOTALL)
    return match.groups() if match else (None, None)


def test_no_claude_button_carries_a_text_label():
    """Four controls open a Claude session, and all four are the same glyph.

    The toolbar's and the selection bar's used to read "Spin up Claude" while a
    task row's and a group header's carried the icon, which is the shape a user
    reads as two different features rather than one control in four places.
    They are all `CLAUDE_ICON` now, and the only difference left is a CSS rule
    about being inside a row.

    The way that comes undone is a label creeping back into one of the two
    markup buttons — they are empty in index.html precisely so the glyph has a
    single definition, and an empty button is exactly what a careless edit
    "fixes" by typing words into it. So this asserts emptiness, that each one
    is a `.claude` like the other two, and that the glyph is defined once.

    What it cannot see: whether the glyph is VISIBLE. `.actions button` outranks
    a bare `.claude`, so the bar's button renders as a pill unless the override
    beside it wins — a specificity fight no text search can referee. That half
    is checked by rendering the real stylesheet and looking at it.
    """
    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")

    missing = [button for button in SPIN_UP_BUTTON_IDS
               if _button_markup(markup, button) == (None, None)]
    assert not missing, (
        "These buttons are not in ui/index.html as plain <button id=…> "
        "elements, so nothing here can check what is inside them: "
        + ", ".join(missing)
    )

    labelled = {button: inner.strip()
                for button in SPIN_UP_BUTTON_IDS
                for _, inner in [_button_markup(markup, button)]
                if inner.strip()}
    assert not labelled, (
        "A Claude button has text in it. Every control that opens a Claude "
        "session is the Claude glyph and nothing else; these are empty in "
        "index.html because ui/tasks.js puts CLAUDE_ICON in them, so text "
        "here is either a label coming back or a second copy of the icon: "
        f"{labelled}"
    )

    unclassed = [button for button in SPIN_UP_BUTTON_IDS
                 if 'class="claude"' not in _button_markup(markup, button)[0]]
    assert not unclassed, (
        "These buttons do not carry class=\"claude\", so they get none of the "
        "orange, the hover tint or the disabled state the other two Claude "
        "buttons have — and with no label left they would draw as nothing at "
        "all: " + ", ".join(unclassed)
    )


def test_the_claude_glyph_has_exactly_one_definition():
    """One mark, one place it is written down.

    A second copy is invisible until the two drift, and drawing a Claude button
    is now the whole of what four controls do — so a hand-pasted <svg> in the
    markup or a second CLAUDE_ICON in another script is how one of them quietly
    stops matching the rest.
    """
    definitions = [script.name for script in UI_SCRIPTS
                   if re.search(r"^const CLAUDE_ICON\s*=", script.read_text(encoding="utf-8"),
                                re.MULTILINE)]
    assert definitions == ["tasks.js"], (
        "CLAUDE_ICON must be defined exactly once, in ui/tasks.js, and every "
        f"Claude button must take the glyph from there. Found: {definitions}"
    )

    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")
    assert "<svg" not in markup, (
        "ui/index.html holds an <svg>. Every icon in this app is a const in a "
        "script, interpolated where it is needed, so that changing the mark "
        "changes it everywhere at once."
    )

    # Each button the markup leaves empty has to be filled by something, or it
    # is a control that draws nothing. Windowed rather than pinned to the exact
    # statement so that unrolling the loop into one line per id still passes —
    # what matters is that the id and the glyph are named together.
    script = (REPO / "ui" / "tasks.js").read_text(encoding="utf-8")
    filled = set()
    for assignment in re.finditer(r"\.innerHTML\s*=\s*CLAUDE_ICON", script):
        window = script[max(0, assignment.start() - 300):assignment.end() + 300]
        filled.update(button for button in SPIN_UP_BUTTON_IDS
                      if f"'{button}'" in window)

    unfilled = sorted(set(SPIN_UP_BUTTON_IDS) - filled)
    assert not unfilled, (
        "These buttons are empty in index.html and nothing in ui/tasks.js puts "
        "CLAUDE_ICON into them, so they render as a blank 28px gap in the "
        "toolbar or the selection bar: " + ", ".join(unfilled)
    )


# What floats over what, bottom rung first. Every one of these is a full-window
# or edge-anchored surface, and the order between them is the whole design:
# the bar covers the list, an overlay covers the bar, the editor covers the
# other overlays, and the zoom readout covers everything because it reports on
# the editor's own size.
STACKING_ORDER = ("#selection-bar", "#drag-layer", ".overlay", "#editor", "#zoom-badge")

_Z_INDEX = re.compile(r"z-index:\s*(\d+)\s*;")


def test_the_floating_surfaces_are_ranked_in_one_order():
    """Painting order is not DOM order once anything makes a stacking context.

    The selection bar carried no z-index at all, on the reasoning that it sits
    before the overlays in index.html and therefore loses to them in DOM order.
    That was true and it was not the whole rule: among elements that all resolve
    to `z-index: auto`, tree order decides — and #task-list comes AFTER the bar
    in the markup, so anything in the list that makes a stacking context of its
    own paints on top of it. `opacity` below 1 makes one, and 28 rules in
    ui/style.css set one; h2 (the bucket headings) and .bucket are two of them.
    The reported symptom was a `now` dropdown and a NOW heading showing through
    an opaque bar, which reads as the bar being transparent and is not
    (2026-07-26, measured: the fill is rgb(30, 30, 30) at opacity 1).

    Hit-testing follows painting, so the same defect ate clicks aimed at Done.

    What this cannot catch: a NEW full-window overlay added with no rank at all.
    It would inherit `.overlay`'s 2 if it carries that class, which is right,
    and would sit under the bar if it does not — invisible, exactly like the
    editor-under-Progress bug that put #editor's rank here in the first place.
    Nor can it see an element that is ranked correctly and positioned wrongly.
    """
    # Comments go first, and that is not tidiness: every rank in this file is
    # discussed in prose above its own rule, so the first textual mention of
    # `#selection-bar` is inside the comment at the top of the stylesheet. A
    # search over the raw text finds that one, reads the NEXT rule's block, and
    # reports the bar as unranked while it is ranked one line below.
    css = re.sub(r"/\*.*?\*/", "", (REPO / "ui" / "style.css").read_text(encoding="utf-8"),
                 flags=re.DOTALL)

    ranks = {}
    for selector in STACKING_ORDER:
        # Every block for this selector, not the first: a selector may be
        # written twice, and reading only the first one answers with whichever
        # rule happens to come earlier rather than with the one that wins the
        # cascade. Last declaration wins, exactly as the browser resolves it.
        declared = [_Z_INDEX.search(block) for block in re.findall(
            rf"(?<![\w.#-]){re.escape(selector)}\s*(?:,[^{{]*)?\{{([^}}]*)\}}", css)]
        found = [match for match in declared if match]
        ranks[selector] = int(found[-1].group(1)) if found else None

    unranked = [selector for selector, rank in ranks.items() if rank is None]
    assert not unranked, (
        "These floating surfaces carry no z-index, so they fall back to `auto` "
        "and are ordered by where they happen to sit in index.html — which is "
        "how an opaque bar ends up under the list it floats over: " + ", ".join(unranked)
    )

    order = [ranks[selector] for selector in STACKING_ORDER]
    assert order == sorted(set(order)), (
        "These ranks must be strictly increasing in this order — "
        f"{' < '.join(STACKING_ORDER)} — and they are {ranks}. Equal ranks fall "
        "back to DOM order, which is the tie #editor's own rule exists to break."
    )


def test_every_bridge_call_names_a_method_that_exists():
    """A renamed or misspelled bridge method fails at click time, not at load.

    `callApi(name, ...)` reaches `window.pywebview.api[name]` — a plain property
    lookup, so a name nothing answers to is `undefined` until the handler that
    calls it runs, and then it throws inside a click nobody is watching. There
    is no JS test runner here and no module graph to check the name against,
    which is why CLAUDE.md's worktree notes end with "grep for the old name"
    after any rename: this is that grep, run by the build instead of by hand.

    Read out of app.py's text rather than by importing it — the same reason
    every other check in this file parses source: importing pulls in webview
    and claude_console, and this question is answerable without either.
    """
    api = next(node for node in ast.parse(
        (REPO / "app.py").read_text(encoding="utf-8")).body
        if isinstance(node, ast.ClassDef) and node.name == "Api")
    methods = {node.name for node in api.body
               if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}

    offenders = []
    for script in UI_SCRIPTS:
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            for called in re.findall(r"callApi\(\s*'([^']+)'", line):
                if called not in methods:
                    offenders.append(f"{script.name}:{number} calls {called}")

    assert not offenders, (
        "These bridge calls name no method on app.Api, so each one throws the "
        "first time its handler runs: " + ", ".join(offenders)
    )


def _without_comment(line):
    """The code part of a JS line, so a rule can be DESCRIBED without breaking it.

    Both call-site tests below search for a literal, and the comment above the
    function that owns that literal is the most natural place in the codebase
    to write it down. Without this, explaining the convention in prose next to
    the code it governs fails the build, which teaches the opposite lesson.
    Line comments only — no `/* */` spans anything here, and a match inside a
    string is not a thing either file does.
    """
    return line.split("//")[0]


def test_the_drag_geometry_never_reads_the_pointer_directly():
    """Where a drop lands is decided by the card's centre, not by the mouse.

    Those are different points, and the difference IS the bug this replaced. The
    pointer sits wherever you happened to grab the row, so grabbing two pixels
    above a row's bottom edge put it below that row's own midpoint before the drag
    had begun — a 6px SIDEWAYS twitch then reordered it, having moved down not at
    all (measured 2026-07-26). Where you grabbed a row decided whether it
    reordered instantly.

    `ui/drag.js` builds the probe, once, and hands it in. A helper in
    `ui/drag-geometry.js` that reached for `event.clientY` instead would work — and
    would silently aim whichever decision it owns with the pointer again, while
    every other decision used the card. Two rules disagreeing about where the
    gesture IS is not something a reviewer would see in a diff; it shows up as the
    drop landing one slot off, sometimes.

    What it cannot catch: a probe built wrongly in drag.js, and a helper handed
    the pointer's coordinates under the name `probe`.
    """
    source = (REPO / "ui" / "drag-geometry.js").read_text(encoding="utf-8")
    offenders = [
        f"{number}: {line.strip()}"
        for number, line in enumerate(source.splitlines(), start=1)
        if "clientX" in _without_comment(line) or "clientY" in _without_comment(line)
    ]
    assert not offenders, (
        "This file must decide from the `probe` point it is handed, never from an "
        "event — otherwise one decision aims with the pointer and the rest aim "
        "with the card:\n  " + "\n  ".join(offenders)
    )


def test_the_selection_is_read_from_the_list_only():
    """A row's clone is not a row, and six queries could not tell the difference.

    Dragging now lifts a `position: fixed` CLONE of the row into `#drag-layer` —
    checkboxes, group container, `data-project` and `data-id` all copied. Every
    document-wide query for `.task`, `.group`, `.select` or `.select-group` then
    finds one more of each than the list holds, and each consequence is silent
    and separately wrong: `selectedIds()` counts a second ticked task,
    `restoreTicks` ticks a box in a decoration nothing can ever clear, Clear
    reports having cleared it, and `focusGroupName` — which runs immediately
    after a pair drop, while the card may still be settling — opens the rename
    box inside a clone that is about to be deleted.

    None of the six authors could have known: five predate the drag layer, and
    "the rows on screen" was an exact synonym for "the rows in the list" until it
    was not. Scoping is what makes it true again, and this is the mechanism
    rather than the principle — a seventh unscoped query is a build failure, not
    something a reviewer has to notice.

    What it cannot catch: a query built by string concatenation, and a NEW
    container of cloned rows that is not `#drag-layer`.
    """
    SELECTION_CLASSES = (".task", ".group", ".select-group", ".select")
    offenders = []
    for script in UI_SCRIPTS:
        for number, line in enumerate(
                script.read_text(encoding="utf-8").splitlines(), start=1):
            code = _without_comment(line)
            for match in re.finditer(
                    r"document\.querySelectorAll?\(\s*'([^']*)'", code):
                selector = match.group(1)
                if not any(name in selector for name in SELECTION_CLASSES):
                    continue
                if "#task-list" in selector or "#drag-layer" in selector:
                    continue
                offenders.append(f"{script.name}:{number}  {selector}")

    assert not offenders, (
        "These query the whole document for rows, so they also find the clone "
        "the drag lifts into #drag-layer. Scope them to `#task-list ` — or to "
        "`#drag-layer ` if the clone really is the target:\n  "
        + "\n  ".join(offenders)
    )


def test_only_the_selection_owns_completing_tasks():
    """A `done` button that completes tasks itself ignores the selection.

    Three buttons finish tasks — a task row's `done`, a group header's `done`,
    and the bar's Done — and the rule that makes them one control is that they
    all go through completeWithSelection in ui/selection.js: what a button
    names is what it completes, unless every task it names is ticked, in which
    case the tick wins. A fourth button written against complete_tasks or
    completeTasksWithConfirm directly gets none of that, and the symptom is the
    one that was reported: four tasks ticked, the bar saying "4 selected", and
    a click finishing exactly one of them.

    What this cannot see: a button that calls completeWithSelection with the
    wrong ids, and a button that completes nothing at all. It pins where the
    rule lives, not that a caller means it.
    """
    offenders = []
    for script in UI_SCRIPTS:
        if script.name == "selection.js":
            continue
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            code = _without_comment(line)
            if "completeTasksWithConfirm" in code or "'complete_tasks'" in code:
                offenders.append(f"{script.name}:{number}")

    assert not offenders, (
        "Completing tasks belongs to ui/selection.js, which is where the rule "
        "about what a tick means lives — call completeWithSelection(project, "
        "ids) instead at: " + ", ".join(offenders)
    )


def test_only_one_call_site_hands_tasks_to_claude():
    """The symmetric half of the test above, for the other thing a row can do.

    Two controls open a session on tasks — the toolbar's Claude button and
    every task row's — and four things have to come out the same either way:
    which tasks (aimedAt), whether the batch-name row is read, the refresh, and
    whether the ticks a refresh threw away are put back. All four live in
    handOff in ui/tasks.js, and one call site is what forces a third control
    through them rather than past them.

    Deliberately a count and not an allowlist: naming the owning file would
    still let a second button in that same file write its own hand-off, which
    is exactly the shape the bug took the first time (a `done` that completed
    the row it sat in while the bar said "4 selected").

    What this cannot see, so that green is not mistaken for proof: a caller
    that reaches handOff with the wrong ids, a button that resolves its own
    targets and then calls it, and a button that does nothing at all. It pins
    where the action lives, not that a caller meant it.
    """
    sites = []
    for script in UI_SCRIPTS:
        for number, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            if "callApi('hand_off'" in _without_comment(line):
                sites.append(f"{script.name}:{number}")

    assert len(sites) == 1, (
        "Opening a session on tasks belongs to exactly one function — handOff "
        "in ui/tasks.js — because the batch name, the refresh and what becomes "
        "of the ticks all live there. Call it instead of callApi('hand_off', "
        "...). Call sites found: " + ", ".join(sites)
    )
