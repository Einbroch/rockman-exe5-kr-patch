#!/usr/bin/env python3
"""Per-archive text statistics over decoded TPLs (Japanese char counts, scripts)."""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

JP = re.compile(r"[぀-ヿ一-鿿]")
STRING = re.compile(r'"""(.*?)"""|"((?:[^"\\]|\\.)*)"', re.S)
SCRIPT = re.compile(r"^script (\d+) (\S+)", re.M)


def stats(text: str) -> dict:
    strings = "".join(a or b for a, b in STRING.findall(text))
    jp = JP.findall(strings)
    dbs = collections.Counter(m.group(2) for m in SCRIPT.finditer(text))
    return {"scripts": sum(dbs.values()), "databases": dict(dbs),
            "string_chars": len(strings), "jp_chars": len(jp), "jp_set": set(jp)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--tpl-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    rows, every = [], collections.Counter()
    for item in catalog["archives"]:
        text = (args.tpl_dir / ("%07X.tpl" % item["rom_offset"])).read_text(encoding="utf-8")
        s = stats(text)
        every.update(s.pop("jp_set"))
        rows.append({"rom_offset": item["rom_offset"], "storage": item["storage"], **s})
    with_jp = [r for r in rows if r["jp_chars"]]
    db_total = collections.Counter()
    for r in rows:
        db_total.update(r["databases"])
    summary = {
        "archives": len(rows),
        "archives_with_japanese": len(with_jp),
        "archives_without_japanese": len(rows) - len(with_jp),
        "scripts": sum(r["scripts"] for r in rows),
        "scripts_by_database": dict(db_total),
        "japanese_chars": sum(r["jp_chars"] for r in rows),
        "unique_japanese_chars": len(every),
    }
    args.out.write_text(json.dumps({"summary": summary, "archives": rows}, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("no-japanese:", [("%X" % r["rom_offset"], r["storage"], r["scripts"], r["string_chars"])
                           for r in rows if not r["jp_chars"]][:60])


if __name__ == "__main__":
    main()
