#!/usr/bin/env python3
"""Classify decoded candidates into text archives and noise; write the population.

text archive : round-trips, lies in the data region (>= 0x1C0000; nothing below
               that decoded as anything but code bytes when inspected), and its
               TPL holds no undecodable byte (`$xx`).
noise        : everything else, with the reason.

Output analysis/population_<version>.json is the translation population. It is a
lower bound: an archive reached by no pointer literal (computed address) is not
in it.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_START = 0x1C0000
JP = re.compile(r"[぀-ヿ一-鿿]")


def main() -> None:
    for version in ("Blues", "Colonel"):
        cat = json.loads((ROOT / "analysis" / ("archives_%s.json" % version)).read_text(encoding="utf-8"))
        tpl_dir = ROOT / "analysis/tpl" / version.lower()
        text, noise = [], []
        for a in cat["archives"]:
            key = "%07X" % a["rom_offset"]
            reason = None
            if not a.get("roundtrip"):
                reason = "no byte round trip"
            elif a["rom_offset"] < DATA_START:
                reason = "code region"
            else:
                tpl = (tpl_dir / (key + ".tpl")).read_text(encoding="utf-8")
                if re.search(r"(?m)^\t\$[0-9A-F]{2}", tpl):
                    reason = "undecodable bytes in TPL"
            if reason:
                noise.append({"archive": key, "storage": a["storage"], "reason": reason})
            else:
                tpl = (tpl_dir / (key + ".tpl")).read_text(encoding="utf-8")
                text.append({"archive": key, "storage": a["storage"], "scripts": a["script_count"],
                             "japanese_chars": len(JP.findall(tpl)),
                             "references": len(a["references"]),
                             "unaligned_references": len(a["unaligned_references"])})
        out = {"version": version, "rule": __doc__.split("\n\n")[1], "text_archives": len(text),
               "with_japanese": sum(1 for t in text if t["japanese_chars"]),
               "japanese_chars": sum(t["japanese_chars"] for t in text),
               "noise": len(noise), "archives": text, "rejected": noise}
        (ROOT / "analysis" / ("population_%s.json" % version.lower())).write_text(
            json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        reasons = {}
        for n in noise:
            reasons[n["reason"]] = reasons.get(n["reason"], 0) + 1
        print(version, {k: out[k] for k in ("text_archives", "with_japanese", "japanese_chars", "noise")}, reasons)
        print("  undecodable in data region:", [n["archive"] for n in noise if n["reason"] == "undecodable bytes in TPL"])


if __name__ == "__main__":
    sys.exit(main())
