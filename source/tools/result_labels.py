"""Battle result windows: デリートタイム / バスティングレベル / チップデータをロストしました….

The loader's table at Blues 0x286C0 holds three windows (normal, WINNER!,
LOSER), each a raw 4bpp tile block uploaded to VRAM 0x06008020 (VRAM tile n =
block tile n-1) and a raw 24x18 BG map (palette 9):
  normal  tiles 0x7607DC (0xE60)  map 0x7632BC
  WINNER  tiles 0x76163C (0xF00)  map 0x76361C
  LOSER   tiles 0x76253C (0xD80)  map 0x76397C
Colonel holds the same bytes 0x14A0 later (located by content).
Labels are two-row bands: ink 9, shade a right/below/diagonal, paper f; the
lower fill tile of the label rows carries the underline.  A band is redrawn
whole on its fill tiles (Galmuri9), every 8x8 cell that is not a fill gets a
tile from the pool of tiles only the bands use (the two labels share one
lower-row tile), and tiles/map are rewritten in place (same sizes).
"""
from __future__ import annotations

import struct
from pathlib import Path

import pet_labels

FONT9 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri9.bdf"
W, H = 24, 18
INK, SHADE = 0x9, 0xA
# (tiles offset, tiles bytes, map offset, fills (upper, lower), bands)
# band: (row, first col, last col, text, align)
WINDOWS = [
    (0x7607DC, 0xE60, 0x7632BC, (0x00C, 0x035),
     [(4, 3, 13, "딜리트 타임", "left"), (6, 3, 13, "버스팅 레벨", "left")]),
    (0x76163C, 0xF00, 0x76361C, (0x00A, 0x03B),
     [(4, 3, 13, "딜리트 타임", "left"), (6, 3, 13, "버스팅 레벨", "left")]),
    (0x76253C, 0xD80, 0x76397C, (0x00A, 0x00A),
     [(5, 3, 20, "칩 데이터를 잃었다…", "center")]),
]


def build(rom: bytearray, write, blues: bytes) -> dict:
    saved = pet_labels.FONT
    pet_labels.FONT = FONT9
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    if "…" not in f:
        raise ValueError("Galmuri9 has no …")
    done = []
    for t_off, t_len, m_off, fills, bands in WINDOWS:
        src_t, src_m = blues[t_off:t_off + t_len], blues[m_off:m_off + W * H * 2]
        t_at, m_at = bytes(rom).find(src_t), bytes(rom).find(src_m)
        if t_at < 0 or m_at < 0:
            raise ValueError("result window %X not found" % t_off)
        tiles = bytearray(src_t)
        m = list(struct.unpack_from("<%dH" % (W * H), src_m))

        def px(t, x, y):
            if t == 0:
                return 0
            b = tiles[(t - 1) * 32 + y * 4 + x // 2]
            return b >> 4 if x & 1 else b & 15
        cells = {(r + d, c) for r, a, z, _, _ in bands for d in (0, 1) for c in range(a, z + 1)}
        band_tiles = {m[r * W + c] & 1023 for r, c in cells} - set(fills)
        outside = {m[i] & 1023 for i in range(W * H) if (i // W, i % W) not in cells}
        pool = sorted(band_tiles - outside)
        if any(m[r * W + c] & 0xFC00 != 0x9000 for r, c in cells):
            raise ValueError("result band cell flipped or not palette 9")
        new = {}
        for row, first, last, text, align in bands:
            width = (last - first + 1) * 8
            img = [[px(fills[y // 8], x % 8, y % 8) for x in range(width)] for y in range(16)]
            ink = pet_labels.text_pixels(f, text)
            tw = max(x for x, _ in ink) + 2
            if tw > width:
                raise ValueError("result text too wide: %r" % text)
            left = 1 if align == "left" else (width - tw) // 2
            q = {(x + left, y + 2) for x, y in ink}
            for x, y in q:
                for dx, dy in ((1, 0), (0, 1), (1, 1)):
                    if (x + dx, y + dy) not in q and y + dy < 14:
                        img[y + dy][x + dx] = SHADE
            for x, y in q:
                img[y][x] = INK
            for half in (0, 1):
                for k in range(last - first + 1):
                    new[(row + half, first + k)] = (tuple(tuple(img[half * 8 + y][k * 8:k * 8 + 8]) for y in range(8)),
                                                    fills[half])
        used = {}
        for (r, c), (cell, fill) in sorted(new.items()):
            if cell == tuple(tuple(px(fill, x, y) for x in range(8)) for y in range(8)):
                t = fill
            else:
                if cell not in used:
                    if not pool:
                        raise ValueError("result window %X: tile pool exhausted" % t_off)
                    used[cell] = pool.pop(0)
                t = used[cell]
            m[r * W + c] = (m[r * W + c] & 0xFC00) | t
        for cell, t in used.items():
            for y in range(8):
                for x in range(0, 8, 2):
                    tiles[(t - 1) * 32 + y * 4 + x // 2] = cell[y][x] | cell[y][x + 1] << 4
        write(t_at, bytes(tiles), "result window tiles %X" % t_off, src_t)
        write(m_at, struct.pack("<%dH" % (W * H), *m), "result window map %X" % m_off, src_m)
        done.append({"tiles": t_at, "map": m_at, "pool_left": len(pool)})
    return {"windows": done}
