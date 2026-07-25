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
