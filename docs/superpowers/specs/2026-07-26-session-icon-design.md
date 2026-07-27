# The handed-off session wears Claude's icon — design

**Date:** 2026-07-26
**Status:** approved

## The problem

A handed-off session's taskbar button is indistinguishable from every other
console on the machine. It briefly was not: for a while the button carried the
Anthropic logo, which is what made a Claude window findable among a row of
terminals.

## What took it

The console host, pinned by invariant 10 on 2026-07-26 (`e4ca880`).

A console window's icon comes from the image the host was launched as, not from
the program running inside it. Measured against a hidden console, comparing the
window's icons pixel by pixel:

| spawned as | window's 32×32 icon |
|---|---|
| `conhost.exe python.exe …` — today's shape | `b6f24c934e74`, byte-identical to conhost.exe's |
| — | |
| `claude.exe`'s own resources | `2e9984fe3d08` |
| `conhost.exe`'s own resources | `b6f24c934e74` |

So the "brief period" was the window between spawning `claude.exe` directly and
pinning the host: a directly-spawned console adopts its client's icon, and one
launched *through* `conhost.exe` adopts conhost's.

Going back to a direct spawn is not an option — that is invariant 10, and it
costs the guarantee that nothing this app opens takes the keyboard.

## What it does

`console_input` sets the icon on the session's console window after the spawn,
through the same attach it already performs for the font. Nothing about
`launcher.spawn_claude` changes.

Three pieces, mirroring `use_font` / `_apply_face` exactly, because one pattern
for "dress the console this app just opened" is the point:

- **`session_icons()`** — resolve `claude` on PATH, `ExtractIconExW` a large and
  a small icon, cache the pair at module level. One pair serves every session.
- **`_apply_icon(icons)`** — `WM_SETICON` for `ICON_BIG` and `ICON_SMALL` on the
  attached console's window.
- **`use_icon(pid)`** — retry until the console exists, then apply.

`deliver` calls it first, ahead of `use_font`: the taskbar button exists before
the session has painted anything, and a hand-off with nothing selected gets an
icon for the same reason it gets a font.

## Both sizes, or the wrong one is missing

`ICON_BIG` is what the taskbar and Alt+Tab draw; `ICON_SMALL` is the title bar.
Setting one leaves the other falling back to conhost's class icon, which reads
as the change half-working. `ExtractIconExW` hands back exactly this pair at the
system's own metrics.

## The image is `claude` on PATH, not the launch command

A per-project override like `pwsh -c claude` still opens a Claude session, so it
still wears the Claude icon. Resolving the icon from the override would give
that window PowerShell's icon, which is the opposite of the point.

## The handles are extracted once and never destroyed

`DestroyIcon` on a handle a live window is holding is how the icon goes blank,
and every open session is holding this one. They are extracted once — measured
at 0.000 s even against a 265 MB `claude.exe` — kept for the tracker's life, and
never released.

The consequence, stated because it is the one wart: **the handles belong to the
tracker**. Measured — an icon handle goes invalid (`ERROR_INVALID_CURSOR_HANDLE`)
the moment the process that supplied it exits, and neither `LR_SHARED` nor a
module-resource load changes that; `kernel32!SetConsoleIcon`, which existed for
exactly this, is gone from this machine's kernel32. So a session that outlives
the tracker — you close it, or press ↻ — is left holding a dead handle. What
Explorer draws then is **not measured**, because it needs a real window on
screen; the guess is that it keeps the bitmap it already rasterised and nothing
visibly changes. If it blanks instead, the fix is to send `WM_SETICON(NULL)` to
each session window on shutdown, which drops it back to conhost's class icon —
exactly today's behaviour. That is a ten-line addition, and it waits on the
by-hand check below rather than being built for a failure nobody has seen.

## Every failure is silent, and costs only the icon

`claude` not on PATH, a console that never appears, a `SendMessage` that times
out: each returns False and nothing else changes. The session, the typed prompt
and the clipboard copy are untouched on all three paths — the same discipline
the rest of this module runs on.

The send is `SendMessageTimeoutW` with `SMTO_ABORTIFHUNG` rather than
`SendMessageW`: a cross-process `SendMessage` blocks until the receiving process
pumps its message queue, and a wedged conhost would otherwise park the hand-off's
daemon thread for as long as the session lives.

## Testing

The mechanism cannot be tested end to end in this suite, and that is a
deliberate limit rather than an oversight. `tests/_console_probe.py` opens its
console with `CREATE_NO_WINDOW`, and a `CREATE_NO_WINDOW` console has **no
window at all** — measured: `GetConsoleWindow` returns 0, so there is nothing to
hang an icon on. The only console with a window is one opened with
`CREATE_NEW_CONSOLE`, which `test_nothing_but_the_hand_off_may_open_a_console_window`
forbids outside the hand-off — a guard bought with a real bug, and not worth
weakening for one test.

So the tests pin the seams, in `tests/test_console_input.py`:

- the icon is applied before anything is typed, like the font;
- both `ICON_BIG` and `ICON_SMALL` are sent;
- a console with no window yet is a failure, not a crash;
- a machine with no `claude` on PATH gets no icon and no attach;
- the pair is extracted once and reused.

And the check that can only be made by hand, on the running app:

- spin up a session and look at the taskbar — the Anthropic logo, not a
  terminal;
- with that session still open, press ↻ and look again. This is the open
  question above: if the button blanks, the shutdown restore gets built.

## Touch set

`console_input.py`, `tests/test_console_input.py`, `CLAUDE.md`.
