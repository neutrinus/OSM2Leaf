#!/usr/bin/env python3
"""Map QEMU ``ze0`` SD block reads to card files through the card's FAT32.

TODO M8.H8.  One L4 boot of the EU 2011 card tells which map files ``Navi.exe``
reads and which byte ranges of each file it consumes.  This tool turns a
block-read log plus the card image into:

* per-file read ranges, in time order (human output);
* a per-file coverage table (bytes read / file size / cluster read-ahead);
* a machine-readable JSON report (``--json``).

Two trace grammars are accepted; both are derived from committed sources, not
guessed:

1. ``-trace sdcard_read_block`` from QEMU 11.1.3.  This tree's
   ``hw/sd/trace-events`` declares
   ``sdcard_read_block(uint64_t addr, uint32_t len) "addr 0x%" PRIx64 " size 0x%x"``
   and its only caller ``hw/sd/sd.c:sd_blk_read()`` passes the byte offset that
   ``sd_req_get_address()`` computed (``arg << 9`` for SDHC) and ``sd_part_offset()``
   returns 0 for an SD card.  So ``addr`` is a byte offset into the card image
   and ``size`` is a byte count.  Example line::

       sdcard_read_block addr 0x6400400 size 0x200

2. The HPB-DMAC transfer log already parsed by ``tools/ze0_sdhost.py``.
   ``decode_dma()`` pairs SD command writes with ``ze0-hpbdmac: chN read ...``
   lines; for SDHC CMD17/CMD18 the byte offset is ``arg * 512`` (the same
   conversion ``ze0_sdhost.check_card()`` uses).

The card→file map uses ``tools/cardcheck.py:Fat32Image`` (MBR → FAT32 boot
sector → FAT chains → directory entries).  A file's cluster chain becomes a
sorted list of on-card byte extents; a read is overlapped against those extents
and the file-relative ranges are emitted.  A read that runs past a file's
logical size is reported as **cluster read-ahead** (the FAT unit is one 64 KiB
cluster, so a 4 KiB ``MMAIN001.DAT`` still occupies a whole cluster).  A block
that overlaps no file extent is **unmapped**, never silently attributed.

Usage::

    python3 tools/ze0_sdtrace.py RUNDIR --card CARD.img --json
    python3 tools/ze0_sdtrace.py LOG   --card CARD.img
    python3 tools/ze0_sdtrace.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import struct
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cardcheck  # noqa: E402
import leafimg  # noqa: E402
import ze0_sdhost  # noqa: E402

SECTOR = 512

# QEMU -trace sdcard_read_block (hw/sd/trace-events, QEMU 11.1.3).
QEMU_READ_RE = re.compile(
    r"sdcard_read_block\s+addr\s+0x([0-9a-fA-F]+)\s+size\s+0x([0-9a-fA-F]+)"
)


@dataclass
class ReadEvent:
    """One guest SD read, attributed (or not) to card-file extents."""

    seq: int
    card_start: int
    length: int
    source: str = ""  # "qemu-trace" | "dmac"
    cmd: str = ""
    # Attributed sub-ranges: (path, file_start, file_end, cluster_readahead).
    ranges: list[tuple[str, int, int, bool]] = field(default_factory=list)
    unmapped: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Extent:
    """A contiguous run of card bytes belonging to one file."""

    card_start: int
    card_end: int
    path: str
    file_offset: int  # file offset of card_start
    file_size: int

    @property
    def logical_end(self) -> int:
        """card_end clamped to the file's logical size."""
        remain = self.file_size - self.file_offset
        if remain <= 0:
            return self.card_start
        return min(self.card_end, self.card_start + remain)


# ---------------------------------------------------------------------------
# trace parsing
# ---------------------------------------------------------------------------


def parse_qemu_trace(text: str) -> list[tuple[int, int, str]]:
    """Return [(card_start, length, source)] in log order."""
    out: list[tuple[int, int, str]] = []
    for line in text.splitlines():
        m = QEMU_READ_RE.search(line)
        if m:
            out.append((int(m.group(1), 16), int(m.group(2), 16), "qemu-trace"))
    return out


def parse_dmac_log(text: str) -> list[tuple[int, int, str]]:
    """Return [(card_start, length, 'dmac CMDxx')] from a ze0_hpbdmac log."""
    out: list[tuple[int, int, str]] = []
    for port, name, arg, direction, nbytes, _addr, _left, _crc in ze0_sdhost.decode_dma(text):
        if direction == "read" and name in ("CMD17+data", "CMD18+data"):
            out.append((arg * SECTOR, nbytes, "dmac " + name))
    return out


def parse_log(text: str) -> tuple[list[tuple[int, int, str]], str]:
    """Auto-detect a grammar and return (events, grammar name)."""
    qemu = parse_qemu_trace(text)
    if qemu:
        return qemu, "qemu-trace:sdcard_read_block"
    dmac = parse_dmac_log(text)
    if dmac:
        return dmac, "dmac:ze0_sdhost.decode_dma"
    return [], "none"


def gather_logs(rundir: Path, explicit_log: str | None) -> str:
    """Concatenate candidate log files from RUNDIR (or read one explicit log)."""
    if explicit_log:
        return Path(explicit_log).read_text(encoding="utf-8", errors="replace")
    if rundir.is_file():
        return rundir.read_text(encoding="utf-8", errors="replace")
    chunks: list[str] = []
    # Read every small text log in the run directory.  qemu.log can be ~GB, so
    # stream it line by line and keep only lines our parsers recognise.
    patterns = ("*.log", "*.trace", "*.txt")
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(rundir.glob(pattern)):
            rp = path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if QEMU_READ_RE.search(line) or "ze0-hpbdmac:" in line or "ze0-sdhi" in line:
                        chunks.append(line.rstrip("\n"))
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# FAT → extents
# ---------------------------------------------------------------------------


def build_extents(card_path: str) -> tuple[list[Extent], dict]:
    """Build the sorted on-card extent list from the card's FAT32."""
    source = cardcheck.Fat32Image(Path(card_path))
    try:
        geo = source.geometry
        data_start = geo.partition_offset + (
            geo.reserved_sectors + geo.fat_count * geo.fat_size_sectors
        ) * geo.bytes_per_sector
        cluster_bytes = geo.cluster_bytes
        extents: list[Extent] = []
        files = 0
        for entry in source.walk():
            if entry.is_dir or not entry.cluster:
                continue
            files += 1
            chain = source._cluster_chain(entry.cluster)
            for i, cluster in enumerate(chain):
                start = data_start + (cluster - 2) * cluster_bytes
                end = start + cluster_bytes
                extents.append(Extent(start, end, entry.path, i * cluster_bytes, entry.size))
        extents.sort(key=lambda e: (e.card_start, e.card_end))
        meta = {
            "card": os.path.abspath(card_path),
            "label": geo.label,
            "partition_offset": geo.partition_offset,
            "cluster_bytes": cluster_bytes,
            "files": files,
            "extents": len(extents),
        }
        return extents, meta
    finally:
        source.close()


def attribute(events: list[tuple[int, int, str]], extents: list[Extent]) -> list[ReadEvent]:
    """Map each read to file-relative byte ranges; keep unmapped blocks."""
    # Simple sweep: extents are few hundred to a few thousand; events can be
    # thousands.  Build a start-sorted index and use bisect to limit the scan.
    import bisect

    starts = [e.card_start for e in extents]
    out: list[ReadEvent] = []
    for seq, (start, length, source) in enumerate(events, 1):
        end = start + length
        ev = ReadEvent(seq=seq, card_start=start, length=length, source=source)
        # Find the first extent that could overlap [start, end).
        idx = bisect.bisect_right(starts, start) - 1
        if idx < 0:
            idx = 0
        cursor = start
        while idx < len(extents):
            ext = extents[idx]
            if ext.card_start >= end:
                break
            if ext.card_end <= cursor:
                idx += 1
                continue
            lo = max(cursor, ext.card_start)
            hi = min(end, ext.card_end)
            if lo < hi:
                logical_hi = min(hi, ext.logical_end)
                if logical_hi > lo:
                    ev.ranges.append(
                        (ext.path, lo - ext.card_start + ext.file_offset,
                         logical_hi - ext.card_start + ext.file_offset, False)
                    )
                if hi > logical_hi:
                    # Bytes past the file's logical size: cluster read-ahead.
                    ev.ranges.append(
                        (ext.path, logical_hi - ext.card_start + ext.file_offset,
                         hi - ext.card_start + ext.file_offset, True)
                    )
                cursor = max(cursor, hi)
            idx += 1
        if cursor < end:
            ev.unmapped.append((cursor, end))
        out.append(ev)
    return out


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def coverage(events: list[ReadEvent]) -> list[dict]:
    """Per-file coverage: exact logical ranges and cluster read-ahead bytes."""
    per: dict[str, dict] = {}
    for ev in events:
        for path, fs, fe, ra in ev.ranges:
            row = per.setdefault(path, {
                "path": path, "ranges": [], "read_bytes": 0,
                "readahead_bytes": 0, "first_seq": ev.seq, "reads": 0,
            })
            row["ranges"].append((fs, fe, ra, ev.seq))
            if ra:
                row["readahead_bytes"] += fe - fs
            else:
                row["read_bytes"] += fe - fs
                row["reads"] += 1
    out = []
    for path, row in per.items():
        # Merge adjacent/overlapping logical ranges for a compact table.
        logical = sorted((a, b) for a, b, ra, _s in row["ranges"] if not ra)
        merged: list[list[int]] = []
        for a, b in logical:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        out.append({
            "path": path,
            "first_seq": row["first_seq"],
            "reads": row["reads"],
            "read_bytes": row["read_bytes"],
            "readahead_bytes": row["readahead_bytes"],
            "ranges": [[a, b] for a, b in merged],
        })
    out.sort(key=lambda r: (r["first_seq"], r["path"]))
    return out


def make_report(events: list[ReadEvent], extents: list[Extent], meta: dict,
                grammar: str, rundir: str) -> dict:
    cov = coverage(events)
    mapped = sum(1 for e in events if e.ranges)
    unmapped_events = sum(1 for e in events if e.unmapped)
    return {
        "run": os.path.abspath(rundir),
        "grammar": grammar,
        "fat": meta,
        "summary": {
            "read_events": len(events),
            "mapped_events": mapped,
            "unmapped_events": unmapped_events,
            "files_seen": len(cov),
            "total_read_bytes": sum(e.length for e in events),
        },
        "coverage": cov,
        "events": [
            {
                "seq": e.seq,
                "card_start": e.card_start,
                "length": e.length,
                "source": e.source,
                "ranges": [list(r) for r in e.ranges],
                "unmapped": [list(u) for u in e.unmapped],
            }
            for e in events
        ],
    }


def print_report(report: dict) -> None:
    s = report["summary"]
    print("grammar: %s" % report["grammar"])
    print("card: %s (label %r, cluster %d B, %d files, %d extents)"
          % (report["fat"]["card"], report["fat"]["label"],
             report["fat"]["cluster_bytes"], report["fat"]["files"],
             report["fat"]["extents"]))
    print("reads: %d events, %d mapped, %d with unmapped bytes, %d bytes total"
          % (s["read_events"], s["mapped_events"], s["unmapped_events"],
             s["total_read_bytes"]))
    print("files seen: %d" % s["files_seen"])
    print()
    print("Per-file read ranges (time order; file-relative byte offsets):")
    for row in report["coverage"]:
        ranges = ", ".join("0x%x-0x%x" % (a, b) for a, b in row["ranges"])
        note = ""
        if row["readahead_bytes"]:
            note = "  [cluster read-ahead %d B]" % row["readahead_bytes"]
        print("  %-40s reads=%-4d bytes=%-10d ranges=%s%s"
              % (row["path"], row["reads"], row["read_bytes"], ranges, note))
    unmapped = [e for e in report["events"] if e["unmapped"]]
    if unmapped:
        print()
        print("Unmapped reads (%d events):" % len(unmapped))
        for e in unmapped[:20]:
            print("  seq %d card 0x%x len %d -> %s"
                  % (e["seq"], e["card_start"], e["length"], e["unmapped"]))
        if len(unmapped) > 20:
            print("  ... %d more" % (len(unmapped) - 20))


# ---------------------------------------------------------------------------
# selftest — a synthetic FAT32 image, positive and negative controls
# ---------------------------------------------------------------------------


def _synthetic_card(path: Path) -> dict:
    """Write a tiny FAT32 image with three known files at known clusters.

    Geometry: 512 B/sector, 1 sector/cluster, partition at LBA 8, reserved 1,
    one FAT of 1 sector, root cluster 2.  data_start = 4096 + 2*512 = 5120.
    Returns the expected {path: (cluster, size, first-card-byte)}.
    """
    part_off = 8 * 512
    total_bytes = part_off + (1 + 1 + 8) * 512  # boot + FAT + 8 data clusters
    img = bytearray(total_bytes)
    # MBR: one FAT32 (0x0b) partition at LBA 8.
    struct.pack_into("<I", img, 0x1BE + 8, 8)          # start LBA
    struct.pack_into("<I", img, 0x1BE + 12, 16)        # sector count
    img[0x1BE + 4] = 0x0B
    img[0x1FF] = 0x55
    img[0x1FE] = 0xAA
    # Boot sector at partition offset.
    bs = part_off
    struct.pack_into("<H", img, bs + 11, 512)          # bytes/sector
    img[bs + 13] = 1                                   # sectors/cluster
    struct.pack_into("<H", img, bs + 14, 1)            # reserved
    img[bs + 16] = 1                                   # fat count
    struct.pack_into("<I", img, bs + 32, 16)           # total sectors
    struct.pack_into("<I", img, bs + 36, 1)            # fat size
    struct.pack_into("<I", img, bs + 44, 2)            # root cluster
    img[bs + 71:bs + 82] = b"SYNTH       "
    # FAT at part_off + 512.  Clusters: 2 root, 3 MMAIN, 4->5 DRSTR, 6 CMP.
    fat = part_off + 512
    EOC = 0x0FFFFFFF
    for cluster, value in {2: EOC, 3: EOC, 4: 5, 5: EOC, 6: EOC}.items():
        struct.pack_into("<I", img, fat + 4 * cluster, value)

    def short_entry(name: str, attr: int, cluster: int, size: int) -> bytes:
        e = bytearray(32)
        e[0:11] = name.encode("ascii").ljust(11, b" ")
        e[11] = attr
        struct.pack_into("<H", e, 20, cluster >> 16)
        struct.pack_into("<H", e, 26, cluster & 0xFFFF)
        struct.pack_into("<I", e, 28, size)
        return bytes(e)

    root = part_off + 2 * 512
    img[root:root + 32] = short_entry("SYNTH       ", 0x08, 2, 0)  # volume label
    files = {
        "MMAIN001.DAT": (3, 100),
        "DRSTR001.DAT": (4, 200),
        "CMP.LST": (6, 19),
    }
    pos = root + 32
    for name, (cluster, size) in files.items():
        base, ext = name.split(".")
        short = ("%-8s%-3s" % (base, ext)).encode("ascii")
        img[pos:pos + 32] = short_entry(short.decode(), 0x20, cluster, size)
        pos += 32
    path.write_bytes(img)

    data_start = part_off + 2 * 512
    expected = {
        name: (cluster, size, data_start + (cluster - 2) * 512)
        for name, (cluster, size) in files.items()
    }
    return {"part_off": part_off, "data_start": data_start,
            "cluster_bytes": 512, "files": expected}


def selftest() -> int:
    import tempfile

    fails = 0

    def check(label: str, got, want) -> None:
        nonlocal fails
        ok = got == want
        fails += not ok
        print("%s %s: got %r want %r" % ("ok  " if ok else "FAIL", label, got, want))

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        card = tmp_path / "synth.img"
        g = _synthetic_card(card)
        files = g["files"]
        mmain_c, mmain_sz, mmain_byte = files["MMAIN001.DAT"]
        drstr_c, drstr_sz, drstr_byte = files["DRSTR001.DAT"]
        cmp_c, cmp_sz, cmp_byte = files["CMP.LST"]
        ds = g["data_start"]

        extents, meta = build_extents(str(card))
        check("fat file count", meta["files"], 3)
        check("fat cluster bytes", meta["cluster_bytes"], 512)
        check("mmain first card byte", mmain_byte, 5632)
        check("cmp first card byte", cmp_byte, 7168)

        # Positive control: known reads map to known file/offset.
        log = "\n".join([
            "sdcard_read_block addr 0x%x size 0x40" % mmain_byte,
            "sdcard_read_block addr 0x%x size 0x200" % drstr_byte,
            "sdcard_read_block addr 0x%x size 0x200" % (ds + (drstr_c + 1 - 2) * 512),
            "sdcard_read_block addr 0x%x size 0x13" % cmp_byte,
        ])
        raw, grammar = parse_log(log)
        check("grammar", grammar, "qemu-trace:sdcard_read_block")
        events = attribute(raw, extents)
        cov = coverage(events)
        check("files seen", [r["path"] for r in cov],
              ["MMAIN001.DAT", "DRSTR001.DAT", "CMP.LST"])
        check("mmain range", cov[0]["ranges"], [[0, 0x40]])
        # DRSTR is 200 B over two clusters: logical 0..200, plus cluster RA.
        dr = next(r for r in cov if r["path"] == "DRSTR001.DAT")
        check("drstr read bytes", dr["read_bytes"], 200)
        check("drstr readahead", dr["readahead_bytes"], 512 + 512 - 200)
        check("cmp range", next(r for r in cov if r["path"] == "CMP.LST")["ranges"],
              [[0, 0x13]])

        # Negative control 1: a bogus block overlaps no file extent -> unmapped,
        # never a false attribution.
        bogus = 0x2222
        raw_b, _ = parse_log("sdcard_read_block addr 0x%x size 0x10\n" % bogus)
        ev_b = attribute(raw_b, extents)
        check("bogus mapped", ev_b[0].ranges, [])
        check("bogus unmapped", ev_b[0].unmapped, [(bogus, bogus + 0x10)])

        # Negative control 2: a corrupted FAT (bogus first cluster) makes the
        # file unreachable; its block reads must be unmapped, not attributed.
        bad = bytearray(card.read_bytes())
        bad_fat = g["part_off"] + 512
        struct.pack_into("<I", bad, bad_fat + 4 * mmain_c, 0x0FFFFFFF)  # isolate
        # repoint MMAIN dir entry cluster to 99 (out of the small FAT)
        # find its short entry
        root_off = g["data_start"]
        for off in range(root_off, root_off + 512, 32):
            if bad[off:off + 11] == b"MMAIN001DAT":
                struct.pack_into("<H", bad, off + 26, 99)
                break
        bad_card = tmp_path / "bad.img"
        bad_card.write_bytes(bad)
        ext_bad, _ = build_extents(str(bad_card))
        raw_bad, _ = parse_log("sdcard_read_block addr 0x%x size 0x40\n" % mmain_byte)
        ev_bad = attribute(raw_bad, ext_bad)
        check("corrupt FAT ranges", ev_bad[0].ranges, [])
        check("corrupt FAT unmapped", bool(ev_bad[0].unmapped), True)

        # DMAC grammar: a CMD18 read of the MMAIN cluster at LBA mmain_byte/512.
        dlog = "\n".join([
            "ze0-sdhi0: wr16 +0x04 = 0x0000",
            "ze0-sdhi0: wr16 +0x06 = 0x%x" % ((mmain_byte // 512) >> 16),
            "ze0-sdhi0: wr16 +0x04 = 0x%x" % ((mmain_byte // 512) & 0xFFFF),
            "ze0-sdhi0: wr16 +0x00 = 0x1812",
            "ze0-hpbdmac: ch8 read 64 bytes, DDAR 0xa99c1000, left 0, crc32 0x0, head 00",
        ])
        raw_d, grammar_d = parse_log(dlog)
        check("dmac grammar", grammar_d, "dmac:ze0_sdhost.decode_dma")
        check("dmac event", [(a, b) for a, b, _ in raw_d], [(mmain_byte, 64)])
        ev_d = attribute(raw_d, extents)
        check("dmac mapped", ev_d[0].ranges[0][0], "MMAIN001.DAT")

    print("selftest: %s (%d failure(s))" % ("PASS" if not fails else "FAIL", fails))
    return 1 if fails else 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("rundir", nargs="?", help="run directory or a single log file")
    ap.add_argument("--card", help="card image (raw .img) to read the FAT from")
    ap.add_argument("--log", help="explicit trace log file (overrides RUNDIR scan)")
    ap.add_argument("--json", action="store_true", help="emit the full JSON report")
    ap.add_argument("--output", help="also write the JSON report to this file")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.rundir or not args.card:
        ap.error("RUNDIR and --card are required (or use --selftest)")
    if not os.path.exists(args.card):
        ap.error("no such card image: %s" % args.card)
    rundir = Path(args.rundir)
    if not rundir.exists():
        ap.error("no such run directory/file: %s" % args.rundir)
    text = gather_logs(rundir, args.log)
    raw, grammar = parse_log(text)
    extents, meta = build_extents(args.card)
    events = attribute(raw, extents)
    report = make_report(events, extents, meta, grammar, str(rundir))
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)
    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
