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
