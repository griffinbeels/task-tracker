# The Claude glyph replaces the "Spin up Claude" label

2026-07-27. Task 0052: *"use the little claude symbol guy for every button that
needs claude. no longer use the 'spin up claude' button — make it just have the
claude icon directly."*

## What was wrong

Four controls open a Claude session. Two of them — the toolbar's `#spin-up` and
the selection bar's `#selection-spin-up` — read **Spin up Claude** as text,
while a task row's and a group header's carried `CLAUDE_ICON`. One action drawn
two different ways reads as two features rather than as one control in four
places, which is the shape a surface takes when it has been half-built.

## The rule

`.claude` stops meaning "hover-revealed row control" and starts meaning **this
button opens a Claude session**. All four carry it. The only difference left
between them is a CSS rule about being *inside a row*:

```css
.claude          { opacity: .75; … }   /* a visible orange glyph */
.claude:hover    { opacity: 1; background: rgba(215,119,87,.18); }
.claude:disabled { opacity: .3; background: none; cursor: default; }
.task .claude, .group-header .claude { opacity: 0; }   /* the row variant */
```

Written as a descendant selector rather than baked into `.claude`, because it
is a fact about the row and not about the button.

## Chrome

Both standalone buttons are a 28px square — the control height of everything
beside them — holding the unchanged 16px glyph. No border, no fill. `.primary`
comes off the bar's button; the orange mark among three grey text buttons is
what makes it the point of that bar now.

**The one silent failure.** `.actions button` is a class *and* a type, so it
outranks a bare `.claude` and would keep its pill — the bar's button would draw
as a grey pill with an orange glyph sitting in it, which reads as deliberate.
`.actions button.claude` and `.actions button.claude:hover` win it back.
Measured against the real stylesheet rather than reasoned about:
`border=0px none`, `bg=rgba(0, 0, 0, 0)`, `box=28.0x28.0`, `glyph=16.0x16.0`.

**Size was decided by looking, not by a number.** 16px and 18px were rendered
side by side at 2× against the real stylesheet. The difference is marginal, so
16px wins: one glyph, one size, four buttons that are literally identical.

**Disabled needed its own rule.** `#spin-up` is disabled until a project
exists, and with no label left there is nothing for the browser to grey out.

## One definition of the glyph

`CLAUDE_ICON` stays a single `const` in `ui/tasks.js`. The two markup buttons
are **empty** in `index.html` and are filled beside the line that already wires
their onclick, so the markup holds no second copy of the SVG.

## The guard

- `test_no_claude_button_carries_a_text_label` — both buttons are empty in
  `index.html` and both carry `class="claude"`.
- `test_the_claude_glyph_has_exactly_one_definition` — `CLAUDE_ICON` is defined
  once, `index.html` holds no `<svg>`, and nothing is left unfilled.

Both were mutation-tested: putting the label back fails the first, dropping one
id from the fill loop fails the second.

**What they structurally cannot catch:** whether the glyph is *visible*. The
specificity fight above is not text-searchable, and a future rule added to
`.actions button` re-opens it silently. That half is a render, not a test — this
repo has no JS runner and no browser in the suite by decision.

## Not changed

The ids, both long-form `title` tooltips (now the only label), `handOff`,
`handOffSelection`, `aimedAt`, invariant 31, the delivery watch. No behaviour
moved.

## Width, and a number that did not reproduce

CLAUDE.md pinned the bar at "fits down to 343px with the full label intact". A
1px-step sweep of the real markup gives **326px** for the glyph version — and
**406px** for the old labelled one, not 343. So the recorded figure came from a
different ruler and the two must not be compared. What one ruler does establish
is the direction and the size of it: dropping the label bought ~80px. The check
in CLAUDE.md is now "the bar must still be one row", with the method recorded
beside it.
