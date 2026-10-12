"""FA FC Hangul in the preloaded-font BG tilemap name writers.

Seven screens (folder, pack, library, ...) upload the 8x16 font codes
0x00..0x9F to VRAM 0x06004000 through their graphics lists ({0x086E20FC,
0x06004000, 0x2800}) and write names as tilemap pairs: code c becomes tile
base+2c over base+2c+1.  Two writers do this:

  C 0x081295B0  r0 text, r2/r3 top/bottom map, r4 base, r5 cells; returns
                r0 = cells drawn; stops at the first byte >= E5 and pads.
  D 0x0812D7B0  the same with the base in r6 and eight cells, no result.

Both entries are replaced by a jump (through r1, which both clobber at once)
to one body that also takes FA FC lo hi.  A syllable goes to one of the font's
kana codes (0x0B..0x5D, 0x9A..0x9F; space, digits, latin and signs stay
native) picked least-recently-drawn from a tag/stamp table in EWRAM
0x0203FC00 (zero in every dump taken, folder screen included).  Its glyph is
copied over that code's tiles at 0x06004000+64*code on every draw, so a
screen that re-uploads the font needs no reset hook: the next draw restores
the syllable, and a stale tag only costs a copy.  A slot's tag may start as
zero (syllable 가); that is harmless for the same reason.
"""
import struct

from build_dialogue_poc import assemble
from name_hangul import place

ENTRIES = {"blues": (0x081295B0, 0x0812D7B0), "colonel": (0x08129698, 0x0812D898)}   # (C, D)
C_EXPECTED = bytes.fromhex("f0b500270178e529")   # push {r4-r7,lr}; movs r7,#0; ldrb r1,[r0]; cmp r1,#0xe5
D_EXPECTED = bytes.fromhex("f0b500270178e529")
CACHE = 0x0203FC00
FONT_VRAM = 0x06004000
SLOT_CODES = list(range(0x0B, 0x5E)) + list(range(0x9A, 0xA0))
STAMPS = (4 + 2 * len(SLOT_CODES) + 3) & ~3

BODY = """c_entry:
push {r4, r5, r6, r7, lr}
b body
d_entry:
push {r4, r5, r6, r7, lr}
adds r4, r6, #0
movs r5, #8
body:
movs r7, #0
loop:
ldrb r1, [r0]
cmp r1, #0xfa
beq fa
cmp r1, #0xe5
bge pad
adds r0, #1
cell:
lsls r1, r1, #1
adds r6, r4, r1
strh r6, [r2]
adds r6, #1
strh r6, [r3]
adds r2, #2
adds r3, #2
adds r7, #1
b loop
fa:
ldrb r1, [r0, #1]
cmp r1, #0xfd
beq jump
cmp r1, #0xfc
bne pad
ldrb r1, [r0, #3]
lsls r1, r1, #8
ldrb r6, [r0, #2]
orrs r1, r6
ldr r6, lookup
mov lr, pc
bx r6
adds r0, #4
b cell
jump:
ldrb r1, [r0, #5]
lsls r1, r1, #8
ldrb r6, [r0, #4]
orrs r1, r6
lsls r1, r1, #8
ldrb r6, [r0, #3]
orrs r1, r6
lsls r1, r1, #8
ldrb r6, [r0, #2]
orrs r1, r6
adds r0, r1, #0
b loop
pad:
adds r6, r7, #0
padloop:
cmp r7, r5
bge done
movs r1, #0
strh r1, [r2]
strh r1, [r3]
adds r2, #2
adds r3, #2
adds r7, #1
b padloop
done:
adds r0, r6, #0
pop {r4, r5, r6, r7, pc}
"""

# In: r1 = syllable index.  Out: r1 = font code of the slot now holding it.
# Every other low register is preserved.
LOOKUP = """push {r0, r2, r3, r4, r5, r6, r7, lr}
adds r0, r1, #0
ldr r7, cache
ldr r6, [r7]
adds r6, #1
str r6, [r7]
mov r12, r6
movs r5, #0
ldr r4, slots
ldr r3, maxstamp
movs r2, #0
scan:
cmp r5, r4
bge miss
lsls r1, r5, #1
adds r1, #4
ldrh r1, [r7, r1]
cmp r1, r0
beq found
lsls r1, r5, #2
ldr r6, stampoff
adds r1, r1, r6
ldr r1, [r7, r1]
cmp r1, r3
bhs next
adds r3, r1, #0
adds r2, r5, #0
next:
adds r5, #1
b scan
miss:
adds r5, r2, #0
lsls r1, r5, #1
adds r1, #4
strh r0, [r7, r1]
found:
lsls r1, r5, #2
ldr r6, stampoff
adds r1, r1, r6
mov r6, r12
str r6, [r7, r1]
lsls r1, r0, #1
ldr r6, glyphmap
ldrh r1, [r6, r1]
lsls r1, r1, #6
ldr r6, glyphs
adds r6, r6, r1
ldr r3, codes
ldrb r5, [r3, r5]
lsls r3, r5, #6
ldr r1, vram
adds r3, r3, r1
movs r2, #16
copy:
ldmia r6!, {r1}
stmia r3!, {r1}
subs r2, #1
bne copy
adds r1, r5, #0
pop {r0, r2, r3, r4, r5, r6, r7, pc}
"""


def install(rom: bytearray, append, write, version: str, glyphs_at: int, map_at: int) -> dict:
    """Needs the name_hangul glyph blob and syllable map already in the ROM."""
    C_ENTRY, D_ENTRY = ENTRIES[version]
    for at, exp in ((C_ENTRY, C_EXPECTED), (D_ENTRY, D_EXPECTED)):
        o = at - 0x08000000
        if rom[o:o + len(exp)] != exp:
            raise ValueError("tilemap writer at %08X differs" % at)
    codes_at = append(bytes(SLOT_CODES), "tile cache slot codes")
    pool = {"cache": CACHE, "slots": len(SLOT_CODES), "maxstamp": 0xFFFFFFFF, "stampoff": STAMPS,
            "glyphmap": 0x08000000 + map_at, "glyphs": 0x08000000 + glyphs_at,
            "codes": 0x08000000 + codes_at, "vram": FONT_VRAM}
    l_at, l_list = place(rom, append, LOOKUP, pool, "tile cache lookup")
    b_at, b_list = place(rom, append, BODY, {"lookup": 0x08000001 + l_at}, "tile cache tilemap writer")
    # d_entry sits after "push; b body" (4 bytes).
    for entry, target in ((C_ENTRY, b_at), (D_ENTRY, b_at + 4)):
        stub, _ = assemble("ldr r1, target\nbx r1\n", entry, {"target": 0x08000001 + target})
        if len(stub) != 8:
            raise ValueError("entry stub is not 8 bytes")
        o = entry - 0x08000000
        write(o, stub, "tilemap writer entry %08X -> cache body" % entry, bytes(rom[o:o + 8]))
    return {"lookup": l_at, "body": b_at, "codes": codes_at, "slots": len(SLOT_CODES),
            "listing": l_list + b_list}
