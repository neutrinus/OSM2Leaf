#!/usr/bin/env python3
"""Declarative WinCE API stub table for the L3 harness.

The firmware calls ``coredll`` and its own logging helpers.  The L3 harness
replaces those calls with deterministic host-side models; this module is the
single source of truth for what each model does, so the Ghidra script and the
documentation cannot drift apart.

Every entry records:

``name``
    Imported symbol name.
``dll``
    Expected provider, or ``"internal"`` for app/library helpers.
``signature``
    C prototype; WinCE 5.0 headers for ``coredll``, ``HYPOTHESIS`` for the
    Clarion logging calls.
``args``
    Ordered ``{"name", "type"}`` pairs, so the harness can bind registers and
    the stack without re-reading the prototype.
``returns``
    Return type and the value rule the harness must implement.
``binding``
    How the call is intercepted: ``patch-call-site`` (ROM is pre-bound, so
    there is no import table), ``hook-thunk``, or ``unresolved``.
``side_effects``
    Ordered, declarative list of what the stub does.  No wall clock, no
    uninitialised memory: buffers are zero-filled or poisoned and logged.
``status``
    ``modeled`` (contract fixed) or ``planned`` (signature still unknown).
``notes``
    Limitations and evidence pointers.

``READER_STUBS`` maps the reader ids used by :mod:`manifest` to the stubs that
reader needs.

Usage::

    python3 tools/l3_harness/stubs.py list
    python3 tools/l3_harness/stubs.py json
    python3 tools/l3_harness/stubs.py schema
    python3 tools/l3_harness/stubs.py selftest

Exit codes: ``0`` ok, ``1`` table problems, ``2`` usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCHEMA = "osm2leaf.l3.stubs/v1"

STATUSES = ("modeled", "planned")
BINDINGS = ("patch-call-site", "hook-thunk", "unresolved")

STUBS = [
    {
        "name": "CreateFileW",
        "dll": "coredll.dll",
        "signature": (
            "HANDLE CreateFileW(LPCWSTR lpFileName, DWORD dwDesiredAccess, "
            "DWORD dwShareMode, LPSECURITY_ATTRIBUTES lpSecurityAttributes, "
            "DWORD dwCreationDisposition, DWORD dwFlagsAndAttributes, "
            "HANDLE hTemplateFile);"
        ),
        "args": [
            {"name": "lpFileName", "type": "LPCWSTR"},
            {"name": "dwDesiredAccess", "type": "DWORD"},
            {"name": "dwShareMode", "type": "DWORD"},
            {"name": "lpSecurityAttributes", "type": "LPSECURITY_ATTRIBUTES"},
            {"name": "dwCreationDisposition", "type": "DWORD"},
            {"name": "dwFlagsAndAttributes", "type": "DWORD"},
            {"name": "hTemplateFile", "type": "HANDLE"},
        ],
        "returns": "HANDLE (INVALID_HANDLE_VALUE on error)",
        "binding": "patch-call-site",
        "side_effects": [
            "decode lpFileName as UTF-16LE and normalise separators to '/'",
            "resolve the result against the corpus root of the manifest",
            "reject absolute, host and '..' paths instead of guessing",
            "open the corpus file read-only and assign the next free handle",
            "record path, access and handle in the call log",
        ],
        "status": "modeled",
        "notes": (
            "The ROM is pre-bound, so there is no import descriptor to hook; "
            "the harness patches the call site or a copied thunk."
        ),
    },
    {
        "name": "CreateFileA",
        "dll": "coredll.dll",
        "signature": (
            "HANDLE CreateFileA(LPCSTR lpFileName, DWORD dwDesiredAccess, "
            "DWORD dwShareMode, LPSECURITY_ATTRIBUTES lpSecurityAttributes, "
            "DWORD dwCreationDisposition, DWORD dwFlagsAndAttributes, "
            "HANDLE hTemplateFile);"
        ),
        "args": [
            {"name": "lpFileName", "type": "LPCSTR"},
            {"name": "dwDesiredAccess", "type": "DWORD"},
            {"name": "dwShareMode", "type": "DWORD"},
            {"name": "lpSecurityAttributes", "type": "LPSECURITY_ATTRIBUTES"},
            {"name": "dwCreationDisposition", "type": "DWORD"},
            {"name": "dwFlagsAndAttributes", "type": "DWORD"},
            {"name": "hTemplateFile", "type": "HANDLE"},
        ],
        "returns": "HANDLE (INVALID_HANDLE_VALUE on error)",
        "binding": "patch-call-site",
        "side_effects": [
            "decode lpFileName as the ANSI code page used by the image",
            "behave exactly like CreateFileW after path normalisation",
        ],
        "status": "modeled",
        "notes": (
            "Kept separate because the 8-bit reader path may be used for "
            "legacy map names; both must resolve to the same corpus file."
        ),
    },
    {
        "name": "ReadFile",
        "dll": "coredll.dll",
        "signature": (
            "BOOL ReadFile(HANDLE hFile, LPVOID lpBuffer, DWORD nNumberOfBytesToRead, "
            "LPDWORD lpNumberOfBytesRead, LPOVERLAPPED lpOverlapped);"
        ),
        "args": [
            {"name": "hFile", "type": "HANDLE"},
            {"name": "lpBuffer", "type": "LPVOID"},
            {"name": "nNumberOfBytesToRead", "type": "DWORD"},
            {"name": "lpNumberOfBytesRead", "type": "LPDWORD"},
            {"name": "lpOverlapped", "type": "LPOVERLAPPED"},
        ],
        "returns": "BOOL (1 on success, 0 on failure)",
        "binding": "patch-call-site",
        "side_effects": [
            "copy min(requested, remaining) bytes from the handle cursor into lpBuffer",
            "advance the handle cursor by the copied byte count",
            "store the byte count at lpNumberOfBytesRead when it is non-NULL",
            "zero-fill the unused tail of the requested range",
            "return 0 with ERROR_HANDLE_EOF when the cursor is at EOF",
            "reject an unbound handle, a NULL buffer or an unmapped buffer range",
        ],
        "status": "modeled",
        "notes": (
            "lpOverlapped is asserted NULL; an asynchronous read is a BLOCKED "
            "case, not a silent fallback."
        ),
    },
    {
        "name": "SetFilePointer",
        "dll": "coredll.dll",
        "signature": (
            "DWORD SetFilePointer(HANDLE hFile, LONG lDistanceToMove, "
            "PLONG lpDistanceToMoveHigh, DWORD dwMoveMethod);"
        ),
        "args": [
            {"name": "hFile", "type": "HANDLE"},
            {"name": "lDistanceToMove", "type": "LONG"},
            {"name": "lpDistanceToMoveHigh", "type": "PLONG"},
            {"name": "dwMoveMethod", "type": "DWORD"},
        ],
        "returns": "DWORD (new low offset; 0xffffffff on error)",
        "binding": "patch-call-site",
        "side_effects": [
            "build the signed 64-bit distance from the low/high pair",
            "apply FILE_BEGIN, FILE_CURRENT or FILE_END to the handle cursor",
            "return 0xffffffff and set ERROR_NEGATIVE_SEEK for a negative cursor",
            "allow a seek past EOF; the following ReadFile returns 0 bytes",
            "log the old and new cursor",
        ],
        "status": "modeled",
        "notes": "64 KiB chunk boundaries are the hot path; log them sparsely.",
    },
    {
        "name": "GetFileSize",
        "dll": "coredll.dll",
        "signature": "DWORD GetFileSize(HANDLE hFile, LPDWORD lpFileSizeHigh);",
        "args": [
            {"name": "hFile", "type": "HANDLE"},
            {"name": "lpFileSizeHigh", "type": "LPDWORD"},
        ],
        "returns": "DWORD (low 32 bits of the size)",
        "binding": "patch-call-site",
        "side_effects": [
            "return the corpus file size as a 64-bit value",
            "write the high dword to lpFileSizeHigh when non-NULL",
        ],
        "status": "modeled",
        "notes": "The corpus is small; a >4 GiB file is not a target.",
    },
    {
        "name": "CloseHandle",
        "dll": "coredll.dll",
        "signature": "BOOL CloseHandle(HANDLE hObject);",
        "args": [{"name": "hObject", "type": "HANDLE"}],
        "returns": "BOOL (1 on success, 0 on failure)",
        "binding": "patch-call-site",
        "side_effects": [
            "drop the handle from the handle table",
            "return 0 for an unbound or already closed handle",
            "record the close and any bytes left unread",
        ],
        "status": "modeled",
        "notes": "A leak (handle still open at return) is reported, not failed.",
    },
    {
        "name": "LocalAlloc",
        "dll": "coredll.dll",
        "signature": "HLOCAL LocalAlloc(UINT uFlags, UINT uBytes);",
        "args": [
            {"name": "uFlags", "type": "UINT"},
            {"name": "uBytes", "type": "UINT"},
        ],
        "returns": "HLOCAL (NULL on failure)",
        "binding": "patch-call-site",
        "side_effects": [
            "allocate from the harness heap with 8-byte alignment",
            "zero the block when LMEM_ZEROINIT is set, else fill with 0xcd",
            "track size and owner for the leak report",
            "return NULL for uBytes == 0",
        ],
        "status": "modeled",
        "notes": (
            "0xcd poison makes uninitialised reads visible in the output "
            "digest instead of depending on host memory."
        ),
    },
    {
        "name": "LocalFree",
        "dll": "coredll.dll",
        "signature": "HLOCAL LocalFree(HLOCAL hMem);",
        "args": [{"name": "hMem", "type": "HLOCAL"}],
        "returns": "NULL (freed) or hMem on error",
        "binding": "patch-call-site",
        "side_effects": [
            "release the block and clear the tracking record",
            "return hMem unchanged for an unknown pointer",
        ],
        "status": "modeled",
        "notes": "Double free is reported as a harness error.",
    },
    {
        "name": "HeapAlloc",
        "dll": "coredll.dll",
        "signature": "LPVOID HeapAlloc(HANDLE hHeap, DWORD dwFlags, DWORD dwBytes);",
        "args": [
            {"name": "hHeap", "type": "HANDLE"},
            {"name": "dwFlags", "type": "DWORD"},
            {"name": "dwBytes", "type": "DWORD"},
        ],
        "returns": "LPVOID (NULL on failure)",
        "binding": "patch-call-site",
        "side_effects": [
            "allocate from the harness heap with 8-byte alignment",
            "zero the block when HEAP_ZERO_MEMORY (0x8) is set, else fill with 0xcd",
            "track size and owner for the leak report",
        ],
        "status": "modeled",
        "notes": "Same heap as LocalAlloc so the two allocators cannot alias.",
    },
    {
        "name": "HeapFree",
        "dll": "coredll.dll",
        "signature": "BOOL HeapFree(HANDLE hHeap, DWORD dwFlags, LPVOID lpMem);",
        "args": [
            {"name": "hHeap", "type": "HANDLE"},
            {"name": "dwFlags", "type": "DWORD"},
            {"name": "lpMem", "type": "LPVOID"},
        ],
        "returns": "BOOL (1 on success)",
        "binding": "patch-call-site",
        "side_effects": [
            "release the block and clear the tracking record",
            "return 0 for an unknown pointer",
        ],
        "status": "modeled",
        "notes": "dwFlags must be 0; anything else is a BLOCKED case.",
    },
    {
        "name": "memset",
        "dll": "internal",
        "signature": "void *memset(void *dst, int value, size_t count);",
        "args": [
            {"name": "dst", "type": "void *"},
            {"name": "value", "type": "int"},
            {"name": "count", "type": "size_t"},
        ],
        "returns": "void * (dst)",
        "binding": "patch-call-site",
        "side_effects": [
            "write count bytes of (value & 0xff) to dst",
            "bounds-check [dst, dst+count) against the mapped regions",
        ],
        "status": "modeled",
        "notes": (
            "The compiler may inline it; only an out-of-line call is stubbed. "
            "SH-4 cdecl: args on the stack, return in R0."
        ),
    },
    {
        "name": "memcpy",
        "dll": "internal",
        "signature": "void *memcpy(void *dst, const void *src, size_t count);",
        "args": [
            {"name": "dst", "type": "void *"},
            {"name": "src", "type": "const void *"},
            {"name": "count", "type": "size_t"},
        ],
        "returns": "void * (dst)",
        "binding": "patch-call-site",
        "side_effects": [
            "copy count bytes from src to dst without overlap semantics",
            "bounds-check both ranges against the mapped regions",
        ],
        "status": "modeled",
        "notes": "An overlapping copy is reported as a harness error, not fixed.",
    },
    {
        "name": "strlen",
        "dll": "internal",
        "signature": "size_t strlen(const char *s);",
        "args": [{"name": "s", "type": "const char *"}],
        "returns": "size_t (bytes before the NUL)",
        "binding": "patch-call-site",
        "side_effects": [
            "scan at most 4096 bytes inside one mapped region",
            "stop at the first NUL byte and return the length",
        ],
        "status": "modeled",
        "notes": "A missing NUL is a harness error with the readable prefix.",
    },
    {
        "name": "sprintf",
        "dll": "internal",
        "signature": "int sprintf(char *buf, const char *fmt, ...);",
        "args": [
            {"name": "buf", "type": "char *"},
            {"name": "fmt", "type": "const char *"},
            {"name": "...", "type": "varargs"},
        ],
        "returns": "int (bytes written, excluding the NUL)",
        "binding": "patch-call-site",
        "side_effects": [
            "format only %s, %d, %u, %x and %% with SH-4 cdecl varargs",
            "write the result and a trailing NUL into buf",
            "reject any other conversion instead of guessing",
        ],
        "status": "planned",
        "notes": (
            "Which conversions the readers use is UNKNOWN; extend only after "
            "a trace shows the format string."
        ),
    },
    {
        "name": "OSM_Printf",
        "dll": "internal",
        "signature": "int OSM_Printf(const char *fmt, ...);",
        "args": [
            {"name": "fmt", "type": "const char *"},
            {"name": "...", "type": "varargs"},
        ],
        "returns": "int (bytes formatted)",
        "binding": "patch-call-site",
        "side_effects": [
            "format the arguments with the same limited sprintf subset",
            "append one line to the captured diagnostic log",
            "never write to a screen or a host terminal",
        ],
        "status": "modeled",
        "notes": (
            "Clarion diagnostic helper; the exact prototype is HYPOTHESIS from "
            "the firmware strings, not from a header. It is the cheapest way "
            "to see a field-level rejection reason."
        ),
    },
    {
        "name": "OSM_LogMsg",
        "dll": "internal",
        "signature": "void OSM_LogMsg(int level, const char *msg);",
        "args": [
            {"name": "level", "type": "int"},
            {"name": "msg", "type": "const char *"},
        ],
        "returns": "void",
        "binding": "patch-call-site",
        "side_effects": [
            "append 'level\\tmsg' to the captured diagnostic log",
            "truncate the message at the first NUL or 4096 bytes",
        ],
        "status": "planned",
        "notes": (
            "Argument count and level encoding are UNKNOWN; keep the stub "
            "behind a flag until a trace confirms it."
        ),
    },
    {
        "name": "StatusData",
        "dll": "internal",
        "signature": "UNKNOWN (see notes)",
        "args": [],
        "returns": "UNKNOWN",
        "binding": "unresolved",
        "side_effects": [
            "must not be guessed: stop the run and report the call site",
        ],
        "status": "planned",
        "notes": (
            "Mentioned as a diagnostic sink in the L3 design, but no "
            "signature, argument count or caller has been recovered. The "
            "harness treats a call as BLOCKED."
        ),
    },
]

#: Reader id (see :mod:`manifest`) -> stub names it needs.
READER_STUBS = {
    "cmp_lst": [
        "CreateFileW",
        "CreateFileA",
        "ReadFile",
        "CloseHandle",
        "OSM_Printf",
        "OSM_LogMsg",
    ],
    "cmp_ind": [
        "CreateFileW",
        "CreateFileA",
        "ReadFile",
        "SetFilePointer",
        "GetFileSize",
        "CloseHandle",
        "HeapAlloc",
        "HeapFree",
        "memset",
        "memcpy",
        "OSM_Printf",
        "OSM_LogMsg",
    ],
    "drstr": [
        "CreateFileW",
        "ReadFile",
        "SetFilePointer",
        "CloseHandle",
        "LocalAlloc",
        "LocalFree",
        "HeapAlloc",
        "memset",
        "memcpy",
        "OSM_Printf",
        "OSM_LogMsg",
    ],
    "tile": [
        "CreateFileW",
        "ReadFile",
        "SetFilePointer",
        "GetFileSize",
        "CloseHandle",
        "HeapAlloc",
        "HeapFree",
        "memset",
        "memcpy",
        "OSM_Printf",
        "OSM_LogMsg",
    ],
    "hdd_info": [
        "CreateFileW",
        "ReadFile",
        "CloseHandle",
        "memcpy",
        "sprintf",
        "OSM_Printf",
        "OSM_LogMsg",
    ],
}

REQUIRED_STUBS = (
    "CreateFileW",
    "CreateFileA",
    "ReadFile",
    "SetFilePointer",
    "CloseHandle",
    "GetFileSize",
    "LocalAlloc",
    "HeapAlloc",
    "memset",
    "memcpy",
    "OSM_Printf",
    "OSM_LogMsg",
)

_ENTRY_KEYS = {
    "name",
    "dll",
    "signature",
    "args",
    "returns",
    "binding",
    "side_effects",
    "status",
    "notes",
}


def by_name(name: str) -> dict | None:
    for stub in STUBS:
        if stub["name"] == name:
            return stub
    return None


def names() -> list[str]:
    return [stub["name"] for stub in STUBS]


def validate(table=None) -> list[str]:
    """Return table problems; an empty list means the table is usable."""

    table = STUBS if table is None else table
    problems: list[str] = []
    if not isinstance(table, list) or not table:
        return ["stub table must be a non-empty list"]

    seen: set[str] = set()
    for index, entry in enumerate(table):
        where = f"stubs[{index}]"
        if not isinstance(entry, dict):
            problems.append(f"{where}: entry is not an object")
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            problems.append(f"{where}: missing name")
            continue
        where = f"stubs[{index}] ({name})"
        if name in seen:
            problems.append(f"{where}: duplicate stub name")
        seen.add(name)

        unknown = sorted(set(entry) - _ENTRY_KEYS)
        if unknown:
            problems.append(f"{where}: unknown key(s) {unknown}")

        for key in ("dll", "signature", "returns", "status", "binding", "notes"):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                problems.append(f"{where}: {key} must be a non-empty string")

        if entry.get("status") not in STATUSES:
            problems.append(
                f"{where}: status must be one of {list(STATUSES)}"
            )
        if entry.get("binding") not in BINDINGS:
            problems.append(
                f"{where}: binding must be one of {list(BINDINGS)}"
            )

        signature = entry.get("signature", "")
        if (
            isinstance(signature, str)
            and isinstance(name, str)
            and entry.get("binding") != "unresolved"
        ):
            if name not in signature:
                problems.append(f"{where}: signature does not contain the name")

        args = entry.get("args")
        if not isinstance(args, list):
            problems.append(f"{where}: args must be a list")
        else:
            for arg_index, arg in enumerate(args):
                if not isinstance(arg, dict):
                    problems.append(f"{where}: args[{arg_index}] is not an object")
                    continue
                for key in ("name", "type"):
                    if not isinstance(arg.get(key), str) or not arg.get(key):
                        problems.append(
                            f"{where}: args[{arg_index}].{key} must be a "
                            "non-empty string"
                        )

        effects = entry.get("side_effects")
        if not isinstance(effects, list) or not effects:
            problems.append(f"{where}: side_effects must be a non-empty list")
        else:
            for effect_index, effect in enumerate(effects):
                if not isinstance(effect, str) or not effect:
                    problems.append(
                        f"{where}: side_effects[{effect_index}] must be a "
                        "non-empty string"
                    )

    missing = [name for name in REQUIRED_STUBS if name not in seen]
    if missing:
        problems.append(f"missing required stubs: {missing}")

    for reader, wanted in READER_STUBS.items():
        if not isinstance(wanted, list) or not wanted:
            problems.append(f"READER_STUBS[{reader}]: must be a non-empty list")
            continue
        for stub_name in wanted:
            if stub_name not in seen:
                problems.append(
                    f"READER_STUBS[{reader}]: unknown stub {stub_name!r}"
                )

    return problems


def json_schema() -> dict:
    """Return the JSON Schema for a stub table document."""

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA,
        "title": "OSM2Leaf L3 WinCE stub table",
        "description": (
            "Declarative model of every WinCE/internal call the L3 harness "
            "replaces. Deterministic: no wall clock, no uninitialised memory."
        ),
        "type": "object",
        "required": ["schema", "stubs", "readers"],
        "additionalProperties": False,
        "properties": {
            "schema": {"const": SCHEMA},
            "stubs": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/$defs/stub"},
            },
            "readers": {
                "type": "object",
                "additionalProperties": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
        },
        "$defs": {
            "stub": {
                "type": "object",
                "required": [
                    "name",
                    "dll",
                    "signature",
                    "args",
                    "returns",
                    "binding",
                    "side_effects",
                    "status",
                    "notes",
                ],
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string", "minLength": 1},
                    "dll": {"type": "string", "minLength": 1},
                    "signature": {"type": "string", "minLength": 1},
                    "args": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "type"],
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "minLength": 1},
                                "type": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "returns": {"type": "string", "minLength": 1},
                    "binding": {"enum": list(BINDINGS)},
                    "side_effects": {
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "string", "minLength": 1},
                    },
                    "status": {"enum": list(STATUSES)},
                    "notes": {"type": "string", "minLength": 1},
                },
            }
        },
    }


def document() -> dict:
    return {"schema": SCHEMA, "stubs": STUBS, "readers": READER_STUBS}


def _print_list() -> None:
    print(f"{'name':<16} {'status':<8} {'binding':<16} returns")
    print("-" * 84)
    for stub in STUBS:
        print(
            f"{stub['name']:<16} {stub['status']:<8} "
            f"{stub['binding']:<16} {stub['returns']}"
        )
    print()
    print(f"{len(STUBS)} stubs; readers: {', '.join(sorted(READER_STUBS))}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WinCE stub table for L3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="human-readable table")
    sub.add_parser("json", help="dump the table as JSON")
    sub.add_parser("schema", help="print the JSON Schema")
    sub.add_parser("selftest", help="run the package self-test")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from l3_harness import selftest

        return selftest.main([])

    problems = validate()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    if args.command == "list":
        _print_list()
    elif args.command == "json":
        print(json.dumps(document(), indent=2))
    elif args.command == "schema":
        print(json.dumps(json_schema(), indent=2))
    else:
        parser.error(f"unknown command {args.command!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
