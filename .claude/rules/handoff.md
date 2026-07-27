---
paths:
  - "launcher.py"
  - "ui/tasks.js"
  - "ui/selection.js"
  - "tests/test_launcher.py"
---

# The hand-off — opening a Claude session on tasks

Invariants 2, 8, 9, 10, 19, 22, 24, 25 and 31, and the shared module.

## The shared module: `claude_console`

**Opening a Claude session and typing into it is not this app's code any more.**
It lives in its own repo — one copy, checked out beside this one and shared with
every project on this machine (the literal path is in the untracked
`CLAUDE.local.md`) — and it owns everything that would be true of a
session opened on a git diff or a form submission rather than on a task:
spawning the session into whatever this machine's default terminal is, resolving
the pid to type into, writing to the console's input buffer, the rebuilt
environment, and `safe_line`/`cap`.

```python
session = claude_console.open_session(project_path, launch)
session.deliver(prompt=prompt, commands=commands)
```

Three things about it that matter here:

- **It is installed editable, so there is no version and nothing to update.**
  `site-packages` holds a `.pth` and a path finder pointing at that source
  tree, not a copy — an edit there (including a brand-new file) is live in the
  next process here. The other half of the same coin: **a breaking change there
  breaks this immediately.** That direction is guarded from the other side —
  this repo is listed in `claude-console/consumers.json`, and a PostToolUse
  hook there runs *this* suite on every edit to the shared package, blocking
  if it goes red. Nothing is needed here to participate; if this checkout ever
  moves, update that file's `path`.
- **A session window is allowed to take focus, and that changed on
  2026-07-26.** It used to be forbidden — a pinned `conhost.exe`, plus a
  watchdog that handed the keyboard back. The rule was over-broad: a window the
  user asked for may come to the front, and fighting that reads as the app not
  responding. Pressing ⏎ on a hand-off is a human gesture and
  earns the focus it takes. What must still open nothing is a **test**, and
  that half is enforced by a conventions guard rather than remembered.
- **The convention guard travelled with the code.** `claude-console` has its
  own `tests/test_conventions.py`. This repo's copy now has an *empty*
  allowlist, which is the assertion: nothing here opens a console at all.

If you find yourself adding something to `launcher.py` that does not mention a
task, a group or a bucket, it belongs over there instead.

2. **A hand-off is a pointer, and a task body is verbatim on disk.** Two
   halves of one rule. `build_prompt` emits the task file's **absolute path**,
   one per line, and nothing else — no prose, no `TYPE:` prefix, no
   instructions. And nothing ever rewrites a body: never strip, trim,
   normalise, re-wrap or append, at either end.

   **Why a path.** A session opened on a project can read the task, so the
   prose does not need to travel — and the file carries what a prompt box
   never could: the type, the group, the dates, any pasted screenshot's
   absolute path, and the prose still formatted as the markdown it was written
   as, lists and numbering included. A session needs no prompt at all for this:
   it reads markdown perfectly well (2026-07-27).

   **What it ended.** A prompt box takes plain text, so everything the editor
   stores as *notation* had to be undone on the way out, and each undoing was
   its own shipped bug found by the user rather than by a test — the escapes,
   the `<br>`, the non-breaking spaces below. All three are still in the file
   and none of them are a problem there, because they are markdown and are
   read as markdown. The lesson generalises past this app: **when a consumer
   can read the source, converting the source for it is the bug.**

   **Absolute, though the session's own directory is the project.** The same
   string goes on the clipboard, where the destination is unknown, and a
   relative path is not *wrong* somewhere else — it silently means a different
   file. Invariant 14's reasoning, one directory up.

   A task with no `path` raises, as in `store.save_task`. Nothing in the app
   can reach it: every task the bridge selects was read off disk.

   **What the editor stores that nobody typed.** Still true of every body, and
   still what `asShown` in `ui/state.js` exists for — search matches on it and
   the `## Outcome` split reads it, so both need the text as drawn. Measured
   against the vendored build, not reasoned about:

   - **Escapes.** Toast UI's serializer escapes an entire line whenever that
     line *looks like* a block construct: `1. resize the text, then (this)` is
     stored as `1\. resize the text\, then \(this\)`, because `Je.list`
     matches the line and the escape set is then `[>(){}[\]+-.!#|]`, whose
     unescaped `+-.` is a *range* covering the comma. `*`, `_`, `~` and
     `` ` `` are escaped unconditionally, so a pasted `## heading` gains
     backslashes too. Undoing one means `\` before ASCII punctuation
     (CommonMark's escapable set); `\` before anything else is a backslash
     somebody typed.
   - **The empty-paragraph filler.** Markdown cannot say "blank line here", so
     the second of two consecutive empty paragraphs — which is what two presses
     of Enter make — serializes as a literal `<br>` on a line of its own.
     `<ol>…</ol><p></p><p></p><p>a</p>` becomes `1. one\n\n\n<br>\na`; a
     *single* empty paragraph needs no tag. A `<br>` the user typed is stored
     **escaped** (`\<br>` — the serializer escapes HTML tags), which is the
     whole difference between markup that is spacing and markup that is
     content.
   - **Non-breaking spaces.** A paste carrying `text/html` off a web page
     leaves U+00A0 behind, indistinguishable from a space until something reads
     the bytes. Tabs are *not* on this list: ProseMirror normalises a tab to a
     space in the document itself, so one cannot reach the file — checked
     rather than assumed, because the report named it.

   **Never repair a body by rewriting the file.** That would have to decide
   whether a `1. ` line is now a list and whether a literal `*` is now
   emphasis — silently changing bodies nobody edited, which is the half of this
   invariant that has not moved. The editor's round-trip (invariant 13) depends
   on the escapes being there.

   **`claude_console` is not the place for any of this, and that was asked.**
   It takes an assembled prompt from any consumer — a git diff, a form
   submission — and cannot tell a markdown escape from a backslash that is
   content. It is also innocent: `deliver` hands `prompt` to `paste` unchanged,
   and `safe_line` touches only the command lines.

8. **A spawned session's environment is rebuilt, never filtered.** `Popen`
   inherits the tracker's environment, and the tracker is normally started
   *from* a Claude session — which sets a batch of variables for the processes
   it spawns. Inheriting them made the handed-off session differ from one
   opened by hand in ways that were all silent: `NO_COLOR=1` rendered it
   monochrome, `GIT_EDITOR=true` and `GIT_TERMINAL_PROMPT=0` left its git
   unable to open an editor or ask for credentials, and
   `CLAUDE_CODE_CHILD_SESSION` turned transcript saving off.
   `claude_console.login_environment()` calls Win32 `CreateEnvironmentBlock`
   instead, which is how Windows builds the environment for a newly launched
   process. **Do not add a var to a strip-list** — the list belongs to
   upstream and grows; rebuilding makes tomorrow's addition absent by
   construction. Nothing is added back on top either: with no
   `CLAUDE_CODE_CHILD_SESSION` to override, `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`
   is redundant, and setting it would be one more difference from a
   hand-started session.

9. **Typed text is bracketed, and waits for the prompt box.**
   `claude_console.console_input`
   writes into the spawned session's console input buffer, which accepts input
   long before Claude is ready to read it. Unbracketed, the newline between two
   tasks reads as Enter and sends the first one alone; unwaited, the text is
   answered into whatever dialog is on screen — a folder Claude has not been
   trusted in opens on a question whose default is Enter. Both failures are
   silent, and both are why `paste()` polls for `READY_MARKERS` first. It is
   allowed to give up: the same text is on the clipboard.

10. **Focus is opt-in, and a hand-off is a human gesture that earns it.**
    Rewritten 2026-07-26, and the correction came from the person the old rule
    was written for. The line is **who asked for the window**, not what kind of
    window it is: a session the user deliberately spun up may take the keyboard
    for a moment, and fighting that reads as the app not responding. What may
    never appear is a window Claude opened for its own purposes — a test, a
    probe, a verification run.
    So a session window opening in front is correct, and the thing that must
    open nothing at all is a **test**.

    **`CREATE_NO_WINDOW` is what anything other than a hand-off uses.** Windows
    11 delegates every *new* console to whatever is set as the default terminal
    application; when that is Windows Terminal — the default on this machine —
    the request is brokered (`svchost` → `OpenConsole.exe`) and **WT creates
    the window itself**, so the spawner's `STARTUPINFO` never reaches it and a
    full, activated Terminal window opens regardless of `wShowWindow`. Measured
    2026-07-25 by spawning the same child three ways from a console-less
    parent: plain and `CREATE_NEW_CONSOLE + SW_SHOWNOACTIVATE` each opened a
    `CASCADIA_HOSTING_WINDOW_CLASS` window; `CREATE_NO_WINDOW` opened nothing.
    A `CREATE_NO_WINDOW` console is still a real console — `AttachConsole`,
    `WriteConsoleInput` and the screen buffer all work — so anything that only
    needs to *reach* a console should use it. `spawn_claude` is the deliberate
    exception: its window is the point.

    **That exception is guarded, not trusted.** `claude-console`'s own
    `tests/test_conventions.py` fails the build if any file but its `session.py`
    names a new-console flag, in any spelling. This repo's copy of that guard
    has an *empty* allowlist, which is the stronger assertion: nothing here
    opens a console at all.

    **The `conhost.exe` pin is gone**, along with the focus watchdog, the forced
    console font and the session icon that depended on it. conhost could not
    draw the session — no monospaced font on this machine covers `U+23BF`, the
    `⎿` on every tool result line. A session now opens in Windows Terminal
    running PowerShell, and `claude_console.session_pid` is the `Popen` itself
    rather than a child, because there is no host in between any more. The full
    measurements, including why the taskbar icon cannot come back, live in
    `claude-console/CLAUDE.md`.

19. **`auto_group` runs after `launcher.hand_off`, never before.**
    `launcher.hand_off` saves the `Task` objects `Api.hand_off` handed it, so
    grouping first would rewrite those same files and leave those objects
    stale — the save would then silently discard the group. Going second also
    means a session that failed to start leaves nothing grouped, which is the
    same guarantee the spawn failure path already gives for `status` and
    `started`.
22. **Commands are submitted before the prompt is typed.**
    `claude_console.console_input.deliver`
    calls `submit()` — which presses Enter — for every `/color` line
    first, and only then `paste()`s the prompt, which never presses Enter. Get
    the order backwards and a command's Enter would land on top of the
    still-unsubmitted task text, submitting the user's prose as a chat message
    instead of leaving it editable — silently breaking invariant 2. Ordered
    this way instead, a command that fails to submit costs only itself: the
    remaining commands are abandoned, but the prompt is attempted regardless,
    so a hand-off whose `/color` was too slow to land still ends exactly
    where a hand-off without this feature always has — task text sitting
    editable in the box. Invariant 24 is what makes each of those writes
    actually land as its own event.

    **`/rename` is not one of those commands any more, as of 2026-07-26.** A
    session's name goes on the launch — `claude -n <name>`, applied by the
    process that draws the window — because a typed rename was two screen
    round-trips standing between a window opening and the tasks arriving in
    it, on the slowest part of a session's life. `launcher.hand_off` passes
    `name=` to `open_session` and never builds the command; the typed form
    survives inside `claude_console` for a caller that supplied its own argv,
    which here means a project with a `launch` override.

    **And the prompt is now proven to have landed rather than assumed.** It
    was the one write in the whole protocol that was never checked — which is
    what "sometimes the prompt gets eaten" was. `paste` writes, reads the box
    back, and clears and writes again if its own text is not there; a prompt
    that never arrives reaches `Deliveries` through `on_finish` and the page
    says so. The measurements behind all of it are `claude_console`'s
    invariants 13 and 14, and the delivery log
    (`%LOCALAPPDATA%\claude_console\delivery.log`) is where a hand-off that
    misbehaves explains itself.

24. **Nothing is written to a session's console until the prompt box shows the
    last thing that was.** Two writes a session reads in one pass are not two
    events to it. `WriteConsoleInput` only queues records; whether they arrive
    as one read depends on when the session next drains the buffer, which is
    the session's business and not the writer's. Measured against a live one:
    with the whole hand-off written back to back, a `\r` sitting between two
    bracketed pastes is read as *part of the paste* — `/rename …` and
    `/color green` merged onto a single line, both Enters vanished, and the
    task prose landed on the end of that line. So `submit` writes the line,
    waits for it to appear in `prompt_box`, writes `\r`, and waits for it to
    leave again. Only a wait on the screen proves anything: a `time.sleep`
    measures the writer, not the reader, which is why the 0.5 s
    `SETTLE_SECONDS` this replaced could not fix it — no constant can, since a
    session busy with its own startup reads when it reads. (The condition-based
    version is also *faster*: 0.42 s for two commands and a prompt, against
    1.0 s of unconditional sleeping.) A command that times out has its text
    still sitting in the box, so `deliver` calls `clear` before pasting the
    prompt onto it — **Ctrl+U**, the one keystroke measured to empty the box.
    Escape, the obvious guess, does nothing to a typed line at all.

25. **The console is not put on a font any more, because the host it was
    fighting is gone.** Nothing here does anything about rendering; a
    WT-hosted session draws every glyph without help, and Windows Terminal
    ignores the console font APIs outright.

    **This entry used to end with a wrong prediction, and that is the lesson
    worth keeping.** It said: no monospaced font on the machine has both `⎿`
    (`U+23BF`, the tool-result elbow, on every tool call) and the quadrant
    blocks `U+2596`–`U+259F` the logo is drawn from; WT renders the elbow only
    because it falls back per glyph; a WT-hosted window is the one thing
    invariant 10 rules out; *"if the elbow ever matters enough, the lever is a
    wider-coverage font, not a different host."*

    Every fact in that was right and the conclusion was backwards. The elbow
    did matter enough, and there is **no** wider-coverage font to reach for —
    measured 2026-07-26 across every font installed on the machine, exactly
    three cover both and all three are proportional, which conhost cannot use.
    So the lever was the host after all, and invariant 10's constraint turned
    out to be the thing that should give. When a note names two levers and
    rules one out on a constraint, check the constraint before believing the
    recommendation.

31. **A button outside the selection bar acts on the tasks it names — unless
    every one of them is ticked, in which case it acts on the selection.**
    `aimedAt` in `ui/selection.js` is that rule, and everything outside the bar
    goes through it: `completeWithSelection` (every `done` in the app) and the
    Claude button, which a task row and a group header each carry. A control
    that decides for itself is the defect, and it is silent in a specific way —
    the bar reads "4 selected", the click finishes or launches exactly one of
    them, and that reads as the ticks being ignored rather than as a button
    being narrower on purpose.

    **What a header's button names is the rows it DREW**, `block.tasks`, not
    the group's full membership — the same set its `done` acts on. The two
    differ only for a header in IN PROGRESS reading `2 of 5`, where the other
    three are in a bucket and not in this session. The group *drag* is the
    deliberate exception on the other side, because a group lives in one
    bucket (invariant 16) and there is no such thing as moving part of one.

    **`fromSelection` is one answer, not two flags.** It says whether the
    selection was what acted, and two separate things hang off it in `handOff`:
    the batch-name row is read only when it is true (the row is hidden below
    two ticks and its value can be left over from a larger selection, so a
    single-task hand-off would take a name meant for a batch still sitting
    there staged), and **the ticks are restored only when it is false**.
    `refresh()` rebuilds `#task-list` with `replaceChildren`, so every checkbox
    comes back new and unchecked — without the restore, launching one unticked
    row would silently clear a batch the user had spent time staging, which is
    the opposite of "that row goes on its own". A group header's box is
    *derived* on the way back rather than remembered: all members ticked is
    exactly what it means.

    The mechanism, rather than the principle: `test_only_one_call_site_hands_
    tasks_to_claude` allows exactly one `callApi('hand_off'` across the UI
    scripts, and `test_only_the_selection_owns_completing_tasks` keeps
    `'complete_tasks'` inside `selection.js`. One call site is what forces a
    new button through `handOff`/`completeWithSelection` and therefore through
    `aimedAt`. Both search code only — `_without_comment` strips `//` first, so
    the convention can be written down next to the code it governs. Neither can
    see a caller that reaches the right function with the wrong ids.

- **Every control that opens a Claude session is the Claude glyph, and the
  glyph is written down once.** Four of them — the toolbar's `#spin-up`, the
  selection bar's `#selection-spin-up`, every task row's and every group
  header's. Two of those read "Spin up Claude" until 2026-07-27 while the other
  two carried the icon, which reads as two features rather than one control in
  four places. `CLAUDE_ICON` is a single `const` in `ui/tasks.js`; the two
  markup buttons are **empty** in `index.html` and are filled beside the line
  that wires their onclick. The only difference left between the four is a CSS
  rule about being *inside a row*: `.claude` is a visible orange glyph, and
  `.task .claude` / `.group-header .claude` hide it until the row is hovered.

  `test_no_claude_button_carries_a_text_label` and
  `test_the_claude_glyph_has_exactly_one_definition` fail the build on a label
  creeping back, on a button that carries no `.claude`, on a second definition
  of the glyph, on an `<svg>` in the markup, and on a button nothing fills.
  **What no text-based test can referee is whether the glyph is visible**:
  `.actions button` is a class *and* a type, so it outranks a bare `.claude`
  and the bar's button renders as a grey pill with an orange glyph in it unless
  `.actions button.claude` wins — which looks deliberate, not broken. Measured
  instead, against the real stylesheet: `border=0px none`, `bg=rgba(0,0,0,0)`,
  `28.0x28.0`. A future rule added to `.actions button` re-opens that fight
  silently.
