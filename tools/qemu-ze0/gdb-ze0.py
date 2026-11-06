#!/usr/bin/env python3
"""Print the Windows CE thread list and the module/section behind each PC.

One file, two entry points:

* **under QEMU's gdbstub**, sourced by gdb::

      gdb-multiarch -q -ex 'target remote 127.0.0.1:1234' \\
          -ex 'source tools/qemu-ze0/gdb-ze0.py'

  gdb detects the ``.py`` suffix and sources the file as Python.  It reads the
  memmap JSON written by ``tools/cerom.py IMG memmap`` from the convenience
  variable ``$ze0_memmap``, else from ``$ZE0_MEMMAP``, else from
  ``./memmap.json``; prints one line per CE thread (name, PC, module, section,
  offset); registers the ``ze0-threads`` command so the report can be repeated
  without re-sourcing; and restores the thread gdb had selected.

* **standalone**, for the selftest and for checking PCs by hand::

      python3 tools/qemu-ze0/gdb-ze0.py --selftest
      python3 tools/qemu-ze0/gdb-ze0.py --memmap WORK/memmap.json --pc 0x8803d266

Without a memmap the thread list still prints the raw PCs and a hint; the
mapping half needs only the JSON, never the image, so ``--selftest`` runs
without gdb, QEMU or vendor data.

SH-4 address handling: gdb reports the PC in the segment the CPU is executing
in, while ``cerom.py memmap`` lists P1 VAs (``0x8xxxxxxx``).  A PC in P2
(``0xA0000000``-``0xBFFFFFFF``), P3 (``0xC0000000``-``0xDFFFFFFF``) or in the low
P0 window is retried through its cached P1 alias, so ``0x0cae1234`` and
``0xc0ae1234`` resolve to the same section as ``0x8cae1234``.  Sections are
matched by ``max(vsize, psize)``; when sections overlap, the smallest extent
wins.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile

from dataclasses import dataclass

try:  # gdb is absent outside gdb; --selftest must not need it
    import gdb  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - exercised by every standalone run
    gdb = None

DEFAULT_MEMMAP = "memmap.json"
P1_BASE = 0x80000000
P2_BASE = 0xA0000000
P2_MASK = 0x1FFFFFFF
P3_BASE = 0xE0000000


# --------------------------------------------------------------------------
# memmap -> sections
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Section:
    """One ``o32`` section of one module, as ``cerom.py memmap`` lists it."""

    module: str
    name: str
    va: int
    extent: int
    rwx: str = ""
    compressed: bool = False
    psize: int = 0


@dataclass(frozen=True)
class ThreadRow:
    """One CE thread as printed: gdb number, label, program counter."""

    num: int
    label: str
    pc: int | None


def _as_int(value, default=0) -> int:
    """Parse ``0x...`` strings, ints and ``None`` from the memmap JSON."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    return int(str(value), 0)


def parse_memmap(document) -> list[Section]:
    """Flatten a ``cerom.py memmap`` document (dict or path) into sections.

    ``extent`` is ``max(vsize, psize)`` so a BSS tail (``psize == 0``) is still
    resolvable; sections with no extent at all are skipped.  Overlapping
    sections are kept as they are and resolved by :func:`resolve`.
    """
    if isinstance(document, (str, os.PathLike)):
        with open(document, "r", encoding="utf-8") as handle:
            document = json.load(handle)

    sections: list[Section] = []
    for segment in document.get("segments", []):
        for module in segment.get("modules", []):
            module_name = str(module.get("module") or module.get("name") or "?")
            for entry in module.get("sections", []):
                if entry.get("va") is None:
                    continue
                psize = _as_int(entry.get("size"))
                vsize = _as_int(entry.get("vsize"))
                extent = max(vsize, psize)
                if extent <= 0:
                    continue
                sections.append(
                    Section(
                        module=module_name,
                        name=str(entry.get("name") or "?"),
                        va=_as_int(entry.get("va")),
                        extent=extent,
                        rwx=str(entry.get("rwx") or ""),
                        compressed=bool(entry.get("compressed")),
                        psize=psize,
                    )
                )
    return sections


def candidate_vas(pc: int):
    """Yield the PC and its cached P1 alias, most direct first."""
    yield pc
    if pc >= P3_BASE:
        return
    if pc >= P2_BASE:
        alias = (pc & P2_MASK) | P1_BASE
        if alias != pc:
            yield alias
    elif pc < P1_BASE:
        alias = pc | P1_BASE
        if alias != pc:
            yield alias


def resolve(sections, pc: int):
    """Return ``(section, matched_va)`` for *pc*, or ``None``.

    The first candidate address that any section covers decides the segment;
    within one address the smallest extent wins, so a small nested section
    beats the module-sized one around it.
    """
    for candidate in candidate_vas(pc):
        hits = [s for s in sections if s.va <= candidate < s.va + s.extent]
        if hits:
            return min(hits, key=lambda s: (s.extent, -s.va)), candidate
    return None


def format_pc(pc: int | None, sections=None) -> str:
    """``0x8ce01010  NK.EXE/sec0+0x10  [r-x]`` (or why it cannot be mapped)."""
    if pc is None:
        return "?  (registers unreadable)"
    text = "0x%08x" % pc
    if not sections:
        return "%s  (no memmap: set $ze0_memmap or pass --memmap)" % text
    hit = resolve(sections, pc)
    if hit is None:
        place = "P4/P3 register space" if pc >= P3_BASE else "outside every mapped module"
        return "%s  (%s)" % (text, place)
    section, matched = hit
    offset = matched - section.va
    notes = []
    if section.rwx:
        notes.append(section.rwx)
    if section.compressed:
        notes.append("compressed")
    if section.psize == 0:
        notes.append("bss")
    suffix = "  [%s]" % ",".join(notes) if notes else ""
    alias = "" if matched == pc else " (via 0x%08x)" % matched
    return "%s  %s/%s+0x%x%s%s" % (
        text,
        section.module,
        section.name,
        offset,
        alias,
        suffix,
    )


# --------------------------------------------------------------------------
# Thread list
# --------------------------------------------------------------------------


def _label(thread) -> str:
    """Thread name, else the ptid, else ``thread N`` (gdb raises on unnamed)."""
    try:
        name = thread.name
    except Exception:
        name = None
    if name:
        return str(name)
    try:
        return str(thread.ptid)
    except Exception:
        return "thread %d" % int(thread.num)


def collect_threads(inferior, frame_pc, current=None) -> list[ThreadRow]:
    """Build rows from a gdb-like inferior and re-select *current* at the end.

    ``frame_pc()`` returns the program counter of the thread that was just
    switched to; a thread whose registers cannot be read (running, dead) gets
    ``pc=None`` instead of aborting the whole report.
    """
    rows: list[ThreadRow] = []
    for thread in inferior.threads():
        try:
            thread.switch()
        except Exception:
            pass
        try:
            pc = frame_pc()
        except Exception:
            pc = None
        rows.append(ThreadRow(num=int(thread.num), label=_label(thread), pc=pc))
    if current is not None:
        try:
            current.switch()
        except Exception:
            pass
    return rows


def format_threads(rows, sections=None, current_num=None) -> list[str]:
    """Render the thread list; returns lines so the selftest can pin them."""
    lines = ["== CE threads (%d) ==" % len(rows)]
    for row in rows:
        mark = "*" if current_num is not None and row.num == current_num else " "
        lines.append(
            "%s %2d  %-14s  pc=%s"
            % (mark, row.num, row.label, format_pc(row.pc, sections))
        )
    return lines


# --------------------------------------------------------------------------
# gdb entry point (skipped when gdb is absent)
# --------------------------------------------------------------------------


def _gdb_memmap_path():
    """``$ze0_memmap``, else ``$ZE0_MEMMAP``, else ``./memmap.json``."""
    path = None
    try:
        value = gdb.convenience_variable("ze0_memmap")
        if value is not None:
            path = value.string()
    except Exception:
        path = None
    if not path:
        path = os.environ.get("ZE0_MEMMAP") or None
    if not path and os.path.exists(DEFAULT_MEMMAP):
        path = DEFAULT_MEMMAP
    return path


def gdb_report() -> None:
    """Print the thread list once; called on source and by ``ze0-threads``."""
    path = _gdb_memmap_path()
    sections = []
    if path:
        try:
            sections = parse_memmap(path)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            print("gdb-ze0: cannot read %s: %s" % (path, exc))
            path = None
    else:
        print('gdb-ze0: no memmap; set $ze0_memmap = "/path/memmap.json"')

    try:
        current = gdb.selected_thread()
    except Exception:
        current = None

    try:
        rows = collect_threads(
            gdb.selected_inferior(),
            lambda: int(gdb.selected_frame().pc()),
            current,
        )
    except Exception as exc:
        print("gdb-ze0: cannot walk threads: %s" % exc)
        print("gdb-ze0: is the target running? press Ctrl-C, then 'ze0-threads'")
        return

    current_num = None
    if current is not None:
        try:
            current_num = int(current.num)
        except Exception:
            current_num = None
    for line in format_threads(rows, sections, current_num):
        print(line)
    if path:
        print("memmap: %s (%d section(s))" % (path, len(sections)))


if gdb is not None:  # sourced by gdb

    class Ze0Threads(gdb.Command):
        """Print the CE thread list with PC -> module/section (memmap JSON)."""

        def __init__(self):
            super().__init__("ze0-threads", gdb.COMMAND_USER)

        def invoke(self, argument, from_tty):
            gdb_report()

    Ze0Threads()
    gdb_report()


# --------------------------------------------------------------------------
# Standalone entry point and selftest (no gdb, no QEMU)
# --------------------------------------------------------------------------


SELFTEST_MEMMAP = {
    "schema": "osm2leaf.cerom.memmap/v1",
    "generator": "tools/cerom.py memmap",
    "segments": [
        {
            "phys_base": "0x8ce00000",
            "modules": [
                {
                    "module": "NK.EXE",
                    "name": "NK.EXE",
                    "vbase": "0x8ce00000",
                    "sections": [
                        {
                            "name": "sec0",
                            "va": "0x8ce00000",
                            "file_offset": 0,
                            "size": 0x400,
                            "vsize": 0x400,
                            "characteristics": "0x60000020",
                            "compressed": False,
                            "rwx": "r-x",
                        },
                        {
                            "name": "sec1",
                            "va": "0x8ce01000",
                            "file_offset": 0x400,
                            "size": 0x100,
                            "vsize": 0x800,
                            "characteristics": "0xc0000040",
                            "compressed": False,
                            "rwx": "rw-",
                        },
                    ],
                },
                {
                    "module": "NAVI.EXE",
                    "name": "NAVI.EXE",
                    "vbase": "0x8d000000",
                    "sections": [
                        {
                            "name": "sec0",
                            "va": "0x8d000000",
                            "file_offset": 0,
                            "size": 0x200,
                            "vsize": 0x200,
                            "characteristics": "0x60000020",
                            "compressed": False,
                            "rwx": "r-x",
                        },
                        {
                            "name": "sec1",
                            "va": "0x8d002000",
                            "file_offset": 0x200,
                            "size": 0x40,
                            "vsize": 0x400,
                            "characteristics": "0xc0002040",
                            "compressed": True,
                            "rwx": "rw-",
                        },
                        {
                            "name": "sec2",
                            "va": "0x8d003000",
                            "file_offset": None,
                            "size": 0,
                            "vsize": 0x100,
                            "characteristics": "0xc0000080",
                            "compressed": False,
                            "rwx": "rw-",
                        },
                    ],
                },
                {
                    "module": "OVER.EXE",
                    "name": "OVER.EXE",
                    "vbase": "0x8ce01000",
                    "sections": [
                        {
                            "name": "sec0",
                            "va": "0x8ce01010",
                            "file_offset": 0,
                            "size": 0x10,
                            "vsize": 0x10,
                            "characteristics": "0xc0000040",
                            "compressed": False,
                            "rwx": "rw-",
                        }
                    ],
                },
            ],
        }
    ],
}


class _FakeThread:
    """The parts of a ``gdb.Thread`` that :func:`collect_threads` touches."""

    current = None

    def __init__(self, num, ptid, name, pc, readable=True):
        self.num = num
        self.ptid = ptid
        self.name = name
        self._pc = pc
        self.readable = readable
        self.switches = 0

    def switch(self):
        self.switches += 1
        _FakeThread.current = self

    def pc(self):
        if not self.readable:
            raise RuntimeError("thread is running")
        return self._pc


class _FakeInferior:
    def __init__(self, threads):
        self._threads = list(threads)

    def threads(self):
        return tuple(self._threads)


def selftest(argv=None) -> int:
    """Synthetic memmap + fake threads: the whole mapping path without gdb."""
    checks = 0
    failures = 0

    def check(name, got, want) -> None:
        nonlocal checks, failures
        checks += 1
        if got == want:
            print("  ok   %s" % name)
        else:
            failures += 1
            print("  FAIL %s: got %r, want %r" % (name, got, want))

    sections = parse_memmap(SELFTEST_MEMMAP)
    check("section count", len(sections), 6)
    check(
        "module/section order",
        [(s.module, s.name) for s in sections],
        [
            ("NK.EXE", "sec0"),
            ("NK.EXE", "sec1"),
            ("NAVI.EXE", "sec0"),
            ("NAVI.EXE", "sec1"),
            ("NAVI.EXE", "sec2"),
            ("OVER.EXE", "sec0"),
        ],
    )
    check(
        "extent is max(vsize, psize)",
        [(s.extent, s.psize) for s in sections],
        [(0x400, 0x400), (0x800, 0x100), (0x200, 0x200), (0x400, 0x40), (0x100, 0), (0x10, 0x10)],
    )

    check("pc at a section start", format_pc(0x8CE00004, sections),
          "0x8ce00004  NK.EXE/sec0+0x4  [r-x]")
    check("pc in a bss tail", format_pc(0x8CE01100, sections),
          "0x8ce01100  NK.EXE/sec1+0x100  [rw-]")
    check("pc in a compressed section", format_pc(0x8D002010, sections),
          "0x8d002010  NAVI.EXE/sec1+0x10  [rw-,compressed]")
    check("pc in a psize=0 section", format_pc(0x8D0030F0, sections),
          "0x8d0030f0  NAVI.EXE/sec2+0xf0  [rw-,bss]")
    check("overlap prefers the tightest section", format_pc(0x8CE01014, sections),
          "0x8ce01014  OVER.EXE/sec0+0x4  [rw-]")
    check("last byte of a section", format_pc(0x8CE003FF, sections),
          "0x8ce003ff  NK.EXE/sec0+0x3ff  [r-x]")
    check("first byte past a section", format_pc(0x8CE01800, sections),
          "0x8ce01800  (outside every mapped module)")
    check("P2 pc resolves through its P1 alias", format_pc(0x0CE00004, sections),
          "0x0ce00004  NK.EXE/sec0+0x4 (via 0x8ce00004)  [r-x]")
    check("P3 pc resolves through its P1 alias", format_pc(0xCCE00004, sections),
          "0xcce00004  NK.EXE/sec0+0x4 (via 0x8ce00004)  [r-x]")
    check("P4 register pc stays unmapped", format_pc(0xFFE46000, sections),
          "0xffe46000  (P4/P3 register space)")
    check("no memmap", format_pc(0x8803D266, []),
          "0x8803d266  (no memmap: set $ze0_memmap or pass --memmap)")
    check("unreadable pc", format_pc(None, sections), "?  (registers unreadable)")

    check("candidate_vas P2", list(candidate_vas(0x0CE00004)), [0x0CE00004, 0x8CE00004])
    check("candidate_vas P3", list(candidate_vas(0xCCE00004)), [0xCCE00004, 0x8CE00004])
    check("candidate_vas P4", list(candidate_vas(0xFFE46000)), [0xFFE46000])
    check("candidate_vas P1", list(candidate_vas(0x8CE00004)), [0x8CE00004])

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "memmap.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(SELFTEST_MEMMAP, handle)
        check("parse_memmap reads a file", len(parse_memmap(path)), 6)

    first = _FakeThread(1, "Thread 1", "ntdll", 0x8CE00004)
    second = _FakeThread(2, "LWP 2", None, 0x00005B90)
    broken = _FakeThread(3, "Thread 3", "stuck", 0, readable=False)
    inferior = _FakeInferior([first, second, broken])

    rows = collect_threads(inferior, lambda: _FakeThread.current.pc(), current=first)
    check(
        "collect_threads rows",
        [(r.num, r.label, r.pc) for r in rows],
        [(1, "ntdll", 0x8CE00004), (2, "LWP 2", 0x5B90), (3, "stuck", None)],
    )
    check("unnamed thread falls back to the ptid", rows[1].label, "LWP 2")
    check("unreadable registers become pc=None", rows[2].pc, None)
    check("restores the selected thread", _FakeThread.current is first, True)

    lines = format_threads(rows, sections, current_num=1)
    check("thread list header", lines[0], "== CE threads (3) ==")
    check("current thread is marked", lines[1],
          "*  1  ntdll           pc=0x8ce00004  NK.EXE/sec0+0x4  [r-x]")
    check("P0 pc is reported unmapped", lines[2],
          "   2  LWP 2           pc=0x00005b90  (outside every mapped module)")
    check("short pc is zero-padded", lines[3],
          "   3  stuck           pc=?  (registers unreadable)")
    check("no mark without a current thread",
          format_threads(rows, sections)[0], "== CE threads (3) ==")
    check("no mark without a current thread (row)",
          format_threads(rows, sections)[1].startswith("   1  ntdll"), True)

    print("checks: %d, failures: %d" % (checks, failures))
    print("selftest: OK" if failures == 0 else "selftest: FAILED")
    return 0 if failures == 0 else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        epilog="Under gdb, source this file instead of running it; see the "
        "module docstring.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run the synthetic memmap/thread checks without gdb",
    )
    parser.add_argument(
        "--memmap",
        metavar="FILE",
        help="cerom.py memmap JSON (VA -> module/section)",
    )
    parser.add_argument(
        "--pc",
        action="append",
        default=[],
        metavar="HEX",
        help="print the module/section for this PC (repeatable, needs --memmap)",
    )
    args = parser.parse_args(argv)

    if args.selftest:
        return selftest()

    if not args.memmap:
        parser.error("--memmap FILE is required unless --selftest is given")
    try:
        sections = parse_memmap(args.memmap)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("gdb-ze0: cannot read %s: %s" % (args.memmap, exc), file=sys.stderr)
        return 1

    modules = len({s.module for s in sections})
    print("memmap: %s (%d section(s) in %d module(s))" % (args.memmap, len(sections), modules))
    if not args.pc:
        return 0
    for value in args.pc:
        try:
            pc = int(value, 0)
        except ValueError:
            print("gdb-ze0: not a number: %r" % value, file=sys.stderr)
            return 2
        print(format_pc(pc, sections))
    return 0


if gdb is None and __name__ == "__main__":
    raise SystemExit(main())
