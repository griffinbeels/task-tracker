"""An isolated preview cannot hand over or write the real tracker instance."""

import importlib

import pytest


def test_config_override_is_used_by_all_registry_files(monkeypatch, tmp_path):
    import registry

    monkeypatch.setenv("TASK_TRACKER_CONFIG_DIR", str(tmp_path / "preview"))
    original = registry.CONFIG_DIR
    try:
        importlib.reload(registry)
        assert registry.CONFIG_DIR == tmp_path / "preview"
        assert registry._projects_file().parent == registry.CONFIG_DIR
    finally:
        registry.CONFIG_DIR = original


def test_preview_port_is_stable_and_cannot_be_the_daily_port(monkeypatch, tmp_path):
    import singleton

    monkeypatch.setenv("TASK_TRACKER_CONFIG_DIR", str(tmp_path / "preview"))
    monkeypatch.delenv("TASK_TRACKER_PORT", raising=False)
    first = singleton.configured_port()
    assert first == singleton.configured_port()
    assert first != 8090
    assert 1024 <= first <= 65535


def test_explicit_port_is_supported_for_test_environments(monkeypatch):
    import singleton

    monkeypatch.setenv("TASK_TRACKER_PORT", "19421")
    assert singleton.configured_port() == 19421


@pytest.mark.parametrize("value", ["0", "-1", "65536", "bad"])
def test_invalid_port_is_rejected_before_handover(monkeypatch, value):
    import singleton

    monkeypatch.setenv("TASK_TRACKER_PORT", value)
    with pytest.raises(ValueError, match="TASK_TRACKER_PORT"):
        singleton.configured_port()
