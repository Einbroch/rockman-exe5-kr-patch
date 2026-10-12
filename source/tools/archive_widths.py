"""Widest source line per archive, with the window kinds its strings use."""
import collections, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from text_width import line_width
from window_budgets import BREAK
ROOT = Path(__file__).resolve().parent.parent
def measure():
    out = collections.defaultdict(lambda: {"max": 0, "line": "", "windows": set(), "strings": 0})
    for l in (ROOT / "analysis/strings.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        arcs = {w[1] for w in r["where"]}
        for a in arcs:
            o = out[a]; o["strings"] += 1; o["windows"].update(r["windows"])
            for ln in BREAK.split(r["src"]):
                w = line_width(ln)[0]
                if w <= 260 and w > o["max"]:
                    o["max"], o["line"] = w, ln
    return out
if __name__ == "__main__":
    m = measure()
    for a in sys.argv[1:]:
        o = m[a]; print(a, o["max"], sorted(o["windows"]), o["strings"], repr(o["line"]))
