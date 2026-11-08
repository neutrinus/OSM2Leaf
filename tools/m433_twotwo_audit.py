#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""M4.33: per-case/counted audit of two->two no_* misses (M4.30 follow-up).

Focus: same-way identity (osm_from_eq_to), u-turn representation, and
OSM-vs-tile way splitting at via for the two->two miss class. Read-only;
imports rd_restrictions helpers (does not modify rd_restrictions.py).

    python3 tools/m433_twotwo_audit.py TILE IMF [--level 1|2] [--seed N]
    python3 tools/m433_twotwo_audit.py --selftest
"""
import argparse
import collections
import importlib.util
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_rr():
    spec = importlib.util.spec_from_file_location(
        "rd_restrictions", os.path.join(HERE, "rd_restrictions.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _classify(row, info, rr):
    r, F, T, ents, nonedge, tag, am, dup, feq = row
    t_regs = rr.regs_of(ents[T])
    f_regs = rr.regs_of(ents[F])
    t_names_f = [w for w in t_regs if (w >> 12) == F]
    f_names_f = [w for w in f_regs if (w >> 12) == F]
    f_names_t = [w for w in f_regs if (w >> 12) == T]
    t_ff_names = [w >> 12 for w in t_regs if (w & 0xFF) == 0xFF]
    f_ff_names = [w >> 12 for w in f_regs if (w & 0xFF) == 0xFF]
    return {
        "id": r["id"],
        "tag": tag,
        "feq": feq,
        "F_eq_T": F == T,
        "hit": info["hit"],
        "mclass": info["mclass"],
        "fclass": info["fclass"],
        "tclass": info["tclass"],
        "amb_margin": am,
        "dup_way": dup,
        "n_nonedge": len(nonedge),
        "T_regs_n": len(t_regs),
        "F_regs_n": len(f_regs),
        "T_names_F_n": len(t_names_f),
        "T_names_F_byte1s": tuple(sorted(set(w & 0xFF for w in t_names_f))),
        "F_names_F_n": len(f_names_f),
        "F_names_F_ff": any((w & 0xFF) == 0xFF for w in f_names_f),
        "F_names_T_ff": any((w & 0xFF) == 0xFF for w in f_names_t),
        "T_ff_names": tuple(sorted(set(t_ff_names))),
        "F_ff_names": tuple(sorted(set(f_ff_names))),
        "T_no_ff": len(t_ff_names) == 0,
        "F_no_ff": len(f_ff_names) == 0,
    }


def _ct(c, key=None):
    cc = collections.Counter()
    for x in c:
        v = key(x) if key else x
        cc[v] += 1
    return cc


def audit_two_two(tile, imf, level=1, seed=42, out=print):
    rr = _load_rr()
    rels, reasons, rows, rng, mapping = rr._deep_rows(tile, imf, level, seed, lambda *a: None)
    out("=== M4.33 two->two audit: %s level %d (seed=%d) ===" % (os.path.basename(tile), level, seed))
    out("precheck context: restrictions=%d no_* rows=%d reasons=%s" % (
        len(rels), sum(1 for rw in rows if rw[5].startswith("no_")), dict(reasons)))
    rng2 = random.Random(seed)
    two = []
    all_no = 0
    for rw in rows:
        r, F, T, ents, nonedge, tag = rw[:6]
        if not tag.startswith("no_"):
            rr._all_row_shuffle(r, F, T, ents, nonedge, tag, rng2)
            continue
        info = rr._no_row(r, F, T, ents, nonedge, tag, rng2)
        all_no += 1
        if info["fclass"] == "two" and info["tclass"] == "two":
            two.append((rw, info, _classify(rw, info, rr)))
    misses = [x for x in two if not x[1]["hit"]]
    hits = [x for x in two if x[1]["hit"]]
    out("all no_* matched: %d; two->two: n=%d hit=%d miss=%d" % (all_no, len(two), len(hits), len(misses)))
    out("-- precheck (M4.30 clustering, over %d two->two misses) --" % len(misses))
    out("  tag:no_u_turn                              %d" % sum(1 for _, _, c in misses if c["tag"] == "no_u_turn"))
    out("  osm_from_eq_to                             %d" % sum(1 for _, _, c in misses if c["feq"]))
    out("  mclass:no_ff_word_naming_F_anywhere        %d" % sum(1 for _, _, c in misses if c["mclass"] == "no_ff_word_naming_F_anywhere"))
    mc = _ct((c["mclass"] for _, _, c in misses))
    out("-- miss mclass (full) --")
    for k, v in mc.most_common():
        out("  %-42s %d" % (k, v))
    tc = _ct((c["tag"] for _, _, c in misses))
    out("-- miss tags --")
    for k, v in tc.most_common():
        out("  %-42s %d" % (k, v))
    # same-way identity / F==T
    out("-- same-way identity (osm_from_eq_to / F==T) --")
    out("  misses feq (osm from==to):                 %d / %d" % (sum(1 for _, _, c in misses if c["feq"]), len(misses)))
    out("  misses F==T (tile entry):                  %d / %d" % (sum(1 for _, _, c in misses if c["F_eq_T"]), len(misses)))
    out("  misses feq AND F==T:                       %d" % sum(1 for _, _, c in misses if c["feq"] and c["F_eq_T"]))
    out("  misses feq AND F!=T:                       %d" % sum(1 for _, _, c in misses if c["feq"] and not c["F_eq_T"]))
    out("  misses !feq AND F==T:                      %d" % sum(1 for _, _, c in misses if not c["feq"] and c["F_eq_T"]))
    out("  hits feq:                                  %d / %d" % (sum(1 for _, _, c in hits if c["feq"]), len(hits)))
    out("  hits F==T:                                 %d / %d" % (sum(1 for _, _, c in hits if c["F_eq_T"]), len(hits)))
    # u-turn representation
    ut_m = [c for _, _, c in misses if c["tag"] == "no_u_turn"]
    ut_h = [c for _, _, c in hits if c["tag"] == "no_u_turn"]
    out("-- u-turn representation (tag=no_u_turn, two->two) --")
    out("  no_u_turn misses / hits:                   %d / %d" % (len(ut_m), len(ut_h)))
    out("  no_u_turn miss feq:                        %d / %d" % (sum(1 for c in ut_m if c["feq"]), len(ut_m)))
    out("  no_u_turn miss F==T:                       %d / %d" % (sum(1 for c in ut_m if c["F_eq_T"]), len(ut_m)))
    out("  no_u_turn miss feq AND F==T:               %d" % sum(1 for c in ut_m if c["feq"] and c["F_eq_T"]))
    out("  no_u_turn miss !feq:                       %d" % sum(1 for c in ut_m if not c["feq"]))
    out("  no_u_turn miss mclass counts:")
    for k, v in _ct((c["mclass"] for c in ut_m)).most_common():
        out("    %-40s %d" % (k, v))
    out("  no_u_turn miss T_has_no_ff_words:          %d" % sum(1 for c in ut_m if c["T_no_ff"]))
    out("  no_u_turn miss F_has_no_ff_words:          %d" % sum(1 for c in ut_m if c["F_no_ff"]))
    out("  no_u_turn miss F_names_F_ff (self on F):   %d" % sum(1 for c in ut_m if c["F_names_F_ff"]))
    out("  no_u_turn miss F_names_T_ff (rev on F):    %d" % sum(1 for c in ut_m if c["F_names_T_ff"]))
    out("  no_u_turn miss T_names_F present:          %d" % sum(1 for c in ut_m if c["T_names_F_n"]))
    out("  no_u_turn hit feq:                         %d / %d" % (sum(1 for c in ut_h if c["feq"]), len(ut_h)))
    out("  no_u_turn hit F==T:                        %d / %d" % (sum(1 for c in ut_h if c["F_eq_T"]), len(ut_h)))
    # osm_from_eq_to class
    feq_m = [c for _, _, c in misses if c["feq"]]
    feq_nm = [c for _, _, c in misses if not c["feq"]]
    out("-- osm_from_eq_to miss class (two->two misses) --")
    out("  feq misses:                                %d / %d" % (len(feq_m), len(misses)))
    out("  feq miss tags:")
    for k, v in _ct((c["tag"] for c in feq_m)).most_common():
        out("    %-40s %d" % (k, v))
    out("  feq miss mclass:")
    for k, v in _ct((c["mclass"] for c in feq_m)).most_common():
        out("    %-40s %d" % (k, v))
    out("  feq miss F==T:                             %d" % sum(1 for c in feq_m if c["F_eq_T"]))
    out("  feq miss F_names_F_ff (self on F):         %d" % sum(1 for c in feq_m if c["F_names_F_ff"]))
    out("  feq miss T_has_no_ff_words:                %d" % sum(1 for c in feq_m if c["T_no_ff"]))
    out("  !feq misses:                               %d" % len(feq_nm))
    out("  !feq miss tags:")
    for k, v in _ct((c["tag"] for c in feq_nm)).most_common():
        out("    %-40s %d" % (k, v))
    # OSM-vs-tile splitting / mapping shape
    out("-- OSM-vs-tile way splitting / mapping shape (counted) --")
    out("  miss dup_way (OSM dup bearing among matched): %d / %d" % (sum(1 for _, _, c in misses if c["dup_way"]), len(misses)))
    out("  hit dup_way:                               %d / %d" % (sum(1 for _, _, c in hits if c["dup_way"]), len(hits)))
    out("  miss amb_margin<15:                        %d / %d" % (sum(1 for _, _, c in misses if c["amb_margin"] < 15), len(misses)))
    out("  miss n_nonedge distribution:")
    for k, v in sorted(_ct((c["n_nonedge"] for _, _, c in misses)).items()):
        out("    n_nonedge=%-4s                             %d" % (k, v))
    out("  miss F/T reg count (T_regs_n=0, F_regs_n=0): T0=%d F0=%d" % (
        sum(1 for _, _, c in misses if c["T_regs_n"] == 0),
        sum(1 for _, _, c in misses if c["F_regs_n"] == 0)))
    # cross: no_u_turn AND feq vs not
    out("-- cross: no_u_turn x feq (two->two misses) --")
    for feqv in (True, False):
        sub = [c for c in ut_m if c["feq"] == feqv]
        out("  no_u_turn feq=%-5s n=%-4d F==T=%d mclass=%s" % (
            feqv, len(sub), sum(1 for c in sub if c["F_eq_T"]),
            dict(_ct((c["mclass"] for c in sub)))))
    out("-- cross: feq x tag (two->two misses) --")
    for tagv, n in tc.most_common():
        sub = [c for _, _, c in misses if c["tag"] == tagv]
        out("  %-20s n=%-4d feq=%d F==T=%d" % (tagv, len(sub), sum(1 for c in sub if c["feq"]), sum(1 for c in sub if c["F_eq_T"])))
    # alternate encoding candidates (counted, no outcome fitting claim beyond counts)
    out("-- alternate encoding candidates on misses (counted) --")
    out("  any ff naming F on F entry (self):          %d" % sum(1 for _, _, c in misses if c["F_names_F_ff"]))
    out("  any ff naming T on F entry (reverse loc):   %d" % sum(1 for _, _, c in misses if c["F_names_T_ff"]))
    out("  ff naming F on any entry other than T:     %d" % sum(1 for _, _, c in misses if c["mclass"] == "ff_naming_F_on_other_entries"))
    out("  reverse ff on F names T:                   %d" % sum(1 for _, _, c in misses if c["mclass"] == "reverse_ff_on_F_names_T"))
    out("  other byte1 on T names F:                  %d" % sum(1 for _, _, c in misses if c["mclass"] == "other_byte1_on_T_names_F"))
    out("  no ff word naming F anywhere:              %d" % sum(1 for _, _, c in misses if c["mclass"] == "no_ff_word_naming_F_anywhere"))
    # feq-specific alternate: self-prohibition on F
    out("  feq miss AND F_names_F_ff:                 %d / %d" % (sum(1 for c in feq_m if c["F_names_F_ff"]), len(feq_m)))
    out("  feq miss AND F==T AND F_names_F_ff:        %d" % sum(1 for c in feq_m if c["F_eq_T"] and c["F_names_F_ff"]))
    out("  no_u_turn feq miss AND F_names_F_ff:       %d / %d" % (sum(1 for c in ut_m if c["feq"] and c["F_names_F_ff"]), sum(1 for c in ut_m if c["feq"])))
    return {
        "level": level, "all_no": all_no, "two_n": len(two), "two_hit": len(hits),
        "two_miss": len(misses),
        "precheck": {
            "no_u_turn": sum(1 for _, _, c in misses if c["tag"] == "no_u_turn"),
            "osm_from_eq_to": sum(1 for _, _, c in misses if c["feq"]),
            "no_ff_word_naming_F_anywhere": sum(1 for _, _, c in misses if c["mclass"] == "no_ff_word_naming_F_anywhere"),
        },
    }


def _ent(regs, cls=0x8000):
    # matches regs_of(): extra[:(w5>>6)&0x3f]; w5 holds reg count in bits 6-11
    return {"extra": list(regs), "w5": (len(regs) << 6), "cls": cls}


def selftest(out=print):
    # synthetic classification logic only (no vendor files)
    rr = _load_rr()
    # T=2 carries a 0xff word naming F=0 -> hit
    e_t = _ent([(0 << 12) | 0xFF, (0 << 12) | 0x01])
    e_f = _ent([])
    ents = [e_f, _ent([], 0), e_t]
    info = rr._no_row({"id": 1}, 0, 2, ents, [0, 2], "no_left_turn", random.Random(0))
    assert info["hit"] is True
    info2 = rr._no_row({"id": 2}, 0, 2, [_ent([]), _ent([]), _ent([])], [0, 2], "no_u_turn", random.Random(0))
    assert info2["hit"] is False and info2["mclass"] == "no_ff_word_naming_F_anywhere"
    row = ({"id": 3, "frm": 7, "to": 7, "tag": "no_u_turn"}, 0, 0, [e_f], [0], "no_u_turn", 5.0, False, True)
    info3 = rr._no_row(row[0], 0, 0, row[3], [0], "no_u_turn", random.Random(0))
    c = _classify(row, info3, rr)
    assert c["feq"] and c["F_eq_T"] and c["tag"] == "no_u_turn"
    e_self = _ent([(0 << 12) | 0xFF])
    row2 = ({"id": 4, "frm": 1, "to": 1, "tag": "no_u_turn"}, 0, 0, [e_self], [0], "no_u_turn", 1.0, False, True)
    c2 = _classify(row2, rr._no_row(row2[0], 0, 0, [e_self], [0], "no_u_turn", random.Random(0)), rr)
    assert c2["F_names_F_ff"] is True
    # invoke rd_restrictions.selftest (no modification to that file)
    rr.selftest()
    out("m433_twotwo_audit selftest: OK (synthetic + rd_restrictions.selftest invoked)")
    return 0


def main():
    ap = argparse.ArgumentParser(description="M4.33 two->two miss class audit")
    ap.add_argument("tile", nargs="?")
    ap.add_argument("imf", nargs="?")
    ap.add_argument("--level", type=int, choices=[1, 2], default=1)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    if not a.tile or not a.imf:
        ap.error("tile and imf required (or --selftest)")
    res = audit_two_two(a.tile, a.imf, a.level, a.seed)
    # exit 0 always for audit; precheck is informational
    sys.exit(0)


if __name__ == "__main__":
    main()
