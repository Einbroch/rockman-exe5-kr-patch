"""GBA BIOS LZ77 (type 0x10) codec.

The compressor never emits displacement 1 so the stream is valid for both
LZ77UnCompWram and LZ77UnCompVram (the VRAM variant writes halfwords and
cannot copy from the byte it is still assembling).
"""
from __future__ import annotations

from scan_text_archives import lz77_decompress  # noqa: F401  (re-export)

MIN_MATCH, MAX_MATCH, WINDOW = 3, 18, 0x1000


def compress(data: bytes) -> bytes:
    if len(data) > 0xFFFFFF:
        raise ValueError("LZ77 length overflow")
    out = bytearray(b"\x10" + len(data).to_bytes(3, "little"))
    index: dict[bytes, list[int]] = {}
    pos = 0
    n = len(data)
    while pos < n:
        flag_at = len(out)
        out.append(0)
        flags = 0
        for bit in range(8):
            if pos >= n:
                break
            best_len, best_disp = 0, 0
            key = data[pos:pos + 3]
            if len(key) == 3:
                for cand in reversed(index.get(key, ())):
                    disp = pos - cand
                    if disp > WINDOW:
                        break
                    if disp < 2:
                        continue
                    length = 3
                    while length < MAX_MATCH and pos + length < n and data[cand + length] == data[pos + length]:
                        length += 1
                    if length > best_len:
                        best_len, best_disp = length, disp
                        if length == MAX_MATCH:
                            break
            step = best_len if best_len >= MIN_MATCH else 1
            if best_len >= MIN_MATCH:
                flags |= 0x80 >> bit
                d = best_disp - 1
                out.append(((best_len - 3) << 4) | (d >> 8))
                out.append(d & 0xFF)
            else:
                out.append(data[pos])
            for k in range(pos, pos + step):
                if k + 3 <= n:
                    index.setdefault(data[k:k + 3], []).append(k)
            pos += step
        out[flag_at] = flags
    while len(out) % 4:
        out.append(0)
    return bytes(out)
