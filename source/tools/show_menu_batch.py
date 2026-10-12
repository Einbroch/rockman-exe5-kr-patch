"""Print a menu batch: id|archive|cells|src (/ = break)|hint."""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOKEN = re.compile(r"\[[^\]]*\]")
for n in sys.argv[1:]:
    d = json.loads((ROOT / "translations/story/src" / ("batch_%s.json" % n.zfill(3))).read_text(encoding="utf-8"))
    for it in d["items"]:
        s = it["src"]
        c = max(len(TOKEN.sub("#", x)) for x in re.split(r"\n|\n", s))
        print("%d|%s|%d|%s|%s" % (it["id"], it["where"][1][-4:], c, s.replace("\n", "/"), it.get("hint", "")))
