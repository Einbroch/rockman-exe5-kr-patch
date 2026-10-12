#!/usr/bin/env python3
"""Thumb disassembly of a ROM range (analysis helper).

usage: dis.py ROM START LENGTH [--base 0x08000000]
Literal loads are annotated with the loaded word.
"""
import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parents[2] / "록맨 에그제 4/_work/exe4-kr/external/arm_debug_python"))
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB  # noqa: E402


def main():
    p = argparse.ArgumentParser()
    p.add_argument("rom")
    p.add_argument("start", type=lambda x: int(x, 0))
    p.add_argument("length", type=lambda x: int(x, 0))
    p.add_argument("--base", type=lambda x: int(x, 0), default=0x08000000,
                   help="runtime address of file offset 0 of the range's mapping")
    p.add_argument("--file-offset", type=lambda x: int(x, 0), default=None,
                   help="file offset of START when base is not ROM (e.g. IWRAM copy)")
    a = p.parse_args()
    rom = Path(a.rom).read_bytes()
    fo = a.start - a.base if a.file_offset is None else a.file_offset
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    pos = 0
    while pos < a.length:
        chunk = rom[fo + pos:fo + a.length]
        got = False
        for i in md.disasm(chunk, a.start + pos):
            got = True
            note = ""
            if i.mnemonic == "ldr" and "[pc," in i.op_str:
                op = int.from_bytes(i.bytes, "little")
                lit = ((i.address + 4) & ~3) + (op & 0xFF) * 4
                note = "  ; =0x%08x" % struct.unpack_from("<I", rom, fo + (lit - a.start))[0]
            if i.mnemonic == "bl":
                note = ""
            print("%08x: %-8s %-6s %s%s" % (i.address, i.bytes.hex(), i.mnemonic, i.op_str, note))
            pos = i.address + i.size - a.start
        if not got:
            print("%08x: %-8s .hword" % (a.start + pos, rom[fo + pos:fo + pos + 2].hex()))
            pos += 2


if __name__ == "__main__":
    main()
