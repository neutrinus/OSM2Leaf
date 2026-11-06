#!/usr/bin/env python3
"""Report which zlib the interpreter actually links, and whether it can be trusted.

The Leaf ZE0 map formats store streams compressed by **stock zlib 1.3.1**
(level 6, windowBits 15, memLevel 8, default strategy).  zlib-ng, which some
Python 3.14 builds ship, produces a *valid but different* stream: it inflates
correctly, yet reproduces 0 of the factory `.cmp` files (C-192) and 0 of the
coarse `LEV3456R.DAT` records (C-997).  A tool that recompresses and claims
byte-identity must therefore distinguish

* ``FAIL`` — the data or the model is wrong, and
* ``UNVERIFIABLE`` — the compressor build cannot reproduce the reference bytes.

This module is that distinction, shared by ``lev3456.py``, ``cmpind.py``,
``cmpind_writer.py`` and ``ind_mutate.py`` so no tool reports a false FAIL on a
zlib-ng machine.

The classifier looks at ``zlib.ZLIB_VERSION`` (the header Python was built
against) and ``zlib.ZLIB_RUNTIME_VERSION`` (the library loaded at run time):

==================  =========================================  ============
flavour             condition                                  trusted
==================  =========================================  ============
``stock``           both plain numeric versions, equal          yes
``zlib-ng``         either version string contains ``zlib-ng``  no
``unknown``         anything else (e.g. versions differ)        no
==================  =========================================  ============

``Runtime.reference`` is true only for the pinned reference build 1.3.1.

Commands::

    python3 tools/zlibinfo.py                     # one line, exit 0
    python3 tools/zlibinfo.py --json              # machine-readable
    python3 tools/zlibinfo.py --require-stock-zlib  # exit 3 when untrusted
    python3 tools/zlibinfo.py --selftest

Exit codes: ``0`` fine (or reported), ``3`` = **unverifiable** (never used for
a data failure), ``2`` usage error.

Selftest note: a zlib-ng machine is simulated by passing fake version strings
to :func:`classify`; ``zlib`` itself is never monkeypatched.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zlib
from dataclasses import dataclass

REFERENCE_VERSION = "1.3.1"
EXIT_UNVERIFIABLE = 3

STOCK = "stock"
ZLIB_NG = "zlib-ng"
UNKNOWN = "unknown"

# A plain upstream version has a numeric X.Y or X.Y.Z tail and nothing else.
_PLAIN_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?$")


@dataclass(frozen=True)
class Runtime:
    """What the interpreter links, and whether a byte-identity claim holds."""

    build: str
    runtime: str
    flavour: str
    ok: bool
    reference: bool

    def line(self) -> str:
        if self.flavour == ZLIB_NG:
            why = "zlib-ng: not the reference compressor"
        elif self.flavour == UNKNOWN:
            why = "unknown build: header and runtime versions do not identify stock zlib"
        elif self.reference:
            why = "stock, reference build"
        else:
            why = "stock, not the pinned reference %s" % REFERENCE_VERSION
        return "zlib %s, runtime %s (%s)" % (self.build, self.runtime, why)

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "zlib_version": self.build,
            "runtime_version": self.runtime,
            "flavour": self.flavour,
            "reference": self.reference,
            "message": self.line(),
        }


def classify(build: str | None = None, runtime: str | None = None) -> Runtime:
    """Classify a ``(ZLIB_VERSION, ZLIB_RUNTIME_VERSION)`` pair.

    Defaults to the running interpreter.  Explicit strings are what the
    selftest uses, so zlib is never patched.
    """
    if build is None:
        build = zlib.ZLIB_VERSION
    if runtime is None:
        runtime = getattr(zlib, "ZLIB_RUNTIME_VERSION", build)
    low_b = build.lower()
    low_r = runtime.lower()
    if "zlib-ng" in low_b or "zlib-ng" in low_r:
        return Runtime(build, runtime, ZLIB_NG, False, False)
    if _PLAIN_VERSION.match(build) and _PLAIN_VERSION.match(runtime) and build == runtime:
        return Runtime(build, runtime, STOCK, True, runtime == REFERENCE_VERSION)
    return Runtime(build, runtime, UNKNOWN, False, False)


def current() -> Runtime:
    return classify()


def runtime_ok(runtime: Runtime | str | None = None, build: str | None = None) -> bool:
    """True when the running zlib is the stock upstream library.

    Accepts an explicit :class:`Runtime` or a fake runtime version string, so
    callers and the selftest can ask the same question without patching zlib.
    """
    if isinstance(runtime, Runtime):
        return runtime.ok
    return classify(build, runtime).ok


def describe(runtime: Runtime | str | None = None, build: str | None = None) -> str:
    """One human-readable line naming both zlib versions and the verdict."""
    if isinstance(runtime, Runtime):
        return runtime.line()
    return classify(build, runtime).line()


def describe_json(runtime: Runtime | str | None = None, build: str | None = None) -> dict:
    if isinstance(runtime, Runtime):
        return runtime.as_dict()
    return classify(build, runtime).as_dict()


# ---------------------------------------------------------------------------
# reporting and refusal
# ---------------------------------------------------------------------------


def report(runtime: Runtime | None = None, stream=None) -> Runtime:
    """Print the runtime line and return it (used by tools that recompress)."""
    rt = runtime or current()
    print("zlib: %s" % rt.line(), file=stream or sys.stdout)
    return rt


def claim_warning(runtime: Runtime, tool: str, require_stock: bool = False) -> str | None:
    """The message a tool prints when it cannot prove byte-identity, else None."""
    if runtime.ok:
        return None
    what = ("zlib-ng" if runtime.flavour == ZLIB_NG else "this zlib build")
    if require_stock:
        return (
            "%s: refusing to run: --require-stock-zlib needs stock zlib, "
            "this interpreter reports %s. Exit %d (unverifiable), not a data failure."
            % (tool, what, EXIT_UNVERIFIABLE)
        )
    return (
        "%s: %s cannot reproduce the factory streams, so a byte-identical "
        "result is UNVERIFIABLE here (exit %d). Re-run with stock zlib %s "
        "(e.g. python3.13). Data-level checks still run and are reported normally."
        % (tool, what, EXIT_UNVERIFIABLE, REFERENCE_VERSION)
    )


def guard(
    *,
    tool: str,
    require_stock: bool = False,
    claims_identity: bool = True,
    always_report: bool = True,
    runtime: Runtime | None = None,
    stream=None,
) -> Runtime:
    """Print the runtime, warn on an untrusted build, refuse when asked to.

    ``claims_identity`` says the caller is about to assert byte-identity; only
    then is the warning useful.  ``require_stock`` turns the warning into a
    ``SystemExit(3)`` *before* any work is done.  The returned :class:`Runtime`
    tells the caller (``rt.ok``) how to label an identity mismatch: on a
    trusted build it is a ``FAIL`` (exit 1), otherwise ``UNVERIFIABLE``
    (exit 3).
    """
    stream = stream or sys.stdout
    rt = runtime or current()
    if always_report or not rt.ok:
        print("zlib: %s" % rt.line(), file=stream)
    if claims_identity and not rt.ok:
        message = claim_warning(rt, tool, require_stock)
        print(message, file=stream)
        if require_stock:
            raise SystemExit(EXIT_UNVERIFIABLE)
    return rt


def note_if_nonstock(
    *, tool: str, note: str, runtime: Runtime | None = None, stream=None
) -> Runtime:
    """A one-line note for tools that never recompress (stock output is silent)."""
    rt = runtime or current()
    if not rt.ok:
        print("zlib: %s" % rt.line(), file=stream or sys.stderr)
        print("%s: %s" % (tool, note), file=stream or sys.stderr)
    return rt


def unverifiable(
    runtime: Runtime, tool: str, reason: str, stream=None
) -> int:
    """Print why an identity claim cannot be decided; return the exit code."""
    print("UNVERIFIABLE: %s: %s" % (tool, reason), file=stream or sys.stdout)
    print("zlib: %s" % runtime.line(), file=stream or sys.stdout)
    print(
        "This is not a data failure (exit %d). Re-run with stock zlib %s."
        % (EXIT_UNVERIFIABLE, REFERENCE_VERSION),
        file=stream or sys.stdout,
    )
    return EXIT_UNVERIFIABLE


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _null():
    import io

    return io.StringIO()


def selftest() -> int:
    import io

    stock = classify("1.3.1", "1.3.1")
    assert stock.flavour == STOCK and stock.ok and stock.reference, stock
    assert runtime_ok(stock) and runtime_ok("1.3.1", "1.3.1")

    older = classify("1.2.11", "1.2.11")
    assert older.flavour == STOCK and older.ok and not older.reference, older
    assert runtime_ok(older) and not runtime_ok("1.3.1.zlib-ng")

    ng = classify("1.3.1.zlib-ng", "1.3.1.zlib-ng")
    assert ng.flavour == ZLIB_NG and not ng.ok and not ng.reference, ng
    assert "zlib-ng" in describe(ng) and "1.3.1.zlib-ng" in describe(ng)
    assert not describe_json(ng)["ok"] and describe_json(ng)["flavour"] == ZLIB_NG

    # zlib-ng names only the runtime library; the header version can stay plain
    ng_runtime_only = classify("1.3.1", "1.3.1.zlib-ng")
    assert ng_runtime_only.flavour == ZLIB_NG and not ng_runtime_only.ok

    mixed = classify("1.3.1", "1.2.13")
    assert mixed.flavour == UNKNOWN and not mixed.ok, mixed
    assert "do not identify stock zlib" in describe(mixed)

    warning = claim_warning(ng, "tools/example.py verify")
    assert warning and "UNVERIFIABLE" in warning and "--require-stock-zlib" not in warning
    refusal = claim_warning(ng, "tools/example.py verify", require_stock=True)
    assert refusal and "--require-stock-zlib" in refusal and "Exit 3" in refusal
    assert claim_warning(stock, "tools/example.py verify") is None

    # The guard must refuse with 3 (not 1) on a fake zlib-ng runtime.
    try:
        guard(
            tool="tools/example.py verify",
            require_stock=True,
            runtime=ng,
            stream=_null(),
        )
    except SystemExit as exc:
        assert exc.code == EXIT_UNVERIFIABLE, exc.code
    else:
        raise AssertionError("guard must refuse on zlib-ng with --require-stock-zlib")

    # ...and only warn (no exit) without the flag.
    rt = guard(tool="tools/example.py verify", runtime=ng, stream=_null())
    assert not rt.ok
    assert guard(tool="tools/example.py verify", runtime=stock, stream=_null()).ok

    # A tool that never recompresses stays silent on stock zlib.
    buf = io.StringIO()
    note_if_nonstock(tool="tools/x.py", note="no recompression", runtime=stock, stream=buf)
    assert buf.getvalue() == "", buf.getvalue()
    note_if_nonstock(tool="tools/x.py", note="no recompression", runtime=ng, stream=buf)
    assert "zlib-ng" in buf.getvalue() and "no recompression" in buf.getvalue()

    assert unverifiable(ng, "tools/x.py verify", "streams differ", stream=_null()) == 3
    print("zlibinfo selftest: OK (11 checks, fake zlib-ng strings, zlib untouched)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument(
        "--require-stock-zlib",
        action="store_true",
        help="exit 3 (unverifiable) when this interpreter does not link stock zlib",
    )
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    rt = current()
    if args.json:
        print(json.dumps(rt.as_dict(), indent=2))
    else:
        print("zlib: %s" % rt.line())
    if args.require_stock_zlib and not rt.ok:
        print(
            "zlibinfo: --require-stock-zlib needs stock zlib; this interpreter "
            "reports %s (exit %d, unverifiable)."
            % ("zlib-ng" if rt.flavour == ZLIB_NG else rt.runtime, EXIT_UNVERIFIABLE)
        )
        return EXIT_UNVERIFIABLE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
