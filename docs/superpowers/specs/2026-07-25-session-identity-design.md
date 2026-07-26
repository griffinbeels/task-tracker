# Session identity — naming and colouring a handed-off Claude window

2026-07-25

## The problem

Spinning up a session from a task opens a Claude window that looks exactly like
every other Claude window. The tracker already knows what that window is for —
it just typed the task into it — and throws the knowledge away. With three or
four sessions open, telling them apart means reading each one's scrollback.

Claude Code has two commands that fix this, and the tracker can send them the
same way it already sends the task text:

- `/rename [name]`
- `/color [red|blue|green|yellow|purple|orange|pink|cyan|default]`

## What ships

A hand-off renames the new session after the task it carries, prefixed with the
task's type, and colours it with a colour the task itself owns. A batch of
tasks can be given a name of its own; left blank, it falls back to the first
task's.

## The hand-off sequence

`launcher.hand_off` spawns the session as it does today, then hands
`console_input` a list of command lines *and* the prompt text:

```
/rename FEATURE: Rename the spawned session (+2)   typed, then Enter
/color purple                                      typed, then Enter
FEATURE: <body verbatim>                           typed, NO Enter
```

**The order is load-bearing.** The commands go first and the task text goes
last and unsubmitted. If both commands fail outright, the session still ends up
in exactly the state it reaches today: the task text sitting editable in the
prompt box. Nothing about invariant 2 (bodies are verbatim) or invariant 9
(typed text is bracketed, and waits for the prompt box) changes — this adds
work *before* the existing paste, never inside it.

### `console_input` contract

`paste(pid, text, timeout)` is unchanged and stays the only thing that writes
unsubmitted text.

Two additions:

- **`submit(pid, line, timeout)`** — waits for `READY_MARKERS`, writes `line`
  wrapped in the existing bracketed-paste markers, then writes a separate
  carriage return as its own input record. Returns whether both writes landed.

  Bracketed rather than raw keystrokes because a `/` at the start of the input
  opens Claude Code's command-suggestion popup, which is a live UI reading
  keystrokes. A paste arrives as one event with a complete line in it, so the
  popup never sees a partial token and cannot claim the Enter that follows.

- **`deliver_when_ready(pid, commands, prompt)`** — replaces
  `paste_when_ready` as the background-thread entry point. Submits each command
  in order, then pastes the prompt.

Timeout budget, because the first wait is qualitatively different from the
rest:

- the first readiness wait keeps the current `READY_TIMEOUT` (45s) — it is
  waiting for a process to boot;
- every later wait gets a short timeout (~5s) — the prompt box is already up,
  so a long wait here only delays the prompt;
- a settle of roughly half a second after each submitted command, so the next
  write does not land while Claude Code is re-rendering;
- **a command that times out abandons the remaining commands but never the
  prompt.** The prompt paste gets a fresh `READY_TIMEOUT`, not whatever budget
  the commands left behind — `deliver` calls `paste(pid, prompt)` with no
  timeout argument of its own. A full retry for the one thing that actually
  matters, since handing it only the leftover budget would make the most
  important part of the hand-off the part most likely to be cut short by
  commands that failed early.

All of it is best-effort and silent on failure, for the reason invariant 9
already gives: the same text is on the clipboard, so the cost of giving up is
one Ctrl+V.

### Failure behaviour

If a command is not recognised — an older Claude Code without `/rename`, say —
the line is submitted as an ordinary user message and the session answers it.
That is noise in the transcript above an otherwise-correct prompt box, not a
lost hand-off. It cannot happen on a machine whose Claude Code has both
commands.

## The colour

### Where it lives

`store.py` owns it, because `store.py` owns `Task`.

```python
CLAUDE_COLORS = ("red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan")
```

`default` is deliberately absent: every task has a real colour, so there is
never a reason to send it.

`Task` gains `color: str`. It is written into frontmatter by `render_task` and
read by `parse_task`:

```
---
id: 12
title: Rename the spawned session
type: FEATURE
color: purple
bucket: now
status: open
...
---
```

### Assignment — one backend rule, one frontend heuristic

**Backend, `store.py`:** a task whose frontmatter has no `color:` — **or a
`color:` that is not one of the eight** — parses as `CLAUDE_COLORS[id % 8]`,
and `create_task` uses the same expression when no colour is passed. That is
the whole backend rule.

Normalising at parse time rather than at each use is what makes `Task.color`
always a valid Claude colour name. A task file is hand-editable, so `color:`
is unvalidated user text arriving on a path that ends in "type this into
another process's console" — the same class of input invariant 5 exists for.
Downstream, the `/color` argument is always legal and the renderer's hex
lookup can never miss.

Consequences, all of them wanted:

- Every task written before this feature has a colour from the first launch, so
  the list never renders a task with no dot. No migration sweep runs.
- The derived value becomes a real field the next time that task is saved for
  any reason — reads never write.
- Consecutive ids never collide, which plain randomness cannot promise.

**Frontend, `ui/state.js`:** `suggestColor(project)` picks at random among the
colours *least used* by that project's open tasks. It runs when the editor
opens a new task, and the chosen colour is passed explicitly to `create_task`.

The heuristic lives in exactly one place. The backend does not reimplement it;
it only supplies a floor for a task created without one.

### Which colour a batch gets

The first selected task's, matching the naming rule below.

## Naming

`launcher.session_name(tasks, name)` returns the `/rename` argument, or
nothing when there is no name to give.

**`name` is passed in; `launcher` never derives it.** That is the seam this
design turns on — see "Relationship to the task-groups design" below.

1. A non-blank `name` wins outright.
2. Otherwise `"{type}: {title}"` from `tasks[0]`, with `" (+N)"` appended when
   more than one task is selected, N being the count of the others.
3. All whitespace runs collapse to single spaces. The UI's title box is
   single-line, but a task file is hand-editable — a newline inside a
   `/rename` argument would submit the line early and leave the rest of the
   name as a stray prompt.
4. Capped at 60 characters. A tab label longer than that is unreadable, and a
   short line is also what keeps Claude Code inserting the paste literally
   rather than collapsing it into a `[Pasted text]` placeholder.
5. An empty result means `/rename` is not sent at all.

`launcher.session_color(tasks)` returns `tasks[0].color`, or nothing when no
tasks were selected.

**Spin up with nothing ticked sends neither command.** No task means nothing to
name and no colour to use, so that path opens a session exactly as it does
today.

## UI

### The colour dot

Every task row gets a small dot at its head, filled with the task's colour.
It sits before the type tag, which keeps its own colour and meaning — the dot
answers "which window will this be", the tag answers "what kind of work is
this".

Colours are rendered from a name → hex map in `ui/state.js`, chosen to sit on
the same Radix scale as the existing default type colours (`#e5484d`,
`#30a46c`, `#0090ff`):

| name | hex | | name | hex |
|---|---|---|---|---|
| red | `#e5484d` | | purple | `#8e4ec6` |
| blue | `#0090ff` | | orange | `#f76b15` |
| green | `#30a46c` | | pink | `#d6409f` |
| yellow | `#f5d90a` | | cyan | `#00a2c7` |

### The editor's COLOUR field

A fourth `.field` row in `#editor-meta`, below `When`, holding eight swatches —
the same 56px label column and chips row the other three use, so the four rows
share one left edge.

A swatch is a filled circle, not a text pill, so it needs its own small builder
alongside `chip()`. Selection is shown the way `.chip.on` shows it: a
difference you see rather than one you look for.

**It renders through `renderChips()` and nothing else** (invariant 12). Picking
a colour must not touch the title, the body or anything else in the overlay.

`editorContext.color` joins the save payload. In capture and triage mode it is
seeded from `suggestColor()`; in edit mode from the task.

### The batch-name row

`<div id="handoff-name" hidden>` sits between `#toolbar` and `#wip-warning` —
the slot already used by the two warning rows for "appears when it has
something to say". It holds one labelled text input and appears when **two or
more** tasks are ticked.

**Its placeholder is the exact name the session will get if it is left blank**,
recomputed as the selection changes. The default therefore explains itself, and
because the suggestion is a placeholder rather than a value there is no
clobber question to get wrong — typing replaces nothing, and clearing the box
restores the default.

`Spin up Claude` passes the trimmed input value to `hand_off`; blank means
"use the fallback".

This box is also where the task-groups design's auto-formed group gets a real
name instead of a silent one — see below.

## Bridge

- `Api.hand_off(project_name, task_ids, name="")` — the new third argument is
  forwarded to `launcher.hand_off`. Blank means "work it out from the tasks".
- `Api.create_task` takes `color` and passes it through.
- `Api.update_task` adds `color` to its settable-key list, and rejects a value
  outside `CLAUDE_COLORS` the way it already rejects an unknown bucket or
  status. Without the settable-key half the editor's colour change is silently
  dropped — the same shape as the bug that made `file_note` discard edited
  prose.

## Relationship to the task-groups design

`docs/superpowers/specs/2026-07-25-task-groups-design.md` introduces
`Task.group: str | None` and `groups.auto_group`, which names a group on
spin-up and returns that name. A group is defined there as "a set of tasks
handed to **one** Claude session" — which is exactly the thing this feature is
naming and colouring.

**`Task.group` has already landed**, in `2613634`, which is this worktree's
base. `groups.py` and `auto_group` have not.

**The two do not need to be built in order, and this one must not read
`Task.group`.** `launcher.session_name` takes the name as an argument and never
asks where it came from. That single choice is what keeps the seam clean:

| | Who supplies `name` |
|---|---|
| Today | the batch row's trimmed value, or `None` |
| Once groups land | `groups.auto_group(...)`'s return value, falling back to the batch row's value, falling back to `None` |

The change when groups arrive is one line in `Api.hand_off` — and the groups
design already says `hand_off` gains a call to `auto_group` there. The batch
row stops being a hand-off-only label at that moment and becomes the group's
name, which is strictly better than the silent seed-from-first-title that
design currently specifies, and it does so **without taking focus during a
spawn** (`CLAUDE.md` invariant 10), because the name is typed before the button
is clicked rather than into a box that opens afterwards.

Two mechanical notes for whoever builds second:

- The groups design splits `ui/tasks.js` into `ui/groups.js` and
  `ui/inprogress.js`. The colour dot belongs to `taskRow`, which stays in
  `tasks.js`; the batch row is toolbar-adjacent and also stays.
- `store.py` gains a field in both designs. They are independent fields with
  independent parse rules and do not interact. `group` parses as `None` for a
  missing key; `color` never parses as `None`, because an unnamed group is a
  real state and an uncoloured task is not.

## Relationship to the selection-bar design

`docs/superpowers/specs/2026-07-25-selection-bar-design.md` (written, not
implemented) puts a bar under the toolbar whenever anything is ticked —
`3 selected [Move to… ▾] [Done] [Delete] [Clear]` — in a new `ui/selection.js`.
That is the same strip of window as the batch-name row, and that design states
its four controls plus a count are the most the row can carry at 420px.

**Two bars under one toolbar is the wrong answer.** The name is a property of
the selection, so it belongs to the selection's own component:

- Built here, now, as `#handoff-name`: its own row, shown at 2+ ticked,
  positioned and styled to sit directly under where that bar will appear.
- When `selection.js` lands, the input **moves into `#selection-bar` as a
  second line** and `#handoff-name` disappears. `selection.js` owns showing and
  hiding it; the placeholder logic and the `spin-up` call site move with it
  unchanged.

That is a named one-input migration, not a surprise. It is called out here so
whoever builds the selection bar absorbs the row instead of stacking a second
one beneath it.

The two features also both add a delegated `change` listener concern on
`#task-list`. The selection-bar design already specifies **one** delegated
listener guarded on `.select`; this feature's placeholder update belongs in
that same handler rather than in a second listener.

## Testing

Directly testable, no window required:

- `session_name`: single task, multiple tasks, a non-blank override, an
  override that is only whitespace, a title containing a newline, a title long
  enough to hit the cap, an empty title.
- `session_color`: first task's colour; nothing for an empty selection.
- `store`: `color` survives a `render_task` → `parse_task` round trip; a file
  with no `color:` parses to `CLAUDE_COLORS[id % 8]`; `create_task` with and
  without an explicit colour; a parsed-and-resaved legacy file gains the field.
- `Api.hand_off` forwards the override, with `subprocess.Popen` and
  `launcher.pyperclip.copy` mocked at the boundary as the existing launcher
  tests do.
- `Api.update_task` accepts `color` and persists it.

Not covered by pytest, and checked by hand instead:

- **Whether a bracketed-paste `/rename foo` registers as a slash command.** The
  detection happens on the input buffer's contents at submit, so it should —
  but this is a claim about someone else's UI, not about this codebase. If it
  turns out only typed input is recognised, the fallback is to write the line
  unbracketed and settle before the Enter. This is the first thing to verify
  when the feature runs for real.
- That the two commands land in order and the prompt text still arrives
  unsubmitted after them.
- The two standing editor checks from CLAUDE.md, since `ui/editor.js` is being
  touched: type a title then click a different type chip (the title must not
  change), and edit only a task's bucket in a tracked project (the `.md` must
  show a frontmatter change and no body diff).

## Files touched

Built in `task_tracker-worktrees/session-identity` on
`feature/session-identity`, branched from `feature/task-groups` at `2613634`
— which already carries copy-as-prompt (`launcher.py`, `app.py`,
`ui/tasks.js`, `ui/style.css`) and `Task.group` (`store.py`). Nothing here
conflicts with either: `build_prompt` and `copy_prompt` are untouched, and
`group` and `color` are independent fields.

Three features are in flight against these same files. This one keeps its
footprint in `ui/tasks.js` to two additions — the dot inside `taskRow`, and
the batch row — for that reason.

| File | Change |
|---|---|
| `store.py` | `CLAUDE_COLORS`, `Task.color`, render/parse, `create_task` |
| `launcher.py` | `session_name`, `session_color`, command assembly, `hand_off` signature |
| `console_input.py` | `submit`, `deliver_when_ready`, short-wait timeout |
| `app.py` | `hand_off` override arg, `create_task` colour, `update_task` key lists |
| `ui/index.html` | `#handoff-name` row, COLOUR field markup |
| `ui/state.js` | colour hex map, `suggestColor` |
| `ui/tasks.js` | row dot, selection handler, batch row, pass the name |
| `ui/editor.js` | swatch builder, COLOUR field, save payload |
| `ui/style.css` | `.dot`, swatch, `#handoff-name` |
| `tests/` | the cases listed above |

## Deliberately not built

- **A group entity of its own.** `2026-07-25-task-groups-design.md` owns that
  concept; this feature only consumes a name someone hands it.
- **Reacting to a colour changing after hand-off.** The session is coloured
  once, when it opens. Recolouring a live window would mean tracking sessions,
  which the tracker deliberately does not do.
- **`/color default`.** Nothing needs to un-colour a session.
- **A setting to turn this off.** It degrades to today's behaviour on its own
  when the commands do not land.
