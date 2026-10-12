"""Title logo subtitle チーム・オブ・ブルース / カーネル -> 팀 오브 블루스 / 커널.

The logo is BG1 of the title screen, 8bpp (BGxCNT bit 7): tiles LZ (Blues
0x7FA23C, 4-byte head + 64-byte tiles), map raw u16 (Blues 0x7FE034).  Only
the subtitle changes; the big ロックマンエグゼ5 stays (user decision).

  1. Mask: inside each subtitle box, pixels of the letters' colour family
     (yellow/orange for チーム オブ, red + white rim for ブルース) and the black
     outline pixels within 2 px of them.
  2. Fill: each masked pixel takes the nearest unmasked pixel at an even
     (dx, dy) offset, so the 2-px purple grid of the emblem keeps its phase.
  3. Draw: Hangul in S-Core Dream 9, sheared like the original italics, black
     outline; 팀 오브 in a yellow->orange vertical ramp, 블루스/커널 in a red ramp
     with a white inner rim -- every colour an index already in the logo
     palette, so the palette is untouched.
  4. Re-tile: changed 8x8 cells get new tiles appended to the tile set (a cell
     whose tile is shared elsewhere in the map is never edited in place);
     tiles and map are rewritten (tiles recompressed) and repointed.
"""
from __future__ import annotations

import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = Path(__file__).resolve().parents[4] / "폰트/S-Core_Dream_OTF/SCDream9.otf"
BLACK, WHITE = 206, 108
YELLOW_RAMP = [118, 121, 133, 151, 161, 162]
RED_RAMP = [5, 196, 210, 197]
FAMILIES = None          # version style: {family letter: set of palette indices}

# The two versions number their logo palettes differently (Colonel: black 205,
# white 78, blue letters on a blue background), so the letter colours are
# listed per version instead of guessed from RGB.
STYLES = {
    "blues": {"black": 206, "white": 108, "small": [118, 121, 133, 151, 161, 162], "big": [5, 196, 210, 197],
              "families": None},
    "colonel": {"black": 205, "white": 78, "small": [72, 74, 71, 69, 67, 66, 64], "big": [75, 71, 66, 59, 47, 42],
                "families": {"C": {43, 47, 59, 64, 66, 67, 68, 69, 71, 72, 74, 75, 58, 78},
                             "B": {37, 41, 42, 43, 47, 58, 59, 64, 66, 67, 68, 69, 71, 72, 74, 75, 78}}},
}


def set_style(version: str) -> None:
    global BLACK, WHITE, YELLOW_RAMP, RED_RAMP, FAMILIES
    st = STYLES[version]
    BLACK, WHITE, YELLOW_RAMP, RED_RAMP, FAMILIES = st["black"], st["white"], st["small"], st["big"], st["families"]


def text_mask(text: str, size: int, shear: float, pad: int = 2) -> set[tuple[int, int]]:
    font = ImageFont.truetype(str(FONT), size)
    l, t, r, b = font.getbbox(text)
    w, h = r - l + pad * 2 + int(abs(shear) * (b - t)) + 2, b - t + pad * 2
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((pad - l, pad - t), text, font=font, fill=255)
    px = set()
    for y in range(h):
        off = int(round(shear * (h - 1 - y)))
        for x in range(w):
            if im.getpixel((x, y)) >= 128:
                px.add((x + off, y))
    y0 = min(y for _, y in px)
    x0 = min(x for x, _ in px)
    return {(x - x0, y - y0) for x, y in px}


def outline(px: set, r: int) -> set:
    out = set()
    for x, y in px:
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if abs(dx) + abs(dy) <= r + (1 if r > 1 else 0):
                    out.add((x + dx, y + dy))
    return out - px


def compose(idx, pal, boxes, words):
    """idx: 160 rows of 240 indices (the logo layer).  boxes: list of
    (x0, y0, x1, y1, family) to erase.  words: list of (text, size, shear,
    x, y, style).  Returns the new index image."""
    def fam(i):
        if FAMILIES is not None:
            return "".join(k for k, v in FAMILIES.items() if i in v) or None
        r, g, b = pal[i]
        if r > 200 and g > 100 and b < 160:
            return "Y"
        if r > 150 and g < 60 and b < 80:
            return "R"
        if r > 230 and g > 230 and b > 230:
            return "W"
        return None
    img = [row[:] for row in idx]
    mask = set()
    for x0, y0, x1, y1, family in boxes:
        core = {(x, y) for y in range(y0, y1) for x in range(x0, x1)
                if any(c in family for c in (fam(idx[y][x]) or "-"))}
        near = {(x + dx, y + dy) for x, y in core for dx in range(-2, 3) for dy in range(-2, 3)}
        mask |= core | {(x, y) for x, y in near if x0 <= x < x1 and y0 <= y < y1 and idx[y][x] == BLACK}
    for x, y in mask:
        best = None
        for d in range(2, 40, 2):
            for dy in range(-d, d + 1, 2):
                for dx in range(-d, d + 1, 2):
                    if max(abs(dx), abs(dy)) != d:
                        continue
                    q = (x + dx, y + dy)
                    if 0 <= q[0] < 240 and 0 <= q[1] < 160 and q not in mask:
                        best = q
                        break
                if best:
                    break
            if best:
                break
        if best:
            img[y][x] = idx[best[1]][best[0]]
    for text, size, shear, ox, oy, style in words:
        px = text_mask(text, size, shear)
        h = max(y for _, y in px) + 1
        ramp = YELLOW_RAMP if style == "yellow" else RED_RAMP
        o2 = outline(px, 2 if style == "red" else 1)
        for x, y in o2:
            img[oy + y][ox + x] = BLACK
        if style == "red":
            for x, y in outline(px, 1):
                img[oy + y][ox + x] = WHITE
        for x, y in px:
            img[oy + y][ox + x] = ramp[min(len(ramp) - 1, y * len(ramp) // h)]
    return img, mask


def plate_pixels(x0, y0, x1, y1, shear):
    """Parallelogram leaning right like the logo's italics (top shifted right)."""
    out = set()
    for y in range(y0, y1):
        off = int(round(shear * (y1 - 1 - y)))
        for x in range(x0 + off, x1 + off):
            out.add((x, y))
    return out


def compose_plate(idx, pal, boxes, plates, words):
    """Variant without background guessing: the erased letters lie under black
    sheared plates (border colour per plate); the Hangul goes on the plates.
    Mask pixels a plate does not cover still get the even-offset fill."""
    covered = set()
    for x0, y0, x1, y1, shear, border in plates:
        covered |= plate_pixels(x0, y0, x1, y1, shear)
    img, mask = compose(idx, pal, boxes, [])
    left = mask - covered
    for x0, y0, x1, y1, shear, border in plates:
        p = plate_pixels(x0, y0, x1, y1, shear)
        edge = {q for q in p if any((q[0] + dx, q[1] + dy) not in p for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))}
        for x, y in p:
            img[y][x] = border if (x, y) in edge else BLACK
    img2, _ = compose(img, pal, [], words)
    return img2, mask, left


# Per version: where the logo lives and how the subtitle is redrawn.
LOGO = {
    "blues": {"tiles_ref": 0x307E0, "map_lit": 0x30828,
              "boxes": [(18, 69, 118, 91, "Y"), (84, 72, 176, 114, "RW")],
              "plates": [(17, 68, 113, 92, 0.25, BLACK), (80, 71, 174, 115, 0.25, BLACK)],
              "words": [("팀", 22, 0.25, 24, 69, "yellow"), ("오브", 18, 0.25, 54, 72, "yellow"),
                        ("블루스", 30, 0.25, 102, 78, "red")]},
    "colonel": {"tiles_ref": 0x307E4, "map_lit": 0x3082C,
                "boxes": [(18, 69, 118, 91, "C"), (84, 68, 186, 106, "B")],
                "plates": [(17, 68, 113, 92, 0.25, 205), (80, 67, 184, 107, 0.25, 205)],
                "words": [("팀", 22, 0.25, 24, 69, "yellow"), ("오브", 18, 0.25, 54, 72, "yellow"),
                          ("커널", 34, 0.25, 104, 70, "red")]},
}
FREE_TILES = 30          # VRAM tiles 482..511 are empty on the title screen (checked)


def build(rom: bytearray, append, write, version: str, pal: list) -> dict:
    """pal: the title's 256 BG colours (RGB), only used to classify letters."""
    from lz77 import compress, lz77_decompress
    cfg = LOGO[version]
    set_style(version)
    tref = struct.unpack_from("<I", rom, cfg["tiles_ref"])[0]
    if tref >> 24 != 0x88:
        raise ValueError("logo tiles reference is not a compressed entry")
    t_at = tref & 0xFFFFFF
    D = bytearray(lz77_decompress(bytes(rom), t_at)[0])
    if struct.unpack_from("<I", D, 0)[0] >> 8 != len(D):
        raise ValueError("logo tile blob head differs")
    m_at = struct.unpack_from("<I", rom, cfg["map_lit"])[0] - 0x08000000
    M = list(struct.unpack_from("<640H", rom, m_at))
    if any(e & 0xFC00 for e in M):
        raise ValueError("logo map uses flips/palette bits")
    n_tiles = (len(D) - 4) // 64
    idx = [[D[4 + (M[(y // 8) * 32 + x // 8]) * 64 + (y % 8) * 8 + x % 8] for x in range(240)] for y in range(160)]
    img, mask, left = compose_plate(idx, pal, cfg["boxes"], cfg["plates"], cfg["words"])
    if left:
        raise ValueError("%d erased pixels outside the plates" % len(left))
    uses = {}
    for e in M:
        uses[e] = uses.get(e, 0) + 1
    extra = []
    for ty in range(20):
        for tx in range(30):
            cell = bytes(img[ty * 8 + y][tx * 8 + x] for y in range(8) for x in range(8))
            t = M[ty * 32 + tx]
            if cell == bytes(D[4 + t * 64:4 + t * 64 + 64]):
                continue
            if uses[t] == 1:
                D[4 + t * 64:4 + t * 64 + 64] = cell
            else:
                extra.append(cell)
                M[ty * 32 + tx] = n_tiles + len(extra) - 1
    if len(extra) > FREE_TILES:
        raise ValueError("logo needs %d new tiles, %d free" % (len(extra), FREE_TILES))
    D += b"".join(extra)
    struct.pack_into("<I", D, 0, len(D) << 8)
    new_t = append(compress(bytes(D)), "title logo tiles with Hangul subtitle (LZ)")
    write(cfg["tiles_ref"], struct.pack("<I", 0x88000000 | new_t), "title logo tiles reference",
          struct.pack("<I", tref))
    write(m_at, struct.pack("<640H", *M), "title logo map (subtitle cells)", bytes(rom[m_at:m_at + 1280]))
    return {"tiles": new_t, "new_tiles": len(extra)}
