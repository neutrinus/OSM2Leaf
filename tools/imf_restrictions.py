#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""List and decode turn restrictions in an IMF file (output of tools/osm_ingest.py).

    python3 tools/imf_restrictions.py IMF.jsonl --named [--limit N]
    python3 tools/imf_restrictions.py IMF.jsonl --id r120176
    python3 tools/imf_restrictions.py --selftest

--named lists the restriction relations whose from and to ways carry a name and
whose via member is a node. --id decodes one relation: the from way, the to way,
the via node, which end of each way the via node is, and how many ways of the
file use the via node (the junction degree). It stops there: the tile-side
connectivity encoding is M4.3's open question, see docs/experiments/EXP-2026-11-08-M4.3-turn-restrictions.md.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
import tempfile
from pathlib import Path


def load(path: Path):
    """(ways, nodes, relations) keyed by IMF id; IMF is JSON Lines after the header."""
    ways, nodes, rels = {}, {}, {}
    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if n == 1 or not line.strip():
                continue
            rec = json.loads(line)
            kind = rec.get("type")
            if kind == "way":
                ways[rec["id"]] = rec
            elif kind == "node":
                nodes[rec["id"]] = rec
            elif kind == "relation":
                rels[rec["id"]] = rec
    return ways, nodes, rels


def degree(ways):
    """Number of ways that use each node id."""
    deg = collections.Counter()
    for w in ways.values():
        deg.update(set(w.get("nodes", [])))
    return deg


def members(rel):
    """{role: ref} for the from/via/to members; a role repeated keeps the first."""
    out = {}
    for m in rel.get("members", []):
        out.setdefault(m.get("role"), m)
    return out


def named_restrictions(ways, rels):
    """Yield (relation id, restriction, from name, to name, via id, from id, to id)."""
    for rid, rel in rels.items():
        if rel.get("tags", {}).get("type") != "restriction":
            continue
        m = members(rel)
        if not all(k in m for k in ("from", "via", "to")):
            continue
        f, v, t = m["from"]["ref"], m["via"]["ref"], m["to"]["ref"]
        if m["via"].get("type") != "node" or f not in ways or t not in ways:
            continue
        nf = ways[f].get("tags", {}).get("name")
        nt = ways[t].get("tags", {}).get("name")
        if nf and nt:
            yield rid, rel["tags"].get("restriction"), nf, nt, v, f, t


def decode(ways, rels, deg, rid):
    """Dict describing one relation, or None when it is not a decodable restriction."""
    rel = rels.get(rid)
    if rel is None:
        return None
    m = members(rel)
    if not all(k in m for k in ("from", "via", "to")):
        return None
    f, v, t = m["from"]["ref"], m["via"]["ref"], m["to"]["ref"]
    if f not in ways or t not in ways:
        return None
    fw, tw = ways[f], ways[t]
    fn, tn = fw.get("nodes", []), tw.get("nodes", [])
    return {
        "id": rid,
        "restriction": rel.get("tags", {}).get("restriction"),
        "from": {"id": f, "name": fw.get("tags", {}).get("name"), "oneway": fw.get("tags", {}).get("oneway"),
                 "nodes": len(fn), "via_end": "last" if fn and fn[-1] == v else "first" if fn and fn[0] == v else "inside" if v in fn else "absent"},
        "via": {"id": v, "degree": deg.get(v, 0)},
        "to": {"id": t, "name": tw.get("tags", {}).get("name"), "oneway": tw.get("tags", {}).get("oneway"),
               "nodes": len(tn), "via_end": "first" if tn and tn[0] == v else "last" if tn and tn[-1] == v else "inside" if v in tn else "absent"},
    }


def cmd_list(path: Path, limit: int) -> int:
    ways, _, rels = load(path)
    deg = degree(ways)
    hits = list(named_restrictions(ways, rels))
    print(f"restriction relations {sum(1 for r in rels.values() if r.get('tags', {}).get('type') == 'restriction')}")
    print(f"named from/to with a node via {len(hits)}")
    for rid, kind, nf, nt, v, f, t in hits[:limit]:
        print(f"{rid}\t{kind}\t{nf} -> {nt}\tvia {v} degree {deg.get(v, 0)}\tfrom {f}\tto {t}")
    return 0


def cmd_id(path: Path, rid: str) -> int:
    ways, _, rels = load(path)
    info = decode(ways, rels, degree(ways), rid)
    if info is None:
        print(f"{rid}: not a decodable restriction (missing relation, member or way)", file=sys.stderr)
        return 1
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def selftest() -> int:
    """A synthetic IMF: a T-junction with one no_left_turn and one unnamed from way."""
    lines = [
        {"imf": 1, "type": "header"},
        {"imf": 1, "type": "node", "id": "n1", "lat": 51.0, "lon": 17.0},
        {"imf": 1, "type": "node", "id": "n2", "lat": 51.001, "lon": 17.0},
        {"imf": 1, "type": "node", "id": "n3", "lat": 51.0, "lon": 17.001},
        {"imf": 1, "type": "node", "id": "n4", "lat": 51.0, "lon": 16.999},
        {"imf": 1, "type": "way", "id": "w1", "nodes": ["n1", "n2"], "tags": {"highway": "primary", "name": "Alfa", "oneway": "yes"}},
        {"imf": 1, "type": "way", "id": "w2", "nodes": ["n2", "n3"], "tags": {"highway": "primary", "name": "Beta"}},
        {"imf": 1, "type": "way", "id": "w3", "nodes": ["n2", "n4"], "tags": {"highway": "primary"}},
        {"imf": 1, "type": "relation", "id": "r1", "members": [
            {"type": "way", "ref": "w1", "role": "from"},
            {"type": "node", "ref": "n2", "role": "via"},
            {"type": "way", "ref": "w2", "role": "to"}],
         "tags": {"type": "restriction", "restriction": "no_left_turn"}},
        {"imf": 1, "type": "relation", "id": "r2", "members": [
            {"type": "way", "ref": "w3", "role": "from"},
            {"type": "node", "ref": "n2", "role": "via"},
            {"type": "way", "ref": "w2", "role": "to"}],
         "tags": {"type": "restriction", "restriction": "no_u_turn"}},
    ]
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "t.imf.jsonl"
        path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
        ways, _, rels = load(path)
        deg = degree(ways)
        named = [h[0] for h in named_restrictions(ways, rels)]
        if named != ["r1"]:
            failures.append(f"named restrictions {named}, want ['r1'] (r2 has an unnamed from way)")
        info = decode(ways, rels, deg, "r1")
        if info is None:
            failures.append("decode r1 returned None")
        else:
            if info["via"]["degree"] != 3:
                failures.append(f"via degree {info['via']['degree']}, want 3")
            if info["from"]["via_end"] != "last" or info["to"]["via_end"] != "first":
                failures.append(f"via ends {info['from']['via_end']}/{info['to']['via_end']}, want last/first")
            if info["restriction"] != "no_left_turn":
                failures.append("restriction kind lost")
        if decode(ways, rels, deg, "r999") is not None:
            failures.append("missing relation decoded")
    for msg in failures:
        print("FAIL", msg)
    if failures:
        return 1
    print("imf_restrictions selftest: OK (3 checks)")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("imf", nargs="?", type=Path)
    ap.add_argument("--named", action="store_true", help="list named from/to restrictions")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--id", help="decode one restriction relation, e.g. r120176")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.imf is None:
        ap.error("IMF file required")
    if args.id:
        return cmd_id(args.imf, args.id)
    return cmd_list(args.imf, args.limit)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
