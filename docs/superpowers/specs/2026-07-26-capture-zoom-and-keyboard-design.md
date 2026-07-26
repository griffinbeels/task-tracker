# Zoom and keyboard reach — design

**Date:** 2026-07-26
**Status:** approved, being implemented on `feature/capture-zoom-keyboard`

Three things the window cannot currently do, all of them reached from the
keyboard, and one of them wanted in two places.

1. Make the text bigger, in the capture editor and in the task list, each
   remembering its own size.
2. Get out of the editor's body and onto the buttons without a mouse.
3. Be asked before a Cancel throws away something that was written.

## What was measured before designing

Two facts this design rests on. Both were checked rather than reasoned about,
because both are the kind of claim that reads as obvious and is wrong.

**WebView2 does not intercept the zoom keys.** pywebview 6.2.1 sets
`settings.AreBrowserAcceleratorKeysEnabled = _state['debug']`
(`webview/platforms/edgechromium.py:287`), and debug is off in a normal launch.
So Ctrl+`+`, Ctrl+`-` and Ctrl+`0` are never claimed by the host and arrive at
the page as ordinary `keydown` events. Nothing has to be suppressed, and there
is no host zoom running underneath ours to disagree with. (`IsZoomControlEnabled`
is separately `True`, which is Ctrl+scroll — the host's own page zoom, untouched
by this and left alone.)

**CSS `zoom` reflows, and does so correctly on a full-screen fixed overlay.**
Measured in headless Edge at a 420px-wide window, `zoom: 1.5` on an element
shaped exactly like `.overlay` (`position: fixed; inset: 0`):

| | baseline | `zoom: 1.5` |
|---|---|---|
| the overlay's own box | `504x605@0,0` | `504x605@0,0` |
| a button inside it | `37x21` | `56x32` |
| `document.scrollWidth` | 504 | 504 |

The overlay stays exactly viewport-sized while its contents scale — Chromium
divides a zoomed element's containing block by the zoom, so `inset: 0` still
resolves to the viewport. **No wrapper is needed inside the overlays**, and
nothing gains a horizontal scrollbar.

The same run confirmed `zoom` on an ordinary in-flow wrapper scales its subtree
(a row 20px → 29px tall) without widening the document.

Two consequences worth stating because a reader would otherwise have to
rediscover them:

- `getBoundingClientRect()` returns **post-zoom** pixels, and `event.clientX/Y`
  are in that same space. Invariant 28's drag geometry is therefore correct
  under zoom with no change at all — it compares rects against pointer
  coordinates and both scale together.
- `getComputedStyle(el).fontSize` reports the **unzoomed** value. Anything that
  ever wants to read the effective size must measure a rect, not ask for a
  computed length. Nothing in this design does, but a future reader will be
  tempted.

## 1. Zoom

### Scopes

One factor per scope, one ladder shared by both.

| scope | elements it scales |
|---|---|
| `editor` | `#editor` |
| `app` | `#list-view`, `#progress`, `#settings` |
| `app`, when `zoom_whole_window` is on | …and `header`, `#toolbar` |

`#list-view` is a new wrapper around the selection bar, the two warning banners
and `#task-list`. It is a plain in-flow `<div>` — the overlays stay siblings of
it, so nothing compounds: an element is in exactly one scope, and the scope it
is not in has its `zoom` cleared rather than left at a stale value.

**Which scope a key press hits is decided by one question: is the editor open.**
Open → `editor`. Otherwise → `app`. There is no mode, no focus rule and nothing
to remember, and it matches the rule Escape already uses for "which overlay is
this key for".

**Progress and Settings always scale with the list**, whatever the toggle says.
They are lists of the same kind; a "make the text bigger" that skipped them
would read as those two panels being unfinished. The toggle therefore names
exactly one difference — whether the header and toolbar join in — which is the
only way a difference like this stays legible (invariant 28's closing note,
applied to a setting instead of a section).

### The setting

`Settings.zoom_whole_window: bool = False`, in `settings.json`, exposed in the
settings overlay as a checkbox reading *"Scale the header and toolbar with the
list"*.

It exists because the right answer is not knowable in advance: scaling the
header at 200% in a 420px window will crowd the top row (the picker is already
`flex: 1 1 auto; min-width: 90px`, and `⚙` has nowhere to go), and whether that
matters is a question about use, not about layout. Shipping both behind a switch
is cheaper than choosing wrong.

Default off.

### Keys and the ladder

- **In:** Ctrl with `+`, `=`, or NumpadAdd.
- **Out:** Ctrl with `-`, `_`, or NumpadSubtract.
- **Reset to 1.0:** Ctrl with `0` or Numpad0.

`Shift` is permitted (US layouts need it for `+`); `Alt` and `Meta` are not, so
nothing here shadows a system chord.

Ladder: **1.0 to 2.0 in steps of 0.1**. 1.0 is the floor, stated by the user —
"a minimum of 100% scale, as it is right now". 2.0 is the ceiling because the
window is 420px wide by habit and nothing above that is legible in it.

Steps are held as an integer count internally and the factor derived from it, so
repeated presses cannot drift into `1.0000000000000002`.

### Feedback

A transient pill, bottom-right, showing the resulting percentage, fading after
roughly 900ms. It is not decoration: **at the floor, Ctrl+`-` does nothing**,
and a key that silently does nothing is indistinguishable from a key that is
broken. It sits outside every zoom scope and above `#editor`'s `z-index: 1`, so
it is neither scaled by the thing it is reporting on nor hidden behind it.

### Where the state lives

The **level** is view state: it describes how this machine's window is being
looked at right now, not anything about the tasks. It goes in `session.json`
beside the fold state and the IN PROGRESS order, through
`registry._update_session` (invariant 17 — replacing the file to set one key
drops the rest). Written on every change, so a crash cannot lose it, exactly as
`set_last_project` is.

The **toggle** is a preference the user configured, so it goes on `Settings` in
`settings.json`.

Both files are documented as hand-editable, so both are filtered on the way out
and refused on the way in — invariant 23's split, which this follows exactly:

- `registry.zoom_view()` **repairs**: a missing key, a non-number, a string, a
  factor outside the ladder all resolve to the nearest legal value, because a
  hand-edited file must not be able to blank the window.
- `Api.set_zoom(scope, factor)` **raises**: an unknown scope or an out-of-range
  factor there means the JS caller is broken, and repairing it would hide the
  bug that produced it.

### Contracts

```
registry.zoom_view() -> {"app": float, "editor": float}
    Every key present, every value in [1.0, 2.0]. Never raises.

registry.set_zoom(scope: str, factor: float) -> None
    Read-modify-write of session.json. Caller has already validated.

Api.set_zoom(scope, factor) -> None
    scope must be "app" or "editor"; factor must be a real number in
    [1.0, 2.0]. Anything else raises ValueError.

Api.get_state() gains "zoom", the dict above.
Api.save_settings() gains zoom_whole_window, a bool.
```

## 2. Shift+Tab

A ring of `body → title → each visible action button → back to the body`.
Wrapping, so it never dead-ends.

The action buttons are whichever `showEditorActions` left visible, in DOM order
— File/Save, Restore, Later, Skip, Discard, Cancel. That list is already
mode-dependent and already correct; the ring reads it rather than restating it,
so a future button joins the ring by existing.

Chips stay mouse-only. This does not change what plain Tab does anywhere.

**Shift+Tab, not Tab, because Tab belongs to the body.** Toast UI binds it to
list indent, so it cannot be the key that escapes. Shift+Tab moving *forward*
is unconventional, and it is the point: there is one key that always advances,
and it works from inside the body where the conventional one cannot.

**The listener is on `#editor` in the capture phase.** ProseMirror binds
Shift+Tab to list-outdent on the contenteditable itself; a capture-phase
listener on an ancestor runs first, and `stopPropagation()` there keeps the
event from ever reaching it.

The cost, stated plainly because it is a real loss: **Shift+Tab no longer
outdents a list item in the editor body.** Backspace at the start of the item
still does.

If focus is somewhere not in the ring — a chip — the next Shift+Tab lands on
the body. That falls out of the modulo rather than being a rule of its own.

### Enter

Enter on a focused `<button>` already fires its click; nothing is needed for
that, and File / Later / Skip / Discard / Cancel all work the moment focus can
reach them.

What *is* needed: **`ui/style.css` currently draws no focus indicator on
`.actions button` at all.** A ring you cannot see is the same defect as no ring,
so `:focus-visible` styling on those buttons is part of this feature and not a
polish item.

Enter in the title box is left alone — it is not part of what was asked, and
making it save would be a second way to trigger the primary action.

## 3. Confirm before a Cancel that loses work

### The rule

Cancel asks first **when closing now would discard something the user did in
this editor**. Not "when there is text": in edit mode the title and body are
always full, so a literal reading would put a dialog in front of every single
cancel of an unchanged task — the same over-prompting the "prompt for an
outcome when marking done" idea was declined for.

"Something the user did" is measured against what this open started with:

| | dirty when |
|---|---|
| capture | anything typed at all — it starts blank, so the general rule collapses into the user's own sentence |
| triage | the title or body differ from the note's, or a chip moved |
| edit | the title, body, type, bucket, colour or group differ from the task's |

The body half compares against **`normalisedBody`**, never against the file
(invariant 13). Toast UI renormalises markdown on every round-trip, so comparing
against the loaded text would mark every hand-written task dirty and put a
dialog in front of a cancel that would have lost nothing.

Chip changes count. A discarded colour pick is a discarded decision, and the
whole reason for the prompt is that discarding decisions silently is what makes
Cancel feel like a trap.

### Escape

Escape is documented as Cancel, deliberately — so **Escape must ask too**. The
handler in `state.js` calls `closeEditor()` directly today; it moves to a new
`cancelEditor()`.

`closeEditor()` stays exactly what it is — the unconditional close every save
path uses. Two functions, one of which asks, rather than a flag on one.

### Not in scope

Triage's **Discard** deletes a note outright and does not confirm. That is a
real gap and it is a different one; changing it here would be scope this was not
given.

## Files

| file | change |
|---|---|
| `ui/zoom.js` | **new** — the scope table, the ladder, the key handler, the pill |
| `ui/index.html` | `#list-view` wrapper, the pill element, the `<script>` tag |
| `ui/editor.js` | the ring, `cancelEditor()`, the dirty check |
| `ui/state.js` | Escape routes through `cancelEditor()`; `refresh()` applies zoom |
| `ui/settings.js` | the `zoom_whole_window` checkbox |
| `ui/style.css` | `:focus-visible` on action buttons, the pill |
| `registry.py` | `zoom_view` / `set_zoom`, `Settings.zoom_whole_window` |
| `app.py` | `Api.set_zoom`, zoom in `get_state`, the flag in `save_settings` |

`ui/zoom.js` loads immediately after `state.js` — it needs `callApi` and reads
`state.zoom`, and `refresh()` calls into it, which is the same
resolved-at-call-time cross-file pattern the other seven scripts already use.

The zoom is applied to `#list-view`, which `render()` never replaces — the same
property that lets `wireDrag` bind once to `#task-list` (invariant 27). Nothing
re-applies zoom on a redraw.

## Testing

Everything on the Python side is directly testable and gets tests: the clamp and
repair in `zoom_view`, a `set_zoom` that preserves the other `session.json` keys,
the bridge's refusals (unknown scope, factor below 1, above 2, non-numeric,
boolean), `get_state` carrying the dict, and `zoom_whole_window` surviving a
save/load round-trip and a hand-edited non-boolean.

There is no JS test runner, and none of the three features can be signed off from
a diff — they are all gesture and keyboard. The by-hand checks go to the user
when this lands, not at the end:

**Zoom.** Ctrl+`+` in the list — the rows grow and the header does not (default).
Ctrl+`-` back down, then again at 100% — nothing moves and the pill says so.
Ctrl+`0` from 180% — straight back to 100%. Open Capture, Ctrl+`+` — the editor
grows and the list behind it does not. Close it: the list is still at its own
size. Press ↻ — both sizes come back. Tick the header/toolbar checkbox in
settings and Ctrl+`+` — the top two rows now grow with the list, and at 200% the
header must still be one row. Zoom the list, then drag a task between buckets and
into a group — it must land where it was drawn (this is the invariant 28
geometry running under a zoom). Zoom the editor, then click into the middle of a
paragraph — the caret must land where clicked, and a pasted screenshot must
still open full size.

**Keyboard.** In Capture, type a body, Shift+Tab — focus lands in the title box
and it is *visible* that it did. Shift+Tab again — the File button, outlined.
Enter — it files. Repeat to Later and to Cancel. Shift+Tab past Cancel — back in
the body, caret in it. In triage the ring must cover Skip and Discard; in edit
on a done task it must cover Restore.

**Cancel.** Capture, type one character, Escape — it asks. Capture, type
nothing, Escape — it closes. Open an existing task and Escape immediately — it
closes, no question. Open one, change only the colour, Escape — it asks. Open
one, change nothing, press Save — it must still save with **no body diff** in a
tracked project (the invariant 13 check, which this feature's dirty check must
not have broken).
