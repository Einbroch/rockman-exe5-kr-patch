#!/usr/bin/env python3
"""Turn a compact authored batch into translations/story/batch_NNN.json.

Input  translations/story/ko/batch_NNN.txt, one line per string:
         <id>\t<korean>      '|' marks a line break
         <id>\t#SKIP <reason>  not text / leave as is (recorded)
         <id>\t<korean>{pad}   pad each line with spaces to its source line's
                               cell count (menu labels that clear their field)
       Lines starting with '#' or blank are comments.
Source translations/story/src/batch_NNN.json (ids and exact source text).

A '|' becomes the break style the source itself uses: a real line break, or
the two-character escape \\n when the source writes its breaks that way.
Every id of the source batch must be covered exactly once. Then the gate
(check_translations.py) runs on this batch.

usage: compile_batch.py 001 [002 ...]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
STORY = ROOT / "translations/story"


def convert(num: str) -> None:
    src = json.loads((STORY / "src" / ("batch_%s.json" % num)).read_text(encoding="utf-8"))
    by_id = {it["id"]: it for it in src["items"]}
    lines = (STORY / "ko" / ("batch_%s.txt" % num)).read_text(encoding="utf-8").splitlines()
    by_source, skip, seen, kana_ok, gloss_ok = {}, {}, set(), [], {}
    for n, line in enumerate(lines, 1):
        if line.startswith("#KANA "):
            kana_ok += line[6:].split()
            continue
        if line.startswith("#GLOSS_OK "):  # id term...: a glossary term that is not the name here
            key, *terms = line[10:].split()
            gloss_ok.setdefault(by_id[int(key)]["src"], []).extend(terms)
            continue
        if not line.strip() or line.startswith("#"):
            continue
        if "\t" not in line:
            raise SystemExit("batch %s line %d: no tab" % (num, n))
        key, ko = line.split("\t", 1)
        i = int(key)
        if i not in by_id:
            raise SystemExit("batch %s line %d: id %d not in this batch" % (num, n, i))
        if i in seen:
            raise SystemExit("batch %s line %d: id %d twice" % (num, n, i))
        seen.add(i)
        s = by_id[i]["src"]
        if ko.startswith("#SKIP"):
            skip[s] = ko[5:].strip() or "not text"
            continue
        if ko.endswith("{pad}"):
            from check_translations import cells
            src_lines = re.split(r"\n|\\n", s)
            ko_lines = ko[:-5].split("|")
            if len(src_lines) != len(ko_lines):
                raise SystemExit("batch %s line %d: {pad} needs the source's line count" % (num, n))
            ko = "|".join(k + " " * max(0, cells(x) - cells(k)) for k, x in zip(ko_lines, src_lines))
        escaped = "\\n" in s and "\n" not in s
        by_source[s] = ko.replace("|", "\\n" if escaped else "\n")
    missing = sorted(set(by_id) - seen)
    if missing:
        raise SystemExit("batch %s: ids not covered: %s" % (num, missing[:20]))
    out = {"batch": int(num), "state": "draft", "by_source": by_source, "skip": skip}
    if kana_ok:
        out["kana_ok"] = kana_ok
    if gloss_ok:
        out["gloss_ok"] = gloss_ok
    (STORY / ("batch_%s.json" % num)).write_text(json.dumps(
        out,
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    nums = [a.zfill(3) for a in sys.argv[1:]]
    for num in nums:
        convert(num)
    return subprocess.call([sys.executable, str(ROOT / "tools/check_translations.py")] + ["batch_" + n for n in nums])


if __name__ == "__main__":
    sys.exit(main())
