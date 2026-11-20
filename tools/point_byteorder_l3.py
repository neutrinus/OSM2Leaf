#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""point_byteorder_l3.py - follow one factory POINT page from the card to the walker (M9.26).

M3.11b showed that the map-file layer swaps every byte pair of a read when the
request word +20 is 0, and that every client read leaves it at 0 (C-4641,
C-4672, C-5810-C-5816).  A POINT page is a zlib stream inside the `.DAT`, so
a swapped stream cannot be inflated as is.  The page loader `fn 0x003fd690`
(EU2011) calls the byte-pair leaf `0x003f6968(buf, nbytes)` twice: on the
compressed buffer right before the inflate wrapper `0x00542100`, and on the
inflated page right after it.  This tool runs that path step by step on the
real card and image:

  1. the layer (`vcard_l3.py` session, firmware code) reads the page's
     compressed bytes with word +20 = 0 and with +20 = 1;
  2. the leaf `0x003f6968` (PySh4, Navi.exe text) runs on the +20 = 0 bytes;
     the result must be the file-order stream (`78 9c ...`), equal to the
     host decode of the `.cmp` pair;
  3. the stream is inflated (host zlib: `0x00542100` is the same zlib the
     chunk engine runs, byte-identical to the host in M9.11/M9.11b);
  4. the leaf runs again on the inflated page; the result must be
     `point_walk_l3.swap16(page)`, the native form;
  5. the walker `fn 0x003f5194` runs on that buffer and on the file-order
     page: the native buffer must give `parse_page`'s record offsets, the
     file-order page must not (control).

Controls: the +20 = 1 read must equal the file-order bytes (the layer did
not swap), inflating the +20 = 0 bytes without the leaf must fail, and the
leaf applied twice must be the identity.

No vendor byte is stored: the tool reads the image and card it is given.

Usage:
  point_byteorder_l3.py run IMG256 --card-image CARD [--page 0x6e06d0] [--json OUT]
  point_byteorder_l3.py --selftest

Exit codes: 0 every step and control holds, 1 one does not, 3 BLOCKED.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import point_walk_l3 as pw  # noqa: E402

FILE = "REFER001/POINT010.DAT"
EU_PAGE = 0x6E06D0          # EU2011 POINT010 page of M9.28/M9.38 (97,158 B inflated)
LEAF_SWAP = 0x003F6968      # EU2011 byte-pair leaf (pdata GAP after fn 0x003f6908)
BUF_VA = 0x20000000
STACK_VA = 0x30000000


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def run_leaf(text_va: int, text: bytes, data: bytes) -> bytes:
    """Run the firmware leaf `0x003f6968(buf, nbytes)` on a copy of *data*."""
    eng = pw.PySh4(endian="little")
    eng.map("text", text_va, text, "rx")
    eng.map("buf", BUF_VA, bytearray(data) + bytearray(0x40), "rw")
    eng.map("stack", STACK_VA, bytearray(0x1000), "rw")
    eng.set_regs(r15=STACK_VA + 0xF00)
    pw.engine_call(eng, LEAF_SWAP, [BUF_VA, len(data)], "eu2011")
    return bytes(eng.read_mem(BUF_VA, len(data)))


def inflate(stream: bytes) -> tuple[bytes | None, str]:
    try:
        d = zlib.decompressobj()
        out = d.decompress(stream)
        if not d.eof:
            return None, "stream not finished"
        return out, ""
    except zlib.error as exc:
        return None, str(exc)


def walker_offsets(text_va, text, page_native: bytes, ns) -> list:
    return [pw.run_nth(text_va, text, page_native, n) for n in ns]


def check(steps: dict) -> list[tuple[str, bool]]:
    """The pass/fail lines from the collected values (pure, for --selftest)."""
    f = steps
    return [
        ("layer +20=1 equals the file-order stream", f["read_plain"] == f["file_stream"]),
        ("layer +20=0 equals swap16(file-order stream)", f["read_swapped"] == pw.swap16(f["file_stream"])),
        ("+20=0 stream does not inflate as read", f["inflate_swapped_error"] != ""),
        ("leaf(+20=0 bytes) equals the file-order stream", f["leaf_stream"] == f["file_stream"]),
        ("leaf(leaf(x)) is x", f["leaf_twice"] == f["read_swapped"]),
        ("inflated page is file order (first header word big-endian)", f["page_ok"]),
        ("leaf(inflated page) equals swap16(page)", f["leaf_page"] == pw.swap16(f["page"])),
        ("walker on the leaf output gives parse_page offsets", f["walk_native"] == f["want"]),
        ("walker on the file-order page does not (control)", f["walk_file"] != f["want"]),
    ]


def cmd_run(args) -> int:
    import mutate_refer_poi as mrp
    import vcard_l3

    image = pw.load_image(args.image)
    text_va, text = pw.navi_text(image, 0x200200)
    card = vcard_l3.make_card(args.card_root, args.card_image)
    out, s = vcard_l3.boot_report(args.image, card)
    if out["verdict"] != "ACCEPT" or s is None:
        print("BLOCKED: boot %s %s" % (out["verdict"], out.get("blocked", "")))
        return 3
    exp = vcard_l3.Expected(card)
    f = s.find_file(FILE)
    head = exp.read(f["path"], args.page, min(0x80000, f["size"] - args.page))
    d = zlib.decompressobj()
    page = d.decompress(head)
    if not d.eof:
        print("BLOCKED: page at %#x is not a complete zlib stream in the first 512 KiB" % args.page)
        return 3
    clen = len(head) - len(d.unused_data)
    clen_even = clen + (clen & 1)
    file_stream = exp.read(f["path"], args.page, clen_even)
    st_plain, read_plain = s.read(FILE, args.page, clen_even, swap=False)
    st_swap, read_swapped = s.read(FILE, args.page, clen_even, swap=True)
    if st_plain or st_swap:
        print("BLOCKED: layer status %#x / %#x" % (st_plain, st_swap))
        return 3
    _, err = inflate(read_swapped)
    leaf_stream = run_leaf(text_va, text, read_swapped)
    leaf_twice = run_leaf(text_va, text, leaf_stream)
    page2, err2 = inflate(leaf_stream)
    recs = mrp.parse_page(page)
    count = len(recs)
    ns = sorted({0, 1, 2, 3, 10, count // 2, count - 1})
    want = [recs[n]["offset"] for n in ns]
    leaf_page = run_leaf(text_va, text, page)
    steps = dict(
        file_stream=file_stream, read_plain=read_plain, read_swapped=read_swapped,
        inflate_swapped_error=err, leaf_stream=leaf_stream, leaf_twice=leaf_twice,
        page=page, page_ok=page2 == page and err2 == "" and page[0] < 0x80,
        leaf_page=leaf_page, want=want,
        walk_native=walker_offsets(text_va, text, leaf_page, ns),
        walk_file=walker_offsets(text_va, text, page, ns[:3]) + [None] * (len(ns) - 3),
    )
    print("%s page %#x: compressed %d B (read %d), inflated %d B, %d records" % (
        FILE, args.page, clen, clen_even, len(page), count))
    print("  file-order stream     sha256 %s  first %s" % (sha(file_stream), file_stream[:4].hex()))
    print("  layer +20=1           sha256 %s  first %s" % (sha(read_plain), read_plain[:4].hex()))
    print("  layer +20=0           sha256 %s  first %s  inflate: %s" % (
        sha(read_swapped), read_swapped[:4].hex(), err or "OK"))
    print("  leaf(+20=0)           sha256 %s  first %s" % (sha(leaf_stream), leaf_stream[:4].hex()))
    print("  inflated page         sha256 %s  first %s" % (sha(page), page[:4].hex()))
    print("  leaf(page)            sha256 %s  first %s" % (sha(leaf_page), leaf_page[:4].hex()))
    print("  walker n=%s" % ns)
    print("    on leaf(page)       %s" % [None if x is None else hex(x) for x in steps["walk_native"]])
    print("    on file-order page  %s" % [None if x is None else hex(x) for x in steps["walk_file"][:3]])
    print("    parse_page          %s" % [hex(x) for x in want])
    lines = check(steps)
    for text_, ok in lines:
        print("  %-62s %s" % (text_, "OK" if ok else "FAIL"))
    bad = sum(1 for _, ok in lines if not ok)
    print("RESULT: %s (%d/%d)" % ("PASS" if not bad else "FAIL", len(lines) - bad, len(lines)))
    if args.json:
        Path(args.json).write_text(json.dumps(dict(
            page=hex(args.page), compressed=clen, inflated=len(page), records=count,
            sha256={k: sha(v) for k, v in steps.items() if isinstance(v, bytes)},
            walker=dict(n=ns, native=steps["walk_native"], file=steps["walk_file"][:3], want=want),
            checks=[dict(check=t, ok=o) for t, o in lines]), indent=1) + "\n")
    return 0 if not bad else 1


def selftest() -> int:
    # pure checks on a synthetic page; the leaf itself is exercised on the image in `run`
    page = bytes.fromhex("6004") + b"\x00\x11" * 3 + bytes.fromhex("6002") + b"\x22\x33"
    stream = zlib.compress(page, 6)
    stream += b"\x00" * (len(stream) & 1)
    sw = pw.swap16(stream)
    _, err = inflate(sw)
    base = dict(file_stream=stream, read_plain=stream, read_swapped=sw, inflate_swapped_error=err,
                leaf_stream=pw.swap16(sw), leaf_twice=sw, page=page, page_ok=True,
                leaf_page=pw.swap16(page), want=[0, 8], walk_native=[0, 8], walk_file=[0, 0x400])
    assert all(ok for _, ok in check(base)), check(base)
    n = 1
    for key, bad in (("read_plain", sw), ("read_swapped", stream), ("inflate_swapped_error", ""),
                     ("leaf_stream", sw), ("leaf_twice", stream), ("page_ok", False),
                     ("leaf_page", page), ("walk_native", [0, 2]), ("walk_file", [0, 8])):
        broken = dict(base, **{key: bad})
        assert not all(ok for _, ok in check(broken)), key
        n += 1
    assert inflate(stream)[0] == page and inflate(sw)[0] is None
    n += 1
    print("selftest OK (%d checks)" % n)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("run")
    p.add_argument("image")
    p.add_argument("--card-image")
    p.add_argument("--card-root")
    p.add_argument("--page", type=lambda x: int(x, 0), default=EU_PAGE)
    p.add_argument("--json")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
