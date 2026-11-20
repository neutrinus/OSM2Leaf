#!/usr/bin/env python3
"""TMC service list (``TMC/reception.dat``) vs ``RDSTM001.DAT`` table codes (M4.16d).

``RDSTM001.DAT``'s ``0x1000`` header names 14 location tables per set by a
``u16 table_code`` (M4.16e, C-5137).  This tool tests the reading

    table_code = ord(CC hex digit) << 8 | LTN

(``CC`` = RDS country code nibble, ``LTN`` = TMC location table number), by
joining three independent sources:

1. ``TMC/reception.dat`` (8-byte rows; the ``ff 0f CC LTN`` rows list the
   card's (CC, LTN) pairs; one ``03 ..`` row carries one more pair at bytes
   ``2..3``);
2. the table codes of the ``RDSTM001.DAT`` header;
3. the country that the table's TMC records land in on the map (set-1 refs →
   MAPAL level-2 parcel ``countries``, the M4.16b/M4.16e chain, majority over a
   sample of refs), mapped to its RDS CC by the IEC 62106 country-code table
   (``RDS_CC`` below, only the countries needed here).

Commands::

    tmc_reception.py rows reception.dat
    tmc_reception.py join reception.dat RDSTM001.DAT MAPAL001 [--refs 300] [--seed 1]
    tmc_reception.py --selftest

``join`` prints, per table: code, CC/LTN from the code, whether reception.dat
lists that pair, the map country and its RDS CC, and a shuffled-country
control.  Stdlib only; reads vendor files, writes nothing.
"""
from __future__ import annotations

import argparse
import collections
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# RDS country code (CC nibble) by ISO 3166 numeric country (IEC 62106 Annex D, European area)
RDS_CC = {40: 0xA, 56: 0x6, 203: 0x2, 208: 0x9, 246: 0x6, 250: 0xF, 276: 0xD, 380: 0x5,
          528: 0x8, 578: 0xF, 616: 0x3, 724: 0xE, 752: 0xE, 756: 0x4, 826: 0xC}


def parse_rows(d: bytes) -> list[tuple[int, int, str]]:
    """[(cc, ltn, kind)] from reception.dat 8-byte rows."""
    out = []
    for i in range(0, len(d) - 7, 8):
        r = d[i:i + 8]
        if r[0] == 0xFF and r[1] == 0x0F:
            out.append((r[2], r[3], "ff0f"))
        elif r[0] == 0x03:
            out.append((r[2], r[3], "03"))
    return out


def code_cc_ltn(code: int):
    """(cc, ltn) if the high byte is an ASCII hex digit, else None."""
    hi, lo = code >> 8, code & 0xFF
    ch = chr(hi)
    if ch in "0123456789ABCDEF":
        return int(ch, 16), lo
    return None


def table_countries(rdstm: bytes, mapal: Path, nref: int, seed: int) -> list:
    """Majority parcel country of a sample of set-1 refs, per set-1 table row."""
    import rdstm_links as rl
    import tmc_fielddir as tf

    h = rl.parse_header(rdstm)
    pairs = tf.rdstm_pairs(rdstm)
    ntab = len(h["sets"][0]["tables"])
    gs = rl.parse_groups(rdstm, h["sets"][1]["index_at"])
    cache = {}

    def entry(ref):
        g = ref >> 16
        if g not in cache:
            cache[g] = rl.group_entries(rdstm, gs[g])
        return cache[g][ref & 0xFFFF]

    rng = random.Random(seed)
    samples = []
    keys = set()
    for t in range(ntab):
        refs = [r for groups in pairs[ntab + t]["links"].values() for _role, rs in groups for r in rs]
        pick = rng.sample(refs, min(nref, len(refs)))
        ents = [entry(r) for r in pick]
        keys.update(e[0] for e in ents)
        samples.append(ents)
    tiles = sorted({rl.tile_of(*rl.parcel_origin(k)) for k in keys})
    sec = rl.load_sec2([mapal / n for n in tiles if (mapal / n).exists()], 2, keys)
    out = []
    for ents in samples:
        c = collections.Counter()
        for key, a, b in ents:
            rec = sec.get(key)
            if rec and rl.resolve(rec, a, b):
                c.update(set(rec["countries"]))
        out.append(c)
    return [t["code"] for t in h["sets"][1]["tables"]], out


def cmd_rows(a) -> int:
    for cc, ltn, kind in parse_rows(Path(a.reception).read_bytes()):
        print(f"{kind:5s} CC {cc:x} LTN {ltn}")
    return 0


def cmd_join(a) -> int:
    rows = parse_rows(Path(a.reception).read_bytes())
    pairs = {(cc, ltn) for cc, ltn, _k in rows}
    codes, ctry = table_countries(Path(a.rdstm).read_bytes(), Path(a.mapal), a.refs, a.seed)
    print(f"reception.dat pairs {len(pairs)}; RDSTM set-1 tables {len(codes)}")
    listed = cc_ok = 0
    majors = []
    print("row code  CC LTN in_reception country(share) RDS_CC match")
    for t, (code, c) in enumerate(zip(codes, ctry)):
        cl = code_cc_ltn(code)
        main, n = c.most_common(1)[0] if c else (None, 0)
        majors.append(main)
        tot = sum(c.values()) or 1
        inrec = cl in pairs
        ok = cl is not None and RDS_CC.get(main) == cl[0]
        listed += inrec
        cc_ok += ok
        print(f"{t:3d} {code:04x} {cl[0] if cl else -1:2x} {cl[1] if cl else -1:3d} {str(inrec):>5} "
              f"{main}({n}/{tot}) {RDS_CC.get(main, -1):x} {ok}")
    rng = random.Random(a.seed)
    ctl = []
    for _ in range(1000):
        sh = majors[:]
        rng.shuffle(sh)
        ctl.append(sum(cl is not None and RDS_CC.get(m) == cl[0]
                       for m, cl in zip(sh, (code_cc_ltn(c) for c in codes))))
    unlisted = pairs - {code_cc_ltn(c) for c in codes}
    print(f"table codes listed in reception.dat {listed}/{len(codes)}; reception pairs without a table {sorted(unlisted)}")
    print(f"code CC = RDS CC of the map country {cc_ok}/{len(codes)}; shuffled countries: "
          f"mean {sum(ctl) / len(ctl):.2f}, max {max(ctl)} (1000 shuffles)")
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            fails.append(name)

    d = bytes([0x01, 0x3E, 0, 0, 0, 0xFF, 0xFF, 0xFF,
               0x03, 0x0A, 0x0C, 0x0A, 0x00, 0xFF, 0xFF, 0xFF,
               0xFF, 0x0F, 0x02, 0x19, 0x00, 0xFF, 0xFF, 0xFF,
               0xFF, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF])
    rows = parse_rows(d)
    check("rows", rows == [(0x0C, 0x0A, "03"), (0x02, 0x19, "ff0f")])
    check("code CZ", code_cc_ltn(0x3219) == (2, 0x19))
    check("code DE", code_cc_ltn(0x4401) == (0xD, 1))
    check("code GB", code_cc_ltn(0x430A) == (0xC, 10))
    check("code not ascii", code_cc_ltn(0x1234) is None)
    check("rds cc", RDS_CC[203] == 2 and RDS_CC[276] == 0xD)
    print("selftest:", "FAIL" if fails else "PASS")
    return 1 if fails else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("rows")
    p.add_argument("reception")
    p = sub.add_parser("join")
    p.add_argument("reception")
    p.add_argument("rdstm")
    p.add_argument("mapal")
    p.add_argument("--refs", type=int, default=300)
    p.add_argument("--seed", type=int, default=1)
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.cmd == "rows":
        return cmd_rows(a)
    if a.cmd == "join":
        return cmd_join(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
