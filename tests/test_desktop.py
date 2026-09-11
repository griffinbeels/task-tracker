"""Native boundary contracts; no test opens a window or another application."""

import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_native_boundary_can_load_without_gui_dependencies():
    """Missing optional GUI packages must not hide startup diagnostics."""
    result = subprocess.run([sys.executable, "-S", "-c", "import desktop"],
                            cwd=Path(__file__).resolve().parent.parent,
                            capture_output=True, text=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    assert result.returncode == 0, result.stderr


def test_mac_open_preserves_a_path_as_one_argument(monkeypatch, tmp_path):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(desktop.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    target = tmp_path / "a name ' 日本語.png"

    desktop.open_target(target)

    assert calls[0][0][0] == ["/usr/bin/open", str(target)]
    assert calls[0][1]["check"] is True
    assert not calls[0][1].get("shell", False)


def test_windows_open_uses_the_native_association(monkeypatch):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "win32")
    calls = []
    monkeypatch.setattr(os, "startfile", calls.append, raising=False)

    desktop.open_target("https://example.com/page?a=1&b=2")

    assert calls == ["https://example.com/page?a=1&b=2"]


def test_open_failure_reaches_the_bridge(monkeypatch):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "darwin")

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="No application")

    monkeypatch.setattr(desktop.subprocess, "run", fail)
    with pytest.raises(OSError, match="No application"):
        desktop.open_target("https://example.com")


@pytest.mark.parametrize("platform,modifier,key", [("darwin", "meta", "Command"),
                                                    ("win32", "ctrl", "Ctrl")])
def test_shortcuts_describe_the_platform(monkeypatch, platform, modifier, key):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", platform)
    assert desktop.shortcuts() == {"modifier": modifier, "label": key}


def test_mac_error_message_is_data_not_applescript(monkeypatch):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    calls = []
    monkeypatch.setattr(desktop.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    message = 'Could not open "file"\n日本語'

    desktop.report_fatal(message)

    args = calls[0][0][0]
    assert args[0] == "/usr/bin/osascript"
    assert args[-1] == message
    assert message not in calls[0][1]["input"]


def test_error_falls_back_to_stderr_if_native_dialog_fails(monkeypatch, capsys):
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))

    desktop.report_fatal("Missing dependency")

    assert "Missing dependency" in capsys.readouterr().err


def test_mac_geometry_uses_primary_origin_with_side_and_upper_displays(monkeypatch):
    from types import SimpleNamespace
    import desktop
    import window_state

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    primary = SimpleNamespace(x=0, y=0, width=1440, height=900)
    side = SimpleNamespace(x=1440, y=0, width=1440, height=900)
    upper = SimpleNamespace(x=0, y=900, width=1440, height=900)
    screens = [primary, side, upper]
    assert desktop.reference_screen(screens) is primary
    normalized = desktop.geometry_screens(screens)
    assert window_state.on_screen(dict(x=1540, y=100, width=420, height=600), normalized)
    assert window_state.on_screen(dict(x=100, y=-700, width=420, height=600), normalized)
    assert not window_state.on_screen(dict(x=2980, y=100, width=420, height=600), normalized)


def test_mac_saved_geometry_accounts_for_changed_primary_height(monkeypatch):
    from types import SimpleNamespace
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    initial = SimpleNamespace(height=900)
    current = SimpleNamespace(x=0, y=0, width=1440, height=1000)
    window = SimpleNamespace(x=100, y=100, width=420, height=600)
    assert desktop.saved_geometry(window, initial, [current])["y"] == 200


def test_windows_geometry_keeps_native_coordinates(monkeypatch):
    from types import SimpleNamespace
    import desktop

    monkeypatch.setattr(desktop.sys, "platform", "win32")
    screens = [SimpleNamespace(x=0, y=-900, width=1440, height=900)]
    assert desktop.reference_screen(screens) is None
    assert desktop.geometry_screens(screens) is screens
