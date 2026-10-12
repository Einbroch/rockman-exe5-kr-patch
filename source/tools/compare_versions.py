#!/usr/bin/env python3
"""Pair Blues/Colonel archives by decoded payload, not by offset.

Data after 0x3BE000 is shifted between the versions by amounts that differ per
structure, so no global delta is assumed: an archive is 'shared' when its
payload bytes are identical in both ROMs, otherwise it is version-specific.
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from decode_archives import payload  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ROMS = {"blues": ROOT.parents[1] / "Rockman EXE 5 - Team of Blues (Japan).gba",
        "colonel": ROOT.parents[1] / "Rockman EXE 5 - Team of Colonel (Japan).gba"}
CATALOGS = {"blues": ROOT / "analysis/archives_Blues.json",
            "colonel": ROOT / "analysis/archives_Colonel.json"}


def main() -> None:
    hashes = {}
    for version, path in ROMS.items():
        rom = path.read_bytes()
        catalog = json.loads(CATALOGS[version].read_text(encoding="utf-8"))
        by_hash = collections.defaultdict(list)
        for item in catalog["archives"]:
            by_hash[hashlib.sha256(payload(rom, item)).hexdigest()].append(item["rom_offset"])
        hashes[version] = by_hash
    blue, colo = hashes["blues"], hashes["colonel"]
    shared = sorted(set(blue) & set(colo))
    pairs = [{"sha256": h, "blues": blue[h], "colonel": colo[h]} for h in shared]
    deltas = collections.Counter(colo[h][0] - blue[h][0] for h in shared)
    report = {
        "schema_version": 1,
        "shared_payloads": len(shared),
        "blues_only_payloads": len(set(blue) - set(colo)),
        "colonel_only_payloads": len(set(colo) - set(blue)),
        "offset_deltas_of_shared": {("%+X" % k): v for k, v in deltas.most_common()},
        "blues_only": sorted(o for h in set(blue) - set(colo) for o in blue[h]),
        "colonel_only": sorted(o for h in set(colo) - set(blue) for o in colo[h]),
        "pairs": pairs,
    }
    out = ROOT / "analysis/version_pairs.json"
    out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("shared_payloads", "blues_only_payloads",
                                             "colonel_only_payloads", "offset_deltas_of_shared")}, indent=1))


if __name__ == "__main__":
    main()
