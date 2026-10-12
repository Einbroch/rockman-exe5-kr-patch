#!/usr/bin/env python3
"""Split the menu strings (TextPet db mmbn5s) into translation batches 109+.

Scope: every mmbn5s string except
  * the name-entry kana grids and the bytes TextPet decodes from non-text
    archives (NOISE_ARCHIVES, by Blues offset or the Colonel-only archive);
  * strings that are already a key of an authored dialogue batch (a menu
    string equal to a dialogue line takes that translation).
Batches follow Blues archive order, one archive never shares a batch with
another, MAX strings each.  Each item carries `hint`: the EXE4 Korean for the
same source (chip folder / menu assets) or the EXE5 glossary term, for
consistency only.  Existing src batches are not overwritten.
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE4 = ROOT.parents[2] / "록맨 에그제 4/_work/exe4-kr/translations"
FIRST, MAX = 109, 120
# 0406E08 / 0344808 / 0400F50 / 0401004 / 0421444: table bytes decoded as text.
NOISE_ARCHIVES = {"0406E08", "0344808", "0400F50", "0401004", "0421444"}
# Name-entry keyboard rows (crossover battle): drawn as typed glyph grids.
KEYBOARD = ("あいうえお", "アイウエオ", "アイヴエオ", " ドバビブベボ")


def main() -> None:
    rows = [json.loads(l) for l in (ROOT / "analysis/strings.jsonl").read_text(encoding="utf-8").splitlines()]
    authored = set()
    for f in glob.glob(str(ROOT / "translations/story/batch_*.json")):
        authored |= set(json.loads(Path(f).read_text(encoding="utf-8"))["by_source"])
    hint = {}
    for name in ("chip_folder_korean.json", "menu_korean.json"):
        for e in json.loads((EXE4 / name).read_text(encoding="utf-8"))["entries"]:
            if isinstance(e["source"], str) and isinstance(e["text"], str):
                hint.setdefault(e["source"], e["text"])
    for line in (ROOT / "translations/glossary.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        p = line.split("\t")
        if len(p) >= 3:
            hint.setdefault(p[1], p[2])
    scope, excluded = [], []
    for r in rows:
        if r["db"] != "mmbn5s":
            continue
        arcs = [w[1] for w in r["where"]]
        if set(arcs) & NOISE_ARCHIVES:
            excluded.append({"id": r["id"], "reason": "table bytes"})
            continue
        if r["src"].startswith(KEYBOARD):
            excluded.append({"id": r["id"], "reason": "name-entry keyboard"})
            continue
        if r["src"] in authored:
            continue
        blues = [w for w in r["where"] if w[0] == "blues"]
        key = (0, blues[0][1], blues[0][2]) if blues else (1, r["where"][0][1], r["where"][0][2])
        scope.append((key, r))
    scope.sort(key=lambda x: x[0])
    out = ROOT / "translations/story/src"
    n, made, cur, items = FIRST - 1, [], None, []

    def flush():
        nonlocal n, items
        if not items:
            return
        n += 1
        path = out / ("batch_%03d.json" % n)
        if not path.exists():
            path.write_text(json.dumps({"batch": n, "kind": "menu", "items": items}, ensure_ascii=False, indent=1)
                            + "\n", encoding="utf-8")
            made.append(n)
        items = []

    for key, r in scope:
        arc = key[1]
        if arc != cur or len(items) >= MAX:
            flush()
            cur = arc
        it = {"id": r["id"], "src": r["src"], "speakers": [], "windows": r["windows"],
              "where": r["where"][0], "uses": len(r["where"])}
        if r["src"] in hint:
            it["hint"] = hint[r["src"]]
        items.append(it)
    flush()
    print(json.dumps({"menu_in_scope": len(scope), "excluded": len(excluded), "last_batch": n, "written": made}))


if __name__ == "__main__":
    main()
