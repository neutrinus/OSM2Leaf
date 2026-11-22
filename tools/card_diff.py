#!/usr/bin/env python3
"""Compare two factory Leaf SD card images file by file (M1.54).

``manifest IMG -o OUT.json`` walks the card's FAT32 map partition and writes
one row per file: path, size, SHA-256. ``compare A.json B.json`` groups the
differences by top-level directory (and by second level under the system
folders), so a reviewer sees which parts of the card are region-specific:
files only on A, only on B, same path with equal bytes, same path with other
bytes. ``--detail DIR`` lists the files of one group.

The manifests carry only names, sizes and hashes, never file content, so
they can be committed as the review artifact of a card comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cardcheck import Fat32Image  # noqa: E402

CHUNK = 1 << 22


def file_sha256(img: Fat32Image, entry) -> str:
    h = hashlib.sha256()
    left = entry.size
    geo = img.geometry
    for cluster in img._cluster_chain(entry.cluster):
        if left <= 0:
            break
        block = img._read_cluster(cluster)
        h.update(block[:left])
        left -= geo.cluster_bytes
    return h.hexdigest()


def manifest(path: Path) -> dict:
    img = Fat32Image(path)
    rows = []
    for entry in img.walk():
        if entry.is_dir:
            continue
        rows.append({"path": entry.path, "size": entry.size,
                     "sha256": file_sha256(img, entry) if entry.size else hashlib.sha256(b"").hexdigest()})
    rows.sort(key=lambda r: r["path"].upper())
    return {"image": path.name, "files": len(rows),
            "bytes": sum(r["size"] for r in rows), "rows": rows}


def group_of(path: str, depth: int) -> str:
    parts = path.split("/")
    return "/".join(parts[:min(depth, len(parts) - 1)]) or "(root)"


def compare(a: dict, b: dict, depth: int, detail: str | None) -> str:
    ra = {r["path"].upper(): r for r in a["rows"]}
    rb = {r["path"].upper(): r for r in b["rows"]}
    groups: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for key in sorted(set(ra) | set(rb)):
        row = ra.get(key) or rb[key]
        g = group_of(row["path"], depth)
        if key not in rb:
            groups[g]["only_a"].append(ra[key])
        elif key not in ra:
            groups[g]["only_b"].append(rb[key])
        elif ra[key]["sha256"] == rb[key]["sha256"]:
            groups[g]["same"].append(ra[key])
        else:
            groups[g]["diff"].append((ra[key], rb[key]))
    out = [f"A = {a['image']} ({a['files']} files, {a['bytes']:,} B)",
           f"B = {b['image']} ({b['files']} files, {b['bytes']:,} B)", "",
           "| Group | only A (files / MB) | only B | same | differ (A MB / B MB) |",
           "| --- | --- | --- | --- | --- |"]

    def mb(rows):
        return sum(r["size"] for r in rows) / 1e6
    for g in sorted(groups):
        d = groups[g]
        diff = d["diff"]
        out.append(
            f"| `{g}` | {len(d['only_a'])} / {mb(d['only_a']):.1f} | "
            f"{len(d['only_b'])} / {mb(d['only_b']):.1f} | "
            f"{len(d['same'])} / {mb(d['same']):.1f} | "
            f"{len(diff)} ({mb([x for x, _ in diff]):.1f} / {mb([y for _, y in diff]):.1f}) |")
    if detail is not None:
        d = groups.get(detail, {})
        out += ["", f"## {detail}"]
        for kind in ("only_a", "only_b", "same"):
            for r in d.get(kind, []):
                out.append(f"{kind}\t{r['path']}\t{r['size']}")
        for x, y in d.get("diff", []):
            out.append(f"diff\t{x['path']}\t{x['size']}\t{y['size']}")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("manifest", help="hash every file on a card image")
    m.add_argument("image", type=Path)
    m.add_argument("-o", "--out", type=Path, required=True)
    c = sub.add_parser("compare", help="group the differences of two manifests")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    c.add_argument("--depth", type=int, default=1,
                   help="directory levels per group (default 1)")
    c.add_argument("--detail", help="list the files of one group")
    args = ap.parse_args(argv)
    if args.cmd == "manifest":
        data = manifest(args.image)
        args.out.write_text(json.dumps(data, indent=0, sort_keys=True) + "\n")
        print(f"{args.image.name}: {data['files']} files, {data['bytes']:,} B")
        return 0
    a = json.loads(args.a.read_text())
    b = json.loads(args.b.read_text())
    print(compare(a, b, args.depth, args.detail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
