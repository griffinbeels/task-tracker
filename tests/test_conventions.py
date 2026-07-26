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


def test_the_editor_assets_are_loaded_from_vendor_not_a_cdn():
    markup = (REPO / "ui" / "index.html").read_text(encoding="utf-8")

    assert "uicdn.toast.com" not in markup and "cdn.jsdelivr.net" not in markup, (
        "A CDN reference makes the app require a network connection to edit a "
        "task. Load the vendored copies in ui/vendor/ instead."
    )
