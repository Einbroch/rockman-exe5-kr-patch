"""Widest source line per window kind (msgOpen variant[:type]) — the window's measured budget.

Strings print where their script last opened a window; a window kind's budget
is the widest line the original game prints in it. 'none' = no window command
in the script before the string (continuation scripts, fragments).
"""
import collections
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from text_width import line_width  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BREAK = re.compile(r"\n|\\n")


def measure():
    st = collections.defaultdict(lambda: [0, 0, ""])
    for l in (ROOT / "analysis/strings.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(l)
        if r["db"] != "mmbn5":
            continue
        for ln in BREAK.split(r["src"]):
            w = line_width(ln)[0]
            if w > 260:
                continue
            for win in r["windows"]:
                s = st[win]
                s[0] += 1
                if w > s[1]:
                    s[1], s[2] = w, ln
    return st


if __name__ == "__main__":
    for k, v in sorted(measure().items(), key=lambda x: -x[1][0]):
        print(k, v[0], v[1], repr(v[2]))
