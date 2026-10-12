#!/usr/bin/env python3
"""Make TextPet's mmbn5 command databases round-trip EXE5 bytes exactly.

Two defects were found by TPL -> MSG byte comparison (decode_archives.py):

1. `[Extension]` blocks decode (FA 03 00 01 is read as printModBuffer) but
   re-encode with the parent command's base (FA 02 00 01). Every extension is
   therefore expanded into its own `[Command]` (name + "_" + base hex) with the
   parent's parameters, so encoding is unique.
2. printFolderName.entry is 4 bits but data uses the whole byte (FA 00 22 04
   came back as FA 00 02 04); widened to 8 bits, as in the EXE4 project.

Source files are kept as external/textpet-plugins-pristine/<name>.orig and the
patched files are regenerated from them, never edited in place.
"""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "external/textpet-plugins"
PRISTINE = ROOT / "external/textpet-plugins-pristine"
FILES = ["mmbn5.ini", "mmbn5s.ini"]


def sections(text: str) -> list[str]:
    parts = re.split(r"(?m)^(?=\[(?:Command|Extension|CommandDatabase)\])", text)
    return [p for p in parts if p]


def field(block: str, key: str) -> str | None:
    m = re.search(r"(?m)^%s = (.*)$" % re.escape(key), block)
    return m.group(1).strip() if m else None


def patch(text: str) -> tuple[str, list[str]]:
    blocks = sections(text)
    commands = {}
    for b in blocks:
        if b.startswith("[Command]"):
            commands.setdefault(field(b, "name"), b)
    notes, out = [], []
    for b in blocks:
        if b.startswith("[Extension]"):
            name, mask, base = field(b, "name"), field(b, "mask"), field(b, "base")
            parent = commands.get(name)
            if parent is None:
                raise SystemExit("extension without parent: %s" % name)
            new_name = "%s_%s" % (name, base.replace(" ", ""))
            clone = re.sub(r"(?m)^name = .*$", "name = " + new_name, parent, count=1)
            clone = re.sub(r"(?m)^mask = .*$", "mask = " + mask, clone, count=1)
            clone = re.sub(r"(?m)^base = .*$", "base = " + base, clone, count=1)
            out.append(clone)
            notes.append("extension %s %s -> command %s" % (name, base, new_name))
            continue
        if b.startswith("[Command]") and field(b, "name") == "printFolderName":
            fixed = re.sub(r"(\[Parameter\]\nname = entry\noffs = 2\nbits = )4", r"\g<1>8", b)
            if fixed != b:
                notes.append("printFolderName.entry 4 -> 8 bits")
            b = fixed
        out.append(b)
    return "".join(out), notes


def main() -> None:
    PRISTINE.mkdir(exist_ok=True)
    for name in FILES:
        orig = PRISTINE / (name + ".orig")
        if not orig.exists():
            shutil.copy2(PLUGINS / name, orig)
        text = orig.read_text(encoding="utf-8")
        new, notes = patch(text)
        (PLUGINS / name).write_text(new, encoding="utf-8", newline="\n")
        print(name, hashlib.sha256(orig.read_bytes()).hexdigest()[:12], "->",
              hashlib.sha256(new.encode()).hexdigest()[:12])
        for n in notes:
            print("  ", n)


if __name__ == "__main__":
    main()
