import subprocess
import sys
from pathlib import Path

import console_input

PROBE = str(Path(__file__).with_name("_console_probe.py"))


def characters_of(records):
    return "".join(records[index].Event.KeyEvent.uChar.UnicodeChar
                   for index in range(len(records)))


def test_every_character_is_written_as_a_press_and_a_release():
    records = console_input.key_records("hi")
    pressed = [bool(records[index].Event.KeyEvent.bKeyDown)
               for index in range(len(records))]

    assert len(records) == 4
    assert characters_of(records) == "hhii"
    assert pressed == [True, False, True, False]


def code_units_of(records):
    """The raw UTF-16 code unit in each record.

    Read as a number rather than through UnicodeChar: half a surrogate pair is
    not a character, and asking ctypes to hand one back as a `str` is asking
    for trouble that has nothing to do with what is being tested.
    """
    return [records[index].Event.KeyEvent.uChar.Code
            for index in range(len(records))]


def utf16_units(text):
    raw = text.encode("utf-16-le", "surrogatepass")
    return [int.from_bytes(raw[at:at + 2], "little")
            for at in range(0, len(raw), 2)]


def test_an_emoji_is_typed_as_its_two_utf16_code_units():
    # A console input record holds one UTF-16 code unit, not one Python
    # character. An emoji is a surrogate pair, so it needs two records — four
    # with press and release — and assigning it to a single WCHAR raises
    # TypeError. That exception surfaced nowhere: paste() runs on a daemon
    # thread, so one emoji in a task body silently stopped the entire hand-off
    # from being typed, with the clipboard copy the only surviving path.
    records = console_input.key_records("\U0001F680")

    assert len(records) == 4
    assert code_units_of(records) == [0xD83D, 0xD83D, 0xDE80, 0xDE80]


def test_a_body_mixing_plain_text_and_an_emoji_keeps_every_code_unit_in_order():
    text = "ship it \U0001F680 now"

    records = console_input.key_records(text)

    expected = [unit for unit in utf16_units(text) for _ in range(2)]
    assert code_units_of(records) == expected


def test_a_session_is_ready_once_its_prompt_hint_is_on_screen():
    assert console_input.is_ready("  ⏵⏵ bypass permissions on (shift+tab to cycle)")
    assert console_input.is_ready("? for shortcuts")


def test_a_startup_dialog_is_not_a_ready_session():
    # The workspace-trust question a never-opened folder starts on. Typing
    # here would answer it — its default is "Yes, I trust this folder" — and
    # the task text would be swallowed by the dialog instead of reaching the
    # prompt box.
    assert not console_input.is_ready(
        "Quick safety check: Is this a project you created or one you trust?\n"
        "❯ 1. Yes, I trust this folder\n  2. No, exit\n"
        "Enter to confirm · Esc to cancel")


def test_nothing_is_typed_for_empty_text():
    # Guards the no-selection hand-off, which must open a session and leave
    # its prompt alone. A pid of 0 would raise if it ever got as far as
    # attaching to a console.
    assert console_input.paste(0, "", timeout=5) is False


def test_text_is_typed_into_another_process_console():
    """The whole mechanism, against a real console this process does not own.

    Flashes a console window for a second or two — that window *is* the test.
    """
    probe = subprocess.run([sys.executable, PROBE, "parent"],
                           capture_output=True, text=True, timeout=90)

    assert probe.returncode == 0, probe.stderr
    assert "typed=True" in probe.stdout, probe.stdout
    # Delivered whole, and wrapped in the bracketed-paste markers so the
    # receiver treats it as one paste rather than keystrokes ending in Enter.
    assert "delivered=True" in probe.stdout, probe.stdout


def test_deliver_submits_every_command_before_typing_the_prompt(monkeypatch):
    events = []

    def fake_submit(pid, line, timeout=None):
        events.append(("submit", line))
        return True

    monkeypatch.setattr(console_input, "submit", fake_submit)
    monkeypatch.setattr(console_input, "paste",
                        lambda pid, text: events.append(("paste", text)))

    console_input.deliver(7, ["/rename A", "/color red"], "BUG: body")

    assert events == [("submit", "/rename A"),
                      ("submit", "/color red"),
                      ("paste", "BUG: body")]


def test_a_command_that_fails_does_not_cost_the_prompt(monkeypatch):
    # The commands are decoration; the editable prompt text is the hand-off.
    pasted = {}
    monkeypatch.setattr(console_input, "submit",
                        lambda pid, line, timeout=None: False)
    monkeypatch.setattr(console_input, "paste",
                        lambda pid, text: pasted.update(text=text))

    console_input.deliver(7, ["/rename A", "/color red"], "BUG: body")

    assert pasted == {"text": "BUG: body"}


def test_the_first_failed_command_abandons_the_rest(monkeypatch):
    tried = []

    def failing_submit(pid, line, timeout=None):
        tried.append(line)
        return False

    monkeypatch.setattr(console_input, "submit", failing_submit)
    monkeypatch.setattr(console_input, "paste", lambda pid, text: None)

    console_input.deliver(7, ["/rename A", "/color red"], "BUG: body")

    assert tried == ["/rename A"]


def test_the_first_command_waits_for_the_session_to_boot(monkeypatch):
    # The first wait is for a process to start; every later one is for a prompt
    # box already on screen.
    waits = []
    monkeypatch.setattr(console_input, "submit",
                        lambda pid, line, timeout=None: waits.append(timeout) or True)
    monkeypatch.setattr(console_input, "paste", lambda pid, text: None)

    console_input.deliver(7, ["/rename A", "/color red"], "BUG: body")

    assert waits == [console_input.READY_TIMEOUT, console_input.COMMAND_TIMEOUT]


def test_no_commands_is_just_a_paste(monkeypatch):
    pasted = {}
    monkeypatch.setattr(console_input, "paste",
                        lambda pid, text: pasted.update(text=text))

    console_input.deliver(7, [], "BUG: body")

    assert pasted == {"text": "BUG: body"}


def test_an_empty_prompt_is_never_typed(monkeypatch):
    pasted = []
    monkeypatch.setattr(console_input, "submit",
                        lambda pid, line, timeout=None: True)
    monkeypatch.setattr(console_input, "paste",
                        lambda pid, text: pasted.append(text))

    console_input.deliver(7, ["/rename A"], "")

    assert pasted == []


def test_a_submitted_line_is_bracketed_and_followed_by_its_own_enter(monkeypatch):
    # Bracketed so the "/" command popup never sees a partial token; the Enter
    # is a separate write so the popup cannot swallow it as a selection.
    written = []
    monkeypatch.setattr(console_input, "SETTLE_SECONDS", 0)
    monkeypatch.setattr(console_input, "_write_input",
                        lambda text: written.append(text) or True)
    monkeypatch.setattr(console_input, "_screen_text",
                        lambda: "shift+tab to cycle")

    class FakeAttach:
        def __enter__(self):
            return True

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(console_input, "_attached", lambda pid: FakeAttach())

    assert console_input.submit(7, "/color red") is True
    assert written == [
        console_input.PASTE_START + "/color red" + console_input.PASTE_END,
        "\r",
    ]
