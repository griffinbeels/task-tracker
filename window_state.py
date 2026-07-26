"""Window geometry that survives a restart, and only geometry a window can be seen at.

While a window is minimized, Windows parks it at a sentinel rectangle far off
every monitor — measured here as -32000,-32000 at 237x39 — and that is what the
toolkit reports for its position and size. Recording it is unrecoverable: the
next launch places the window somewhere the user cannot reach, cannot move, and
cannot close into a better position, so the bad value re-saves itself forever.
The only way out is deleting a JSON file nobody knows about.

So geometry is checked against the monitors on both sides of the trip. Saving
keeps the last position that was on a screen rather than overwriting it with the
sentinel, and loading discards a rectangle that no longer overlaps anything —
which also covers the window left on a monitor that has since been unplugged,
the same symptom from a different cause.
"""

import json
from pathlib import Path

import registry

DEFAULTS = {"width": 420, "height": 900, "x": None, "y": None, "on_top": True}


def _state_file() -> Path:
    # Reached through registry at call time, never bound at import: tests
    # monkeypatch CONFIG_DIR, and a module-level constant would capture the
    # real home directory and write the user's own window position.
    return registry.CONFIG_DIR / "window.json"


def on_screen(geometry: dict, screens) -> bool:
    """Would a window with this geometry be visible on one of these monitors?

    Screens are pywebview's: objects with x/y/width/height in logical pixels.
    Overlapping by any amount counts — a window dragged most of the way off an
    edge was dragged there deliberately, and rejecting it would move a window
    the user had just placed.
    """
    if not screens:
        return True                       # nothing to judge it against
    if geometry.get("x") is None or geometry.get("y") is None:
        return True                       # no position saved; the OS picks one

    left, top = geometry["x"], geometry["y"]
    right = left + geometry.get("width", 0)
    bottom = top + geometry.get("height", 0)
    return any(
        left < screen.x + screen.width and right > screen.x
        and top < screen.y + screen.height and bottom > screen.y
        for screen in screens
    )


def _stored() -> dict:
    """What is on disk, over the defaults, with a corrupt file read as absent."""
    path = _state_file()
    if not path.exists():
        return dict(DEFAULTS)
    try:
        return {**DEFAULTS, **json.loads(path.read_text(encoding="utf-8"))}
    except (json.JSONDecodeError, OSError, TypeError):
        return dict(DEFAULTS)


def load(screens) -> dict:
    """The geometry to open at, guaranteed to land somewhere visible."""
    geometry = _stored()
    if on_screen(geometry, screens):
        return geometry
    # Unreachable: keep the preference that is not geometry, and let the window
    # open at its default size wherever the OS puts a new one.
    return {**DEFAULTS, "on_top": geometry["on_top"]}


def save(geometry: dict, screens) -> None:
    """Record this geometry, or keep the last good one if it is off-screen."""
    kept = geometry if on_screen(geometry, screens) else _stored()
    path = _state_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "width": kept["width"], "height": kept["height"],
        "x": kept["x"], "y": kept["y"],
        # on_top is a preference rather than geometry, so it is taken from the
        # window even when the rectangle it came with is thrown away.
        "on_top": geometry["on_top"],
    }, indent=2), encoding="utf-8", newline="\n")
