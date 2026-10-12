#!/usr/bin/env python3
"""Show where TPL -> MSG differs from the payload for chosen archives (diagnosis)."""
from __future__ import annotations

import json
import shutil
import struct
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from decode_archives import PLUGINS, convert, cut_last_script, payload  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    version, offsets = sys.argv[1], sys.argv[2:]
    rom = (ROOT.parents[1] / ("Rockman EXE 5 - Team of %s (Japan).gba" % version.capitalize())).read_bytes()
    cat = {"%07X" % a["rom_offset"]: a for a in json.loads(
        (ROOT / "analysis" / ("archives_%s.json" % version.capitalize())).read_text(encoding="utf-8"))["archives"]}
    with tempfile.TemporaryDirectory() as name:
        temp = Path(name)
        plugins = temp / "plugins"
        shutil.copytree(PLUGINS, plugins)
        (temp / "w").mkdir()
        for off in offsets:
            a = cat[off.upper().zfill(7)]
            if a["storage"] == "raw":
                a = dict(a, payload_length=a["window"])
            p = payload(rom, a)
            tpl = convert({"x": p}, "bin", "tpl", plugins, temp / "w")["x"].decode("utf-8-sig")
            if a["storage"] == "raw":
                tpl = cut_last_script(tpl)[0]
            msg = convert({"x": tpl.encode()}, "tpl", "bin", plugins, temp / "w").get("x")
            if msg is None:
                print(off, "re-encode failed")
                continue
            n = struct.unpack_from("<H", p)[0] // 2
            offs = struct.unpack_from("<%dH" % n, p)
            i = next((k for k in range(min(len(p), len(msg))) if p[k] != msg[k]), None)
            if i is None:
                print(off, a["storage"], "prefix equal; lengths", len(p), len(msg), "tail", p[len(msg):len(msg) + 24].hex(" "))
                continue
            script = max(k for k in range(n) if offs[k] <= i)
            print(off, a["storage"], "first diff at", hex(i), "script", script, "(starts %x)" % offs[script])
            print("   src", p[max(0, i - 12):i + 16].hex(" "))
            print("   new", msg[max(0, i - 12):i + 16].hex(" "))
            (ROOT / "analysis" / ("diag_%s.tpl" % off)).write_text(tpl, encoding="utf-8")


if __name__ == "__main__":
    main()
