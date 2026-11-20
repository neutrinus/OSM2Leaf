#!/usr/bin/env python3
"""Virtual card: the firmware's own map-file code reads a card tree (M9.44).

``Navi.exe`` (build A, EU2011) is loaded into the pure-Python SH-4 engine with
its real code and its real initialised data.  Every import slot is bound to a
trampoline; the C library calls the map-file layer makes (``fopen``, ``fseek``,
``ftell``, ``fread``, ``fclose``, string and memory helpers, the ``OSMDLL``
allocator and locks) are served by small host models, and files come from an
extracted card tree (``--card-root``).  Nothing of the firmware is replaced:
its wrappers, its error handling and its parsers run as shipped.

The result of a run is a *verdict* (the firmware function's return value) and
a *read log*: every ``(file, offset, length)`` the firmware asked for.  Two
card trees that give the same verdict and the same log are indistinguishable
to that code path.

An import with no model stops the run with its name (``BLOCKED``) - a stop is a
result, never a pass.  ``OSM_TaskSend`` is not answered: the message is logged
and the call returns 0 (queued), which is what the sender sees in the unit.

No vendor byte is stored here: the tool reads the image and tree it is given.

Usage:
  vcard_l3.py --selftest
  vcard_l3.py boot    IMG256 --card-image CARD.img [--tree] [--json OUT]
  vcard_l3.py boot    IMG256 --card-root ROOT --flip DRSTR001.DAT@0x2f
  vcard_l3.py compare IMG256 --card-image A.img --other-root B_ROOT
  vcard_l3.py read    IMG256 --card-image CARD.img REFER001/POINT010.DAT --length 0x10000
  vcard_l3.py sweep   IMG256 --card-image CARD.img [--dir MAPAL001] [--bytes 0x4000]
  vcard_l3.py lookup  IMG256 --card-image CARD.img REFER001/POINT010.DAT MAPAL001/LEV3456R.DAT
  vcard_l3.py trace   IMG256 --card-image CARD.img 0x003fbed8 --args ctx,0,7 --ctx 124=4

A card is an extracted tree (--card-root) or a raw SD image (--card-image);
--hide / --replace / --flip / --truncate change one file of it for this run.

Exit codes: 0 ACCEPT (boot), identical (read, compare), all OK (sweep);
1 REJECT / different / not OK; 3 BLOCKED (no verdict); 2 usage or missing
input.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
for p in (HERE, HERE / "l3_harness"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from engine import RETURN_VA, EngineError, PySh4, StubReturn  # noqa: E402

IMAGE_A, IMAGE_B = 0x200200, 0x3E00200
TRAMP_VA = 0x7E000000            # one 4-byte cell per import slot
HEAP_VA, HEAP_SIZE = 0x30000000, 32 << 20
STACK_VA, STACK_SIZE = 0x7F000000, 1 << 20
FILE_VA = 0x6F000000             # FILE* values handed to the guest (never mapped)
M32 = 0xFFFFFFFF


class Blocked(Exception):
    """The run cannot continue; the message names what is missing."""


# --------------------------------------------------------------------------
# card tree
class MemorySource:
    """A card tree held in memory ({"DIR/FILE": bytes}); used by the selftest."""

    def __init__(self, files: dict[str, bytes]):
        self.files = {k.strip("/"): v for k, v in files.items()}

    def list_dir(self, rel: str = ""):
        from cardcheck import Entry
        rel = rel.strip("/")
        seen, out = set(), []
        for path, data in sorted(self.files.items()):
            if rel and not path.startswith(rel + "/"):
                continue
            rest = path[len(rel) + 1 if rel else 0:]
            name, _, more = rest.partition("/")
            if name and name not in seen:
                seen.add(name)
                out.append(Entry(name=name, is_dir=bool(more), size=0 if more else len(data),
                                 path=(rel + "/" + name).strip("/")))
        return out

    def read_range(self, rel: str, offset: int, length: int) -> bytes:
        return self.files[rel.strip("/")][offset:offset + length]


def open_source(root: str | None = None, image: str | None = None):
    """A card source: an extracted tree or a raw SD image (FAT32 read in place)."""
    import cardcheck
    if image:
        return cardcheck.Fat32Image(Path(image))
    if root:
        return cardcheck.RootSource(Path(root))
    return None


class Card:
    """A card, addressed the way the firmware names files.

    ``source`` has ``list_dir(rel)`` and ``read_range(rel, offset, length)``
    (``cardcheck.RootSource``, ``cardcheck.Fat32Image`` or ``MemorySource``).
    ``overlay`` maps a card path to replacement bytes, or to ``None`` to hide
    the file: one changed file on an otherwise untouched card.
    """

    def __init__(self, source=None, mount: str = "", overlay: dict | None = None):
        self.source = source
        self.set_mount(mount)
        self.overlay = {k.strip("/").lower(): v for k, v in (overlay or {}).items()}
        self.handles: dict[int, dict] = {}
        self.next_handle = FILE_VA
        self.log: list[dict] = []          # opens, reads, finds in call order
        self._dirs: dict[str, dict] = {}

    def set_mount(self, mount: str) -> None:
        self.mount = mount.replace("/", "\\").strip("\\").lower()

    def _list(self, rel: str) -> dict:
        """{lower name: Entry} of one directory, overlay applied."""
        if rel not in self._dirs:
            try:
                items = {e.name.lower(): e for e in self.source.list_dir(rel)}
            except (OSError, KeyError, ValueError):
                items = {}
            prefix = (rel + "/").lower() if rel else ""
            for path, data in self.overlay.items():
                if path.startswith(prefix) and "/" not in path[len(prefix):]:
                    name = path[len(prefix):]
                    if data is None:
                        items.pop(name, None)
                    else:
                        from cardcheck import Entry
                        old = items.get(name)
                        real = old.name if old else name.upper()
                        items[name] = Entry(name=real, is_dir=False, size=len(data),
                                            path=(rel + "/" + real).strip("/"))
            self._dirs[rel] = items
        return self._dirs[rel]

    def resolve(self, guest_path: str):
        """Guest path -> directory entry (case-insensitive), or None."""
        if self.source is None:
            return None
        parts = [p for p in guest_path.replace("/", "\\").split("\\") if p and p != "."]
        mount = [p for p in self.mount.split("\\") if p]
        if [p.lower() for p in parts[:len(mount)]] == mount:
            parts = parts[len(mount):]
        from cardcheck import Entry
        entry = Entry(name="", is_dir=True, path="")
        for part in parts:
            if part == ".." or not entry.is_dir:
                return None
            entry = self._list(entry.path).get(part.lower())
            if entry is None:
                return None
        return entry

    def _read(self, entry, offset: int, length: int) -> bytes:
        data = self.overlay.get(entry.path.lower())
        if data is not None:
            return data[offset:offset + length]
        if offset >= entry.size or length <= 0:
            return b""
        return self.source.read_range(entry.path, offset, min(length, entry.size - offset))

    def fopen(self, guest_path: str, mode: str) -> int:
        entry = self.resolve(guest_path)
        ok = entry is not None and not entry.is_dir and "w" not in mode and "a" not in mode
        self.log.append({"op": "open", "path": guest_path, "mode": mode,
                         "file": entry.path if ok else None})
        if not ok:
            return 0
        handle = self.next_handle
        self.next_handle += 0x20
        self.handles[handle] = {"file": entry.path, "entry": entry, "pos": 0,
                                "size": entry.size, "eof": False}
        return handle

    def get(self, handle: int) -> dict:
        try:
            return self.handles[handle]
        except KeyError:
            raise Blocked("stdio call on %#010x, which is not an open FILE*" % handle) from None

    def fread(self, handle: int, length: int) -> bytes:
        h = self.get(handle)
        data = self._read(h["entry"], h["pos"], length)
        self.log.append({"op": "read", "file": h["file"], "offset": h["pos"],
                         "length": length, "got": len(data)})
        h["pos"] += len(data)
        h["eof"] = len(data) < length
        return data

    def fseek(self, handle: int, offset: int, whence: int) -> int:
        h = self.get(handle)
        base = (0, h["pos"], h["size"])[whence] if whence in (0, 1, 2) else None
        if base is None or base + offset < 0:
            return M32
        h["pos"] = base + offset
        h["eof"] = False
        return 0

    def ftell(self, handle: int) -> int:
        return self.get(handle)["pos"]

    def fclose(self, handle: int) -> int:
        h = self.handles.pop(handle, None)
        if h is None:
            return M32
        self.log.append({"op": "close", "file": h["file"]})
        return 0

    def find(self, pattern: str) -> list:
        """Entries matching a ``dir\\glob`` pattern, in name order (case folded)."""
        import fnmatch
        head, _, glob = pattern.replace("/", "\\").rpartition("\\")
        folder = self.resolve(head)
        found = []
        if folder is not None and folder.is_dir:
            found = sorted((e for n, e in self._list(folder.path).items() if fnmatch.fnmatch(n, glob.lower())),
                           key=lambda e: e.name.lower())
        self.log.append({"op": "find", "path": pattern, "count": len(found)})
        return found

    def reads(self) -> list[tuple]:
        """The read log as comparable tuples."""
        return [(e["file"], e["offset"], e["length"], e["got"]) for e in self.log if e["op"] == "read"]

    def opens(self) -> list[tuple]:
        return [(e["path"], e["file"]) for e in self.log if e["op"] == "open"]


# --------------------------------------------------------------------------
# printf family
def format_c(fmt: str, next_arg, read_cstr, read_wstr, wide: bool = False) -> str:
    """A small ``printf``: d i u x X c s S p, flags, width, precision, l/h."""
    out, i, n = [], 0, len(fmt)
    while i < n:
        ch = fmt[i]
        if ch != "%":
            out.append(ch)
            i += 1
            continue
        j = i + 1
        flags = ""
        while j < n and fmt[j] in "-+ #0":
            flags += fmt[j]
            j += 1
        width = ""
        while j < n and (fmt[j].isdigit() or fmt[j] == "*"):
            width += str(next_arg()) if fmt[j] == "*" else fmt[j]
            j += 1
        prec = None
        if j < n and fmt[j] == ".":
            j += 1
            prec = ""
            while j < n and (fmt[j].isdigit() or fmt[j] == "*"):
                prec += str(next_arg()) if fmt[j] == "*" else fmt[j]
                j += 1
        size = ""
        while j < n and fmt[j] in "lhLw":
            size += fmt[j]
            j += 1
        if j >= n:
            out.append(fmt[i:])
            break
        conv = fmt[j]
        spec = "%" + flags + width + ("." + prec if prec is not None else "")
        if conv == "%":
            out.append("%")
        elif conv in "di":
            v = next_arg()
            out.append((spec + "d") % (v - (1 << 32) if v & 0x80000000 else v))
        elif conv in "uxX":
            out.append((spec + conv) % next_arg())
        elif conv == "p":
            out.append("%08x" % next_arg())
        elif conv == "c":
            out.append((spec + "c") % chr(next_arg() & 0xFF))
        elif conv in "sS":
            va = next_arg()
            is_wide = (conv == "S") != wide or "l" in size or "w" in size
            if "h" in size:
                is_wide = False
            text = "(null)" if va == 0 else (read_wstr(va) if is_wide else read_cstr(va))
            out.append((spec + "s") % text)
        else:
            raise Blocked("printf conversion %%%s is not modelled (format %r)" % (conv, fmt))
        i = j + 1
    return "".join(out)


# --------------------------------------------------------------------------
class Machine:
    """``Navi.exe`` in PySh4 with bound imports and a card."""

    def __init__(self, image: bytes, card: Card, module: str = "Navi.exe",
                 image_start: int = IMAGE_A, data_cache: Path | None = None,
                 imports_text: str | None = None, trace_imports: bool = False):
        import cerom
        import nk_decomp
        self.card = card
        self.trace_imports = trace_imports
        self.import_log: list[dict] = []      # every import call, in order
        self.messages: list[dict] = []        # OSM_TaskSend and friends
        self.prints: list[str] = []
        self.finds: dict[int, list] = {}
        self.objects: list[dict] = []       # OBJDLL writes (the layer's published state)
        self.heap_next = HEAP_VA + 0x100
        self.allocs: dict[int, int] = {}
        self.free_blocks: dict[int, list[int]] = {}
        self.last_error = 0
        eng = self.eng = PySh4(endian="little")
        rom = cerom.CERom(image, image_start)
        self.sections = []
        for index, s in enumerate(rom.o32(rom.module(module))):
            size = (s["vsize"] + 0xFFF) & ~0xFFF
            buf = bytearray(size)
            off = rom.va2file(s["dataptr"])
            if s["flags"] & cerom.IMAGE_SCN_COMPRESSED:
                blob = None
                if data_cache and data_cache.is_file() and index == 1:
                    blob = data_cache.read_bytes()
                    if len(blob) != s["vsize"]:
                        blob = None
                if blob is None:
                    r0, blob = nk_decomp.decompress(image, off, s["psize"], s["vsize"])
                    if r0 == M32:
                        raise Blocked("section %d of %s does not decompress" % (index, module))
                    if data_cache and index == 1:
                        data_cache.parent.mkdir(parents=True, exist_ok=True)
                        data_cache.write_bytes(blob)
                buf[:len(blob)] = blob
            else:
                n = min(s["psize"], s["vsize"])
                buf[:n] = image[off:off + n]
            writable = bool(s["flags"] & 0x80000000)
            eng.map("%s/sec%d" % (module, index), s["realaddr"], buf, "rw" if writable else "rx")
            self.sections.append((s["realaddr"], size, writable))
        eng.map("heap", HEAP_VA, bytearray(HEAP_SIZE), "rw")
        eng.map("stack", STACK_VA, bytearray(STACK_SIZE), "rw")
        # imports: slot -> trampoline -> host model
        if imports_text is None:
            raise Blocked("no import list")
        self.slots: dict[int, str] = {}
        for line in imports_text.splitlines():
            if "slot=" not in line:
                continue
            parts = line.split()
            name = parts[2] if len(parts) > 2 else "?"
            if "!" not in name:
                name = parts[0].rsplit(".", 1)[0].upper() + "!" + name
            self.slots[int(parts[1].split("=")[1], 16)] = name
        eng.map("imports", TRAMP_VA, bytearray((len(self.slots) * 4 + 0xFFF) & ~0xFFF or 0x1000), "rx")
        for i, (slot, name) in enumerate(sorted(self.slots.items())):
            tramp = TRAMP_VA + 4 * i
            eng.write_mem(slot, struct.pack("<I", tramp))
            eng.on_exec(tramp, self._make_import(name))

    # -- guest memory helpers ----------------------------------------------
    def reg(self, name: str) -> int:
        return self.eng._get_reg(name) & M32

    def arg(self, index: int) -> int:
        """C argument *index*: r4-r7, then the caller's stack from sp+16."""
        if index < 4:
            return self.reg("r%d" % (4 + index))
        return struct.unpack("<I", self.eng.read_mem(self.reg("r15") + 16 + 4 * (index - 4), 4))[0]

    def cstr(self, va: int, limit: int = 4096) -> str:
        out = bytearray()
        while len(out) < limit:
            b = self.eng.read_mem(va + len(out), 1)[0]
            if b == 0:
                break
            out.append(b)
        return out.decode("latin-1")

    def wstr(self, va: int, limit: int = 2048) -> str:
        out = []
        while len(out) < limit:
            w = struct.unpack("<H", self.eng.read_mem(va + 2 * len(out), 2))[0]
            if w == 0:
                break
            out.append(chr(w))
        return "".join(out)

    def put(self, va: int, data: bytes) -> None:
        if data:
            self.eng.write_mem(va, data)

    def u32(self, va: int) -> int:
        return struct.unpack("<I", self.eng.read_mem(va, 4))[0]

    def malloc(self, size: int) -> int:
        size = max(16, (size + 15) & ~15)
        bucket = self.free_blocks.get(size)
        if bucket:                         # exact-size reuse; contents are stale
            va = bucket.pop()
            self.allocs[va] = size
            return va
        va = self.heap_next
        if va + size > HEAP_VA + HEAP_SIZE:
            return 0
        self.heap_next = va + size + 16
        self.allocs[va] = size
        return va

    def free(self, va: int) -> None:
        size = self.allocs.pop(va, None)
        if size is not None:
            self.free_blocks.setdefault(size, []).append(va)

    # -- import dispatch ----------------------------------------------------
    def _make_import(self, name: str):
        short = name.split("!", 1)[1]

        def handler(engine, va):
            model = MODELS.get(name) or MODELS.get(short)
            if model is None:
                raise Blocked("missing import model: %s (called from %#010x)"
                              % (name, (self.reg("pr") - 4) & M32))
            value = model(self)
            entry = {"name": name, "pr": self.reg("pr"), "r0": value & M32}
            self.import_log.append(entry)
            if self.trace_imports:
                print("  import %-32s pr=%#010x -> %#x" % (name, entry["pr"], entry["r0"]), file=sys.stderr)
            return StubReturn(value & M32)
        return handler

    def call(self, va: int, args=(), stack_args=(), max_insns: int = 200_000_000) -> int:
        sp = STACK_VA + STACK_SIZE - 0x1000
        self.put(sp + 16, b"".join(struct.pack("<I", a & M32) for a in stack_args))
        self.eng.set_regs(r15=sp, pr=RETURN_VA, pc=va)
        for i in range(4):
            self.eng._set_reg("r%d" % (4 + i), (args[i] if i < len(args) else 0) & M32)
        self.eng.run_until(None, max_insns)
        return self.reg("r0")


# --------------------------------------------------------------------------
# import models.  Each takes the machine and returns r0.
MODELS: dict = {}


def model(*names):
    def deco(fn):
        for n in names:
            MODELS[n] = fn
        return fn
    return deco


def _s32(v: int) -> int:
    return v - (1 << 32) if v & 0x80000000 else v


@model("fopen")
def _fopen(m):
    return m.card.fopen(m.cstr(m.arg(0)), m.cstr(m.arg(1)))


@model("_wfopen")
def _wfopen(m):
    return m.card.fopen(m.wstr(m.arg(0)), m.wstr(m.arg(1)))


@model("fclose")
def _fclose(m):
    return m.card.fclose(m.arg(0))


@model("fread")
def _fread(m):
    buf, size, count, fp = m.arg(0), m.arg(1), m.arg(2), m.arg(3)
    if size == 0 or count == 0:
        return 0
    data = m.card.fread(fp, size * count)
    m.put(buf, data)
    return len(data) // size


@model("fwrite")
def _fwrite(m):
    raise Blocked("fwrite: the virtual card is read-only (file %s)" % m.card.get(m.arg(3))["file"])


@model("fseek")
def _fseek(m):
    return m.card.fseek(m.arg(0), _s32(m.arg(1)), m.arg(2))


@model("ftell")
def _ftell(m):
    return m.card.ftell(m.arg(0))


@model("ferror")
def _ferror(m):
    m.card.get(m.arg(0))
    return 0


@model("feof")
def _feof(m):
    return 1 if m.card.get(m.arg(0))["eof"] else 0


@model("clearerr")
def _clearerr(m):
    m.card.get(m.arg(0))["eof"] = False
    return 0


@model("memset")
def _memset(m):
    m.put(m.arg(0), bytes([m.arg(1) & 0xFF]) * m.arg(2))
    return m.arg(0)


@model("memcpy", "memmove")
def _memcpy(m):
    n = m.arg(2)
    if n:
        m.put(m.arg(0), bytes(m.eng.read_mem(m.arg(1), n)))
    return m.arg(0)


@model("memcmp")
def _memcmp(m):
    a, b = bytes(m.eng.read_mem(m.arg(0), m.arg(2))), bytes(m.eng.read_mem(m.arg(1), m.arg(2)))
    return (a > b) - (a < b)


@model("strlen")
def _strlen(m):
    return len(m.cstr(m.arg(0), 1 << 20))


@model("strcpy")
def _strcpy(m):
    m.put(m.arg(0), m.cstr(m.arg(1), 1 << 20).encode("latin-1") + b"\0")
    return m.arg(0)


@model("strncpy")
def _strncpy(m):
    src = m.cstr(m.arg(1), m.arg(2)).encode("latin-1")[:m.arg(2)]
    m.put(m.arg(0), src + b"\0" * (m.arg(2) - len(src)))
    return m.arg(0)


@model("strcat")
def _strcat(m):
    dst = m.arg(0)
    m.put(dst + len(m.cstr(dst, 1 << 20)), m.cstr(m.arg(1), 1 << 20).encode("latin-1") + b"\0")
    return dst


@model("strncat")
def _strncat(m):
    dst = m.arg(0)
    m.put(dst + len(m.cstr(dst, 1 << 20)), m.cstr(m.arg(1), m.arg(2)).encode("latin-1")[:m.arg(2)] + b"\0")
    return dst


def _cmp(a, b) -> int:
    return ((a > b) - (a < b)) & M32


@model("strcmp")
def _strcmp(m):
    return _cmp(m.cstr(m.arg(0), 1 << 20), m.cstr(m.arg(1), 1 << 20))


@model("strncmp")
def _strncmp(m):
    return _cmp(m.cstr(m.arg(0), m.arg(2))[:m.arg(2)], m.cstr(m.arg(1), m.arg(2))[:m.arg(2)])


@model("_stricmp", "stricmp")
def _stricmp(m):
    return _cmp(m.cstr(m.arg(0), 1 << 20).lower(), m.cstr(m.arg(1), 1 << 20).lower())


@model("strchr")
def _strchr(m):
    text = m.cstr(m.arg(0), 1 << 20)
    i = text.find(chr(m.arg(1) & 0xFF))
    return m.arg(0) + i if i >= 0 else 0


@model("strrchr")
def _strrchr(m):
    text = m.cstr(m.arg(0), 1 << 20)
    i = text.rfind(chr(m.arg(1) & 0xFF))
    return m.arg(0) + i if i >= 0 else 0


@model("atoi", "atol")
def _atoi(m):
    text = m.cstr(m.arg(0)).strip()
    n = 0
    sign = -1 if text[:1] == "-" else 1
    for ch in text.lstrip("+-"):
        if not ch.isdigit():
            break
        n = n * 10 + int(ch)
    return (sign * n) & M32


@model("wcslen")
def _wcslen(m):
    return len(m.wstr(m.arg(0), 1 << 16))


@model("wcstombs")
def _wcstombs(m):
    dst, text, n = m.arg(0), m.wstr(m.arg(1), 1 << 16), m.arg(2)
    raw = text.encode("latin-1", "replace")[:n]
    if dst:
        m.put(dst, raw + (b"\0" if len(raw) < n else b""))
    return len(raw)


@model("mbstowcs")
def _mbstowcs(m):
    dst, text, n = m.arg(0), m.cstr(m.arg(1), 1 << 16), m.arg(2)
    text = text[:n]
    if dst:
        m.put(dst, text.encode("utf-16-le") + (b"\0\0" if len(text) < n else b""))
    return len(text)


def _printf_args(m, first: int):
    state = {"i": first}

    def nxt():
        v = m.arg(state["i"])
        state["i"] += 1
        return v
    return nxt


def _va_args(m, va_list: int):
    state = {"p": va_list}

    def nxt():
        v = m.u32(state["p"])
        state["p"] += 4
        return v
    return nxt


@model("sprintf")
def _sprintf(m):
    text = format_c(m.cstr(m.arg(1)), _printf_args(m, 2), m.cstr, m.wstr)
    m.put(m.arg(0), text.encode("latin-1", "replace") + b"\0")
    return len(text)


@model("_snprintf")
def _snprintf(m):
    text = format_c(m.cstr(m.arg(2)), _printf_args(m, 3), m.cstr, m.wstr)[:m.arg(1)]
    m.put(m.arg(0), text.encode("latin-1", "replace") + (b"\0" if len(text) < m.arg(1) else b""))
    return len(text)


@model("vsprintf")
def _vsprintf(m):
    text = format_c(m.cstr(m.arg(1)), _va_args(m, m.arg(2)), m.cstr, m.wstr)
    m.put(m.arg(0), text.encode("latin-1", "replace") + b"\0")
    return len(text)


@model("_vsnprintf")
def _vsnprintf(m):
    text = format_c(m.cstr(m.arg(2)), _va_args(m, m.arg(3)), m.cstr, m.wstr)[:m.arg(1)]
    m.put(m.arg(0), text.encode("latin-1", "replace") + (b"\0" if len(text) < m.arg(1) else b""))
    return len(text)


@model("printf", "OSM_Printf")
def _printf(m):
    text = format_c(m.cstr(m.arg(0)), _printf_args(m, 1), m.cstr, m.wstr)
    m.prints.append(text)
    return len(text)


@model("NKDbgPrintfW")
def _nkdbg(m):
    text = format_c(m.wstr(m.arg(0)), _printf_args(m, 1), m.cstr, m.wstr, wide=True)
    m.prints.append(text)
    return 0


@model("DebugShellOutput")
def _dbgshell(m):
    m.prints.append("DebugShellOutput(%#x, %#x)" % (m.arg(0), m.arg(1)))
    return 0


@model("ErrorLogMsg")
def _errlog(m):
    m.messages.append({"kind": "ErrorLogMsg", "args": [m.arg(i) for i in range(4)],
                       "pr": m.reg("pr")})
    return 0


@model("_divls", "__divls")
def _divls(m):
    a, b = _s32(m.arg(0)), _s32(m.arg(1))
    if b == 0:
        raise Blocked("division by zero in _divls")
    q = abs(a) // abs(b)
    return (-q if (a < 0) != (b < 0) else q) & M32


@model("_divlu")
def _divlu(m):
    if m.arg(1) == 0:
        raise Blocked("division by zero in _divlu")
    return m.arg(0) // m.arg(1)


@model("_modls")
def _modls(m):
    a, b = _s32(m.arg(0)), _s32(m.arg(1))
    if b == 0:
        raise Blocked("division by zero in _modls")
    r = abs(a) % abs(b)
    return (-r if a < 0 else r) & M32


@model("_modlu")
def _modlu(m):
    if m.arg(1) == 0:
        raise Blocked("division by zero in _modlu")
    return m.arg(0) % m.arg(1)


@model("malloc", "OSM_Malloc")
def _malloc(m):
    return m.malloc(m.arg(0))


@model("calloc", "OSM_Calloc")
def _calloc(m):
    size = m.arg(0) * m.arg(1)
    va = m.malloc(size)
    if va:
        m.put(va, bytes(size))
    return va


@model("LocalAlloc")
def _localalloc(m):
    va = m.malloc(m.arg(1))
    return va


@model("free", "OSM_Free", "LocalFree")
def _free(m):
    m.free(m.arg(0))
    return 0


@model("taskLock", "taskUnlock", "intContext", "OSM_TaskDelay", "Sleep",
       "ReleaseMutex", "WaitForSingleObject", "OSM_SramSet", "OSM_SramClear",
       "EnterCriticalSection", "LeaveCriticalSection")
def _zero(m):
    return 0


@model("taskIdSelf")
def _taskidself(m):
    return 1


@model("GetTickCount")
def _ticks(m):
    return 0


@model("GetLastError")
def _gle(m):
    return m.last_error


@model("SetLastError")
def _sle(m):
    m.last_error = m.arg(0)
    return 0


@model("OSM_TaskSend")
def _tasksend(m):
    # (task, message *, flags).  Never answered here: the message is logged
    # and the call returns 0 = queued, which is what the sender sees.
    try:
        body = bytes(m.eng.read_mem(m.arg(1), 32))
    except EngineError:
        body = b""
    m.messages.append({"kind": "send", "task": m.arg(0), "body": body.hex(), "pr": m.reg("pr")})
    return 0


@model("SYS_Timer_setMsg")
def _timer(m):
    m.messages.append({"kind": "timer", "args": [m.arg(i) for i in range(4)], "pr": m.reg("pr")})
    return 0


def _find_data(m, va: int, entry) -> None:
    """WIN32_FIND_DATAW as Windows CE lays it out (attrs, 3 FILETIME, size hi/lo, OID, name)."""
    size = 0 if entry.is_dir else entry.size
    name = entry.name.encode("utf-16-le")[:518] + b"\0\0"
    m.put(va, struct.pack("<I24xIII", 0x10 if entry.is_dir else 0x20, size >> 32, size & M32, 0) + name)


@model("FindFirstFileW")
def _findfirst(m):
    items = m.card.find(m.wstr(m.arg(0)))
    if not items:
        m.last_error = 2
        return M32
    handle = m.card.next_handle
    m.card.next_handle += 0x20
    m.finds[handle] = items[1:]
    _find_data(m, m.arg(1), items[0])
    return handle


@model("FindNextFileW")
def _findnext(m):
    items = m.finds.get(m.arg(0))
    if not items:
        m.last_error = 18
        return 0
    _find_data(m, m.arg(1), items.pop(0))
    return 1


@model("FindClose")
def _findclose(m):
    return 1 if m.finds.pop(m.arg(0), None) is not None else 0


@model("wsprintfW", "swprintf")
def _wsprintf(m):
    text = format_c(m.wstr(m.arg(1)), _printf_args(m, 2), m.cstr, m.wstr, wide=True)
    m.put(m.arg(0), text.encode("utf-16-le") + b"\0\0")
    return len(text)


@model("InitializeCriticalSection", "DeleteCriticalSection")
def _cs(m):
    return 0


@model("OBJ_DriveInfo_getObjID", "OBJ_DiscInfo_getObjID")
def _objid(m):
    # (id *out, index): store an id, return 0 = OK (0x0041a244 logs a non-zero return)
    m.put(m.arg(0), struct.pack("<I", (0xB1D << 16) + (m.arg(1) & 0xFFFF)))
    return 0


def _obj_write(kind):
    def fn(m):
        m.objects.append({"kind": kind, "args": [m.arg(i) for i in range(4)], "pr": m.reg("pr")})
        return 0
    return fn


for _name in ("OBJ_DriveInfo_writeRecogSts", "OBJ_DriveInfo_writeDataVol", "OBJ_DiscInfo_writeDiscVol"):
    MODELS[_name] = _obj_write(_name)


# --------------------------------------------------------------------------
# The map-file layer of Navi.exe, EU2011 build A.  Every VA is a pdata START
# (docs/format/firmware.md, "The map-file layer"; EXP-2026-11-19-M9.44).
EU2011 = {
    "build": "eu2011",
    "head_sha256": "92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9",
    # L"\\SystemSD", the prefix of every file name: a data address (image base
    # 0x10000 + rva 0x39fd4), written as a sum so fn_audit does not read it as
    # a function citation
    "volume_root_w": 0x10000 + 0x39FD4,
    "init": 0x00417924,            # layer init (tables, pools, state 0)
    "event": 0x00419C38,           # (kind): runs the handler for (state, kind)
    "read": 0x0041841C,            # (file id, request *): queue a read
    "resolve": 0x0040B358,         # (directory path, file name) -> file id or -1
    "read_clients": {0x00409BA0: "range clamp", 0x003F6C88: "read request",
                     0x003F7384: "read wrapper A", 0x003F73DC: "read wrapper B"},
    "cancel": 0x00418428,          # (request serial): withdraw a queued read
    "logger": 0x0041BBEC,          # the layer's error logger
    "state": 0x009CFCE0,           # state-machine state (0, 1, 2)
    "mount": 0x009CFCE4,           # mount state (2 = volume table valid)
    "ndirs": 0x009CFCD4,           # directory count
    "dirs": 0x00E25420,            # 36-byte directory records
    "mmain_buf": 0x00E23CC0,       # 0x1000 bytes of MMAIN001.DAT
    "reply_msg": 0x04A0,           # message id of a read completion
}

# The same layer in the US2011 build A (`archive/us256.img`, SHA-256 70d945d8…).
# Functions: `fn_match.py match` (12 UNIQUE pairs; `read` is a 12-byte stub
# that fn_match calls AMBIGUOUS and is taken as the pdata START at the same
# distance as its EU neighbours, with the same words). Data addresses: the
# literal-pool value at the same load index of the matched function
# (`vcard_l3.py port EU_HEAD US_HEAD` re-derives and checks every one, M9.14);
# `mount` is `state + 4` as in EU2011 (no pool of these functions loads it).
US2011 = {
    "build": "us2011",
    "head_sha256": "70d945d823f93f04cae4e6c7113a723cae3a992ab7a6f9b24e94ce2e006a04da",
    "volume_root_w": 0x10000 + 0x46634,
    "init": 0x0043F688,
    "event": 0x0044199C,
    "read": 0x00440180,
    "resolve": 0x00433458,
    "read_clients": {0x00431CA0: "range clamp", 0x0041F5E8: "read request",
                     0x0041FCE4: "read wrapper A", 0x0041FD3C: "read wrapper B"},
    "cancel": 0x0044018C,
    "logger": 0x00443950,
    "state": 0x00A10EA8,
    "mount": 0x00A10EAC,
    "ndirs": 0x00A10E9C,
    "dirs": 0x00D53020,
    "mmain_buf": 0x00D518C0,
    "reply_msg": 0x04A0,
}
BUILDS = {"eu2011": EU2011, "us2011": US2011}

#: Functions that only ``port`` uses: they load data addresses the layer
#: dict names (EU2011 -> US2011, fn_match UNIQUE).
PORT_EXTRA = {0x00419350: 0x004410B4,   # DRSTR parser
              0x00419684: 0x004413E8,   # its caller (volume table build)
              0x0041A438: 0x0044219C}   # mmain_reader
PORT_DATA = ("volume_root_w", "state", "ndirs", "dirs", "mmain_buf")


def port_pairs(a: dict, b: dict) -> list[tuple[int, int]]:
    """EU -> US function pairs implied by two build dicts (+ PORT_EXTRA)."""
    pairs = []
    for key in ("init", "event", "read", "resolve", "cancel", "logger"):
        pairs.append((a[key], b[key]))
    pairs += list(zip(a["read_clients"], b["read_clients"]))
    pairs += sorted(PORT_EXTRA.items())
    return pairs


def pool_values(u16, va: int, length: int) -> list[int]:
    """Values of the PC-relative loads of the function at *va*, in order."""
    from fn_match import _pool_loads
    words = [u16(va + 2 * i) for i in range(length // 2)]
    out = []
    for _i, lit, size, _dest in _pool_loads(words, va):
        lo = u16(lit)
        out.append(lo if size == 2 else lo | (u16(lit + 2) << 16))
    return out


def port_data(pairs, eu_u16, us_u16, lengths, wanted: dict) -> dict:
    """For every EU data value in *wanted* (value -> name), the US values found
    at the same pool-load index of the paired function; ``{name: {us: n}}``."""
    found: dict = {}
    for eva, uva in pairs:
        ea = pool_values(eu_u16, eva, lengths[eva])
        ub = pool_values(us_u16, uva, lengths[eva])
        if len(ea) != len(ub):
            continue
        for x, y in zip(ea, ub):
            if x in wanted:
                found.setdefault(wanted[x], {}).setdefault(y, 0)
                found[wanted[x]][y] += 1
    return found


def cmd_port(args) -> int:
    import sh4dis
    from fn_match import parse_pdata, locate
    import nk_decomp
    heads = {}
    for name, path in (("eu", args.image), ("us", args.other)):
        data = nk_decomp.load_image(path)
        heads[name] = (sh4dis.load_segments(path, IMAGE_A, "Navi.exe")[0],
                       parse_pdata(nk_decomp.section_init(data, "Navi.exe", 2)))
    (me, pe), (mu, pu) = heads["eu"], heads["us"]
    pairs = port_pairs(EU2011, US2011)
    lengths, bad = {}, 0
    for eva, uva in pairs:
        ke, re_ = locate(pe, eva)
        ku, ru = locate(pu, uva)
        same = 0
        if ke == "START":
            lengths[eva] = re_[2]
            same = sum(me.u16(eva + i) == mu.u16(uva + i) for i in range(0, re_[2], 2))
        ok = ke == ku == "START" and re_[2] == ru[2]
        bad += not ok
        print("fn 0x%08x -> 0x%08x  EU %s US %s  len %s/%s  same halfwords %d  %s" % (
            eva, uva, ke, ku, hex(re_[2]) if re_ else "-", hex(ru[2]) if ru else "-",
            same, "ok" if ok else "MISMATCH"))
    wanted = {EU2011[k]: k for k in PORT_DATA}
    found = port_data([p for p in pairs if p[0] in lengths], me.u16, mu.u16, lengths, wanted)
    for key in PORT_DATA:
        hits = found.get(key, {})
        ok = list(hits) == [US2011[key]]
        bad += not ok
        print("%-14s EU 0x%08x -> US %s (dict 0x%08x) %s" % (
            key, EU2011[key], ", ".join("0x%08x x%d" % kv for kv in hits.items()) or "none",
            US2011[key], "ok" if ok else "MISMATCH"))
    ok = US2011["mount"] - US2011["state"] == EU2011["mount"] - EU2011["state"]
    bad += not ok
    print("mount          state + %d in both builds %s" % (EU2011["mount"] - EU2011["state"], "ok" if ok else "MISMATCH"))
    print("port: %s" % ("OK" if not bad else "%d MISMATCH" % bad))
    return 0 if not bad else 1


STATUS_TEXT = {-10: "request queue full", -11: "request refused (bad range or arguments)",
               -12: "card not mounted", 0x1FF: "no completion: the open failed and the request was re-queued"}
REPLY_TASK = 0x77            # our "client task" id; any non-zero value
MAX_EVENTS = 8
SECTOR = 2048


class Session:
    """One virtual card in one virtual unit: boot it, then ask for files."""

    def __init__(self, image_path: str, card: Card, trace: bool = False, build: dict = EU2011):
        self.b = build
        self.card = card
        self.m = load_machine(image_path, card, trace)
        card.set_mount(self.m.wstr(build["volume_root_w"]))
        self.fwlog: list[dict] = []
        self.m.eng.on_exec(build["logger"], self._on_log)
        self.states: list[tuple] = []
        self._tree = None

    def _on_log(self, engine, va):
        m = self.m
        self.fwlog.append({"caller": (m.reg("pr") - 4) & M32, "level": m.arg(0), "module": m.arg(1),
                           "func": m.arg(2), "line": m.arg(3), "value": m.arg(4)})
        return None                       # let the firmware's logger run

    def state(self) -> tuple:
        return (self.m.u32(self.b["state"]), self.m.u32(self.b["mount"]))

    def boot(self) -> dict:
        """Layer init, then media events until the state machine settles."""
        m = self.m
        m.call(self.b["init"])
        self.states = [self.state()]
        for _ in range(MAX_EVENTS):
            m.call(self.b["event"], [0])
            self.states.append(self.state())
            if self.states[-1] == (2, 2) or (len(self.states) > 3 and len(set(self.states[-3:])) == 1):
                break
        ok = self.states[-1] == (2, 2)
        return {"verdict": "ACCEPT" if ok else "REJECT", "states": self.states,
                "events": len(self.states) - 1}

    # -- what the firmware built ------------------------------------------
    def tree(self) -> list[dict]:
        """The firmware's own volume table: directories and their entries."""
        if self._tree is not None:
            return self._tree
        m, out = self.m, []
        count = m.u32(self.b["ndirs"])
        if count > 200:
            raise Blocked("directory count %d is not a volume table" % count)
        for i in range(count):
            rec = bytes(m.eng.read_mem(self.b["dirs"] + 36 * i, 36))
            dir_id, parent, n = struct.unpack_from("<HHH", rec, 20)
            size, ptr = struct.unpack_from("<II", rec, 28)
            entries = []
            for j in range(n if ptr else 0):
                e = bytes(m.eng.read_mem(ptr + 28 * j, 28))
                eid, kind, esize = struct.unpack_from("<HHI", e, 20)
                entries.append({"name": e[:20].split(b"\0")[0].decode("latin-1"), "id": eid,
                                "is_dir": kind == 2, "size": esize})
            out.append({"name": rec[:20].split(b"\0")[0].decode("latin-1"), "id": dir_id,
                        "parent": parent, "size": size, "entries": entries})
        by_id = {d["id"]: d for d in out}
        for d in out:
            parts, cur, guard = [], d, 0
            while cur["name"] != "/" and guard < 16:
                parts.append(cur["name"])
                cur = by_id.get(cur["parent"], {"name": "/"})
                guard += 1
            d["path"] = "/".join(reversed(parts))
        self._tree = out
        return out

    def tree_digest(self) -> str:
        rows = []
        for d in self.tree():
            for e in d["entries"]:
                rows.append("%s|%d|%d|%s|%d|%d|%d" % (d["path"], d["id"], d["parent"], e["name"],
                                                      e["id"], e["is_dir"], e["size"]))
        return hashlib.sha256("\n".join(rows).encode()).hexdigest()

    def files(self) -> list[dict]:
        out = []
        for d in self.tree():
            for e in d["entries"]:
                if not e["is_dir"]:
                    out.append({"path": (d["path"] + "/" + e["name"]).strip("/"), "size": e["size"],
                                "fid": (d["id"] << 16) | e["id"]})
        return out

    def find_file(self, path: str) -> dict:
        want = path.replace("\\", "/").strip("/").lower()
        for f in self.files():
            if f["path"].lower() == want:
                return f
        raise Blocked("%s is not in the firmware's volume table" % path)

    # -- reads through the layer -------------------------------------------
    def request(self, fid: int, offset: int, length: int, swap: bool = False) -> tuple[int, bytes]:
        """One read request, queued and served by firmware code.

        Returns (status, data).  status 0 = the layer's completion message
        said OK; a negative status is the queueing call's own return value
        (-10 busy, -11 bad request, -12 not mounted); 0x100+n is a completion
        with error n.
        """
        m = self.m
        if offset % SECTOR or length <= 0 or length % 4 or length > 1 << 20:
            raise Blocked("request must be sector-aligned, 4-byte sized and at most 1 MiB")
        req, dst = m.malloc(64), m.malloc(length + 16)
        m.put(dst, bytes(length))
        # +0 dest, +4 sector, +8 byte offset, +12 length, +16 kind (1), +20 1 = no
        # byte swap, +24 0, +28 0, +32 reply task, +36 out: serial
        m.put(req, struct.pack("<IIIIIIIHHII", dst, offset // SECTOR, 0, length, 1,
                               0 if swap else 1, 0, 0, 0, REPLY_TASK, 0))
        try:
            return self._request(fid, req, dst)
        finally:
            m.free(req)
            m.free(dst)

    def _request(self, fid: int, req: int, dst: int) -> tuple[int, bytes]:
        m = self.m
        first = len(m.messages)
        r0 = _s32(m.call(self.b["read"], [fid, req]))
        if r0 != 0:
            return r0, b""
        serial = m.u32(req + 36)
        m.call(self.b["event"], [2])       # the queued message reaches the task
        for msg in m.messages[first:]:
            if msg["kind"] == "send" and msg["task"] == REPLY_TASK and len(msg["body"]) >= 48:
                body = bytes.fromhex(msg["body"])
                msg_id, _serial, status, buf, n = struct.unpack_from("<HHIII", body, 8)
                if msg_id != self.b["reply_msg"] or buf != dst:
                    continue
                if status:
                    return 0x100 + status, b""
                return 0, bytes(m.eng.read_mem(dst, n))
        m.call(self.b["cancel"], [serial])  # still queued: withdraw it, the buffer is ours
        return 0x1FF, b""

    def read(self, path: str, offset: int = 0, length: int | None = None, chunk: int = 0x10000,
             swap: bool = False) -> tuple[int, bytes]:
        """Bytes [offset, offset+length) of a card file, as the firmware returns them."""
        f = self.find_file(path)
        if length is None:
            length = f["size"] - offset
        end = min(offset + length, f["size"])
        pos, out = offset - offset % SECTOR, bytearray()
        while pos < end:
            n = min(chunk, end - pos)
            ask = (n + 3) & ~3
            if pos + ask > f["size"]:      # the layer refuses a range past the end
                ask = n & ~3
            if ask == 0:
                return -11, bytes(out)
            status, data = self.request(f["fid"], pos, ask, swap)
            if status:
                return status, bytes(out)
            out += data[:n]
            pos += n
        skip = offset % SECTOR
        return 0, bytes(out[skip:skip + (end - offset)])


class HostReject(Exception):
    """The host-side decoder refuses the file (the comparison has no reference)."""


class Expected:
    """What a file's bytes should be, computed without the firmware."""

    def __init__(self, card: Card):
        self.card = card
        self._cache: dict[str, bytes] = {}

    def _whole(self, entry) -> bytes:
        return self.card._read(entry, 0, entry.size)

    def read(self, path: str, offset: int, length: int) -> bytes | None:
        guest = path.replace("/", "\\")
        plain = self.card.resolve(guest)
        if plain is not None and not plain.is_dir:
            return self.card._read(plain, offset, length)
        cmp_e, ind_e = self.card.resolve(guest + ".cmp"), self.card.resolve(guest + ".ind")
        if cmp_e is None or ind_e is None:
            return None
        if path not in self._cache:
            import cardcheck
            self._cache.clear()            # one decoded file at a time
            try:
                self._cache[path] = cardcheck.decode_cmp(self._whole(cmp_e), self._whole(ind_e))[0]
            except ValueError as exc:
                raise HostReject(str(exc)) from exc
        return self._cache[path][offset:offset + length]


# --------------------------------------------------------------------------
def parse_mods(args) -> dict:
    """--hide P, --replace P=FILE, --flip P@OFF[:XOR], --truncate P@N -> overlay."""
    return {"hide": list(args.hide or []), "replace": list(args.replace or []),
            "flip": list(args.flip or []), "truncate": list(args.truncate or [])}


def make_card(root: str | None, image: str | None, mods: dict | None = None, source=None) -> Card:
    source = source or open_source(root, image)
    card = Card(source)
    mods = mods or {}
    overlay: dict = {}

    def current(path: str) -> bytes:
        key = path.strip("/").lower()
        if key in overlay and overlay[key] is not None:
            return overlay[key]
        entry = card.resolve(path.replace("/", "\\"))
        if entry is None or entry.is_dir:
            raise Blocked("cannot modify %s: not a file on the card" % path)
        return card._read(entry, 0, entry.size)

    for spec in mods.get("replace", []):
        path, _, host = spec.partition("=")
        overlay[path.strip("/").lower()] = Path(host).read_bytes()
    for spec in mods.get("truncate", []):
        path, _, n = spec.rpartition("@")
        overlay[path.strip("/").lower()] = current(path)[:int(n, 0)]
    for spec in mods.get("flip", []):
        path, _, rest = spec.rpartition("@")
        off, _, xor = rest.partition(":")
        data = bytearray(current(path))
        data[int(off, 0)] ^= int(xor, 0) if xor else 0xFF
        overlay[path.strip("/").lower()] = bytes(data)
    for path in mods.get("hide", []):
        overlay[path.strip("/").lower()] = None
    return Card(source, overlay=overlay)


def boot_report(image: str, card: Card, trace: bool = False,
                build: dict | None = None) -> tuple[dict, "Session | None"]:
    build = build or EU2011
    out = {"build": build["build"]}
    digest = hashlib.sha256(Path(image).read_bytes()).hexdigest()
    if digest != build["head_sha256"]:
        out.update(verdict="BLOCKED", blocked="image SHA-256 %s… is not the %s head (%s…); pass --build"
                   % (digest[:8], build["build"], build["head_sha256"][:8]))
        return out, None
    try:
        s = Session(image, card, trace, build)
    except Blocked as exc:
        out.update(verdict="BLOCKED", blocked=str(exc))
        return out, None
    try:
        out.update(s.boot())
        if out["verdict"] == "ACCEPT":
            tree = s.tree()
            out["dirs"] = len(tree)
            out["files"] = len(s.files())
            out["tree_sha256"] = s.tree_digest()
    except Blocked as exc:
        out.update(verdict="BLOCKED", blocked=str(exc))
    except EngineError as exc:
        out.update(verdict="BLOCKED", blocked="%s: %s" % (type(exc).__name__, str(exc)[:300]))
    out["opens"] = card.opens()
    out["reads"] = card.reads()
    out["finds"] = [(e["path"], e["count"]) for e in card.log if e["op"] == "find"]
    out["fwlog"] = [(("%#010x" % e["caller"]), e["level"], e["func"], e["line"]) for e in s.fwlog]
    out["recog_sts"] = [o["args"][1] for o in s.m.objects if o["kind"] == "OBJ_DriveInfo_writeRecogSts"]
    out["timers"] = len([x for x in s.m.messages if x["kind"] == "timer"])
    out["mmain_sha256"] = hashlib.sha256(bytes(s.m.eng.read_mem(build["mmain_buf"], 0x1000))).hexdigest()
    out["prints"] = [p.strip() for p in s.m.prints[-8:]]
    return out, s


def show_boot(out: dict, label: str = "") -> None:
    print("boot%s: %s  states %s" % (label, out["verdict"],
                                     " -> ".join("%d/%d" % s for s in out.get("states", []))))
    if "blocked" in out:
        print("  blocked: " + out["blocked"])
    for path, file in out.get("opens", []):
        print("  open %-34s -> %s" % (path, file or "NOT FOUND"))
    for r in out.get("reads", []):
        print("  read %-34s off=%#x len=%#x got=%#x" % tuple(r))
    for path, count in out.get("finds", []):
        print("  find %-34s -> %d entries" % (path, count))
    if "dirs" in out:
        print("  volume table: %d directories, %d files, sha256 %s" % (out["dirs"], out["files"], out["tree_sha256"]))
    print("  firmware error log calls: %d%s" % (len(out.get("fwlog", [])),
          "".join("  [%s lvl %d fn %d line %d]" % tuple(e) for e in out.get("fwlog", [])[:4])))
    print("  recognition status writes: %s, retry timers: %d" % (out.get("recog_sts"), out.get("timers", 0)))


def cmd_boot(args) -> int:
    card = make_card(args.card_root, args.card_image, parse_mods(args))
    out, s = boot_report(args.image, card, args.trace_imports, build=BUILDS[args.build])
    show_boot(out)
    if args.tree and s is not None and out["verdict"] == "ACCEPT":
        for d in s.tree():
            print("  dir id %-3d parent %-3d %-24s %d entries" % (d["id"], d["parent"], d["path"] or "/", len(d["entries"])))
    if args.json:
        Path(args.json).write_text(json.dumps(out, indent=1))
    return {"ACCEPT": 0, "REJECT": 1}.get(out["verdict"], 3)


def cmd_compare(args) -> int:
    a, _ = boot_report(args.image, make_card(args.card_root, args.card_image), build=BUILDS[args.build])
    b, _ = boot_report(args.image, make_card(args.other_root, args.other_image, parse_mods(args)), build=BUILDS[args.build])
    show_boot(a, " A")
    show_boot(b, " B")
    keys = ("verdict", "states", "reads", "tree_sha256", "mmain_sha256", "recog_sts")
    diff = [k for k in keys if a.get(k) != b.get(k)]
    print("compare: %s" % ("SAME (verdict, states, read log, volume table, MMAIN bytes)" if not diff
                           else "DIFFERENT in " + ", ".join(diff)))
    if "BLOCKED" in (a["verdict"], b["verdict"]):
        return 3
    return 1 if diff else 0


def check_file(s: Session, exp: Expected, f: dict, nbytes: int) -> dict:
    """Read the head and the tail of one file through the firmware and compare."""
    spans = [(0, min(nbytes, f["size"]))]
    tail = (max(0, f["size"] - nbytes) // SECTOR) * SECTOR
    if tail > 0 and f["size"] > nbytes:
        spans.append((tail, f["size"] - tail))
    row = {"path": f["path"], "size": f["size"], "checked": 0, "status": "OK"}
    for off, n in spans:
        if n % 4:
            # the read API takes lengths in multiples of 4 and refuses a range
            # past the end of the file, so the last size%4 bytes are out of reach
            row["unreachable_tail"] = n % 4
            n -= n % 4
        if n <= 0:
            continue
        status, data = s.read(f["path"], off, n)
        try:
            want = exp.read(f["path"], off, n)
        except HostReject as exc:
            row["status"] = "HOST-REJECT " + str(exc)[:80]
            break
        if status:
            row["status"] = "READ-ERROR %#x at %#x" % (status & M32, off)
        elif want is None:
            row["status"] = "NO-HOST-FILE"
        elif data != want:
            at = next((i for i, (x, y) in enumerate(zip(data, want)) if x != y), min(len(data), len(want)))
            row["status"] = "MISMATCH at %#x (got %d B, want %d B)" % (off + at, len(data), len(want))
        if row["status"] != "OK":
            break
        row["checked"] += n
    return row


def cmd_read(args) -> int:
    card = make_card(args.card_root, args.card_image, parse_mods(args))
    out, s = boot_report(args.image, card, args.trace_imports, build=BUILDS[args.build])
    if out["verdict"] != "ACCEPT":
        show_boot(out)
        return {"REJECT": 1}.get(out["verdict"], 3)
    try:
        f = s.find_file(args.file)
        length = args.length if args.length is not None else f["size"] - args.offset
        mark = len(card.log)
        if args.swap and (args.offset % 2 or length % 2):
            raise Blocked("--swap needs an even offset and length")
        status, data = s.read(args.file, args.offset, length, swap=args.swap)
        try:
            want, host_error = Expected(card).read(f["path"], args.offset, length), None
            if args.swap and want is not None:
                # request word +20 = 0: the completion routine swaps each byte pair
                want = bytes(want[i ^ 1] for i in range(len(want) & ~1))
        except HostReject as exc:
            want, host_error = None, str(exc)
    except (Blocked, EngineError) as exc:
        print("BLOCKED: %s" % str(exc)[:400])
        return 3
    print("%s: file id %#x, size %d; read [%#x, +%#x) -> status %#x, %d bytes, sha256 %s"
          % (f["path"], f["fid"], f["size"], args.offset, length, status & M32, len(data),
             hashlib.sha256(data).hexdigest()))
    for e in card.log[mark:][:args.show]:
        if e["op"] == "open":
            print("  open %-44s -> %s" % (e["path"], e["file"] or "NOT FOUND"))
        elif e["op"] == "read":
            print("  read %-44s off=%#x len=%#x got=%#x" % (e["file"], e["offset"], e["length"], e["got"]))
    if args.output:
        Path(args.output).write_bytes(data)
    for e in s.fwlog[len(out["fwlog"]):][:4]:
        print("  firmware error log: caller %#010x level %d function %d line %d value %#x"
              % (e["caller"], e["level"], e["func"], e["line"], e["value"]))
    if host_error:
        print("  host decoder rejects the file: " + host_error)
    if status:
        print("  firmware: %s" % STATUS_TEXT.get(status, "completion with error %d" % (status - 0x100)))
        return 1
    if host_error:
        print("  firmware returned data the host decoder refuses")
        return 1
    if want is None:
        print("  no host-side expectation for this path (not on the card as a file or .cmp/.ind pair)")
        return 3
    same = data == want
    print("  host decode of the same range: %s" % ("IDENTICAL" if same else "DIFFERENT"))
    return 0 if same else 1


def cmd_sweep(args) -> int:
    card = make_card(args.card_root, args.card_image, parse_mods(args))
    out, s = boot_report(args.image, card, build=BUILDS[args.build])
    if out["verdict"] != "ACCEPT":
        show_boot(out)
        return {"REJECT": 1}.get(out["verdict"], 3)
    exp = Expected(card)
    files = [f for f in s.files() if not args.dir or f["path"].lower().startswith(args.dir.lower().strip("/") + "/")
             or (args.dir == "/" and "/" not in f["path"])]
    if args.limit:
        files = files[:args.limit]
    rows, bad, blocked = [], 0, None
    for f in files:
        try:
            row = check_file(s, exp, f, args.bytes)
        except (Blocked, EngineError) as exc:
            blocked = "%s: %s" % (f["path"], str(exc)[:300])
            break
        rows.append(row)
        bad += row["status"] != "OK"
        if row["status"] != "OK" or args.verbose:
            note = " (last %d B not reachable: length must be a multiple of 4)" % row["unreachable_tail"] \
                if row.get("unreachable_tail") else ""
            print("  %-40s %10d B  %s%s" % (row["path"], row["size"], row["status"], note), flush=True)
    total = sum(r["checked"] for r in rows)
    print("sweep: %d files, %d OK, %d not OK, %d bytes compared through the firmware"
          % (len(rows), len(rows) - bad, bad, total))
    if blocked:
        print("BLOCKED at " + blocked)
    if args.json:
        Path(args.json).write_text(json.dumps({"schema": "osm2leaf.vcard_sweep/v1", "boot": out,
                                               "rows": rows, "blocked": blocked}, indent=1))
    return 3 if blocked else (1 if bad else 0)


def _guest_str(m: Machine, text: str) -> int:
    va = m.malloc(len(text) + 1)
    m.put(va, text.encode("latin-1") + b"\0")
    return va


def resolve_name(s: Session, directory: str, name: str) -> int:
    """The firmware's own name lookup on its volume table; -1 = not found."""
    m = s.m
    a, b = _guest_str(m, directory), _guest_str(m, name)
    try:
        return _s32(m.call(s.b["resolve"], [a, b]))
    finally:
        m.free(a)
        m.free(b)


def cmd_lookup(args) -> int:
    card = make_card(args.card_root, args.card_image, parse_mods(args))
    out, s = boot_report(args.image, card, args.trace_imports, build=BUILDS[args.build])
    if out["verdict"] != "ACCEPT":
        show_boot(out)
        return {"REJECT": 1}.get(out["verdict"], 3)
    missing = 0
    for item in args.names:
        directory, _, name = item.replace("\\", "/").rpartition("/")
        fid = resolve_name(s, directory, name)
        missing += fid == -1
        print("  %-12s %-14s -> %s" % (directory or "/", name, "not found" if fid == -1 else "%#010x" % fid))
    return 1 if missing else 0


def cmd_trace(args) -> int:
    """Call one firmware function on a mounted card and list the files it names."""
    card = make_card(args.card_root, args.card_image, parse_mods(args))
    out, s = boot_report(args.image, card, args.trace_imports, build=BUILDS[args.build])
    if out["verdict"] != "ACCEPT":
        show_boot(out)
        return {"REJECT": 1}.get(out["verdict"], 3)
    m, events = s.m, []

    live = [True]

    def on_resolve(engine, va):
        if live[0]:
            events.append(("resolve", m.cstr(m.arg(0)), m.cstr(m.arg(1)), (m.reg("pr") - 4) & M32))
        return None

    def on_client(label):
        def handler(engine, va):
            if live[0]:
                events.append((label, m.arg(0), m.arg(1), (m.reg("pr") - 4) & M32))
            return None
        return handler

    ctx = m.malloc(0x800)
    m.put(ctx, bytes(0x800))
    for spec in args.ctx or []:
        off, _, val = spec.partition("=")
        m.put(ctx + int(off, 0), struct.pack("<I", int(val, 0) & M32))
    argv = [ctx if a == "ctx" else int(a, 0) for a in (args.args.split(",") if args.args else [])]
    mark, msgs, stop = len(card.log), len(m.messages), None
    # hooks go in after the mount so the trace shows the function under test only
    m.eng.on_exec(s.b["resolve"], on_resolve)
    for va, label in s.b["read_clients"].items():
        m.eng.on_exec(va, on_client(label))
    try:
        r0 = m.call(int(args.va, 0), argv, max_insns=args.max_insns)
    except (Blocked, EngineError) as exc:
        r0, stop = None, str(exc)[:200]
    live[0] = False
    print("%s(%s) -> %s" % (args.va, args.args or "", "stopped: " + stop if stop else "r0=%#x" % r0))
    rows = []
    for e in events:
        if e[0] == "resolve":
            fid = resolve_name(s, e[1], e[2])
            rows.append({"event": "resolve", "dir": e[1], "name": e[2], "caller": "%#010x" % e[3],
                         "fid": None if fid == -1 else "%#010x" % fid})
            print("  resolve %-10s %-14s from %#010x -> %s" % (e[1], e[2], e[3],
                                                                "not found" if fid == -1 else "%#010x" % fid))
        else:
            rows.append({"event": e[0], "r4": "%#x" % e[1], "r5": "%#x" % e[2], "caller": "%#010x" % e[3]})
            print("  %s (r4=%#x, r5=%#x) from %#010x" % e)
    for e in card.log[mark:][:args.show]:
        if e["op"] == "open":
            print("  open %-44s -> %s" % (e["path"], e["file"] or "NOT FOUND"))
        elif e["op"] == "read":
            print("  read %-44s off=%#x len=%#x got=%#x" % (e["file"], e["offset"], e["length"], e["got"]))
    sends = [x for x in m.messages[msgs:] if x["kind"] == "send"]
    print("  messages sent: %d%s" % (len(sends), "".join("  [task %#x]" % x["task"] for x in sends[:4])))
    if args.json:
        Path(args.json).write_text(json.dumps({"schema": "osm2leaf.vcard_trace/v1", "va": args.va,
                                               "args": args.args, "ctx": args.ctx, "stop": stop,
                                               "events": rows}, indent=1))
    return 3 if stop and not rows else 0


def cmd_call(args) -> int:
    card = make_card(args.card_root, args.card_image)
    m = load_machine(args.image, card, args.trace_imports)
    card.set_mount(m.wstr(BUILDS[args.build]["volume_root_w"]))
    try:
        for va in args.va:
            print("%s -> r0=%#x" % (va, m.call(int(va, 0))))
    except (Blocked, EngineError) as exc:
        print("BLOCKED: %s" % str(exc)[:400])
    for e in card.log[:60]:
        print("  %s" % e)
    for msg in m.messages[:10]:
        print("  message %s" % msg)
    for line in m.prints[-10:]:
        print("  print: " + line.rstrip()[:200])
    return 0


def load_machine(image_path: str, card: Card, trace: bool = False) -> Machine:
    image = Path(image_path).read_bytes()
    digest = hashlib.sha256(image[:1 << 20]).hexdigest()[:16]
    cache = Path(image_path).resolve().parent / "work" / ("vcard_navi_sec1_%s.bin" % digest)
    text = subprocess.run([sys.executable, str(HERE / "cerom.py"), "--image-start", hex(IMAGE_A),
                           image_path, "imports", "Navi.exe", "--resolve-with", hex(IMAGE_B)],
                          capture_output=True, text=True).stdout
    # imports by ordinal get the exporter's own name (C-4624)
    from callgraph import parse_exports
    lines, tables = [], {}
    for line in text.splitlines():
        parts = line.split()
        if "slot=" in line and len(parts) > 2 and parts[2].startswith("#"):
            dll = parts[0]
            if dll not in tables:
                out = subprocess.run([sys.executable, str(HERE / "cerom.py"), "--image-start", hex(IMAGE_A),
                                      image_path, "exports", dll], capture_output=True, text=True).stdout
                tables[dll] = parse_exports(out)
            parts[2] = tables[dll].get(parts[2], parts[2])
            line = " ".join(parts)
        lines.append(line)
    return Machine(image, card, data_cache=cache, imports_text="\n".join(lines), trace_imports=trace)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")

    def common(p, mods=True):
        p.add_argument("image", help="first 256 MiB of the card image (the firmware)")
        p.add_argument("--card-root", help="extracted card tree")
        p.add_argument("--card-image", help="raw SD image; its FAT32 partition is read in place")
        p.add_argument("--trace-imports", action="store_true")
        p.add_argument("--json")
        p.add_argument("--build", choices=sorted(BUILDS), default="eu2011",
                       help="Navi.exe build of IMAGE (its map-file layer VAs)")
        if mods:
            p.add_argument("--hide", action="append", metavar="PATH", help="the file is not on the card")
            p.add_argument("--replace", action="append", metavar="PATH=FILE", help="serve FILE's bytes as PATH")
            p.add_argument("--flip", action="append", metavar="PATH@OFF[:XOR]", help="xor one byte (default 0xff)")
            p.add_argument("--truncate", action="append", metavar="PATH@N", help="keep the first N bytes")

    p = sub.add_parser("boot", help="mount the card with the firmware's state machine")
    common(p)
    p.add_argument("--tree", action="store_true", help="print the firmware's directory table")
    p = sub.add_parser("compare", help="boot two cards; exit 0 when the firmware cannot tell them apart")
    common(p)
    p.add_argument("--other-root")
    p.add_argument("--other-image")
    p = sub.add_parser("read", help="read one file through the firmware and compare with a host decode")
    common(p)
    p.add_argument("file")
    p.add_argument("--offset", type=lambda x: int(x, 0), default=0)
    p.add_argument("--length", type=lambda x: int(x, 0))
    p.add_argument("-o", "--output")
    p.add_argument("--show", type=int, default=12, help="card accesses to print")
    p.add_argument("--swap", action="store_true",
                   help="ask the layer for its 16-bit byte swap; the expectation is swapped too")
    p = sub.add_parser("sweep", help="read head and tail of every file through the firmware")
    common(p)
    p.add_argument("--dir", help="only this directory (\"/\" = root files)")
    p.add_argument("--bytes", type=lambda x: int(x, 0), default=0x4000)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("-v", "--verbose", action="store_true")
    p = sub.add_parser("lookup", help="resolve DIR/NAME with the firmware's own name lookup")
    common(p)
    p.add_argument("names", nargs="+", metavar="DIR/NAME")
    p = sub.add_parser("trace", help="call one function on the mounted card; list the names it resolves")
    common(p)
    p.add_argument("va")
    p.add_argument("--args", help="comma-separated r4..r7; the word ctx = a zeroed 2 KiB block")
    p.add_argument("--ctx", action="append", metavar="OFF=VALUE", help="store a 32-bit value in the block")
    p.add_argument("--max-insns", type=int, default=3_000_000)
    p.add_argument("--show", type=int, default=8)
    p = sub.add_parser("port", help="check the US2011 layer dict against the EU2011 one (pdata + literal pools)")
    p.add_argument("image", help="EU2011 head (archive/head256.img)")
    p.add_argument("other", help="US2011 head (archive/us256.img)")
    p = sub.add_parser("call", help="research: call raw VAs in order")
    common(p, mods=False)
    p.add_argument("va", nargs="+")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not args.cmd:
        ap.print_help()
        return 2
    if args.cmd == "port":
        return cmd_port(args)
    paths = [args.image, args.card_root, args.card_image,
             getattr(args, "other_root", None), getattr(args, "other_image", None)]
    for path in paths:
        if path and not Path(path).exists():
            print("error: missing input %s" % path, file=sys.stderr)
            return 2
    if not (args.card_root or args.card_image):
        print("error: give --card-root or --card-image", file=sys.stderr)
        return 2
    try:
        return {"boot": cmd_boot, "compare": cmd_compare, "read": cmd_read,
                "sweep": cmd_sweep, "call": cmd_call, "lookup": cmd_lookup,
                "trace": cmd_trace}[args.cmd](args)
    except Blocked as exc:
        print("BLOCKED: %s" % exc)
        return 3


def selftest() -> int:
    """Host-side logic on a synthetic card; the firmware part runs only when
    the git-ignored images are present (skipped otherwise, and said so)."""
    fails = []

    def check(name, cond):
        print("  %-62s %s" % (name, "ok" if cond else "FAIL"))
        if not cond:
            fails.append(name)

    files = {"CMP.LST": b"\\SystemSD\\REFER001\\", "MMAIN001.DAT": bytes(range(256)) * 16,
             "MAPAL001/B28R070R.DAT": b"tile" * 1024, "REFER001/POINT010.DAT.cmp": b"x" * 40,
             "REFER001/POINT010.DAT.ind": b"y" * 24}
    src = MemorySource(files)
    card = Card(src)
    card.set_mount("\\SystemSD")
    h = card.fopen("\\SystemSD\\mapal001\\b28r070r.dat", "rb")
    check("open is case-insensitive and strips the mount prefix", h != 0)
    card.fseek(h, 8, 0)
    check("seek + read return the file's bytes", card.fread(h, 8) == b"tiletile" and card.ftell(h) == 16)
    card.fseek(h, 0, 2)
    check("seek to end reports the size", card.ftell(h) == 4096 and card.fread(h, 4) == b"")
    card.fclose(h)
    check("a missing file does not open", card.fopen("\\SystemSD\\NOPE.DAT", "rb") == 0)
    check("a path outside the mount does not open", card.fopen("\\Other\\CMP.LST", "rb") == 0)
    check("the read log has offset, length, bytes returned",
          card.reads() == [("MAPAL001/B28R070R.DAT", 8, 8, 8), ("MAPAL001/B28R070R.DAT", 4096, 4, 0)])
    check("the open log records the miss", card.opens()[1] == ("\\SystemSD\\NOPE.DAT", None))
    names = sorted(e.name for e in card.find("\\SystemSD\\*"))
    check("find lists the root", names == ["CMP.LST", "MAPAL001", "MMAIN001.DAT", "REFER001"])

    class A:
        hide, replace, flip, truncate = ["CMP.LST"], [], ["MMAIN001.DAT@0x10:0x01"], ["MAPAL001/B28R070R.DAT@6"]
    mod = make_card(None, None, parse_mods(A), source=src)
    mod.set_mount("\\SystemSD")
    check("--hide removes the file", mod.fopen("\\SystemSD\\CMP.LST", "rb") == 0)
    h = mod.fopen("\\SystemSD\\MMAIN001.DAT", "rb")
    data = mod.fread(h, 32)
    check("--flip changes exactly one byte", data[0x10] == 0x11 and data[:0x10] == bytes(range(16))
          and data[0x11:] == bytes(range(0x11, 32)))
    h = mod.fopen("\\SystemSD\\MAPAL001\\B28R070R.DAT", "rb")
    check("--truncate shortens the file", mod.fread(h, 100) == b"tileti")
    mod.fseek(h, 0, 2)
    check("--truncate reports the short size", mod.ftell(h) == 6)
    try:
        make_card(None, None, {"flip": ["NOPE.DAT@0"]}, source=src)
        check("a modification of a missing file is refused", False)
    except Blocked:
        check("a modification of a missing file is refused", True)

    exp = Expected(Card(src))
    check("host expectation of a plain file", exp.read("MAPAL001/B28R070R.DAT", 4, 8) == b"tiletile")
    check("host expectation of an absent file is None", exp.read("MAPAL001/NOPE.DAT", 0, 4) is None)
    try:
        exp.read("REFER001/POINT010.DAT", 0, 4)
        check("a broken .cmp/.ind pair is a HostReject, not data", False)
    except HostReject:
        check("a broken .cmp/.ind pair is a HostReject, not data", True)

    args = iter([7, 0x1234, 100])
    text = format_c("n=%d h=%08x s=%s", lambda: next(args), lambda va: "str@%d" % va, lambda va: "w")
    check("printf subset", text == "n=7 h=00001234 s=str@100")
    check("signed 32-bit helper", _s32(0xFFFFFFF4) == -12 and _s32(5) == 5)
    check("every import model is callable", all(callable(f) for f in MODELS.values()) and len(MODELS) > 60)

    def mem(words):
        return lambda va: words.get(va)
    eu = mem({0x100: 0xD100, 0x102: 0x000B, 0x104: 0x5678, 0x106: 0x1234})
    us = mem({0x200: 0xD100, 0x202: 0x000B, 0x204: 0xDEF0, 0x206: 0x9ABC})
    got = port_data([(0x100, 0x200)], eu, us, {0x100: 8}, {0x12345678: "state"})
    check("port: the US pool value at the same load index", got == {"state": {0x9ABCDEF0: 1}})
    check("port: an EU value no pool loads is not found",
          port_data([(0x100, 0x200)], eu, us, {0x100: 8}, {0x11111111: "x"}) == {})
    check("port: the US dict pairs every EU layer function",
          len(port_pairs(EU2011, US2011)) == 13 and set(EU2011) == set(US2011))
    with tempfile.TemporaryDirectory() as tmp:
        fake = Path(tmp) / "head.img"
        fake.write_bytes(b"not a head")
        out, sess = boot_report(str(fake), Card(src), build=US2011)
        check("a head of another build is BLOCKED before the engine starts",
              out["verdict"] == "BLOCKED" and "us2011" in out["blocked"] and sess is None)

    head = HERE.parent / "archive" / "head256.img"
    full = HERE.parent / "archive" / "sd-images" / "LEAF_2011-2012_QSD-309-101_navi158_eu.img"
    if head.exists() and full.exists():
        out, s = boot_report(str(head), make_card(None, str(full)))
        check("firmware mounts the factory EU card", out["verdict"] == "ACCEPT" and out["dirs"] == 40
              and [r[:3] for r in out["reads"]] == [("CMP.LST", 0, 0x13), ("MMAIN001.DAT", 0, 0x1000),
                                                    ("DRSTR001.DAT", 0, 0x2EC0)])
        status, data = s.read("MAPAL001/B28R070R.DAT", 0, 0x800)
        check("firmware read of a tile equals the card bytes",
              status == 0 and data == Expected(s.card).read("MAPAL001/B28R070R.DAT", 0, 0x800))
        check("firmware name lookup: exact name found, lower case not",
              resolve_name(s, "REFER001", "POINT010.DAT") == 0x60089
              and resolve_name(s, "REFER001", "point010.dat") == -1)
        out, _ = boot_report(str(head), make_card(None, str(full), {"truncate": ["DRSTR001.DAT@0x800"]}))
        check("a truncated DRSTR001.DAT is rejected by the firmware", out["verdict"] == "REJECT")
    else:
        print("  firmware checks skipped: archive/head256.img and the full EU image are not both present")
    print("vcard_l3 selftest: %s" % ("FAIL (%d)" % len(fails) if fails else "ok"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
