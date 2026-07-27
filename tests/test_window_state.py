import json
from types import SimpleNamespace

import pytest

import registry
import window_state


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "CONFIG_DIR", tmp_path / "config")


# The layout this was written against: a primary monitor, and a second one to
# its LEFT — which is why negative coordinates have to stay valid. A check that
# treated x < 0 as impossible would place a real window off the screen it was
# actually on.
PRIMARY = SimpleNamespace(x=0, y=0, width=2560, height=1440)
LEFT_MONITOR = SimpleNamespace(x=-2560, y=372, width=2560, height=1440)
SCREENS = [PRIMARY, LEFT_MONITOR]

# What Windows reports for a window that is minimized: it is parked at a
# sentinel position, sized like a title bar. Measured with GetWindowRect
# against the minimized windows on this machine.
MINIMIZED = {"width": 237, "height": 39, "x": -32000, "y": -32000}


def write_saved_state(geometry):
    path = registry.CONFIG_DIR / "window.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(geometry), encoding="utf-8")


def read_saved_state():
    return json.loads((registry.CONFIG_DIR / "window.json").read_text(encoding="utf-8"))


def test_load_returns_defaults_when_nothing_was_ever_saved():
    assert window_state.load(SCREENS) == window_state.DEFAULTS


def test_load_falls_back_to_defaults_when_the_file_is_corrupt():
    registry.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (registry.CONFIG_DIR / "window.json").write_text("{not json", encoding="utf-8")

    restored = window_state.load(SCREENS)

    assert restored["width"] == 420
    assert restored["height"] == 900


def test_load_restores_a_position_on_the_monitor_left_of_the_primary():
    write_saved_state({"width": 760, "height": 1018, "x": -812, "y": 396})

    assert window_state.load(SCREENS) == {
        "width": 760, "height": 1018, "x": -812, "y": 396,
    }


def test_load_restores_a_window_hanging_off_the_edge_of_its_screen():
    # Dragged mostly off the right of the primary. The user put it there.
    write_saved_state({"width": 420, "height": 900, "x": 2500, "y": 200})

    assert window_state.load(SCREENS)["x"] == 2500


def test_load_discards_the_minimized_sentinel_and_places_the_window_normally():
    write_saved_state(MINIMIZED)

    restored = window_state.load(SCREENS)

    assert restored["x"] is None and restored["y"] is None
    assert restored["width"] == 420 and restored["height"] == 900


def test_load_discards_a_position_on_a_monitor_that_is_no_longer_attached():
    # Same unrecoverable symptom as the sentinel: a window nobody can reach.
    write_saved_state({"width": 760, "height": 1018, "x": -812, "y": 396})

    assert window_state.load([PRIMARY])["x"] is None


def test_load_fills_in_keys_a_hand_edited_file_is_missing():
    write_saved_state({"x": 100, "y": 100})

    restored = window_state.load(SCREENS)

    assert restored["width"] == 420
    assert restored["height"] == 900


def test_load_accepts_the_saved_position_when_no_screens_can_be_read():
    write_saved_state({"width": 760, "height": 1018, "x": -812, "y": 396})

    assert window_state.load([])["x"] == -812


def test_save_records_a_position_that_is_on_a_screen():
    window_state.save({"width": 760, "height": 1018, "x": -812, "y": 396}, SCREENS)

    assert read_saved_state()["x"] == -812


def test_save_keeps_the_last_good_geometry_when_closing_while_minimized():
    window_state.save({"width": 760, "height": 1018, "x": -812, "y": 396}, SCREENS)

    window_state.save(MINIMIZED, SCREENS)

    assert read_saved_state() == {
        "width": 760, "height": 1018, "x": -812, "y": 396,
    }


def test_save_falls_back_to_defaults_when_there_is_no_earlier_geometry_to_keep():
    window_state.save(MINIMIZED, SCREENS)

    assert read_saved_state() == window_state.DEFAULTS


def test_save_then_load_round_trips():
    geometry = {"width": 500, "height": 700, "x": 40, "y": 60}

    window_state.save(geometry, SCREENS)

    assert window_state.load(SCREENS) == geometry


def test_this_file_holds_geometry_and_no_preferences_at_all():
    """`on_top` used to live here, and it was never anything but geometry's
    passenger: nothing ever assigned it, so it round-tripped True forever. It
    is a preference now — settings.json, beside the other one the settings
    panel writes — and a second copy here is how the two would drift.
    """
    write_saved_state({"width": 500, "height": 700, "x": 40, "y": 60,
                       "on_top": True})

    window_state.save(window_state.load(SCREENS), SCREENS)

    assert "on_top" not in read_saved_state()
