"""Print a source batch compactly: id|speakers|archive tail[+Q1 = chip-description window, 99px]|text (/ = break)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for n in sys.argv[1:]:
    d = json.loads((ROOT / "translations/story/src" / ("batch_%s.json" % n.zfill(3))).read_text(encoding="utf-8"))
    for it in d["items"]:
        sp = ",".join(it["speakers"]) or "-"
        wn = "Q1" if "msgOpenQuickExt:1" in it.get("windows", []) else ""
        print("%d|%s|%s%s|%s" % (it["id"], sp, it["where"][1][-4:], wn, it["src"].replace("\n", "/")))
