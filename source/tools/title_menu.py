"""Title menu はじめから / つづきから redrawn as 처음부터 / 이어하기.

Measured on the title screen (runtime/title_snap2, Blues): the two items are
OBJs, 1D-mapped, each a row of 32x16 + 32x16 + 16x16 sprites (80x16):
はじめから tiles 35..54, つづきから tiles 55..74 (palettes 3 / 2, the game
swaps them for the selection).  Ink colour 1, shadow 4, transparent 0, ink
rows 2..13 from x=0.  The tiles come from LZ 0x7F936C (decompressed: 4-byte
head + OBJ tiles from VRAM tile 1), referenced with the 0x88 compressed flag.
The Hangul is Galmuri11 drawn bold (one extra column), shadow 4 right, below
and diagonal; the blob is recompressed to the ROM end and repointed.
"""
from __future__ import annotations

import struct
from pathlib import Path

import pet_labels
from lz77 import compress, lz77_decompress
from sort_labels import find_lz

FONT11 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri11.bdf"
BLUES_AT = 0x7F936C
ITEMS = [("처음부터", 35), ("이어하기", 55)]
PARTS = [(0, 32), (32, 32), (64, 16)]          # x offset, width of the three sprites
INK, SHADOW = 1, 4


def sprite_cell(first: int, x: int, y: int) -> tuple[int, int, int]:
    """(tile, local x, local y) of pixel (x, y) in an 80x16 item."""
    t = first
    for ox, w in PARTS:
        if ox <= x < ox + w:
            lx = x - ox
            return t + (y // 8) * (w // 8) + lx // 8, lx % 8, y % 8
        t += (w // 8) * 2
    raise ValueError("pixel outside the item")


def build(rom: bytearray, append, write, blues: bytes) -> dict:
    D = lz77_decompress(blues, BLUES_AT)[0]
    part = slice(4 + 34 * 32, 4 + 74 * 32)        # VRAM tile n = blob tile n-1
    at, refs = find_lz(bytes(rom), D, part)
    out = bytearray(lz77_decompress(bytes(rom), at)[0])
    saved = pet_labels.FONT
    pet_labels.FONT = FONT11
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    for text, first in ITEMS:
        ink = set()
        for x, y in pet_labels.text_pixels(f, text):
            ink |= {(x, y + 2), (x + 1, y + 2)}
        img = {}
        for x, y in ink:
            for dx, dy in ((1, 0), (0, 1), (1, 1)):
                img[(x + dx, y + dy)] = SHADOW
        for p in ink:
            img[p] = INK
        if max(x for x, _ in img) >= 80 or max(y for _, y in img) >= 16:
            raise ValueError("title item %r too large" % text)
        for y in range(16):
            for x in range(80):
                t, lx, ly = sprite_cell(first, x, y)
                i = 4 + (t - 1) * 32 + ly * 4 + lx // 2
                sh = 4 * (lx & 1)
                out[i] = (out[i] & ~(15 << sh) & 0xFF) | (img.get((x, y), 0) << sh)
    new = append(compress(bytes(out)), "title OBJ tiles with Hangul menu (LZ)")
    for r in refs:
        write(r, struct.pack("<I", 0x88000000 | new), "title OBJ tiles reference",
              struct.pack("<I", 0x88000000 | at))
    return {"at": new, "refs": len(refs)}
