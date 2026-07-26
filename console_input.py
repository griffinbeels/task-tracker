"""Type text into another process's console window, the way a keyboard would.

Claude Code has no flag that pre-fills its prompt box. A positional prompt is
*submitted* the instant the session opens, and there is nothing in between — so
the only way to hand a fresh session text it has not yet sent is to deliver it
as console input. Windows allows exactly that: attach to another process's
console and write into its input buffer.

Four things this module has to get right, each learned by watching a real
session receive the text:

* **Bracketed paste.** The text is wrapped in the markers a terminal emits for
  Ctrl+V (`ESC [ 200 ~` … `ESC [ 201 ~`). Without them a newline mid-text reads
  as Enter and submits the first task on its own.
* **Wait for the prompt box.** Input written earlier is not lost — it queues in
  the console input buffer — but it can be *consumed by whatever is on screen
  first*. A folder Claude has not been trusted in opens on "Is this a project
  you trust?", whose default answer is Enter. So poll until the session's
  status hint proves the prompt box is up, and only then type.
* **Give up quietly.** Every caller has already put the same text on the
  clipboard, so a timeout costs one Ctrl+V, never the text itself.
* **A slash command must be submitted; the task text must not be.** A `/rename`
  or `/color` line is dead unless Enter follows it, but the prompt it hands off
  to is meant to sit there for the user to edit — so `deliver` submits every
  command first and pastes the prompt last. A failed command then costs only
  itself: the prompt still arrives, because it was never made to depend on the
  commands succeeding.

The calling process must not own a console it still needs: attaching to another
console means leaving your own, and there is no way back. The tracker runs
under `pythonw.exe`, which has no console at all.
"""

import ctypes
import threading
import time
from contextlib import contextmanager
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

PASTE_START = "\x1b[200~"
PASTE_END = "\x1b[201~"

# Text that only the interactive prompt box draws, so seeing it means the
# session is past its startup dialogs and is reading keystrokes as a prompt.
# Matching on rendered text is a guess about someone else's UI, so it is a
# guess that fails safe: if these ever stop appearing, the paste times out and
# the clipboard copy is still there.
READY_MARKERS = ("shift+tab to cycle", "for shortcuts")

READY_TIMEOUT = 45.0
POLL_SECONDS = 0.4

# A command's prompt box is already on screen by the time it is sent — unlike
# the first wait, which is for the process to boot — so it gets a much
# shorter timeout.
COMMAND_TIMEOUT = 5.0
# Long enough for Claude Code to act on a submitted command before the next
# write lands on top of whatever that command changed.
SETTLE_SECONDS = 0.5

_ERROR_ACCESS_DENIED = 5  # "already attached to a console" from AttachConsole
_KEY_EVENT = 0x0001
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_FILE_SHARE_READ_WRITE = 0x00000003
_OPEN_EXISTING = 3
_INVALID_HANDLE = wintypes.HANDLE(-1).value

# Console attachment is per *process*, not per thread, so two hand-offs
# starting at once would fight over which console this process is attached to.
_attachment = threading.Lock()


class _KeyChar(ctypes.Union):
    # Code overlays the same two bytes as UnicodeChar. Writing through it is
    # what lets a surrogate be set at all: half a surrogate pair is not a
    # character, so assigning one to a WCHAR raises TypeError.
    _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", ctypes.c_char),
                ("Code", ctypes.c_ushort)]


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", _KeyChar),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class _EventUnion(ctypes.Union):
    # The union is as wide as its largest member (MOUSE_EVENT_RECORD, 16
    # bytes); padding it keeps INPUT_RECORD the size Windows expects even
    # though only key events are ever written.
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("_padding", ctypes.c_byte * 16)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", _EventUnion)]


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class SMALL_RECT(ctypes.Structure):
    _fields_ = [("Left", ctypes.c_short), ("Top", ctypes.c_short),
                ("Right", ctypes.c_short), ("Bottom", ctypes.c_short)]


class CONSOLE_SCREEN_BUFFER_INFO(ctypes.Structure):
    _fields_ = [("dwSize", COORD), ("dwCursorPosition", COORD),
                ("wAttributes", wintypes.WORD), ("srWindow", SMALL_RECT),
                ("dwMaximumWindowSize", COORD)]


kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.AttachConsole.argtypes = [wintypes.DWORD]


def utf16_code_units(text: str) -> list[int]:
    """The text as Windows counts it: UTF-16 code units, not Python characters.

    A console input record holds one code unit. Anything outside the BMP — an
    emoji, most obviously — is a surrogate pair and therefore two records, so
    iterating Python characters is wrong for exactly the text a task body is
    most likely to contain.
    """
    raw = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(raw[at:at + 2], "little")
            for at in range(0, len(raw), 2)]


def key_records(text: str) -> ctypes.Array:
    """One key-down/key-up pair per UTF-16 code unit, as a real keypress arrives.

    Only the character matters — Claude reads the console as a stream, not as
    scan codes — so the virtual key and scan code are left at zero.

    Written through uChar.Code rather than uChar.UnicodeChar: a lone surrogate
    is not a character and assigning one to a WCHAR raises TypeError. That
    exception had nowhere to surface, since paste() runs on a daemon thread —
    a single emoji in a task body silently stopped the whole hand-off from
    being typed, leaving only the clipboard copy.
    """
    units = utf16_code_units(text)
    records = (INPUT_RECORD * (len(units) * 2))()
    for index, unit in enumerate(units):
        for offset, pressed in ((0, 1), (1, 0)):
            key = records[index * 2 + offset].Event.KeyEvent
            records[index * 2 + offset].EventType = _KEY_EVENT
            key.bKeyDown = pressed
            key.wRepeatCount = 1
            key.uChar.Code = unit
    return records


@contextmanager
def _attached(pid: int):
    """Borrow another process's console for the body of the `with`."""
    with _attachment:
        if not kernel32.AttachConsole(pid):
            # Access denied means this process still holds a console of its
            # own. Dropping it is the only way to attach elsewhere.
            if ctypes.get_last_error() != _ERROR_ACCESS_DENIED:
                yield False
                return
            kernel32.FreeConsole()
            if not kernel32.AttachConsole(pid):
                yield False
                return
        try:
            yield True
        finally:
            kernel32.FreeConsole()


def _write_input(text: str) -> bool:
    handle = kernel32.CreateFileW(
        "CONIN$", _GENERIC_READ | _GENERIC_WRITE, _FILE_SHARE_READ_WRITE,
        None, _OPEN_EXISTING, 0, None)
    if handle == _INVALID_HANDLE:
        return False
    records = key_records(text)
    written = wintypes.DWORD(0)
    ok = kernel32.WriteConsoleInputW(handle, records, len(records),
                                     ctypes.byref(written))
    kernel32.CloseHandle(handle)
    return bool(ok) and written.value == len(records)


def _screen_text() -> str:
    """Whatever the attached console is currently showing, as plain text."""
    handle = kernel32.CreateFileW(
        "CONOUT$", _GENERIC_READ | _GENERIC_WRITE, _FILE_SHARE_READ_WRITE,
        None, _OPEN_EXISTING, 0, None)
    if handle == _INVALID_HANDLE:
        return ""
    info = CONSOLE_SCREEN_BUFFER_INFO()
    if not kernel32.GetConsoleScreenBufferInfo(handle, ctypes.byref(info)):
        kernel32.CloseHandle(handle)
        return ""
    row_buffer = ctypes.create_unicode_buffer(info.dwSize.X)
    read = wintypes.DWORD(0)
    rows = []
    for row in range(info.srWindow.Top, info.srWindow.Bottom + 1):
        kernel32.ReadConsoleOutputCharacterW(
            handle, row_buffer, info.dwSize.X, COORD(0, row),
            ctypes.byref(read))
        rows.append(row_buffer[:read.value])
    kernel32.CloseHandle(handle)
    return "\n".join(rows)


def is_ready(screen: str) -> bool:
    return any(marker in screen for marker in READY_MARKERS)


def paste(pid: int, text: str, timeout: float = READY_TIMEOUT) -> bool:
    """Type `text` into the process's prompt box once it is accepting input."""
    if not text:
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _attached(pid) as attached:
            if attached and is_ready(_screen_text()):
                return _write_input(PASTE_START + text + PASTE_END)
        time.sleep(POLL_SECONDS)
    return False


def submit(pid: int, line: str, timeout: float = COMMAND_TIMEOUT) -> bool:
    """Type `line` into the process's prompt box and press Enter for it.

    Bracketed for the same reason `paste` is bracketed, but for the opposite
    danger: a leading "/" opens Claude Code's command-suggestion popup, a live
    UI that reads keystrokes as they arrive. A raw Enter sent right after raw
    characters risks the popup reading it as "accept the highlighted
    suggestion" rather than "submit what I typed". A paste arrives as one
    event carrying the whole line, so the popup never sees a partial token and
    has nothing to select — only then is the Enter, a separate write, safe to
    send.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _attached(pid) as attached:
            if attached and is_ready(_screen_text()):
                wrote_line = _write_input(PASTE_START + line + PASTE_END)
                wrote_enter = _write_input("\r")
                time.sleep(SETTLE_SECONDS)
                return wrote_line and wrote_enter
        time.sleep(POLL_SECONDS)
    return False


def deliver(pid: int, commands: list[str], prompt: str) -> None:
    """Submit every command, then leave `prompt` typed but unsent.

    Commands go first because they are decoration on the hand-off, not the
    hand-off itself: a command that fails to submit abandons the commands
    still queued behind it, but never costs the prompt, which is pasted
    regardless. Only the first wait is for a process that has not booted yet
    — every command after it is typed into a prompt box already on screen, so
    it gets the shorter `COMMAND_TIMEOUT` instead of `READY_TIMEOUT`.

    Returns nothing: this runs off the caller's thread, on a daemon thread
    with no one left to hand a result to.
    """
    timeout = READY_TIMEOUT
    for command in commands:
        if not submit(pid, command, timeout=timeout):
            break
        timeout = COMMAND_TIMEOUT
    if prompt:
        paste(pid, prompt)


def deliver_when_ready(pid: int, commands: list[str], prompt: str) -> threading.Thread:
    """Start `deliver` in the background so the caller's UI never waits on it."""
    waiter = threading.Thread(target=deliver, args=(pid, commands, prompt),
                              daemon=True)
    waiter.start()
    return waiter
