"""Turn ui/icon.svg into ui/icon.ico — the file both taskbar and title bar draw.

    & ".venv\\Scripts\\python.exe" tools\\build_icon.py

No new dependency does this. This machine has neither Pillow nor ImageMagick,
and CLAUDE.md says another dependency needs a reason — it does not need one:

- **Chrome is the rasteriser.** A generated harness page draws the SVG into a
  <canvas> at each size and writes the getImageData bytes out as base64;
  `--headless=new --dump-dom` brings them back as text. Nothing opens on screen,
  which is the rule for anything that is not a hand-off.
- **struct is the packer.** An .ico is a 6-byte header, a 16-byte directory
  entry per frame, and one bottom-up 32bpp DIB per frame with a 1bpp AND mask.

SIZES stops at 128 deliberately. A 256px frame packs into a file
System.Drawing.Icon still loads, but asking that loader for 256 hands back 128
— the frame is present, unreachable, and costs 270KB of a 374KB file. Measured
2026-07-26 against the loader pywebview's winforms backend itself uses.
"""
from __future__ import annotations

import base64
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SOURCE = REPO / "ui" / "icon.svg"
TARGET = REPO / "ui" / "icon.ico"

# The title bar's ladder (SM_CXSMICON: 16 at 100% DPI, 20 at 125%, 24 at 150%,
# 32 at 200%) and the taskbar's (32, 40, 48, 64 across the same range), plus 128
# as headroom for Alt+Tab and Explorer's larger views.
SIZES = (16, 20, 24, 32, 40, 48, 64, 128)

CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")

_HARNESS = """<meta charset="utf-8">
<pre id="out">EMPTY</pre>
<script>
const SIZES = %s;
const SOURCE = "%s";

function rasterise(image, size) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const brush = canvas.getContext('2d');
  brush.clearRect(0, 0, size, size);
  brush.drawImage(image, 0, 0, size, size);
  const pixels = brush.getImageData(0, 0, size, size).data;
  let binary = '';
  for (let index = 0; index < pixels.length; index += 1) {
    binary += String.fromCharCode(pixels[index]);
  }
  return btoa(binary);
}

const image = new Image();
image.onload = () => {
  document.getElementById('out').textContent =
    SIZES.map(size => size + ':' + rasterise(image, size)).join('\\n');
};
image.onerror = () => { document.getElementById('out').textContent = 'IMAGE_LOAD_FAILED'; };
image.src = 'data:image/svg+xml;base64,' + SOURCE;
</script>
"""


def rasterise(svg: str, sizes=SIZES) -> dict[int, bytes]:
    """{size: raw top-down RGBA} for this SVG, rendered by headless Chrome.

    The harness carries the SVG as a base64 data URL rather than as markup, so
    nothing in the artwork — a quote, a `</script>`, a stray backslash — can
    break out of the page that measures it.
    """
    if not CHROME.is_file():
        raise SystemExit(f"Chrome is the rasteriser and it is not at {CHROME}")

    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    page = _HARNESS % (list(sizes), encoded)

    with tempfile.TemporaryDirectory() as scratch:
        harness = Path(scratch) / "harness.html"
        harness.write_text(page, encoding="utf-8", newline="\n")
        finished = subprocess.run(
            [str(CHROME), "--headless=new", "--disable-gpu", "--no-first-run",
             f"--user-data-dir={Path(scratch) / 'profile'}",
             "--virtual-time-budget=8000", "--dump-dom", harness.as_uri()],
            capture_output=True, text=True,
            # Nothing this app runs for its own purposes may put a window on
            # screen. --headless=new is the guarantee; this is the belt.
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    if finished.returncode != 0:
        raise SystemExit(f"chrome failed ({finished.returncode}):\n{finished.stderr}")

    frames = frames_from_dump(finished.stdout)
    missing = set(sizes) - set(frames)
    if missing:
        raise SystemExit(f"chrome returned no pixels for {sorted(missing)}")
    return frames


def frames_from_dump(dump: str) -> dict[int, bytes]:
    """{size: raw RGBA} out of one --dump-dom, or a SystemExit naming the fault.

    Every sentinel is read out of the OUTPUT ELEMENT and never out of the whole
    dump. --dump-dom echoes the <script> source back verbatim, so the literal
    "IMAGE_LOAD_FAILED" is present in stdout on a perfectly successful run —
    `if "IMAGE_LOAD_FAILED" in stdout` is a check that can only ever fail, which
    is exactly what it did on the first real call. Split out of rasterise() so a
    test can feed it a realistic dump without launching a browser.
    """
    body = re.search(r'<pre id="out">(.*?)</pre>', dump, re.DOTALL)
    if body is None:
        raise SystemExit("the harness page produced no output element at all")
    result = body.group(1).strip()
    if result == "IMAGE_LOAD_FAILED":
        raise SystemExit("the SVG did not render — is it valid standalone markup?")
    if result == "EMPTY":
        raise SystemExit("the harness script never ran — see --virtual-time-budget")

    frames = {}
    for line in result.splitlines():
        size, payload = line.split(":", 1)
        frames[int(size)] = base64.b64decode(payload)
    return frames


def _dib(rgba: bytes, size: int) -> bytes:
    """One frame as a bottom-up 32bpp DIB followed by its 1bpp AND mask.

    Canvas hands back top-down RGBA; a DIB wants bottom-up BGRA, hence both
    reversals. The mask is redundant on anything since Vista, which reads the
    alpha channel — but it is part of the format, and a Windows that falls back
    to it should get transparency rather than a black box.
    """
    xor = bytearray()
    for row in range(size - 1, -1, -1):
        for column in range(size):
            start = (row * size + column) * 4
            red, green, blue, alpha = rgba[start:start + 4]
            xor += bytes((blue, green, red, alpha))

    stride = ((size + 31) // 32) * 4
    mask = bytearray()
    for row in range(size - 1, -1, -1):
        bits = bytearray(stride)
        for column in range(size):
            if rgba[(row * size + column) * 4 + 3] == 0:
                bits[column // 8] |= 0x80 >> (column % 8)
        mask += bits

    header = struct.pack("<IiiHHIIiiII", 40, size, size * 2, 1, 32, 0,
                         len(xor) + len(mask), 0, 0, 0, 0)
    return header + bytes(xor) + bytes(mask)


def pack_ico(frames: dict[int, bytes]) -> bytes:
    """Every frame in one .ico, smallest first."""
    images = []
    for size in sorted(frames):
        if not 0 < size < 256:
            raise ValueError(f"{size}px cannot be addressed by an .ico directory entry")
        if len(frames[size]) != size * size * 4:
            raise ValueError(f"the {size}px frame is not {size}x{size} RGBA")
        images.append((size, _dib(frames[size], size)))

    offset = 6 + 16 * len(images)
    directory = b""
    for size, blob in images:
        # colour count 0, one plane, 32bpp — the modern-icon spelling.
        directory += struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32,
                                 len(blob), offset)
        offset += len(blob)
    return (struct.pack("<HHH", 0, 1, len(images)) + directory
            + b"".join(blob for _, blob in images))


def main() -> int:
    if not SOURCE.is_file():
        print(f"no artwork at {SOURCE.relative_to(REPO)} — pick a candidate from "
              f"tools/icon-gallery.html first", file=sys.stderr)
        return 1

    frames = rasterise(SOURCE.read_text(encoding="utf-8"))
    TARGET.write_bytes(pack_ico(frames))
    print(f"{TARGET.relative_to(REPO)}: {len(SIZES)} frames "
          f"({', '.join(str(size) for size in SIZES)}), "
          f"{TARGET.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
