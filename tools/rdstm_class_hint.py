#!/usr/bin/env python3
"""Road-class hints from TMC location types through the RDSTM link join (M4.31).

M4.17 found ``class_code`` (``LCTBL001`` header ``u16`` at +14) "motorway-pure"
for a few values on numbered roads, and M4.31's first pass stopped because no
join reached a routing link.  M4.16b/M4.16e closed that join: a TMC location
code -> ``RDSTM001.DAT`` link record -> ``u32`` ref -> level-2 section-2
``(parcel, node, link)``.  This tool carries every code-joined TMC record of
the chosen set-1 tables to the section-2 entries its refs name and reads the
entry's class word (``cls & 0xf``, the class nibble of the link key, C-5150).

It then asks whether a TMC attribute predicts that class better than a
shuffled label:

* ``type``   - the record's own location type (field 0);
* ``parent`` - the location type of the record's road: field 6 (linear
  reference) followed up to a road-level linear ``L1.x``/``L2.x`` (``L1.1``
  motorway, ``L1.2`` first-class road ...);
* ``road``   - that road's location code (road identity: positive control,
  a road is mostly one class);
* ``parity`` - ``code & 1`` (negative control, no class information).

Per record the link class is the majority nibble over its resolved links
(``--pick majority``, default) or the smallest nibble in 3..7 (``--pick
top``, which assumes the level 3-5 shape order and is kept as a variant).
Score: modal accuracy = share of records whose link class equals the modal
class of their group (groups below ``--min-group`` records pooled into
one), against the same score with labels shuffled within each table
(``--shuffles`` runs, mean and max reported).  It also checks that
``lctbl_records.class_code`` equals field 0 for every record.

Usage::

    rdstm_class_hint.py run LCTBL001.DAT RDSTM001.DAT MAPAL001 [--tables 0,9]
    rdstm_class_hint.py --selftest
"""
from __future__ import annotations

import argparse
import collections
import random
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE / "ze0-viewer" / "tools_ze0"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

ID_MASK = 0x1FFF


def tmc_type(t: int | None) -> str:
    """ISO 14819-3 style label: 10101 -> L1.1, 20303 -> P3.3, 300 -> A3.0."""
    if t is None:
        return "-"
    cls, typ, sub = t // 10000, (t // 100) % 100, t % 100
    letter = {0: "A", 1: "L", 2: "P"}.get(cls, "?")
    return f"{letter}{typ}.{sub}"


def load_class_view(paths, keys: set) -> dict:
    """{parcel_key: {(link_id, node): cls & 0xf}} for level-2 section-2 records."""
    import clarion_rd  # noqa: E402
    import rd_check  # noqa: E402
    from tile_scan import TileScan  # noqa: E402

    out = {}
    for path in paths:
        with TileScan(str(path)) as t:
            for r in t.records(section=2, level=2):
                if r.k % 2:
                    continue
                plain = r.plain()
                key = struct.unpack_from(">I", plain, 0)[0]
                if key not in keys:
                    continue
                rec = clarion_rd.parse_record(rd_check.part_a(plain, 2))
                if "nnodes" not in rec:
                    continue
                view = {}
                for i, nd in enumerate(rec["nodes"]):
                    for e in nd["entries"]:
                        if e["cls"] & 0x8000:
                            continue
                        view[(e["id"] & ID_MASK, i)] = e["cls"] & 0xF
                out[key] = view
    return out


def is_road_type(t: int | None) -> bool:
    """TMC road-level linear types: L1.x (road) and L2.x (ring road)."""
    return t is not None and t // 10000 == 1 and (t // 100) % 100 in (1, 2)


def road_of(code: int, types: dict, fields: dict, depth: int = 4) -> int | None:
    """Follow the linear reference (field 6) up to a road-level linear (L1.x/L2.x)."""
    import tmc_fielddir as tf

    c = code
    for _ in range(depth):
        if c != code and is_road_type(types.get(c)):
            return c
        f = fields.get(c)
        nxt = tf.u16(f[6]) if f else None
        if not nxt or nxt == c:
            return None
        c = nxt
    return c if is_road_type(types.get(c)) else None


def top_class(cnt) -> int:
    """Highest road class among the record's links (smallest nibble 3..7), else the majority."""
    main = [c for c in cnt if 3 <= c <= 7]
    return min(main) if main else cnt.most_common(1)[0][0]


def modal_accuracy(items, min_group: int = 20) -> tuple[float, int, dict]:
    """items: [(label, cls)].  Small groups are pooled under label None."""
    sizes = collections.Counter(lab for lab, _ in items)
    groups: dict = collections.defaultdict(collections.Counter)
    for lab, c in items:
        groups[lab if sizes[lab] >= min_group else None][c] += 1
    hit = sum(cnt.most_common(1)[0][1] for cnt in groups.values())
    n = len(items)
    return (hit / n if n else 0.0), n, groups


def shuffled_scores(by_table, key, shuffles, rng, min_group):
    out = []
    for _ in range(shuffles):
        items = []
        for recs in by_table.values():
            labs = [r[key] for r in recs]
            rng.shuffle(labs)
            items += [(lab, r["cls"]) for lab, r in zip(labs, recs)]
        out.append(modal_accuracy(items, min_group)[0])
    return out


def score(by_table, key, shuffles, seed, min_group):
    items = [(r[key], r["cls"]) for recs in by_table.values() for r in recs]
    acc, n, groups = modal_accuracy(items, min_group)
    null = shuffled_scores(by_table, key, shuffles, random.Random(seed), min_group)
    return acc, n, groups, null


def cmd_run(a) -> int:
    import rdstm_links as rl
    import tmc_fielddir as tf

    ldata = Path(a.lctbl).read_bytes()
    d = Path(a.rdstm).read_bytes()
    h = rl.parse_header(d)
    recs = tf.load_records(ldata)
    tables = tf.parse_index(ldata)
    slices = tf.table_slices(tables)
    pairs = tf.rdstm_pairs(d)
    nps = tf.neg_pos(recs)
    ntab = len(h["sets"][0]["tables"])
    gs = rl.parse_groups(d, h["sets"][1]["index_at"])
    cache: dict = {}

    def entry(ref):
        g = ref >> 16
        if g not in cache:
            cache[g] = rl.group_entries(d, gs[g])
        return cache[g][ref & 0xFFFF]

    # class_code (M4.17) == field 0 (location type)?
    same = diff = 0
    for raw in recs:
        # lctbl_records.parse_stream: class_code = header u16 big-endian at +14
        cc = int.from_bytes(raw[14:16], "big") if len(raw) >= 16 else None
        f0 = tf.u16(tf.decode_record(raw)["fields"][0])
        if cc == f0:
            same += 1
        else:
            diff += 1
    print(f"class_code (header u16 @+14) == field 0 (location type): {same}/{same + diff}")

    rows = list(range(ntab)) if not a.tables else [int(x) for x in a.tables.split(",")]
    plan, keys = [], set()
    for t in rows:
        pr = pairs[ntab + t]
        best = max(range(len(tables)), key=lambda ti: tf.join_table(nps, tables[ti], pr, slices[ti][0], 0)[0])
        s0, s1 = slices[best]
        code_k = {}
        for k in range(s1 - s0):
            c = tables[best].get(k)
            if c is not None:
                code_k[c] = k
        plan.append((t, best, s0, code_k, pr))
        for c in code_k:
            for _r, refs in pr["links"].get(c, ()):
                keys.update(entry(r)[0] for r in refs)
    tiles = sorted({rl.tile_of(*rl.parcel_origin(k)) for k in keys})
    mapal = Path(a.mapal)
    view = load_class_view([mapal / n for n in tiles if (mapal / n).exists()], keys)
    print(f"level-2 parcels {len(view)}/{len(keys)} in {len(tiles)} tiles")

    by_table: dict = {}
    cls_all = collections.Counter()
    nrefs = nres = 0
    for t, best, s0, code_k, pr in plan:
        types = {}
        fields = {}
        for c, k in code_k.items():
            f = tf.decode_record(recs[s0 + k])["fields"]
            fields[c] = f
            types[c] = tf.u16(f[0])
        out = []
        for c, k in code_k.items():
            if c not in pr["links"]:
                continue
            cnt = collections.Counter()
            for _r, refs in pr["links"][c]:
                for r in refs:
                    nrefs += 1
                    key, ea, eb = entry(r)
                    v = view.get(key)
                    cl = v.get((eb & ID_MASK, ea & ID_MASK)) if v else None
                    if cl is None:
                        continue
                    nres += 1
                    cnt[cl] += 1
            if not cnt:
                continue
            cls_all.update(cnt)
            parent = tf.u16(fields[c][6])
            road = road_of(c, types, fields)
            pick = cnt.most_common(1)[0][0] if a.pick == "majority" else top_class(cnt)
            out.append(dict(code=c, cls=pick, type=types[c],
                            parent=types.get(road) if road else None,
                            road=(t, road) if road else None, parity=c & 1))
        by_table[t] = out
    n = sum(len(v) for v in by_table.values())
    print(f"tables {len(rows)}; records with a resolved link {n}; refs {nrefs} resolved {nres}")
    print("link class nibble over resolved refs: "
          + ", ".join(f"{c}:{v}" for c, v in sorted(cls_all.items())))
    print(f"\n{'attribute':9s} {'n':>7s} {'modal acc':>9s} {'null mean':>9s} {'null max':>9s}  role")
    results = {}
    for key, role in (("type", "test"), ("parent", "test"), ("road", "positive control"),
                      ("parity", "negative control")):
        acc, nn, groups, null = score(by_table, key, a.shuffles, a.seed, a.min_group)
        results[key] = groups
        print(f"{key:9s} {nn:7d} {acc:9.3f} {sum(null) / len(null):9.3f} {max(null):9.3f}  {role}")
    for key in ("parent", "type"):
        print(f"\nlink class by {key} location type (groups >= {a.min_group}; None = pooled):")
        groups = results[key]
        order = sorted(groups, key=lambda g: -sum(groups[g].values()))
        for g in order[: a.top]:
            cnt = groups[g]
            tot = sum(cnt.values())
            lab = "pooled" if g is None else f"{g} {tmc_type(g)}"
            dist = " ".join(f"{c}:{v}" for c, v in sorted(cnt.items(), key=lambda x: -x[1])[:5])
            print(f"  {lab:14s} n={tot:6d} modal {cnt.most_common(1)[0][0]:2d} "
                  f"({cnt.most_common(1)[0][1] / tot:.3f})  {dist}")
    roads = (10101, 10102, 10103, 10104)
    print("\nper table: modal link class (share, n) of records on " + ", ".join(tmc_type(r) for r in roads))
    for t, recs in by_table.items():
        cells = []
        for rt in roads:
            cnt = collections.Counter(r["cls"] for r in recs if r["parent"] == rt)
            tot = sum(cnt.values())
            if tot < a.min_group:
                cells.append(f"{tmc_type(rt)} -")
                continue
            c, v = cnt.most_common(1)[0]
            cells.append(f"{tmc_type(rt)} {c} ({v / tot:.2f}, {tot})")
        print(f"  table {t:2d}: " + "  ".join(cells))
    return 0


def _selftest() -> int:
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name)
        ok &= bool(cond)

    check("tmc_type L1.1", tmc_type(10101) == "L1.1")
    check("tmc_type P3.3", tmc_type(20303) == "P3.3")
    check("tmc_type A3.0", tmc_type(300) == "A3.0")
    rng = random.Random(3)
    # a label equal to the class gives accuracy 1 and beats its shuffled null
    recs = [dict(cls=c, lab=c, rnd=rng.randrange(2)) for c in [rng.randrange(1, 8) for _ in range(800)]]
    acc, n, _g, null = score({0: recs}, "lab", 10, 1, 20)
    check("class-equal label acc 1.0", acc == 1.0 and n == 800)
    check("class-equal label beats null", max(null) < 0.5)
    acc_r, _n, _g, null_r = score({0: recs}, "rnd", 10, 1, 20)
    check("random label within null +0.05", acc_r <= max(null_r) + 0.05)
    # small groups are pooled
    acc_p, _n, g, _ = score({0: [dict(cls=1, lab=i) for i in range(10)]}, "lab", 2, 1, 20)
    check("small groups pooled", list(g) == [None] and acc_p == 1.0)
    check("top_class picks motorway", top_class(collections.Counter({7: 5, 3: 1, 1: 9})) == 3)
    check("top_class falls back", top_class(collections.Counter({1: 2, 12: 1})) == 1)
    check("is_road_type", is_road_type(10101) and is_road_type(10202) and not is_road_type(10300))
    print("selftest: " + ("OK" if ok else "FAIL"))
    return 0 if ok else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    r = sub.add_parser("run")
    r.add_argument("lctbl")
    r.add_argument("rdstm")
    r.add_argument("mapal")
    r.add_argument("--tables", default="")
    r.add_argument("--shuffles", type=int, default=20)
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--min-group", type=int, default=20)
    r.add_argument("--top", type=int, default=12)
    r.add_argument("--pick", choices=("majority", "top"), default="majority",
                   help="per-record link class: majority nibble or highest road class (3..7)")
    a = ap.parse_args(argv)
    if a.selftest:
        return _selftest()
    if a.cmd == "run":
        return cmd_run(a)
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
