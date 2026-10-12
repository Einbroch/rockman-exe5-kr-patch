"""Visibility PoC for tools/name_hangul.py on the chip name archive.

Takes the story build, installs the name renderer's FA FC handler, rebuilds
the chip name archive (0..255) with a few names in Hangul at the ROM end and
repoints every reference to it.  Output: poc/output/exe5_<ver>_names_poc.gba.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from name_hangul import encode_factory, install, install_prop  # noqa: E402
import name_tilecache  # noqa: E402

ARCHIVE = {"blues": 0x74B3C0, "colonel": 0x74C830}
TEST = {0: "록버스터", 1: "캐논", 2: "하이캐논", 3: "메가캐논"}


def main():
    ver = sys.argv[1] if len(sys.argv) > 1 else "blues"
    rom = bytearray((ROOT / ("poc/output/exe5_%s_story.gba" % ver)).read_bytes())

    def append(data, owner):
        while len(rom) % 4:
            rom.append(0xFF)
        at = len(rom)
        rom.extend(data)
        return at

    info = install(rom, append)
    encode = encode_factory(info["slots"])
    tc = name_tilecache.install(rom, append, info["glyphs"], info["map"])
    info["listing"] += tc["listing"]
    fv, wv = (struct.unpack_from("<I", rom, a)[0] - 0x08000000 for a in (0x1C9030, 0x1C9038))
    pr = install_prop(rom, append, fv, wv)
    info["listing"] += pr["listing"]

    base = ARCHIVE[ver]
    first = struct.unpack_from("<H", rom, base)[0]
    count = first // 2
    offs = list(struct.unpack_from("<%dH" % count, rom, base))
    bodies = []
    for i in range(count):
        end = rom.index(0xE6, base + offs[i]) + 1      # every name ends with E6
        bodies.append(bytes(rom[base + offs[i]:end]))
    for i, text in TEST.items():
        bodies[i] = b"".join(encode(c) for c in text) + b"\xe6"
    table, blob = [], b""
    for b in bodies:
        table.append(count * 2 + len(blob))
        blob += b
    new = struct.pack("<%dH" % count, *table) + blob
    at = append(new, "chip names")
    refs = [i for i in range(0, 0x800000, 4) if struct.unpack_from("<I", rom, i)[0] == 0x08000000 + base]
    for r in refs:
        struct.pack_into("<I", rom, r, 0x08000000 + at)
    out = ROOT / ("poc/output/exe5_%s_names_poc.gba" % ver)
    out.write_bytes(rom)
    print(json.dumps({"out": str(out), "sha256": hashlib.sha256(rom).hexdigest(), "handler": hex(info["handler"]),
                      "archive": hex(at), "refs": [hex(r) for r in refs]}, indent=1))
    for line in info["listing"]:
        print(line["address"], line["asm"])


if __name__ == "__main__":
    main()
