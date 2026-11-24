#!/usr/bin/env python3
"""EU vs US 2011 audio comparison (M1.58).

Answers "what differs in the audio path between the EU and the US 2011
card, and what does the unit's own kernel start for it" with four
sub-commands. Stdlib only; reads the first ~100 MiB of each card image
(``curl -r 0-104857599``) or the whole image.

  modules EU US [--all]   per module of ROM A: section layout, differing
                          bytes and clusters, and the strings only one
                          build has (build stamps filtered: PDB path,
                          ``RSDS`` record). Default: the audio set.
  drivers EU US           device names (``XXXn:``) and ``IOCTL_*`` names
                          in each ``Audio.exe``.
  tnr NK1                 the tuner driver table of a kernel (``TNRn:``,
                          area mask, ``\\Drivers\\Launch`` key).
  objtable IMG            the ``OBJ_SEM_*`` backup object table of
                          ``OBJDLL.dll`` (index = object number in the
                          ``OBJ_BackUp_Load`` logs).

Method and results: docs/experiments/EXP-2026-11-24-M1.58-eu-us-audio.md

Usage:
  audio_diff.py modules EU.sys US.sys [--all]
  audio_diff.py drivers EU.sys US.sys
  audio_diff.py tnr firmware/unit-flash/nk1-QY7200ND.bin
  audio_diff.py objtable EU.sys
  audio_diff.py --selftest
"""
import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cerom  # noqa: E402

ROM_A_START = 0x200200          # build A, first copy (cerom census default)
READ_BYTES = 100 << 20

AUDIO_SET = (
    "Audio.exe", "auiapp.exe", "auirtdll.dll", "AuiMonitoringCC.dll",
    "waveapi.dll", "audevman.dll", "wavessi1.dll", "wavessi2.dll",
    "BtAudioCC.dll", "UsbAudioCC.dll", "AuxCC.dll", "CddaCC.dll",
    "BT_MGR.dll", "BT_ENG.dll", "PhoneBTA.exe", "Speech.exe",
    "SpeechCC.dll", "Vehicle.exe",
)

AREA_MASKS = {0xffff0000: "all areas", 0x00010000: "Japan",
              0x00020000: "Euro", 0x00040000: "USA",
              0x00080000: "Russia", 0x00100000: "China"}

# strings that only stamp the build, not its behaviour
BUILD_STAMP = re.compile(r"\.pdb$|^RSDS|pbworkspaces|PBWorkspaces", re.I)
ASCII_RUN = re.compile(rb"[\x20-\x7e]{8,}")
UTF16_RUN = re.compile(rb"(?:[\x20-\x7e]\x00){8,}")
DEVICE = re.compile(r"^[A-Z]{3}[0-9]:$")
SLACK_DLL = re.compile(r"^\W*\w+\.dll$", re.I)
IOCTL = re.compile(r"IOCTL_[A-Z0-9_]+")


def load_rom(path, start=ROM_A_START):
    with open(path, "rb") as fh:
        data = fh.read(READ_BYTES)
    return cerom.CERom(data, start)


def module_sections(rom, name):
    """``[(realaddr, bytes)]`` of the stored sections of module ``name``."""
    for m in rom.modules():
        if m["name"].lower() == name.lower():
            out = []
            for s in rom.o32(m):
                if not s["psize"]:
                    continue
                o = rom.va2file(s["dataptr"])
                out.append((s["realaddr"], bytes(rom.d[o:o + s["psize"]])))
            return out
    return None


def strings(blobs):
    """Printable ASCII and UTF-16LE runs of >= 8 characters with a word."""
    out = set()
    for b in blobs:
        out.update(m.group().decode() for m in ASCII_RUN.finditer(b))
        out.update(m.group().decode("utf-16le") for m in UTF16_RUN.finditer(b))
    return {s for s in out if re.search(r"[A-Za-z]{4}", s)}


def diff_clusters(x, y, gap=16):
    """Count differing bytes of two equal-length blobs and their clusters."""
    n = clusters = 0
    prev = -gap - 1
    for i in range(min(len(x), len(y))):
        if x[i] != y[i]:
            n += 1
            if i > prev + gap:
                clusters += 1
            prev = i
    return n, clusters


def meaningful(s, word):
    """Text or identifier, not section slack or random bytes.

    Dropped: ``name.dll`` leftovers in section padding (module names of the
    linker's slack) and short runs with no separator (``4KGxVR5=``).
    """
    if not word.match(s) or SLACK_DLL.match(s):
        return False
    return len(s) >= 12 or bool(re.search(r"[ _:]", s))


def compare_module(sec_a, sec_b):
    """Layout, byte diff and string diff of one module in two builds."""
    rep = {}
    layout_a = [(va, len(b)) for va, b in sec_a]
    layout_b = [(va, len(b)) for va, b in sec_b]
    rep["size_a"] = sum(n for _, n in layout_a)
    rep["size_b"] = sum(n for _, n in layout_b)
    rep["same_layout"] = layout_a == layout_b
    if rep["same_layout"]:
        n = c = 0
        for (_, x), (_, y) in zip(sec_a, sec_b):
            dn, dc = diff_clusters(x, y)
            n += dn
            c += dc
        rep["diff_bytes"], rep["diff_clusters"] = n, c
    sa = {s for s in strings(b for _, b in sec_a) if not BUILD_STAMP.search(s)}
    sb = {s for s in strings(b for _, b in sec_b) if not BUILD_STAMP.search(s)}
    # drop high-entropy noise: keep runs that look like identifiers/text
    word = re.compile(r"^[\w :<>\[\]()%.,!#*=/\\-]+$")
    rep["only_a"] = sorted(s for s in sa - sb if meaningful(s, word))
    rep["only_b"] = sorted(s for s in sb - sa if meaningful(s, word))
    if rep["same_layout"] and not rep["only_a"] and not rep["only_b"]:
        rep["verdict"] = "build-only"
    elif not rep["only_a"] and not rep["only_b"]:
        rep["verdict"] = "relinked, same strings"
    else:
        rep["verdict"] = "functional"
    return rep


def cmd_modules(args):
    ra, rb = load_rom(args.eu), load_rom(args.us)
    names = AUDIO_SET
    if args.all:
        na = {m["name"] for m in ra.modules()}
        nb = {m["name"] for m in rb.modules()}
        names = sorted(na & nb, key=str.lower)
    for name in names:
        sa, sb = module_sections(ra, name), module_sections(rb, name)
        if sa is None or sb is None:
            print("%-22s missing in %s" % (name, "EU" if sa is None else "US"))
            continue
        r = compare_module(sa, sb)
        lay = ("same layout, %d B in %d clusters" % (r["diff_bytes"], r["diff_clusters"])
               if r["same_layout"] else "layout differs")
        print("%-22s EU %7d  US %7d  %-36s %-22s EU-only %3d  US-only %3d"
              % (name, r["size_a"], r["size_b"], lay, r["verdict"],
                 len(r["only_a"]), len(r["only_b"])))
        if args.verbose:
            for s in r["only_a"]:
                print("    EU< %s" % s)
            for s in r["only_b"]:
                print("    US> %s" % s)
    return 0


def audio_drivers(rom):
    sec = module_sections(rom, "Audio.exe") or []
    st = strings(b for _, b in sec)
    # device names are short: rescan with a 4-character floor
    dev = set()
    for _, b in sec:
        for m in re.finditer(rb"(?:[A-Z]\x00){3}[0-9]\x00:\x00\x00\x00", b):
            dev.add(m.group()[:-2].decode("utf-16le"))
    ioctl = set()
    for s in st:
        ioctl.update(IOCTL.findall(s))
    return sorted(dev), sorted(ioctl)


def cmd_drivers(args):
    out = {}
    for label, path in (("EU", args.eu), ("US", args.us)):
        out[label] = audio_drivers(load_rom(path))
        print("%s Audio.exe devices: %s" % (label, " ".join(out[label][0])))
    ia, ib = set(out["EU"][1]), set(out["US"][1])
    print("IOCTL names: EU %d, US %d, common %d" % (len(ia), len(ib), len(ia & ib)))
    print("  common : %s" % " ".join(sorted(ia & ib)))
    print("  EU only: %s" % " ".join(sorted(ia - ib)))
    print("  US only: %s" % " ".join(sorted(ib - ia)))
    return 0


def tnr_table(data):
    """Records of the tuner driver table: (offset, name, mask, launch key).

    Each record holds ``TNRn:`` in UTF-16; the dword 8 bytes before the name
    is the AppLaunch area mask (``AREA_MASKS``); the ``\\Drivers\\Launch\\…``
    key follows at +0x40.
    """
    out = []
    for m in re.finditer(rb"T\x00N\x00R\x00[0-9]\x00:\x00\x00\x00", data):
        i = m.start()
        mask = struct.unpack_from("<I", data, i - 8)[0] if i >= 8 else None
        key = data[i + 0x40:i + 0x40 + 0x80]
        k = re.match(rb"((?:[\x20-\x7e]\x00)+)", key)
        if not k or not k.group(1).startswith("\\Drivers\\".encode("utf-16le")):
            continue
        out.append((i, m.group()[:-2].decode("utf-16le"), mask,
                    k.group(1).decode("utf-16le")))
    return out


def cmd_tnr(args):
    with open(args.nk, "rb") as fh:
        data = fh.read()
    rows = tnr_table(data)
    for off, name, mask, key in rows:
        area = AREA_MASKS.get(mask, "other")
        print("0x%06x %-6s mask 0x%08x  %-20s %s" % (off, name, mask, area, key))
    return 0 if rows else 1


def obj_table(data, start=None):
    """``OBJ_SEM_*`` names of OBJDLL's backup table, in index order."""
    i = data.find(b"OBJ_SEM_CARSPEED\x00")
    if i < 4:
        return []
    base = i - 4
    out = []
    for n in range(64):
        rec = data[base + 36 * n:base + 36 * n + 36]
        if len(rec) < 36 or struct.unpack_from("<I", rec)[0] != n:
            break
        out.append(rec[4:].split(b"\0")[0].decode())
    return out


def cmd_objtable(args):
    rom = load_rom(args.img)
    blob = b"".join(b for _, b in module_sections(rom, "OBJDLL.dll") or [])
    names = obj_table(blob)
    for n, name in enumerate(names):
        print("0x%02X %s" % (n, name))
    return 0 if names else 1


def selftest():
    # diff_clusters
    assert diff_clusters(b"abcdef", b"abcdef") == (0, 0)
    assert diff_clusters(b"a" * 64, b"b" + b"a" * 62 + b"b") == (2, 2)
    assert diff_clusters(b"aaaa", b"abba") == (2, 1)
    # compare_module: build stamp only vs a functional string
    base = b"\0" * 32 + "TNR2:\0".encode("utf-16le") + b"SetVolumeCommand\0"
    a = [(0x11000, base + b"C:\\x\\10EV_EU\\a.pdb\0")]
    b = [(0x11000, base + b"C:\\x\\10EVNAM\\a.pdb\0")]
    r = compare_module(a, b)
    assert r["verdict"] == "build-only", r
    b2 = [(0x11000, base.replace(b"SetVolumeCommand", b"SetXmRadioCmd123"))]
    r2 = compare_module(a, b2)
    assert r2["verdict"] != "build-only" and "SetVolumeCommand" in r2["only_a"], r2
    assert not meaningful(" .iphlpapi.dll", re.compile(r".*"))
    assert not meaningful("4KGxVR5=", re.compile(r".*"))
    assert meaningful("OBJ_TelSet_getObjID", re.compile(r".*"))
    # tnr_table: one record with the Euro mask, one without a key (rejected)
    rec = (b"\0" * 4 + struct.pack("<I", 0x00020000) + b"\0" * 4 + "TNR2:".encode("utf-16le")
           + b"\0" * 6)
    rec = rec + b"\0" * (12 + 0x40 - len(rec) + 12)
    rec = rec[:12 + 0x40] + "\\Drivers\\Launch\\Rds".encode("utf-16le") + b"\0" * 4
    rows = tnr_table(rec + b"\0" * 16 + "TNR9:\0".encode("utf-16le") + b"\0" * 0x100)
    assert [(n, m, k) for _, n, m, k in rows] == [("TNR2:", 0x00020000, "\\Drivers\\Launch\\Rds")], rows
    # obj_table: two records then a break
    t = b""
    for n, name in enumerate([b"OBJ_SEM_CARSPEED", b"OBJ_SEM_SETTING"]):
        t += struct.pack("<I", n) + name.ljust(32, b"\0")
    t += struct.pack("<I", 7) + b"x" * 32
    assert obj_table(b"pad" + t) == ["OBJ_SEM_CARSPEED", "OBJ_SEM_SETTING"]
    print("selftest ok")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true")
    sub = p.add_subparsers(dest="cmd")
    m = sub.add_parser("modules")
    m.add_argument("eu")
    m.add_argument("us")
    m.add_argument("--all", action="store_true", help="every common module")
    m.add_argument("-v", "--verbose", action="store_true", help="print the strings")
    d = sub.add_parser("drivers")
    d.add_argument("eu")
    d.add_argument("us")
    t = sub.add_parser("tnr")
    t.add_argument("nk")
    o = sub.add_parser("objtable")
    o.add_argument("img")
    args = p.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.cmd == "modules":
        return cmd_modules(args)
    if args.cmd == "drivers":
        return cmd_drivers(args)
    if args.cmd == "tnr":
        return cmd_tnr(args)
    if args.cmd == "objtable":
        return cmd_objtable(args)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
