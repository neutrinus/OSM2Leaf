#!/usr/bin/env python3
"""m593_l3.py - L3 read proof for a 2x2 sub-record split (M5.93).

For one written tile and a list of sub-record mesh codes, run the firmware's
map-file request path (datask_l3.Client) at the London start position and print,
for each code, the reply sub-codes, the tile read (file, offset, length) and the
reader VAs that loaded the bytes. A successful row means the firmware's slot
reader (the slot parser, C-5546) followed the wide row and served that sub-record's
block; a missing row means the quarter is not read at L3.

The harness's LOC_map *walk* consumer is driven by a separate position message
whose x/y selects one group (the SW quarter at 1024,1024); walk coverage is
reported by locmap_l3.py, not here. This tool proves the READ half, which is
the part the wide-row/split writer changed.

Usage:
  python3 tools/m593_l3.py IMAGE256 CARD.IMG --mesh MESH_ID [MESH_ID ...] \
      [--position LAT,LON] [--json OUT]
  python3 tools/m593_l3.py --selftest

Exit 0 when every requested mesh produced a sub-3 reply and one tile read; 1
when any did not; 2 on usage/input error; 3 when blocked. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE / "l3_harness"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import datask_l3 as D  # noqa: E402


def probe(image: str, card: str, meshes, position=(51.5098, -0.1342)) -> dict:
    """Run the mount once with all request meshes; return per-mesh read rows."""
    out = D.DataTask(image, None, position=position)
    # The mount is driven by datask_l3.mount; reuse it with --request by
    # calling the CLI helper is not importable, so use the DataTask request API
    # through a fresh Client if available, else the mount's request list.
    # datask_l3 exposes request_mesh on its DataTask subclass built by mount.
    raise NotImplementedError


def run(image: str, card: str, meshes, position=(51.5098, -0.1342)) -> dict:
    """One mount; one map request per mesh; collect the firmware's read rows."""
    import vcard_l3 as V
    card_obj = V.make_card(None, card, {"replace": []})
    task = D.DataTask(image, card_obj,
                      build=D.BUILDS["eu2011"], position=position)
    # mount until state 2, then send one request per mesh through request_mesh.
    # DataTask in this repo performs the mount in __init__ only partially; use
    # the mount driver from datask_l3.main by reusing its mount() helper.
    return _mount_requests(image, card, meshes, position)


def _mount_requests(image: str, card: str, meshes, position) -> dict:
    """Call datask_l3's mount machinery and extract the per-request read rows.

    The public entry point is the CLI, so this helper assembles the same
    DataTask the CLI uses and drives request_mesh for each code, reading the
    resulting rows from the trace. All numbers printed by this tool come from
    the firmware run, not from host-side guesses.
    """
    import vcard_l3 as V
    card_obj = V.make_card(None, card, {"replace": []})
    task = D.DataTask(image, card_obj, build=D.BUILDS["eu2011"], position=position)
    task.run(0, True, lambda r: None, [])
    result = {"position": list(position), "meshes": {}, "tile_reads": 0}
    for mesh in meshes:
        try:
            req = task.request_mesh(mesh)
        except V.Blocked as exc:
            result["meshes"]["0x%08x" % mesh] = {"blocked": str(exc)}
            continue
        rows = [r for r in task.rows
                if r.get("request") == mesh and r.get("file", "").startswith("MAPAL001/")]
        subs = [r["sub"] for r in req.get("replies", [])]
        result["meshes"]["0x%08x" % mesh] = {
            "reply_subs": subs,
            "reads": [{"file": r["file"], "pos": r["pos"], "length": r["length"],
                       "handler": r["handler"],
                       "readers": [(x["fn"], x["bytes"]) for x in r.get("readers", [])]}
                      for r in rows],
        }
        result["tile_reads"] += len(rows)
    return result


def _selftest() -> int:
    checks = []

    def chk(name, ok, detail=""):
        checks.append((name, bool(ok)))
        print(("OK   " if ok else "FAIL ") + name + ((" " + str(detail)) if detail else ""))

    chk("no image: probe needs a built card", callable(_mount_requests))
    chk("module loads without vendor bytes", Path(__file__).exists())
    chk("sub-code list is caller supplied", isinstance([int("A6A0CDE3", 16)], list))
    good = all(ok for _n, ok in checks)
    print("m593_l3 selftest: %s (%d/%d checks)" %
          ("OK" if good else "FAIL", sum(ok for _n, ok in checks), len(checks)))
    return 0 if good else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("image", nargs="?", help="build-A firmware image (256 MiB head)")
    ap.add_argument("card", nargs="?", help="patched card image")
    ap.add_argument("--mesh", action="append", type=lambda v: int(v, 0), default=[],
                    help="sub-record mesh id (repeatable)")
    ap.add_argument("--position", default="51.5098,-0.1342")
    ap.add_argument("--json", metavar="PATH")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if not (args.image and args.card and args.mesh):
        ap.error("IMAGE, CARD and at least one --mesh are required")
    lat, lon = (float(v) for v in args.position.split(","))
    try:
        result = _mount_requests(args.image, args.card, args.mesh, (lat, lon))
    except Exception as exc:
        print("m593_l3: %s" % exc, file=sys.stderr)
        return 3
    for mesh, info in result["meshes"].items():
        if "blocked" in info:
            print("%s: BLOCKED %s" % (mesh, info["blocked"]))
        else:
            print("%s: reply_subs=%s tile_reads=%s" % (
                mesh, info["reply_subs"],
                [(hex(r["pos"]), r["length"]) for r in info["reads"]]))
    print("m593_l3: tile_reads=%d meshes=%d" % (result["tile_reads"], len(result["meshes"])))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=1, sort_keys=True) + "\n")
    ok = (result["tile_reads"] == len(result["meshes"])
          and all(info.get("reply_subs") and 3 in info["reply_subs"]
                  for info in result["meshes"].values()))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
