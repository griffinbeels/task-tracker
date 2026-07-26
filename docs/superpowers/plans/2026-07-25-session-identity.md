# Session Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Claude session spawned from a task renames itself after that task and colours itself with a colour the task owns.

**Architecture:** `store.Task` gains a `color` field normalised at construction to one of Claude's eight colour names. `launcher` turns the selected tasks plus an optional name into a list of slash-command lines. `console_input` submits those lines — each typed and followed by Enter — *before* pasting the task text unsubmitted, so a total failure of both commands leaves the session exactly where it lands today. The editor gains a colour field, every task row gains a dot, and a batch-name row above the list feeds the `/rename` argument.

**Tech Stack:** Python 3.12, pywebview, pytest. Plain `<script>` files sharing one global scope — no bundler, no framework, no JS test runner.

## Global Constraints

- **Run tests with:** `& ".venv\Scripts\python.exe" -m pytest tests/ -q` from the worktree root. PowerShell, not Bash. PowerShell 5.1 has no `&&`/`||` — chain with `;`.
- **Worktree:** `C:\Users\griff\Desktop\code\task_tracker-worktrees\session-identity` on `feature/session-identity`, based on `feature/task-groups` at `2613634`. Its `.venv` exists and the suite is green at 127 tests.
- **Never run `app.py`.** It opens a window and writes to the user's real `~/.task-tracker/`.
- Every `write_text` passes `newline="\n"` (invariant 1).
- Task bodies are verbatim (invariant 2). Nothing in this plan touches `build_prompt` or `copy_prompt`.
- Frontend bridge calls go through `callApi('name', ...)` (invariant 3).
- The failure sentinel is `API_FAILED`, a Symbol — never compare against `null`, and never against truthiness (invariant 4).
- User-authored text never reaches `innerHTML`. Build elements and set `.textContent` / `.style.background` (invariant 5).
- Reach `registry.CONFIG_DIR` through the module at call time (invariant 7).
- Nothing this app opens may take focus (invariant 10).
- Choosing a chip re-renders chips and nothing else (invariant 12).
- **No CDN references.** `tests/test_conventions.py` enforces it.
- **The constants and expected values in this plan may be wrong.** They were written against the files as they read at `2613634`. If a test's expected value contradicts the real API, say so and stop — do not bend working code to fit a number in this document.

---

## File Structure

| File | Responsibility after this plan |
|---|---|
| `store.py` | adds `CLAUDE_COLORS`, `Task.color`, and the single normalisation rule |
| `launcher.py` | adds `session_name`, `session_color`, `setup_commands`; `hand_off` takes a name |
| `console_input.py` | adds `submit` and `deliver` / `deliver_when_ready`; `paste_when_ready` is replaced |
| `inbox.py` | `file_note` forwards a colour |
| `app.py` | bridge wiring: name argument, colour arguments, `suggest_session_name` |
| `ui/state.js` | the name→hex map, `colorHex`, `suggestColor` |
| `ui/tasks.js` | the row dot, the batch-name row, the name passed to `hand_off` |
| `ui/editor.js` | the swatch builder and the COLOUR field |
| `ui/index.html` | `#handoff-name` markup, COLOUR field markup |
| `ui/style.css` | `.dot`, `.swatch`, `#handoff-name` |

Tasks 1–5 are backend and each carries a real pytest cycle. Tasks 6–8 are frontend; this project has no JS test runner by standing decision, so their gate is the manual check listed in the task. Task 9 is documentation plus the hand-verification pass.

Dependencies: 1 → 2 → 4, 3 → 4, (1,4) → 5, 5 → 6,7,8 → 9. Task 3 is independent of 1 and 2 and can run alongside them.

---

### Task 1: The colour field

**Files:**
- Modify: `store.py` (the `Task` dataclass at :19-36, `render_task` at :44-58, `parse_task` at :61-85, `create_task`)
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `store.CLAUDE_COLORS: tuple[str, ...]` (eight names, in this order: `red, blue, green, yellow, purple, orange, pink, cyan`); `store.Task.color: str`, guaranteed to be one of them on every constructed instance; `store.create_task(project_path, title, body, type, bucket="now", color="")`.

**Design notes for the implementer:**

The normalisation lives in `Task.__post_init__`, not in `parse_task` and `create_task` separately. One rule in one place means a `Task` built anywhere — parsed, created, or hand-constructed in a test — always carries a legal `/color` argument, so no downstream caller has to defend against `""` or against `color: chartreuse` typed into a task file by hand.

`color` is declared **after `group` and before `path`**, with a default, for the same reason `group` was: every existing construction site keeps working untouched.

`CLAUDE_COLORS[id % 8]` is the fallback. It is deterministic (reads never write, and no migration sweep runs) and it gives eight consecutive ids eight different colours, which plain randomness cannot promise. The "pick a colour not already in use" heuristic is **frontend-only** — see Task 6. Do not implement it here.

In `render_task`'s `meta` dict, `color` goes between `type` and `bucket`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_store.py`:

```python
LEGACY_FILE = (
    "---\n"
    "id: 3\n"
    "title: A task written before colours existed\n"
    "type: BUG\n"
    "bucket: now\n"
    "status: open\n"
    "order: 0\n"
    "created: 2026-07-25\n"
    "started: null\n"
    "done: null\n"
    "---\n"
    "\n"
    "body\n"
)


def make_task(task_id=1, **overrides):
    fields = dict(
        id=task_id, title="t", type="BUG", bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body="b",
    )
    fields.update(overrides)
    return store.Task(**fields)


def test_a_colour_survives_the_frontmatter_round_trip():
    task = make_task(42, color="purple")

    assert store.parse_task(store.render_task(task)).color == "purple"


def test_a_task_file_with_no_colour_gets_one_derived_from_its_id():
    # Every task written before this feature must have a colour from the first
    # launch — a row with no dot beside rows with dots reads as a broken render.
    assert store.parse_task(LEGACY_FILE).color == store.CLAUDE_COLORS[3]


def test_a_hand_edited_colour_that_is_not_a_claude_colour_is_replaced():
    # A task file is hand-editable, so `color:` is unvalidated text on a path
    # that ends in "type this into another process's console".
    text = LEGACY_FILE.replace("bucket: now", "color: chartreuse\nbucket: now")

    assert store.parse_task(text).color == store.CLAUDE_COLORS[3]


def test_an_empty_colour_is_treated_as_no_colour():
    text = LEGACY_FILE.replace("bucket: now", "color: ''\nbucket: now")

    assert store.parse_task(text).color == store.CLAUDE_COLORS[3]


def test_eight_consecutive_ids_get_eight_different_colours():
    colours = {make_task(task_id).color for task_id in range(1, 9)}

    assert len(colours) == 8


def test_every_derived_colour_is_one_claude_accepts():
    for task_id in range(0, 40):
        assert make_task(task_id).color in store.CLAUDE_COLORS


def test_create_task_takes_an_explicit_colour(tmp_path):
    store.create_task(tmp_path, "A", "body", "BUG", color="cyan")

    assert store.list_tasks(tmp_path)[0].color == "cyan"


def test_create_task_without_a_colour_derives_a_legal_one(tmp_path):
    task = store.create_task(tmp_path, "A", "body", "BUG")

    assert task.color in store.CLAUDE_COLORS


def test_a_legacy_task_keeps_its_derived_colour_once_it_is_saved(tmp_path):
    # Reads never write, but the next save for any reason makes the derived
    # value a real field.
    path = tmp_path / "legacy.md"
    path.write_text(LEGACY_FILE, encoding="utf-8", newline="\n")
    task = store.parse_task(path.read_text(encoding="utf-8"), path)
    derived = task.color

    store.save_task(task)

    assert f"color: {derived}" in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_store.py -q`
Expected: FAIL — `AttributeError: module 'store' has no attribute 'CLAUDE_COLORS'`, and `TypeError` on the `color=` keyword.

- [ ] **Step 3: Implement**

In `store.py`:

1. Add the constant beside `BUCKETS` and `STATUSES`:

```python
# The colours Claude Code's /color command accepts, minus `default` — every
# task has a real colour, so there is never a reason to send it.
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange",
                 "pink", "cyan")
```

2. Add `color: str = ""` to `Task`, after `group` and before `path`, and give the dataclass a `__post_init__` that replaces any value not in `CLAUDE_COLORS` with `CLAUDE_COLORS[self.id % len(CLAUDE_COLORS)]`. Comment it with why it is here rather than in the two callers.

3. `render_task`: add `"color": task.color` to `meta`, between `type` and `bucket`.

4. `parse_task`: pass `color=str(meta.get("color") or "")`. `__post_init__` does the rest — do not repeat the fallback here.

5. `create_task`: add a `color: str = ""` parameter after `bucket`, and pass it to the `Task(...)` construction.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS, and the count rises from 127.

- [ ] **Step 5: Commit**

```
git add store.py tests/test_store.py
git commit -F <message file>
```
Message: `feat: give every task one of Claude's eight colours`

---

### Task 2: Naming and colouring rules

**Files:**
- Modify: `launcher.py`
- Test: `tests/test_launcher.py`

**Interfaces:**
- Consumes: `store.CLAUDE_COLORS`, `store.Task.color` from Task 1.
- Produces:
  - `launcher.SESSION_NAME_LIMIT: int` (60)
  - `launcher.session_name(tasks: list[store.Task], name: str | None = None) -> str` — `""` means "send no `/rename`"
  - `launcher.session_color(tasks: list[store.Task]) -> str | None`
  - `launcher.setup_commands(tasks, name=None) -> list[str]` — the lines to submit, in order

**Design notes for the implementer:**

`session_name` **takes the name; it never derives one from `Task.group`.** That is deliberate and load-bearing — `docs/superpowers/specs/2026-07-25-task-groups-design.md` will supply that name from `groups.auto_group` later, and this seam is what lets the two features be built in either order.

Composition order matters. Build `prefix = f"{task.type}: "` and `suffix = f" (+{n-1})"` (empty when `n == 1`), collapse the title's whitespace, then truncate **the title** to the room left inside `SESSION_NAME_LIMIT` — not the finished string. Truncating the finished string would eat the `(+2)`, which is the most informative part of it.

Collapsing whitespace with `" ".join(text.split())` is not cosmetic: a newline inside a `/rename` argument would submit the line early and leave the rest as a stray prompt. Titles come from a single-line `<input>`, but a task file is hand-editable.

`no tasks → ""`, even when a name is given. No task means no session identity; the spec's empty spin-up sends neither command.

- [ ] **Step 1: Write the failing tests**

In `tests/test_launcher.py`, extend the existing `make_task` helper to accept a colour, then append the tests:

```python
def make_task(task_id, title, type, body, color=""):
    return store.Task(
        id=task_id, title=title, type=type, bucket="now", status="open",
        order=0, created="2026-07-25", started=None, done=None, body=body,
        color=color,
    )


def test_session_name_is_the_type_then_the_title():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b")

    assert launcher.session_name([task]) == "FEATURE: Rename the spawned session"


def test_session_name_names_the_first_task_and_counts_the_others():
    tasks = [make_task(1, "Rename the spawned session", "FEATURE", "b"),
             make_task(2, "Colour it too", "FEATURE", "b"),
             make_task(3, "And a dot on the row", "BUG", "b")]

    assert launcher.session_name(tasks) == "FEATURE: Rename the spawned session (+2)"


def test_a_name_that_was_given_wins_and_carries_no_type_prefix():
    tasks = [make_task(1, "Rename the spawned session", "FEATURE", "b"),
             make_task(2, "Colour it too", "FEATURE", "b")]

    assert launcher.session_name(tasks, "Editor polish") == "Editor polish"


def test_a_whitespace_only_name_is_not_a_name():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b")

    assert launcher.session_name([task], "   ") == "FEATURE: Rename the spawned session"


def test_a_newline_in_a_title_never_reaches_the_command_line():
    # Unbracketed, a newline mid-line submits early and leaves the rest as a
    # stray prompt. Task files are hand-editable, so this is reachable.
    task = make_task(1, "Rename\nthe spawned\tsession", "FEATURE", "b")

    assert launcher.session_name([task]) == "FEATURE: Rename the spawned session"


def test_a_long_title_is_capped_but_the_count_survives():
    tasks = [make_task(1, "R" * 200, "FEATURE", "b"),
             make_task(2, "Second", "FEATURE", "b"),
             make_task(3, "Third", "FEATURE", "b")]

    name = launcher.session_name(tasks)

    assert len(name) <= launcher.SESSION_NAME_LIMIT
    assert name.startswith("FEATURE: ")
    assert name.endswith(" (+2)")


def test_a_long_given_name_is_capped_too():
    task = make_task(1, "Short", "FEATURE", "b")

    name = launcher.session_name([task], "E" * 200)

    assert len(name) <= launcher.SESSION_NAME_LIMIT


def test_nothing_selected_has_no_name_even_if_one_was_typed():
    assert launcher.session_name([]) == ""
    assert launcher.session_name([], "Editor polish") == ""


def test_a_task_with_no_title_has_no_name():
    # "FEATURE: " on its own names nothing, so no /rename is sent at all.
    assert launcher.session_name([make_task(1, "  ", "FEATURE", "b")]) == ""


def test_session_color_is_the_first_selected_task_s():
    tasks = [make_task(1, "First", "FEATURE", "b", color="purple"),
             make_task(2, "Second", "FEATURE", "b", color="red")]

    assert launcher.session_color(tasks) == "purple"


def test_nothing_selected_has_no_colour():
    assert launcher.session_color([]) is None


def test_setup_commands_renames_then_colours():
    task = make_task(1, "Rename the spawned session", "FEATURE", "b",
                     color="purple")

    assert launcher.setup_commands([task]) == [
        "/rename FEATURE: Rename the spawned session",
        "/color purple",
    ]


def test_setup_commands_is_empty_with_nothing_selected():
    assert launcher.setup_commands([]) == []


def test_setup_commands_still_colours_a_task_that_cannot_be_named():
    task = make_task(1, "  ", "FEATURE", "b", color="cyan")

    assert launcher.setup_commands([task]) == ["/color cyan"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_launcher.py -q`
Expected: FAIL — `AttributeError: module 'launcher' has no attribute 'session_name'`.

- [ ] **Step 3: Implement**

In `launcher.py`, below `copy_prompt`:

- `SESSION_NAME_LIMIT = 60`, with a comment giving both reasons: a tab label longer than that is unreadable, and a short line is what keeps Claude Code inserting the paste literally rather than collapsing it into a `[Pasted text]` placeholder.
- `session_name(tasks, name=None)` per the composition order in the design notes above. When the room left for the title is less than 1 (an absurdly long type name), fall back to capping the whole composed string.
- Truncation appends a single `…` so the result lands exactly on the limit.
- `session_color(tasks)` returns `tasks[0].color` or `None`.
- `setup_commands(tasks, name=None)` builds `/rename <name>` then `/color <colour>`, omitting either line when its value is empty.

Docstrings carry the *why*, matching this module's existing style: why the whitespace collapse exists, why the count is preserved through truncation, and why the name is an argument rather than something read off the tasks.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: name a session after the task it carries`

---

### Task 3: Submitting a command line

**Files:**
- Modify: `console_input.py`
- Test: `tests/test_console_input.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `console_input.COMMAND_TIMEOUT: float` (5.0)
  - `console_input.SETTLE_SECONDS: float` (0.5)
  - `console_input.submit(pid: int, line: str, timeout: float = COMMAND_TIMEOUT) -> bool`
  - `console_input.deliver(pid: int, commands: list[str], prompt: str) -> None`
  - `console_input.deliver_when_ready(pid, commands, prompt) -> threading.Thread`
- Removes: `console_input.paste_when_ready`. It has exactly one caller (`launcher.hand_off`), rewired in Task 4.

**Design notes for the implementer:**

`paste` is unchanged and stays the only thing that writes *unsubmitted* text.

`submit` waits for `READY_MARKERS` exactly as `paste` does, writes the line wrapped in the existing bracketed-paste markers, then writes a carriage return as a **separate** `_write_input` call. Bracketed rather than raw keystrokes because a leading `/` opens Claude Code's command-suggestion popup, which is a live UI reading keystrokes; a paste arrives as one event carrying a complete line, so the popup never sees a partial token and cannot claim the Enter that follows.

**The `SETTLE_SECONDS` sleep belongs inside `submit`, after the write** — not in `deliver`. That keeps `deliver` pure orchestration, which is what makes it testable at all: the tests below monkeypatch `submit` and would otherwise sit through a real sleep per command.

Timeouts differ on purpose. The first wait is for a process to boot and keeps `READY_TIMEOUT` (45s); every later wait is for a prompt box that is already up and gets `COMMAND_TIMEOUT`. `deliver` therefore submits the first command with `READY_TIMEOUT` and the rest with the default.

`deliver`'s contract, in one sentence: **a command that fails abandons the remaining commands but never the prompt.** The prompt is the thing that matters; the commands are decoration on it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_console_input.py`. These monkeypatch `submit` and `paste`, so no console is opened — unlike the existing test in that file, which really does open one.

```python
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
```

Note on the last test: it monkeypatches `SETTLE_SECONDS` indirectly by leaving it at 0.5s, which costs half a second once. If that proves annoying, set `monkeypatch.setattr(console_input, "SETTLE_SECONDS", 0)` at the top of it — read the real constant name from the implementation rather than assuming.

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_console_input.py -q`
Expected: FAIL — `AttributeError: module 'console_input' has no attribute 'deliver'`.

- [ ] **Step 3: Implement**

In `console_input.py`:

- `COMMAND_TIMEOUT = 5.0` and `SETTLE_SECONDS = 0.5`, each with a one-line reason beside it.
- `submit(pid, line, timeout=COMMAND_TIMEOUT)` — the same poll loop shape `paste` uses: attach, check `is_ready(_screen_text())`, and on success write the bracketed line, then write `"\r"`, then sleep `SETTLE_SECONDS`, then return whether both writes landed. On timeout, return `False`.
- `deliver(pid, commands, prompt)` — first command at `READY_TIMEOUT`, the rest at `COMMAND_TIMEOUT`, stopping at the first failure; then `paste(pid, prompt)` if `prompt`. **Pass `timeout` explicitly on both branches** rather than letting the later ones fall through to the default — `test_the_first_command_waits_for_the_session_to_boot` observes the argument, and a defaulted call arrives as `None`.
- `deliver_when_ready(pid, commands, prompt)` — the daemon-thread wrapper, replacing `paste_when_ready`.
- Delete `paste_when_ready`.
- Extend the module docstring: the three things it has to get right become four, the new one being that a slash command must be *submitted* while the task text must not be, and that the commands go first so a failure costs decoration rather than the hand-off.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: FAIL in `tests/test_launcher.py` only — its `spawned` fixture still patches `paste_when_ready`, which no longer exists. That is Task 4's job. Every `test_console_input.py` test passes.

- [ ] **Step 5: Commit**

Message: `feat: submit a command line, then leave the prompt unsent`

---

### Task 4: Wire the hand-off

**Files:**
- Modify: `launcher.py` (`hand_off`)
- Test: `tests/test_launcher.py` (the `spawned` fixture and two existing assertions change)

**Interfaces:**
- Consumes: `launcher.setup_commands` (Task 2), `console_input.deliver_when_ready` (Task 3).
- Produces: `launcher.hand_off(project_path, tasks, launch=None, name=None) -> str` — return value unchanged: the prompt text.

**Design notes for the implementer:**

`hand_off` currently guards the typing on `if prompt:`. It becomes `if prompt or commands:` — defensive, since in practice a non-empty task list always yields both, but the guard should say what it means.

The clipboard copy stays guarded on `prompt` alone. A session that gets only `/color` has nothing to put on the clipboard, and clobbering the user's clipboard for that would be a side effect with no purpose.

Nothing about the order of the status write changes: tasks are marked in-progress after the spawn, exactly as now, so a `Popen` that raises leaves them untouched (there is an existing test for this).

- [ ] **Step 1: Update the fixture and write the failing tests**

Replace the `spawned` fixture in `tests/test_launcher.py`:

```python
@pytest.fixture
def spawned(monkeypatch):
    """Swallow the process spawn and record what would have been sent to it."""
    typed = {}
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: FakeSession())
    monkeypatch.setattr(
        launcher.console_input, "deliver_when_ready",
        lambda pid, commands, text: typed.update(
            pid=pid, commands=commands, text=text))
    return typed
```

Update the two existing assertions that spell out the fixture's contents —
`test_hand_off_types_the_prompt_into_the_session_it_opened` becomes:

```python
    assert spawned["pid"] == FakeSession.pid
    assert spawned["text"] == prompt
```

`test_hand_off_with_nothing_selected_opens_a_bare_session` keeps `assert spawned == {}` unchanged.

Then append:

```python
def test_hand_off_renames_and_colours_the_session_it_opened(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG",
                             color="purple")

    launcher.hand_off(tmp_path, [task])

    assert spawned["commands"] == ["/rename BUG: Replay audio desync",
                                   "/color purple"]


def test_hand_off_uses_the_name_it_was_given(tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    first = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")
    second = store.create_task(tmp_path, "Chips rewrite the row", "x", "BUG")

    launcher.hand_off(tmp_path, [first, second], name="Editor polish")

    assert spawned["commands"][0] == "/rename Editor polish"


def test_the_commands_are_sent_before_the_prompt_is_typed(
        tmp_path, monkeypatch, spawned):
    # Ordering is the whole safety argument: if both commands fail, the session
    # still ends up where it lands today — task text sitting editable.
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)
    task = store.create_task(tmp_path, "Replay audio desync", "drifts", "BUG")

    prompt = launcher.hand_off(tmp_path, [task])

    assert spawned["commands"][0].startswith("/rename ")
    assert spawned["text"] == prompt


def test_hand_off_with_nothing_selected_sends_no_commands(
        tmp_path, monkeypatch, spawned):
    monkeypatch.setattr(launcher.pyperclip, "copy", lambda text: None)

    launcher.hand_off(tmp_path, [])

    assert spawned == {}
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_launcher.py -q`
Expected: FAIL — `hand_off()` takes no `name` argument, and `spawned` has no `commands` key.

- [ ] **Step 3: Implement**

In `launcher.hand_off`: add the `name: str | None = None` parameter, build `commands = setup_commands(tasks, name)`, copy the prompt when there is one, and call `console_input.deliver_when_ready(session.pid, commands, prompt)` when `prompt or commands`.

Extend the docstring with the ordering argument — commands first, prompt last and unsubmitted, so a failed command costs decoration and never the hand-off.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: rename and colour the session a hand-off opens`

---

### Task 5: The bridge

**Files:**
- Modify: `app.py` (`update_task` at :101-116, `create_task` at :118-126, `file_note` at :87-92, `hand_off` at :176-184)
- Modify: `inbox.py` (`file_note`)
- Test: `tests/test_app.py`, `tests/test_inbox.py`

**Interfaces:**
- Consumes: `store.CLAUDE_COLORS`, `launcher.session_name`, `launcher.hand_off(..., name=...)`.
- Produces:
  - `Api.hand_off(project_name, task_ids, name="")`
  - `Api.create_task(project_name, title, body, type, bucket, color="")`
  - `Api.file_note(note_id, project_name, title, type, bucket, body=None, color="")`
  - `Api.update_task(...)` accepting `color` in `fields`
  - `Api.suggest_session_name(project_name, task_ids) -> str`
  - `Api._selected_tasks(project_name, task_ids) -> tuple[registry.Project, list[store.Task]]`
  - `inbox.file_note(note_id, project_path, title, type, bucket, body=None, color="")`

**Design notes for the implementer:**

**`suggest_session_name` exists so the naming rule has exactly one implementation.** The batch row's placeholder must show precisely what the backend will produce; computing it in JS would be a second copy of the rule, free to drift. The frontend asks the backend instead.

`_selected_tasks` is `hand_off`'s existing inline id→task lookup, extracted so `suggest_session_name` shares it. **Name it exactly `_selected_tasks`.** `docs/superpowers/specs/2026-07-25-selection-bar-design.md` plans an `Api._tasks` with the same shape plus deduplication; using a different name keeps the two from colliding in a merge, and whoever lands second collapses them into one.

`file_note` gains a colour because triage shows the COLOUR field (Task 7), and a field the user can set that is then discarded is the same class of bug that made `file_note` silently drop edited prose.

`update_task` validates colour membership the way it already validates bucket and status — a raise, not a silent correction. `store.Task.__post_init__` would silently repair a bad value, which is right for a hand-edited file and wrong for the bridge, where a bad value means the caller is broken.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_app.py`:

```python
def test_update_task_rejects_a_colour_claude_does_not_accept(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG", color="cyan")

    with pytest.raises(ValueError):
        app.Api().update_task("repo", task.id, {"color": "chartreuse"})

    assert store.list_tasks(repo)[0].color == "cyan"


def test_update_task_applies_a_valid_colour(tmp_path):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG", color="cyan")

    app.Api().update_task("repo", task.id, {"color": "purple"})

    assert store.list_tasks(repo)[0].color == "purple"


def test_create_task_takes_a_colour(tmp_path):
    make_repo(tmp_path)

    payload = app.Api().create_task("repo", "A", "body", "BUG", "now", "pink")

    assert payload["color"] == "pink"


def test_create_task_rejects_a_colour_claude_does_not_accept(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().create_task("repo", "A", "body", "BUG", "now", "chartreuse")


def test_a_task_crosses_the_bridge_carrying_its_colour(tmp_path):
    repo = make_repo(tmp_path)
    store.create_task(repo, "A", "body", "BUG", color="orange")

    payload = app.Api().get_state()["tasks"][0]

    assert payload["color"] == "orange"


def test_hand_off_passes_the_name_it_was_given(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "A", "body", "BUG")
    second = store.create_task(repo, "B", "body", "BUG")
    captured = {}
    monkeypatch.setattr(
        app.launcher, "hand_off",
        lambda path, tasks, launch=None, name=None: captured.update(name=name) or "")

    app.Api().hand_off("repo", [first.id, second.id], "Editor polish")

    assert captured["name"] == "Editor polish"


def test_hand_off_without_a_name_passes_nothing(tmp_path, monkeypatch):
    repo = make_repo(tmp_path)
    task = store.create_task(repo, "A", "body", "BUG")
    captured = {}
    monkeypatch.setattr(
        app.launcher, "hand_off",
        lambda path, tasks, launch=None, name=None: captured.update(name=name) or "")

    app.Api().hand_off("repo", [task.id])

    assert not captured["name"]


def test_suggest_session_name_is_what_hand_off_would_use(tmp_path):
    repo = make_repo(tmp_path)
    first = store.create_task(repo, "Rename the spawned session", "b", "FEATURE")
    second = store.create_task(repo, "Colour it too", "b", "FEATURE")

    suggested = app.Api().suggest_session_name("repo", [first.id, second.id])

    assert suggested == "FEATURE: Rename the spawned session (+1)"


def test_suggest_session_name_raises_on_an_unknown_id(tmp_path):
    make_repo(tmp_path)

    with pytest.raises(ValueError):
        app.Api().suggest_session_name("repo", [99])
```

Append to `tests/test_inbox.py` (read that file first for its fixture pattern — it uses the same `monkeypatch.setattr(registry, "CONFIG_DIR", ...)` shape):

```python
def test_filing_a_note_carries_the_colour_that_was_picked(tmp_path):
    note = inbox.save_note("some prose")
    project = tmp_path / "repo"
    project.mkdir()

    task = inbox.file_note(note.id, project, "A title", "BUG", "now",
                           color="pink")

    assert task.color == "pink"
```

- [ ] **Step 2: Run them and watch them fail**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_app.py tests/test_inbox.py -q`
Expected: FAIL — `hand_off()` takes 3 positional arguments, `Api` has no `suggest_session_name`, `create_task()` takes no colour.

- [ ] **Step 3: Implement**

In `inbox.py`: add `color: str = ""` to `file_note`'s signature, after `body`, and pass it through to `store.create_task`.

In `app.py`:

1. Add `_selected_tasks(self, project_name, task_ids)` — the body currently inline in `hand_off` (int-coerce the ids, build `by_id`, raise `ValueError` naming any missing id, return the project and the tasks in the order the ids arrived). Refactor `hand_off` onto it.
2. `hand_off(self, project_name, task_ids, name="")` — validate `name` is a string, forward it to `launcher.hand_off` as a keyword.
3. `suggest_session_name(self, project_name, task_ids)` — `_selected_tasks`, then `launcher.session_name(tasks)`.
4. `create_task` — add `color=""` after `bucket`; raise `ValueError` when it is neither `""` nor in `store.CLAUDE_COLORS`; pass it to `store.create_task`.
5. `file_note` — add `color=""`, same validation, forward to `inbox.file_note`.
6. `update_task` — add `"color"` to the string-type check tuple, add a membership check beside the bucket and status ones, and add `"color"` to the `setattr` key tuple. **Both halves.** Without the second, the editor's colour change is silently dropped.

- [ ] **Step 4: Run the whole suite**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `feat: carry a colour and a session name across the bridge`

---

### Task 6: The colour on the row

**Files:**
- Modify: `ui/state.js`, `ui/tasks.js` (`taskRow` at :7-49), `ui/style.css`

**Interfaces:**
- Consumes: `task.color` from `get_state` (Task 5).
- Produces: `CLAUDE_COLORS` (a name→hex object), `colorHex(name) -> string`, `suggestColor(project) -> string` — all globals in `state.js`, callable from `tasks.js` and `editor.js` at call time, which is this project's cross-file pattern.

**Design notes for the implementer:**

The hexes sit on the same Radix scale as the existing default type colours (`#e5484d`, `#30a46c`, `#0090ff`), so a dot and a type tag look like they come from one system:

```js
const CLAUDE_COLORS = {
  red: '#e5484d', blue: '#0090ff', green: '#30a46c', yellow: '#f5d90a',
  purple: '#8e4ec6', orange: '#f76b15', pink: '#d6409f', cyan: '#00a2c7',
};
```

`colorHex` falls back to `#8e8e8e` for an unknown name, mirroring `typeColor`'s existing shape. It should never fire — `Task.__post_init__` guarantees a legal name — but the two functions doing the same thing differently would be the surprise.

`suggestColor(project)` is the "avoid colours already in use" heuristic, and it lives **only here**. Count how many of that project's non-done tasks use each of the eight names, find the lowest count, and pick at random among the names tied at it. With eight or fewer open tasks that yields eight distinct colours; beyond that it spreads evenly.

The dot goes **before** the type tag inside `taskRow`'s existing `innerHTML` template. The template is static markup with no user text in it, so adding an empty `<span class="dot"></span>` does not touch invariant 5 — but the colour itself is set afterwards via `.style.background`, exactly as the type tag's is, because it comes from a hand-editable file.

`.dot` needs `flex: none`, or the flex row will squash it into an oval. That is the same class of bug as the checkbox that got stretched to 28px and knocked its label off the baseline — `style.css` documents that one at :11.

- [ ] **Step 1: Implement**

1. `ui/state.js` — add `CLAUDE_COLORS`, `colorHex`, `suggestColor` beside `typeColor`.
2. `ui/tasks.js` — add the span to the template; set its background from `colorHex(task.color)` in the block that already sets the type tag's, and extend that block's comment to cover it.
3. `ui/style.css` — `.dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }` beside the existing `.type` rule, with a comment on why `flex: none` is there.

- [ ] **Step 2: Check the conventions test still passes**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_conventions.py -q`
Expected: PASS. It globs `ui/*.js` for the newline and `API_FAILED` conventions.

- [ ] **Step 3: Check by hand**

Launch the app (`run.bat`) and confirm: every task row shows a coloured dot before its type tag; the dot is round, not oval; no row is missing one, including tasks written before this feature.

- [ ] **Step 4: Commit**

Message: `feat: show each task's session colour on its row`

---

### Task 7: The COLOUR field in the editor

**Files:**
- Modify: `ui/index.html` (`#editor-meta` at :32-46), `ui/editor.js` (`chip` at :36-51, `renderChips` at :148-158, `openEditor` at :170-251, the save handler at :259-324), `ui/style.css`

**Interfaces:**
- Consumes: `CLAUDE_COLORS`, `colorHex`, `suggestColor` (Task 6); `Api.create_task`/`file_note`/`update_task` colour arguments (Task 5).
- Produces: `editorContext.color`.

**Design notes for the implementer:**

Markup, matching the three `.field` rows already there so all four share one left edge:

```html
<div class="field">
  <span class="field-label">Colour</span>
  <div id="editor-colors" class="chips"></div>
</div>
```

A swatch is a filled circle, not a text pill, so it needs its own builder beside `chip()` rather than a fourth argument to it. Give each swatch a `title` of its colour name so the choice is nameable, and show selection as a fill-plus-ring — `.chip.on`'s reasoning applies: a difference you see, not one you look for.

**`renderChips()` renders it and nothing else touches it** (invariant 12). Every swatch's `onclick` sets `editorContext.color` and calls `renderChips()` — never a broader render. The bug that rule replaced discarded a typed title when a type chip was clicked.

In `openEditor`, seed it:

```js
color: context.color || suggestColor(context.project || currentProject),
```

Seeded once per open, like the rest of `editorContext`. Do **not** re-suggest when the project chip changes — a colour the user picked must survive picking a different project, which is the same "one keystroke marks it yours" rule as the title (invariant 11).

`taskRow`'s `openEditor({...})` call in `tasks.js` must pass `color: task.color`, or every edit re-suggests and silently recolours the task on save.

Three save paths, all three needing the colour:

- edit → add `color: editorContext.color` to the `fields` object
- triage → `file_note(note.id, project, title, type, bucket, body, editorContext.color)`
- capture → `create_task(project, title, body, type, bucket, editorContext.color)`

- [ ] **Step 1: Implement**

Markup, `swatch()`, the `renderChips` block, the `openEditor` seed, the `tasks.js` pass-through, the three save call sites, and the `.swatch` CSS.

- [ ] **Step 2: Check the conventions test still passes**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_conventions.py -q`
Expected: PASS.

- [ ] **Step 3: Check by hand — including the two standing editor checks**

`CLAUDE.md` requires both of these every time `ui/editor.js` is touched, because both are silent when broken:

1. Type a title, then click a *different type chip* — the title must not change.
2. Edit **only** a task's bucket in a tracked project, then `git status` — the `.md` shows a frontmatter change and **no body diff**.

Plus this feature's own:

3. Open an existing task — the swatch matching its dot is the selected one.
4. Click a different swatch, save, reopen — the new colour persisted, and the row's dot changed to match.
5. Capture a new task — a swatch is preselected, and it is not the same one every time.
6. Pick a colour in triage, file the note — the resulting task has that colour.

- [ ] **Step 4: Commit**

Message: `feat: pick a task's session colour in the editor`

---

### Task 8: The batch-name row

**Files:**
- Modify: `ui/index.html` (between `#toolbar` at :21 and `#wip-warning` at :22), `ui/tasks.js` (the `spin-up` handler at :119-131), `ui/style.css`

**Interfaces:**
- Consumes: `Api.suggest_session_name` (Task 5), `selectedIds()` (already in `tasks.js`).
- Produces: `renderHandoffName()` — a global in `tasks.js`.

**Design notes for the implementer:**

Markup goes in the slot the two warning rows already use for "appears when it has something to say":

```html
<div id="handoff-name" hidden>
  <span class="field-label">Name</span>
  <input id="handoff-name-input">
</div>
```

**The suggestion is a placeholder, never a value.** That is what removes the whole clobber question: typing replaces nothing, clearing the box restores the default, and there is no "has the user touched this" flag to get wrong. Fetch it from `suggest_session_name` rather than composing it in JS — one implementation of the naming rule, no drift.

Showing and hiding: `renderHandoffName()` reads `selectedIds()`, hides the row below two selections, and otherwise sets the placeholder. Call it from `render()` and from **one delegated `change` listener on `#task-list`**, guarded on `.select` so the row's bucket picker does not trigger it. Delegation is what survives `replaceChildren`; a per-row listener would need re-attaching on every render. The selection-bar design specifies exactly this listener for its own use — when that feature lands, these two collapse into one handler, not two.

The `spin-up` handler passes the trimmed value, but **only when the row is showing**. Below two selections the row is hidden and its value may be stale from an earlier selection, which would silently name a single-task session after a batch you abandoned.

Clear the input's value after a successful hand-off, or the next batch inherits the last one's name.

`#handoff-name[hidden] { display: none }` is required: the rule that lays the row out sets `display`, which a bare `hidden` attribute loses to on equal specificity. `style.css` documents this same trap three times already — for `.overlay`, `.chips` and `.field`.

**This row is temporary in its current shape.** `docs/superpowers/specs/2026-07-25-selection-bar-design.md` puts a bar in the same strip; when it lands, this input moves into `#selection-bar` as a second line and `#handoff-name` goes away. Leave a comment saying so.

- [ ] **Step 1: Implement**

Markup, `renderHandoffName()`, the delegated listener, the `render()` call, the `spin-up` changes, the CSS.

- [ ] **Step 2: Check the conventions test still passes**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/test_conventions.py -q`
Expected: PASS.

- [ ] **Step 3: Check by hand**

1. Tick one task — no name row.
2. Tick a second — the row appears, and its placeholder reads exactly `TYPE: <first title> (+1)`.
3. Tick a third — the placeholder's count becomes `(+2)`.
4. Untick back to one — the row disappears.
5. Change a row's bucket dropdown — the row does not appear or flicker.
6. The list moves down when the row appears, and the window gains **no vertical scrollbar**.
7. Type a name, spin up, then tick two tasks again — the box is empty.
8. Search for something — the row never appears (search disables `.select`).

- [ ] **Step 4: Commit**

Message: `feat: name a batch before handing it to a session`

---

### Task 9: Documentation and the hand-verification pass

**Files:**
- Modify: `CLAUDE.md`

**Design notes for the implementer:**

This task is where the one genuinely unverifiable claim in the design gets tested against the real thing.

- [ ] **Step 1: Verify the hand-off end to end**

Open the tracker, tick one task in a real project, and click `Spin up Claude`. Watch the spawned console and confirm, in order:

1. The session's name changes to `TYPE: <title>`.
2. Its colour changes to the task's colour.
3. The task's text is sitting in the prompt box, **unsubmitted**.
4. The console did **not** take focus at any point (invariant 10).

- [ ] **Step 2: If the slash commands did not register, apply the documented fallback**

The open question is whether a **bracketed-paste** `/rename foo` registers as a slash command or only typed input does. Detection happens on the input buffer's contents at submit, so it should — but this is a claim about someone else's UI.

Symptoms and fixes, in order of likelihood:

- *The line appears in the transcript as a user message rather than running:* the paste was not treated as command input. Write the line **unbracketed** through `key_records` and lengthen `SETTLE_SECONDS` before the Enter.
- *The line appears in the prompt box but never submits:* the `\r` is not being read as Enter. Set `wVirtualKeyCode = 0x0D` on that record — `key_records` currently leaves the virtual key at zero on the documented grounds that Claude reads the console as a stream, which holds for characters and may not for Enter.
- *The first command runs and the second is swallowed:* raise `SETTLE_SECONDS`.

Whatever the answer turns out to be, **write it into `CLAUDE.md` as a numbered invariant.** It is exactly the kind of thing that is silent when broken, which is this project's bar for that list.

- [ ] **Step 3: Update `CLAUDE.md`**

- The test count in the Run-and-test block.
- `store.py`'s row: it now owns the colour vocabulary as well.
- `launcher.py`'s row: session naming and the command list.
- `console_input.py`'s row: submitted commands as well as unsubmitted text.
- Data-on-disk: `color` in the frontmatter sketch.
- A new invariant for the ordering rule — commands are submitted before the prompt is typed, so a failed command costs decoration and never the hand-off — plus whatever step 2 established.
- The colour normalisation rule, stated once: `Task.__post_init__` guarantees a legal colour, so no caller defends against an empty or hand-edited one.
- Known gaps: the batch-name row is absorbed into the selection bar when that lands.

- [ ] **Step 4: Run the whole suite one more time**

Run: `& ".venv\Scripts\python.exe" -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 5: Commit**

Message: `docs: record what a session identity costs and guarantees`

---

## Notes for whoever merges this

Three features are in flight against these files. This branch is based on `feature/task-groups` at `2613634`.

- `Api._selected_tasks` and the selection-bar design's planned `Api._tasks` are the same helper under two names. Whoever lands second collapses them; `_tasks` (with dedup) is the better of the two.
- The delegated `change` listener on `#task-list` is specified by both this plan and the selection-bar design. One listener, two callees.
- `#handoff-name` is absorbed into `#selection-bar` as a second line when the selection bar lands.
- `store.Task` carries `group` (already landed) and `color` (this branch). Independent fields, independent parse rules: `group` is `None` when absent because an ungrouped task is a real state; `color` never is, because an uncoloured task is not.
