"""FA FC Hangul in the 8x16 name renderer (IWRAM 0x03006DE0).

Menus, chip names, virus names and the like are drawn by the routine that
0x0804528C reaches through 0x03006DE1: one byte per 8x16 cell (E4 xx for the
second page), E5..FF dispatched through the IWRAM table 0x03006D64.  Its FA
entry (0x03006FAD) knows only FA 00..03, so FA FC would index past its table.

This module repoints that FA entry -- in the ROM source of the IWRAM copy, so
the boot copy carries it -- to a ROM handler: FA FC lo hi draws syllable
U+AC00+(lo|hi<<8) through the renderer's own cell copier 0x03006E60 with a
Hangul glyph base, counts the cell as the loop does for a normal character
(sb += 1) and advances four bytes; anything else tail-jumps to 0x03006FAD
unchanged.  Glyphs are the EXE 1 [K] 8x16 lettering (tools/exe1k_hangul.py),
ink 1 / shadow 2 on 0 as the native records are, all 2,350 KS X 1001
syllables, reached through a u16 map over the 11,172 syllable indices.
A syllable outside KS X 1001 has no glyph: encode() refuses it.

Both versions share these IWRAM addresses (measured: same bytes at the same
ROM offsets 0x1C8B64 / 0x1C8BE0).
"""
import struct
from pathlib import Path

from build_dialogue_poc import assemble
from exe1k_hangul import KS_COUNT, ink as exe1k_ink, load as exe1k_load
from exe5_profiles import IWRAM_BASE, IWRAM_ROM_BASE

EXE1K = Path("D:/Games/Kor Patch/CLude/록맨 에그제 2/Battle Network Rockman EXE 1 [K].gba")
HANGUL = 11172
GLYPH = 64
NO_GLYPH = 0xFFFF

FA_SLOT_IWRAM = 0x03006D64 + (0xFA - 0xE5) * 4
FA_LEGACY = 0x03006FAD
COPIER = 0x03006E61
COPIER_SIG = bytes.fromhex("41b58f01f6195046806b806b3c21")   # push {r0,r6,lr}; lsls r7,r1,#6 ...
LEGACY_SIG = bytes.fromhex("88b5034943789b00")               # push {r3,r7,lr}; ldr r1,=0x03006fc0 ...


def rom_of(iwram: int) -> int:
    return (iwram & ~1) - IWRAM_BASE + IWRAM_ROM_BASE


# FA FD a0..a3 -- the builder's RAM stub for a changed script of a compressed
# archive: continue the stream at that ROM address.  The legacy FA tables of
# A and B have no FD entry (it would index past them and crash).
JUMP = """jump:
push {r3}
ldrb r1, [r0, #5]
lsls r1, r1, #8
ldrb r3, [r0, #4]
orrs r1, r3
lsls r1, r1, #8
ldrb r3, [r0, #3]
orrs r1, r3
lsls r1, r1, #8
ldrb r3, [r0, #2]
orrs r1, r3
adds r0, r1, #0
pop {r3}
mov pc, lr
"""

HANDLER = """ldrb r1, [r0, #1]
cmp r1, #0xfc
beq hangul
cmp r1, #0xfd
beq jump
ldr r1, legacy
bx r1
""" + JUMP + """hangul:
push {r3, r6, lr}
ldrb r1, [r0, #3]
lsls r1, r1, #8
ldrb r3, [r0, #2]
orrs r1, r3
lsls r1, r1, #1
ldr r3, map
ldrh r1, [r3, r1]
ldr r6, glyphs
ldr r3, copier
mov lr, pc
bx r3
mov r3, sb
adds r3, #1
mov sb, r3
adds r0, #4
pop {r3, r6, pc}
"""


def pack(pixels) -> bytes:
    """Native record: rows 0..15 of four bytes, ink 1, shadow one pixel right and down 2."""
    grid = [[0] * 8 for _ in range(16)]
    for x, y in pixels:
        for dx, dy in ((1, 0), (0, 1), (1, 1)):
            if x + dx < 8 and y + dy < 16:
                grid[y + dy][x + dx] = 2
    for x, y in pixels:
        grid[y][x] = 1
    return bytes(grid[y][x] | grid[y][x + 1] << 4 for y in range(16) for x in range(0, 8, 2))


def glyph_table():
    """(glyph blob, map blob, syllable -> slot) for every KS X 1001 syllable."""
    source = exe1k_load(EXE1K)
    blob, slots = bytearray(), {}
    for cp in range(0xAC00, 0xAC00 + HANGUL):
        pixels = exe1k_ink(source, chr(cp))
        if pixels is None:
            continue
        slots[chr(cp)] = len(slots)
        blob += pack(pixels)
    if len(slots) != KS_COUNT:
        raise ValueError("EXE 1 [K] supplies %d/%d syllables" % (len(slots), KS_COUNT))
    table = [NO_GLYPH] * HANGUL
    for ch, slot in slots.items():
        table[ord(ch) - 0xAC00] = slot
    return bytes(blob), struct.pack("<%dH" % HANGUL, *table), slots


def encode_factory(slots):
    def encode(ch: str) -> bytes:
        if ch not in slots:
            raise ValueError("no 8x16 glyph for %r (outside KS X 1001)" % ch)
        return b"\xfa\xfc" + (ord(ch) - 0xAC00).to_bytes(2, "little")
    return encode


def place(rom, append, source: str, pool: dict, owner: str):
    """Assemble at the next 4-aligned end of `rom` and append there."""
    at = (len(rom) + 3) & ~3
    code, listing = assemble(source, 0x08000000 + at, pool)
    if append(code, owner) != at:
        raise ValueError("code moved after assembly: " + owner)
    return at, listing


def install(rom: bytearray, append, write) -> dict:
    """Append glyphs, map and handler; repoint the FA slot. `append(data, owner)`
    returns the 4-aligned ROM offset it wrote at; `write(offset, data, owner,
    expected)` patches in place after checking the expected bytes."""
    if rom[rom_of(COPIER):rom_of(COPIER) + len(COPIER_SIG)] != COPIER_SIG:
        raise ValueError("cell copier signature differs")
    if rom[rom_of(FA_LEGACY):rom_of(FA_LEGACY) + len(LEGACY_SIG)] != LEGACY_SIG:
        raise ValueError("legacy FA handler signature differs")
    slot = rom_of(FA_SLOT_IWRAM)
    if struct.unpack_from("<I", rom, slot)[0] != FA_LEGACY:
        raise ValueError("FA slot of the name renderer is not the legacy handler")
    glyphs, table, slots = glyph_table()
    g_at = append(glyphs, "name glyphs")
    m_at = append(table, "name glyph map")
    pool = {"legacy": FA_LEGACY, "map": 0x08000000 + m_at, "glyphs": 0x08000000 + g_at, "copier": COPIER}
    h_at, listing = place(rom, append, HANDLER, pool, "name renderer FA FC handler")
    write(slot, struct.pack("<I", 0x08000001 + h_at), "name renderer FA slot (IWRAM source)",
          struct.pack("<I", FA_LEGACY))
    return {"handler": h_at, "glyphs": g_at, "map": m_at, "fa_slot": slot, "slots": slots, "listing": listing}


# ---------------------------------------------------------------- B
# 0x0804546C (Blues): the proportional 12-row renderer behind the stubs
# 0x080452BC/C6/D0/DA (six call sites, every one passing the dialogue font in r6).
# Its copier 0x080454E8 always draws twelve rows, so the dialogue font view
# (484 source records + 11172 Hangul, built by build_dialogue_poc.py) and an
# advance view with 12 per syllable are enough; its FA slot gets FA FC.
# Measured on each ROM (code patterns, then the values checked below).
PROP = {
    "blues": {"fa_slot": 0x08045460, "fa_legacy": 0x08045769, "copier": 0x080454E9, "width_table": 0x080455A0,
              "widths": [0x080425C0, 0x08042CA4], "font": 0x086D7B5C,
              "font_loads": [0x080292EC, 0x08029310, 0x0803A8F0, 0x0813CBB8, 0x0803B12E, 0x08054B32]},
    "colonel": {"fa_slot": 0x08045468, "fa_legacy": 0x08045771, "copier": 0x080454F1, "width_table": 0x080455A8,
                "widths": [0x080425C8, 0x08042CAC], "font": 0x086D8FF0,
                "font_loads": [0x080292F0, 0x08029314, 0x0803A8F4, 0x0813CCA0, 0x0803B132, 0x08054B3A]},
}
PROP_COPIER_SIG = bytes.fromhex("09b5534608b4434608b481b0")
LEGACY = 0x1E4

PROP_HANDLER = """ldrb r1, [r0, #1]
cmp r1, #0xfc
beq hangul
cmp r1, #0xfd
beq jump
ldr r1, legacy
bx r1
""" + JUMP + """hangul:
push {r3, lr}
ldrb r1, [r0, #3]
lsls r1, r1, #8
ldrb r3, [r0, #2]
orrs r1, r3
ldr r3, bias
adds r1, r1, r3
ldr r3, copier
mov lr, pc
bx r3
adds r0, #4
pop {r3, pc}
"""


def install_prop(rom: bytearray, append, write, version: str, font_view: int, width_view: int) -> dict:
    """font_view/width_view: ROM offsets of the dialogue build's extended views."""
    pr = PROP[version]
    o = pr["copier"] - 1 - 0x08000000
    if rom[o:o + len(PROP_COPIER_SIG)] != PROP_COPIER_SIG:
        raise ValueError("proportional copier signature differs")
    slot = pr["fa_slot"] - 0x08000000
    if struct.unpack_from("<I", rom, slot)[0] != pr["fa_legacy"]:
        raise ValueError("proportional FA slot is not the legacy handler")
    literals = []
    for at in pr["font_loads"]:
        hw = struct.unpack_from("<H", rom, at - 0x08000000)[0]
        if hw >> 11 != 0b01001 or (hw >> 8) & 7 != 6:
            raise ValueError("no ldr r6,[pc] at %08X" % at)
        lit = ((at + 4) & ~3) + (hw & 0xFF) * 4 - 0x08000000
        if struct.unpack_from("<I", rom, lit)[0] not in (pr["font"], 0x08000000 + font_view):
            raise ValueError("font literal at %X is not the dialogue font" % lit)
        literals.append(lit)
    tables = list(struct.unpack_from("<2I", rom, pr["width_table"] - 0x08000000))
    if tables != pr["widths"]:
        raise ValueError("proportional advance tables differ")
    w2 = tables[1] - 0x08000000
    second = bytes(rom[w2:w2 + LEGACY * 4]) + (12).to_bytes(4, "little") * HANGUL
    second_at = append(second, "proportional advance view 2")
    pool = {"legacy": pr["fa_legacy"], "bias": LEGACY, "copier": pr["copier"]}
    h_at, listing = place(rom, append, PROP_HANDLER, pool, "proportional FA FC handler")
    for lit in literals:
        write(lit, struct.pack("<I", 0x08000000 + font_view), "proportional renderer font literal",
              bytes(rom[lit:lit + 4]))
    write(pr["width_table"] - 0x08000000, struct.pack("<2I", 0x08000000 + width_view, 0x08000000 + second_at),
          "proportional advance tables", struct.pack("<2I", *tables))
    write(slot, struct.pack("<I", 0x08000001 + h_at), "proportional FA slot", struct.pack("<I", pr["fa_legacy"]))
    return {"handler": h_at, "font_literals": literals, "listing": listing}
