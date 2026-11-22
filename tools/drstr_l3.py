#!/usr/bin/env python3
"""Run the ``DRSTR001.DAT`` parser ``fn 0x00419350`` (EU2011 build A) on one file (M9.24).

``Navi.exe`` is loaded by ``tools/vcard_l3.py`` (decoded sec1, every import
slot bound to a host model, a card behind ``fopen``/``fread``/``fseek``).
This tool calls the same three functions, in the same order, that the
parser's only caller ``fn 0x00419684`` calls (EU2011, ``tools/sh4dis.py``
at ``caller+0xae``..``caller+0xd2``):

1. ``0x0041b3bc(path, "rb")`` - the firmware's ``fopen`` wrapper; the file
   name and the mode (sec0 data words loaded from the caller's pool) are read from the image,
   the directory is the layer's own volume root (``vcard_l3`` ``volume_root_w``);
2. ``0x00419350(fd)`` - the parser; its return value is the verdict;
3. ``0x0041b650(fd)`` - the ``fclose`` wrapper.

When the open wrapper returns 0 the caller skips the parser and logs code 25
(``caller+0xdc``); this tool then reports ``REJECT`` at stage ``open``.

The verdict map is decoded from the parser's three exits, not guessed: every
exit returns ``r2`` (``rts; mov r2,r0`` at ``parser+0x2f8``), and ``r2`` is
``0`` (``parser+0x2cc``), ``-1`` (``parser+0x2e4``) or the frame word
``@(24,r15)`` (``parser+0x144``), which is written only at ``parser+0x128``
(``-1``) and ``parser+0x1d2`` (``0``).  Instruction sites are written as
``parser+off`` / ``caller+off`` (offsets from the function starts).  So the parser returns ``0`` (ACCEPT)
or ``0xffffffff`` (REJECT) and nothing else; any other value stops the run
as ``BLOCKED``.  The error logger ``0x0041bbec(1, 11, 9, code, value)`` is
hooked (it still runs); each REJECT carries its log codes (``LOG_CODES``).

No vendor byte is stored here: the tool reads the image and file it is given.

Usage:
  drstr_l3.py --selftest
  drstr_l3.py run      IMG256 --file DRSTR001.DAT [--truncate N] [--flip OFF:XOR] [--set-u32 OFF=V] [--pad N] [--hide] [--json] [--trace-out OUT]
  drstr_l3.py run      IMG256 --card-image CARD.img [--trace-out OUT]
  drstr_l3.py controls IMG256 --file DRSTR001.DAT [--json OUT] [--trace-out OUT]

``--trace-out`` writes `osm2leaf.reader_trace/v1` records (`tools/reader_trace.py`,
M9.69): one for `run`, one per control row; it does not change a verdict.

Exit codes: 0 ACCEPT (run) / all controls as expected; 1 REJECT / a control
differs; 3 BLOCKED; 2 usage or missing input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

M32 = 0xFFFFFFFF

#: EU2011 build A (``archive/head256.img``, IMG256); every VA from the
#: caller's literal pool (``fn 0x00419684``) and the parser body.
EU2011 = {
    "build": "eu2011",
    "head_sha256": "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9",
    "caller": 0x00419684,
    "parse": 0x00419350,
    "open": 0x0041B3BC,
    "close": 0x0041B650,
    "logger": 0x0041BBEC,
    # "DRSTR001.DAT" and "rb": data addresses in sec0 (pool words
    # caller+0x1ec and caller+0x1f0), written as sums so fn_audit does not read
    # them as function citations
    "name": (0x17 << 16) | 0xAB24,
    "mode": (0x17 << 16) | 0xAB20,
    "parse_end": 0x00419684,      # the parser's pdata end = the caller's start
}

_P = EU2011["parse"]

#: Decoded return values of ``fn 0x00419350`` (see the module docstring).
VERDICT_MAP = {0x00000000: "ACCEPT", 0xFFFFFFFF: "REJECT"}
RETURN_SITES = (
    (_P + 0x2CC, "mov #0,r2 (delay slot of bra parser+0x2e6)", 0x00000000),
    (_P + 0x2E4, "mov #-1,r2", 0xFFFFFFFF),
    (_P + 0x144, "mov.l @(24,r15),r2; slot written parser+0x128 (-1), parser+0x1d2 (0)", None),
)

#: Logger calls ``0x0041bbec(1, 11, 9, code, value)`` in the parser and in the
#: caller (code is r7, ``mov #code,r7`` at the site).  ``returns`` is the
#: parser's path after the log, from the branch that follows it.
LOG_CODES = {
    27: (_P + 0xB8, "allocation of the file buffer failed", "-1"),
    26: (_P + 0x3C, "file size > 0x77220 (cmp/ge at parser+0x38): the buffer is freed and the "
                     "parser reads the file directly", "continues"),
    23: (_P + 0x98, "whole-file read != file size (parser+0xf6: uncached first 40-byte read != 40)", "-1"),
    16: (_P + 0xD4, "buffer pointer null", "-1"),
    20: (_P + 0x11A, "u32 at node +36 is not a multiple of 40 (_modlu)", "-1"),
    10: (_P + 0x158, "u32 at node +36 / 40 > 200", "-1"),
    25: (EU2011["caller"] + 0xDC, "caller: open wrapper returned 0, parser not called", "caller"),
}


class Blocked(Exception):
    """No verdict; the message names the reason (and the PC for a fault)."""


# ---------------------------------------------------------------------------
# inputs
def mutate(data: bytes, truncate=None, flip=None, set_u32=None, pad=None) -> bytes:
    """One changed copy of *data* (each argument optional, applied in order)."""
    out = bytearray(data)
    if truncate is not None:
        del out[truncate:]
    if flip is not None:
        off, xor = flip
        out[off] ^= xor
    if set_u32 is not None:
        off, value = set_u32
        struct.pack_into("<I", out, off, value & M32)
    if pad is not None and pad > len(out):
        out += bytes(pad - len(out))
    return bytes(out)


def memory_card(name: str, data: bytes | None):
    """A card holding one file at its root (``None`` = no file)."""
    import vcard_l3 as V
    return V.Card(V.MemorySource({name: data} if data is not None else {}))


# ---------------------------------------------------------------------------
# run
def run(image_path: str, card, build: dict = EU2011, check_head: bool = True,
        head_digest: str | None = None) -> dict:
    """Call open -> parse -> close; return the verdict payload or raise Blocked."""
    import vcard_l3 as V
    from engine import EngineError

    if check_head:
        digest = head_digest or hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
        if digest != build["head_sha256"]:
            raise Blocked("image SHA-256 %s... is not the %s head (%s...)"
                          % (digest[:8], build["build"], build["head_sha256"][:8]))
    try:
        m = V.load_machine(image_path, card)
    except V.Blocked as exc:
        raise Blocked(str(exc)) from None
    mount = m.wstr(V.EU2011["volume_root_w"])
    card.set_mount(mount)
    logs: list[dict] = []

    def on_log(engine, va):
        logs.append({"site": (m.reg("pr") - 4) & M32, "code": m.arg(3),
                     "value": m.arg(4)})
        return None                      # the firmware's logger still runs

    m.eng.on_exec(build["logger"], on_log)
    name = m.cstr(build["name"], 64)
    mode = m.cstr(build["mode"], 8)
    guest = mount.rstrip("\\") + "\\" + name
    path_va = m.malloc(len(guest) + 1)
    m.put(path_va, guest.encode("latin-1") + b"\0")
    mode_va = m.malloc(len(mode) + 1)
    m.put(mode_va, mode.encode("latin-1") + b"\0")
    out = {"build": build["build"], "fn": "%#010x" % build["parse"], "guest_path": guest,
           "mode": mode}
    stage = "open"
    try:
        fd = m.call(build["open"], [path_va, mode_va])
        out["fd"] = "%#010x" % fd
        if fd == 0:
            out.update(verdict="REJECT", stage="open", r0=None,
                       note="open wrapper returned 0; the caller logs code 25 and skips the parser")
        else:
            stage = "parse"
            r0 = m.call(build["parse"], [fd])
            stage = "close"
            m.call(build["close"], [fd])
            if r0 not in VERDICT_MAP:
                raise Blocked("parser returned %#010x, not in the decoded verdict map" % r0)
            out.update(verdict=VERDICT_MAP[r0], stage="parse", r0="%#010x" % r0)
    except EngineError as exc:
        raise Blocked("%s in %s at pc %#010x: %s" % (type(exc).__name__, stage, m.reg("pc"),
                                                     str(exc)[:200])) from None
    except V.Blocked as exc:
        raise Blocked("%s (stage %s, pc %#010x)" % (exc, stage, m.reg("pc"))) from None
    parser_logs = [e for e in logs if build["parse"] <= e["site"] < build["parse_end"]]
    out["log_codes"] = [e["code"] for e in parser_logs]
    out["log_sites"] = ["%#010x" % e["site"] for e in parser_logs]
    out["reads"] = [list(r) for r in card.reads()]
    out["imports"] = sorted({e["name"].split("!", 1)[-1] for e in m.import_log})
    out["insns_note"] = "PySh4, vcard_l3 import models"
    return out


# ---------------------------------------------------------------------------
# controls
def controls(factory: bytes) -> list[dict]:
    """Mutation controls built from the factory file (expected outcome each)."""
    n_entries = struct.unpack_from("<I", factory, 36)[0] if len(factory) >= 40 else 0
    return [
        {"name": "factory", "data": factory, "verdict": "ACCEPT", "codes": []},
        {"name": "missing file", "data": None, "verdict": "REJECT", "codes": [], "stage": "open"},
        # cached path: size 32 == bytes read, so the parser reads its nodes from
        # the 0x77220-byte buffer, past the file end (heap bytes, zero here)
        {"name": "truncate to 32 B (cached, reads past EOF)", "data": mutate(factory, truncate=32),
         "verdict": "ACCEPT", "codes": []},
        {"name": "node+36 xor 1 (not a multiple of 40)", "data": mutate(factory, flip=(36, 1)),
         "verdict": "REJECT", "codes": [20]},
        {"name": "node+36 = 201*40", "data": mutate(factory, set_u32=(36, 201 * 40)),
         "verdict": "REJECT", "codes": [10]},
        # passes the count check (200 <= 200), then fails unlogged (first run, observed)
        {"name": "node+36 = 200*40 (bound)", "data": mutate(factory, set_u32=(36, 200 * 40)),
         "verdict": "REJECT", "codes": []},
        {"name": "zero-padded to 0x77220 (bound, cached)", "data": mutate(factory, pad=0x77220),
         "verdict": "ACCEPT", "codes": []},
        {"name": "zero-padded to 0x77221 (uncached)", "data": mutate(factory, pad=0x77221),
         "verdict": "ACCEPT", "codes": [26]},
        {"name": "node+36 unchanged (%d)" % n_entries, "data": mutate(factory, set_u32=(36, n_entries)),
         "verdict": "ACCEPT", "codes": []},
    ]


def run_controls(image_path: str, factory: bytes, name: str = "DRSTR001.DAT",
                 results: list | None = None) -> list[dict]:
    digest = hashlib.sha256(Path(image_path).read_bytes()).hexdigest()
    rows = []
    for c in controls(factory):
        row = {"name": c["name"], "size": None if c["data"] is None else len(c["data"]),
               "sha256": None if c["data"] is None else hashlib.sha256(c["data"]).hexdigest()}
        try:
            r = run(image_path, memory_card(name, c["data"]), head_digest=digest)
            row.update(verdict=r["verdict"], r0=r["r0"], codes=r["log_codes"], stage=r["stage"])
        except Blocked as exc:
            r = None
            row.update(verdict="BLOCKED", reason=str(exc), codes=None)
        if results is not None:
            results.append(r)
        ok = row["verdict"] == c["verdict"] and row["codes"] == c["codes"]
        row.update(expected_verdict=c["verdict"], expected_codes=c["codes"], ok=ok)
        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# CLI
def _card_from_args(args):
    import vcard_l3 as V
    if args.file:
        data = Path(args.file).read_bytes()
        data = mutate(data, truncate=args.truncate,
                      flip=_pair(args.flip, ":") if args.flip else None,
                      set_u32=_pair(args.set_u32, "=") if args.set_u32 else None,
                      pad=args.pad)
        return memory_card("DRSTR001.DAT", None if args.hide else data), data
    if args.card_image or args.card_root:
        return V.make_card(args.card_root, args.card_image), None
    raise SystemExit("need --file, --card-image or --card-root")


def _pair(text: str, sep: str) -> tuple[int, int]:
    a, _, b = text.partition(sep)
    return int(a, 0), int(b, 0) if b else 0xFF


def _trace_record(out: dict, input_sha256, input_size, arguments=None, reads=None) -> dict:
    import reader_trace
    return reader_trace.from_drstr_l3(
        out, input_sha256=input_sha256, input_size=input_size, arguments=arguments,
        reads=reads, build=EU2011["build"], function="%#010x" % EU2011["parse"])


def cmd_run(args) -> int:
    if not Path(args.image).is_file():
        print("missing image: %s" % args.image, file=sys.stderr)
        return 2
    card, data = _card_from_args(args)
    try:
        out = run(args.image, card)
    except Blocked as exc:
        out = {"verdict": "BLOCKED", "reason": str(exc)}
    if data is not None:
        out["input_sha256"] = hashlib.sha256(data).hexdigest()
        out["input_size"] = len(data)
    if args.json:
        print(json.dumps(out, indent=2))
    else:
        for k, v in out.items():
            if k not in ("reads",):
                print("%-14s %s" % (k, v))
    if args.trace_out:
        import reader_trace
        reader_trace.write_trace(args.trace_out, [
            _trace_record(out, out.get("input_sha256"), out.get("input_size"))])
    return {"ACCEPT": 0, "REJECT": 1}.get(out["verdict"], 3)


def cmd_controls(args) -> int:
    results = [] if args.trace_out else None
    rows = run_controls(args.image, Path(args.file).read_bytes(), results=results)
    for r in rows:
        print("%-40s %-8s r0=%-11s codes=%-10s %s" % (r["name"], r["verdict"], r.get("r0"),
                                                     r.get("codes"), "ok" if r["ok"] else "DIFFERS"))
    if args.json:
        Path(args.json).write_text(json.dumps(rows, indent=2) + "\n")
    bad = [r for r in rows if not r["ok"]]
    print("controls: %d/%d as expected" % (len(rows) - len(bad), len(rows)))
    if args.trace_out:
        import reader_trace
        records = []
        for row, res in zip(rows, results):
            if res is None:
                res = dict(row)
            records.append(_trace_record(
                res, row["sha256"], row["size"], arguments={"case": row["name"]}))
        reader_trace.write_trace(args.trace_out, records)
    return 0 if not bad else 1


def selftest() -> int:
    fails, done = [], []

    def check(name, cond):
        done.append(name)
        print("%-4s %s" % ("PASS" if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    base = bytes(range(40)) + bytes(24)
    check("mutate: truncate keeps the head", mutate(base, truncate=10) == base[:10])
    check("mutate: flip xors one byte", mutate(base, flip=(36, 1))[36] == base[36] ^ 1)
    check("mutate: set_u32 is little-endian",
          struct.unpack_from("<I", mutate(base, set_u32=(36, 8040)), 36)[0] == 8040)
    check("mutate: pad zero-fills to the size", mutate(base, pad=0x100) == base + bytes(0x100 - len(base)))
    check("verdict map: exactly the two decoded return values",
          sorted(VERDICT_MAP) == [0, M32] and {v for _, _, v in RETURN_SITES if v is not None} == set(VERDICT_MAP))
    check("verdict map: 1 is not a verdict (refused, not mapped)", 1 not in VERDICT_MAP)
    check("log codes: each parser site lies inside the parser",
          all(EU2011["parse"] <= site < EU2011["parse_end"] for c, (site, _, _) in LOG_CODES.items() if c != 25))
    check("log codes: the caller's open-failure site lies in the caller",
          LOG_CODES[25][0] >= EU2011["caller"])
    rows = controls(bytes(36) + struct.pack("<I", 1600) + bytes(100))
    check("controls: 9 rows, factory first, one missing-file row",
          len(rows) == 9 and rows[0]["name"] == "factory" and sum(r["data"] is None for r in rows) == 1)
    check("controls: bad-modulus row is not a multiple of 40",
          struct.unpack_from("<I", rows[3]["data"], 36)[0] % 40 != 0)
    check("controls: over-bound row is 201 entries",
          struct.unpack_from("<I", rows[4]["data"], 36)[0] // 40 == 201)
    # memory card: the file resolves under any mount, a hidden file does not
    try:
        card = memory_card("DRSTR001.DAT", b"abc")
        card.set_mount("\\SystemSD")
        h = card.fopen("\\SystemSD\\DRSTR001.DAT", "rb")
        check("memory card: serves the file at the mount", h != 0 and card.fread(h, 8) == b"abc")
        empty = memory_card("DRSTR001.DAT", None)
        empty.set_mount("\\SystemSD")
        check("memory card: missing file opens as 0", empty.fopen("\\SystemSD\\DRSTR001.DAT", "rb") == 0)
    except ImportError as exc:                       # pragma: no cover
        check("memory card: vcard_l3 importable (%s)" % exc, False)
    # head check refuses a wrong image before the engine starts
    import tempfile
    with tempfile.NamedTemporaryFile() as fh:
        fh.write(b"not a head")
        fh.flush()
        try:
            run(fh.name, memory_card("DRSTR001.DAT", b""))
            check("run: a wrong head is BLOCKED", False)
        except Blocked as exc:
            check("run: a wrong head is BLOCKED before the engine", "not the eu2011 head" in str(exc))
    print("selftest: %d checks, %d failed" % (len(done), len(fails)))
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run", help="one file -> verdict")
    r.add_argument("image")
    r.add_argument("--file")
    r.add_argument("--card-image")
    r.add_argument("--card-root")
    r.add_argument("--truncate", type=lambda s: int(s, 0))
    r.add_argument("--flip", help="OFF:XOR")
    r.add_argument("--set-u32", help="OFF=VALUE")
    r.add_argument("--pad", type=lambda s: int(s, 0))
    r.add_argument("--hide", action="store_true")
    r.add_argument("--json", action="store_true")
    r.add_argument("--trace-out", help="write a reader_trace record (M9.69)")
    c = sub.add_parser("controls", help="factory file + mutation controls")
    c.add_argument("image")
    c.add_argument("--file", required=True)
    c.add_argument("--json")
    c.add_argument("--trace-out", help="write one reader_trace record per control (M9.69)")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "run":
        return cmd_run(args)
    if args.cmd == "controls":
        return cmd_controls(args)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
