"""PET main menu labels (チップフォルダ .. セーブ) redrawn in Hangul.

Measured on the PET screen (runtime/gfx_pet_snap, Blues):
  * BG0 (tiles at VRAM 0x8000, map 0xE000).  The eight labels are an 8x16
    map block (ROM 0x6F982C, blitted at (6,3) by 0x03005F78 every frame from
    the literal at 0x1283A0): per label two rows of [cap, six inner cells,
    flipped cap]; unused inner cells hold the fill tile 0x2A0 (bottom row
    v-flipped).
  * Tiles: graphics list at 0x128178 (pointer 0x128174) uploads 0x6F87FC ->
    tiles 640..665 and 0x6F8B3C -> tiles 666..731 (label block).
  * Label k inks in colour 8+k of palette 15 (the game whitens that colour on
    the selected row), shadow colour 6 to the right, below and diagonal; the
    box is colour 7 with a colour-6 border on rows 0-1 and 14-15.
  * VRAM tiles 735..747 are zero in every snapshot taken (732-734 and 748+
    hold resident data and are left alone).
Each Hangul label is drawn in Galmuri9 from x=9, ink rows 3..11, with a diagonal
shadow only (Galmuri7 with the native three-way shadow read 록맨 as 족맨 in the
unselected colour); every inner
cell it touches gets its own tile from the pool 667..731 (minus the fill
0x2A0) + 735..747.  New tile blocks, map and graphics list go to the ROM end;
only the two pointers change.  Colonel is located by the same bytes.
"""
from __future__ import annotations

import struct
from pathlib import Path

FONT = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri9.bdf"
LABELS = ["칩 폴더", "서브칩", "도감", "록맨", "E메일", "키 아이템", "통신", "세이브"]
BASE = {"blues": {"tiles_lo": 0x6F87FC, "tiles_hi": 0x6F8B3C, "map": 0x6F982C, "list_ptr": 0x128174,
                  "map_lit": 0x1283A0}}
CAP, FILL = 0x29A, 0x2A0
POOL = [t for t in range(0x29B, 0x2DC) if t != FILL] + list(range(735, 748))
X0, INK_TOP = 9, 3


def font():
    out = {}
    for block in FONT.read_text(encoding="utf-8", errors="replace").split("STARTCHAR ")[1:]:
        L = block.splitlines()
        cp = int(next(x.split()[1] for x in L if x.startswith("ENCODING ")))
        w, h, xo, yo = map(int, next(x for x in L if x.startswith("BBX ")).split()[1:])
        dw = int(next(x.split()[1] for x in L if x.startswith("DWIDTH ")))
        s = L.index("BITMAP") + 1
        rows = [int(r, 16) for r in L[s:s + h]]
        pad = ((w + 7) // 8) * 8
        out[chr(cp)] = (dw, {(xo + x, -(h + yo) + y) for y, r in enumerate(rows) for x in range(w)
                             if r & (1 << (pad - 1 - x))})
    return out


def text_pixels(f, text):
    pen, px = 0, set()
    for c in text:
        if c not in f:
            raise ValueError("no Galmuri9 glyph for %r" % c)
        dw, ink = f[c]
        px |= {(pen + x, y) for x, y in ink}
        pen += dw
    y0 = min(y for _, y in px)
    return {(x, y - y0) for x, y in px}


def locate(rom: bytes, blues: bytes) -> dict:
    """Same structures in another version: find each by its Blues bytes."""
    b = BASE["blues"]
    out = {}
    for key, size in (("tiles_lo", 0x340), ("tiles_hi", 0x840), ("map", 0x100)):
        at = rom.find(blues[b[key]:b[key] + size])
        if at < 0 or rom.find(blues[b[key]:b[key] + size], at + 1) >= 0:
            raise ValueError("PET %s not unique in this ROM" % key)
        out[key] = at
    lst = struct.pack("<6I", 0x08000000 + out["tiles_lo"], 0x0600D000, 0x340,
                      0x08000000 + out["tiles_hi"], 0x0600D340, 0x840)
    la = rom.find(lst)
    out["list_ptr"] = rom.find(struct.pack("<I", 0x08000000 + la))
    out["map_lit"] = rom.find(struct.pack("<I", 0x08000000 + out["map"]))
    if la < 0 or out["list_ptr"] < 0 or out["map_lit"] < 0:
        raise ValueError("PET graphics list or map literal not found")
    return out


def build(rom: bytearray, append, write, version: str, blues: bytes) -> dict:
    b = BASE["blues"] if version == "blues" else locate(rom, blues)
    hi = bytes(rom[b["tiles_hi"]:b["tiles_hi"] + 0x840])
    lst_at = struct.unpack_from("<I", rom, b["list_ptr"])[0] - 0x08000000
    lst = list(struct.unpack_from("<12I", rom, lst_at))
    # Four {source, VRAM/RAM destination, bytes} entries, then a zero word.
    if lst[0:6] != [0x08000000 + b["tiles_lo"], 0x0600D000, 0x340, 0x08000000 + b["tiles_hi"], 0x0600D340, 0x840] \
            or struct.unpack_from("<I", rom, lst_at + 48)[0] != 0:
        raise ValueError("PET graphics list differs")
    old_map = list(struct.unpack_from("<128H", rom, b["map"]))
    f = font()
    tiles = {}                                   # tile number -> 32 bytes
    new_map = list(old_map)
    pool = list(POOL)
    for k, text in enumerate(LABELS):
        ink = text_pixels(f, text)
        img = {}
        for x, y in ink:                         # shadow first, ink over it
            img[(X0 + x + 1, INK_TOP + y + 1)] = 6
        for x, y in ink:
            img[(X0 + x, INK_TOP + y)] = 8 + k
        if max(x for x, _ in img) >= 56 or max(y for _, y in img) > 13:
            raise ValueError("label %r leaves its box" % text)
        for col in range(1, 7):
            if not any(col * 8 <= x < col * 8 + 8 for x, _ in img):
                new_map[(2 * k) * 8 + col] = 0xF000 | FILL
                new_map[(2 * k + 1) * 8 + col] = 0xF800 | FILL
                continue
            for row in (0, 1):
                t = pool.pop(0)
                data = bytearray(32)
                for yy in range(8):
                    py = row * 8 + yy
                    for xx in range(8):
                        c = 6 if py in (0, 1, 14, 15) else 7
                        c = img.get((col * 8 + xx, py), c)
                        data[yy * 4 + xx // 2] |= c << (4 * (xx & 1))
                tiles[t] = bytes(data)
                new_map[(2 * k + row) * 8 + col] = 0xF000 | t
    blk = bytearray(hi)
    for t, d in tiles.items():
        if 0x29A <= t <= 0x2DB:
            blk[(t - 0x29A) * 32:(t - 0x29A + 1) * 32] = d
    hi_at = append(bytes(blk), "PET label tiles 666..731")
    map_at = append(struct.pack("<128H", *new_map), "PET label map")
    new_list = struct.pack("<12I", *lst[:3], 0x08000000 + hi_at, 0x0600D340, 0x840, *lst[6:12])
    if any(t >= 735 for t in tiles):          # only when the labels outgrow 666..731
        extra = b"".join(tiles.get(t, bytes(32)) for t in range(735, 748))
        ex_at = append(extra, "PET label tiles 735..747")
        new_list += struct.pack("<3I", 0x08000000 + ex_at, 0x06008000 + 735 * 32, len(extra))
    new_list += struct.pack("<I", 0)
    list_at = append(new_list, "PET graphics list (+ tiles 735..747)")
    write(b["list_ptr"], struct.pack("<I", 0x08000000 + list_at), "PET graphics list pointer",
          struct.pack("<I", 0x08000000 + lst_at))
    write(b["map_lit"], struct.pack("<I", 0x08000000 + map_at), "PET label map literal",
          struct.pack("<I", 0x08000000 + b["map"]))
    return {"tiles_used": len(tiles), "pool_left": len(pool), "list": list_at, "map": map_at}
