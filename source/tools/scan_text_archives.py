#!/usr/bin/env python3
"""List every text archive an EXE5 ROM points at.

A text archive is found by what points at it, not by its shape alone (a u16
boundary table is just rising numbers): a u32 literal equal to
0x08000000+offset (bit 31 may mark compression), and at that offset either a
raw boundary table or an LZ77 (0x10) stream whose decompressed data holds one.
The first table value must equal the table's own byte size.

References are searched at EVERY byte offset, not only aligned words: cutscene
bytecode stores archive pointers unaligned (the opening scene's archive
0x7B083C is reachable only from 0x8C577). Each reference records its
alignment so relocation rewrites all of them.

The last table value is the START of the last script, not the archive's end.
Compressed archives therefore keep their whole decompressed payload; LZ77
data often begins with a 4-byte size header (u32 >> 8 == decompressed length).
Raw archives get a provisional window here; decode_archives.py fixes the exact
end by TextPet re-encoding.
"""
from __future__ import annotations

import argparse
import collections
import json
import struct
from pathlib import Path

ROM_BASE = 0x08000000
MIN_TABLE, MAX_TABLE = 4, 4096
MAX_ARCHIVE = 0x10000


def lz77_decompress(rom: bytes, offset: int, limit: int = 0x40000):
    """GBA BIOS LZ77 (type 0x10). Returns (data, compressed_length) or None."""
    if offset + 4 > len(rom) or rom[offset] != 0x10:
        return None
    size = rom[offset + 1] | rom[offset + 2] << 8 | rom[offset + 3] << 16
    if size == 0 or size > limit:
        return None
    out = bytearray()
    pos = offset + 4
    try:
        while len(out) < size:
            flags = rom[pos]
            pos += 1
            for bit in range(8):
                if len(out) >= size:
                    break
                if flags & (0x80 >> bit):
                    b1, b2 = rom[pos], rom[pos + 1]
                    pos += 2
                    length = (b1 >> 4) + 3
                    disp = ((b1 & 0xF) << 8 | b2) + 1
                    if disp > len(out):
                        return None
                    for _ in range(length):
                        out.append(out[-disp])
                else:
                    out.append(rom[pos])
                    pos += 1
    except IndexError:
        return None
    return bytes(out[:size]), pos - offset


def boundary_table(data: bytes, offset: int = 0, limit: int | None = None):
    """Script start offsets, or None. `limit` bounds the last start."""
    limit = len(data) - offset if limit is None else limit
    if offset + 2 > len(data):
        return None
    size = struct.unpack_from("<H", data, offset)[0]
    if size < MIN_TABLE or size % 2 or size > MAX_TABLE or offset + size > len(data):
        return None
    values = list(struct.unpack_from("<%dH" % (size // 2), data, offset))
    if values[0] != size or values != sorted(values):
        return None
    if values[-1] > limit or values[-1] > MAX_ARCHIVE:
        return None
    return values


def pointer_targets(rom: bytes):
    """offset -> [(reference_offset, flagged)] for every byte-aligned u32 that
    points into the ROM at an even address."""
    targets = collections.defaultdict(list)
    size = len(rom)
    for at in range(0, size - 3):
        top = rom[at + 3]
        if top not in (0x08, 0x88):
            continue
        value = rom[at] | rom[at + 1] << 8 | rom[at + 2] << 16
        if value & 1 or value >= size:
            continue
        targets[value].append((at, top == 0x88))
    return targets


def scan(rom: bytes):
    found = []
    for offset, refs in sorted(pointer_targets(rom).items()):
        entry = None
        values = None
        if rom[offset] == 0x10:
            unpacked = lz77_decompress(rom, offset)
            if unpacked:
                data, clen = unpacked
                header = 0
                if len(data) > 4 and struct.unpack_from("<I", data)[0] >> 8 == len(data):
                    header = 4
                values = boundary_table(data, header)
                if values and values[-1] <= len(data) - header:
                    entry = {"storage": "lz77", "size_header": header, "compressed_length": clen,
                             "decompressed_length": len(data),
                             "payload_length": len(data) - header}
                else:
                    values = None
        if entry is None:
            values = boundary_table(rom, offset, MAX_ARCHIVE)
            if values:
                entry = {"storage": "raw",
                         "payload_length": None,
                         "window": min(MAX_ARCHIVE, len(rom) - offset)}
        if entry is None:
            continue
        entry.update({
            "rom_offset": offset,
            "table_bytes": values[0],
            "script_count": values[0] // 2,
            "last_script_start": values[-1],
            "references": [r for r, _ in refs],
            "unaligned_references": [r for r, _ in refs if r % 4],
            "flagged_references": sum(1 for _, f in refs if f),
        })
        found.append(entry)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    found = scan(rom)
    report = {
        "schema_version": 2,
        "kind": "exe5_pointer_reachable_text_archive_candidates",
        "rom": args.rom.name,
        "criterion": "u32 at any byte offset (bit31 may be set) + boundary table (raw or after LZ77)",
        "count": len(found),
        "by_storage": dict(collections.Counter(a["storage"] for a in found)),
        "with_unaligned_reference": sum(1 for a in found if a["unaligned_references"]),
        "only_unaligned": sum(1 for a in found if len(a["unaligned_references"]) == len(a["references"])),
        "archives": found,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("rom", "count", "by_storage", "with_unaligned_reference",
                                             "only_unaligned")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
