#!/usr/bin/env python3
"""Split the dialogue strings into translation batches.

Scope: command database mmbn5 (dialogue). mmbn5s (names/labels read by menu
and chip renderers) is excluded until those consumers support Hangul.
Excluded as not-text: decoded image/table bytes (`junk`) and the name-entry
kana grids. Strings identical to an EXE4 source reuse the EXE4 Korean
(translations/story/batch_000_exe4_reuse.json, state reused_from_exe4).

Batches follow the order strings first appear (Blues archive order, then
Colonel-only), BATCH strings each: translations/story/src/batch_NNN.json.
Existing authored batches are never overwritten; ids are stable because
analysis/strings.jsonl is regenerated deterministically from the population.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from text_width import line_width  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
EXE4 = ROOT.parents[2] / "록맨 에그제 4/_work/exe4-kr/translations/story_authored"
BATCH = 150


def split_lines(s: str) -> list[str]:
    return re.split(r"\n|\\n", s)


def junk(s: str) -> str | None:
    if re.search(r"\[(V\d|bat|z|SP|DS)\]", s) or "■" in s:
        return "image or table bytes"
    if any(line_width(x)[0] > 260 for x in split_lines(s)):
        return "wider than any window (kana grid or bytes)"
    if len(re.findall(r"[0-9]", s)) >= 6 and re.search(r"[0-9]  ", s):
        return "digit/space byte pattern"
    return None


def main() -> None:
    rows = [json.loads(l) for l in (ROOT / "analysis/strings.jsonl").read_text(encoding="utf-8").splitlines()]
    exe4 = {}
    for f in sorted(glob.glob(str(EXE4 / "batch_*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for k, v in (d.get("by_source") or {}).items():
            if isinstance(v, str):
                exe4.setdefault(k, v)
    scope, excluded, reuse = [], [], {}
    for r in rows:
        if r["db"] != "mmbn5":
            continue
        why = junk(r["src"])
        if why:
            excluded.append({"id": r["id"], "src": r["src"][:80], "reason": why})
            continue
        if r["src"] in exe4 and all(line_width(x)[0] <= 180 for x in split_lines(exe4[r["src"]])):
            reuse[r["src"]] = exe4[r["src"]]
            continue
        scope.append(r)
    out = ROOT / "translations/story"
    (out / "src").mkdir(parents=True, exist_ok=True)
    (out / "batch_000_exe4_reuse.json").write_text(json.dumps(
        {"batch": 0, "state": "reused_from_exe4", "by_source": reuse}, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    n = 0
    for i in range(0, len(scope), BATCH):
        n += 1
        items = [{"id": r["id"], "src": r["src"], "speakers": r["speakers"], "windows": r["windows"],
                  "where": r["where"][0], "uses": len(r["where"])} for r in scope[i:i + BATCH]]
        (out / "src" / ("batch_%03d.json" % n)).write_text(
            json.dumps({"batch": n, "items": items}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (ROOT / "analysis/story_scope.json").write_text(json.dumps(
        {"in_scope": len(scope), "reused_from_exe4": len(reuse), "batches": n,
         "excluded": excluded}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"in_scope": len(scope), "reused_from_exe4": len(reuse), "excluded": len(excluded),
                      "batches": n}))


if __name__ == "__main__":
    main()
