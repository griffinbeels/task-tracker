"""The icon build: reading Chrome's dump, and packing the .ico.

Neither test launches a browser. The rasteriser is Chrome and testing that
would only assert that Chrome draws, at a second per run on a suite that runs
constantly — what is worth pinning is the two places this code can be wrong
about a dump it is handed, and the byte layout it writes.
"""
import base64
import hashlib
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import build_icon  # noqa: E402


def _dump(output: str) -> str:
    """A --dump-dom as Chrome really returns it: the script source comes back.

    This is the whole point of the first test below. Every sentinel the harness
    can print is a string literal *inside* that echoed source, so a check
    written against the dump rather than against the output element matches on
    a completely successful run.
    """
    return (
        '<html><head><meta charset="utf-8">\n</head><body>'
        f'<pre id="out">{output}</pre>\n'
        "<script>\n"
        "const image = new Image();\n"
        "image.onerror = () => { document.getElementById('out').textContent = "
        "'IMAGE_LOAD_FAILED'; };\n"
        "</script></body></html>"
    )


def test_a_successful_dump_is_not_read_as_a_failure():
    """The sentinel appears in every dump. Only the output element counts.

    Shipped as a bug: `if "IMAGE_LOAD_FAILED" in stdout` matched the harness's
    own source, so the tool reported "the SVG did not render" for artwork that
    had rendered perfectly. It could never have succeeded once.
    """
    pixels = bytes(range(16)) * 16  # 2x2 RGBA is 16 bytes; any blob will do
    encoded = base64.b64encode(pixels).decode("ascii")

    frames = build_icon.frames_from_dump(_dump(f"2:{encoded}"))

    assert frames == {2: pixels}


def test_a_real_render_failure_is_still_reported():
    """The other half — narrowing the check must not blind it."""
    with pytest.raises(SystemExit, match="did not render"):
        build_icon.frames_from_dump(_dump("IMAGE_LOAD_FAILED"))

    with pytest.raises(SystemExit, match="never ran"):
        build_icon.frames_from_dump(_dump("EMPTY"))


def test_the_ico_directory_describes_the_frames_that_follow_it():
    """Every entry's offset and length must land on its own image.

    A wrong offset produces a file Windows opens and draws as garbage rather
    than one it rejects, so this is checked by walking the directory the way a
    reader does instead of by comparing against a golden file.
    """
    sizes = (16, 32)
    frames = {size: bytes([9, 40, 90, 255]) * (size * size) for size in sizes}

    blob = build_icon.pack_ico(frames)

    reserved, kind, count = struct.unpack_from("<HHH", blob, 0)
    assert (reserved, kind) == (0, 1), "an .ico is type 1 with a zero reserved field"
    assert count == len(sizes)

    for index, size in enumerate(sizes):
        (width, height, colours, pad, planes, depth, length,
         offset) = struct.unpack_from("<BBBBHHII", blob, 6 + 16 * index)
        assert (width, height) == (size, size)
        assert (colours, pad, planes, depth) == (0, 0, 1, 32)
        assert offset + length <= len(blob), "the entry points past the file"

        header = struct.unpack_from("<Iii", blob, offset)
        assert header == (40, size, size * 2), (
            "a BITMAPINFOHEADER whose height is not twice its width has lost "
            "the AND mask the format still expects")

    packed = sum(struct.unpack_from("<I", blob, 6 + 16 * index + 8)[0]
                 for index in range(count))
    assert len(blob) == 6 + 16 * count + packed, "trailing or missing image bytes"


def test_a_frame_that_is_not_square_rgba_is_refused():
    """Silently packing a short frame writes an .ico that draws as noise."""
    with pytest.raises(ValueError, match="not 16x16 RGBA"):
        build_icon.pack_ico({16: b"\x00" * 4})


def test_the_committed_icon_was_built_from_the_committed_artwork():
    """A stale .ico is silent — nothing in it says which SVG produced it.

    The way this goes wrong is now a workflow the repo invites: copy an
    alternate from ui/icon-alternates/ over ui/icon.svg, commit, and ship an
    icon that is not the artwork in the tree. build_icon.py records the source
    hash so that mistake fails here instead of on someone's taskbar.
    """
    stamp = json.loads(build_icon.STAMP.read_text(encoding="utf-8"))
    actual = hashlib.sha256(build_icon.SOURCE.read_bytes()).hexdigest()

    assert actual == stamp["sha256"], (
        f"{build_icon.SOURCE.name} has changed since {build_icon.TARGET.name} "
        f"was built — run: python tools/build_icon.py")
    assert stamp["sizes"] == list(build_icon.SIZES)

    count = struct.unpack_from("<H", build_icon.TARGET.read_bytes(), 4)[0]
    assert count == len(build_icon.SIZES), "the .ico holds a different frame count"


@pytest.mark.parametrize("artwork", sorted(
    [build_icon.SOURCE] + list((build_icon.REPO / "ui" / "icon-alternates").glob("*.svg"))))
def test_every_shipped_svg_stands_alone(artwork):
    """A <use> is how one of these silently becomes a blank icon.

    The gallery draws each candidate from a <symbol>, and lifting one out with
    a <use> still in it produces markup that renders as nothing at all — a
    missing reference is not an error, so the rasteriser succeeds, the .ico
    packs, and the taskbar shows an empty square. Every file here must carry
    its own geometry.
    """
    markup = artwork.read_text(encoding="utf-8")

    assert "<use" not in markup, (
        f"{artwork.name} references something outside itself and will render blank")
    assert markup.count("<svg") == 1 and "</svg>" in markup
    assert 'viewBox="0 0 32 32"' in markup, "the 32-unit grid is what keeps 16px on whole pixels"


def test_the_size_ladder_stays_addressable():
    """256 does not fit a directory entry, and the loader cannot reach it.

    Measured 2026-07-26: with a 256px frame packed, System.Drawing.Icon — the
    loader pywebview's winforms backend uses — answers a request for 256 with
    the 128px frame, so the entry is present, unreachable, and 270KB of a
    374KB file. The cap is a measurement, so a future edit that raises it
    should have to change this line and read why.
    """
    assert max(build_icon.SIZES) == 128
    assert all(0 < size < 256 for size in build_icon.SIZES)
