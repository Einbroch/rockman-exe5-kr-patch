"""Data-block puzzles (メインシステムの電脳 1/2) redesigned with Korean words.

The puzzle data letters are 27 ids (in-game data icon order):
   0..6  1 2 3 4 5 6 7          (digits, kept)
   7..26 イ ウ キ ギ コ サ タ テ ニ ヌ ノ ビ ブ ボ マ ミ ム ャ ユ ン
Each puzzle room is a list of 8-byte block records (1c 0e A B C D 00 00):
A = animation (= D * 3), B = block slot 0x10.., C = room 0..5, D = letter id.
Read in slot order the records spell each room's answer (762 / インコ /
ウサギ タヌキ / キャノン ミニボム / ミギテ コユビ マブタ / 53214), and the room
starts with the letters in record order -- so rewriting D (and A) changes the
answer and the starting scramble together, and the move limit still fits.
(User decision 10/11: Korean words, not transliteration.)  New answers:
   room 1 오소리, room 2 원숭이 / 너구리, room 3 메가캐논 / 에너지봄,
   room 4 오른손 / 옆구리 / 발가락; rooms 0 and 5 (digits) unchanged.
The game judges a block by the home slot its data carries (0x080B0DF4:
carried slot == block slot), not by the letter, so a room must never show two
equal letters -- the player could not tell the twins apart.  rewrite_rooms
refuses that.
Room 2 keeps its ids (a save made inside that room holds them).
After the start records come the solved-state records (0xB0770 comp 1,
0xB07D0 comp 2; slot order, A = letter * 3 + 2): what a solved room shows.
They are rewritten from the same letters -- left stale, the rooms with new
letters never finished (user report 10/11, 전뇌 2).

Move limits (Colonel 0x0809C49C: 04 04 06 06 07 07, one per room) stay as
they are: the controller (0x0809C530) runs the judge (0x0809C614, every block
of the room: carried home == its slot) only when the count reaches 0, so each
limit equals that room's minimum.  Raising room 2/3 to 7 left a finished room
with 1 move and no judgement (user report 10/11); never change them.

Three graphics show a letter id:
 * Floor letters on the blocks: one LZ sprite (Colonel 0x48931C, sprite table
   0x32CD4).  14 tilesets, each holding TWO letters overlaid (ids 2g, 2g+1;
   id 8 alone): anims 3*id .. 3*id+2 (static, rising, raised); the second
   letter's OAM entries carry 0x10 in the shape byte, which selects OBJ
   palette +1.  Palette 3 / 4 make one letter visible and hide the other:
     index: 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15
     pal 3: N M B N M B - - - N  M  B  B  N  M     (N navy rim, M mid, B bright,
     pal 4: N M B - - - N M B B  B  N  M  M  N      - hidden)
   so every pixel is coded from its (first letter, second letter) colours.
   Glyphs: Galmuri11 doubled with 3-px strokes, laid on the block top
   (upright (a, b) -> screen s * (a - b, (a + b) / 2); the axes were fitted on
   the original digits), rim/mid/core shading; header byte 0 (11) caps a tileset at 11 tiles.  Redrawn tilesets
   are written after the rebuilt OAM area (the old ones stay, unused).
 * Data icon (top right while carrying): raw sprite (Colonel 0x7D9F78, sprite
   table 0x33038), one frame whose OAM list holds the box and one entry per
   letter (8x16, サ 16x16).  The kana entries become 16x16 Galmuri11 bold with a
   1-px rim; the tileset grows (header byte 0 = tile count), so the sprite is
   rebuilt at the ROM end and repointed.
"""
from __future__ import annotations

import struct
from pathlib import Path


import pet_labels

FONT11 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri11.bdf"
COLONEL_FLOOR = 0x48931C
COLONEL_ICON = 0x7D9F78
COLONEL_ROOMS = 0xB0660          # start records: rooms 0..2 (12), rooms 3..5 (22); then the solved lists (12 + 22)
B = 8                            # LZ floor sprite: offsets relative to here
SCALES = (0.85, 0.8, 0.75, 0.7)     # floor projection scale; the largest whose two letters fit 11 tiles
MAX_TILES = 11

SYLLABLE = {7: "오", 8: "원", 9: "리", 10: "이", 11: "소", 12: "숭", 13: "너", 14: "메", 15: "가",
            16: "구", 17: "캐", 18: "논", 19: "에", 20: "지", 21: "봄", 22: "른", 23: "손", 24: "락",
            25: "발", 26: "옆"}
# (room, slot) -> new letter id; rooms 0, 2, 5 keep theirs
NEW_LETTER = {(1, 0x13): 7, (1, 0x14): 11, (1, 0x15): 9,
              (3, 0x10): 14, (3, 0x11): 15, (3, 0x12): 17, (3, 0x13): 18,
              (3, 0x14): 19, (3, 0x15): 13, (3, 0x16): 20, (3, 0x17): 21,
              (4, 0x18): 7, (4, 0x19): 22, (4, 0x1A): 23, (4, 0x1B): 26, (4, 0x1C): 16,
              (4, 0x1D): 9, (4, 0x1E): 25, (4, 0x1F): 15, (4, 0x20): 24}
ANSWERS = {0: "762", 1: "오소리", 2: "원숭이너구리", 3: "메가캐논에너지봄", 4: "오른손옆구리발가락", 5: "53214"}
DIGITS = "1234567"

COMBO = {(1, 1): 1, (2, 2): 2, (3, 3): 3, (1, 0): 4, (2, 0): 5, (3, 0): 6, (0, 1): 7, (0, 2): 8,
         (0, 3): 9, (1, 3): 10, (2, 3): 11, (3, 1): 12, (3, 2): 13, (1, 2): 14, (2, 1): 15}
PAL3 = {i: a for (a, b), i in COMBO.items()}           # index -> first letter's colour


# ------------------------------------------------------------------ floor letters
_FONT11 = None


def upright(ch: str) -> set:
    """Galmuri11 doubled with one extra column/row per pixel: 3-px strokes, so
    the floor projection keeps them as thick as the original letters'."""
    global _FONT11
    if _FONT11 is None:
        saved = pet_labels.FONT
        pet_labels.FONT = FONT11
        try:
            _FONT11 = pet_labels.font()
        finally:
            pet_labels.FONT = saved
    _, ink = _FONT11[ch]
    x0, y0 = min(x for x, _ in ink), min(y for _, y in ink)
    return {(2 * (x - x0) + i, 2 * (y - y0) + j) for x, y in ink for i in range(3) for j in range(3)}


def project(up: set, scale: float) -> dict:
    """Lay an upright glyph on the block top, centred on the original letters'
    mean ink position (x 0, y -27); returns screen pixel -> colour 1/2/3."""
    m = set()
    for y in range(-4, 48):
        for x in range(-40, 40):
            for ox in (0, 0.5):
                X, Y = (x + ox) / scale, y / scale
                a, b = (X + 2 * Y) / 2, (2 * Y - X) / 2
                if a >= 0 and b >= 0 and (int(a), int(b)) in up:
                    m.add((x, y))
    cx = round(sum(x for x, _ in m) / len(m))
    cy = round(sum(y for _, y in m) / len(m))
    m = {(x - cx, y - cy - 27) for x, y in m}
    img = {}
    for x, y in m:
        d = 1
        while (x - d, y) in m and (x + d, y) in m and d < 3:
            d += 1
        c = (1, 2, 3)[d - 1]
        if c == 3 and ((x, y - 1) not in m or (x, y + 1) not in m):
            c = 2
        img[(x, y)] = c
    return img


def tile_cover(img: dict):
    best = None
    for px in range(8):
        for py in range(8):
            cells = {((x + px) // 8, (y + py) // 8) for x, y in img}
            if best is None or len(cells) < len(best[2]):
                best = (px, py, cells)
    px, py, cells = best
    pieces, tiles = [], []
    for row in sorted({cy for _, cy in cells}):
        xs = sorted(cx for cx, cy in cells if cy == row)
        runs, cur = [], [xs[0]]
        for c in xs[1:]:
            if c == cur[-1] + 1:
                cur.append(c)
            else:
                runs.append(cur)
                cur = [c]
        runs.append(cur)
        for r in runs:
            while r:
                n = 4 if len(r) >= 4 else 2 if len(r) >= 2 else 1
                pieces.append((r[0] * 8 - px, row * 8 - py, n * 8, len(tiles)))
                for c in r[:n]:
                    t = bytearray(32)
                    for yy in range(8):
                        for xx in range(8):
                            v = img.get((c * 8 - px + xx, row * 8 - py + yy), 0)
                            t[yy * 4 + xx // 2] |= v << (4 * (xx & 1))
                    tiles.append(bytes(t))
                r = r[n:]
    return pieces, tiles


SIZES = {(0, 0): (8, 8), (0, 1): (16, 16), (0, 2): (32, 32), (1, 0): (16, 8), (1, 1): (32, 8),
         (1, 2): (32, 16), (1, 3): (64, 32), (2, 0): (8, 16), (2, 1): (8, 32), (2, 2): (16, 32)}


def parse(d: bytes):
    na = struct.unpack_from("<I", d, B)[0] // 4
    anims = []
    for a in range(na):
        q = struct.unpack_from("<I", d, B + a * 4)[0]
        fr = []
        while True:
            fr.append(B + q)
            if d[B + q + 18] & 0x80:
                break
            q += 20
        anims.append(fr)
    return anims


def oam_entries(d: bytes, oam: int):
    p = B + oam + struct.unpack_from("<I", d, B + oam)[0]
    out = []
    while d[p:p + 5] != b"\xff" * 5:
        t, x, y, f, sh = d[p:p + 5]
        out.append((t, x - 256 if x > 127 else x, y - 256 if y > 127 else y, f, sh))
        p += 5
    return out


def index_image(d: bytes, frame: int) -> dict:
    ts = struct.unpack_from("<I", d, frame)[0]
    img = {}
    for t, x, y, f, sh in oam_entries(d, struct.unpack_from("<I", d, frame + 12)[0]):
        w, h = SIZES[(sh & 3, f & 3)]
        for ty in range(h // 8):
            for tx in range(w // 8):
                tt = t + ty * (w // 8) + tx
                for yy in range(8):
                    for xx in range(8):
                        b = d[B + ts + 4 + tt * 32 + yy * 4 + xx // 2]
                        c = b >> 4 if xx & 1 else b & 15
                        if c:
                            img[(x + tx * 8 + xx, y + ty * 8 + yy)] = c
    return img


def rebuild_floor(D: bytes):
    d = bytearray(D)
    anims = parse(d)
    if len(anims) != 81 or d[4] != MAX_TILES:
        raise ValueError("puzzle floor sprite layout differs")
    groups = []
    for i, fr in enumerate(anims):
        ts = struct.unpack_from("<I", d, fr[0])[0]
        if not groups or groups[-1][0] != ts:
            groups.append((ts, []))
        groups[-1][1].append(i)
    ids, nxt = [], 0
    for ts, idx in groups:
        ids.append(list(range(nxt, nxt + len(idx) // 3)))
        nxt += len(idx) // 3
    if nxt != 27:
        raise ValueError("puzzle floor sprite: %d letters" % nxt)
    oam_start = min(struct.unpack_from("<I", d, f + 12)[0] for fr in anims for f in fr)
    body = bytearray()
    report = []

    def copy_oam(f):
        o = struct.unpack_from("<I", d, f + 12)[0]
        p = B + o + 4
        while d[p:p + 5] != b"\xff" * 5:
            p += 5
        blk = d[B + o:p + 5]
        blk += b"\0" * (-len(blk) % 4)
        struct.pack_into("<I", d, f + 12, oam_start + len(body))
        body.extend(blk)

    for (ts, idx), pair in zip(groups, ids):
        if all(i < 7 and i in (0, 1, 2, 3, 4, 5) for i in pair):      # digit pairs 1/2 3/4 5/6
            for i in idx:
                for f in anims[i]:
                    copy_oam(f)
            continue
        ref = oam_entries(d, struct.unpack_from("<I", d, anims[idx[0]][0] + 12)[0])
        keep = {}
        if pair[0] == 6:                                   # 7 shares its tiles with the first kana
            keep = {p: PAL3[c] for p, c in index_image(d, anims[idx[0]][0]).items() if PAL3.get(c)}
        for size in SCALES:
            layers = []
            for k, i in enumerate(pair):
                if i == 6:
                    layers.append(keep)
                elif SYLLABLE.get(i):
                    layers.append(project(upright(SYLLABLE[i]), size))
                else:
                    layers.append({})
            while len(layers) < 2:
                layers.append({})
            img = {}
            for p in set(layers[0]) | set(layers[1]):
                img[p] = COMBO[(layers[0].get(p, 0), layers[1].get(p, 0))]
            pieces, tiles = tile_cover(img)
            if len(tiles) <= MAX_TILES:
                break
        if len(tiles) > MAX_TILES:
            raise ValueError("puzzle letters %r need %d tiles" % (pair, len(tiles)))
        n_orig = struct.unpack_from("<I", d, B + ts)[0] // 32
        new_ts = oam_start + len(body)            # tilesets differ in size: the new one goes after the OAM area
        body += struct.pack("<I", 32 * len(tiles)) + b"".join(tiles)
        for i in idx:
            for f in anims[i]:
                struct.pack_into("<I", d, f, new_ts)
        for i in idx:
            for f in anims[i]:
                e = oam_entries(d, struct.unpack_from("<I", d, f + 12)[0])
                dx, dy, flip = e[0][1] - ref[0][1], e[0][2] - ref[0][2], e[0][4] & 0x10
                blk = bytearray(struct.pack("<I", 4))
                for x, y, w, t in pieces:
                    sh, sz = {32: (1, 1), 16: (1, 0), 8: (0, 0)}[w]
                    blk += bytes([t, (x + dx) & 0xFF, (y + dy) & 0xFF, sz, sh | flip])
                blk += b"\xff" * 5 + b"\0" * (-(len(blk) + 5) % 4)
                struct.pack_into("<I", d, f + 12, oam_start + len(body))
                body += blk
        report.append(("".join(SYLLABLE.get(i) or DIGITS[i] if i < 7 else SYLLABLE.get(i) or "-" for i in pair),
                       size, len(tiles), n_orig))
    d = d[:B + oam_start] + body
    struct.pack_into("<I", d, 0, len(d) << 8)
    return bytes(d), report


# ------------------------------------------------------------------ data icon
def icon_glyph(f, ch: str) -> dict:
    """16x16 cell: Galmuri11 bold, ink 0xB with a 1-px 0xA rim (the icons' colours)."""
    _, ink = f[ch]
    ink = ink | {(x + 1, y) for x, y in ink}          # bold, like the digit icons' 2-px strokes
    x0, y0 = min(x for x, _ in ink), min(y for _, y in ink)
    w = max(x for x, _ in ink) - x0 + 1
    h = max(y for _, y in ink) - y0 + 1
    ox, oy = (16 - w) // 2, (16 - h) // 2
    px = {(x - x0 + ox, y - y0 + oy) for x, y in ink}
    img = {}
    for x, y in px:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                img[(x + dx, y + dy)] = 0xA
    for p in px:
        img[p] = 0xB
    if min(x for x, _ in img) < 0 or max(x for x, _ in img) > 15 or min(y for _, y in img) < 0 or max(y for _, y in img) > 15:
        raise ValueError("icon glyph %r does not fit 16x16" % ch)
    return img


def rebuild_icon(rom: bytes, at: int) -> bytes:
    Bi = at + 4
    if rom[at:at + 4] != b"\x48\x00\x01\x01":
        raise ValueError("data icon sprite header differs")
    fr = Bi + struct.unpack_from("<I", rom, Bi)[0]
    t_off, p_off, j_off, o_off = struct.unpack_from("<4I", rom, fr)
    lo = Bi + o_off
    ents_at = lo + struct.unpack_from("<I", rom, lo)[0]
    ents = [list(rom[ents_at + k * 5:ents_at + k * 5 + 5]) for k in range(29)]
    if rom[ents_at + 29 * 5:ents_at + 29 * 5 + 5] != b"\xff" * 5:
        raise ValueError("data icon OAM list differs")
    end = ents_at + 29 * 5 + 5
    old_tiles = rom[Bi + t_off + 4:Bi + t_off + 4 + struct.unpack_from("<I", rom, Bi + t_off)[0]]
    keep = 30                                  # box (0..15) and the seven digits (16..29)
    if ents[2 + 6][0] != 28 or ents[2 + 7][0] != 30:
        raise ValueError("data icon tile order differs")
    tiles = bytearray(old_tiles[:keep * 32])
    saved = pet_labels.FONT
    pet_labels.FONT = FONT11
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    for i in range(7, 27):
        t = len(tiles) // 32
        img = icon_glyph(f, SYLLABLE[i]) if SYLLABLE.get(i) else {}
        for ty in range(2):
            for tx in range(2):
                cell = bytearray(32)
                for yy in range(8):
                    for xx in range(8):
                        cell[yy * 4 + xx // 2] |= img.get((tx * 8 + xx, ty * 8 + yy), 0) << (4 * (xx & 1))
                tiles += cell
        ents[2 + i] = [t, (-8) & 0xFF, (-8) & 0xFF, 1, 0]             # 16x16
    out = bytearray(rom[at:end])
    out += b"\0" * (-len(out) % 4)
    new_t = len(out) - 4                       # tileset offset relative to Bi
    out += struct.pack("<I", len(tiles)) + tiles
    out[0] = len(tiles) // 32
    struct.pack_into("<I", out, fr - at, new_t)
    for k, e in enumerate(ents):
        out[ents_at - at + k * 5:ents_at - at + k * 5 + 5] = bytes(e)
    return bytes(out)


# ------------------------------------------------------------------ rooms
def rewrite_rooms(block: bytes) -> tuple[bytes, dict]:
    """block: the 34 start records (comp 1: 12, comp 2: 22) and right after them
    the 34 solved-state records (same split, slot order, A = letter * 3 + 2 =
    the raised animation, D = 0).  The solved list must name the same letters
    as the start list's homes, or a finished room is never taken as solved."""
    out = bytearray(block)
    rooms, solved_of = {}, {}
    for k in range(0, 34 * 8, 8):
        if out[k:k + 2] != b"\x1c\x0e" or out[k + 6:k + 8] != b"\0\0":
            raise ValueError("puzzle block record %d differs" % (k // 8))
        slot, room = out[k + 3], out[k + 4]
        comp = 0 if k < 12 * 8 else 1
        if (comp, slot) in solved_of:
            raise ValueError("puzzle home slot %X used twice" % slot)
        old_letter = out[k + 5]
        new = NEW_LETTER.get((room, slot), old_letter)
        out[k + 5] = new
        out[k + 2] = new * 3
        rooms.setdefault(room, {})[slot] = new
        solved_of[(comp, slot)] = (old_letter, new)
    for k in range(34 * 8, 68 * 8, 8):
        comp = 0 if k < (34 + 12) * 8 else 1
        slot = out[k + 3]
        if out[k:k + 2] != b"\x1c\x0e" or out[k + 4:k + 8] != b"\0\0\0\0":
            raise ValueError("puzzle solved record %d differs" % (k // 8 - 34))
        old_letter, new = solved_of[(comp, slot)]
        if out[k + 2] != old_letter * 3 + 2:
            raise ValueError("solved record for slot %X does not show the home letter" % slot)
        out[k + 2] = new * 3 + 2
    answers = {}
    for room, slots in rooms.items():
        shown = [i for i in slots.values()]
        glyphs = [DIGITS[i] if i < 7 else SYLLABLE[i] for i in shown]
        if len(set(glyphs)) != len(glyphs):
            raise ValueError("room %d shows a letter twice: %s" % (room, "".join(glyphs)))
        answers[room] = "".join(DIGITS[i] if i < 7 else SYLLABLE[i] for _, i in sorted(slots.items()))
        if answers[room] != ANSWERS[room]:
            raise ValueError("room %d spells %r, expected %r" % (room, answers[room], ANSWERS[room]))
    return bytes(out), answers


def build(rom: bytearray, append, write, colonel: bytes) -> dict:
    from lz77 import compress, lz77_decompress
    from sort_labels import find_lz
    report = {}
    # rooms
    src = colonel[COLONEL_ROOMS:COLONEL_ROOMS + 68 * 8]
    at = bytes(rom).find(src)
    if at < 0 or bytes(rom).find(src, at + 1) >= 0:
        raise ValueError("puzzle room records not found once")
    new, report["answers"] = rewrite_rooms(src)
    write(at, new, "puzzle room records (Korean answers)", src)
    # floor letters
    D = lz77_decompress(colonel, COLONEL_FLOOR)[0]
    fat, refs = find_lz(bytes(rom), D)
    if len(refs) != 1:
        raise ValueError("puzzle letter sprite reference count changed: %d" % len(refs))
    new_d, report["floor"] = rebuild_floor(D)
    nf = append(compress(new_d), "puzzle floor letters in Hangul (LZ)")
    write(refs[0], struct.pack("<I", 0x88000000 | nf), "puzzle floor letter sprite reference",
          struct.pack("<I", 0x88000000 | fat))
    # data icon
    isrc = colonel[COLONEL_ICON:COLONEL_ICON + 0x9EC]
    iat = bytes(rom).find(isrc)
    if iat < 0:
        raise ValueError("data icon sprite not found")
    ptr = struct.pack("<I", 0x08000000 | iat)
    irefs = [i for i in range(0, len(rom) - 3, 4) if rom[i:i + 4] == ptr]
    if len(irefs) != 1:
        raise ValueError("data icon sprite reference count: %d" % len(irefs))
    ni = append(rebuild_icon(bytes(rom), iat), "puzzle data icons in Hangul (raw sprite)")
    write(irefs[0], struct.pack("<I", 0x08000000 | ni), "data icon sprite reference", ptr)
    report["icon"] = ni
    return report
