"""Custom-screen "CHIP DATA TRANSMISSION / チップデータを 送信します" picture.

A 56x48 4bpp image shown in the chip-art slot of the custom window (BG3,
palette 10) after OK, read raw by two literals (Blues 0x244EC/0x24554).
Blues 0x747E60, Colonel 0x7492D0 (same bytes; located by content).  In
palette 10 indices 1 and 6 are the same dark blue, 3 and 5 the same light ink,
c the mid tone the kana use as edge.  The English top half stays; rows 22..42
inside the frame (x 4..51) are cleared to 1 and "칩 데이터 / 전송 중" is drawn
in Galmuri9, ink 5, centred ("칩 데이터를 / 전송합니다" does not fit 48 px).
Same size, written in place after an expected-bytes check.
"""
from __future__ import annotations

from pathlib import Path

import pet_labels

FONT9 = Path(__file__).resolve().parents[4] / "폰트/Galmuri-v2.24.29/Galmuri9.bdf"
BLUES_AT = 0x747E60
SIZE = 56 * 48 // 2
LINES = [("칩 데이터", 24), ("전송 중", 35)]
X0, X1, Y0, Y1 = 4, 52, 22, 43


def redraw(img: bytes) -> bytes:
    out = bytearray(img)

    def put(x, y, c):
        t = (y // 8) * 7 + x // 8
        i = t * 32 + (y % 8) * 4 + (x % 8) // 2
        sh = 4 * (x & 1)
        out[i] = (out[i] & ~(15 << sh) & 0xFF) | (c << sh)
    for y in range(Y0, Y1):
        for x in range(X0, X1):
            put(x, y, 1)
    saved = pet_labels.FONT
    pet_labels.FONT = FONT9
    try:
        f = pet_labels.font()
    finally:
        pet_labels.FONT = saved
    for text, top in LINES:
        px = pet_labels.text_pixels(f, text)
        w = max(x for x, _ in px) + 1
        left = X0 + (X1 - X0 - w) // 2
        if w > X1 - X0:
            raise ValueError("transmission line too wide: %r" % text)
        for x, y in px:
            put(left + x, top + y, 5)
    return bytes(out)


def build(rom: bytearray, write, blues: bytes) -> dict:
    src = blues[BLUES_AT:BLUES_AT + SIZE]
    at = bytes(rom).find(src)
    if at < 0 or bytes(rom).find(src, at + 1) >= 0:
        raise ValueError("transmission picture not unique")
    write(at, redraw(src), "custom-screen transmission picture", src)
    return {"at": at}
