#!/usr/bin/env python3
"""Gate for authored dialogue translations (translations/story/batch_*.json).

Every entry src -> ko must:
  * have a src that exists in analysis/strings.jsonl (no stale keys);
  * be encodable: each char is a Hangul syllable or in the exe5 table (no jamo);
  * keep no kana/kanji (Japanese punctuation 「」『』、・ and symbols allowed;
    a batch may declare "kana_ok" words, accepted only as 「word」);
  * fit the window: <= 3 lines, each <= 180 px (measured, Hangul 12 px);
  * keep a leading/trailing line break exactly when the source has one
    (option prompts end with a break; joined strings start with one);
  * not be empty when the source has text;
  * carry the glossary Korean term when the source has the Japanese term
    (entries may list accepted exceptions in "gloss_ok": {"src": ["term"]}).
Menu strings (TextPet db mmbn5s only: names, labels) are drawn one 8x16 cell
per character instead: they must fit their archive's widest source in cells
([TOKEN] = one cell) and use only KS X 1001 syllables (the 8x16 name glyphs);
the pixel rule applies to them only in archives the proportional renderer B
draws (PX_MENU).
Also: one source has one translation across all batches.
Exit 1 with a report on any failure.
"""
from __future__ import annotations

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from text_width import line_width, table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MAX_PX, MAX_LINES = 180, 3
# Measured per window kind (tools/window_budgets.py): the widest source line.
WINDOW_PX = {"msgOpenQuickExt:1": 99}
JP = re.compile(r"[぀-ゟァ-ヺヽ-ヿ一-鿿]")
JAMO = re.compile(r"[ᄀ-ᇿ㄰-㆏]")
# Menu batches whose entries are names (chips 125-127, viruses 129-130, navis
# 131, records 112, programs 113-114, key items 133, liberation 142, 124).
NAME_BATCHES = {112, 113, 114, 124, 125, 126, 127, 129, 130, 131, 133, 142}
# Names that also occur as ordinary words or inside other words in dialogue.
ALIGN_SKIP = {"なにもしない", "B+左", "ロール", "バスター", "ラッシュ", "サーチ", "そうび", "スイコミ", "かれえだ",
              "パパのIDカード", "ハンディース"}
# Dialogue whose names change on purpose: the data-block puzzle answers were
# redesigned in Korean (tools/puzzle_letters.py; ミニボム -> 에너지봄).
NAME_REDESIGNED = ("コタエハ ミニボム デスカ!",)
PX_MENU = {"07EB500", "07DA780"}      # Blues offsets of the B-drawn label archives
TOKEN = re.compile(r"\[[^\]]*\]")


def cells(s: str) -> int:
    return len(TOKEN.sub("#", s))


def ks_x_1001(ch: str) -> bool:
    try:
        e = ch.encode("euc_kr")
    except UnicodeEncodeError:
        return False
    return len(e) == 2 and 0xB0 <= e[0] <= 0xC8


GLOSS_SKIP = {"光", "PET", "ナビ", "エリア", "ロール"}  # too generic for a substring rule


def lines_of(s: str) -> list[str]:
    return re.split(r"\n|\\n", s)


def main() -> int:
    rows = [json.loads(l) for l in (ROOT / "analysis/strings.jsonl").read_text(encoding="utf-8").splitlines()]
    sources = {r["src"] for r in rows}
    # Archive budget: a full dialogue window when the archive opens a plain
    # msgOpen anywhere, else (descriptions, lists) its own widest source line.
    from archive_widths import measure
    arc = {a: (MAX_PX if "msgOpen" in o["windows"] else min(MAX_PX, o["max"])) for a, o in measure().items()}
    budget = {}
    for r in rows:
        b = [WINDOW_PX.get(w, MAX_PX) for w in r.get("windows", [])] + [arc.get(w[1], MAX_PX) for w in r["where"]]
        budget[r["src"]] = min(b or [MAX_PX])
    menu, cell_budget = {}, {}
    for r in rows:
        menu.setdefault(r["src"], True)
        if r["db"] != "mmbn5s":
            menu[r["src"]] = False
    for r in rows:
        if r["db"] == "mmbn5s":
            for w in r["where"]:
                for x in lines_of(r["src"]):
                    cell_budget[w[1]] = max(cell_budget.get(w[1], 0), cells(x))
    menu_budget = {}
    for r in rows:
        if r["db"] == "mmbn5s":
            b = min(cell_budget[w[1]] for w in r["where"])
            menu_budget[r["src"]] = min(menu_budget.get(r["src"], b), b)
    px_menu = {r["src"] for r in rows if r["db"] == "mmbn5s" and any(w[1] in PX_MENU for w in r["where"])}
    gloss = []
    for line in (ROOT / "translations/glossary.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 3 and parts[1] not in GLOSS_SKIP:
            gloss.append((parts[1], parts[2]))
    gloss.sort(key=lambda g: -len(g[0]))
    encodable = set(table()) | {"\n", " "}
    seen: dict[str, tuple[str, str]] = {}
    problems = []
    total = 0
    files = sorted(glob.glob(str(ROOT / "translations/story/batch_*.json")))
    if len(sys.argv) > 1:
        files = [f for f in files if any(Path(f).name.startswith(a) for a in sys.argv[1:] + ["batch_000"])]
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        ok_terms = d.get("gloss_ok", {})
        # Kana the player must match against kana-drawn puzzle blocks; allowed
        # only inside 「」 and only for the words the batch declares.
        kana_ok = d.get("kana_ok", [])
        for src, ko in d["by_source"].items():
            total += 1
            where = "%s: %r" % (Path(f).name, src[:40])
            if src in seen and seen[src][0] != ko:
                problems.append("%s conflicting translation (also in %s)" % (where, seen[src][1]))
            seen[src] = (ko, Path(f).name)
            if src not in sources:
                problems.append(where + " source not in strings.jsonl")
            if not ko.strip() and JP.search(src):
                problems.append(where + " empty translation")
            kana_free = ko
            for word in sorted(kana_ok, key=len, reverse=True):
                kana_free = kana_free.replace("「%s」" % word, "")
            if JP.search(kana_free):
                problems.append(where + " Japanese left: " + "".join(JP.findall(kana_free)))
            if JAMO.search(ko):
                problems.append(where + " jamo")
            plain = TOKEN.sub(lambda m: "" if m.group(0) in encodable else m.group(0), ko)
            bad = {c for c in plain if not (0xAC00 <= ord(c) <= 0xD7A3) and c not in encodable and c != "\\"}
            if bad:
                problems.append(where + " not encodable: " + "".join(sorted(bad)))
            ls = lines_of(ko)
            if len(ls) > MAX_LINES and not menu.get(src, False) or len(ls) > len(lines_of(src)) and menu.get(src):
                problems.append("%s %d lines" % (where, len(ls)))
            is_menu = menu.get(src, False)
            if is_menu:
                for x in ls:
                    if cells(x) > menu_budget[src]:
                        problems.append("%s %d cells > %d: %r" % (where, cells(x), menu_budget[src], x))
                # A label padded with trailing spaces clears its field: keep its width.
                for x, k in zip(lines_of(src), ls):
                    if x.endswith(" ") and cells(k) != cells(x):
                        problems.append("%s padded label %d cells != source %d: %r" % (where, cells(k), cells(x), k))
                if any(0xAC00 <= ord(c) <= 0xD7A3 and not ks_x_1001(c) for c in ko):
                    problems.append(where + " syllable outside KS X 1001 (no 8x16 glyph)")
            for x in ls:
                if is_menu and src not in px_menu:
                    continue
                w = line_width(x)[0]
                if w > budget.get(src, MAX_PX):
                    problems.append("%s line %dpx > %d: %r" % (where, w, budget.get(src, MAX_PX), x))
            for edge, test in (("leading", lambda s: s[:1] == "\n" or s[:2] == "\\n"),
                               ("trailing", lambda s: s[-1:] == "\n" or s[-2:] == "\\n")):
                if test(src) != test(ko):
                    problems.append("%s %s line break differs" % (where, edge))
            rest = src
            for jp, kr in gloss:  # longest first; a matched term hides its substrings
                if jp in rest:
                    if kr not in ko and jp not in ok_terms.get(src, []):
                        problems.append("%s glossary %s -> %s missing" % (where, jp, kr))
                    rest = rest.replace(jp, "〓")
    # Names the menus print (chips, viruses, navis, key items, programs) must
    # read the same inside dialogue: a dialogue line holding the Japanese name
    # carries the menu's Korean (spaces ignored).  Runs over every batch.
    menu_names = {}
    dialogue = {}
    for f in sorted(glob.glob(str(ROOT / "translations/story/batch_*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        n = d["batch"] if isinstance(d["batch"], int) else 0
        for k, v in d["by_source"].items():
            if n in NAME_BATCHES and len(k) >= 3 and "\n" not in k and k not in ALIGN_SKIP:
                menu_names[k] = v.strip()
            elif n < 109:
                dialogue[k] = v
    order = sorted(menu_names, key=len, reverse=True)
    for src, ko in dialogue.items():
        if src.startswith(NAME_REDESIGNED):
            continue
        rest = src
        flat = re.sub(r"\s|\\n", "", ko)
        for jp in order:
            if jp in rest:
                rest = rest.replace(jp, "〓")
                if menu_names[jp].replace(" ", "") not in flat:
                    problems.append("menu name %s -> %s not in dialogue %r" % (jp, menu_names[jp], src[:30]))
    print(json.dumps({"files": len(files), "entries": total, "problems": len(problems)}, ensure_ascii=False))
    for p in problems[:200]:
        print(" ", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
