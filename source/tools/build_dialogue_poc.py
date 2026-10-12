#!/usr/bin/env python3
"""EXE5 dialogue visibility PoC: FA FC + u16 Hangul in the normal dialogue path.

What it changes (NON-DISTRIBUTION development build):
  * appends a font view = the source's first 484 glyph records (every index the
    E4-extended encoding can reach, copied byte for byte) + 11,172 Hangul
    glyphs, and a matching u32 advance table; repoints the four IWRAM-source
    literals of the two dialogue renderers to it;
  * appends a Thumb-1 FA handler and points control-table slot FA at it.
    FA FC lo hi draws syllable U+AC00+lo|hi<<8 in either loop (one character
    per frame, or instant), mirroring the source's E4 path in that loop and
    resuming at that loop's continuation; any other FA tail-calls the source
    handler unchanged;
  * recompiles the selected archives from TPL with Korean substituted, keeps
    each archive's storage form (raw / LZ77 with size header), appends it and
    rewrites every pointer literal to it (bit 31 preserved).

Gates: input SHA-256, expected bytes at every write, function signatures,
Thumb-1 assemble/disassemble round trip, unchanged TPL->MSG byte identity,
untranslated-script byte identity, re-decode of written strings, and an
Expected Write ledger checked against the full diff.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(ROOT.parents[2] / "록맨 에그제 4/_work/exe4-kr/external/arm_debug_python"))

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, __version__ as CS_VERSION  # noqa: E402
from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB, __version__ as KS_VERSION  # noqa: E402

from decode_archives import payload  # noqa: E402
from exe5_profiles import FUNCTION_SIGNATURES, IWRAM_BASE, IWRAM_ROM_BASE, PROFILES  # noqa: E402
from lz77 import compress, lz77_decompress  # noqa: E402

TEXTPET = ROOT / "external/TextPet-v1.0.0/TextPet.exe"
PLUGINS = ROOT / "external/textpet-plugins"
LEGACY = 0x1E4          # E4 xx reaches index 0xE4+0xFF = 0x1E3
HANGUL = 11172
GLYPH = 0x60
ADVANCE = 12


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- font
def hangul_glyphs(bdf: Path) -> dict[str, bytes]:
    """Galmuri BDF -> EXE5 dialogue records: 16x12, 4bpp, ink 1 on 0, no shadow."""
    found = {}
    for block in bdf.read_text(encoding="utf-8").split("STARTCHAR ")[1:]:
        lines = block.splitlines()
        cp = int(next(x.split()[1] for x in lines if x.startswith("ENCODING ")))
        if not 0xAC00 <= cp < 0xAC00 + HANGUL:
            continue
        w, h, xoff, yoff = map(int, next(x for x in lines if x.startswith("BBX ")).split()[1:])
        start = lines.index("BITMAP") + 1
        rows = [int(x, 16) for x in lines[start:start + h]]
        top = 11 - h - yoff
        if w + xoff > 12 or xoff < 0 or top < 0 or top + h > 12:
            raise ValueError("glyph does not fit 12x12: U+%04X" % cp)
        grid = [[0] * 16 for _ in range(12)]
        stride = ((w + 7) // 8) * 8
        ink = 0
        for y, row in enumerate(rows):
            for x in range(w):
                if row & (1 << (stride - 1 - x)):
                    grid[top + y][xoff + x] = 1
                    ink += 1
        if not ink:
            raise ValueError("empty glyph U+%04X" % cp)
        found[chr(cp)] = bytes(grid[y][x] | grid[y][x + 1] << 4 for y in range(12) for x in range(0, 16, 2))
    if len(found) != HANGUL:
        raise ValueError("BDF supplies %d/%d Hangul syllables" % (len(found), HANGUL))
    return found


# ---------------------------------------------------------------- Thumb
def assemble(code: str, address: int, literals: dict[str, int]):
    if KS_VERSION != "0.9.2" or CS_VERSION != "5.0.7":
        raise ValueError("ARM toolchain version drift")
    header = ".syntax unified\n.cpu arm7tdmi\n.thumb\n"
    pool = "\n".join("%s: .word %d" % (k, v) for k, v in literals.items())
    blob = bytes(Ks(KS_ARCH_ARM, KS_MODE_THUMB).asm(header + code + "\n.balign 4\n" + pool, address)[0])
    count = sum(1 for line in code.splitlines() if line.strip() and not line.strip().endswith(":"))
    length = count * 2
    insns = list(Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(blob[:length], address))
    if len(insns) != count or any(i.size != 2 for i in insns):
        raise ValueError("not a complete Thumb-1 instruction sequence")
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB)
    for i in insns:
        if bytes(ks.asm(header + i.mnemonic + " " + i.op_str, i.address)[0]) != i.bytes:
            raise ValueError("assemble/disassemble disagreement at %x" % i.address)
        if i.mnemonic.startswith("b") and i.mnemonic not in ("bx", "bics", "bl"):
            target = int(i.op_str.lstrip("#"), 0)
            if not address <= target < address + length:
                raise ValueError("branch leaves the handler at %x" % i.address)
        if i.mnemonic == "ldr" and "[pc," in i.op_str:
            lit = ((i.address + 4) & ~3) + (int.from_bytes(i.bytes, "little") & 0xFF) * 4
            if not address + length <= lit < address + len(blob):
                raise ValueError("literal load outside pool at %x" % i.address)
    start = (length + 3) & ~3
    values = [int.from_bytes(blob[k:k + 4], "little") for k in range(start, len(blob), 4)]
    if values != list(literals.values()):
        raise ValueError("literal pool mismatch")
    return blob, [{"address": "0x%08X" % i.address, "hex": i.bytes.hex(), "asm": i.mnemonic + " " + i.op_str}
                  for i in insns]


def call(label: str) -> str:
    return "ldr r7, %s\nmov lr, pc\nbx r7\n" % label


INDEX = """ldrb r1, [r4, #3]
lsls r1, r1, #8
ldrb r2, [r4, #2]
adds r1, r1, r2
ldr r2, bias
adds r1, r1, r2
"""

# FA FD a0 a1 a2 a3: continue the stream at the little-endian address a0..a3.
# Read byte by byte (the command is unaligned). Returns r0=1: the normal loop
# keeps going this frame, the instant loop ignores r0.
JUMP = """jump:
ldrb r1, [r4, #5]
lsls r1, r1, #8
ldrb r2, [r4, #4]
orrs r1, r2
lsls r1, r1, #8
ldrb r2, [r4, #3]
orrs r1, r2
lsls r1, r1, #8
ldrb r2, [r4, #2]
orrs r1, r2
movs r4, r1
movs r0, #1
mov pc, lr
"""

HANDLER = ("""ldrb r1, [r4, #1]
cmp r1, #0xfc
beq hangul
cmp r1, #0xfd
beq jump
ldr r7, legacy
bx r7
""" + JUMP + """hangul:
ldrb r0, [r5, #0x11]
cmp r0, #0
beq fast
movs r0, #1
""" + call("flag_clear") + """movs r0, #0
ldrb r2, [r5, #9]
cmp r2, #0
bgt delay
ldrb r2, [r5, #8]
strb r2, [r5, #9]
movs r0, #0x40
""" + call("flag_test") + """bne draw
movs r2, #0x68
ldrh r0, [r5, r2]
""" + call("sound") + """draw:
""" + INDEX + """movs r0, #0
ldr r6, [r5, #0x7c]
""" + call("renderer") + """adds r4, #4
""" + call("mouth") + """movs r0, #1
b normal_resume
delay:
subs r2, #1
strb r2, [r5, #9]
movs r0, #0
normal_resume:
ldr r7, cont_normal
bx r7
fast:
ldr r0, fast_mask
""" + call("flag_set") + INDEX + """movs r0, #0
ldr r6, [r5, #0x7c]
""" + call("renderer") + call("ctrl_done") + """adds r4, #4
ldr r7, cont_fast
bx r7
""")


RENDERER = """push {r1, r4, r5, r6, r7, lr}
mov r7, r8
mov r2, sb
mov r3, sl
mov r4, ip
push {r2, r3, r4, r7}
ldr r3, bitmap
lsrs r4, r6, #5
lsls r4, r4, #2
adds r2, r3, r4
lsls r4, r4, #3
subs r3, r6, r4
ldr r4, font
movs r7, #0x60
muls r7, r1, r7
adds r7, r7, r4
ldr r4, widths
lsls r1, r1, #2
ldr r4, [r4, r1]
push {r4}
push {r6}
ldr r6, [r5, #0x70]
adds r6, r6, r4
str r6, [r5, #0x70]
pop {r6}
lsls r4, r4, #2
adds r6, r6, r4
str r6, [r5, #0x7c]
subs r4, #0x40
rsbs r4, r4, #0
ldr r6, pal_off
ldrh r6, [r5, r6]
lsls r6, r6, #2
ldr r0, pal_table
ldr r0, [r0, r6]
mov ip, r0
pop {r6}
{ROWS}row:
push {r3}
mov r3, ip
ldr r0, [r7]
ldr r1, [r7, #4]
adds r0, r0, r3
adds r1, r1, r3
lsls r1, r4
lsrs r1, r4
pop {r3}
push {r4, r6}
push {r2}
movs r4, #0x20
subs r4, r4, r3
ldr r2, [r2]
adds r6, r0, #0
lsls r6, r3
orrs r6, r2
adds r2, r1, #0
lsls r2, r3
lsrs r0, r4
orrs r0, r2
lsrs r1, r4
pop {r2}
str r6, [r2]
str r0, [r2, #4]
str r1, [r2, #8]
adds r7, #8
movs r0, #0x60
adds r2, r2, r0
pop {r4, r6}
subs r6, #1
bge row
pop {r2, r3, r4, r7}
mov r8, r7
mov sb, r2
mov sl, r3
mov ip, r4
pop {r1, r4, r5, r6, r7, pc}
"""


def verify_renderer_transcription(src: bytes, rom_off: int, runtime: int, pool: dict) -> None:
    """The clone source without its change must equal the source renderer
    instruction for instruction (pc-relative loads compared by loaded value)."""
    def listing(code: bytes, address: int, base: bytes, base_addr: int):
        out = []
        for i in Cs(CS_ARCH_ARM, CS_MODE_THUMB).disasm(code, address):
            if i.mnemonic == "ldr" and "[pc," in i.op_str:
                lit = ((i.address + 4) & ~3) + (int.from_bytes(i.bytes, "little") & 0xFF) * 4
                value = struct.unpack_from("<I", base, lit - base_addr)[0]
                out.append(("ldr", i.op_str.split(",")[0], value))
            elif i.mnemonic.startswith("b") and i.mnemonic not in ("bx", "bics"):
                out.append((i.mnemonic, int(i.op_str.lstrip("#"), 0) - address))
            else:
                out.append((i.mnemonic, i.op_str))
            if i.mnemonic == "pop" and "pc" in i.op_str:
                break
        return out
    original = listing(src[rom_off:rom_off + 0xC0], runtime, src[rom_off:rom_off + 0xC0], runtime)
    plain, _ = assemble(RENDERER.replace("{ROWS}", ""), runtime, {
        "bitmap": pool["bitmap"], "font": pool["font"], "widths": pool["widths"],
        "pal_off": pool["pal_off"], "pal_table": pool["pal_table"]})
    mine = listing(plain, runtime, plain, runtime)
    if mine != original:
        diff = next(k for k in range(min(len(mine), len(original))) if mine[k] != original[k])
        raise SystemExit("renderer transcription differs at instruction %d: %r vs %r"
                         % (diff, mine[diff], original[diff]))


# ---------------------------------------------------------------- TextPet
def textpet(args: list[str]) -> None:
    run = subprocess.run([str(TEXTPET), "silent", *args], capture_output=True, text=True, encoding="utf-8")
    if run.returncode or "Done." not in (run.stdout or ""):
        raise RuntimeError("TextPet failed: %s %s" % (run.stdout[-500:], run.stderr[-500:]))


def compile_tpls(tpls: dict[str, str], syllables: set[str]) -> dict[str, bytes]:
    with tempfile.TemporaryDirectory(prefix="exe5-build-") as name:
        temp = Path(name)
        plugins = temp / "plugins"
        shutil.copytree(PLUGINS, plugins)
        table = plugins / "exe5-utf8.tbl"
        extra = "".join("\nFAFC%s=%s" % ((ord(c) - 0xAC00).to_bytes(2, "little").hex().upper(), c)
                        for c in sorted(syllables))
        table.write_text(table.read_text(encoding="utf-8").rstrip("\n") + extra + "\n", encoding="utf-8")
        src, out = temp / "in", temp / "out"
        src.mkdir()
        out.mkdir()
        for stem, text in tpls.items():
            (src / (stem + ".tpl")).write_text(text, encoding="utf-8")
        textpet(["load-plugins", str(plugins) + "\\", "game", "exe5",
                 "read-text-archives", str(src) + "\\", "-f", "tpl",
                 "write-text-archives", str(out) + "\\", "-f", "bin"])
        result = {stem: (out / (stem + ".msg")).read_bytes() for stem in tpls}
        # Independent re-decode with the same extended table: what was written.
        back = temp / "back"
        back.mkdir()
        textpet(["load-plugins", str(plugins) + "\\", "game", "exe5",
                 "read-text-archives", str(out) + "\\", "-f", "bin",
                 "write-text-archives", str(back) + "\\", "-f", "tpl"])
        redecoded = {stem: (back / (stem + ".tpl")).read_text(encoding="utf-8") for stem in tpls}
    return result, redecoded


STRING = re.compile(r'"""\n(.*?)\n\t"""|"((?:[^"\\]|\\.)*)"', re.S)


def strings_of(tpl: str) -> list[str]:
    out = []
    for block, single in STRING.findall(tpl):
        if block:
            out.append("\n".join(line[1:] if line.startswith("\t") else line for line in block.split("\n")))
        else:
            out.append(single)
    return out


SCRIPT_SPLIT = re.compile(r"(?m)^(script \d+ (\S+) \{)$")
DIALOGUE_DB = "mmbn5"
TEXT_DBS = (DIALOGUE_DB, "mmbn5s")   # menus too, since every FA renderer takes FA FC


def substitute(tpl: str, by_source: dict[str, str]) -> tuple[str, int]:
    """Replace translated string literals inside dialogue (mmbn5) and menu
    (mmbn5s) scripts.  Menu scripts were left byte for byte until the name
    renderers A/B/C/D took FA FC (tools/name_hangul.py, name_tilecache.py).
    Translations are always written as
    a quoted string with real line breaks: a \"\"\" block whose first line is
    empty loses that line break when TextPet reads it."""
    count = 0

    def repl(m):
        nonlocal count
        block, single = m.group(1), m.group(2)
        body = ("\n".join(line[1:] if line.startswith("\t") else line for line in block.split("\n"))
                if block is not None else single)
        if body not in by_source:
            return m.group(0)
        count += 1
        ko = by_source[body]
        if '"' in ko:
            raise SystemExit("double quote in translation: %r" % ko)
        return '"%s"' % ko

    parts = SCRIPT_SPLIT.split(tpl.replace("\r\n", "\n"))
    out = [parts[0]]
    for i in range(1, len(parts), 3):
        head, db, body = parts[i], parts[i + 1], parts[i + 2]
        out.append(head)
        out.append(STRING.sub(repl, body) if db in TEXT_DBS else body)
    return "".join(out), count


def script_slices(msg: bytes) -> list[bytes]:
    size = struct.unpack_from("<H", msg)[0]
    offs = list(struct.unpack_from("<%dH" % (size // 2), msg)) + [len(msg)]
    return [msg[offs[i]:offs[i + 1]] for i in range(size // 2)]


# ---------------------------------------------------------------- build
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--version", choices=PROFILES, required=True)
    ap.add_argument("--font", type=Path, required=True)
    ap.add_argument("--translation", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    prof = PROFILES[args.version]
    src = (ROOT.parents[1] / prof["rom_name"]).read_bytes()
    if sha(src) != prof["sha256"]:
        raise SystemExit("input ROM SHA-256 mismatch")
    for key, sig in FUNCTION_SIGNATURES.items():
        a = prof[key] & ~1
        off = a - IWRAM_BASE + IWRAM_ROM_BASE if a < 0x08000000 else a - 0x08000000
        if src[off:off + len(sig) // 2].hex() != sig:
            raise SystemExit("function signature drift: " + key)

    rom = bytearray(src)
    ledger = []        # Expected Write: (offset, length, owner)
    append_at = len(rom)

    def write(offset: int, data: bytes, owner: str, expected: bytes | None = None):
        if expected is not None and bytes(rom[offset:offset + len(expected)]) != expected:
            raise SystemExit("expected-bytes mismatch at %X (%s)" % (offset, owner))
        rom[offset:offset + len(data)] = data
        ledger.append({"offset": offset, "length": len(data), "owner": owner, "sha256": sha(data)})

    def append(data: bytes, owner: str) -> int:
        while len(rom) % 4:
            rom.append(0xFF)
        at = len(rom)
        rom.extend(data)
        ledger.append({"offset": at, "length": len(data), "owner": owner, "sha256": sha(data)})
        return at

    # Font view and advances.
    glyphs = hangul_glyphs(args.font)
    font_view = bytes(src[prof["font"]:prof["font"] + LEGACY * GLYPH]) + b"".join(
        glyphs[chr(0xAC00 + i)] for i in range(HANGUL))
    width_view = bytes(src[prof["width"]:prof["width"] + LEGACY * 4]) + ADVANCE.to_bytes(4, "little") * HANGUL
    font_at = append(font_view, "font view: 484 source records + 11172 Hangul")
    width_at = append(width_view, "advance view: 484 source entries + 11172 x %d" % ADVANCE)
    for lit in prof["font_literals"]:
        write(lit, (0x08000000 + font_at).to_bytes(4, "little"), "renderer font literal",
              (0x08000000 + prof["font"]).to_bytes(4, "little"))
    for lit in prof["width_literals"]:
        write(lit, (0x08000000 + width_at).to_bytes(4, "little"), "renderer advance literal",
              (0x08000000 + prof["width"]).to_bytes(4, "little"))

    # Hangul renderer: the source dialogue renderer re-assembled into ROM with
    # one change. The source loops `advance + 1` rows (its row counter is the
    # advance it just looked up); at advance 12 that draws a 13th row, which on
    # the third line is bitmap row 40 = the first tile of the staging buffer
    # 0x0200D800, i.e. line 1's first cell. The clone always draws 12 rows.
    ren_rom = (prof["renderer"] & ~1) - IWRAM_BASE + IWRAM_ROM_BASE
    pool = {name: struct.unpack_from("<I", src, ren_rom + off)[0]
            for name, off in (("font", 0x98), ("bitmap", 0x9C), ("widths", 0xA0), ("pal_table", 0xA4),
                              ("pal_off", 0xB8))}
    if (pool["font"], pool["widths"], pool["bitmap"], pool["pal_off"]) != (
            0x08000000 + prof["font"], 0x08000000 + prof["width"], 0x0200C900, 0x1D0):
        raise SystemExit("renderer literal pool drift")
    verify_renderer_transcription(src, ren_rom, prof["renderer"] & ~1, pool)
    while len(rom) % 4:
        rom.append(0xFF)
    clone_at = len(rom)
    clone, clone_listing = assemble(RENDERER.replace("{ROWS}", "movs r6, #11\n"), 0x08000000 + clone_at, {
        "bitmap": pool["bitmap"], "font": 0x08000000 + font_at, "widths": 0x08000000 + width_at,
        "pal_off": pool["pal_off"], "pal_table": pool["pal_table"]})
    if append(clone, "Hangul renderer (12 rows)") != clone_at:
        raise SystemExit("renderer clone moved after assembly")

    # Handler.
    literals = {
        "legacy": prof["fa_legacy"], "flag_clear": prof["flag_clear"], "flag_test": prof["flag_test"],
        "sound": prof["sound"], "bias": LEGACY, "renderer": 0x08000001 + clone_at, "mouth": prof["mouth"],
        "cont_normal": prof["cont_normal"], "fast_mask": 0x840, "flag_set": prof["flag_set"],
        "ctrl_done": prof["ctrl_done"], "cont_fast": prof["cont_fast"],
    }
    while len(rom) % 4:
        rom.append(0xFF)
    handler_at = len(rom)
    blob, listing = assemble(HANDLER, 0x08000000 + handler_at, literals)
    if append(blob, "FA FC handler") != handler_at:
        raise SystemExit("handler moved after assembly")
    write(prof["fa_slot"], (0x08000001 + handler_at).to_bytes(4, "little"), "control table FA slot",
          prof["fa_legacy"].to_bytes(4, "little"))

    # The other renderers of the same FA FC stream (menus, chip/virus/navi
    # names): A the 8x16 name copier (IWRAM), B the proportional 12-row
    # renderer, C/D the preloaded-font tilemap writers through a VRAM tile
    # cache.  See tools/name_hangul.py and tools/name_tilecache.py.
    import name_hangul
    import name_tilecache
    names = name_hangul.install(rom, append, write)
    tiles = name_tilecache.install(rom, append, write, args.version, names["glyphs"], names["map"])
    prop = name_hangul.install_prop(rom, append, write, args.version, font_at, width_at)
    name_slots = names["slots"]
    # PET main menu labels are pixels, not text (tools/pet_labels.py).
    import pet_labels
    pet = pet_labels.build(rom, append, write, args.version,
                           (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import sort_labels
    pet["sort"] = sort_labels.build(rom, append, write,
                                    (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import tx_panel
    pet["transmission"] = tx_panel.build(rom, write, (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import tab_labels
    pet["tabs"] = tab_labels.build(rom, append, write, (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import title_menu
    pet["title_menu"] = title_menu.build(rom, append, write, (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import map_labels
    colonel_src = (ROOT.parents[1] / PROFILES["colonel"]["rom_name"]).read_bytes()
    pet["map_labels"] = map_labels.build(rom, append, write, colonel_src)
    pet["map_hint"] = map_labels.build_hint(rom, append, write, colonel_src)
    import puzzle_letters
    pet["puzzle_letters"] = puzzle_letters.build(rom, append, write, colonel_src)
    import result_labels
    pet["result"] = result_labels.build(rom, write, (ROOT.parents[1] / PROFILES["blues"]["rom_name"]).read_bytes())
    import logo_subtitle
    if args.version in logo_subtitle.LOGO:
        pal = struct.unpack_from("<256H", (ROOT / ("translations/menu_sources/title_palette_%s.bin" % args.version)).read_bytes())
        pet["logo"] = logo_subtitle.build(rom, append, write, args.version,
                                          [((c & 31) << 3, (c >> 5 & 31) << 3, (c >> 10 & 31) << 3) for c in pal])

    # Text.
    tr = load_translation(args.translation)
    by_source = tr["by_source"]
    catalog = {a["rom_offset"]: a for a in json.loads(
        (ROOT / "analysis" / ("archives_%s.json" % args.version.capitalize())).read_text(encoding="utf-8"))["archives"]}
    tpls, originals, used = {}, {}, set()
    if tr["archives"] == "auto":
        # Every text archive (population) holding a translated dialogue string.
        pop = json.loads((ROOT / "analysis" / ("population_%s.json" % args.version)).read_text(encoding="utf-8"))
        selected = [int(a["archive"], 16) for a in pop["archives"]]
    else:
        selected = resolve_archives(tr, args.version)
    for offset in selected:
        stem = "%07X" % offset
        text = (ROOT / "analysis/tpl" / args.version / (stem + ".tpl")).read_text(encoding="utf-8")
        new, n = substitute(text, by_source)
        if n == 0:
            if tr["archives"] == "auto":
                continue
            raise SystemExit("no translated string in archive " + stem)
        originals[stem] = text
        tpls[stem] = new
        used.add(stem)
    korean = {c for v in by_source.values() for c in v if 0xAC00 <= ord(c) < 0xAC00 + HANGUL}
    stray = {c for v in by_source.values() for c in v if 0x1100 <= ord(c) <= 0x11FF or 0x3130 <= ord(c) <= 0x318F}
    if stray:
        raise SystemExit("jamo cannot be encoded: " + "".join(sorted(stray)))
    compiled, redecoded = compile_tpls(tpls, korean)
    compiled.update({k + "_orig": v for k, v in compile_tpls(originals, set())[0].items()})
    report_text = []
    for stem in tpls:
        item = catalog[int(stem, 16)]
        source_payload = payload(src, item)
        if compiled[stem + "_orig"] != source_payload:
            raise SystemExit("unchanged TPL does not reproduce the source payload: " + stem)
        new_msg = compiled[stem]
        old_s, new_s = script_slices(source_payload), script_slices(new_msg)
        old_t, new_t = strings_of(originals[stem]), strings_of(tpls[stem])
        if len(old_s) != len(new_s):
            raise SystemExit("script count changed: " + stem)
        changed_scripts = [i for i in range(len(old_s)) if old_s[i] != new_s[i]]
        # Every changed script must be one whose text we substituted.
        per_script_src = split_scripts(originals[stem])
        per_script_new = split_scripts(tpls[stem])
        for i in changed_scripts:
            if per_script_src.get(i) == per_script_new.get(i):
                raise SystemExit("script %d of %s changed bytes without a text change" % (i, stem))
        def same_text(xs):  # the escape \n and a real line break are the same byte (E9)
            return [x.replace("\\n", "\n") for x in xs]
        if same_text(strings_of(redecoded[stem])) != same_text(new_t):
            raise SystemExit("re-decoded strings differ from the authored strings: " + stem)
        if len(old_t) != len(new_t):
            raise SystemExit("string count changed: " + stem)
        # Rebuild the stored form exactly as the source stores it.
        ram_bytes = None
        if item["storage"] == "lz77":
            # Compressed archives are unpacked into fixed RAM slots (0x7B083C:
            # 184 bytes at 0x0203E000, the text-box tilemap right after it).
            # The translated archive lives whole in ROM; the RAM copy keeps
            # unchanged scripts and turns each changed one into FA FD <ROM>.
            body_at = append(new_msg, "ROM body of archive %s" % stem)
            ram = stub_archive(source_payload, new_msg, 0x08000000 + body_at)
            if len(ram) > len(source_payload):
                raise SystemExit("RAM copy of %s grows %d -> %d bytes" % (stem, len(source_payload), len(ram)))
            ram_bytes = len(ram)
            raw, _ = lz77_decompress(src, item["rom_offset"])
            head = raw[:item["size_header"]]
            body = ram
            if item["size_header"]:
                body = ((len(body) + 4) << 8).to_bytes(4, "little") + body
                if (struct.unpack_from("<I", head)[0] & 0xFF) != 0:
                    raise SystemExit("unexpected size-header low byte: " + stem)
            stored = compress(body)
            check, _ = lz77_decompress(stored + b"\0" * 8, 0)
            if check != body:
                raise SystemExit("LZ77 round trip failed: " + stem)
        else:
            stored = new_msg
        at = append(stored, "archive %s (%s)" % (stem, item["storage"]))
        for ref in item["references"]:
            old = struct.unpack_from("<I", src, ref)[0]
            new = (old & 0x80000000) | (0x08000000 + at)
            write(ref, new.to_bytes(4, "little"), "pointer to archive " + stem, old.to_bytes(4, "little"))
        report_text.append({"archive": stem, "storage": item["storage"], "new_offset": "0x%X" % at,
                            "scripts_changed": changed_scripts, "strings": len(new_t),
                            "pointers": len(item["references"]),
                            "payload_bytes": [len(source_payload), len(new_msg)],
                            "ram_bytes": [len(source_payload), ram_bytes]})

    while len(rom) % 0x10:
        rom.append(0xFF)
    # Expected Write ledger vs the actual diff.
    covered = bytearray(len(rom))
    for w in ledger:
        covered[w["offset"]:w["offset"] + w["length"]] = b"\1" * w["length"]
    for i in range(len(src)):
        if rom[i] != src[i] and not covered[i]:
            raise SystemExit("untracked write at %X" % i)
    for i in range(len(src), len(rom)):
        if not covered[i] and rom[i] not in (0xFF, 0x00):
            raise SystemExit("untracked appended byte at %X" % i)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(rom)
    report = {
        "kind": "exe5_dialogue_visibility_poc", "distribution": "NON-DISTRIBUTION",
        "version": args.version, "source_sha256": prof["sha256"], "output_sha256": sha(bytes(rom)),
        "output_bytes": len(rom), "encoding": "FA FC + u16 LE syllable index from U+AC00",
        "glyph_index_bias": LEGACY, "font_view": "0x%X" % font_at, "advance_view": "0x%X" % width_at,
        "handler": "0x%X" % handler_at, "handler_listing": listing, "text": report_text,
        "name_renderers": {"A_handler": "0x%X" % names["handler"], "name_glyphs": "0x%X" % names["glyphs"],
                           "tile_cache_body": "0x%X" % tiles["body"], "tile_cache_slots": tiles["slots"],
                           "B_handler": "0x%X" % prop["handler"], "pet_labels": pet,
                           "listing": names["listing"] + tiles["listing"] + prop["listing"]},
        "hangul_used": len(korean), "ledger": ledger,
        "font": {"path": str(args.font), "sha256": sha(args.font.read_bytes())},
    }
    args.out.with_suffix(".json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                                              encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("version", "output_sha256", "output_bytes", "handler", "hangul_used")},
                     ensure_ascii=False))
    for t in report_text:
        print(t)


def table_of(msg: bytes) -> list[int]:
    n = struct.unpack_from("<H", msg)[0] // 2
    return list(struct.unpack_from("<%dH" % n, msg))


def body_at(msg: bytes, offs: list[int], i: int) -> bytes:
    later = [o for o in offs if o > offs[i]]
    return msg[offs[i]:min(later) if later else len(msg)]


def stub_archive(old: bytes, new: bytes, rom_body: int) -> bytes:
    """RAM archive: same table shape as `old`; a script whose bytes changed
    becomes FA FD <rom_body + its offset in `new`>, others keep their bytes.
    Aliases (equal table values) stay aliases."""
    old_offs, new_offs = table_of(old), table_of(new)
    if len(old_offs) != len(new_offs):
        raise SystemExit("table length changed")
    for i in range(len(old_offs)):
        for j in range(i):
            if (old_offs[i] == old_offs[j]) != (new_offs[i] == new_offs[j]):
                raise SystemExit("alias structure changed")
    changed = {old_offs[i] for i in range(len(old_offs))
               if body_at(old, old_offs, i) != body_at(new, new_offs, i)}
    first = {}
    for i, o in enumerate(old_offs):
        first.setdefault(o, i)
    out = bytearray(len(old_offs) * 2)
    place = {}
    for o in sorted(first):
        place[o] = len(out)
        i = first[o]
        if o in changed:
            out += b"\xfa\xfd" + (rom_body + new_offs[i]).to_bytes(4, "little")
        else:
            out += body_at(old, old_offs, i)
    for i, o in enumerate(old_offs):
        struct.pack_into("<H", out, i * 2, place[o])
    return bytes(out)


def load_translation(path: Path) -> dict:
    """A single translation JSON, or the directory translations/story: every
    batch_*.json merged (their by_source; skip entries stay Japanese) and
    archives chosen automatically. A source translated twice must agree
    (check_translations.py enforces it; this re-checks)."""
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    merged: dict[str, str] = {}
    for f in sorted(path.glob("batch_*.json")):
        for k, v in json.loads(f.read_text(encoding="utf-8"))["by_source"].items():
            if k in merged and merged[k] != v:
                raise SystemExit("conflicting translation for %r (%s)" % (k[:30], f.name))
            merged[k] = v
    return {"archives": "auto", "by_source": merged}


def split_scripts(tpl: str) -> dict[int, str]:
    parts = re.split(r"^script (\d+) \S+ \{", tpl, flags=re.M)
    return {int(parts[i]): parts[i + 1] for i in range(1, len(parts), 2)}


def resolve_archives(tr: dict, version: str) -> list[int]:
    if version in tr["archives"]:
        return tr["archives"][version]
    pairs = json.loads((ROOT / "analysis/version_pairs.json").read_text(encoding="utf-8"))["pairs"]
    out = []
    for offset in tr["archives"]["blues"]:
        match = [p[version] for p in pairs if offset in p["blues"]]
        if len(match) != 1 or len(match[0]) != 1:
            raise SystemExit("archive %X has no unique %s counterpart" % (offset, version))
        out.append(match[0][0])
    return out


if __name__ == "__main__":
    main()
