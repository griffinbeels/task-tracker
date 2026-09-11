"""Startup order with a fake GUI; these tests never construct native windows."""

from types import SimpleNamespace

import pytest

import app


def test_unusable_replacement_does_not_close_the_current_tracker(monkeypatch):
    asked_to_take_over = []
    monkeypatch.setattr(app, "_report_fatal", lambda text: None)
    monkeypatch.setattr(app.singleton, "acquire", lambda: asked_to_take_over.append(True))
    monkeypatch.setattr(app.window_state, "load", lambda screens: {
        "width": 420, "height": 900, "x": None, "y": None,
    })
    monkeypatch.setattr(app.registry, "load_settings", lambda: SimpleNamespace(always_on_top=False))

    class BrokenGui:
        @property
        def screens(self):
            raise RuntimeError("GUI unavailable")

    monkeypatch.setattr(app, "webview", BrokenGui())

    with pytest.raises(RuntimeError, match="GUI unavailable"):
        app.main()

    assert asked_to_take_over == []


def test_geometry_is_loaded_after_handover_and_lock_is_released(monkeypatch):
    events = []
    lock = SimpleNamespace(close=lambda: events.append("released"))
    monkeypatch.setattr(app.singleton, "acquire", lambda: (events.append("handover"), lock)[1])
    monkeypatch.setattr(app.registry, "load_settings", lambda: SimpleNamespace(always_on_top=False))

    def geometry(screens):
        assert events == ["handover"]
        events.append("geometry")
        return dict(width=600, height=800, x=50, y=60)

    def construct(*args, **kwargs):
        assert kwargs["x"] == 50
        raise RuntimeError("construction failed")

    monkeypatch.setattr(app.window_state, "load", geometry)
    monkeypatch.setattr(app, "webview", SimpleNamespace(screens=[], create_window=construct))
    with pytest.raises(RuntimeError, match="construction failed"):
        app.main()
    assert events == ["handover", "geometry", "released"]
