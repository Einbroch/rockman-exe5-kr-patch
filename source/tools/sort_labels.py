"""Folder SORT menu labels (ID .. チップ容量) redrawn in Hangul.

Measured on the folder-edit SORT window (runtime/sort_snap_e5bf2228, Blues):
  * BG0 tiles from LZ 0x70001C (decompressed: 4-byte size head + tiles 1..62,
    uploaded to VRAM 0x06008020), map from LZ 0x70039C (head + 8x17 u16).
    Both are graphics-list entries with the 0x88000000 compressed flag, three
    references each (folder, pack and one more screen); Colonel stores the
    same decompressed bytes compressed differently.
  * Seven labels, two map rows each (rows 2..15), inner columns 1..5 (40 px);
    unused cells hold the plain tile 0x10.  Ink colour 8, shadow c to the
    right and below, background d, ink rows 3..12.
Labels are drawn in Galmuri9 from x=8+1, y=3; every cell a label touches gets
a tile from the pool of the label cells' own tiles (44).  The sort keys read
ID / 가나다 / 코드 / 공격력 / 계통 / 매수 / 용량 ("칩 용량" needs 46 tiles).
"""
from __future__ import annotations

import struct
from pathlib import Path

from lz77 import compress, lz77_decompress
from pet_labels import font as load_font, text_pixels
import pet_labels

FONT9 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri9.bdf"
LABELS = ["ID", "가나다", "코드", "공격력", "계통", "매수", "용량"]
BLUES = {"tiles": 0x70001C, "map": 0x70039C}
W, PLAIN = 8, 0x10


def find_lz(rom: bytes, want: bytes, part: slice | None = None) -> tuple[int, list[int]]:
    """The LZ blob (0x88-flagged references) whose data is `want` -- or, with
    `part`, whose data has want's length and the same bytes in that slice."""
    seen = {}
    for i in range(0, len(rom) - 3, 4):
        v = struct.unpack_from("<I", rom, i)[0]
        if v >> 24 != 0x88:
            continue
        at = v & 0x00FFFFFF
        if at not in seen:
            try:
                d = lz77_decompress(rom, at)[0]
                seen[at] = d == want if part is None else (len(d) == len(want) and d[part] == want[part])
            except Exception:
                seen[at] = False
        if seen[at]:
            return at, [j for j in range(0, len(rom) - 3, 4) if struct.unpack_from("<I", rom, j)[0] == 0x88000000 | 0x08000000 | at]
    raise ValueError("SORT graphics not found")


def build(rom: bytearray, append, write, blues: bytes) -> dict:
    T = lz77_decompress(blues, BLUES["tiles"])[0]
    M = lz77_decompress(blues, BLUES["map"])[0]
    t_at, t_refs = find_lz(bytes(rom), T)
    m_at, m_refs = find_lz(bytes(rom), M)
    if len(t_refs) != 3 or len(m_refs) != 3:
        raise ValueError("SORT graphics reference count changed: %d/%d" % (len(t_refs), len(m_refs)))
    m = list(struct.unpack_from("<%dH" % ((len(M) - 4) // 2), M, 4))
    pool = sorted({m[r * W + c] & 1023 for r in range(2, 16) for c in range(1, 6)} - {PLAIN})
    tiles = bytearray(T)
    saved = pet_labels.FONT
    pet_labels.FONT = FONT9
    try:
        f = load_font()
    finally:
        pet_labels.FONT = saved
    for k, text in enumerate(LABELS):
        ink = text_pixels(f, text)
        img = {}
        for x, y in ink:
            for dx, dy in ((1, 0), (0, 1), (1, 1)):
                img[(9 + x + dx, 3 + y + dy)] = 0xC
        for x, y in ink:
            img[(9 + x, 3 + y)] = 8
        if max(x for x, _ in img) >= 48 or max(y for _, y in img) > 15:
            raise ValueError("SORT label %r leaves its row" % text)
        for col in range(1, 6):
            for row in (0, 1):
                cell = (2 + 2 * k + row) * W + col
                if not any(col * 8 <= x < col * 8 + 8 for x, _ in img):
                    m[cell] = (m[cell] & 0xF000) | PLAIN
                    continue
                t = pool.pop(0)
                data = bytearray(32)
                for yy in range(8):
                    for xx in range(8):
                        c = img.get((col * 8 + xx, row * 8 + yy), 0xD)
                        data[yy * 4 + xx // 2] |= c << (4 * (xx & 1))
                tiles[4 + (t - 1) * 32:4 + t * 32] = data
                m[cell] = (m[cell] & 0xF000) | t
    new_map = M[:4] + struct.pack("<%dH" % len(m), *m)
    nt = append(compress(bytes(tiles)), "SORT label tiles (LZ)")
    nm = append(compress(new_map), "SORT label map (LZ)")
    for refs, old, new in ((t_refs, t_at, nt), (m_refs, m_at, nm)):
        for r in refs:
            write(r, struct.pack("<I", 0x88000000 | 0x08000000 | new), "SORT graphics reference",
                  struct.pack("<I", 0x88000000 | 0x08000000 | old))
    return {"tiles": nt, "map": nm, "pool_left": len(pool)}
