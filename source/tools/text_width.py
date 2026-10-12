"""Pixel width of dialogue text, measured with the game's own advance table.

Japanese is encoded with TextPet's exe5 table (longest match) and each glyph
index looked up in the source advance table; Hangul syllables advance 12
(the PoC font). Inline commands ({...} or [..] tokens) are not text and count 0
here; callers that print names must add those widths themselves.
"""
from __future__ import annotations

import struct
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANGUL_ADVANCE = 12
ROM = ROOT.parents[1] / "Rockman EXE 5 - Team of Blues (Japan).gba"
WIDTH_TABLE = 0x425C0


@lru_cache(maxsize=1)
def table() -> dict[str, int]:
    rom = ROM.read_bytes()
    widths = {}
    for line in (ROOT / "external/textpet-plugins/exe5-utf8.tbl").read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        code, ch = line.split("=", 1)
        if not ch or ch in widths or ch == "\\n":
            continue
        raw = bytes.fromhex(code)
        if len(raw) == 1 and raw[0] < 0xE4:
            index = raw[0]
        elif len(raw) == 2 and raw[0] == 0xE4:
            index = 0xE4 + raw[1]
        else:
            continue
        widths[ch] = struct.unpack_from("<I", rom, WIDTH_TABLE + index * 4)[0]
    return widths


def line_width(text: str) -> tuple[int, list[str]]:
    """Width in px and the characters that could not be measured."""
    w = table()
    keys = sorted(w, key=len, reverse=True)
    maxlen = max(len(k) for k in keys)
    px, unknown, i = 0, [], 0
    while i < len(text):
        c = text[i]
        if 0xAC00 <= ord(c) <= 0xD7A3:
            px += HANGUL_ADVANCE
            i += 1
            continue
        for n in range(min(maxlen, len(text) - i), 0, -1):
            if text[i:i + n] in w:
                px += w[text[i:i + n]]
                i += n
                break
        else:
            unknown.append(c)
            i += 1
    return px, unknown
