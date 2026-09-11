---
paths:
  - "tests/*.py"
---

# Tests — what is covered, and what is deliberately not

Including the rule that no test here may put anything on screen.

- **Tests:** `store.py`, `registry.py`, `inbox.py`, `migrate.py`, `launcher.py`,
  `groups.py` and `Api` methods are all directly testable. Use `tmp_path` and the
  `monkeypatch.setattr(registry, "CONFIG_DIR", ...)` fixture pattern from
  `tests/test_registry.py`. Mock at the boundary — `claude_console.open_session`
  and `launcher.pyperclip.copy` — never spawn a real process. `open_session` is
  the seam for anything touching a hand-off; `test_launcher.py` stubbed
  `subprocess.Popen` before the extraction, which meant every task-shaped
  assertion also carried Win32 scaffolding it had no opinion about.
  **No test here opens a console at all any more**, and
  `test_nothing_in_this_repo_may_open_a_console_window` has an empty allowlist
  saying so. The one test that genuinely does — typing into another process's
  console is OS behaviour, and a mock of it would only assert that the mock was
  called — moved to `claude-console` along with its windowless probe and the
  guard that keeps it windowless. The suite runs while someone else is at the
  keyboard: **no test may put anything on screen.**
- **Native windows remain a human check.** Startup ordering and error handling
  can be tested with a fake webview and mocked `desktop.report_fatal`; no test
  may let a real `MessageBoxW`, AppleScript dialog or webview reach the screen.
  Headless page checks do not prove native geometry, clipboard or focus.
- **Both platforms:** run the shared suite on Windows and macOS; use native-only
  skips solely for native structures and retain shared contract coverage.
  See `docs/platform-support.md` for the boundaries and acceptance checklist.
