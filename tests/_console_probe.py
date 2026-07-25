"""Two halves of the console-typing test, kept out of the pytest process.

`paste` attaches this process to someone else's console, which means leaving
its own — pytest's terminal would go with it. Running both halves here keeps
that where it belongs: in a throwaway process.

  child   prints a fake "ready" prompt, then logs every character it reads
  parent  opens the child in a new console, types into it, prints the log
"""

import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import console_input  # noqa: E402


def run_child(log_path: str) -> None:
    import msvcrt

    # One of console_input.READY_MARKERS: the parent waits to see it before
    # typing, exactly as it waits for a real session's prompt box.
    print("? for shortcuts", flush=True)
    seen = []
    deadline = time.time() + 15
    while time.time() < deadline and console_input.PASTE_END not in "".join(seen):
        if msvcrt.kbhit():
            seen.append(msvcrt.getwch())
        else:
            time.sleep(0.01)
    Path(log_path).write_text("".join(seen), encoding="utf-8", newline="\n")


def run_parent() -> None:
    log_path = str(Path(__file__).with_name("_console_probe_log.txt"))
    Path(log_path).unlink(missing_ok=True)
    child = subprocess.Popen(
        [sys.executable, __file__, "child", log_path],
        creationflags=subprocess.CREATE_NEW_CONSOLE)
    typed = console_input.paste(child.pid, "hello there", timeout=20)
    child.wait(timeout=30)
    received = Path(log_path).read_text(encoding="utf-8")
    Path(log_path).unlink(missing_ok=True)
    # A new console arrives with a few stray characters of its own in the
    # input buffer, so what matters is that the payload is delivered whole and
    # unbroken — which is what the paste markers around it are for.
    payload = console_input.PASTE_START + "hello there" + console_input.PASTE_END
    print(f"typed={typed}")
    print(f"delivered={payload in received}")
    print(f"received={received!r}")


if __name__ == "__main__":
    if sys.argv[1] == "child":
        run_child(sys.argv[2])
    else:
        run_parent()
