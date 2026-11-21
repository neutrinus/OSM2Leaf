#!/usr/bin/env python3
"""One reproducible map of what is on a ZE0 card: the ROM modules and the data.

M1.36 was a scratch census whose code hashes included XIP relocation (a module
that only moved in memory read as "changed"). This tool turns the census into a
committed atlas with **reloc-masked** code hashes, so equal modules do read
equal, and adds the data side the census never had.

What it reads (nothing is written to the repo; vendor bytes stay on disk)
--------------------------------------------------------------------------
*ROM side.* Every SH-4/WinCE CE ROM segment on the image (build A `0x200200`,
B `0x3e00200`, C `0x5200200`) through ``tools/cerom.py``. Per module:

  - size, section count, number of executable sections, code bytes (sum of the
    executable section ``psize``),
  - a **reloc-masked** code hash: the module's executable sections hashed with
    every literal-pool slot a ``mov.l/mov.w @(disp,PC)`` names masked to ``0``,
    and every pool value that is a relocated pointer (inside the module's VA
    range) or an import-table slot masked to ``0xff``; branch displacements are
    reduced to a same-function/other-function bit. The same masking
    ``tools/fn_match.py`` uses, applied at section granularity,
  - named imports (DLLs and slot count), named exports (count and the first
    few names),
  - COM co-classes from the module's ``.rgs`` registration text
    (``Mod.CoClass.1 = s 'CoClass Control'``), and
  - a one-line role where a string/export/COM registration supports it, else
    ``unknown`` (the ``basis`` column says which).

*Data side.* The FAT32 map partition: the file families and their file counts,
the ``FILESentry`` rom-files of build B, and the ``TFAT16`` system tail volume
at the FAT32 partition end (``0x1c8400400``; README, ``docs/format/firmware.md``).
The FAT walk covers the whole volume, so it needs the **full image** (a 256 MiB
head cannot reach subdirectory clusters beyond its boundary); the ROM side runs
on the 256 MiB heads. Supply either.

Usage
-----
    rom_atlas.py --selftest
    rom_atlas.py atlas --head EU2011=archive/head256.img --head US2011=...
        [--head EU2014=PATH --head EU2016=PATH]
        [--full EU2011=PATH ...] [--json OUT] [-o OUT.md]
    rom_atlas.py equal --head EU2011=PATH --head US2011=PATH [--rom A] [--json]

``atlas`` prints a Markdown table per image (the generated
``docs/research/rom-atlas.md`` is this output plus a header) and, with
``--json``, the whole structure. ``equal`` reports, per ROM, which modules in
two images are equal after reloc masking.

Image keys and pins
-------------------
The four pinned cards are ``EU2011``/``US2011`` (256 MiB heads pinned by
``fetch_image.py``) and ``EU2014``/``EU2016`` (heads pinned there too). The tool
never downloads; give it paths. Missing a `--full` path only drops the FAT walk.

Exit codes: 0 ok, 1 a requested comparison failed, 2 usage or unreadable input.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cardcheck  # noqa: E402
import cerom  # noqa: E402
import leafimg  # noqa: E402

READ_LIMIT = 128 << 20          # builds A/B/C all live in the first 128 MiB
ROM_KEYS = ("A", "B", "C")
DEFAULT_ROM_STARTS = {"A": 0x200200, "B": 0x3e00200, "C": 0x5200200}
TFAT_SCAN = 1 << 20             # how far past the FAT32 partition to look
RGS_CLASS_RE = re.compile(rb"([A-Za-z0-9_]+)\.([A-Za-z0-9_]+)\.1\s*=\s*s\s*'")
HASH_PREFIX = 16


# --------------------------------------------------------------------------
# Reloc-masked section digest (the fn_match mask at section granularity)
# --------------------------------------------------------------------------


def digest_words(words, base_va, code_bytes, load_range, iat_slots=frozenset()):
    """Reloc-masked SHA-256 of one section's halfwords.

    ``words`` are the section's u16 halfwords (little-endian SH-4), ``base_va``
    the section's realaddr, ``code_bytes`` the section bytes (for reading pool
    values), ``load_range`` the whole module's ``(lo, hi)`` VA span and
    ``iat_slots`` the module's import-slot VAs. A pool slot is masked to zeros
    (its value travels through the referencing load, which keeps its opcode and
    register), a branch is reduced to a same/other-function bit, and a pool
    value that is a relocated pointer or an IAT slot is masked to ``0xff``; a
    constant is kept. This is ``fn_match.fingerprint`` without the pdata split,
    so a module that moved in memory hashes equal.
    """
    import fn_match

    n = len(words)
    span = 2 * n
    # Pass 1: every byte offset a pool load names is pool data; record it and
    # the slot's size (4 for mov.l, 2 for mov.w), exactly as fn_match does.
    pool_bytes = set()
    pool_meta = {}
    for i, w in enumerate(words):
        if fn_match.is_mov_pc(w):
            lit = fn_match.pool_addr(base_va + 2 * i, w)
            size = 4 if (w >> 12) == 0xD else 2
            off2 = lit - base_va
            for k in range(size):
                pool_bytes.add(off2 + k)
            pool_meta[off2] = size

    fp = hashlib.sha256()
    for i, w in enumerate(words):
        off = 2 * i
        if off in pool_bytes:
            fp.update(b"\x00\x00")
            continue
        if fn_match.is_branch(w):
            tgt = fn_match.branch_target(base_va + off, w)
            same = base_va <= tgt < base_va + span
            cls = (w >> 12) if (w >> 12) in (0xA, 0xB) else 0x80 | ((w >> 8) & 0xF)
            fp.update(struct.pack("<BB", cls, 1 if same else 0))
            continue
        if fn_match.is_mov_pc(w):
            fp.update(struct.pack("<BH", (w >> 12), (w >> 8) & 0xF))
            continue
        fp.update(struct.pack("<H", w))

    lo, hi = load_range
    for off in sorted(pool_meta):
        size = pool_meta[off]
        if 0 <= off and off + size <= len(code_bytes):
            val = struct.unpack_from("<I" if size == 4 else "<H", code_bytes, off)[0]
            if lo <= val < hi or (base_va + off) in iat_slots or val in iat_slots:
                fp.update(b"\xff" * size)
            else:
                fp.update(struct.pack("<I" if size == 4 else "<H", val))
        else:
            fp.update(b"\x00" * size)
    return fp.hexdigest()


def module_range(rom, mod):
    """The module's own process VA span, for pointer masking.

    A relocated pointer is one that points into the module's own image, whose
    process window is ``[vbase, vbase+vsize)`` from the ``e32`` header. It must
    not be the ``min``/``max`` over *all* sections: an import or resource
    section carries a ROM-space realaddr (e.g. ``0x1e6c000``) that is not the
    module's load range and would keep every relocated pool value unmasked.
    Fall back to the executable sections' span only when ``vbase``/``vsize`` are
    unset.
    """
    e = rom.e32(mod)
    if e["vbase"] and e["vsize"]:
        return e["vbase"], e["vbase"] + e["vsize"]
    secs = [s for s in rom.o32(mod) if s["flags"] & cerom.MEM_EXECUTE] or list(rom.o32(mod))
    lo = min(s["realaddr"] for s in secs)
    hi = max(s["realaddr"] + s["vsize"] for s in secs)
    return lo, hi


def module_digest(rom, mod):
    """``(code_sha or None, exec_section_count, code_bytes)`` for one module."""
    lo, hi = module_range(rom, mod)
    iat = frozenset(slot for _dll, slot, _n, _o in rom.imports(mod))
    d = rom.d
    parts = []
    code_bytes = 0
    exec_sections = 0
    for idx, sec in enumerate(rom.o32(mod)):
        if not sec["flags"] & cerom.MEM_EXECUTE:
            continue
        exec_sections += 1
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            parts.append(("compressed", idx, sec["vsize"]))
            continue
        code_bytes += sec["psize"]
        off = rom.va2file(sec["dataptr"])
        blob = d[off:off + sec["psize"]]
        words = [blob[i] | (blob[i + 1] << 8) for i in range(0, len(blob) - 1, 2)]
        parts.append((digest_words(words, sec["realaddr"], blob, (lo, hi), iat), idx, sec["vsize"]))
    if any(p[0] != "compressed" for p in parts):
        fp = hashlib.sha256()
        # Key by executable-section index and vsize, never by the section's
        # absolute realaddr: a module that moved in memory must hash equal.
        for p in parts:
            fp.update(("c" if p[0] == "compressed" else p[0]).encode())
            fp.update((":%d:%x:" % (p[1], p[2])).encode())
        code_sha = fp.hexdigest()
    else:
        code_sha = None
    return code_sha, exec_sections, code_bytes


# --------------------------------------------------------------------------
# COM co-classes, cross-checked against the .rgs registration string
# --------------------------------------------------------------------------


def parse_rgs_classes(blob):
    """``{(prefix, coclass)}`` pairs from a module's .rgs registration text.

    The value names the co-class (``VerInfoCC.VerInfoCtrl.1 = s 'VerInfoCtrl
    Control'``); the pair ``(VerInfoCC, VerInfoCtrl)`` is the class a reader can
    check. Only ASCII .rgs text holds this; compressed sections do not.
    """
    out = set()
    for m in RGS_CLASS_RE.finditer(blob):
        out.add((m.group(1).decode("latin1"), m.group(2).decode("latin1")))
    return out


def module_com_classes(rom, mod):
    blob = b""
    for sec in rom.o32(mod):
        if sec["flags"] & cerom.IMAGE_SCN_COMPRESSED:
            continue
        off = rom.va2file(sec["dataptr"])
        blob += rom.d[off:off + sec["psize"]]
    return sorted(parse_rgs_classes(blob))


# --------------------------------------------------------------------------
# Role lines: only where a string/export/COM registration supports them
# --------------------------------------------------------------------------

# Modules a CE reader knows from their name alone. ``basis=name`` flags that the
# line is the common WinCE role of that file name, not a string found here.
KNOWN_ROLES = {
    "nk.exe": ("kernel", "name"),
    "coredll.dll": ("core CE runtime (Coredll)", "name"),
    "gwes.exe": ("graphics/window/event subsystem (GWES)", "name"),
    "device.exe": ("device manager", "name"),
    "filesys.exe": ("filesystem manager", "name"),
    "shell.exe": ("shell", "name"),
}


def infer_role(name, exports, com_classes, known=KNOWN_ROLES):
    lname = (name or "").lower()
    if com_classes:
        return ("COM control (%s)" % com_classes[0][1], "com")
    if lname in known:
        return known[lname]
    ex = set(exports)
    if "DllCanUnloadNow" in ex or "DllGetClassObject" in ex:
        return ("COM server", "export")
    if "UpdateMng" in lname or lname.endswith("update.exe") or "updatecc" in lname:
        return ("firmware updater", "name")
    return ("unknown", "unknown")


# --------------------------------------------------------------------------
# Data side: FAT32 families, TFAT16 tail
# --------------------------------------------------------------------------

# A family is a root directory plus the file-name stem of its contents. The map
# layout puts every map shard of a kind in one directory (REFER001, MAPAL001);
# VER_INFO/TMC/OPNG/RDSTM001/BICON001/SPEECH hold singletons.
FAMILY_DIRS = {
    "MAPAL001": "map tiles (BxxRyyR / LEV3456R .DAT)",
    "REFER001": "refer/address/POI/street shards (.cmp/.ind)",
    "REFER002": "EV/charging refer layer (.cmp/.ind)",
    "SPEECH": "speech prompts",
    "TMC": "traffic message channel config",
    "XMD": "US XM traffic config",
    "BICON001": "brand icons",
    "RDSTM001": "road-status tiles (US)",
    "OPNG": "opening animation",
    "VER_INFO": "version/HDD_INFO",
}


def family_of(rel_path):
    """Family name for a root-relative path inside a family directory."""
    parts = rel_path.replace("\\", "/").strip("/").split("/")
    return parts[0] if len(parts) > 1 else "(root files)"


def count_families(paths):
    """``{family: count}`` over a list of root-relative file paths."""
    out = {}
    for p in paths:
        fam = family_of(p)
        out[fam] = out.get(fam, 0) + 1
    return out


def tfat_geometry(boot):
    """Geometry of a FAT12/16 boot sector (TFAT16 tail), parsed from 512 B."""
    if len(boot) < 62:
        raise ValueError("short boot sector")
    bps = struct.unpack_from("<H", boot, 11)[0]
    spc = boot[13]
    reserved = struct.unpack_from("<H", boot, 14)[0]
    fat_count = boot[16]
    root_entries = struct.unpack_from("<H", boot, 17)[0]
    total16 = struct.unpack_from("<H", boot, 19)[0]
    fat_size = struct.unpack_from("<H", boot, 22)[0]
    return {
        "oem": boot[3:11].decode("latin1").rstrip(),
        "fstype": boot[54:62].decode("latin1").rstrip(),
        "bytes_per_sector": bps,
        "sectors_per_cluster": spc,
        "cluster_bytes": bps * spc,
        "reserved_sectors": reserved,
        "fat_count": fat_count,
        "root_entries": root_entries,
        "total_sectors": total16,
        "fat_size_sectors": fat_size,
    }


def tfat_list(boot_bytes, volume_offset, image_path, max_entries=64):
    """List the entries of the TFAT16 volume's root directory.

    The TFAT stores one hidden ``__TFAT~1`` directory holding ``DONT_DEL.<nnn>``
    placeholders (README). Listing stops at the first zero entry or
    ``max_entries``.
    """
    geo = tfat_geometry(boot_bytes)
    bps, spc = geo["bytes_per_sector"], geo["sectors_per_cluster"]
    if not bps or not spc or not geo["fat_size_sectors"]:
        return geo, None, []
    root_off = volume_offset + (geo["reserved_sectors"]
                                + geo["fat_count"] * geo["fat_size_sectors"]) * bps
    with open(image_path, "rb") as fh:
        fh.seek(root_off)
        root = fh.read(geo["root_entries"] * 32)
    entries = []
    for i in range(geo["root_entries"]):
        e = root[i * 32:(i + 1) * 32]
        if len(e) < 32 or e[0] == 0:
            break
        if e[0] == 0xE5 or e[11] == 0x0F:
            continue
        base = e[0:8].decode("latin1").rstrip()
        ext = e[8:11].decode("latin1").rstrip()
        entries.append(base + ("." + ext if ext else ""))
    return geo, entries[0] if entries else None, entries


def data_side(full_path):
    """Families, FILESentry-independent map summary and TFAT16 tail of one image."""
    result = {"image": str(full_path), "size": None, "families": {},
              "root_files": [], "tfat16": None, "note": ""}
    p = Path(full_path)
    if not p.is_file():
        result["note"] = "full image not supplied; FAT tree not walked"
        return result
    result["size"] = p.stat().st_size
    try:
        fat = cardcheck.Fat32Image(p)
    except (ValueError, OSError) as exc:
        result["note"] = "FAT unreadable: %s" % exc
        return result
    try:
        top = fat.list_dir("")
        paths = []
        for e in top:
            if not e.is_dir:
                result["root_files"].append([e.name, e.size])
                continue
            try:
                for sub in fat.list_dir(e.name):
                    paths.append("%s/%s" % (e.name, sub.name))
            except (ValueError, FileNotFoundError):
                result["note"] = (result["note"] + " " if result["note"] else "") + \
                    "truncated image: %s not fully walkable" % e.name
        result["families"] = count_families(paths)
        result["label"] = fat.geometry.label
        part_end = fat.geometry.partition_offset + fat.geometry.partition_bytes
    finally:
        fat.close()
    try:
        with open(p, "rb") as fh:
            if part_end + 512 <= p.stat().st_size:
                fh.seek(part_end)
                boot = fh.read(512)
                geo, first, entries = tfat_list(boot, part_end, p)
                result["tfat16"] = {
                    "offset": "0x%x" % part_end,
                    "fstype": geo["fstype"],
                    "cluster_bytes": geo["cluster_bytes"],
                    "first_entry": first,
                    "entries": entries[:16],
                    "entry_count": len(entries),
                }
            else:
                result["note"] = (result["note"] + " " if result["note"] else "") + \
                    "tail past end of file (truncated head?)"
    except (OSError, ValueError) as exc:
        result["note"] = (result["note"] + " " if result["note"] else "") + "tail: %s" % exc
    return result


# --------------------------------------------------------------------------
# ROM side: one image -> {A/B/C: {...}}
# --------------------------------------------------------------------------


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_image(path):
    with open(path, "rb") as fh:
        return fh.read(READ_LIMIT)


def rom_side(path, do_hash=True):
    data = read_image(path)
    segments, duplicates = cerom.find_segments(data)
    out = {"duplicates": duplicates, "segments": {}}
    # Label by the known start offsets when they match, else in discovery order.
    by_start = {start: key for key, start in DEFAULT_ROM_STARTS.items()}
    for idx, seg in enumerate(segments):
        key = by_start.get(seg.start) or ROM_KEYS[idx]
        mods = list(seg.modules())
        seg_info = {
            "start": "0x%x" % seg.start,
            "nummods": seg.hdr["nummods"],
            "numfiles": seg.hdr["numfiles"],
            "modules": [],
            "filesentry": [],
        }
        for m in mods:
            exports = [name for _o, name, _r in seg.exports(m)] if do_hash else []
            imports = list(seg.imports(m))
            com = module_com_classes(seg, m) if do_hash else []
            code_sha, exec_secs, code_bytes = module_digest(seg, m) if do_hash else (None, 0, 0)
            all_secs = list(seg.o32(m))
            role, basis = infer_role(m["name"], exports, com)
            seg_info["modules"].append({
                "name": m["name"],
                "size": m["size"],
                "sections": len(all_secs),
                "exec_sections": exec_secs,
                "code_bytes": code_bytes,
                "code_sha": code_sha,
                "import_dlls": len({d for d, _s, _n, _o in imports}),
                "import_slots": len(imports),
                "exports": len(exports),
                "export_names": exports[:8],
                "com_classes": ["%s.%s" % c for c in com],
                "role": role,
                "basis": basis,
            })
        for f in seg.files():
            seg_info["filesentry"].append({
                "name": f["name"], "rsize": f["rsize"], "csize": f["csize"],
                "compressed": f["csize"] != f["rsize"],
            })
        out["segments"][key] = seg_info
    return out


# --------------------------------------------------------------------------
# Comparison: which modules are equal after reloc masking
# --------------------------------------------------------------------------


def equal_modules(rom_a, rom_b, rom_key):
    a = {m["name"].lower(): m for m in rom_a["segments"][rom_key]["modules"]}
    b = {m["name"].lower(): m for m in rom_b["segments"][rom_key]["modules"]}
    common = sorted(set(a) & set(b))
    equal, different, unreadable, nocode = [], [], [], []
    for k in common:
        ha, hb = a[k]["code_sha"], b[k]["code_sha"]
        if not a[k]["exec_sections"] or not b[k]["exec_sections"]:
            nocode.append(a[k]["name"])
        elif ha is None or hb is None:
            unreadable.append(a[k]["name"])
        elif ha == hb:
            equal.append(a[k]["name"])
        else:
            different.append(a[k]["name"])
    return {
        "rom": rom_key,
        "count_a": len(a),
        "count_b": len(b),
        "common": len(common),
        "equal": equal,
        "different": different,
        "unreadable": unreadable,
        "nocode": nocode,
        "only_a": sorted(a[k]["name"] for k in set(a) - set(b)),
        "only_b": sorted(b[k]["name"] for k in set(b) - set(a)),
    }


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render_image(name, image):
    out = []
    rom = image["rom"]
    for key in ROM_KEYS:
        seg = rom["segments"][key]
        mods = seg["modules"]
        code = sum(m["code_bytes"] for m in mods)
        out.append("### %s · ROM %s (`%s`)" % (name, key, seg["start"]))
        out.append("")
        out.append("%d modules, %d code bytes, %d `FILESentry` file(s)." %
                   (seg["nummods"], code, seg["numfiles"]))
        out.append("")
        out.append("| module | size | secs (exec) | code bytes | reloc-masked `sha256` | imports | exports | COM | role |")
        out.append("| --- | ---: | ---: | ---: | --- | ---: | ---: | --- | --- |")
        for m in mods:
            sha = m["code_sha"][:HASH_PREFIX] if m["code_sha"] else "-"
            com = m["com_classes"][0] if m["com_classes"] else "-"
            role = m["role"] + ("" if m["basis"] == "unknown" else " *(%s)*" % m["basis"])
            out.append("| `%s` | %d | %d (%d) | %d | `%s` | %d/%d | %d | %s | %s |" % (
                m["name"], m["size"], m["sections"], m["exec_sections"],
                m["code_bytes"], sha, m["import_dlls"], m["import_slots"],
                m["exports"], com, role))
        if seg["filesentry"]:
            fs = ", ".join("`%s` %d/%d" % (f["name"], f["csize"], f["rsize"])
                           for f in seg["filesentry"])
            out.append("")
            out.append("`FILESentry`: %s." % fs)
        out.append("")
    d = image.get("data")
    if d:
        out.append("### %s · data (FAT32 + TFAT16)" % name)
        out.append("")
        if d["families"]:
            fams = ", ".join("%s %d" % (k, v) for k, v in sorted(d["families"].items()))
            out.append("FAT32 `%s`: %s; root files %s." % (
                d.get("label", "?"), fams,
                ", ".join("`%s`" % n for n, _s in d["root_files"])))
        else:
            out.append("FAT32: %s" % (d.get("note") or "no files"))
        if d["tfat16"]:
            t = d["tfat16"]
            out.append("")
            out.append("TFAT16 tail at `%s`: `%s`, %d B/cluster, %d entries (`%s` …)." % (
                t["offset"], t["fstype"], t["cluster_bytes"], t["entry_count"],
                t["first_entry"] or "?"))
        out.append("")
    return out


def render_comparison(images, pairs):
    """``## Comparison (reloc-masked)`` for the given image-key pairs present."""
    out = []
    present = [(a, b) for a, b in pairs if a in images and b in images]
    if not present:
        return out
    out.append("## Equal modules after reloc masking")
    out.append("")
    out.append("Two modules are *equal* when their reloc-masked executable sections "
               "hash the same: a relocated pointer or an import slot is masked, so a "
               "module that only moved in memory still reads equal (M1.36's scratch "
               "hash did not mask, and read those as changed).")
    out.append("")
    out.append("| pair | ROM | modules | common | equal | different | unreadable | only left | only right |")
    out.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for a, b in present:
        for rk in ROM_KEYS:
            r = equal_modules(images[a]["rom"], images[b]["rom"], rk)
            out.append("| %s vs %s | %s | %d / %d | %d | %d | %d | %d | %d | %d |" % (
                a, b, rk, r["count_a"], r["count_b"], r["common"], len(r["equal"]),
                len(r["different"]), len(r["unreadable"]), len(r["only_a"]), len(r["only_b"])))
    out.append("")
    for a, b in present:
        for rk in ROM_KEYS:
            r = equal_modules(images[a]["rom"], images[b]["rom"], rk)
            if rk == "A":
                out.append("%s vs %s, ROM A — equal (%d): %s" % (
                    a, b, len(r["equal"]), ", ".join("`%s`" % n for n in r["equal"]) or "-"))
                only = []
                if r["only_a"]:
                    only.append("only %s: %s" % (a, ", ".join("`%s`" % n for n in r["only_a"])))
                if r["only_b"]:
                    only.append("only %s: %s" % (b, ", ".join("`%s`" % n for n in r["only_b"])))
                if only:
                    out.append("")
                    out.append("; ".join(only) + ".")
                out.append("")
    if ("EU2011", "US2011") in present:
        rc = equal_modules(images["EU2011"]["rom"], images["US2011"]["rom"], "C")
        rb = equal_modules(images["EU2011"]["rom"], images["US2011"]["rom"], "B")
        out.append("Negative control (C-6281): ROM B %d/%d and ROM C %d/%d equal — "
                   "so ROM A's %d equal module(s) is a real difference, not a masking "
                   "failure." % (len(rb["equal"]), rb["common"], len(rc["equal"]),
                                 rc["common"], len(equal_modules(images["EU2011"]["rom"],
                                                                 images["US2011"]["rom"], "A")["equal"])))
        out.append("")
    return out


def render_atlas(images, command="", pairs=(("EU2011", "US2011"), ("EU2011", "EU2014"), ("EU2014", "EU2016")),
                 provenance=None):
    out = []
    out.append("# ROM and data atlas of the ZE0 cards")
    out.append("")
    out.append("Generated by `tools/rom_atlas.py`; do not edit by hand. Re-run the "
               "`atlas` command with the four pinned heads and full images to "
               "reproduce every table below.")
    out.append("")
    if command:
        out.append("```bash")
        out.append(command)
        out.append("```")
        out.append("")
    if provenance:
        out.append("| image | sha256 (head) | head bytes | full image |")
        out.append("| --- | --- | ---: | --- |")
        for name, image in images.items():
            hdr = image["image"]
            out.append("| %s | `%s` | %d | %s |" % (
                name, hdr["sha256"], hdr["size"],
                provenance.get(name, "not supplied")))
        out.append("")
    out.append("`imports` is `distinct DLLs / slots`; `exports` is the named-export "
               "count; `COM` is the first co-class read from the module's `.rgs` "
               "registration; a role marked *(name)/(export)/(com)* is supported by "
               "that, else `unknown`.")
    out.append("")
    for name, image in images.items():
        hdr = image["image"]
        out.append("## %s" % name)
        out.append("")
        out.append("`%s` — %d bytes, sha256 `%s`%s" % (
            hdr["path"], hdr["size"], hdr["sha256"],
            " (256 MiB head)" if hdr.get("truncated") else ""))
        out.append("")
        out.extend(render_image(name, image))
    out.extend(render_comparison(images, pairs))
    return "\n".join(out)


# --------------------------------------------------------------------------
# Self-test (synthetic ROM + FAT boot sector; no vendor data)
# --------------------------------------------------------------------------


def selftest():
    failures = []

    def check(name, cond):
        print(("ok   " if cond else "FAIL ") + name)
        if not cond:
            failures.append(name)

    # 1. slug-free basics: family classifier and TFAT geometry.
    check("family_of picks the family directory",
          family_of("REFER001/ADDRE001.DAT.cmp") == "REFER001"
          and family_of("CMP.LST") == "(root files)")
    fams = count_families(["REFER001/a", "REFER001/b", "MAPAL001/c"])
    check("count_families counts per directory",
          fams == {"REFER001": 2, "MAPAL001": 1})

    boot = bytearray(512)
    boot[3:11] = b"MSWIN4.1"
    struct.pack_into("<H", boot, 11, 512)
    boot[13] = 64
    struct.pack_into("<H", boot, 14, 1)
    boot[16] = 2
    struct.pack_into("<H", boot, 17, 512)
    struct.pack_into("<H", boot, 19, 61440)
    struct.pack_into("<H", boot, 22, 38)
    boot[54:62] = b"TFAT16  "
    geo = tfat_geometry(bytes(boot))
    check("tfat_geometry reads the FAT16 boot sector",
          geo["fstype"] == "TFAT16" and geo["cluster_bytes"] == 512 * 64
          and geo["fat_size_sectors"] == 38)

    # 2. .rgs co-class parser, positive and negative.
    rgs = (b"\r\n{\r\n\tVerInfoCC.VerInfoCtrl.1 = s 'VerInfoCtrl Control'\r\n"
           b"\tVerInfoCC.VerInfoCtrl.2 = s 'VerInfoCtrl Control'\r\n}\r\n")
    check("parse_rgs_classes finds the co-class",
          parse_rgs_classes(rgs) == {("VerInfoCC", "VerInfoCtrl")})
    check("parse_rgs_classes ignores a non-registration file",
          parse_rgs_classes(b"VerInfoCC VerInfoCtrl") == set())

    # 3. reloc-masked digest: a relocated pointer masks, a constant stays.
    def section(val):
        # mov.l @(4,PC),r1 loads the literal at offsets 4-7 (word 1 is filler;
        # 0x1004 = ((0x1000+4)&~3) + 0*4), then rts + delay slot.
        return [0xD100, 0x0009, val & 0xFFFF, (val >> 16) & 0xFFFF, 0x000B, 0x0009]

    def blob_of(words):
        return struct.pack("<%dH" % len(words), *words)

    lo, hi = 0x1000, 0x2000
    da = digest_words(section(0x1800), 0x1000, blob_of(section(0x1800)), (lo, hi))
    db = digest_words(section(0x1900), 0x1000, blob_of(section(0x1900)), (lo, hi))
    check("relocated pool pointer hashes equal (masked)", da == db)
    ca = digest_words(section(0x12345678), 0x1000, blob_of(section(0x12345678)), (lo, hi))
    cb = digest_words(section(0x9ABCDEF0), 0x1000, blob_of(section(0x9ABCDEF0)), (lo, hi))
    check("a changed constant hashes different (kept)", ca != cb)
    # import-slot masking: a value that equals an IAT slot VA masks too.
    slot = 0x1800
    ia = digest_words(section(slot), 0x1000, blob_of(section(slot)), (lo, hi), frozenset([slot]))
    ib = digest_words(section(0x1900), 0x1000, blob_of(section(0x1900)), (lo, hi), frozenset([slot]))
    check("import-slot pool value masks to the same hash", ia == ib)

    # 4. a real synthetic CE ROM: census, module digest, equality.
    data, layout = cerom.build_synthetic_rom()
    segments, _dups = cerom.find_segments(data, layout["image_start"])
    check("synthetic ROM parses as one segment with two modules",
          len(segments) == 1 and segments[0].hdr["nummods"] == 2)
    names = [m["name"] for m in segments[0].modules()]
    check("synthetic ROM modules are NK.EXE and NAVI.EXE",
          names == ["NK.EXE", "NAVI.EXE"])

    tmp = Path(layout.get("_tmp", "/tmp/rom_atlas_selftest.img"))
    import tempfile
    with tempfile.TemporaryDirectory(prefix="rom-atlas-") as td:
        img = Path(td) / "synth.img"
        img.write_bytes(data)
        rom = rom_side(str(img), do_hash=True)
        navi = {m["name"]: m for m in rom["segments"]["A"]["modules"]}["NAVI.EXE"]
        check("synthetic NAVI.EXE has a reloc-masked code hash",
              navi["code_sha"] and len(navi["code_sha"]) == 64)
        eq = equal_modules(rom, rom, "A")
        check("a ROM compared with itself has every executable module equal",
              eq["equal"] == ["NAVI.EXE"] and not eq["different"]
              and eq["nocode"] == ["NK.EXE"])

        # negative control: change one code byte, the digest must change.
        mutated = bytearray(data)
        sec = next(s for s in list(segments[0].o32(segments[0].module("NAVI.EXE")))
                   if s["flags"] & cerom.MEM_EXECUTE)
        off = segments[0].va2file(sec["dataptr"])
        mutated[off] ^= 0xFF
        mimg = Path(td) / "mut.img"
        mimg.write_bytes(bytes(mutated))
        rom2 = rom_side(str(mimg), do_hash=True)
        navi2 = {m["name"]: m for m in rom2["segments"]["A"]["modules"]}["NAVI.EXE"]
        check("a one-byte code change changes the digest",
              navi2["code_sha"] != navi["code_sha"])
        eq2 = equal_modules(rom, rom2, "A")
        check("the mutated ROM differs in exactly NAVI.EXE",
              eq2["different"] == ["NAVI.EXE"] and eq2["equal"] == []
              and eq2["nocode"] == ["NK.EXE"])

    print("failures: %d" % len(failures))
    return 1 if failures else 0


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def _built_command(heads, fulls):
    """The reproducer line, with the paths the caller gave (not a repo copy)."""
    parts = ["python3 tools/rom_atlas.py atlas"]
    for key in sorted(heads):
        parts.append("--head %s=%s" % (key, heads[key]))
    for key in sorted(fulls):
        parts.append("--full %s=%s" % (key, fulls[key]))
    return " \\\n  ".join(parts)


def parse_pairs(items):
    out = {}
    for item in items or []:
        if "=" not in item:
            raise SystemExit("rom_atlas: --head/--full needs KEY=PATH, got %r" % item)
        key, path = item.split("=", 1)
        out[key.strip()] = path.strip()
    return out


def cmd_atlas(args):
    heads = parse_pairs(args.head)
    fulls = parse_pairs(args.full)
    keys = args.only or sorted(set(heads) | set(fulls))
    if not keys:
        raise SystemExit("rom_atlas: atlas needs at least one --head KEY=PATH")
    images = {}
    provenance = {}
    for key in keys:
        if key not in heads:
            raise SystemExit("rom_atlas: no --head for %s" % key)
        p = Path(heads[key])
        if not p.is_file():
            raise SystemExit("rom_atlas: %s missing (%s)" % (key, p))
        size = p.stat().st_size
        image = {
            "image": {
                "path": str(p),
                "size": size,
                "sha256": sha256_of(p),
                "truncated": size < (1 << 33),
            },
            "rom": rom_side(str(p), do_hash=True),
            "data": data_side(fulls[key]) if key in fulls else data_side(""),
        }
        images[key] = image
        if key in fulls:
            provenance[key] = "`%s` sha256 `%s`" % (fulls[key], sha256_of(fulls[key]))
        else:
            provenance[key] = "not supplied (head only; FAT tree not walked)"
    md = render_atlas(images, command=args.reproducer or _built_command(heads, fulls),
                      provenance=provenance)
    if args.output:
        Path(args.output).write_text(md + "\n")
        print("wrote %s (%d images)" % (args.output, len(images)))
    else:
        print(md)
    if args.json:
        Path(args.json).write_text(json.dumps(images, indent=1) + "\n")
        print("wrote %s" % args.json, file=sys.stderr)
    return 0


def cmd_equal(args):
    heads = parse_pairs(args.head)
    if len(heads) != 2:
        raise SystemExit("rom_atlas: equal needs exactly two --head KEY=PATH")
    (ka, pa), (kb, pb) = list(heads.items())
    rom_a = rom_side(pa, do_hash=True)
    rom_b = rom_side(pb, do_hash=True)
    rom_keys = [args.rom] if args.rom else list(ROM_KEYS)
    report = {}
    for rk in rom_keys:
        report[rk] = equal_modules(rom_a, rom_b, rk)
    if args.json:
        Path(args.json).write_text(json.dumps({"%s:%s" % (ka, kb): report}, indent=1) + "\n")
        print("wrote %s" % args.json, file=sys.stderr)
    for rk in rom_keys:
        r = report[rk]
        print("%s vs %s, ROM %s: %d/%d modules, common %d: equal %d, different %d, unreadable %d"
              % (ka, kb, rk, r["count_a"], r["count_b"], r["common"],
                 len(r["equal"]), len(r["different"]), len(r["unreadable"])))
        print("  equal: %s" % (", ".join(r["equal"]) or "-"))
        print("  only %s: %s" % (ka, ", ".join(r["only_a"]) or "-"))
        print("  only %s: %s" % (kb, ", ".join(r["only_b"]) or "-"))
        if r["unreadable"]:
            print("  unreadable (compressed exec): %s" % ", ".join(r["unreadable"]))
        if rk == "A" and args.negative_bcs:
            # The control for C-6281: B and C are equal, so A is not trivially so.
            for ctrl in ("B", "C"):
                cr = equal_modules(rom_a, rom_b, ctrl)
                if cr["different"] or cr["only_a"] or cr["only_b"]:
                    print("  NEGATIVE CONTROL FAILED: ROM %s is not fully equal" % ctrl)
                    return 1
                print("  control ROM %s: %d/%d equal (as expected)" % (ctrl, len(cr["equal"]), cr["common"]))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true", help="run the built-in tests")
    sub = ap.add_subparsers(dest="command")
    a = sub.add_parser("atlas", help="print the module+data atlas")
    a.add_argument("--head", action="append", metavar="KEY=PATH",
                   help="a 256 MiB head for image KEY (repeatable)")
    a.add_argument("--full", action="append", metavar="KEY=PATH",
                   help="a full image for KEY (enables the FAT/TFAT data side)")
    a.add_argument("--only", nargs="+", metavar="KEY", help="limit to these keys")
    a.add_argument("--json", metavar="PATH", help="write the whole atlas as JSON")
    a.add_argument("-o", "--output", metavar="PATH", help="write Markdown here")
    a.add_argument("--reproducer", dest="reproducer", metavar="TEXT",
                   help="the reproducer command to quote in the header (default: built from --head/--full)")
    a.set_defaults(func=cmd_atlas)
    e = sub.add_parser("equal", help="compare two images module by module")
    e.add_argument("--head", action="append", metavar="KEY=PATH", required=True)
    e.add_argument("--rom", choices=ROM_KEYS, help="only this ROM (default A/B/C)")
    e.add_argument("--negative-bcs", action="store_true",
                   help="also assert B and C are fully equal (the C-6281 control)")
    e.add_argument("--json", metavar="PATH")
    e.set_defaults(func=cmd_equal)
    return ap


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "command", None):
        ap.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
