---
paths:
  - "ui/editor.js"
  - "ui/triage.js"
  - "ui/settings.js"
---

# The editor overlay, triage, and settings

Invariants 11, 12, 13, 14 and 30.

11. **A suggested value is written once, into an untouched field.** The title
    suggested from a note's first line is filled when that note first becomes
    current and never again; one keystroke marks the box yours for the life of
    that note. Capture has no note to key off, so an identity-less open takes a
    fresh `Symbol` — which can never equal a previous or future
    `titleFilledFor`, so every capture starts blank instead of inheriting the
    last one's title. Both halves shipped as bugs first.

12. **Choosing a chip re-renders chips and nothing else.** `renderChips()`
    touches the three chip rows and nothing else, and every chip's `onclick`
    calls exactly that. The bug this replaced was a single render function that
    also rewrote the title, so picking a type after typing a title silently
    discarded it. Never route a chip click through a broader render.

13. **A body is written only when it changed — and "changed" is measured
    against the editor's own baseline, not the file.** Toast UI normalises
    markdown on every round-trip, so `setMarkdown(body)` then `getMarkdown()`
    can differ from what went in with nobody typing anything. Comparing against
    the loaded text would therefore report "changed" for every hand-written
    task and silently reformat prose no one touched. `openEditor` records
    `normalisedBody` — what this load's round-trip produced from the untouched
    content — and the save path omits `body` from the update entirely when the
    two match, so the file keeps its original bytes.

14. **Attachment paths come from the backend and are `file://` URLs.** The
    renderer never builds a path. `Api.save_attachment` returns `as_uri()`, not
    `as_posix()`: a bare `C:/repos/x/a.png` is not a URL — the leading `C:`
    parses as a *scheme*, so the browser never resolves it as a path and the
    image silently fails to load. The design spec called for the bare form and
    was wrong about this. The absolute form is also what lets a handed-off
    Claude session open the screenshot the body refers to.

30. **Cancel and Escape are one action, and it asks before it discards.**
    `cancelEditor()` is that action; `closeEditor()` is the unconditional
    close and belongs only to the save paths. A new exit that reaches for
    `closeEditor` gets the old behaviour — silently throwing away whatever was
    typed — and nothing will report it.

    "Would this discard something" is measured against **what the overlay was
    showing when the open finished** (`openedWith`), not against the task on
    disk. The two differ on purpose in triage, where a title the user has
    already typed is deliberately carried across a Skip (invariant 11) and is
    that visit's starting point rather than an edit made during it. The body
    is compared against `normalisedBody` for invariant 13's reason: comparing
    against the file marks every hand-written task as edited, which would put
    a dialog in front of every cancel of a task nobody touched.

    Chip changes count. A discarded colour pick is a discarded decision.

- **Anything that edits a task** goes through `openEditor()` in `ui/editor.js`
  rather than a new overlay. It is one component with three entry points —
  capture, triage, and clicking a row — precisely so the no-clobber rules
  (invariants 11–13) hold in all three rather than being reimplemented and
  half-forgotten in each.
