# Task Tracker — Design

**Date:** 2026-07-25
**Status:** Draft, pending review

A single-window task tracker for personal projects. Replaces the notepad, not
Jira. The bar it must clear: capture has to be as frictionless as opening
Notepad, or it gets abandoned the way Beads did.

## Problem

Tasks currently live in a notepad as freeform prose, tagged `BUG` / `FEATURE` /
`ITERATION`, each defining what is wanted and why. This works because it asks
nothing at capture time. It fails at everything after: no cross-project view, no
priority, no way to hand a task to Claude, and no separation between "still to
do" and "long since done."

`sm64_tracker/internal_notes/design_log.md` is the reference case — 560 lines
where completed and pending items are visually near-identical, ideas from
months ago sit unmarked, and it serves as task queue and project history at
once, doing both badly.

## Design principles

Drawn from lightweight PM practice, and the reason each is here:

- **Capture is zero-decision.** No field is required to write a thought down.
  Structure is added later, deliberately.
- **Three statuses.** `open → in-progress → done`. State machines beyond this
  are theater for one person.
- **Ordered buckets, not priority labels.** P0/P1/P2 collapses — within months
  everything is P1. Buckets with manual ordering inside resist this because an
  oversized `now` is visually obvious.
- **Ephemeral and durable are separate.** Tasks are throwaway. The dated record
  of what got done is permanent, and it is *generated*, never hand-maintained.
- **Plain text.** Greppable, editable in any editor, readable by Claude with no
  export step — and diffable in git if you opt a project into tracking.
- **The app is optional.** Everything is markdown in your repos. If the app
  breaks, the backlog is still there and still readable.

## Architecture

### Storage

Tasks live in each project's own repo. A central registry only records where
projects are.

```
~/.task-tracker/
  projects.json        registry: name -> path, tracked flag, launch override
  settings.json        wip_limit, stale_days, task types
  inbox/               untriaged raw notes (no project assigned yet)
    2026-07-25-143022.md

<project>/.tasks/
  .gitignore           contains `*` — the folder is invisible to git
  open/  0042-replay-audio-desync.md
  done/  0031-streak-targets.md
```

`open/` and `done/` are directories because the archive should not weigh down
the working set. `bucket` and `order` are frontmatter, not directories — moving
a task between buckets is a metadata edit, not a file move.

### Git tracking

`.tasks/` is **not committed** by default. On first use in a project the app
writes `.tasks/.gitignore` containing `*`, which ignores the folder and the
ignore file itself — zero footprint in the repo. This matters because several
projects (`sm64_tracker`) are public, and committing would publish raw backlog
prose.

A per-project `tracked` flag in `projects.json` flips this: setting it true
deletes that `.gitignore` and the folder becomes ordinary versioned content.
Reversible in either direction at any time, since nothing else depends on it.

Two consequences worth naming. First, an untracked backlog has no git history,
so "how the project progressed" comes entirely from the progress view reading
`done/` dates — which is how it was going to work anyway. Second, gitignoring
does *not* hide files from Claude; it reads them normally, so the handoff is
unaffected.

### Task file

```markdown
---
id: 42
title: Replay audio desync after ~2 minutes
type: BUG              # any type defined in settings.json
bucket: now            # now | next | someday
status: open           # open | in-progress | done
order: 1               # manual rank within bucket
created: 2026-07-25
started:               # set when spun up in Claude
done:                  # set when closed
---

<your text, verbatim and untouched>

## Outcome
<optional, added when closing>
```

**The body is verbatim.** No template is enforced. If you write What/Why
headings you get them; if you write three rambling paragraphs you get those.
This matters because the body is what gets handed to Claude — the value is in
your own verbose framing of the problem, not in a normalized summary of it.

IDs are per-project integers, assigned as `max(existing) + 1` scanned at write
time. No counter file to drift out of sync.

### Application

Python, hosted in a native window via pywebview. No HTTP server, no port, no
uvicorn — pywebview's `js_api` bridge lets the frontend call Python directly.
Three dependencies total: `pywebview`, `pyperclip`, `pyyaml`.

```
task_tracker/
  app.py         pywebview window + Api bridge (the only wiring)
  store.py       .tasks/ read/write, task model
  registry.py    projects.json + settings.json
  launcher.py    clipboard + Claude process spawn
  console_input.py  types the prompt into the spawned session's console
  ui/index.html  one page
  ui/app.js
  ui/style.css
  pyproject.toml
```

`uv run app.py` starts it. Backend edit → ~1s restart; frontend edit → refresh.
Packaging to an .exe is deliberately deferred; it is a PyInstaller step later if
this ever leaves the machine.

The window is small, always-on-top (toggleable), and remembers size and
position — it is meant to sit beside your editor permanently, not be summoned.

External edits to task files are picked up by rescanning `.tasks/` on window
focus, plus a manual refresh. No file watcher in v1.

## Features

### Capture

A dump box, opened by a button in the window, takes text and saves it. No
fields, no project, no type. It lands in `~/.task-tracker/inbox/` as raw text
with a timestamp. This is the notepad, preserved exactly.

No global hotkey. System-wide hotkeys on Windows want an extra dependency and
are historically fiddly, and the window already sits always-on-top beside the
editor — a button is one click from wherever you are.

### Triage

A separate view walks untriaged notes one at a time with single-key assignment:
project, then type, then bucket. Roughly two seconds per note, done in batches
when you're in the mood for it, never in the middle of a thought.

For a dump containing several distinct ideas, **split with Claude**: assign the
project, then hand the raw text to a Claude window that breaks it into
individual task files. Used when a note is genuinely multiple tasks, not as the
default path.

### Priority and the task list

Three buckets shown as sections — `NOW`, `NEXT`, `SOMEDAY` — with
drag-to-reorder inside each. The top of `NOW` is the next thing you do; no
interpretation required. Type renders as an orthogonal colored tag, so "what
kind of work" and "how soon" read independently.

Reordering rewrites `order` across the affected bucket. Lists are small enough
that this needs no fractional-index cleverness.

### Task types

Types live in `settings.json` as a list of name plus color, seeded with `BUG`,
`FEATURE`, `ITERATION`. They are editable in the app — add, rename, recolor,
remove — because those three are a current intuition about what's useful, not a
fixed taxonomy, and the categories should be free to evolve as the way you work
does.

Editing a type migrates existing tasks immediately, so the stored data always
matches the configured types:

- **Rename** rewrites the `type` field of every task using it, across all
  registered projects, `done/` archives included. Skipping the archive would
  leave the progress view showing a type that no longer exists.
- **Delete** requires choosing a replacement type when any task still uses it.
  The same rewrite runs, then the type is removed. There is no orphaned state to
  land in.
- **Recolor** touches settings only — no task files change.

The sweep is a full scan and rewrite of every `.tasks/` directory in the
registry. At a realistic scale of a few hundred files this is effectively
instant, and doing it eagerly avoids a lazy-migration path that would have to be
correct forever.

One case can't be fully handled: a registered project whose path is currently
unreachable — external drive, moved directory — can't be rewritten during the
sweep. The app reports which projects were skipped, and the rename is still
applied everywhere else. Tasks in a skipped project therefore keep the old type
string, so **unknown types still render in a neutral color** rather than
erroring. That fallback is a safety net for this case and for hand-edited files,
not a substitute for migrating.

### Claude handoff

Select one or more tasks, hit spin up:

1. Selected tasks flip to `in-progress`, `started` is stamped.
2. Their bodies are joined verbatim, one task per line, each prefixed with its
   type — `FEATURE: <the idea>` — and copied to the clipboard.
3. A new visible terminal opens in the project directory running `claude`.
4. Once that session's prompt box is up, the text is **typed into it** and left
   unsent, so it can be edited or added to before it runs. The clipboard copy
   is the fallback for a session that never got there.

With nothing selected, spin up is still live: it opens a session in the current
project with an empty prompt, which is the "just get me a window here" case.

```python
subprocess.Popen(["claude", "--dangerously-skip-permissions"],
                 cwd=project_path, env=claude_environment(),
                 creationflags=subprocess.CREATE_NEW_CONSOLE)
```

Spawning the process directly rather than through PowerShell or `wt.exe` means
no shell ever parses the prompt, so quotes, newlines and backticks in your notes
survive intact — the escaping class of bug that `CLAUDE.md` already flags for
commit messages simply cannot occur. On Windows 11 this still opens in Windows
Terminal, since that is the default terminal application.

The environment is built explicitly rather than inherited. `Popen` otherwise
passes down `CLAUDE_CODE_CHILD_SESSION` and the rest of the launching session's
identity, which makes the handed-off terminal a nested child: it disables
transcript saving and keeps no history. `claude_environment()` strips those and
sets `CLAUDE_CODE_FORCE_SESSION_PERSISTENCE`, so the session is an ordinary
top-level one no matter how the tracker itself was started.

The prompt is **prefilled, not sent**: `Ctrl+V` drops it in, you can edit or add
a constraint, `Enter` starts it. This keeps the session yours and makes a
mis-selected task a no-op rather than an interruption.

Nothing is appended to the prompt — no instructions, no completion footer. What
Claude receives is exactly what you wrote. Closing the loop is manual and stays
that way: you end the Claude session and mark the task done in the app. You are
the one who decides something is finished, and a task auto-closing because a
session ended would be wrong more often than right.

Multiple selected tasks go to **one** window, worked in order. Two Claude
sessions editing one working tree would clobber each other, and making that safe
means git worktrees — real machinery this tool should not own.

Projects needing special startup (a venv, a wrapper script) can override the
launch command per-project in `projects.json`.

### Progress view

Closing a task moves its file to `.tasks/done/` with a `done` date. The progress
view renders those in reverse chronological order, grouped by month, per
project. It is entirely generated — the history is a byproduct of closing
tasks, with nothing to maintain.

The optional `## Outcome` section on a task surfaces here as a note beneath the
entry, for when *why it went the way it did* is worth keeping.

### Cross-project view

One list showing `NOW` tasks across every registered project, project name
alongside each row. Clicking through jumps to that project.

### Cross-project search

One box matching titles and bodies across all projects, `done/` included —
for "didn't I already write this idea down somewhere?"

### Staleness

Tasks untouched beyond `stale_days` (default 90) get a dim age marker. Not a
nag and never blocking; it just makes a stalling backlog visible so things get
killed on purpose instead of by neglect.

### WIP limit

A soft warning when `in-progress` exceeds `wip_limit`, configurable in settings,
**default 5** — matching the practical ceiling of roughly five concurrent Claude
windows before things get unruly. Warns, never blocks.

## Testing

`store.py` and `registry.py` are pure file-in/file-out and carry the real logic:
round-tripping a task through write/read, ID assignment against an existing set,
bucket reordering, the `open/ → done/` transition, and `.gitignore` bootstrapping
plus its removal when a project is flipped to tracked. These get direct tests
against a temp directory.

The type migration sweep earns its own tests, being the one operation that
writes across every project at once: a rename rewriting matching tasks in both
`open/` and `done/` across two projects while leaving other types untouched, a
delete-with-reassignment, and an unreachable project path being reported as
skipped rather than aborting the whole sweep.

`launcher.py` is mocked at the boundary — assert the constructed prompt text and
the arguments handed to `Popen`, never actually spawn a process.

The UI is not unit-tested. It is one page and the feedback loop is a refresh.

## Explicitly out of scope

Due dates, estimates, sprints, burndown, subtasks, dependencies, recurring
tasks, tags beyond type, multi-user anything, and sync. Each is a plausible
addition and each is a step back toward the tool that got abandoned.

## Decisions

Resolved during design, recorded because the reasoning is easy to lose:

- **`.tasks/` is untracked by default**, flipped per-project by a registry flag.
  Public repos would otherwise publish raw backlog prose.
- **Nothing is appended to the Claude prompt.** Closing is a human judgement,
  made in the app, not inferred from a session ending.
- **A button, not a global hotkey.** The window is always-on-top and adjacent;
  a system-wide hotkey buys a dependency and a class of Windows bugs to solve a
  problem that isn't there.
- **Types are user-editable, and edits migrate existing tasks immediately.** The
  current three are an intuition, not a taxonomy. Renames and deletions rewrite
  affected task files across every project rather than leaving stale type
  strings behind.
