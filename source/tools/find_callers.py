#!/usr/bin/env python3
"""Find Thumb BL callers of target addresses, and aligned u32 literals equal to them.

usage: find_callers.py ROM ADDR [ADDR ...]   (addresses are ROM runtime, e.g. 0x080451CC)
"""
import struct
import sys
from pathlib import Path


def main():
    rom = Path(sys.argv[1]).read_bytes()
    targets = {int(x, 0) & ~1 for x in sys.argv[2:]}
    end = min(len(rom), 0x1C0000)
    for a in range(0, end - 4, 2):
        hi, lo = struct.unpack_from("<HH", rom, a)
        if hi >> 11 == 0b11110 and lo >> 11 == 0b11111:
            off = ((hi & 0x7FF) << 12) | ((lo & 0x7FF) << 1)
            if off & 0x400000:
                off -= 0x800000
            dest = 0x08000000 + a + 4 + off
            if dest in targets:
                print("bl  at %08x -> %08x" % (0x08000000 + a, dest))
    for a in range(0, len(rom) - 4, 4):
        v = struct.unpack_from("<I", rom, a)[0]
        if v & ~1 in targets:
            print("lit at %08x = %08x" % (0x08000000 + a, v))


if __name__ == "__main__":
    main()
