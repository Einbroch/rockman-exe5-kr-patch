#!/usr/bin/env python3
"""Extract every TPL string literal of the text population, with context.

Unit = one TPL string literal (what the builder substitutes). Rows are unique
by source text across both versions; each keeps every place it occurs
(version, archive, script), the speaker in effect (last mugshotShow, or None
after mugshotHide), the command database and its neighbours in the script.

Output: analysis/strings.jsonl (one JSON object per line, archive order of Blues
then Colonel-only), analysis/strings_summary.json.
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JP = re.compile(r"[぀-ヿ一-鿿]")
HEAD = re.compile(r"^script (\d+) (\S+) \{$")


def parse(tpl: str, windows: list | None = None):
    """Yield (script, db, speaker, string) in order.

    If `windows` is a list, the window in effect for each yielded string (last
    msgOpen* command of the script and its `type`, or 'none') is appended."""
    lines = tpl.replace("\r\n", "\n").split("\n")
    i, script, db, speaker, window = 0, None, None, None, "none"
    while i < len(lines):
        line = lines[i]
        m = HEAD.match(line)
        if m:
            script, db, speaker, window = int(m.group(1)), m.group(2), None, "none"
            i += 1
            continue
        if line.startswith("\tmsgOpen"):
            window = line[1:].strip()
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("type ="):
                window += ":" + lines[i + 1].split("=", 1)[1].strip()
        if windows is not None and line.startswith("\t") and not line.startswith("\t\t") and (
                line[1:] == '"""' or line[1:].startswith('"')):
            windows.append(window)
        if line.startswith("\t") and not line.startswith("\t\t"):
            body = line[1:]
            if body == '"""':
                j = i + 1
                parts = []
                while lines[j] != '\t"""':
                    parts.append(lines[j][1:] if lines[j].startswith("\t") else lines[j])
                    j += 1
                yield script, db, speaker, "\n".join(parts)
                i = j + 1
                continue
            if body.startswith('"'):
                # Quoted string, may span lines (real line breaks inside).
                text = body
                j = i
                while not (text.endswith('"') and len(text) > 1 and not text.endswith('\\"')):
                    j += 1
                    text += "\n" + lines[j]
                yield script, db, speaker, text[1:-1]
                i = j + 1
                continue
            name = body.split()[0] if body.split() else ""
            if name == "mugshotShow" and i + 1 < len(lines) and lines[i + 1].strip().startswith("mugshot ="):
                speaker = lines[i + 1].split("=", 1)[1].strip()
            elif name == "mugshotHide":
                speaker = None
        i += 1


def main() -> None:
    rows: dict[str, dict] = {}
    order = []
    for version in ("blues", "colonel"):
        pop = json.loads((ROOT / "analysis" / ("population_%s.json" % version)).read_text(encoding="utf-8"))
        for a in pop["archives"]:
            tpl = (ROOT / "analysis/tpl" / version / (a["archive"] + ".tpl")).read_text(encoding="utf-8")
            wins: list = []
            for k, (script, db, speaker, text) in enumerate(parse(tpl, wins)):
                if not JP.search(text):
                    continue
                row = rows.get(text)
                if row is None:
                    row = rows[text] = {"src": text, "db": db, "speakers": [], "windows": [], "where": []}
                    order.append(text)
                if speaker and speaker not in row["speakers"]:
                    row["speakers"].append(speaker)
                if wins[k] not in row["windows"]:
                    row["windows"].append(wins[k])
                row["where"].append([version, a["archive"], script])
    out = ROOT / "analysis/strings.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for n, text in enumerate(order):
            row = rows[text]
            row["id"] = n
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    summary = {
        "unique_strings": len(order),
        "japanese_chars_unique": sum(len(JP.findall(t)) for t in order),
        "occurrences": sum(len(rows[t]["where"]) for t in order),
        "blues_only": sum(1 for t in order if all(w[0] == "blues" for w in rows[t]["where"])),
        "colonel_only": sum(1 for t in order if all(w[0] == "colonel" for w in rows[t]["where"])),
        "by_db": dict(collections.Counter(rows[t]["db"] for t in order)),
    }
    (ROOT / "analysis/strings_summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
