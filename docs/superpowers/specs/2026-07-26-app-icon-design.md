# The app wears its own icon — design

**Date:** 2026-07-26
**Status:** approved

## The problem

The tracker's taskbar button and title-bar corner both show the Python logo.
Not a placeholder anybody chose — pywebview's WinForms backend falls back to
`ExtractIconW(sys.executable)` when no icon is given, and the executable is
`pythonw.exe`. Among a row of taskbar buttons the app is indistinguishable from
any other Python process on the machine.

## One file feeds both surfaces

The two places the icon appears are one `HICON` pair on one window:
`ICON_SMALL` is the title-bar corner, `ICON_BIG` is the taskbar button and
Alt+Tab. WinForms' `Form.Icon` sets both, and pywebview already exposes it —
`webview.start(icon=...)`, a real keyword on the real signature
(`webview/__init__.py:179`), read by the winforms backend at
`platforms/winforms.py:243`. So the whole wiring is one argument, and the
interesting part of this work is the artwork and the build.

Not in scope: a notification-area ("system tray") icon. Both screenshots that
prompted this pointed at the taskbar, and a real tray presence — minimise-to-
tray, a context menu, a click target that restores the window — is a feature,
not an icon.

## Building the `.ico` with nothing new installed

This machine has no Pillow and no ImageMagick, and `CLAUDE.md` says another
dependency needs a reason. It does not need one:

- **Chrome is the rasteriser.** `--headless=new --dump-dom` on a harness page
  that draws the SVG into a `<canvas>` at each size and writes the
  `getImageData` bytes out as base64. The measurement comes back as text; no
  window opens and no screenshot has to be interpreted.
- **`struct` is the packer.** An `.ico` is a 6-byte header, a 16-byte directory
  entry per frame, and one 32bpp bottom-up DIB per frame with a 1bpp AND mask.
  About sixty lines.

**The ladder stops at 128, and that is measured rather than chosen.** Packing a
256px frame writes a file `System.Drawing.Icon` still loads, but asking it for
256 hands back 128 — the frame is present and unreachable, and it costs 270KB
of the 374KB file. Capped at 128, every frame round-trips exactly through the
loader pywebview itself will use:

| requested | 16 | 20 | 24 | 32 | 48 | 64 | 128 |
|---|---|---|---|---|---|---|---|
| returned | 16 | 20 | 24 | 32 | 48 | 64 | 128 |

Frames ship at 16, 20, 24, 32, 40, 48, 64 and 128 — the title bar's ladder
(`SM_CXSMICON`: 16 at 100% DPI, 20 at 125%, 24 at 150%, 32 at 200%) and the
taskbar's (32, 40, 48, 64 across the same range), plus 128 as headroom. The
file lands near 110KB and is committed, so `run.bat` gains no step.

## What the artwork has to survive

**The dark taskbar is the primary context.** A near-black chassis disappears
into it — which is why the notepad app sitting beside us in the same taskbar is
pale blue. Candidates therefore lead with a light or saturated body and use the
app's own near-black only as internal detail. The accent is the app's own green
`#4cc38a`, so the icon reads as *this* app rather than as generic stationery.

**16px is a pass/fail, not a hope.** Everything is drawn on a 32-unit grid with
features on even coordinates, so a halving to 16px lands on whole pixels. The
gallery renders true-pixel 16/20/24/32/40/48 for exactly this reason: legibility
at the size the title bar actually draws is the thing least visible in a 128px
preview and least knowable by reasoning about the artwork.

## The ten candidates

Seven attempts at the futuristic-robotic-notepad idea, three from adjacent
directions — the brief said "maybe", so a fifth of the budget goes to trying to
prove the idea wrong.

| # | Name | Idea |
|---|---|---|
| 1 | Visor Pad | The pad's top third is a dark visor with two lit eye-slits; ruled lines below are the body |
| 2 | Spiral Servo | Spiral binding rendered as machined servo joints; ruling drawn as circuit traces with nodes |
| 3 | Chassis Pad | A page clamped inside an exoskeleton frame — corner bolts, a status LED |
| 4 | Terminal Pad | The page *is* a terminal: prompt chevron, a caret block, one scanline |
| 5 | Checkbox Bot | Two checklist boxes as eyes, one ticked; antenna above |
| 6 | Folded Circuit | A dog-eared corner where the fold reveals circuitry beneath the paper |
| 7 | Clipboard Droid | The clip becomes a brow, its grip a sensor bar |
| 8 | Robot Head | No notepad at all — a screen-faced head showing a check |
| 9 | Servo Check | The checkmark as an articulated arm on a visible servo pivot |
| 10 | Stacked Tasks | Three rounded task rows, the top one ticked and lit; straight out of the app's own list |

## The gallery

`tools/icon-gallery.html` — one self-contained file holding all ten as inline
`<symbol>`s, opened by double-click. It is not a mockup of the icons; it renders
the same markup the build rasterises, so what is judged is the artifact.

Each candidate shows a 128px hero, a true-pixel size strip, and the two contexts
faked at real scale: a dark Windows 11 taskbar button with a 24px icon, and a
light title bar with a 16px icon beside the word "Tasks". A row across the top
puts all ten at 16px together, which is the single most decisive view and the
one a per-card layout cannot give.

Opening it is a human gesture, so it is allowed to take focus. Nothing in the
build path opens a window: the rasteriser is headless.

## Two rounds

Round 1 is these ten and a choice — favourites, not necessarily one. Round 2
refines the winner (weight, palette, and a hand-simplified 16px frame if it
needs one; Windows allows different artwork per size) and ships `ui/icon.ico`
plus the one-line wiring.

Rejected candidates stay in the gallery rather than being deleted, so reopening
one to see whether it *could* work costs nothing.

## What drawing them changed

Three candidates were revised before anyone was asked to look, because
rendering them said what the markup could not.

Slot 9 was a prompt caret beside a checkmark and went through two versions
that both read as a single zigzag — two angular strokes at similar heights
merge into one mark, and separating them further did not help. It is now one
mark: the check drawn as an articulated arm on a servo pivot. **Chassis Pad**'s
frame was dark enough to swallow its own page at 16px and was lightened;
**Stacked Tasks**' pale rows dissolved into a white title bar and gained an
outline, taking it from the worst light-backdrop contrast of the ten to
mid-field.

None of that was visible in the contrast measurement, which passed all ten both
times. A number says something is there; it cannot say it reads as a robotic
notepad. Both checks were needed and neither substitutes for the other.

## Files

| Path | Role |
|---|---|
| `tools/icon-gallery.html` | the ten candidates, and the demo that judges them |
| `tools/build_icon.py` | `ui/icon.svg` → `ui/icon.ico`, via headless Chrome and `struct` |
| `ui/icon.svg` | the winner, source of truth (round 2) |
| `ui/icon.ico` | committed build output (round 2) |
| `app.py` | `webview.start(icon=...)` — one line (round 2) |
