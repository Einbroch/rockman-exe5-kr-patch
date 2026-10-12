#!/usr/bin/env python3
"""Regenerate the menu batches whose layout is computed, not authored.

Inputs are the authored tables in translations/menu_sources/ and the chip
name batches; outputs are translations/story/ko/batch_NNN.txt (then run
compile_batch.py on them):

  109  staff credits (06F05D8): names right-aligned to the source width
       (credits.txt: id <TAB> Korean)
  110/111  place names (06F992C): right-aligned in 12 cells, '_' fill as the
       source does (places.txt; '#SKIP' lines pass through)
  120  chip + code three-line lists (0706594): chip names from batches
       125..127 (+ CHIP_EXTRA), the code letter in the source's column
  137..141  BBS title rows (07E1558..07E5E70): ' ' + poster (8 cells) + ' ' +
       title, padded to the source length (bbs_names.tsv, bbs_titles.tsv;
       a leading 'RE:' is carried over)

usage: make_menu_derived.py      (then: compile_batch.py 109 110 111 120 137 138 139 140 141)
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "translations/story/src"
KO = ROOT / "translations/story/ko"
TABLES = ROOT / "translations/menu_sources"
CHIP_EXTRA = {"ロングソード": "롱소드", "コスモマン": "코스모맨", "スワローマン": "스왈로맨", "フットマン": "풋맨",
              "シェードマン": "셰이드맨", "ジャンゴ": "장고"}


def items(n: int) -> list[dict]:
    return json.loads((SRC / ("batch_%03d.json" % n)).read_text(encoding="utf-8"))["items"]


def table(name: str) -> list[tuple[str, str]]:
    return [tuple(l.split("\t", 1)) for l in (TABLES / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def write(n: int, head: str, rows: list[str]) -> None:
    (KO / ("batch_%03d.txt" % n)).write_text("\n".join(["# " + head] + rows) + "\n", encoding="utf-8")


def credits() -> None:
    src = {it["id"]: it["src"] for it in items(109)}
    rows = []
    for i, k in table("credits.txt"):
        s = src[int(i)]
        if s.startswith(" "):
            k = " " * max(0, len(s) - len(k)) + k
        rows.append("%s\t%s" % (i, k))
    write(109, "batch 109 — 스태프 크레딧(06F05D8). 생성: tools/make_menu_derived.py (menu_sources/credits.txt)", rows)


def places() -> None:
    ids = {110: {it["id"] for it in items(110)}, 111: {it["id"] for it in items(111)}}
    src = {it["id"]: it["src"] for n in (110, 111) for it in items(n)}
    out = {110: [], 111: []}
    for i, k in table("places.txt"):
        # Only the place names are '_'-padded; 302 is the one-cell count unit
        # (BUGPIECE 1コ) that shares the archive.
        if not k.startswith("#SKIP") and src[int(i)].startswith("_"):
            if len(k) > 12:
                raise SystemExit("place name over 12 cells: %s %s" % (i, k))
            k = "_" * (12 - len(k)) + k
        out[110 if int(i) in ids[110] else 111].append("%s\t%s" % (i, k))
    for n in (110, 111):
        write(n, "batch %d — 지명(06F992C), 12칸 오른쪽 정렬 _ 채움. 생성: make_menu_derived.py (menu_sources/places.txt)" % n,
              out[n])


def chip_lists() -> None:
    names = dict(CHIP_EXTRA)
    for n in (125, 126, 127):
        names.update(json.loads((ROOT / ("translations/story/batch_%d.json" % n)).read_text(encoding="utf-8"))["by_source"])
    rows = []
    for it in items(120):
        ko = []
        for x in it["src"].split("\n"):
            code, name, suf = x[-1], x[:-1].rstrip(), ""
            if name not in names and name[-2:] in ("SP", "DS"):
                name, suf = name[:-2], name[-2:]
            k = names[name] + suf
            ko.append(k + " " * max(0, len(x) - 1 - len(k)) + code)
        rows.append("%d\t%s" % (it["id"], "|".join(ko)))
    write(120, "batch 120 — 칩+코드 3줄 목록(0706594). 생성: make_menu_derived.py (칩 이름 batch 125~127)", rows)


def bbs() -> None:
    names = dict(table("bbs_names.tsv"))
    titles = dict(table("bbs_titles.tsv"))
    for n in range(137, 142):
        rows = []
        its = items(n)
        for it in its:
            s = it["src"]
            nm, tt, pre = s[1:9].rstrip(), s[10:].rstrip(), ""
            while tt.startswith("RE:"):
                pre, tt = pre + "RE:", tt[3:]
            kn, kt = names[nm], pre + titles[tt]
            if len(kn) > 8 or 10 + len(kt) > len(s):
                raise SystemExit("BBS row too wide: %d %s" % (it["id"], kt))
            rows.append("%d\t%s" % (it["id"], (" " + kn.ljust(8) + " " + kt).ljust(len(s))))
        write(n, "batch %d — 게시판 제목 줄(%s). 생성: make_menu_derived.py (menu_sources/bbs_*.tsv)"
              % (n, its[0]["where"][1]), rows)


if __name__ == "__main__":
    credits()
    places()
    chip_lists()
    bbs()
    print("regenerated 109 110 111 120 137-141")
