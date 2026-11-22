#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""ce_module.py - one CE ROMHDR -> section -> bytes path for the L3 tools (M1.47).

The same ROM-to-code step used to be written in each ``*_l3.py`` tool, and the
copies drifted: some skipped a compressed section (``blob = None``) while only
one of them decoded it through the kernel's own routine (H51).  This module is
the single owner of that step.

Two shapes, because the call sites want different things:

``module_sections(image, image_start, module)``
    the rich view, one 8-tuple per section::

        (index, va, vsize, psize, compressed, exec, init_len, blob)

    ``va`` is the section ``realaddr``, ``init_len`` the number of stored
    bytes the loader writes before the zero BSS (``psize`` for a plain
    section, the kernel decoder's ``r0`` for a compressed one).  ``blob`` is
    what the loader maps: ``vsize`` bytes (init + zero BSS).  A VA at or past
    ``init_len`` is therefore BSS, never code.

    A compressed section is **decoded through** ``nk_decomp`` (the kernel's
    own routine, H51), never skipped.  Eager decoding is scoped: it is the
    default only for the image starts the four call sites use
    (:data:`EAGER_STARTS`), because build B of the 2014/2016 cards fails in
    the decoder (C-6509).  For any other image start a compressed section is
    returned lazy — ``init_len is None`` and ``blob is None`` — unless the
    caller passes ``decode=True``.  ``decode=False`` forces lazy everywhere.

``legacy_sections(image, image_start, module)``
    the cheap 3-tuple view ``(o32 record, compressed, blob_or_None)`` the old
    ``point_walk_l3.module_sections`` returned.  It never decodes; a
    compressed section is ``(sec, True, None)``.  Kept for the tools that only
    walk section records (their own decode, if any, is unchanged).

Both ``text_section`` (the ``navi_text`` step) and ``find_section`` (the
``chunk_decoder_l3`` lookup loop) read only section records, so neither
decodes.

Out of scope for this helper (see EXP-2026-11-22-M1.47-ce-module):
``vcard_l3.py`` (a loader total) and ``va_class.py`` (a classifier) keep their
own; ``ce_strfind.py`` has a same-named but different function over
``cecompress`` statuses, not this ROMHDR path.

Usage::

  ce_module.py --selftest
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import cerom  # noqa: E402

IMAGE_START_A = 0x200200
IMAGE_START_B = 0x3E00200
#: Image starts whose compressed sections the four M1.47 call sites decode
#: eagerly.  Everything else stays lazy: build B of the EU2014/2016 cards
#: fails in nk_decomp (C-6509), so an unconditional eager decode would break
#: those paths.
EAGER_STARTS = frozenset((IMAGE_START_A, IMAGE_START_B))
EXEC = 0x20000000
IMAGE_CHUNK = 128 << 20


def load_image(path: str) -> bytes:
    """The first 128 MiB of a card image (every L3 tool's working window)."""
    with open(path, "rb") as fh:
        return fh.read(IMAGE_CHUNK)


def module_sections(image: bytes, image_start: int, module: str,
                    decode: bool | None = None):
    """The rich per-section view; see the module docstring.

    ``decode=None`` decides by :data:`EAGER_STARTS`; ``True`` forces a decode
    (raising if the kernel routine refuses, never ``None``); ``False`` forces
    the lazy shape.
    """
    rom = cerom.CERom(image, image_start)
    out = []
    for index, sec in enumerate(rom.o32(rom.module(module))):
        comp = bool(sec["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        ex = bool(sec["flags"] & EXEC)
        if not comp:
            off = rom.va2file(sec["dataptr"])
            blob = bytes(image[off:off + sec["psize"]])
            init_len = sec["psize"]
        else:
            eager = decode if decode is not None else image_start in EAGER_STARTS
            if not eager:
                init_len, blob = None, None
            else:
                import nk_decomp
                blob = nk_decomp.section_bytes(image, module, index, image_start)
                init_len = len(nk_decomp.section_init(image, module, index,
                                                     image_start))
        out.append((index, sec["realaddr"], sec["vsize"], sec["psize"],
                    comp, ex, init_len, blob))
    return out


def legacy_sections(image: bytes, image_start: int, module: str):
    """``[(o32 record, compressed, blob_or_None)]`` without decoding (M1.47).

    This is the shape ``point_walk_l3.module_sections`` returned and that
    ``mapcode_l3``'s synthetic ``fake_layout`` mirrors: a compressed section
    is ``(sec, True, None)``.
    """
    rom = cerom.CERom(image, image_start)
    return _legacy(rom, image, module)


def legacy_module(image: bytes, image_start: int, module: str):
    """``(rom, legacy_sections)`` — the exact pair ``point_walk_l3`` returned."""
    rom = cerom.CERom(image, image_start)
    return rom, _legacy(rom, image, module)


def _legacy(rom, image: bytes, module: str):
    out = []
    for sec in rom.o32(rom.module(module)):
        comp = bool(sec["flags"] & cerom.IMAGE_SCN_COMPRESSED)
        blob = None
        if not comp:
            off = rom.va2file(sec["dataptr"])
            blob = bytes(image[off:off + sec["psize"]])
        out.append((sec, comp, blob))
    return out


def text_section(image: bytes, image_start: int, module: str = "Navi.exe"):
    """``(va, bytes)`` of the module's first uncompressed executable section.

    The ``navi_text`` step: the firmware text the PySh4 harness maps ``rx``.
    Reads the section record only (``psize`` bytes), so no decode.
    """
    rom = cerom.CERom(image, image_start)
    for sec in rom.o32(rom.module(module)):
        if (sec["flags"] & cerom.IMAGE_SCN_COMPRESSED
                or not sec["flags"] & EXEC):
            continue
        off = rom.va2file(sec["dataptr"])
        return sec["realaddr"], bytes(image[off:off + sec["psize"]])
    raise SystemExit("%s has no uncompressed executable section" % module)


def find_section(image: bytes, module: str, va: int, image_start: int):
    """``(index, o32 record, file offset)`` of the section covering *va*.

    ``None`` when no section of *module* covers the VA.  This is the
    ``chunk_decoder_l3`` lookup loop moved here; it reads records, not bytes.
    """
    rom = cerom.CERom(image, image_start)
    for index, sec in enumerate(rom.o32(rom.module(module))):
        if sec["realaddr"] <= va < sec["realaddr"] + sec["vsize"]:
            return index, sec, rom.va2file(sec["dataptr"])
    return None


# ---------------------------------------------------------------------------
# selftest


def selftest() -> int:
    import struct
    import tempfile

    import nk_decomp

    fails = 0

    def check(name, cond):
        nonlocal fails
        print("%-58s %s" % (name, "ok" if cond else "FAIL"))
        fails += not cond

    # The synthetic CE ROM from cerom: NAVI.EXE holds an uncompressed code
    # section (index 0) and a compressed data section (index 1).  No vendor
    # bytes; the decoder is faked below so no firmware is needed.
    image, layout = cerom.build_synthetic_rom()
    start = layout["image_start"]
    module = "NAVI.EXE"
    rom = cerom.CERom(image, start)
    secs = list(rom.o32(rom.module(module)))
    code, data = secs[0], secs[1]

    # --- plain section ------------------------------------------------------
    got = module_sections(image, start, module, decode=False)
    plain = got[0]
    check("rich tuple has 8 fields",
          len(plain) == 8)
    check("plain code section is not compressed", plain[4] is False)
    check("plain code section is executable", plain[5] is True)
    check("plain section init_len == psize", plain[6] == code["psize"])
    check("plain section blob is psize bytes", len(plain[7]) == code["psize"])

    # --- compressed section: decoded through nk_decomp, never skipped ------
    calls = {"bytes": 0, "init": 0}
    real_bytes, real_init = nk_decomp.section_bytes, nk_decomp.section_init
    fake_init = b"\x11" * 0x10                      # 0x10 stored bytes
    fake_blob = fake_init + bytes(data["vsize"] - len(fake_init))

    def fake_section_bytes(image_, module_, index_, image_start_=None, cache=True):
        calls["bytes"] += 1
        return fake_blob

    def fake_section_init(image_, module_, index_, image_start_=None, cache=True):
        calls["init"] += 1
        return fake_init

    nk_decomp.section_bytes = fake_section_bytes
    nk_decomp.section_init = fake_section_init
    try:
        # lazy: an image start outside EAGER_STARTS is not decoded by default
        lazy = module_sections(image, start, module)
        check("outside EAGER_STARTS a compressed section stays lazy (no call)",
              lazy[1][6] is None and lazy[1][7] is None and calls["bytes"] == 0)
        check("lazy compressed section is not silently None-decoded",
              lazy[1][4] is True)

        # explicit decode=True: the kernel routine is called and its bytes used
        rich = module_sections(image, start, module, decode=True)
        check("decode=True decodes a compressed section, not None",
              rich[1][7] == fake_blob and calls["bytes"] == 1)
        check("decode=True reports the kernel r0 as init_len",
              rich[1][6] == len(fake_init))
        check("a VA in BSS is reported with init length, not as code",
              rich[1][6] < rich[1][2] and rich[1][5] is False
              and rich[1][7][rich[1][6]:] == bytes(rich[1][2] - rich[1][6]))

        # default eager when the image start is in EAGER_STARTS
        saved = EAGER_STARTS
        globals()["EAGER_STARTS"] = frozenset(saved | {start})
        try:
            calls["bytes"] = 0
            eager = module_sections(image, start, module)
            check("inside EAGER_STARTS the default decodes the section",
                  eager[1][7] == fake_blob and calls["bytes"] == 1)
        finally:
            globals()["EAGER_STARTS"] = saved

        # a decoder failure must raise, not hand back None
        def boom(*a, **k):
            raise nk_decomp.DecompError("kernel refused")

        nk_decomp.section_bytes = boom
        try:
            module_sections(image, start, module, decode=True)
            check("a failed decode raises (never a silent None)", False)
        except nk_decomp.DecompError:
            check("a failed decode raises (never a silent None)", True)
    finally:
        nk_decomp.section_bytes, nk_decomp.section_init = real_bytes, real_init

    # --- legacy shape: mapcode's fake_layout contract ---------------------
    legacy = legacy_sections(image, start, module)
    check("legacy_sections returns (sec, comp, blob) per section",
          all(len(entry) == 3 and isinstance(entry[1], bool)
              for entry in legacy))
    check("legacy plain entry carries its bytes",
          legacy[0][1] is False and legacy[0][2] == plain[7])
    check("legacy compressed entry is (sec, True, None)",
          legacy[1][1] is True and legacy[1][2] is None)
    # point_walk_l3.module_sections returned (rom, sections); keep that pair
    rom2, pair = legacy_module(image, start, module)
    check("legacy_module returns (CERom, legacy_sections)",
          isinstance(rom2, cerom.CERom) and pair == legacy)
    # the exact shape of mapcode_l3's fake_layout: two entries, one compressed
    fake_layout = [(code, False, bytes(code["psize"])),
                   (data, True, None)]
    check("fake_layout's 3-tuple entries match the legacy contract",
          all(len(e) == 3 and (e[2] is None) == e[1] for e in fake_layout))

    # --- text_section -----------------------------------------------------
    va, text = text_section(image, start, module)
    check("text_section returns the uncompressed exec section",
          va == code["realaddr"] and len(text) == code["psize"])

    # --- find_section -----------------------------------------------------
    hit = find_section(image, module, code["realaddr"] + 4, start)
    check("find_section finds the plain section by VA",
          hit is not None and hit[0] == 0 and hit[1]["realaddr"] == code["realaddr"])
    bss_va = data["realaddr"] + data["vsize"] - 1
    hit = find_section(image, module, bss_va, start)
    check("find_section covers a VA in the compressed section's BSS",
          hit is not None and hit[0] == 1)
    check("find_section returns None outside every section",
          find_section(image, module, 0x7FFFFFF0, start) is None)

    # --- load_image -------------------------------------------------------
    with tempfile.TemporaryDirectory(prefix="ce-module-selftest-") as tmp:
        path = os.path.join(tmp, "synth.img")
        with open(path, "wb") as fh:
            fh.write(image)
        check("load_image reads the image window",
              load_image(path) == image)

    print("selftest:", "OK" if not fails else "FAIL (%d)" % fails)
    return 0 if not fails else 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
