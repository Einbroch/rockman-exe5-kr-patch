"""Small tab headers of the Rockman status screen (ロック バスター, フォルダ, プログラム).

They are tiles of the shared PET BG tile blob, LZ 0x6FCABC (decompressed:
4-byte size head + tiles 1..447 for BG2 charblock 0), loaded by 16 graphics
lists (0x88 compressed flag).  Each header is one tile row: row 0 is the tab
border (a), rows 1..7 background b, kana in colour 1 on rows 2..6.
  ロック バスター  tiles 0xFD..0x102 (48 px)
  フォルダ        tiles 0x106..0x109 (32 px)
  プログラム      tiles 0x10A..0x10D (32 px)
The Hangul goes in the same tiles (Galmuri7, colour 1, rows 1..7, from x=1;
dakuten ink left in border row 0 goes back to a).  ロック バスター reads
버스터: at 7 px 록 (ㄹ over ㅗ over ㄱ) reads as 족;
the blob is recompressed to the ROM end and every reference repointed.
Colonel's blob differs in 8 bytes outside the headers (located by the header tiles).
"""
from __future__ import annotations

import struct
from pathlib import Path

import pet_labels
from lz77 import compress, lz77_decompress
from sort_labels import find_lz

FONT7 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri7.bdf"
BLUES_AT = 0x6FCABC
TABS = [("버스터", 0xFD, 6), ("폴더", 0x106, 4), ("프로그램", 0x10A, 4)]
BG, INK, BORDER = 0xB, 0x1, 0xA


def build(rom: bytearray, append, write, blues: bytes) -> dict:
    D = lz77_decompress(blues, BLUES_AT)[0]
    # Colonel's blob differs in 8 bytes elsewhere: match the header tiles only
    # and edit that version's own data.
    at, refs = find_lz(bytes(rom), D, slice(4 + (0xFD - 1) * 32, 4 + 0x10E * 32))
    out = bytearray(lz77_decompress(bytes(rom), at)[0])
    saved = pet_labels.FONT
    pet_labels.FONT = FONT7
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    for text, first, count in TABS:
        px = pet_labels.text_pixels(f, text)
        if max(x for x, _ in px) + 1 >= count * 8 or max(y for _, y in px) > 6:
            raise ValueError("tab %r does not fit" % text)
        for k in range(count):
            o = 4 + (first + k - 1) * 32
            for x in range(8):                    # kana dakuten reach into the border row
                i, sh = o + x // 2, 4 * (x & 1)
                if (out[i] >> sh) & 15 == INK:
                    out[i] = (out[i] & ~(15 << sh) & 0xFF) | (BORDER << sh)
            for y in range(1, 8):
                for x in range(8):
                    gx = k * 8 + x
                    c = INK if (gx - 1, y - 1) in px else BG
                    i = o + y * 4 + x // 2
                    sh = 4 * (x & 1)
                    out[i] = (out[i] & ~(15 << sh) & 0xFF) | (c << sh)
    new = append(compress(bytes(out)), "PET shared BG tiles with Hangul tab headers (LZ)")
    for r in refs:
        write(r, struct.pack("<I", 0x88000000 | new), "PET shared BG tiles reference",
              struct.pack("<I", 0x88000000 | at))
    return {"at": new, "refs": len(refs)}
