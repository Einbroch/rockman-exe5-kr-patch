#!/usr/bin/env python3
"""Decode every candidate archive with TextPet (game exe5) and prove the round trip.

Payload:
  lz77  the whole decompressed data after the optional 4-byte size header (the
        last table value starts the last script; it is not the end);
  raw   a window up to the next pointer target, decoded, then the last script is
        cut at its first always-ending command (end/startBBS/startShop/
        startWarp/waitHold, or a jump whose target is not `continue`) and
        re-encoded: the re-encoded length is the archive's length, accepted
        only if those bytes equal the ROM.

Each archive is accepted only if TPL -> MSG reproduces its payload byte for byte
(`roundtrip`). Batches of TextPet runs fall back to one archive at a time,
because one unreadable file aborts the whole run.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from scan_text_archives import lz77_decompress  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TEXTPET = ROOT / "external" / "TextPet-v1.0.0" / "TextPet.exe"
PLUGINS = ROOT / "external" / "textpet-plugins"
ENDING = {"end", "startBBS", "startShop", "startWarp", "waitHold"}
BATCH = 40


def payload(rom: bytes, item: dict) -> bytes:
    """The archive bytes as the game sees them (decompressed, no size header)."""
    if item["storage"] == "raw":
        start = item["rom_offset"]
        length = item.get("payload_length") or item["window"]
        return rom[start:start + length]
    data, _ = lz77_decompress(rom, item["rom_offset"])
    head = item["size_header"]
    return data[head:]


def textpet(args: list[str]) -> bool:
    run = subprocess.run([str(TEXTPET), "silent", *args], capture_output=True, text=True, encoding="utf-8")
    return run.returncode == 0 and "Done." in (run.stdout or "")


def convert(files: dict[str, bytes], src_fmt: str, dst_fmt: str, plugins: Path, temp: Path) -> dict[str, bytes]:
    """Run TextPet over `files` (stem -> content); returns stem -> output, missing on failure."""
    results: dict[str, bytes] = {}

    def run(group: list[str]) -> bool:
        src, dst = temp / "src", temp / "dst"
        for d in (src, dst):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir()
        ext_in = ".msg" if src_fmt == "bin" else ".tpl"
        ext_out = ".msg" if dst_fmt == "bin" else ".tpl"
        for stem in group:
            (src / (stem + ext_in)).write_bytes(files[stem])
        ok = textpet(["load-plugins", str(plugins) + "\\", "game", "exe5",
                      "read-text-archives", str(src) + "\\", "-f", src_fmt,
                      "write-text-archives", str(dst) + "\\", "-f", dst_fmt])
        if not ok:
            return False
        for stem in group:
            path = dst / (stem + ext_out)
            if path.is_file():
                results[stem] = path.read_bytes()
        return True

    stems = list(files)
    for i in range(0, len(stems), BATCH):
        group = stems[i:i + BATCH]
        if not run(group):
            for stem in group:
                run([stem])
    return results


SCRIPT_HEAD = re.compile(r"^script (\d+) (\S+) \{$")


def cut_last_script(tpl: str) -> tuple[str, bool]:
    """Truncate the last script after its first always-ending top-level command.

    Returns (tpl, found). Without an ending command the last table value is
    taken as the archive end (an empty end-marker script); the caller records
    that assumption so the archive can be reviewed.
    """
    lines = tpl.replace("\r\n", "\n").split("\n")
    heads = [i for i, line in enumerate(lines) if SCRIPT_HEAD.match(line)]
    if not heads:
        return tpl, False
    start = heads[-1]
    i = start + 1
    in_block = False
    while i < len(lines):
        line = lines[i]
        if in_block:
            if line.strip() == '"""':
                in_block = False
            i += 1
            continue
        if line.startswith("\t$"):
            break  # undecodable byte before any ending: not script data
        if line.startswith("\t") and not line.startswith("\t\t"):
            body = line[1:]
            if body == '"""':
                in_block = True
                i += 1
                continue
            name = body.split()[0] if body.split() else ""
            params, j = [], i + 1
            while j < len(lines) and lines[j].startswith("\t\t"):
                params.append(lines[j].strip())
                j += 1
            ends = name in ENDING or (name == "jump" and "target = continue" not in params)
            if ends:
                return "\n".join(lines[:j] + ["}", ""]), True
            i = j
            continue
        i += 1
    return empty_last(tpl), False


LEADING_BLANK_BLOCK = re.compile(r'"""\n(\t\n.*?)\n\t"""', re.S)


def keep_leading_newline(tpl: str) -> str:
    """TextPet writes a string that starts with a line break as a \"\"\" block whose
    first line is empty, and drops that line break when reading it back
    (07DA780: `ec 01 12 e9` -> `ec 01 12`). A plain quoted string with the same
    real line breaks round-trips, so such blocks are rewritten to that form."""
    def plain(m: re.Match) -> str:
        lines = [line[1:] if line.startswith("\t") else line for line in m.group(1).split("\n")]
        return '"' + "\n".join(lines) + '"'
    return LEADING_BLANK_BLOCK.sub(plain, tpl.replace("\r\n", "\n"))


def empty_last(tpl: str) -> str:
    """The TPL with its last script emptied (the last table value is the end)."""
    lines = tpl.replace("\r\n", "\n").split("\n")
    start = [i for i, line in enumerate(lines) if SCRIPT_HEAD.match(line)][-1]
    m = SCRIPT_HEAD.match(lines[start])
    return "\n".join(lines[:start] + ["script %s %s {" % (m.group(1), m.group(2)), "}", ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--tpl-dir", type=Path, required=True)
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    items = {"%07X" % a["rom_offset"]: a for a in catalog["archives"]}
    starts = sorted(a["rom_offset"] for a in catalog["archives"])
    # Raw window: up to the next candidate start (other data follows otherwise).
    for k, a in items.items():
        if a["storage"] == "raw":
            nxt = next((s for s in starts if s > a["rom_offset"]), len(rom))
            a["window"] = max(a["table_bytes"], min(a["window"], nxt - a["rom_offset"]))
            a["payload_length"] = None
    args.tpl_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="exe5-decode-") as name:
        temp = Path(name)
        plugins = temp / "plugins"
        shutil.copytree(PLUGINS, plugins)
        work = temp / "work"
        work.mkdir()
        first = convert({k: payload(rom, a) for k, a in items.items()}, "bin", "tpl", plugins, work)
        tpls = {}
        for k, raw_tpl in first.items():
            text = keep_leading_newline(raw_tpl.decode("utf-8-sig"))
            if items[k]["storage"] == "raw":
                tpls[k], found = cut_last_script(text)
                items[k]["last_script_end"] = "ending_command" if found else "assumed_empty"
            else:
                tpls[k] = text
        back = convert({k: v.encode("utf-8") for k, v in tpls.items()}, "tpl", "bin", plugins, work)
        # A cut that does not reproduce the ROM decoded data past the archive
        # (an `end` inside foreign bytes): fall back to an empty last script.
        retry = {}
        for k, a in items.items():
            if a["storage"] == "raw" and a.get("last_script_end") == "ending_command":
                msg = back.get(k)
                if msg is None or rom[a["rom_offset"]:a["rom_offset"] + len(msg)] != msg:
                    tpls[k] = empty_last(keep_leading_newline(first[k].decode("utf-8-sig")))
                    a["last_script_end"] = "assumed_empty_after_failed_cut"
                    retry[k] = tpls[k].encode("utf-8")
        if retry:
            back.update(convert(retry, "tpl", "bin", plugins, work))
    ok = 0
    for k, a in items.items():
        a.pop("decode_error", None)
        if k not in first:
            a["decoded"], a["roundtrip"] = False, False
            a["decode_error"] = "TextPet could not read the payload"
            continue
        a["decoded"] = True
        msg = back.get(k)
        if a["storage"] == "raw":
            if msg is not None and rom[a["rom_offset"]:a["rom_offset"] + len(msg)] == msg:
                a["payload_length"] = len(msg)
                a["roundtrip"] = True
            else:
                a["roundtrip"] = False
        else:
            a["roundtrip"] = msg == payload(rom, a)
        if a["roundtrip"]:
            (args.tpl_dir / (k + ".tpl")).write_text(tpls[k], encoding="utf-8")
            ok += 1
    catalog["decoded_count"] = sum(1 for a in items.values() if a["decoded"])
    catalog["roundtrip_count"] = ok
    args.catalog.write_text(json.dumps(catalog, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    failed = [k for k, a in items.items() if not a.get("roundtrip")]
    print(json.dumps({"rom": args.rom.name, "candidates": len(items), "decoded": catalog["decoded_count"],
                      "roundtrip": ok, "failed_sample": failed[:20]}))


if __name__ == "__main__":
    main()
