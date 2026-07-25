"""Single-instance lock over a loopback port, with graceful handover.

Binding a port is atomic and the OS releases it when the process dies, so
unlike a PID file there is no stale lock to clear by hand after a crash.

The listening socket doubles as a control channel. A newly launched instance
that cannot bind connects instead, asks the running one to shut down, waits
for it to save its window state and release the port, then takes over. So
launching the tracker always leaves exactly one window open, always running
the current code — which is what you want from something you start by reflex
after editing it.
"""

import socket
import threading
import time

LOCK_HOST = "127.0.0.1"
LOCK_PORT = 8090
SHUTDOWN = b"SHUTDOWN"
HANDOVER_TIMEOUT = 10.0


def _bind() -> socket.socket | None:
    lock = socket.socket()
    try:
        lock.bind((LOCK_HOST, LOCK_PORT))
        lock.listen(1)
    except OSError:
        lock.close()
        return None
    return lock


def _ask_running_instance_to_quit() -> None:
    try:
        with socket.create_connection((LOCK_HOST, LOCK_PORT), timeout=2) as client:
            client.sendall(SHUTDOWN)
    except OSError:
        pass  # nothing listening, or something that isn't us holds the port


def acquire(timeout: float = HANDOVER_TIMEOUT) -> socket.socket | None:
    """Take the lock, shutting down a running instance first if there is one.

    Returns the held socket, or None if the port never came free — which means
    something other than a Task Tracker window is holding it. Refusing to start
    beats opening a second window that silently diverges from the first.
    """
    lock = _bind()
    if lock is not None:
        return lock

    _ask_running_instance_to_quit()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.2)
        lock = _bind()
        if lock is not None:
            return lock
    return None


def serve(lock: socket.socket, on_shutdown) -> None:
    """Answer handover requests from later launches, on a daemon thread."""

    def listen() -> None:
        while True:
            try:
                connection, _ = lock.accept()
            except OSError:
                return  # lock closed — this instance is already shutting down
            with connection:
                try:
                    request = connection.recv(64)
                except OSError:
                    continue
            if SHUTDOWN in request:
                on_shutdown()
                return

    threading.Thread(target=listen, daemon=True).start()
