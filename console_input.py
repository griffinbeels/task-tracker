"""Type text into another process's console window, the way a keyboard would.

Claude Code has no flag that pre-fills its prompt box. A positional prompt is
*submitted* the instant the session opens, and there is nothing in between — so
the only way to hand a fresh session text it has not yet sent is to deliver it
as console input. Windows allows exactly that: attach to another process's
console and write into its input buffer.

Three things this module has to get right, each learned by watching a real
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


def paste_when_ready(pid: int, text: str) -> threading.Thread:
    """Start `paste` in the background so the caller's UI never waits on it."""
    waiter = threading.Thread(target=paste, args=(pid, text), daemon=True)
    waiter.start()
    return waiter
