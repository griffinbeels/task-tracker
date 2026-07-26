"""The handed-off session must start from your environment, not the tracker's.

These call the real Win32 API rather than mocking it. The whole point of the
module is what Windows itself considers a fresh login environment, so a mock
would only assert that the mock was called.
"""

import ctypes
import os
import subprocess
from pathlib import Path

import launcher
import user_environment


def test_the_block_is_walked_by_utf16_code_units_not_characters():
    """A variable holding an emoji must not desync everything after it.

    Windows stores the block as UTF-16 code units. Anything outside the BMP is
    one Python character and two units, so advancing the cursor by len() lands
    two bytes short — mid-surrogate — and every later variable is misread. The
    same mistake shipped in console_input.key_records this session, which is
    why the second instance gets a test rather than only a fix.
    """
    block = ctypes.create_unicode_buffer(
        "PLAIN=before\x00ROCKET=\U0001F680\x00AFTER=still readable\x00")

    parsed = user_environment._parse_block(ctypes.addressof(block))

    assert parsed["PLAIN"] == "before"
    assert parsed["ROCKET"] == "\U0001F680"
    assert parsed["AFTER"] == "still readable"


def upper_keys(environment):
    """Windows env names are case-insensitive; the raw block preserves the
    casing Windows stores (`Path`, `SystemRoot`) while os.environ upper-cases.
    Compare on one side only, or an absent var looks present under
    a different case."""
    return {name.upper(): value for name, value in environment.items()}


def test_a_variable_set_only_in_this_process_does_not_reach_the_session(monkeypatch):
    monkeypatch.setenv("TRACKER_ONLY_VAR", "set by the tracker's own launcher")

    assert "TRACKER_ONLY_VAR" not in upper_keys(user_environment.login_environment())


def test_the_baseline_still_carries_the_real_user_environment():
    environment = upper_keys(user_environment.login_environment())

    # Rebuilding is only correct if what comes back is a usable environment.
    # These are the vars every process on this machine genuinely has.
    for name in ("PATH", "SYSTEMROOT", "USERPROFILE", "APPDATA", "TEMP"):
        assert environment.get(name), f"{name} missing from the rebuilt environment"


def test_identity_vars_windows_omits_from_the_block_are_restored():
    # CreateEnvironmentBlock leaves USERNAME/USERDOMAIN out of the block it
    # builds from a process token, but a real console has them.
    environment = upper_keys(user_environment.login_environment())

    for name in user_environment.IDENTITY_VARS:
        if name in os.environ:
            assert environment.get(name.upper()) == os.environ[name]


def test_the_launch_executable_is_still_resolvable_on_the_rebuilt_path():
    # The one way this approach could fail outright: rebuilding PATH from the
    # registry drops wherever `claude` lives, and hand-off stops working.
    environment = upper_keys(user_environment.login_environment())
    directories = [d for d in environment["PATH"].split(os.pathsep) if d]
    executable = launcher.DEFAULT_LAUNCH[0]

    assert any((Path(directory) / f"{executable}.exe").is_file()
               for directory in directories), (
        f"{executable} is not on the rebuilt PATH, so hand-off would fail")


CHILD_PROCESS_VARS = [
    # Set by Claude Code for the processes it spawns, so the tracker inherits
    # them whenever it was itself started from a session. Each one makes the
    # handed-off session behave unlike a terminal you opened yourself:
    ("NO_COLOR", "1"),                    # renders the whole UI monochrome
    ("CLAUDE_CODE_CHILD_SESSION", "1"),   # turns transcript saving off
    ("CLAUDECODE", "1"),
    ("CLAUDE_CODE_SESSION_ID", "abc-123"),
    ("CLAUDE_PID", "20380"),
    ("GIT_EDITOR", "true"),               # git commit silently opens nothing
    ("GIT_TERMINAL_PROMPT", "0"),         # git never asks for credentials
    ("GCM_INTERACTIVE", "never"),
    ("PYTHONIOENCODING", "utf-8:surrogateescape"),
]


def test_no_variable_claude_injects_into_child_processes_is_passed_on(monkeypatch):
    for name, value in CHILD_PROCESS_VARS:
        monkeypatch.setenv(name, value)

    environment = upper_keys(launcher.claude_environment())

    leaked = [name for name, _ in CHILD_PROCESS_VARS if name in environment]
    assert not leaked, (
        "the spawned session must be indistinguishable from one started by "
        "hand in a fresh terminal; these were inherited instead: " + ", ".join(leaked))


def test_the_session_is_not_told_to_force_transcript_persistence(monkeypatch):
    # Only needed while CLAUDE_CODE_CHILD_SESSION leaked through. With a
    # rebuilt environment there is no marker to override, and setting it
    # anyway would be one more way the session differs from a hand-started one.
    assert "CLAUDE_CODE_FORCE_SESSION_PERSISTENCE" not in upper_keys(
        launcher.claude_environment())


def test_spawn_hands_the_rebuilt_environment_to_the_process(monkeypatch):
    captured = {}
    monkeypatch.setenv("TRACKER_ONLY_VAR", "set by the tracker's own launcher")
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **kwargs: captured.update(kwargs))

    launcher.spawn_claude(Path("C:/repos/x"))

    assert "TRACKER_ONLY_VAR" not in upper_keys(captured["env"])
    assert upper_keys(captured["env"])["USERPROFILE"]
