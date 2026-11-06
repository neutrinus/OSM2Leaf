#!/usr/bin/env python3
"""Declarative WinCE API stub table for the L3 harness.

The firmware calls ``coredll`` and its own logging helpers.  The L3 harness
replaces those calls with deterministic host-side models; this module is the
single source of truth for what each model does, so the Ghidra script and the
documentation cannot drift apart.

Every entry is **bound to an exporter**, not just to a C name: ``module`` +
``export`` + ``ordinal`` give the ``module!name`` key a call site is resolved
through.  :func:`binding_index` and :func:`ordinal_index` are the lookup
tables; :mod:`dispatch` uses them to answer a call target or to stop with
``missing stub: NAME``.

Every entry records:

``name``
    Imported symbol name.
``module``
    Exporting module (``"coredll.dll"``), or ``"internal"`` for app/library
    helpers.  Normalised by :func:`normalize_module` for the key.
``export``
    Export name in that module; the binding key is ``module!export``.
``ordinal``
    Export ordinal when it is known from ``cerom.py exports`` (C-527), else
    ``None``.  Never guessed: an unknown ordinal is resolved by name only.
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

The host-side implementations live in :mod:`dispatch`; the table stays
declarative so a missing implementation or a missing export is visible here.

Usage::

    python3 tools/l3_harness/stubs.py list
    python3 tools/l3_harness/stubs.py bindings
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
        "module": "coredll.dll",
        "export": "CreateFileW",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "CreateFileA",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "ReadFile",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "SetFilePointer",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "GetFileSize",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "CloseHandle",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "LocalAlloc",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "LocalFree",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "HeapAlloc",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "HeapFree",
        "ordinal": None,
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
        "module": "internal",
        "export": "memset",
        "ordinal": None,
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
        "module": "internal",
        "export": "memcpy",
        "ordinal": None,
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
        "module": "internal",
        "export": "strlen",
        "ordinal": None,
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
        "module": "coredll.dll",
        "export": "sprintf",
        "ordinal": 719,
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
            "accept '-' and '0' flags plus a decimal width, nothing else",
            "write the result and a trailing NUL into buf",
            "reject any other conversion instead of guessing",
        ],
        "status": "modeled",
        "notes": (
            "Ordinal 719 on this image (C-527, `cerom.py exports coredll.dll`); "
            "the name binding also works, and the ordinal is the only one in "
            "the table that is VERIFIED. Conversions outside the listed subset "
            "stop the run."
        ),
    },
    {
        "name": "OSM_Printf",
        "module": "internal",
        "export": "OSM_Printf",
        "ordinal": None,
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
        "module": "internal",
        "export": "OSM_LogMsg",
        "ordinal": None,
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
        "module": "internal",
        "export": "StatusData",
        "ordinal": None,
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
    {
        "name": "InitializeCriticalSection",
        "module": "coredll.dll",
        "export": "InitializeCriticalSection",
        "ordinal": None,
        "signature": "void InitializeCriticalSection(LPCRITICAL_SECTION lpCriticalSection);",
        "args": [{"name": "lpCriticalSection", "type": "LPCRITICAL_SECTION"}],
        "returns": "void",
        "binding": "patch-call-site",
        "side_effects": [
            "register the pointer as an initialised section with depth 0",
            "reject NULL or an already initialised section as a harness error",
        ],
        "status": "modeled",
        "notes": (
            "An L3 run is single-threaded, so the section serialises nothing; "
            "the model still tracks init/enter/leave order because a wrong "
            "order would mask a real bug in the caller."
        ),
    },
    {
        "name": "EnterCriticalSection",
        "module": "coredll.dll",
        "export": "EnterCriticalSection",
        "ordinal": None,
        "signature": "void EnterCriticalSection(LPCRITICAL_SECTION lpCriticalSection);",
        "args": [{"name": "lpCriticalSection", "type": "LPCRITICAL_SECTION"}],
        "returns": "void",
        "binding": "patch-call-site",
        "side_effects": [
            "increment the recursion depth of an initialised section",
            "reject an uninitialised pointer or NULL",
        ],
        "status": "modeled",
        "notes": "Recursive entry is allowed, as the Win32 contract allows it.",
    },
    {
        "name": "LeaveCriticalSection",
        "module": "coredll.dll",
        "export": "LeaveCriticalSection",
        "ordinal": None,
        "signature": "void LeaveCriticalSection(LPCRITICAL_SECTION lpCriticalSection);",
        "args": [{"name": "lpCriticalSection", "type": "LPCRITICAL_SECTION"}],
        "returns": "void",
        "binding": "patch-call-site",
        "side_effects": [
            "decrement the recursion depth; it must stay >= 0",
            "reject an uninitialised pointer or a leave without an enter",
        ],
        "status": "modeled",
        "notes": "A leave without a matching enter is an error, not a no-op.",
    },
    {
        "name": "DeleteCriticalSection",
        "module": "coredll.dll",
        "export": "DeleteCriticalSection",
        "ordinal": None,
        "signature": "void DeleteCriticalSection(LPCRITICAL_SECTION lpCriticalSection);",
        "args": [{"name": "lpCriticalSection", "type": "LPCRITICAL_SECTION"}],
        "returns": "void",
        "binding": "patch-call-site",
        "side_effects": [
            "forget the section; its depth must be 0",
            "reject a still-held or uninitialised section",
        ],
        "status": "modeled",
        "notes": "A leaked held section is reported, not silently discarded.",
    },
    {
        "name": "RegOpenKeyExW",
        "module": "coredll.dll",
        "export": "RegOpenKeyExW",
        "ordinal": None,
        "signature": (
            "LONG RegOpenKeyExW(HKEY hKey, LPCWSTR lpSubKey, DWORD ulOptions, "
            "REGSAM samDesired, PHKEY phkResult);"
        ),
        "args": [
            {"name": "hKey", "type": "HKEY"},
            {"name": "lpSubKey", "type": "LPCWSTR"},
            {"name": "ulOptions", "type": "DWORD"},
            {"name": "samDesired", "type": "REGSAM"},
            {"name": "phkResult", "type": "PHKEY"},
        ],
        "returns": "LONG (0 ERROR_SUCCESS, 2 ERROR_FILE_NOT_FOUND)",
        "binding": "patch-call-site",
        "side_effects": [
            "resolve the key in the registry fixture loaded from JSON",
            "return a synthetic key handle for a key that exists",
            "write ERROR_FILE_NOT_FOUND without a handle when the key is absent",
            "reject a non-zero ulOptions instead of guessing",
        ],
        "status": "modeled",
        "notes": (
            "The firmware reads path/configuration state from the registry; "
            "the harness takes that state from a JSON fixture, never from the "
            "host registry or hive files."
        ),
    },
    {
        "name": "RegQueryValueExW",
        "module": "coredll.dll",
        "export": "RegQueryValueExW",
        "ordinal": None,
        "signature": (
            "LONG RegQueryValueExW(HKEY hKey, LPCWSTR lpValueName, "
            "LPDWORD lpReserved, LPDWORD lpType, LPBYTE lpData, "
            "LPDWORD lpcbData);"
        ),
        "args": [
            {"name": "hKey", "type": "HKEY"},
            {"name": "lpValueName", "type": "LPCWSTR"},
            {"name": "lpReserved", "type": "LPDWORD"},
            {"name": "lpType", "type": "LPDWORD"},
            {"name": "lpData", "type": "LPBYTE"},
            {"name": "lpcbData", "type": "LPDWORD"},
        ],
        "returns": "LONG (0, 2 ERROR_FILE_NOT_FOUND, 234 ERROR_MORE_DATA)",
        "binding": "patch-call-site",
        "side_effects": [
            "look the value up by name in the opened key (case-insensitive)",
            "write REG_SZ as UTF-16LE + NUL, REG_DWORD as 4 bytes, REG_BINARY verbatim",
            "copy min(available, *lpcbData) and write the real size back",
            "return ERROR_MORE_DATA for a short buffer without a partial copy",
        ],
        "status": "modeled",
        "notes": (
            "Registry strings are UTF-16LE like the W API family; check > 2 "
            "bytes are written back so a caller's two-pass query works."
        ),
    },
    {
        "name": "RegCloseKey",
        "module": "coredll.dll",
        "export": "RegCloseKey",
        "ordinal": None,
        "signature": "LONG RegCloseKey(HKEY hKey);",
        "args": [{"name": "hKey", "type": "HKEY"}],
        "returns": "LONG (0 ERROR_SUCCESS, 6 ERROR_INVALID_HANDLE)",
        "binding": "patch-call-site",
        "side_effects": [
            "drop a synthetic key handle",
            "return ERROR_INVALID_HANDLE for a predefined or unknown handle",
        ],
        "status": "modeled",
        "notes": "Predefined root handles are not closable, as on WinCE.",
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
    "LocalFree",
    "HeapAlloc",
    "HeapFree",
    "memset",
    "memcpy",
    "strlen",
    "sprintf",
    "OSM_Printf",
    "OSM_LogMsg",
    "InitializeCriticalSection",
    "EnterCriticalSection",
    "LeaveCriticalSection",
    "DeleteCriticalSection",
    "RegOpenKeyExW",
    "RegQueryValueExW",
    "RegCloseKey",
)

_ENTRY_KEYS = {
    "name",
    "module",
    "export",
    "ordinal",
    "signature",
    "args",
    "returns",
    "binding",
    "side_effects",
    "status",
    "notes",
}


def normalize_module(module: str) -> str:
    """Canonical exporter key: lowercase basename, no ``.dll``/``.exe``.

    ``"COREDLL.dll"``, ``"coredll"`` and ``"C:\\Windows\\coredll.dll"`` all
    become ``"coredll"``, so the same key matches ``cerom.py`` display names,
    names-DB modules and the table.
    """

    text = str(module or "").strip().replace("\\", "/")
    text = text.rsplit("/", 1)[-1].lower()
    for suffix in (".dll", ".exe"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return text


def stub_key(stub: dict) -> str:
    """Binding key ``module!export`` for one table entry."""

    return f"{normalize_module(stub['module'])}!{stub['export']}"


def ordinal_key(stub: dict) -> str | None:
    """Ordinal binding key ``module!#ordinal``, or ``None`` when unknown."""

    ordinal = stub.get("ordinal")
    if ordinal is None:
        return None
    return f"{normalize_module(stub['module'])}!#{ordinal}"


def by_name(name: str) -> dict | None:
    for stub in STUBS:
        if stub["name"] == name:
            return stub
    return None


def by_key(key: str, table=None) -> dict | None:
    return binding_index(table).get(key)


def binding_index(table=None) -> dict[str, dict]:
    """``module!export`` -> stub entry (the primary call-target index)."""

    index: dict[str, dict] = {}
    for stub in STUBS if table is None else table:
        index[stub_key(stub)] = stub
    return index


def ordinal_index(table=None) -> dict[tuple[str, int], dict]:
    """``(module, ordinal)`` -> stub entry, for ordinals that are known."""

    index: dict[tuple[str, int], dict] = {}
    for stub in STUBS if table is None else table:
        ordinal = stub.get("ordinal")
        if ordinal is not None:
            index[(normalize_module(stub["module"]), ordinal)] = stub
    return index


def load_export_names(path) -> dict[str, dict[int, str]]:
    """Load a ``cerom.py`` export-names DB as ``{module: {ordinal: name}}``.

    Accepted shapes (the loader in ``tools/cerom.py`` accepts the same three):

    * ``{"modules": {"coredll.dll": {"719": "sprintf"}}}``;
    * ``{"coredll.dll": {"719": "sprintf"}}``;
    * ``[{"module"/"dll": "coredll.dll", "ordinal": 719, "name": "sprintf"}]``.

    Only names and ordinals are read; no image bytes and no host path.
    """

    with open(path, "r", encoding="utf-8") as handle:
        doc = json.load(handle)

    result: dict[str, dict[int, str]] = {}

    def add(module, ordinal, name) -> None:
        if module is None or ordinal is None or name is None:
            return
        try:
            number = int(ordinal)
        except (TypeError, ValueError):
            return
        result.setdefault(normalize_module(module), {})[number] = str(name)

    if isinstance(doc, dict) and isinstance(doc.get("modules"), dict):
        doc = doc["modules"]

    if isinstance(doc, list):
        for record in doc:
            if isinstance(record, dict):
                add(
                    record.get("module") or record.get("dll"),
                    record.get("ordinal"),
                    record.get("name"),
                )
    elif isinstance(doc, dict):
        for module, mapping in doc.items():
            if module in ("schema", "notes") or not isinstance(mapping, dict):
                continue
            for ordinal, name in mapping.items():
                add(module, ordinal, name)

    return result


def bind_exports(exports, table=None) -> tuple[list[dict], list[str]]:
    """Fill unknown ordinals from an export-names table.

    ``exports`` is :func:`load_export_names` output.  Returns a new table and
    a list of problems: an ordinal that disagrees with a known one is a
    problem, never a silent overwrite.
    """

    import copy

    new_table = copy.deepcopy(STUBS if table is None else table)
    problems: list[str] = []
    normalised: dict[str, dict[int, str]] = {}
    for module, mapping in (exports or {}).items():
        for ordinal, name in (mapping or {}).items():
            try:
                number = int(ordinal)
            except (TypeError, ValueError):
                continue
            normalised.setdefault(normalize_module(module), {})[number] = str(name)
    for stub in new_table:
        module = normalize_module(stub["module"])
        by_ordinal = normalised.get(module, {})
        name_to_ordinal = {name: number for number, name in by_ordinal.items()}
        found = name_to_ordinal.get(stub["export"])
        if found is None:
            continue
        if stub.get("ordinal") is None:
            stub["ordinal"] = found
        elif stub["ordinal"] != found:
            problems.append(
                f"{stub_key(stub)}: table ordinal {stub['ordinal']} disagrees "
                f"with the export table ({found})"
            )
    return new_table, problems


def names() -> list[str]:
    return [stub["name"] for stub in STUBS]


def validate(table=None) -> list[str]:
    """Return table problems; an empty list means the table is usable."""

    table = STUBS if table is None else table
    problems: list[str] = []
    if not isinstance(table, list) or not table:
        return ["stub table must be a non-empty list"]

    seen: set[str] = set()
    seen_keys: set[str] = set()
    seen_ordinals: set[tuple[str, int]] = set()
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

        for key in (
            "module",
            "export",
            "signature",
            "returns",
            "status",
            "binding",
            "notes",
        ):
            if not isinstance(entry.get(key), str) or not entry.get(key):
                problems.append(f"{where}: {key} must be a non-empty string")

        export = entry.get("export")
        if isinstance(export, str) and export and export != name:
            problems.append(
                f"{where}: export {export!r} must equal the stub name {name!r}"
            )

        ordinal = entry.get("ordinal")
        if ordinal is not None:
            if isinstance(ordinal, bool) or not isinstance(ordinal, int):
                problems.append(f"{where}: ordinal must be an integer or null")
            elif ordinal < 0:
                problems.append(f"{where}: ordinal must be non-negative")

        if (
            isinstance(entry.get("module"), str)
            and entry.get("module")
            and isinstance(export, str)
            and export
        ):
            key = stub_key(entry)
            if key in seen_keys:
                problems.append(f"{where}: duplicate binding key {key!r}")
            seen_keys.add(key)
            okey = ordinal_key(entry)
            if okey is not None and isinstance(ordinal, int):
                pair = (key.split("!", 1)[0], ordinal)
                if pair in seen_ordinals:
                    problems.append(f"{where}: duplicate ordinal {okey!r}")
                seen_ordinals.add(pair)

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
                    "module",
                    "export",
                    "ordinal",
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
                    "module": {"type": "string", "minLength": 1},
                    "export": {"type": "string", "minLength": 1},
                    "ordinal": {"type": ["integer", "null"], "minimum": 0},
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
    print(f"{'name':<26} {'status':<8} {'binding':<16} return")
    print("-" * 96)
    for stub in STUBS:
        print(
            f"{stub_key(stub):<26} {stub['status']:<8} "
            f"{stub['binding']:<16} {stub['returns']}"
        )
    print()
    print(
        f"{len(STUBS)} stubs ({sum(1 for s in STUBS if s['status'] == 'modeled')} "
        f"modeled, {sum(1 for s in STUBS if s['status'] == 'planned')} planned); "
        f"readers: {', '.join(sorted(READER_STUBS))}"
    )


def _print_bindings() -> None:
    print(f"{'module!export':<34} {'ordinal':<10} status")
    print("-" * 64)
    for stub in STUBS:
        ordinal = stub.get("ordinal")
        print(
            f"{stub_key(stub):<34} "
            f"{'#%d' % ordinal if ordinal is not None else '-':<10} "
            f"{stub['status']}"
        )


def selftest() -> int:
    """Validate the table, then run every stub through the dispatcher."""

    problems = validate()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1
    modeled = sum(1 for stub in STUBS if stub["status"] == "modeled")
    planned = len(STUBS) - modeled
    print(
        f"stub table: {len(STUBS)} entries, {modeled} modeled, "
        f"{planned} planned, {len(binding_index())} binding keys"
    )
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from l3_harness import dispatch

    return dispatch.selftest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="WinCE stub table for L3")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="human-readable table")
    sub.add_parser("bindings", help="module!export and ordinal keys")
    sub.add_parser("json", help="dump the table as JSON")
    sub.add_parser("schema", help="print the JSON Schema")
    sub.add_parser("selftest", help="table checks plus a dispatcher self-test")
    return parser


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["--selftest"]:
        argv = ["selftest"]

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "selftest":
        return selftest()

    problems = validate()
    if problems:
        for problem in problems:
            print(f"error: {problem}", file=sys.stderr)
        return 1

    if args.command == "list":
        _print_list()
    elif args.command == "bindings":
        _print_bindings()
    elif args.command == "json":
        print(json.dumps(document(), indent=2))
    elif args.command == "schema":
        print(json.dumps(json_schema(), indent=2))
    else:
        parser.error(f"unknown command {args.command!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
