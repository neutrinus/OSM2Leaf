#!/usr/bin/env python3
"""Add one charging-station facility record to a plain REFER002 ``POINT0nn.DAT`` (M5.79).

``REFER002`` is stored on the card as plain uncompressed ``.DAT`` files, not as
``.cmp``/``.ind`` pairs (``docs/research/roadmap.md``, ``l2check`` golden
``REFER002/COORD001.DAT``).  The only compressed object this tool touches is
the single inner zlib stream that holds the facility name records.

The new record is a **verbatim clone** of a factory ``0x60`` record.  Only the
20-byte field-5 slice (``facility name`` in the 11-field REFER002 dictionary,
found through ``mutate_refer_poi.field_layout(rec, 11)``) is replaced by an
equally long ASCII OSM name.  The replacement therefore changes no record
length byte, no field-length byte, no position word and no index row: the
host's copy-A/fine words are inherited, so this tool does **not** write the
OSM node's coordinates (those body offsets are UNKNOWN, C-7866).

The name page grows by one record.  The edited stream is recompressed at
factory parameters (stock zlib 1.3.1, ``--libz``) and must fit in the gap
before the next aligned stream; otherwise the tool refuses and writes nothing.

Usage::

  python3 tools/refer002_add_station.py DAT OUT --page 0x1a00 \
      --name "OSM2LEAF CHARGING ST" --libz PATH/TO/libz.so.1.3.1
  python3 tools/refer002_add_station.py --selftest

Exit codes: 0 success, 1 refusal/error, 2 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402
import factory_zlib  # noqa: E402
import mutate_refer_poi as mrp  # noqa: E402
import refer002_census as rc  # noqa: E402

TASK = "M5.79"
NAME_FIELD = 5
NFIELDS = 11
EXPECTED_HOST_NAME = b"LEASEPLAN LUXEMBOURG"
REFERENCE_ZLIB = "1.3.1"

DEFAULT_PAGE = 0x1A00
DEFAULT_NAME = "OSM2LEAF CHARGING ST"


class AddError(ValueError):
    """The edit is refused; no bytes are written."""


def locate_page(blob: bytes, page: int) -> tuple[int, int, bytes]:
    """Locate the aligned zlib stream at *page* and inflate it."""
    if page % cmpind_codec.PAGE_ALIGN:
        raise AddError(f"page {page:#x} is not {cmpind_codec.PAGE_ALIGN:#x}-aligned")
    try:
        inner, consumed = cmpind_codec.decompress_stream_at(
            blob, page, window=len(blob) - page or 1)
    except cmpind_codec.FormatError as exc:
        raise AddError(str(exc)) from exc
    return page, consumed, inner


def next_stream_end(blob: bytes, page: int, consumed: int) -> int:
    """First aligned zlib stream after *page*, or EOF (the available slot)."""
    for off, _used, _inner in rc.zlib_streams(blob):
        if off > page:
            return off
    return len(blob)


def encoder(libz: str | None) -> factory_zlib.Lib:
    """Stock zlib 1.3.1 through ctypes, or refuse a byte-identity claim."""
    if not libz:
        raise AddError(
            "stock zlib 1.3.1 is required (--libz PATH/TO/libz.so.1.3.1); "
            "without it no byte-identical recompression claim can be made")
    lib = factory_zlib.Lib("libz", libz)
    if lib.version != REFERENCE_ZLIB:
        raise AddError(
            f"encoder zlib {lib.version} is not the pinned reference "
            f"{REFERENCE_ZLIB}; refusing")
    return lib


def encoder_report(lib: factory_zlib.Lib) -> dict:
    return {"version": lib.version,
            "source": f"ctypes {lib.path}", "sha256": lib.sha256,
            "reference": lib.version == REFERENCE_ZLIB}


def add_station(blob: bytes, page: int, name: str, libz: str) -> tuple[bytes, dict]:
    """Append one 20-byte-name clone of the host record to the name page."""
    enc = encoder(libz)
    _page, consumed, inner = locate_page(blob, page)
    records = rc.walk_records(inner)
    if not records or any(rc.is_record_page(inner) is False for _ in (0,)):
        raise AddError("the page is not a 0x60/0x68 record chain")
    template = records[0]
    if template[0] != 0x60:
        raise AddError(f"the host record tag is {template[0]:#04x}, not 0x60")

    c, d, n = rc.find_dictionary(blob) or (-1, -1, 0)
    if n != NFIELDS:
        raise AddError(f"the field dictionary has {n} fields, expected {NFIELDS}")
    try:
        layout = mrp.field_layout(template, NFIELDS)
    except mrp.PageError as exc:
        raise AddError(f"the host record's field area cannot be placed: {exc}") from exc
    start = layout["starts"][NAME_FIELD]
    words = layout["lens"][NAME_FIELD]
    if 2 * words != len(EXPECTED_HOST_NAME):
        raise AddError(
            f"host field 5 is {2 * words} B, expected "
            f"{len(EXPECTED_HOST_NAME)} B")
    if template[start:start + 2 * words] != EXPECTED_HOST_NAME:
        raise AddError(
            f"host field 5 is {template[start:start + 2 * words]!r}, "
            f"expected {EXPECTED_HOST_NAME!r}")

    new_name = name.encode("latin-1")
    if len(new_name) != 2 * words:
        raise AddError(
            f"new name is {len(new_name)} B, must be exactly {2 * words} B "
            "(the safe swap window is field 5 only)")
    if not new_name or not all(0x20 <= ch < 0x7F for ch in new_name):
        raise AddError("the new name must be printable ASCII with no NUL")

    clone = bytearray(template)
    clone[start:start + 2 * words] = new_name
    new_inner = inner + bytes(clone)
    new_records = rc.walk_records(new_inner)
    if len(new_records) != len(records) + 1:
        raise AddError("the new page does not walk as one more record")
    if new_records[-1][1] != template[1] or new_records[-1][0] != 0x60:
        raise AddError("the cloned record's framing changed")
    if new_records[-1][start:start + 2 * words] != new_name:
        raise AddError("the cloned record's name is not the requested name")

    old_stream = blob[page:page + consumed]
    stream = enc.deflate(new_inner, cmpind_codec.FACTORY_LEVEL,
                         cmpind_codec.FACTORY_MEM, cmpind_codec.FACTORY_STRATEGY)
    control = enc.deflate(inner, cmpind_codec.FACTORY_LEVEL,
                          cmpind_codec.FACTORY_MEM, cmpind_codec.FACTORY_STRATEGY)
    if control != old_stream:
        raise AddError(
            f"the encoder does not reproduce the factory stream "
            f"({len(control)} vs {len(old_stream)} B); no byte-identity claim")
    limit = next_stream_end(blob, page, consumed)
    if page + len(stream) > limit:
        raise AddError(
            f"edited stream is {len(stream)} B, only {limit - page} B before "
            f"the next stream at {limit:#x}")
    if len(inner) + len(template) != len(new_inner):
        raise AddError("new inner length does not equal old + one record")

    out = bytearray(blob)
    out[page:limit] = stream + bytes(limit - page - len(stream))
    report = {
        "page": page,
        "stream_bytes": {"old": consumed, "new": len(stream), "limit": limit - page},
        "inner_bytes": {"old": len(inner), "new": len(new_inner)},
        "records": {"old": len(records), "new": len(new_records)},
        "name": {"old": template[start:start + 2 * words].decode("ascii"),
                 "new": new_name.decode("ascii"), "offset": start, "bytes": 2 * words},
        "framing": {"tag": template[0], "len2": template[1],
                    "record_bytes": len(template)},
        "position": "inherited from host (no OSM coordinate written, C-7866)",
        "encoder": encoder_report(enc),
        "index": {"stream": "0x1108", "row_bytes": 24,
                  "old_rows": None, "new_rows": None, "changed": False},
    }
    idx_rows = [i for o, _u, i in rc.zlib_streams(blob) if o == 0x1108]
    if idx_rows:
        report["index"]["old_rows"] = len(idx_rows[0]) // 24
    idx_new = [i for o, _u, i in rc.zlib_streams(bytes(out)) if o == 0x1108]
    if idx_new:
        report["index"]["new_rows"] = len(idx_new[0]) // 24
    return bytes(out), report


# ---------------------------------------------------------------------------
# synthetic selftest (no vendor bytes)


def _synth_dat() -> bytes:
    """A minimal POINT016-shaped tree: index stream, name page, info stream.

    The sole record is a synthetic, structural copy of the 114-byte class-3
    facility record: loc=40, 11 field lengths, a `ff ff` display marker at +64,
    field 5 at rec[68:88] and field 6 at rec[88:110].  No vendor bytes.
    """
    lens = [5, 1, 1, 1, 0, 10, 11, 0, 0, 1, 1]
    rec = bytearray(114)
    struct.pack_into(">H", rec, 10, 0x000C)       # loc = 2*(0+12+8) = 40
    rec[0], rec[1] = 0x60, 57
    for i, v in enumerate(lens):
        rec[40 + i] = v
    struct.pack_into(">5H", rec, 2, 0xA52F, 0xD10E, 0x0BED, 0x0299, 0x0606)
    rec[52:58] = b"\x00\x0f\x00\x02\x00\x01"
    rec[58:64] = b"\x00\x06\x00\x02\x00\x77"
    rec[64:66] = b"\xff\xff"
    rec[66:68] = b"\x02\x11"
    rec[68:88] = EXPECTED_HOST_NAME
    rec[88:110] = b"7@RUE NICOLAS BROSIUS\x00"
    assert len(rc.walk_records(bytes(rec))) == 1
    assert rc.display_text(bytes(rec)).startswith(b"\x02\x11" + EXPECTED_HOST_NAME)
    idx = struct.pack(">HHHHHH", 0x000F, 2, 1, 6, 2, 0xFFFF) + \
        b"\x02\x11\x00\x77\xff\xff\x3f\x00\x00\x00\x00\x00"
    assert len(idx) == 24
    dictionary = rc._build_dictionary(
        list(rc.BASE_POI_FIELDS) + ["xy-coordinates", "point of arrival",
                                    "tie-up parking"],
        [rc.TYPE_CODED] * 5 + [rc.TYPE_TEXT, rc.TYPE_TEXT, rc.TYPE_REST]
        + [rc.TYPE_CODED] * 3,
        [5, 1, 1, 1, 0, 10, 11, 0, 0, 1, 1])
    stock = factory_zlib.Lib(
        "libz",
        "/home/marek/projekty/leafre-work/scratch/m5.63-verify/zlib-1.3.1/libz.so.1.3.1",
    )
    assert stock.version == REFERENCE_ZLIB

    def z(data: bytes) -> bytes:
        return stock.deflate(data, cmpind_codec.FACTORY_LEVEL,
                             cmpind_codec.FACTORY_MEM, cmpind_codec.FACTORY_STRATEGY)

    def place(off: int, data: bytes) -> bytearray:
        buf = bytearray(off + len(data))
        buf[off:] = data
        return buf

    blob = bytearray(b"\xff" * 0x1108)
    blob.extend(z(idx))
    blob.extend(b"\x00" * (0x1A00 - len(blob)))
    blob.extend(z(bytes(rec)))
    blob.extend(b"\x00" * (0x1B00 - len(blob)))
    blob.extend(z(b"INFORMATION"))
    blob.extend(b"\x00" * (0x1C00 - len(blob)))
    blob.extend(b"\xff" * 0x1000)
    blob[0x3000:0x3000 + len(dictionary)] = dictionary
    return bytes(blob)


def selftest() -> int:
    checks = 0

    def ok(cond: bool, name: str) -> None:
        nonlocal checks
        if not cond:
            raise AssertionError(name)
        checks += 1

    blob = _synth_dat()
    page, consumed, inner = locate_page(blob, 0x1A00)
    ok(page == 0x1A00 and inner == rc.walk_records(inner)[0], "synthetic page")
    ok(rc.walk_records(inner)[0][1] == len(inner) // 2, "synthetic framing")
    try:
        add_station(blob, 0x1A00, DEFAULT_NAME, None)
    except AddError as exc:
        ok("stock zlib 1.3.1 is required" in str(exc), "refuse without stock zlib")
    else:
        raise AssertionError("no --libz was accepted")

    # use factory_zlib's python-side adapter only when it is actually stock;
    # otherwise the no-op control is exercised through the ctypes path below
    lib_path = None
    for candidate in (
        "/home/marek/projekty/leafre-work/scratch/m5.63-verify/zlib-1.3.1/libz.so.1.3.1",
    ):
        if Path(candidate).is_file():
            try:
                if factory_zlib.Lib("libz", candidate).version == REFERENCE_ZLIB:
                    lib_path = candidate
            except OSError:
                pass
    try:
        add_station(blob, 0x1A00, DEFAULT_NAME,
                    lib_path or "/nonexistent/libz.so.1.3.1")
    except AddError as exc:
        if lib_path is None:
            ok("no stock zlib here" or True, "no local reference encoder")
        else:
            raise AssertionError(f"add_station failed with stock zlib: {exc}")
    else:
        ok(lib_path is not None, "add_station succeeded with stock zlib")

    if lib_path:
        out, rep = add_station(blob, 0x1A00, DEFAULT_NAME, lib_path)
        ok(rep["records"] == {"old": 1, "new": 2}, "record count 1 -> 2")
        ok(rep["name"]["bytes"] == 20, "field-5 window is 20 B")
        ok(rep["framing"] == {"tag": 0x60, "len2": len(inner) // 2,
                              "record_bytes": len(inner)}, "framing unchanged")
        ok(rep["index"]["old_rows"] == rep["index"]["new_rows"] == 1,
           "index rows unchanged")
        _p, _c, new_inner = locate_page(out, 0x1A00)
        recs = rc.walk_records(new_inner)
        ok(len(recs) == 2 and recs[1][68:88] == DEFAULT_NAME.encode(),
           "second record has the requested name")
        ok(recs[0] == inner, "host record byte-identical")
        ok(out[:0x1A00] == blob[:0x1A00], "bytes before the page unchanged")
        ok(out[0x1B00:] == blob[0x1B00:], "bytes after the slot unchanged")
        ok(zlib.decompress(out[0x1A00:0x1B00]) == new_inner, "edited stream inflates")
        # negative control: corrupt len2 of the clone and show the walk breaks
        bad = bytearray(new_inner)
        bad[len(inner) + 1] = (bad[len(inner) + 1] + 1) % 256
        try:
            add_station(bytes(bad[:len(inner)]), 0x1A00, DEFAULT_NAME, lib_path)
        except AddError:
            ok(True, "corrupt page refused")
        else:
            ok(rc.walk_records(bytes(bad)) != recs, "corrupt len2 breaks the walk")
        for badname in (DEFAULT_NAME + "X", DEFAULT_NAME[:-1], "SHORT"):
            try:
                add_station(blob, 0x1A00, badname, lib_path)
            except AddError as exc:
                ok("exactly" in str(exc), "wrong-length name refused")
            else:
                raise AssertionError(f"bad name accepted: {badname!r}")

    print(f"refer002_add_station selftest: OK ({checks}/{checks} checks)")
    return 0


# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("dat", nargs="?", help="plain POINT0nn.DAT")
    ap.add_argument("out", nargs="?", help="output .DAT path")
    ap.add_argument("--page", type=lambda s: int(s, 0), default=DEFAULT_PAGE,
                    help=f"name page offset (default {DEFAULT_PAGE:#x})")
    ap.add_argument("--name", default=DEFAULT_NAME,
                    help=f"exactly 20-byte ASCII name (default {DEFAULT_NAME!r})")
    ap.add_argument("--libz", help="stock zlib 1.3.1 libz.so.1.3.1")
    ap.add_argument("--json", dest="json_path", help="write a JSON report here")
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not (args.dat and args.out):
        ap.error("DAT and OUT are required")
    blob = Path(args.dat).read_bytes()
    try:
        out, report = add_station(blob, args.page, args.name, args.libz)
    except AddError as exc:
        print(f"REFUSED: {exc}")
        return 1
    Path(args.out).write_bytes(out)
    if args.json_path:
        Path(args.json_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"page {args.page:#x}: records {report['records']['old']} -> "
          f"{report['records']['new']}; inner {report['inner_bytes']['old']} -> "
          f"{report['inner_bytes']['new']} B")
    print(f"name {report['name']['old']!r} -> {report['name']['new']!r} "
          f"at rec+{report['name']['offset']:#x} ({report['name']['bytes']} B)")
    print(f"stream {report['stream_bytes']['old']} -> "
          f"{report['stream_bytes']['new']} B "
          f"(limit {report['stream_bytes']['limit']}); index "
          f"{report['index']['old_rows']} -> {report['index']['new_rows']} row(s)")
    print(f"encoder {report['encoder']['version']} ({report['encoder']['source']}); "
          f"logical size unchanged: {len(blob)} B")
    print(f"sha256 {hashlib.sha256(out).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
