#!/usr/bin/env python3
"""Rebuild DRSTR001.DAT, MMAIN001.DAT 0x1ac totals, REFER001 .ind files and
CMP.LST for a Leaf ZE0 card tree so ``cardcheck`` L1 passes (M5.6).

The rebuild is structural: it makes the manifest/index files consistent with
the files actually present in the tree. It does not change map payload bytes
(except rewriting ``.ind`` headers and the compressed ``.cmp`` copy produced
by a stream-preserving pair rewrite) and never touches the FAT partition or
vendor image.

Policy (TODO.md M5.6, C-164/C-1788, EXP-2026-11-06-M3.8, M4.20/C-2100):
- ``DRSTR001.DAT``: rebuilt from the tree with ``drstr_ze0.build()``, which
  preserves an existing DRSTR's entry order and stored name case.
- ``MMAIN001.DAT``: the ``0x1ac`` level-table ``count`` values are recomputed
  as the sums over every ``MAPAL001/*.DAT`` tile header (same rule cardcheck
  enforces). All other bytes of the existing file are preserved. Counts are
  big-endian ``u16`` (C-1788). The firmware reads only the 4096-byte length
  (M3.8); ``cardcheck`` requires the sum to match.
- ``REFER001/*.ind``: every ``.cmp``/``.ind`` pair is read and rewritten
  stream-preserving (``cmpind_writer.CmpFile``), so the ``.ind`` header and
  chunk offsets match the actual ``.cmp`` bytes.
- ``CMP.LST``: written as ``\\SystemSD\\REFER001\\`` (19 bytes, no newline).

Usage:
    python3 tools/rebuild_manifests.py --root /path/to/card-tree
    python3 tools/rebuild_manifests.py --root /path/to/card-tree --check
    python3 tools/rebuild_manifests.py --selftest
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import cardcheck  # noqa: E402
import cmpind_writer  # noqa: E402
import drstr_ze0  # noqa: E402

CMP_LIST = b"\\SystemSD\\REFER001\\"
MMAIN_PATH = "MMAIN001.DAT"
DRSTR_PATH = "DRSTR001.DAT"
CMP_LST_PATH = "CMP.LST"
REFER_DIR = "REFER001"
MAPAL_DIR = "MAPAL001"


def rebuild_cmp_lst(root: Path) -> dict:
    path = root / CMP_LST_PATH
    before = path.read_bytes() if path.exists() else None
    path.write_bytes(CMP_LIST)
    return {"path": CMP_LST_PATH, "bytes": len(CMP_LIST),
            "changed": before != CMP_LIST}


def rebuild_drstr(root: Path, *, ignore_dump: bool = False) -> dict:
    path = root / DRSTR_PATH
    before = path.read_bytes() if path.exists() else None
    built = drstr_ze0.build(root, ignore_dump=ignore_dump)
    path.write_bytes(built)
    return {"path": DRSTR_PATH, "bytes": len(built),
            "changed": before != built}


def _tile_level_totals(root: Path) -> dict[tuple[int, int], tuple[int, int]]:
    """Sum (type, count) per (section, level) over every MAPAL001 tile header."""
    totals: dict[tuple[int, int], list[int]] = {}
    mapal = root / MAPAL_DIR
    if not mapal.is_dir():
        return {}
    for entry in sorted(mapal.iterdir(), key=lambda p: p.name):
        if entry.name.startswith("._") or entry.suffix.upper() != ".DAT":
            continue
        head = entry.read_bytes()[:0x400]
        for group in cardcheck.parse_level_table(head, 0x1AC):
            for row in group["rows"]:
                key = (group["section"], row["level"])
                acc = totals.setdefault(key, [row["type"], 0])
                acc[0] = row["type"]
                acc[1] += row["count"]
    return {k: (v[0], v[1]) for k, v in totals.items()}


def rebuild_mmain(root: Path) -> dict:
    path = root / MMAIN_PATH
    data = bytearray(path.read_bytes())
    totals = _tile_level_totals(root)
    master = cardcheck.parse_level_table(bytes(data), 0x1AC)
    changes = 0
    pos = 0x1AC + 2
    for group in master:
        pos += 2  # section, row_count
        for row in group["rows"]:
            key = (group["section"], row["level"])
            if key in totals:
                _, new_count = totals[key]
                old_count = struct.unpack_from(">H", data, pos + 2)[0]
                if old_count != new_count:
                    struct.pack_into(">H", data, pos + 2, new_count & 0xFFFF)
                    changes += 1
            pos += 4
    path.write_bytes(bytes(data))
    return {"path": MMAIN_PATH, "bytes": len(data),
            "count_fields_changed": changes,
            "tile_keys_summed": len(totals)}


def rebuild_refer_inds(root: Path) -> dict:
    refer = root / REFER_DIR
    rebuilt = errors = 0
    details = []
    if not refer.is_dir():
        return {"pairs": 0, "rebuilt": 0, "errors": 0, "details": []}
    for ind in sorted(refer.glob("*.ind")):
        if ind.name.startswith("._"):
            continue
        cmp_path = ind.with_suffix(".cmp")
        if not cmp_path.exists():
            errors += 1
            details.append({"pair": ind.stem, "error": "missing .cmp"})
            continue
        try:
            c = cmpind_writer.CmpFile.from_files(cmp_path, ind)
            c.write(refer, ind.stem)
            rebuilt += 1
        except Exception as exc:  # noqa: BLE001 - report per pair
            errors += 1
            details.append({"pair": ind.stem, "error": str(exc)})
    return {"pairs": rebuilt + errors, "rebuilt": rebuilt,
            "errors": errors, "details": details}


def rebuild(root: Path, *, ignore_dump: bool = False) -> dict:
    root = Path(root)
    result = {
        "root": str(root),
        "cmp_lst": rebuild_cmp_lst(root),
        "refer_ind": rebuild_refer_inds(root),
        "mmain": rebuild_mmain(root),
        "drstr": rebuild_drstr(root, ignore_dump=ignore_dump),
    }
    return result


def check(root: Path, **kwargs) -> tuple[bool, dict]:
    source = cardcheck.RootSource(Path(root))
    try:
        report = cardcheck.Report("L1", {"kind": "root", "path": str(root)})
        cardcheck.check_tree(source, report, partial=kwargs.get("partial", False),
                             ignore_artifacts=kwargs.get("ignore_dump", False))
        cardcheck.check_headers(source, report,
                                ignore_artifacts=kwargs.get("ignore_dump", False))
        cardcheck.check_cmp(source, report, fast=kwargs.get("fast", False),
                            ignore_artifacts=kwargs.get("ignore_dump", False))
        cardcheck.check_drstr(source, report, partial=kwargs.get("partial", False),
                              ignore_artifacts=kwargs.get("ignore_dump", False))
        cardcheck.check_mmain(source, report,
                              ignore_artifacts=kwargs.get("ignore_dump", False))
        cardcheck.check_version(source, report, partial=kwargs.get("partial", False))
        result = report.finish(strict=False)
    finally:
        source.close()
    return result["ok"], result


# ---- synthetic selftest (no vendor data) ---------------------------------

def _put_utf16be(buf: bytearray, off: int, text: str) -> None:
    raw = text.encode("utf-16-be")
    buf[off:off + len(raw)] = raw


def _synth_header(model: str = "CLA-NAVI05-01") -> bytearray:
    buf = bytearray(b"\xff" * 512)
    _put_utf16be(buf, 0x00, "CLARION")
    _put_utf16be(buf, 0x40, "HITACHI")
    _put_utf16be(buf, 0x80, model)
    _put_utf16be(buf, 0xA0, "FORMAT VERSION X08-02-00")
    _put_utf16be(buf, 0xE0, "DATA VERSION 11/06/27/01")
    buf[0x160:0x162] = b"\x16\x00"
    _put_utf16be(buf, 0x162, "V05.00.00")
    buf[0x180:0x18C] = bytes.fromhex("ff ff 24 ff 12 c0 05 00 fb 50 0f f0")
    buf[0x18C:0x1A0] = b"\x3f" * 20
    buf[0x1A0:0x1AC] = b"\xff" * 12
    return buf


def _write_level_table(buf: bytearray, groups: list[tuple[int, list[tuple]]]) -> None:
    struct.pack_into(">H", buf, 0x1AC, len(groups))
    pos = 0x1AE
    for sec, rows in groups:
        buf[pos] = sec
        buf[pos + 1] = len(rows)
        pos += 2
        for level, kind, count in rows:
            struct.pack_into(">BBH", buf, pos, level, kind, count)
            pos += 4


def _synth_mmain(wrong: bool = False) -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x1000 - len(buf)))
    # wrong=True: totals don't match the tile we'll create (forces rebuild)
    c = 99 if wrong else 1
    _write_level_table(buf, [(1, [(6, 0x80, c), (5, 0x90, c)])])
    return bytes(buf)


def _synth_tile() -> bytes:
    buf = bytearray(_synth_header())
    buf.extend(b"\x00" * (0x400 - len(buf)))
    _write_level_table(buf, [(1, [(6, 0x80, 1), (5, 0x90, 1)])])
    # bbox table at 0x2ac (cardcheck doesn't parse it, but harmless)
    struct.pack_into(">H", buf, 0x2AC, 1)
    buf[0x2AE] = 1; buf[0x2AF] = 1
    struct.pack_into(">BBhhhh", buf, 0x2B0, 2, 0, 1920, 1685, -720, -562)
    return bytes(buf)


def _synth_cmp_ind(root: Path, stem: str = "POINT001.DAT") -> None:
    # create a minimal valid .cmp/.ind pair whose decoded payload has a common header
    payload = bytearray(_synth_header())
    payload.extend(b"\x00" * 64)
    c = cmpind_writer.CmpFile.from_dat(bytes(payload))
    refer = root / REFER_DIR
    refer.mkdir(exist_ok=True)
    c.write(refer, stem)


def _synth_tree(root: Path, *, wrong_mmain: bool = False,
                wrong_cmp_lst: bool = False, drop_ind: bool = False) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for d in (MAPAL_DIR, REFER_DIR, "REFER002", "RDSTM001", "BICON001",
              "OPNG", "SPEECH", "TMC"):
        (root / d).mkdir(exist_ok=True)
    (root / MMAIN_PATH).write_bytes(_synth_mmain(wrong=wrong_mmain))
    (root / MAPAL_DIR / "LEV3456R.DAT").write_bytes(_synth_tile())
    (root / MAPAL_DIR / "B00R6CR.DAT").write_bytes(_synth_tile())  # lat 0, lon 0 hex C? use valid
    # actually use a name mesh_grid accepts? check pattern: BxxRyyR.DAT
    (root / MAPAL_DIR / "B00R6CR.DAT").unlink()
    (root / MAPAL_DIR / "B30R060R.DAT").write_bytes(_synth_tile())
    _synth_cmp_ind(root)
    if drop_ind:
        (root / REFER_DIR / "POINT001.DAT.ind").unlink()
        # recreate from cmp? impossible; instead create a deliberately bad ind
        (root / REFER_DIR / "POINT001.DAT.ind").write_bytes(b"\x00" * 16)
    (root / CMP_LST_PATH).write_bytes(b"WRONG" if wrong_cmp_lst else CMP_LIST)
    # minimal DRSTR (will be rebuilt)
    (root / DRSTR_PATH).write_bytes(drstr_ze0.build(root))


def selftest() -> int:
    import tempfile

    fails = []

    def chk(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"  ok   {name}")
        else:
            fails.append(f"{name}: {detail}" if detail else name)
            print(f"  FAIL {name} {detail}".rstrip())

    with tempfile.TemporaryDirectory(prefix="rebuild-m5.6-") as tmp:
        root = Path(tmp) / "tree"
        _synth_tree(root, wrong_mmain=True, wrong_cmp_lst=True)
        # break DRSTR by writing stale one? rebuild will fix it; also make it wrong
        (root / DRSTR_PATH).write_bytes(b"\x00" * 80)
        result = rebuild(root)
        chk("cmp_lst fixed", (root / CMP_LST_PATH).read_bytes() == CMP_LIST)
        chk("drstr written", len((root / DRSTR_PATH).read_bytes()) > 40)
        chk("mmain counts changed", result["mmain"]["count_fields_changed"] >= 1)
        chk("refer pair rebuilt", result["refer_ind"]["rebuilt"] == 1,
              str(result["refer_ind"]))
        ok, report = check(root, partial=True, fast=False)
        for c in report["checks"]:
            if c["errors"]:
                print(f"    {c['id']}: {c['errors']}")
        chk("L1 passes on rebuilt synthetic tree (partial)", ok,
            "; ".join(report["errors"][:5]))

        # idempotent
        r2 = rebuild(root)
        ok2, _ = check(root, partial=True)
        chk("second rebuild still L1-pass", ok2)
        chk("second mmain stable", r2["mmain"]["count_fields_changed"] == 0)

    print(f"selftest: {'OK' if not fails else 'FAIL'} ({len(fails)} failure(s))")
    if fails:
        for f in fails:
            print(f"  FAILED {f}")
    return 0 if not fails else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", help="card tree root")
    ap.add_argument("--check", action="store_true",
                    help="run cardcheck L1 on the root after rebuild")
    ap.add_argument("--partial", action="store_true")
    ap.add_argument("--ignore-dump-artifacts", action="store_true")
    ap.add_argument("--fast", action="store_true",
                    help="skip .cmp decompression in --check")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.root:
        ap.error("--root is required")
    result = rebuild(Path(args.root), ignore_dump=args.ignore_dump_artifacts)
    if args.check:
        ok, report = check(Path(args.root), partial=args.partial,
                           ignore_dump=args.ignore_dump_artifacts, fast=args.fast)
        result["l1"] = {"ok": ok, "errors": report["errors"],
                        "warnings": report["warnings"]}
        result["ok"] = ok
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"rebuilt manifests in {result['root']}")
        for k in ("cmp_lst", "drstr", "mmain", "refer_ind"):
            print(f"  {k}: {result[k]}")
        if "l1" in result:
            print(f"  L1: {'PASS' if result['l1']['ok'] else 'FAIL'}")
            for e in result["l1"]["errors"][:10]:
                print(f"    ERROR {e}")
    return 0 if result.get("ok", True) else 1


if __name__ == "__main__":
    raise SystemExit(main())
