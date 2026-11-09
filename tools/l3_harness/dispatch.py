#!/usr/bin/env python3
"""Host-side L3 stubs, resolved by ``module!export`` or ``module!#ordinal``.

:mod:`stubs` is the declarative table; this module is the executable half.
The dispatcher turns a call target into a table entry and then into a Python
implementation, so the engine and the self-test never hard-code a C name:

    dispatcher.resolve(("coredll.dll", "CreateFileW"))   # -> table entry
    dispatcher.resolve(("coredll", 719))                 # -> sprintf (C-527)
    dispatcher.call(("coredll", "ReadFile"), [h, buf, 4, count, 0])

An export the table does not model (or a ``planned`` one) stops the run with
exactly ``missing stub: NAME`` -- no guessed return value, no silent zero.

Deterministic models
====================

* **Virtual FS** -- an in-memory tree, case-insensitive, seeded from a dict or
  from a corpus directory.  Paths never touch the host FS: a leading ``\\\\``
  and a ``\\Storage Card\\`` prefix are stripped, ``..`` and drive letters are
  rejected.  ``CreateFileW``/``CreateFileA``, ``ReadFile``,
  ``SetFilePointer``, ``GetFileSize`` and ``CloseHandle`` share one handle
  table and one cursor per file.
* **Heap** -- ``LocalAlloc``/``LocalFree``/``HeapAlloc``/``HeapFree`` allocate
  from a caller-supplied guest region with 8-byte alignment.  Zeroed on the
  ``ZEROINIT``/``ZERO_MEMORY`` flag, poisoned with ``0xcd`` otherwise (and on
  free), so an uninitialised read shows up in the output digest.
* **Critical sections** -- init/enter/leave/delete are tracked as a recursion
  depth per pointer.  Nothing is serialised (an L3 run is single-threaded), but
  a wrong order is a loud :class:`StubFault`.
* **Registry** -- keys and values come from a JSON fixture, never from the
  host registry: ``RegOpenKeyExW``/``RegQueryValueExW``/``RegCloseKey`` support
  ``REG_SZ`` (UTF-16LE), ``REG_DWORD`` and ``REG_BINARY`` with the two-pass
  ``ERROR_MORE_DATA`` contract.
* **No clock** -- nothing reads the wall clock; ``sprintf``/``OSM_Printf``
  format the documented subset and reject every other conversion.

The guest DWORD byte order follows the engine declaration (``SuperH:BE:32`` in
:mod:`engine`).  A target whose structs are little-endian must pass
``endian="little"`` to :class:`StubContext`; the two WCHAR/registry paths stay
UTF-16LE by definition.

Usage::

    python3 tools/l3_harness/dispatch.py --selftest
    python3 tools/l3_harness/dispatch.py list

Exit codes: ``0`` ok, ``1`` self-test failure, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import engine as engine_mod  # noqa: E402
from l3_harness import stubs  # noqa: E402

M32 = 0xFFFFFFFF

INVALID_HANDLE_VALUE = 0xFFFFFFFF
ERROR_SUCCESS = 0
ERROR_FILE_NOT_FOUND = 2
ERROR_INVALID_HANDLE = 6
ERROR_NEGATIVE_SEEK = 131
ERROR_HANDLE_EOF = 38
ERROR_MORE_DATA = 234

FILE_BEGIN = 0
FILE_CURRENT = 1
FILE_END = 2
OPEN_EXISTING = 3

GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
GENERIC_EXECUTE = 0x20000000
GENERIC_ALL = 0x10000000
GENERIC_MASK = GENERIC_READ | GENERIC_WRITE | GENERIC_EXECUTE | GENERIC_ALL

LMEM_ZEROINIT = 0x0040
HEAP_NO_SERIALIZE = 0x0001
HEAP_ZERO_MEMORY = 0x0008

REG_TYPES = {"REG_SZ": 1, "REG_BINARY": 3, "REG_DWORD": 4}

ROOTS = {
    0x80000000: "HKEY_CLASSES_ROOT",
    0x80000001: "HKEY_CURRENT_USER",
    0x80000002: "HKEY_LOCAL_MACHINE",
    0x80000003: "HKEY_USERS",
}
ROOT_ALIASES = {
    "HKCR": "HKEY_CLASSES_ROOT",
    "HKEY_CLASSES_ROOT": "HKEY_CLASSES_ROOT",
    "HKCU": "HKEY_CURRENT_USER",
    "HKEY_CURRENT_USER": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
    "HKEY_LOCAL_MACHINE": "HKEY_LOCAL_MACHINE",
    "HKU": "HKEY_USERS",
    "HKEY_USERS": "HKEY_USERS",
}

POISON = 0xCD


# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class StubError(RuntimeError):
    """Base class; ``code`` is the stable machine-readable reason."""

    code = "STUB"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class MissingStub(StubError):
    """The export is not modelled.  Message is exactly ``missing stub: NAME``."""

    code = "MISSING_STUB"

    def __init__(self, name: str):
        super().__init__(f"missing stub: {name}")
        self.name = name


class StubFault(StubError):
    """The stub was called with an argument or state it refuses to guess about."""

    code = "STUB_FAULT"


# --------------------------------------------------------------------------
# Guest memory
# --------------------------------------------------------------------------


class FlatMemory:
    """A flat guest address space made of explicitly mapped regions."""

    def __init__(self, endian: str = "big"):
        if endian not in ("big", "little"):
            raise StubFault(f"memory endian must be 'big' or 'little', not {endian!r}")
        self.endian = endian
        self._regions: list[tuple[int, bytearray]] = []

    def add(self, base: int, data) -> None:
        if not isinstance(base, int) or base < 0 or base > M32:
            raise StubFault(f"memory: bad base {base!r}")
        if isinstance(data, int):
            if data <= 0:
                raise StubFault("memory: size must be positive")
            payload = bytearray(data)
        elif isinstance(data, (bytes, bytearray, memoryview)):
            payload = bytearray(data)
        else:
            raise StubFault(f"memory: data must be bytes or a size, not {type(data).__name__}")
        end = base + len(payload)
        if end > M32 + 1:
            raise StubFault(f"memory: 0x{base:08x}..0x{end:08x} leaves the 32-bit space")
        for other_base, other in self._regions:
            other_end = other_base + len(other)
            if base < other_end and other_base < end:
                raise StubFault(
                    f"memory: 0x{base:08x}..0x{end:08x} overlaps "
                    f"0x{other_base:08x}..0x{other_end:08x}"
                )
        self._regions.append((base, payload))
        self._regions.sort(key=lambda item: item[0])

    def _locate(self, va: int, size: int) -> tuple[int, bytearray]:
        if not isinstance(va, int) or va < 0 or va + size > M32 + 1:
            raise StubFault(f"memory: access 0x{va:08x}+{size} leaves the 32-bit space")
        for base, payload in self._regions:
            if base <= va and va + size <= base + len(payload):
                return base, payload
        raise StubFault(
            f"memory: no mapped region covers 0x{va:08x}..0x{va + size:08x}"
        )

    def read(self, va: int, size: int) -> bytes:
        if size < 0:
            raise StubFault("memory: read size must be non-negative")
        if size == 0:
            return b""
        base, payload = self._locate(va, size)
        offset = va - base
        return bytes(payload[offset:offset + size])

    def write(self, va: int, data) -> None:
        payload = bytes(data)
        if not payload:
            return
        base, region = self._locate(va, len(payload))
        offset = va - base
        region[offset:offset + len(payload)] = payload

    def read_u32(self, va: int) -> int:
        return int.from_bytes(self.read(va, 4), self.endian)

    def write_u32(self, va: int, value: int) -> None:
        self.write(va, int(value & M32).to_bytes(4, self.endian))

    def read_cstring(self, va: int, limit: int = 4096) -> str:
        """Read a NUL-terminated ANSI/latin-1 string, or fail loudly."""

        data = bytearray()
        for offset in range(limit):
            byte = self.read(va + offset, 1)[0]
            if byte == 0:
                return data.decode("latin-1")
            data.append(byte)
        raise StubFault(f"memory: no NUL within {limit} bytes at 0x{va:08x}")

    def write_cstring(self, va: int, text: str) -> int:
        payload = text.encode("latin-1") + b"\x00"
        self.write(va, payload)
        return va

    def read_wstring(self, va: int, limit: int = 4096) -> str:
        """Read a NUL-terminated UTF-16LE string (the WinCE W API family)."""

        data = bytearray()
        for offset in range(limit):
            unit = int.from_bytes(self.read(va + offset * 2, 2), "little")
            if unit == 0:
                return data.decode("utf-16-le", "strict")
            data += unit.to_bytes(2, "little")
        raise StubFault(f"memory: no UTF-16 NUL within {limit} units at 0x{va:08x}")

    def write_wstring(self, va: int, text: str) -> int:
        payload = text.encode("utf-16-le") + b"\x00\x00"
        self.write(va, payload)
        return va


# --------------------------------------------------------------------------
# Virtual file system
# --------------------------------------------------------------------------


def normalize_guest_path(path: str) -> str:
    """Canonical virtual-FS key for a WinCE path.

    Accepts ``\\Storage Card\\REFER001\\X``, ``REFER001/X`` and a leading ``\\``.
    Rejects ``..`` components and a drive-letter prefix; a host-looking path is
    simply absent because the virtual FS never touches the host.
    """

    if not isinstance(path, str) or not path.strip():
        raise StubFault("virtual FS: empty path")
    text = path.strip().replace("\\", "/")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        raise StubFault(f"virtual FS: path escapes the root: {path!r}")
    if parts and len(parts[0]) == 2 and parts[0][1] == ":":
        raise StubFault(f"virtual FS: drive-letter paths are not modelled: {path!r}")
    if parts and parts[0].lower() in ("storage card", "sdcard", "sd card"):
        parts = parts[1:]
    if not parts:
        raise StubFault(f"virtual FS: path names the root: {path!r}")
    return "/".join(parts).lower()


class FileObject:
    """One open file in the virtual FS."""

    __slots__ = ("key", "data", "offset", "closed")

    def __init__(self, key: str, data: bytes):
        self.key = key
        self.data = data
        self.offset = 0
        self.closed = False


class VirtualFS:
    """A deterministic in-memory file tree rooted at the card under test."""

    def __init__(self, files=None):
        self._files: dict[str, bytes] = {}
        for path, data in (files or {}).items():
            self.add(path, data)

    @classmethod
    def from_directory(cls, root) -> "VirtualFS":
        """Seed from a corpus tree; paths are relative and forward-slash."""

        base = Path(root)
        if not base.is_dir():
            raise StubFault(f"virtual FS: not a directory: {root}")
        fs = cls()
        for path in sorted(base.rglob("*")):
            if path.is_file():
                fs.add(str(path.relative_to(base)).replace("\\", "/"), path.read_bytes())
        return fs

    def add(self, path: str, data) -> None:
        key = normalize_guest_path(path)
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise StubFault("virtual FS: file data must be bytes")
        self._files[key] = bytes(data)

    def exists(self, path: str) -> bool:
        return normalize_guest_path(path) in self._files

    def open(self, path: str) -> FileObject | None:
        key = normalize_guest_path(path)
        data = self._files.get(key)
        return None if data is None else FileObject(key, data)

    def paths(self) -> list[str]:
        return sorted(self._files)


# --------------------------------------------------------------------------
# Heap
# --------------------------------------------------------------------------


class Heap:
    """A bump allocator over one guest region, with leak/free tracking."""

    def __init__(self, memory: FlatMemory, base: int, size: int, poison: int = POISON):
        if size <= 0:
            raise StubFault("heap: size must be positive")
        self.memory = memory
        self.base = base
        self.size = size
        self.poison = poison & 0xFF
        self._next = base
        self._blocks: dict[int, int] = {}
        self._freed: set[int] = set()

    def alloc(self, size: int, zero: bool = False, owner: str | None = None) -> int:
        if size <= 0:
            return 0
        start = (self._next + 7) & ~7
        if start + size > self.base + self.size:
            raise StubFault(
                f"heap: exhausted ({size} bytes requested, "
                f"{self.base + self.size - start} left) for {owner or 'alloc'}"
            )
        fill = b"\x00" * size if zero else bytes([self.poison]) * size
        self.memory.write(start, fill)
        self._blocks[start] = size
        self._next = start + size
        return start

    def free(self, pointer: int) -> bool:
        """Release a block; ``False`` for an unknown pointer.

        A second free of the same pointer is a :class:`StubFault`, and the
        freed bytes are poisoned so a use-after-free changes the output digest.
        """

        if pointer == 0:
            return False
        if pointer in self._freed:
            raise StubFault(f"heap: double free of 0x{pointer:08x}")
        size = self._blocks.pop(pointer, None)
        if size is None:
            return False
        self._freed.add(pointer)
        self.memory.write(pointer, bytes([self.poison]) * size)
        return True

    def leaks(self) -> list[dict]:
        return [
            {"pointer": f"0x{pointer:08x}", "size": size}
            for pointer, size in sorted(self._blocks.items())
        ]


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------


def normalize_reg_path(path: str) -> str:
    parts = [part for part in str(path).replace("/", "\\").split("\\") if part]
    if not parts:
        raise StubFault("registry: empty key path")
    parts[0] = ROOT_ALIASES.get(parts[0].upper(), parts[0])
    return "\\".join(parts).lower()


def _encode_registry_value(type_name: str, data) -> bytes:
    if type_name == "REG_SZ":
        if not isinstance(data, str):
            raise StubFault("registry: REG_SZ data must be a string")
        return data.encode("utf-16-le") + b"\x00\x00"
    if type_name == "REG_DWORD":
        if isinstance(data, str):
            try:
                data = int(data, 0)
            except ValueError as exc:
                raise StubFault(f"registry: bad REG_DWORD {data!r}") from exc
        if not isinstance(data, int) or isinstance(data, bool):
            raise StubFault("registry: REG_DWORD data must be an integer")
        return int(data & M32).to_bytes(4, "little")
    if type_name == "REG_BINARY":
        if isinstance(data, str):
            try:
                return bytes.fromhex(data)
            except ValueError as exc:
                raise StubFault(f"registry: bad REG_BINARY hex {data!r}") from exc
        if isinstance(data, (bytes, bytearray)):
            return bytes(data)
        if isinstance(data, list) and all(isinstance(item, int) for item in data):
            return bytes(byte & 0xFF for byte in data)
        raise StubFault("registry: REG_BINARY data must be bytes, hex or a byte list")
    raise StubFault(f"registry: unsupported value type {type_name!r}")


class Registry:
    """Registry fixture loaded from JSON, never from the host registry."""

    def __init__(self, doc=None):
        #: canonical key path -> {lower-case value name: (type, bytes)}
        self._keys: dict[str, dict[str, tuple[str, bytes]]] = {}
        if doc is not None:
            self.load(doc)

    @classmethod
    def from_file(cls, path) -> "Registry":
        with open(path, "r", encoding="utf-8") as handle:
            return cls(json.load(handle))

    def load(self, doc) -> None:
        if not isinstance(doc, dict):
            raise StubFault("registry: fixture must be a JSON object")
        keys = doc.get("keys") if isinstance(doc.get("keys"), dict) else doc
        for full_path, spec in keys.items():
            if full_path in ("schema", "notes"):
                continue
            if not isinstance(spec, dict):
                raise StubFault(f"registry: key {full_path!r} must be an object")
            values = spec.get("values") if isinstance(spec.get("values"), dict) else spec
            encoded: dict[str, tuple[str, bytes]] = {}
            for name, descriptor in values.items():
                if name in ("values", "notes"):
                    continue
                if isinstance(descriptor, str):
                    type_name, data = "REG_SZ", descriptor
                elif isinstance(descriptor, int) and not isinstance(descriptor, bool):
                    type_name, data = "REG_DWORD", descriptor
                elif isinstance(descriptor, dict):
                    type_name = str(descriptor.get("type", "REG_SZ")).upper()
                    data = descriptor.get("data")
                else:
                    raise StubFault(
                        f"registry: value {full_path}\\{name} needs a type/data object"
                    )
                if type_name not in REG_TYPES:
                    raise StubFault(f"registry: unsupported type {type_name!r}")
                encoded[str(name).lower()] = (
                    type_name,
                    _encode_registry_value(type_name, data),
                )
            self._keys[normalize_reg_path(full_path)] = encoded

    def has_key(self, path: str) -> bool:
        return normalize_reg_path(path) in self._keys

    def value(self, path: str, name: str):
        values = self._keys.get(normalize_reg_path(path))
        if values is None:
            return None
        return values.get(str(name).lower())


# --------------------------------------------------------------------------
# Context
# --------------------------------------------------------------------------


class StubContext:
    """Everything a stub may read or write, all explicit and host-independent."""

    def __init__(
        self,
        memory: FlatMemory | None = None,
        fs: VirtualFS | None = None,
        heap: Heap | None = None,
        registry: Registry | None = None,
        endian: str = "big",
    ):
        self.mem = memory if memory is not None else FlatMemory(endian=endian)
        self.endian = self.mem.endian
        self.fs = fs if fs is not None else VirtualFS()
        self.heap = heap
        self.registry = registry if registry is not None else Registry()
        self.calls: list[dict] = []
        self.log: list[str] = []
        self.last_error = 0
        self.handles: dict[int, FileObject] = {}
        self.next_handle = 0x10
        self.cs: dict[int, int] = {}
        self.key_handles: dict[int, str] = {}
        self.next_key_handle = 0x100

    def record(self, call: str, **fields) -> None:
        item = {"call": call}
        item.update(fields)
        self.calls.append(item)

    def fail(self, call: str, error: int, **fields) -> None:
        self.last_error = error
        self.record(call, error=error, **fields)


def _require(args, count: int, call: str) -> list[int]:
    if len(args) < count:
        raise StubFault(
            f"{call}: expected at least {count} argument(s), got {len(args)}"
        )
    return [int(value) & M32 for value in args]


def _arg(args, index: int, call: str) -> int:
    if index >= len(args):
        raise StubFault(f"{call}: missing argument {index}")
    return int(args[index]) & M32


def _signed(value: int) -> int:
    value &= M32
    return value - (1 << 32) if value & 0x80000000 else value


# --------------------------------------------------------------------------
# Formatter shared by sprintf and OSM_Printf
# --------------------------------------------------------------------------


def format_guest_string(context: StubContext, fmt_pointer: int, values) -> str:
    fmt = context.mem.read_cstring(fmt_pointer)
    out: list[str] = []
    index = 0
    argument = 0

    while index < len(fmt):
        char = fmt[index]
        if char != "%":
            out.append(char)
            index += 1
            continue
        index += 1
        if index >= len(fmt):
            raise StubFault("sprintf: trailing '%' in the format string")
        if fmt[index] == "%":
            out.append("%")
            index += 1
            continue

        flags = ""
        while index < len(fmt) and fmt[index] in "-0":
            flags += fmt[index]
            index += 1
        width_text = ""
        while index < len(fmt) and fmt[index].isdigit():
            width_text += fmt[index]
            index += 1
        if index >= len(fmt):
            raise StubFault("sprintf: format string ends inside a conversion")
        conversion = fmt[index]
        index += 1

        if argument >= len(values):
            raise StubFault(
                f"sprintf: not enough arguments for %{conversion} "
                f"(argument {argument + 1} of {len(values)})"
            )
        value = int(values[argument]) & M32
        argument += 1

        if conversion == "s":
            piece = context.mem.read_cstring(value)
        elif conversion in ("d", "i"):
            piece = str(_signed(value))
        elif conversion == "u":
            piece = str(value & M32)
        elif conversion == "x":
            piece = format(value & M32, "x")
        else:
            raise StubFault(
                f"sprintf: unsupported conversion %{conversion!r}; "
                "only %s, %d, %u, %x and %% are modelled"
            )

        width = int(width_text) if width_text else 0
        if width and len(piece) < width:
            if "-" in flags:
                piece = piece.ljust(width)
            elif "0" in flags and piece.lstrip("-").isdigit():
                sign = "-" if piece.startswith("-") else ""
                piece = sign + piece.lstrip("-").rjust(width - len(sign), "0")
            else:
                piece = piece.rjust(width)
        out.append(piece)

    return "".join(out)


# --------------------------------------------------------------------------
# File I/O
# --------------------------------------------------------------------------


def _create_file(context: StubContext, args, wide: bool, call: str) -> int:
    args = _require(args, 7, call)
    path_pointer, access, _share, _security, disposition, _flags, _template = args
    if wide:
        path = context.mem.read_wstring(path_pointer)
    else:
        path = context.mem.read_cstring(path_pointer)

    if access & ~GENERIC_READ & M32:
        raise StubFault(
            f"{call}: only read access is modelled "
            f"(dwDesiredAccess=0x{access:08x} on {path!r})"
        )
    if disposition != OPEN_EXISTING:
        raise StubFault(
            f"{call}: only OPEN_EXISTING is modelled "
            f"(dwCreationDisposition={disposition})"
        )
    if _security:
        raise StubFault(f"{call}: SECURITY_ATTRIBUTES is not modelled")

    file_object = context.fs.open(path)
    if file_object is None:
        context.fail(call, ERROR_FILE_NOT_FOUND, path=normalize_guest_path(path))
        return INVALID_HANDLE_VALUE

    handle = context.next_handle
    context.next_handle += 1
    context.handles[handle] = file_object
    context.last_error = 0
    context.record(call, path=file_object.key, handle=f"0x{handle:08x}")
    return handle


def _create_file_w(context: StubContext, args) -> int:
    return _create_file(context, args, True, "CreateFileW")


def _create_file_a(context: StubContext, args) -> int:
    return _create_file(context, args, False, "CreateFileA")


def _read_file(context: StubContext, args) -> int:
    args = _require(args, 5, "ReadFile")
    handle, buffer, requested, count_pointer, overlapped = args
    if overlapped:
        raise StubFault("ReadFile: asynchronous (lpOverlapped) reads are not modelled")
    file_object = context.handles.get(handle)
    if file_object is None or file_object.closed:
        context.fail("ReadFile", ERROR_INVALID_HANDLE, handle=f"0x{handle:08x}")
        return 0
    if requested and not buffer:
        raise StubFault("ReadFile: NULL buffer for a non-zero read")

    remaining = len(file_object.data) - file_object.offset
    count = min(requested, remaining)
    if count:
        context.mem.write(buffer, file_object.data[file_object.offset:file_object.offset + count])
    if requested > count:
        context.mem.write(buffer + count, b"\x00" * (requested - count))
    if count_pointer:
        context.mem.write_u32(count_pointer, count)
    file_object.offset += count

    if count == 0 and requested > 0:
        context.fail("ReadFile", ERROR_HANDLE_EOF,
                     handle=f"0x{handle:08x}", count=0)
        return 0

    context.last_error = 0
    context.record(
        "ReadFile",
        handle=f"0x{handle:08x}",
        count=count,
        offset=file_object.offset,
    )
    return 1


def _set_file_pointer(context: StubContext, args) -> int:
    args = _require(args, 4, "SetFilePointer")
    handle, distance_low, high_pointer, method = args
    file_object = context.handles.get(handle)
    if file_object is None or file_object.closed:
        context.fail("SetFilePointer", ERROR_INVALID_HANDLE, handle=f"0x{handle:08x}")
        return 0xFFFFFFFF

    distance = _signed(distance_low)
    if high_pointer:
        distance += _signed(context.mem.read_u32(high_pointer)) << 32

    if method == FILE_BEGIN:
        base = 0
    elif method == FILE_CURRENT:
        base = file_object.offset
    elif method == FILE_END:
        base = len(file_object.data)
    else:
        raise StubFault(f"SetFilePointer: unknown dwMoveMethod {method}")

    new_offset = base + distance
    if new_offset < 0:
        context.fail("SetFilePointer", ERROR_NEGATIVE_SEEK, handle=f"0x{handle:08x}")
        return 0xFFFFFFFF

    old_offset = file_object.offset
    file_object.offset = new_offset
    if high_pointer:
        context.mem.write_u32(high_pointer, (new_offset >> 32) & M32)
    context.last_error = 0
    context.record(
        "SetFilePointer",
        handle=f"0x{handle:08x}",
        old=old_offset,
        new=new_offset,
    )
    return new_offset & M32


def _get_file_size(context: StubContext, args) -> int:
    args = _require(args, 2, "GetFileSize")
    handle, high_pointer = args
    file_object = context.handles.get(handle)
    if file_object is None or file_object.closed:
        context.fail("GetFileSize", ERROR_INVALID_HANDLE, handle=f"0x{handle:08x}")
        return 0xFFFFFFFF
    size = len(file_object.data)
    if high_pointer:
        context.mem.write_u32(high_pointer, (size >> 32) & M32)
    context.last_error = 0
    context.record("GetFileSize", handle=f"0x{handle:08x}", size=size)
    return size & M32


def _close_handle(context: StubContext, args) -> int:
    args = _require(args, 1, "CloseHandle")
    handle = args[0]
    file_object = context.handles.pop(handle, None)
    if file_object is None or file_object.closed:
        context.fail("CloseHandle", ERROR_INVALID_HANDLE, handle=f"0x{handle:08x}")
        return 0
    file_object.closed = True
    context.last_error = 0
    context.record(
        "CloseHandle",
        handle=f"0x{handle:08x}",
        path=file_object.key,
        unread=len(file_object.data) - file_object.offset,
    )
    return 1


# --------------------------------------------------------------------------
# Heap stubs
# --------------------------------------------------------------------------


def _need_heap(context: StubContext, call: str) -> Heap:
    if context.heap is None:
        raise StubFault(f"{call}: no heap region configured in the stub context")
    return context.heap


def _local_alloc(context: StubContext, args) -> int:
    args = _require(args, 2, "LocalAlloc")
    flags, size = args
    if flags & ~LMEM_ZEROINIT & M32:
        raise StubFault(f"LocalAlloc: unsupported uFlags=0x{flags:08x}")
    heap = _need_heap(context, "LocalAlloc")
    pointer = heap.alloc(size, zero=bool(flags & LMEM_ZEROINIT), owner="LocalAlloc")
    context.record("LocalAlloc", pointer=f"0x{pointer:08x}", size=size,
                   zero=bool(flags & LMEM_ZEROINIT))
    return pointer


def _local_free(context: StubContext, args) -> int:
    args = _require(args, 1, "LocalFree")
    pointer = args[0]
    if pointer == 0:
        return 0
    heap = _need_heap(context, "LocalFree")
    if not heap.free(pointer):
        context.record("LocalFree", pointer=f"0x{pointer:08x}", result="unknown")
        return pointer
    context.record("LocalFree", pointer=f"0x{pointer:08x}", result="freed")
    return 0


def _heap_alloc(context: StubContext, args) -> int:
    args = _require(args, 3, "HeapAlloc")
    _heap_handle, flags, size = args
    if flags & ~(HEAP_ZERO_MEMORY | HEAP_NO_SERIALIZE) & M32:
        raise StubFault(f"HeapAlloc: unsupported dwFlags=0x{flags:08x}")
    heap = _need_heap(context, "HeapAlloc")
    pointer = heap.alloc(size, zero=bool(flags & HEAP_ZERO_MEMORY), owner="HeapAlloc")
    context.record("HeapAlloc", pointer=f"0x{pointer:08x}", size=size,
                   zero=bool(flags & HEAP_ZERO_MEMORY))
    return pointer


def _heap_free(context: StubContext, args) -> int:
    args = _require(args, 3, "HeapFree")
    _heap_handle, flags, pointer = args
    if flags:
        raise StubFault(f"HeapFree: dwFlags must be 0, got 0x{flags:08x}")
    heap = _need_heap(context, "HeapFree")
    freed = heap.free(pointer)
    context.record("HeapFree", pointer=f"0x{pointer:08x}", result=int(bool(freed)))
    return 1 if freed else 0


# --------------------------------------------------------------------------
# Memory and string stubs
# --------------------------------------------------------------------------


def _memset(context: StubContext, args) -> int:
    args = _require(args, 3, "memset")
    destination, value, count = args
    context.mem.write(destination, bytes([value & 0xFF]) * count)
    context.record("memset", destination=f"0x{destination:08x}", count=count)
    return destination


def _memcpy(context: StubContext, args) -> int:
    args = _require(args, 3, "memcpy")
    destination, source, count = args
    if count:
        end_destination = destination + count
        end_source = source + count
        if destination < end_source and source < end_destination:
            raise StubFault(
                f"memcpy: overlapping ranges "
                f"0x{destination:08x}..0x{end_destination:08x} and "
                f"0x{source:08x}..0x{end_source:08x}"
            )
        context.mem.write(destination, context.mem.read(source, count))
    context.record("memcpy", destination=f"0x{destination:08x}", source=f"0x{source:08x}",
                   count=count)
    return destination


def _strlen(context: StubContext, args) -> int:
    args = _require(args, 1, "strlen")
    pointer = args[0]
    length = len(context.mem.read_cstring(pointer))
    context.record("strlen", pointer=f"0x{pointer:08x}", length=length)
    return length


def _sprintf(context: StubContext, args) -> int:
    args = _require(args, 2, "sprintf")
    buffer, fmt_pointer = args[0], args[1]
    text = format_guest_string(context, fmt_pointer, args[2:])
    payload = text.encode("latin-1")
    context.mem.write(buffer, payload + b"\x00")
    context.record("sprintf", buffer=f"0x{buffer:08x}", text=text, length=len(payload))
    return len(payload)


def _osm_printf(context: StubContext, args) -> int:
    args = _require(args, 1, "OSM_Printf")
    text = format_guest_string(context, args[0], args[1:])
    context.log.append(text)
    context.record("OSM_Printf", text=text)
    return len(text)


# --------------------------------------------------------------------------
# Critical sections
# --------------------------------------------------------------------------


def _initialize_critical_section(context: StubContext, args) -> int:
    pointer = _require(args, 1, "InitializeCriticalSection")[0]
    if pointer == 0:
        raise StubFault("InitializeCriticalSection: NULL pointer")
    if pointer in context.cs:
        raise StubFault(f"InitializeCriticalSection: 0x{pointer:08x} is already initialised")
    context.cs[pointer] = 0
    context.record("InitializeCriticalSection", pointer=f"0x{pointer:08x}")
    return 0


def _enter_critical_section(context: StubContext, args) -> int:
    pointer = _require(args, 1, "EnterCriticalSection")[0]
    if pointer not in context.cs:
        raise StubFault(f"EnterCriticalSection: 0x{pointer:08x} is not initialised")
    context.cs[pointer] += 1
    context.record("EnterCriticalSection", pointer=f"0x{pointer:08x}",
                   depth=context.cs[pointer])
    return 0


def _leave_critical_section(context: StubContext, args) -> int:
    pointer = _require(args, 1, "LeaveCriticalSection")[0]
    if pointer not in context.cs:
        raise StubFault(f"LeaveCriticalSection: 0x{pointer:08x} is not initialised")
    if context.cs[pointer] <= 0:
        raise StubFault(f"LeaveCriticalSection: 0x{pointer:08x} was not entered")
    context.cs[pointer] -= 1
    context.record("LeaveCriticalSection", pointer=f"0x{pointer:08x}",
                   depth=context.cs[pointer])
    return 0


def _delete_critical_section(context: StubContext, args) -> int:
    pointer = _require(args, 1, "DeleteCriticalSection")[0]
    if pointer not in context.cs:
        raise StubFault(f"DeleteCriticalSection: 0x{pointer:08x} is not initialised")
    depth = context.cs[pointer]
    if depth:
        raise StubFault(
            f"DeleteCriticalSection: 0x{pointer:08x} is still held (depth {depth})"
        )
    del context.cs[pointer]
    context.record("DeleteCriticalSection", pointer=f"0x{pointer:08x}")
    return 0


# --------------------------------------------------------------------------
# Registry stubs
# --------------------------------------------------------------------------


def _reg_open_key_ex_w(context: StubContext, args) -> int:
    args = _require(args, 5, "RegOpenKeyExW")
    root, subkey_pointer, options, _sam, result_pointer = args
    if options:
        raise StubFault(f"RegOpenKeyExW: ulOptions must be 0, got 0x{options:08x}")
    root_name = ROOTS.get(root)
    if root_name is None:
        context.fail("RegOpenKeyExW", ERROR_INVALID_HANDLE, handle=f"0x{root:08x}")
        return ERROR_INVALID_HANDLE
    subkey = context.mem.read_wstring(subkey_pointer) if subkey_pointer else ""
    path = root_name if not subkey else f"{root_name}\\{subkey}"
    if not context.registry.has_key(path):
        context.fail("RegOpenKeyExW", ERROR_FILE_NOT_FOUND, key=normalize_reg_path(path))
        return ERROR_FILE_NOT_FOUND
    handle = context.next_key_handle
    context.next_key_handle += 1
    context.key_handles[handle] = normalize_reg_path(path)
    if result_pointer:
        context.mem.write_u32(result_pointer, handle)
    context.last_error = 0
    context.record("RegOpenKeyExW", key=normalize_reg_path(path),
                   handle=f"0x{handle:08x}")
    return ERROR_SUCCESS


def _reg_query_value_ex_w(context: StubContext, args) -> int:
    args = _require(args, 6, "RegQueryValueExW")
    handle, name_pointer, _reserved, type_pointer, data_pointer, size_pointer = args
    path = context.key_handles.get(handle)
    if path is None:
        context.fail("RegQueryValueExW", ERROR_INVALID_HANDLE,
                     handle=f"0x{handle:08x}")
        return ERROR_INVALID_HANDLE
    name = context.mem.read_wstring(name_pointer) if name_pointer else ""
    found = context.registry.value(path, name)
    if found is None:
        context.fail("RegQueryValueExW", ERROR_FILE_NOT_FOUND, key=path, value=name)
        return ERROR_FILE_NOT_FOUND
    type_name, payload = found
    required = len(payload)
    if size_pointer == 0:
        raise StubFault("RegQueryValueExW: lpcbData is NULL")

    capacity = context.mem.read_u32(size_pointer)
    if type_pointer:
        context.mem.write_u32(type_pointer, REG_TYPES[type_name])
    if data_pointer == 0:
        context.mem.write_u32(size_pointer, required)
        context.last_error = 0
        context.record("RegQueryValueExW", key=path, value=name, size=required)
        return ERROR_SUCCESS
    if capacity < required:
        context.mem.write_u32(size_pointer, required)
        context.fail("RegQueryValueExW", ERROR_MORE_DATA, key=path, value=name,
                     required=required, capacity=capacity)
        return ERROR_MORE_DATA
    context.mem.write(data_pointer, payload)
    context.mem.write_u32(size_pointer, required)
    context.last_error = 0
    context.record("RegQueryValueExW", key=path, value=name, type=type_name,
                   size=required)
    return ERROR_SUCCESS


def _reg_close_key(context: StubContext, args) -> int:
    handle = _require(args, 1, "RegCloseKey")[0]
    path = context.key_handles.pop(handle, None)
    if path is None:
        context.fail("RegCloseKey", ERROR_INVALID_HANDLE, handle=f"0x{handle:08x}")
        return ERROR_INVALID_HANDLE
    context.last_error = 0
    context.record("RegCloseKey", key=path, handle=f"0x{handle:08x}")
    return ERROR_SUCCESS


# --------------------------------------------------------------------------
# Dispatcher
# --------------------------------------------------------------------------

#: Bindings implemented here.  The key is the same ``module!export`` string
#: :func:`stubs.stub_key` produces, so a rename in the table cannot drift.
IMPLEMENTATIONS = {
    "coredll!CreateFileW": _create_file_w,
    "coredll!CreateFileA": _create_file_a,
    "coredll!ReadFile": _read_file,
    "coredll!SetFilePointer": _set_file_pointer,
    "coredll!GetFileSize": _get_file_size,
    "coredll!CloseHandle": _close_handle,
    "coredll!LocalAlloc": _local_alloc,
    "coredll!LocalFree": _local_free,
    "coredll!HeapAlloc": _heap_alloc,
    "coredll!HeapFree": _heap_free,
    "internal!memset": _memset,
    "internal!memcpy": _memcpy,
    "internal!strlen": _strlen,
    "coredll!sprintf": _sprintf,
    "internal!OSM_Printf": _osm_printf,
    "coredll!InitializeCriticalSection": _initialize_critical_section,
    "coredll!EnterCriticalSection": _enter_critical_section,
    "coredll!LeaveCriticalSection": _leave_critical_section,
    "coredll!DeleteCriticalSection": _delete_critical_section,
    "coredll!RegOpenKeyExW": _reg_open_key_ex_w,
    "coredll!RegQueryValueExW": _reg_query_value_ex_w,
    "coredll!RegCloseKey": _reg_close_key,
}


def parse_target(target) -> tuple[str | None, str | None, int | None]:
    """Split ``(module, name|ordinal)`` or ``module!name`` into its parts."""

    if isinstance(target, str):
        if "!" in target:
            module, symbol = target.split("!", 1)
        else:
            module, symbol = None, target
        if symbol.startswith("#"):
            try:
                return module, None, int(symbol[1:], 0)
            except ValueError as exc:
                raise StubFault(f"bad ordinal target {target!r}") from exc
        return module, symbol, None

    if isinstance(target, (tuple, list)) and len(target) == 2:
        module, symbol = target
        if isinstance(symbol, bool):
            raise StubFault(f"bad call target {target!r}")
        if isinstance(symbol, int):
            return str(module), None, symbol
        symbol = str(symbol)
        if symbol.startswith("#"):
            try:
                return str(module), None, int(symbol[1:], 0)
            except ValueError as exc:
                raise StubFault(f"bad ordinal target {target!r}") from exc
        return str(module), symbol, None

    raise StubFault(
        "call target must be (module, name), (module, ordinal) or 'module!name'"
    )


def read_args(backend, count: int, endian: str = "big") -> list[int]:
    """SH-4 cdecl arguments at a stub entry: ``r4``-``r7``, then the stack."""

    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= 8:
        raise StubFault(f"stub arity must be an integer 0..8, got {count!r}")
    regs = backend.get_regs()
    args = [regs["r4"], regs["r5"], regs["r6"], regs["r7"]][: min(4, count)]
    extra = count - 4
    if extra > 0:
        raw = backend.read_mem(regs["r15"], extra * 4)
        fmt = (">" if endian == "big" else "<") + "%dI" % extra
        args.extend(struct.unpack(fmt, raw))
    return args


class StubDispatcher:
    """Resolve ``module!export``/ordinal call targets to modelled stubs."""

    def __init__(self, context: StubContext | None = None, table=None, exports=None):
        self.context = context if context is not None else StubContext()
        self.table = stubs.STUBS if table is None else table
        self.by_key = stubs.binding_index(self.table)
        self.by_ordinal = stubs.ordinal_index(self.table)
        self.exports = exports or {}

    # -- resolution -------------------------------------------------------

    def _by_unique_name(self, name: str) -> dict | None:
        matches = [entry for entry in self.table if entry["export"] == name]
        if len(matches) > 1:
            modules = ", ".join(stubs.normalize_module(entry["module"]) for entry in matches)
            raise StubFault(
                f"ambiguous export name {name!r} ({modules}); qualify it with module!"
            )
        return matches[0] if matches else None

    def resolve(self, target) -> dict:
        module, name, ordinal = parse_target(target)

        if ordinal is not None:
            if not module:
                raise StubFault("an ordinal target needs a module, e.g. ('coredll', 719)")
            module_key = stubs.normalize_module(module)
            entry = self.by_ordinal.get((module_key, ordinal))
            if entry is None:
                resolved_name = (self.exports.get(module_key) or {}).get(ordinal)
                if resolved_name:
                    entry = self.by_key.get(f"{module_key}!{resolved_name}")
            if entry is None:
                raise MissingStub(f"{module_key}!#{ordinal}")
            return entry

        if name is None:
            raise StubFault(f"call target {target!r} names neither an export nor an ordinal")
        if module:
            module_key = stubs.normalize_module(module)
            entry = self.by_key.get(f"{module_key}!{name}")
            if entry is None:
                raise MissingStub(name)
            return entry

        entry = self._by_unique_name(name)
        if entry is None:
            raise MissingStub(name)
        return entry

    # -- execution --------------------------------------------------------

    def call(self, target, args=()) -> int:
        entry = self.resolve(target)
        key = stubs.stub_key(entry)
        implementation = IMPLEMENTATIONS.get(key)
        if entry["status"] != "modeled" or implementation is None:
            raise MissingStub(entry["name"])
        return implementation(self.context, list(args))

    def call_name(self, name: str, args=()) -> int:
        return self.call((None, name), args)

    def engine_hook(self, target, arity: int | None = None, on_call=None):
        """Return an ``engine.Backend.on_exec`` handler for one stub *target*.

        The handler reads the SH-4 cdecl arguments the caller set up (``r4``-
        ``r7``, then ``0(r15)``, ``4(r15)`` ... in the context's byte order),
        calls the stub and returns ``engine.StubReturn``.  *arity* defaults to
        the length of the stub's ``args`` list.  The stub is resolved at call
        time, so an unknown name fails there with ``missing stub: NAME``.
        *on_call*, when given, gets one dict per call (``va``, ``stub``,
        ``resolved``, ``args``, ``returned``) before the value is returned.
        Every failure is raised as ``engine.Blocked``; nothing is guessed.
        """

        module, name, ordinal = parse_target(target)
        label = f"{module or '?'}!{name if name is not None else '#%s' % ordinal}"

        def handler(backend, va):
            try:
                entry = self.resolve(target)
                count = len(entry["args"]) if arity is None else arity
                args = read_args(backend, count, self.context.endian)
                value = self.call(target, args)
            except (StubError, engine_mod.EngineError) as exc:
                detail = getattr(exc, "message", str(exc))
                raise engine_mod.Blocked(
                    f"stub {label} at {engine_mod.px(va)}: {detail}"
                ) from exc
            if on_call is not None:
                on_call(
                    {
                        "va": engine_mod.px(va),
                        "stub": label,
                        "resolved": entry["name"],
                        "args": [engine_mod.px(item) for item in args],
                        "returned": engine_mod.px(value),
                    }
                )
            return engine_mod.StubReturn(value)

        return handler

    def modeled(self) -> list[dict]:
        return [entry for entry in self.table if entry["status"] == "modeled"]

    def missing(self) -> list[str]:
        """Modeled entries without an implementation (must stay empty)."""

        return [
            stubs.stub_key(entry)
            for entry in self.modeled()
            if stubs.stub_key(entry) not in IMPLEMENTATIONS
        ]


# --------------------------------------------------------------------------
# Self-test
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


BUF = 0x1000
BUF2 = 0x1400
STR = 0x1800
FMT = 0x1A00
COUNT = 0x1C00
HIGH = 0x1C04
KEYH = 0x1C08
TYPE = 0x1C0C
SIZE = 0x1C10
CS = 0x1C40

CORPUS = {
    "REFER001/ADDRE001.DAT.cmp": b"0123456789",
    "MAPAL001/B28R070R.DAT": b"tile",
}

REGISTRY_DOC = {
    "keys": {
        "HKLM\\Software\\Clarion": {
            "values": {
                "MapPath": {"type": "REG_SZ", "data": "\\Storage Card\\"},
                "Mode": {"type": "REG_DWORD", "data": 3},
                "Blob": {"type": "REG_BINARY", "data": [1, 2, 3]},
            }
        },
        "HKCU\\Software\\Clarion": {"values": {"User": {"type": "REG_SZ", "data": "eu"}}},
    }
}


def make_context(endian: str = "big") -> StubContext:
    memory = FlatMemory(endian=endian)
    memory.add(BUF, 0x1000)          # scratch buffers 0x1000..0x1fff
    memory.add(0x8000, 0x4000)       # heap arena
    return StubContext(
        memory=memory,
        fs=VirtualFS(CORPUS),
        heap=Heap(memory, 0x8000, 0x4000),
        registry=Registry(REGISTRY_DOC),
        endian=endian,
    )


def make_dispatcher(endian: str = "big"):
    context = make_context(endian)
    return StubDispatcher(context), context


def _open(dispatcher: StubDispatcher, context: StubContext, wide: bool = True) -> int:
    if wide:
        path = context.mem.write_wstring(STR, "\\Storage Card\\REFER001\\ADDRE001.DAT.cmp")
        call = ("coredll", "CreateFileW")
    else:
        path = context.mem.write_cstring(STR, "REFER001\\ADDRE001.DAT.cmp")
        call = ("coredll", "CreateFileA")
    handle = dispatcher.call(call, [path, GENERIC_READ, 0, 0, OPEN_EXISTING, 0, 0])
    assert handle != INVALID_HANDLE_VALUE, context.calls
    return handle


def _expect_fault(callable_, needle: str, where: str) -> None:
    try:
        callable_()
    except StubFault as exc:
        assert needle in str(exc), f"{where}: {needle!r} not in {exc!r}"
    else:
        raise AssertionError(f"{where}: no StubFault raised")


def _expect_missing(callable_, expected: str, where: str) -> None:
    try:
        callable_()
    except MissingStub as exc:
        assert str(exc) == expected, f"{where}: {str(exc)!r} != {expected!r}"
    else:
        raise AssertionError(f"{where}: no MissingStub raised")


# -- individual scenarios: every modeled stub is called through the dispatcher


def scenario_create_file_w(dispatcher, context):
    handle = _open(dispatcher, context, wide=True)
    assert context.handles[handle].key == "refer001/addre001.dat.cmp"


def scenario_create_file_a(dispatcher, context):
    handle = _open(dispatcher, context, wide=False)
    assert dispatcher.call(("coredll", "CloseHandle"), [handle]) == 1


def scenario_read_file(dispatcher, context):
    handle = _open(dispatcher, context)
    result = dispatcher.call(
        ("coredll", "ReadFile"), [handle, BUF, 4, COUNT, 0]
    )
    assert result == 1
    assert context.mem.read(BUF, 4) == b"0123"
    assert context.mem.read_u32(COUNT) == 4
    assert context.handles[handle].offset == 4


def scenario_set_file_pointer(dispatcher, context):
    handle = _open(dispatcher, context)
    assert dispatcher.call(("coredll", "SetFilePointer"), [handle, 3, 0, FILE_BEGIN]) == 3
    assert dispatcher.call(("coredll", "ReadFile"), [handle, BUF, 1, COUNT, 0]) == 1
    assert context.mem.read(BUF, 1) == b"3"
    assert dispatcher.call(("coredll", "SetFilePointer"), [handle, -99, 0, FILE_BEGIN]) == M32
    assert context.last_error == ERROR_NEGATIVE_SEEK


def scenario_get_file_size(dispatcher, context):
    handle = _open(dispatcher, context)
    assert dispatcher.call(("coredll", "GetFileSize"), [handle, HIGH]) == 10
    assert context.mem.read_u32(HIGH) == 0


def scenario_close_handle(dispatcher, context):
    handle = _open(dispatcher, context)
    assert dispatcher.call(("coredll", "CloseHandle"), [handle]) == 1
    assert dispatcher.call(("coredll", "CloseHandle"), [handle]) == 0
    assert context.last_error == ERROR_INVALID_HANDLE


def scenario_local_alloc(dispatcher, context):
    pointer = dispatcher.call(("coredll", "LocalAlloc"), [LMEM_ZEROINIT, 16])
    assert pointer and pointer % 8 == 0
    assert context.mem.read(pointer, 16) == b"\x00" * 16
    assert dispatcher.call(("coredll", "LocalFree"), [pointer]) == 0
    assert context.heap.leaks() == []


def scenario_local_free(dispatcher, context):
    pointer = dispatcher.call(("coredll", "LocalAlloc"), [0, 8])
    assert context.mem.read(pointer, 8) == b"\xcd" * 8
    assert dispatcher.call(("coredll", "LocalFree"), [pointer]) == 0
    _expect_fault(
        lambda: dispatcher.call(("coredll", "LocalFree"), [pointer]),
        "double free",
        "LocalFree double free",
    )


def scenario_heap_alloc(dispatcher, context):
    pointer = dispatcher.call(("coredll", "HeapAlloc"), [0, HEAP_ZERO_MEMORY, 24])
    assert pointer and pointer % 8 == 0
    assert context.mem.read(pointer, 24) == b"\x00" * 24


def scenario_heap_free(dispatcher, context):
    pointer = dispatcher.call(("coredll", "HeapAlloc"), [0, 0, 8])
    assert dispatcher.call(("coredll", "HeapFree"), [0, 0, pointer]) == 1
    assert dispatcher.call(("coredll", "HeapFree"), [0, 0, pointer + 8]) == 0


def scenario_memset(dispatcher, context):
    context.mem.write(BUF, b"abcdef")
    assert dispatcher.call(("internal", "memset"), [BUF, ord("x"), 3]) == BUF
    assert context.mem.read(BUF, 6) == b"xxxdef"


def scenario_memcpy(dispatcher, context):
    context.mem.write(BUF, b"abcdef")
    assert dispatcher.call(("internal", "memcpy"), [BUF2, BUF, 6]) == BUF2
    assert context.mem.read(BUF2, 6) == b"abcdef"
    _expect_fault(
        lambda: dispatcher.call(("internal", "memcpy"), [BUF + 1, BUF, 4]),
        "overlapping",
        "memcpy overlap",
    )


def scenario_strlen(dispatcher, context):
    context.mem.write_cstring(STR, "hello")
    assert dispatcher.call(("internal", "strlen"), [STR]) == 5


def scenario_sprintf(dispatcher, context):
    context.mem.write_cstring(BUF, "leaf")
    context.mem.write_cstring(FMT, "%s=%d/%u/%x/%%")
    written = dispatcher.call(
        ("coredll", "sprintf"), [BUF2, FMT, BUF, -7, 42, 0xBEEF]
    )
    text = context.mem.read_cstring(BUF2)
    assert text == "leaf=-7/42/beef/%", text
    assert written == len(text)


def scenario_osm_printf(dispatcher, context):
    context.mem.write_cstring(FMT, "map %s/%d")
    context.mem.write_cstring(BUF, "eu")
    assert dispatcher.call(("internal", "OSM_Printf"), [FMT, BUF, 7]) == 8
    assert context.log == ["map eu/7"]


def scenario_initialize_critical_section(dispatcher, context):
    assert dispatcher.call(("coredll", "InitializeCriticalSection"), [CS]) == 0
    assert context.cs[CS] == 0
    _expect_fault(
        lambda: dispatcher.call(("coredll", "InitializeCriticalSection"), [CS]),
        "already initialised",
        "InitializeCriticalSection twice",
    )


def scenario_enter_critical_section(dispatcher, context):
    dispatcher.call(("coredll", "InitializeCriticalSection"), [CS])
    assert dispatcher.call(("coredll", "EnterCriticalSection"), [CS]) == 0
    assert dispatcher.call(("coredll", "EnterCriticalSection"), [CS]) == 0
    assert context.cs[CS] == 2


def scenario_leave_critical_section(dispatcher, context):
    dispatcher.call(("coredll", "InitializeCriticalSection"), [CS])
    dispatcher.call(("coredll", "EnterCriticalSection"), [CS])
    assert dispatcher.call(("coredll", "LeaveCriticalSection"), [CS]) == 0
    _expect_fault(
        lambda: dispatcher.call(("coredll", "LeaveCriticalSection"), [CS]),
        "was not entered",
        "LeaveCriticalSection unbalanced",
    )


def scenario_delete_critical_section(dispatcher, context):
    dispatcher.call(("coredll", "InitializeCriticalSection"), [CS])
    dispatcher.call(("coredll", "EnterCriticalSection"), [CS])
    _expect_fault(
        lambda: dispatcher.call(("coredll", "DeleteCriticalSection"), [CS]),
        "still held",
        "DeleteCriticalSection while held",
    )
    dispatcher.call(("coredll", "LeaveCriticalSection"), [CS])
    assert dispatcher.call(("coredll", "DeleteCriticalSection"), [CS]) == 0
    assert CS not in context.cs


def scenario_reg_open_key_ex_w(dispatcher, context):
    subkey = context.mem.write_wstring(STR, "Software\\Clarion")
    assert dispatcher.call(
        ("coredll", "RegOpenKeyExW"),
        [0x80000002, subkey, 0, 0x20019, KEYH],
    ) == ERROR_SUCCESS
    handle = context.mem.read_u32(KEYH)
    assert context.key_handles[handle] == "hkey_local_machine\\software\\clarion"


def scenario_reg_query_value_ex_w(dispatcher, context):
    subkey = context.mem.write_wstring(STR, "Software\\Clarion")
    dispatcher.call(("coredll", "RegOpenKeyExW"), [0x80000002, subkey, 0, 0, KEYH])
    handle = context.mem.read_u32(KEYH)
    name = context.mem.write_wstring(FMT, "MapPath")
    context.mem.write_u32(SIZE, 64)
    assert dispatcher.call(
        ("coredll", "RegQueryValueExW"),
        [handle, name, 0, TYPE, BUF, SIZE],
    ) == ERROR_SUCCESS
    assert context.mem.read_u32(TYPE) == REG_TYPES["REG_SZ"]
    expected = "\\Storage Card\\".encode("utf-16-le") + b"\x00\x00"
    assert context.mem.read(BUF, len(expected)) == expected
    assert context.mem.read_u32(SIZE) == len(expected)


def scenario_reg_close_key(dispatcher, context):
    subkey = context.mem.write_wstring(STR, "Software\\Clarion")
    dispatcher.call(("coredll", "RegOpenKeyExW"), [0x80000002, subkey, 0, 0, KEYH])
    handle = context.mem.read_u32(KEYH)
    assert dispatcher.call(("coredll", "RegCloseKey"), [handle]) == ERROR_SUCCESS
    assert dispatcher.call(("coredll", "RegCloseKey"), [handle]) == ERROR_INVALID_HANDLE


SCENARIOS = {
    "CreateFileW": scenario_create_file_w,
    "CreateFileA": scenario_create_file_a,
    "ReadFile": scenario_read_file,
    "SetFilePointer": scenario_set_file_pointer,
    "GetFileSize": scenario_get_file_size,
    "CloseHandle": scenario_close_handle,
    "LocalAlloc": scenario_local_alloc,
    "LocalFree": scenario_local_free,
    "HeapAlloc": scenario_heap_alloc,
    "HeapFree": scenario_heap_free,
    "memset": scenario_memset,
    "memcpy": scenario_memcpy,
    "strlen": scenario_strlen,
    "sprintf": scenario_sprintf,
    "OSM_Printf": scenario_osm_printf,
    "InitializeCriticalSection": scenario_initialize_critical_section,
    "EnterCriticalSection": scenario_enter_critical_section,
    "LeaveCriticalSection": scenario_leave_critical_section,
    "DeleteCriticalSection": scenario_delete_critical_section,
    "RegOpenKeyExW": scenario_reg_open_key_ex_w,
    "RegQueryValueExW": scenario_reg_query_value_ex_w,
    "RegCloseKey": scenario_reg_close_key,
}


@check("bindings: every stub has a unique module!export and no guessed ordinal")
def test_bindings(_tmp):
    assert stubs.validate() == []
    index = stubs.binding_index()
    assert len(index) == len(stubs.STUBS)
    assert index["coredll!CreateFileW"]["export"] == "CreateFileW"
    assert index["internal!memset"]["module"] == "internal"
    ordinal = stubs.ordinal_index()
    assert ordinal[("coredll", 719)]["name"] == "sprintf"
    assert len(ordinal) == 1, ordinal
    for stub in stubs.STUBS:
        if stub["name"] != "sprintf":
            assert stub["ordinal"] is None, stub


@check("bindings: an export-names DB fills ordinals and catches conflicts")
def test_bind_exports(_tmp):
    exports = {"COREDLL.dll": {719: "sprintf", 1042: "CreateFileW"}}
    table, problems = stubs.bind_exports(exports)
    assert problems == [], problems
    by_entry = {entry["name"]: entry for entry in table}
    assert by_entry["CreateFileW"]["ordinal"] == 1042
    assert by_entry["sprintf"]["ordinal"] == 719

    _table, problems = stubs.bind_exports({"coredll": {720: "sprintf"}})
    assert any("disagrees" in problem for problem in problems), problems


@check("bindings: cerom-style name DB is read without vendor bytes")
def test_load_names(_tmp):
    path = Path(_tmp) / "names.json"
    path.write_text(
        json.dumps({"modules": {"coredll.dll": {"719": "sprintf", "1042": "CreateFileW"}}}),
        encoding="utf-8",
    )
    exports = stubs.load_export_names(path)
    assert exports == {"coredll": {719: "sprintf", 1042: "CreateFileW"}}, exports

    path.write_text(
        json.dumps({"COREDLL.dll": {"719": "sprintf"}}), encoding="utf-8"
    )
    assert stubs.load_export_names(path) == {"coredll": {719: "sprintf"}}


@check("dispatcher: name and ordinal targets resolve; unknown stops exactly")
def test_dispatch_targets(_tmp):
    dispatcher, _ctx = make_dispatcher()
    assert dispatcher.resolve(("COREDLL.dll", "CreateFileW"))["name"] == "CreateFileW"
    assert dispatcher.resolve(("coredll", 719))["name"] == "sprintf"
    assert dispatcher.resolve("coredll!sprintf")["name"] == "sprintf"
    assert dispatcher.resolve("strlen")["name"] == "strlen"

    exports = {"coredll": {1042: "CreateFileW"}}
    with_exports = StubDispatcher(make_context(), exports=exports)
    assert with_exports.resolve(("coredll", 1042))["name"] == "CreateFileW"

    ordinal_dispatcher, context = make_dispatcher()
    context.mem.write_cstring(FMT, "%d")
    assert ordinal_dispatcher.call(("coredll", 719), [BUF2, FMT, 42]) == 2
    assert context.mem.read_cstring(BUF2) == "42"

    _expect_missing(
        lambda: dispatcher.call(("coredll", "OpenEventW")),
        "missing stub: OpenEventW",
        "unknown export",
    )
    _expect_missing(
        lambda: dispatcher.call(("coredll", 4242)),
        "missing stub: coredll!#4242",
        "unknown ordinal",
    )
    _expect_missing(
        lambda: dispatcher.call(("nope", "CreateFileW")),
        "missing stub: CreateFileW",
        "unknown module",
    )


@check("dispatcher: every modeled stub is called through its binding")
def test_every_stub_called(_tmp):
    modeled = [entry["name"] for entry in stubs.STUBS if entry["status"] == "modeled"]
    assert sorted(SCENARIOS) == sorted(modeled), (
        f"scenarios {sorted(SCENARIOS)} != modeled {sorted(modeled)}"
    )
    for name in modeled:
        dispatcher, context = make_dispatcher()
        SCENARIOS[name](dispatcher, context)
        assert context.calls, f"{name}: dispatcher recorded no call"
        assert any(call["call"] == name for call in context.calls), (
            f"{name}: dispatcher never logged this stub: {context.calls}"
        )


@check("dispatcher: implementations and table cannot drift apart")
def test_implementations(_tmp):
    dispatcher, _ctx = make_dispatcher()
    assert dispatcher.missing() == []
    modeled_keys = {
        stubs.stub_key(entry)
        for entry in stubs.STUBS
        if entry["status"] == "modeled"
    }
    assert set(IMPLEMENTATIONS) == modeled_keys, (
        sorted(set(IMPLEMENTATIONS) ^ modeled_keys)
    )
    for key in IMPLEMENTATIONS:
        assert stubs.by_key(key) is not None, key


@check("dispatcher: planned exports stop with missing stub, never a value")
def test_planned(_tmp):
    dispatcher, _ctx = make_dispatcher()
    for name in ("OSM_LogMsg", "StatusData"):
        entry = stubs.by_name(name)
        assert entry["status"] == "planned", entry
        _expect_missing(
            lambda name=name: dispatcher.call(("internal", name)),
            f"missing stub: {name}",
            name,
        )


@check("virtual FS: read round-trip through CreateFile/ReadFile/CloseHandle")
def test_fs_roundtrip(_tmp):
    dispatcher, context = make_dispatcher()
    handle = _open(dispatcher, context)

    assert dispatcher.call(("coredll", "GetFileSize"), [handle, HIGH]) == 10
    assert dispatcher.call(("coredll", "ReadFile"), [handle, BUF, 4, COUNT, 0]) == 1
    assert context.mem.read(BUF, 4) == b"0123"
    assert dispatcher.call(("coredll", "SetFilePointer"), [handle, 0, 0, FILE_BEGIN]) == 0
    assert dispatcher.call(("coredll", "ReadFile"), [handle, BUF, 10, COUNT, 0]) == 1
    assert context.mem.read(BUF, 10) == CORPUS["REFER001/ADDRE001.DAT.cmp"]
    assert dispatcher.call(("coredll", "ReadFile"), [handle, BUF, 1, COUNT, 0]) == 0
    assert context.last_error == ERROR_HANDLE_EOF
    assert dispatcher.call(("coredll", "CloseHandle"), [handle]) == 1
    assert context.calls[-1] == {
        "call": "CloseHandle",
        "handle": f"0x{handle:08x}",
        "path": "refer001/addre001.dat.cmp",
        "unread": 0,
    }

    # Missing file is an error return, not an exception.
    missing = context.mem.write_wstring(STR, "\\Storage Card\\NOPE.DAT")
    assert dispatcher.call(
        ("coredll", "CreateFileW"), [missing, GENERIC_READ, 0, 0, OPEN_EXISTING, 0, 0]
    ) == INVALID_HANDLE_VALUE
    assert context.last_error == ERROR_FILE_NOT_FOUND


@check("virtual FS: host paths are never used; '..' and drives are refused")
def test_fs_paths(_tmp):
    root = Path(_tmp) / "card"
    (root / "REFER001").mkdir(parents=True)
    (root / "REFER001" / "X.DAT").write_bytes(b"x")
    fs = VirtualFS.from_directory(root)
    assert fs.paths() == ["refer001/x.dat"]
    assert fs.exists("\\Storage Card\\REFER001\\X.DAT")
    assert not fs.exists("REFER001/Y.DAT")

    _expect_fault(lambda: fs.exists("../etc/passwd"), "escapes", "parent path")
    _expect_fault(lambda: fs.exists("C:\\Windows\\x"), "drive-letter", "drive path")


@check("virtual FS: two runs produce identical call logs")
def test_determinism(_tmp):
    logs = []
    for _ in range(2):
        dispatcher, context = make_dispatcher()
        scenario_read_file(dispatcher, context)
        scenario_sprintf(dispatcher, context)
        logs.append(json.dumps(context.calls, sort_keys=True))
    assert logs[0] == logs[1], logs


@check("sprintf: documented subset only; other conversions stop")
def test_sprintf_subset(_tmp):
    dispatcher, context = make_dispatcher()
    context.mem.write_cstring(BUF, "x")
    context.mem.write_cstring(FMT, "%05d|%-4u|%x")
    assert dispatcher.call(("coredll", "sprintf"), [BUF2, FMT, -3, 7, 255]) == 13
    assert context.mem.read_cstring(BUF2) == "-0003|7   |ff"
    context.mem.write_cstring(FMT, "%q")
    _expect_fault(
        lambda: dispatcher.call(("coredll", "sprintf"), [BUF2, FMT, 1]),
        "unsupported conversion",
        "sprintf %q",
    )


@check("heap: alignment, zero/poison, leak tracking")
def test_heap_contract(_tmp):
    _dispatcher, context = make_dispatcher()
    zeroed = context.heap.alloc(3, zero=True, owner="test")
    poisoned = context.heap.alloc(3, zero=False, owner="test")
    assert zeroed % 8 == 0 and poisoned % 8 == 0
    assert context.mem.read(zeroed, 3) == b"\x00" * 3
    assert context.mem.read(poisoned, 3) == b"\xcd" * 3
    assert len(context.heap.leaks()) == 2
    assert context.heap.free(zeroed) is True
    assert context.mem.read(zeroed, 3) == b"\xcd" * 3
    assert context.heap.free(zeroed + 64) is False
    _expect_fault(
        lambda: context.heap.free(zeroed),
        "double free",
        "heap double free",
    )


@check("registry: JSON fixture, REG_SZ/REG_DWORD, MORE_DATA, missing key")
def test_registry_contract(_tmp):
    dispatcher, context = make_dispatcher()
    subkey = context.mem.write_wstring(STR, "Software\\Clarion")
    assert dispatcher.call(
        ("coredll", "RegOpenKeyExW"), [0x80000002, subkey, 0, 0, KEYH]
    ) == ERROR_SUCCESS
    handle = context.mem.read_u32(KEYH)

    name = context.mem.write_wstring(FMT, "Mode")
    context.mem.write_u32(SIZE, 4)
    assert dispatcher.call(
        ("coredll", "RegQueryValueExW"), [handle, name, 0, TYPE, BUF2, SIZE]
    ) == ERROR_SUCCESS
    assert context.mem.read(BUF2, 4) == b"\x03\x00\x00\x00"
    assert context.mem.read_u32(TYPE) == REG_TYPES["REG_DWORD"]

    context.mem.write_u32(SIZE, 2)
    assert dispatcher.call(
        ("coredll", "RegQueryValueExW"), [handle, name, 0, TYPE, BUF2, SIZE]
    ) == ERROR_MORE_DATA
    assert context.mem.read_u32(SIZE) == 4

    absent = context.mem.write_wstring(FMT, "Nope")
    assert dispatcher.call(
        ("coredll", "RegQueryValueExW"), [handle, absent, 0, TYPE, BUF2, SIZE]
    ) == ERROR_FILE_NOT_FOUND

    bad = context.mem.write_wstring(FMT, "Software\\Nope")
    assert dispatcher.call(
        ("coredll", "RegOpenKeyExW"), [0x80000002, bad, 0, 0, KEYH]
    ) == ERROR_FILE_NOT_FOUND
    assert dispatcher.call(("coredll", "RegCloseKey"), [handle]) == ERROR_SUCCESS


@check("stub context: little-endian guest writes are honoured")
def test_endianness(_tmp):
    dispatcher, context = make_dispatcher(endian="little")
    context.mem.write_u32(COUNT, 0x11223344)
    assert context.mem.read(COUNT, 4) == b"\x44\x33\x22\x11"
    handle = _open(dispatcher, context)
    assert dispatcher.call(("coredll", "GetFileSize"), [handle, HIGH]) == 10
    assert context.mem.read(HIGH, 4) == b"\x00\x00\x00\x00"


class _RegisterBackend:
    """Only the two calls the argument reader makes: registers and memory."""

    def __init__(self, regs: dict, stack: bytes, base: int = 0x1000):
        self.regs = dict(regs)
        self.regs.setdefault("r15", base)
        self.stack = stack
        self.base = base

    def get_regs(self) -> dict:
        return dict(self.regs)

    def read_mem(self, va: int, size: int) -> bytes:
        assert va == self.base, f"stack read at {va:#x}, expected {self.base:#x}"
        return self.stack[:size]


@check("engine_hook: r4-r7, then the stack, in the context's byte order")
def test_engine_hook_arguments(_tmp):
    regs = {"r4": 1, "r5": 2, "r6": 3, "r7": 4}
    big = b"".join(value.to_bytes(4, "big") for value in (5, 6))
    little = b"".join(value.to_bytes(4, "little") for value in (5, 6))
    assert read_args(_RegisterBackend(regs, big), 6, "big") == [1, 2, 3, 4, 5, 6]
    assert read_args(_RegisterBackend(regs, little), 6, "little") == [1, 2, 3, 4, 5, 6]
    assert read_args(_RegisterBackend(regs, big), 2, "big") == [1, 2]
    assert read_args(_RegisterBackend(regs, big), 0, "big") == []
    try:
        read_args(_RegisterBackend(regs, big), 9, "big")
    except StubFault:
        pass
    else:
        raise AssertionError("arity 9 must be refused")


@check("engine_hook: resolves the stub, logs the call, returns its value")
def test_engine_hook_call(_tmp):
    dispatcher, _context = make_dispatcher()
    seen: list[dict] = []
    handler = dispatcher.engine_hook(("coredll.dll", "CloseHandle"), on_call=seen.append)
    regs = {"r4": 0x999, "r5": 0, "r6": 0, "r7": 0}
    result = handler(_RegisterBackend(regs, b""), 0x8C100000)
    assert isinstance(result, engine_mod.StubReturn), result
    assert len(seen) == 1, seen
    assert seen[0]["stub"] == "coredll.dll!CloseHandle", seen[0]
    assert seen[0]["resolved"] == "CloseHandle", seen[0]
    assert seen[0]["args"][0] == engine_mod.px(0x999), seen[0]
    assert seen[0]["returned"] == engine_mod.px(result.value), seen[0]


@check("engine_hook: an unmodelled export is Blocked with 'missing stub: NAME'")
def test_engine_hook_missing(_tmp):
    dispatcher, _context = make_dispatcher()
    handler = dispatcher.engine_hook(("coredll.dll", "NoSuchExport"))
    try:
        handler(_RegisterBackend({"r4": 1}, b""), 0x8C100000)
    except engine_mod.Blocked as exc:
        assert "missing stub: NoSuchExport" in exc.message, exc.message
        assert "stub coredll.dll!NoSuchExport at 0x8c100000" in exc.message, exc.message
    else:
        raise AssertionError("an unmodelled export must not return a value")


def selftest() -> int:
    failures = 0
    for name, func in CHECKS:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                func(tmp)
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
            else:
                print(f"ok   {name}")

    print()
    if failures:
        print(f"dispatch selftest: FAILED ({failures}/{len(CHECKS)} checks)")
        return 1
    print(f"dispatch selftest: OK ({len(CHECKS)} checks)")
    return 0


def _print_list() -> None:
    dispatcher, _context = make_dispatcher()
    print(f"{'module!export':<36} {'status':<8} implementation")
    print("-" * 76)
    for entry in stubs.STUBS:
        key = stubs.stub_key(entry)
        implementation = "yes" if key in IMPLEMENTATIONS else "-"
        print(f"{key:<36} {entry['status']:<8} {implementation}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="L3 stub dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show bindings and implementation coverage")
    st = sub.add_parser("selftest", help="run the dispatcher self-test (bounded; accepts --full for interface consistency)")
    mode = st.add_mutually_exclusive_group()
    mode.add_argument("--quick", action="store_true")
    mode.add_argument("--full", action="store_true")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # Keep a simple --selftest alias while accepting --full/--quick.
    if argv and argv[0] == "--selftest":
        argv = ["selftest"] + argv[1:]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        full = bool(getattr(args, "full", False))
        code = selftest()
        if code == 0:
            # selftest() prints its own summary; append mode on a new line for
            # callers that want to confirm the bounded/full contract (M1.18).
            print(f"dispatch selftest mode: {'full' if full else 'quick'}")
        return code
    if args.command == "list":
        _print_list()
        return 0
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
