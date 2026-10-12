"""MAP DATA screen place labels (秋原町 / 科学省 / オラン島 / エンドシティ).

A sprite file, LZ (Colonel 0x6F7A08, two 0x88-flagged references), decompressed:
  0x00  u32 size<<8
  0x04  offsets (rel. 4): 0x04 header, 0x18 tiles, 0x4DC palette, 0x560 frames, 0x58C OAM lists
  0x20  u32 tile bytes (0x4C0 = 38 tiles) ; 0x24 tiles (all 38 go to OBJ VRAM 48..85 at once,
        86+ belong to other sprites, so the budget is 38 tiles)
  0x590 ... OAM lists: u32 offsets (rel. 0x594) of four lists, each a run of 5-byte entries
        (tile, x, y, size, shape) closed by ff ff ff ff ff.
Ink colour 1, outline 2, transparent 0.  Original frames: 秋原町 32x16 (tiles 0-7),
科学省 32x16 (8-15), オラン島 32x16+8x16 (16-25), エンドシティ 8x16+32x16+8x16 (26-37).
New frames (centred like the source): 아키하라 32x16+8x16, 과학성 32x16, 오란섬 32x16,
엔드시티 32x16+8x16 = 36 tiles; Galmuri9 set by ink width + 1 clear column, shaded right/below in colour 2 (a full
outline makes the four-syllable labels 41 px, one over their 40).
The OAM block is rebuilt (its offset table rewritten); the size word is updated.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pet_labels
from lz77 import compress, lz77_decompress
from sort_labels import find_lz

FONT9 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri9.bdf"
COLONEL_AT = 0x6F7A08
INK, LINE = 1, 2
# (text, [(width, x)]) -- each piece is 32x16 (shape 1, size 2) or 8x16 (shape 2, size 0)
LABELS = [("아키하라", [(32, -20), (8, 12)]), ("과학성", [(32, -16)]),
          ("오란섬", [(32, -16)]), ("엔드시티", [(32, -20), (8, 12)])]
SHAPE = {32: (2, 1), 8: (0, 2)}           # width -> (size, shape) for 16-px-tall pieces


def draw(f, text: str, width: int):
    px, pen = set(), 0
    for ch in text:
        dw, ink = f[ch]
        lo = min(x for x, _ in ink)
        px |= {(pen + x - lo, y) for x, y in ink}
        pen += max(x for x, _ in ink) - lo + 2      # ink width + one clear column
    x0, y0 = min(x for x, _ in px), min(y for _, y in px)
    px = {(x - x0, y - y0) for x, y in px}
    w, h = max(x for x, _ in px) + 2, max(y for _, y in px) + 2
    if w > width or h > 16:
        raise ValueError("map label %r is %dx%d, room %dx16" % (text, w, h, width))
    left, top = (width - w) // 2, (16 - h) // 2
    img = {}
    for x, y in px:                      # shade right, below and diagonal
        for dx, dy in ((1, 0), (0, 1), (1, 1)):
            img[(left + x + dx, top + y + dy)] = LINE
    for x, y in px:
        img[(left + x, top + y)] = INK
    return img


def build(rom: bytearray, append, write, colonel: bytes) -> dict:
    D = lz77_decompress(colonel, COLONEL_AT)[0]
    at, refs = find_lz(bytes(rom), D)
    if len(refs) != 2:
        raise ValueError("map label sprite reference count changed: %d" % len(refs))
    d = bytearray(D)
    if struct.unpack_from("<I", d, 0x20)[0] != 0x4C0 or struct.unpack_from("<I", d, 0x18)[0] != 0x58C:
        raise ValueError("map label sprite layout differs")
    saved = pet_labels.FONT
    pet_labels.FONT = FONT9
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    tiles = [bytes(32)] * 38
    lists, t = [], 0
    for text, pieces in LABELS:
        width = sum(w for w, _ in pieces)
        img = draw(f, text, width)
        entries, ox = b"", 0
        for w, x in pieces:
            size, shape = SHAPE[w]
            entries += bytes([t, x & 0xFF, 0xF8, size, shape])
            for ty in range(2):
                for tx in range(w // 8):
                    cell = bytearray(32)
                    for yy in range(8):
                        for xx in range(8):
                            c = img.get((ox + tx * 8 + xx, ty * 8 + yy), 0)
                            cell[yy * 4 + xx // 2] |= c << (4 * (xx & 1))
                    tiles[t] = bytes(cell)
                    t += 1
            ox += w
        lists.append(entries + b"\xff" * 5)
    if t > 38:
        raise ValueError("map labels need %d tiles, 38 available" % t)
    d[0x24:0x24 + 38 * 32] = b"".join(tiles)
    base = 0x594                                # list offsets are relative to here
    if struct.unpack_from("<I", d, base)[0] != 0x10:
        raise ValueError("map label OAM table differs")
    body, offs, pos = b"", [], 0x10
    for l in lists:
        offs.append(pos)
        body += l
        pos += len(l)
    d = d[:base] + struct.pack("<4I", *offs) + body
    struct.pack_into("<I", d, 0, len(d) << 8)
    new = append(compress(bytes(d)), "MAP DATA place labels sprite (LZ)")
    for r in refs:
        write(r, struct.pack("<I", 0x88000000 | new), "MAP DATA label sprite reference",
              struct.pack("<I", 0x88000000 | at))
    return {"at": new, "tiles": t}


# ---------------------------------------------------------------- hint line
# "L・Rボタン：せつめい" under the map: BG1 row 18, VRAM tiles 0x158..0x161
# (each used once, palette 8, ink 1 on 2), from the map's LZ tile blob
# (Colonel 0x6F2648, Blues 0x6F11B4 -- 65 bytes differ elsewhere; VRAM tile t =
# blob tile t-2).  Redrawn as "L·R 버튼: 설명" in Galmuri7 from x=4, rows 1..7.
FONT7 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri7.bdf"
HINT_TILES = range(0x158 - 2, 0x162 - 2)        # blob tile numbers
HINT_TEXT = "L·R 버튼: 설명"


def build_hint(rom: bytearray, append, write, colonel: bytes) -> dict:
    D = lz77_decompress(colonel, 0x6F2648)[0]
    part = slice(4 + HINT_TILES[0] * 32, 4 + (HINT_TILES[-1] + 1) * 32)
    at, refs = find_lz(bytes(rom), D, part)
    d = bytearray(lz77_decompress(bytes(rom), at)[0])
    saved = pet_labels.FONT
    pet_labels.FONT = FONT7
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    px = pet_labels.text_pixels(f, HINT_TEXT)
    if max(x for x, _ in px) + 4 >= len(HINT_TILES) * 8 or max(y for _, y in px) > 6:
        raise ValueError("map hint does not fit")
    for k, t in enumerate(HINT_TILES):
        cell = bytearray(32)
        for y in range(8):
            for x in range(8):
                c = 1 if (k * 8 + x - 4, y - 1) in px else 2
                cell[y * 4 + x // 2] |= c << (4 * (x & 1))
        d[4 + t * 32:4 + t * 32 + 32] = cell
    new = append(compress(bytes(d)), "MAP DATA tiles with Hangul hint line (LZ)")
    for r in refs:
        write(r, struct.pack("<I", 0x88000000 | new), "MAP DATA tiles reference",
              struct.pack("<I", 0x88000000 | at))
    return {"at": new, "refs": len(refs)}
