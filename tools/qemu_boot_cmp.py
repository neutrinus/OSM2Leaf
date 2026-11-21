#!/usr/bin/env python3
"""Compare ``-M ze0`` boots made with different QEMU builds (TODO M8.A9).

Each argument is a ``tools/qemu-ze0/run.sh --workdir`` directory (it holds
``qemu.log`` and ``serial.log``).  The first one is the reference.  A boot is
reduced to the observables that do not depend on the emulator's own
translation cache:

* ``serial``   the kernel debug text; two runs agree when one is a prefix of
               the other (a faster host simply gets further in the same
               wall-clock time);
* ``traps``    the sequence of synchronous exceptions that the guest program
               causes by itself, as ``(code, pc)``: everything except the TLB
               misses (``0x040``/``0x060``, which depend on the soft-TLB
               state of the QEMU build and are not reproducible even between
               two runs of QEMU 11.1.3) and the interrupts (``>= 0x200``,
               whose pc is a timing phase); compared as a common prefix;
* ``irqs``     the number of interrupts per code;
* ``access``   the unmodelled-access list of ``ce_qemu_probe.summarize_log``
               (first-seen order).

Exit 0 when every run agrees with the reference on all four, 1 otherwise.
The TLB-miss counts are printed for information only.

Usage:
    qemu_boot_cmp.py REF_DIR DIR [DIR...]
    qemu_boot_cmp.py --selftest
"""
import argparse
import hashlib
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ce_qemu_probe  # noqa: E402

TLB = (0x040, 0x060)


def load(workdir):
    with open(os.path.join(workdir, "qemu.log"), errors="replace") as f:
        accesses, exceptions = ce_qemu_probe.summarize_log(f.read())
    serial_path = os.path.join(workdir, "serial.log")
    serial = b""
    if os.path.exists(serial_path):
        with open(serial_path, "rb") as f:
            serial = f.read()
    traps = [(c, pc) for c, _n, pc in exceptions if c not in TLB and c < 0x200]
    irqs = {}
    tlb = 0
    for c, _n, _pc in exceptions:
        if c >= 0x200:
            irqs[c] = irqs.get(c, 0) + 1
        elif c in TLB:
            tlb += 1
    return {"dir": workdir, "serial": serial, "traps": traps, "irqs": irqs,
            "tlb": tlb, "access": accesses}


def is_prefix(a, b):
    n = min(len(a), len(b))
    return a[:n] == b[:n]


def compare(ref, run):
    """Return a dict name -> bool for the four observables."""
    return {
        "serial": is_prefix(ref["serial"], run["serial"]) and bool(ref["serial"]) == bool(run["serial"]),
        "traps": is_prefix(ref["traps"], run["traps"]) and bool(ref["traps"]) == bool(run["traps"]),
        "irqs": ref["irqs"] == run["irqs"],
        "access": ref["access"] == run["access"],
    }


def describe(run):
    h = hashlib.sha256(run["serial"]).hexdigest()[:16]
    irq = " ".join("0x%03x x%d" % kv for kv in sorted(run["irqs"].items())) or "-"
    return ("%s: serial %d bytes sha256:%s | traps %d | irqs %s | accesses %d | tlb misses %d (info)"
            % (run["dir"], len(run["serial"]), h, len(run["traps"]), irq,
               len(run["access"]), run["tlb"]))


def report(dirs):
    runs = [load(d) for d in dirs]
    ok = True
    print(describe(runs[0]))
    for run in runs[1:]:
        print(describe(run))
        res = compare(runs[0], run)
        for name in ("serial", "traps", "irqs", "access"):
            print("  %-6s %s" % (name, "same" if res[name] else "DIFFERENT"))
        ok = ok and all(res.values())
    print("verdict: %s (%d run(s) against the reference)"
          % ("SAME" if ok else "DIFFERENT", len(runs) - 1))
    return 0 if ok else 1


def _write(d, name, exc, serial, access=()):
    path = os.path.join(d, name)
    os.makedirs(path)
    lines = []
    for kind, addr in access:
        lines.append("Invalid %s at addr 0x%X, size 2, region '(null)', reason: rejected" % (kind, addr))
    for code, nm, pc in exc:
        lines.append("exception 0x%03x [%s] raised" % (code, nm))
        lines.append("pc=0x%08x sr=0x40000000 pr=0x00000000 fpscr=0x00040001" % pc)
    with open(os.path.join(path, "qemu.log"), "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(path, "serial.log"), "wb") as f:
        f.write(serial)
    return path


def selftest():
    fails = []

    def check(name, cond):
        print("%s %s" % ("ok  " if cond else "FAIL", name))
        if not cond:
            fails.append(name)

    base = [(0x040, "tlb_miss", 0x100), (0x0e0, "addr_error", 0xfffffd8d),
            (0x400, "interrupt", 0x200), (0x0c0, "tlb_violation", 0x300)]
    acc = [("read", 0x1FE46010), ("write", 0x38)]
    with tempfile.TemporaryDirectory() as d:
        ref = _write(d, "ref", base, b"Windows CE\nline2\n", acc)
        # same guest behaviour: extra TLB miss, other irq pc, longer serial
        same = _write(d, "same", [(0x040, "tlb_miss", 0x104)] + base[:2]
                      + [(0x400, "interrupt", 0x208)] + base[3:]
                      + [(0x0e0, "addr_error", 0xfffffd8d)],
                      b"Windows CE\nline2\nline3\n", acc)
        trap = _write(d, "trap", base[:1] + [(0x0e0, "addr_error", 0xfffff001)] + base[2:],
                      b"Windows CE\nline2\n", acc)
        text = _write(d, "text", base, b"Windows CE\nother\n", acc)
        irq = _write(d, "irq", base + [(0x400, "interrupt", 0x200)], b"Windows CE\nline2\n", acc)
        accd = _write(d, "acc", base, b"Windows CE\nline2\n", acc[:1])
        empty = _write(d, "empty", [], b"", [])
        r = load(ref)
        check("reference parses: 2 traps, 1 irq, 1 tlb miss, 2 accesses",
              len(r["traps"]) == 2 and r["irqs"] == {0x400: 1} and r["tlb"] == 1 and len(r["access"]) == 2)
        check("TLB misses, irq pc and a longer run do not matter", all(compare(r, load(same)).values()))
        check("a different trap pc is detected", compare(r, load(trap))["traps"] is False)
        check("different debug text is detected", compare(r, load(text))["serial"] is False)
        check("a different interrupt count is detected", compare(r, load(irq))["irqs"] is False)
        check("a different access list is detected", compare(r, load(accd))["access"] is False)
        e = compare(r, load(empty))
        check("an empty run is not 'a prefix' of the reference", not e["serial"] and not e["traps"])
        check("report(): exit 0 for the same boot", report([ref, same]) == 0)
        check("report(): exit 1 when one run differs", report([ref, same, trap]) == 1)
    print("selftest: %d failed" % len(fails))
    return 1 if fails else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("dirs", nargs="*", help="run.sh work directories; the first is the reference")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if len(a.dirs) < 2:
        ap.error("need a reference directory and at least one more")
    for d in a.dirs:
        if not os.path.exists(os.path.join(d, "qemu.log")):
            print("qemu_boot_cmp: no qemu.log in %s" % d, file=sys.stderr)
            return 2
    return report(a.dirs)


if __name__ == "__main__":
    sys.exit(main())
