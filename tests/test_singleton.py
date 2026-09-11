import socket
import threading

import pytest

import singleton


@pytest.fixture(autouse=True)
def unused_port(monkeypatch):
    """Keep the tests off the real lock port so they never fight a live app."""
    with socket.socket() as probe:
        probe.bind((singleton.LOCK_HOST, 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(singleton, "LOCK_PORT", port)


def test_acquire_binds_when_the_port_is_free():
    lock = singleton.acquire()

    try:
        assert lock is not None
    finally:
        lock.close()


def test_a_second_launch_takes_over_from_the_running_one():
    first = singleton.acquire()
    assert first is not None
    asked_to_quit = threading.Event()

    def on_shutdown():
        asked_to_quit.set()
        first.close()

    singleton.serve(first, on_shutdown)

    second = singleton.acquire(timeout=5)

    try:
        assert asked_to_quit.is_set()
        assert second is not None
    finally:
        if second is not None:
            second.close()


def test_acquire_gives_up_when_something_else_holds_the_port():
    squatter = socket.socket()
    squatter.bind((singleton.LOCK_HOST, singleton.LOCK_PORT))
    squatter.listen(1)

    try:
        # A squatter that never answers the handover request must not be
        # killed or worked around — refusing to start beats a second window.
        assert singleton.acquire(timeout=1) is None
    finally:
        squatter.close()


def test_handover_when_the_old_server_closes_the_connection_first(monkeypatch):
    first = singleton.acquire()
    assert first is not None
    singleton.serve(first, first.close)

    def wait_for_server_close():
        with socket.create_connection((singleton.LOCK_HOST, singleton.LOCK_PORT), timeout=2) as client:
            client.sendall(singleton.SHUTDOWN)
            assert client.recv(1) == b""  # old server owns TCP TIME_WAIT

    monkeypatch.setattr(singleton, "_ask_running_instance_to_quit", wait_for_server_close)
    replacement = singleton.acquire(timeout=1)
    try:
        assert replacement is not None
        assert singleton._bind() is None  # still an exclusive listening lock
    finally:
        if replacement is not None:
            replacement.close()
