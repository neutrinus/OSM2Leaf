#!/usr/bin/env python3
"""Check KIWI specification chapter tokens against a PDF's own text.

The KIWI-W chapter PDFs (see ``docs/research/kiwi-sources.md``) tag their
headings with the chapter numbers that ``jharg/kiwiread`` quotes, e.g.
``1.2.13 Parcel ID`` or ``6.1.2 Block Set Management Record``.  This tool
extracts the visible text from a PDF's FlateDecode content streams (stdlib
``zlib`` only), normalises it, and reports whether a token such as ``6.1.2``
co-occurs with a title such as ``Block Set Management Record`` within a small
window.

It reads only the local PDF you pass; it never fetches anything.  The way to
obtain the PDFs (Wayback Machine, ``if_`` flag) and their SHA-256 are in the
M4.65 EXP record.

Usage::

    python3 tools/kiwi_spec_tokens.py PDF [TOKEN=TITLE ...]

    # what the M4.65 EXP runs against the four archived chapter PDFs:
    python3 tools/kiwi_spec_tokens.py pdf/0600122e.pdf \\
        "6.1.1=Level Management Record" \\
        "6.1.2=Block Set Management Record" \\
        "6.2.1=Block Management Record"

With no TOKEN=TITLE argument the tool prints the token count and exits 0 when
the PDF has any extractable text (a quick "is this a real PDF" check).

Exit codes: ``0`` every requested token/title was found, ``1`` at least one
missing, ``2`` usage/IO error.
"""

from __future__ import annotations

import argparse
import re
import sys
import zlib
from pathlib import Path

WINDOW = 80  # characters after the token to look for the title in

# The chapter tags ``jharg/kiwiread`` uses, paired with the title each one
# stands for.  Used by ``--selftest`` and as documentation of what "match"
# means; callers may pass any subset of them on the command line.
KIWIREAD_TAGS = [
    ("1.2.7", "Sector Address Type"),
    ("1.2.13", "Parcel ID Number Type"),
    ("1.2.14", "Manufacturer Identification Type"),
    ("5.1", "Data Volume"),
    ("5.1.1", "Level Management Information"),
    ("6.1", "Parcel Data Management Distribution Header"),
    ("6.1.1", "Level Management Record"),
    ("6.1.2", "Block Set Management Record"),
    ("6.2.1", "Block Management Record"),
    ("7.2", "Road Data Frame"),
    ("7.3", "Background Data Frame"),
    ("7.4", "Name Data Frame"),
    ("10.1", "Route Planning Distribution Header"),
    ("10.6", "Node Data Frame"),
    ("10.7", "Link Data Frame"),
    ("10.10", "Link Cost Data Frame"),
    ("10.12", "Node Coordinate Data Frame"),
]


def extract_text(path: Path) -> str:
    """Return the visible text of a PDF's FlateDecode streams.

    This is not a full PDF parser: it decompresses each stream it can and
    joins the string literals used by text-showing operators.  That is enough
    for the KIWI chapter PDFs (PDF 1.2, one FlateDecode stream per page) and is
    deliberately dependency-free.
    """
    data = path.read_bytes()
    pieces: list[str] = []
    i = 0
    while True:
        j = data.find(b"stream", i)
        if j < 0:
            break
        k = j + len(b"stream")
        if data[k:k + 2] == b"\r\n":
            k += 2
        elif data[k:k + 1] in (b"\r", b"\n"):
            k += 1
        e = data.find(b"endstream", k)
        if e < 0:
            break
        try:
            raw = zlib.decompress(data[k:e])
        except zlib.error:
            i = j + len(b"stream")
            continue
        literals = re.findall(rb"\((?:[^()\\]|\\.)*\)", raw)
        text = b" ".join(lit[1:-1] for lit in literals).decode("latin-1")
        pieces.append(text)
        i = e + len(b"endstream")
    full = " ".join(pieces)
    # PDF line breaks split words; collapse them and normalise whitespace.
    full = re.sub(r"[ \t]*\r?\n[ \t]*", " ", full)
    full = re.sub(r"\s+", " ", full)
    # Some producers print "6 . 2 . 1" for "6.2.1"; join dotted numbers.
    full = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", full)
    return full


def find_snippet(text: str, token: str) -> tuple[bool, str]:
    """Return (token_present, the ~70 chars of heading text after it).

    The token must stand alone: ``6.1`` matches "6.1 Parcel..." but not
    "6.1.2 ...".  PDF line breaks and hyphen-less splits ("Di stribution")
    are left as-is; callers choose title fragments that survive them.
    """
    pat = re.compile(r"(?<!\d)" + re.escape(token) + r"(?!\d|\.\d)")
    m = pat.search(text)
    if not m:
        return False, ""
    snippet = re.sub(r"\s+", " ", text[m.end():m.end() + 70]).strip()
    return True, snippet


def title_present(snippet: str, title: str) -> bool:
    """True when ``title`` appears in the snippet ignoring whitespace.

    PDF text extraction splits words at arbitrary points ("Block S et",
    "Di stribution"), so both sides are compared with all whitespace removed.
    """
    return re.sub(r"\s+", "", title) in re.sub(r"\s+", "", snippet)


def check(text: str, token: str, title: str) -> bool:
    """True when ``token`` heads a line whose snippet contains ``title``."""
    present, snippet = find_snippet(text, token)
    return present and title_present(snippet, title)


def selftest() -> int:
    """Synthetic PDF-like bytes only; no vendor data, no network."""
    failures = 0

    def expect(cond: bool, label: str) -> None:
        nonlocal failures
        if not cond:
            failures += 1
        print(f"  {label:<48} {'OK' if cond else 'FAIL'}")

    # Build a tiny fake PDF: one FlateDecode stream with a heading.
    body = b"BT (6.1.2 Block Set Management Record) Tj ET"
    comp = zlib.compress(body)
    fake = b"%PDF-1.2\n5 0 obj\n<< /Filter /FlateDecode >>\nstream\n" + comp + \
           b"\nendstream\nendobj\n%%EOF\n"

    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "fake.pdf"
        p.write_bytes(fake)
        text = extract_text(p)
        expect("Block Set Management Record" in text, "extracts a heading")
        expect(check(text, "6.1.2", "Block Set Management Record"),
               "token+title found (positive)")
        # Negative: the title is not near a different token.
        expect(not check(text, "6.1.1", "Block Set Management Record"),
               "wrong token not matched (negative)")
        # Boundary: "6.1" must not be satisfied by the "6.1.2" heading.
        present, _ = find_snippet(text, "6.1")
        expect(not present, "6.1 does not stand alone in '6.1.2' (negative)")
        # Negative: a title that is absent must fail even when the token is present.
        expect(not check(text, "6.1.2", "Node Data Frame"),
               "present token, absent title fails (negative)")
        # Spaced dotted number normalises to the plain form.
        body2 = zlib.compress(b"BT (6 . 2 . 1 Block Management Record) Tj ET")
        fake2 = b"%PDF-1.2\nstream\n" + body2 + b"\nendstream\n%%EOF\n"
        p2 = Path(td) / "fake2.pdf"
        p2.write_bytes(fake2)
        expect(check(extract_text(p2), "6.2.1", "Block Management Record"),
               "spaced '6 . 2 . 1' normalises (positive)")

    print(f"kiwi_spec_tokens selftest: {'OK' if not failures else 'FAILED'} "
          f"({6 - failures}/6)")
    return 0 if not failures else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Check KIWI chapter tokens/titles in a local PDF.")
    ap.add_argument("pdf", nargs="?", help="local KIWI chapter PDF")
    ap.add_argument("checks", nargs="*", metavar="TOKEN=TITLE",
                    help="token and the title it must head, e.g. "
                         "'6.1.2=Block Set Management Record'")
    ap.add_argument("--selftest", action="store_true",
                    help="run synthetic tests and exit")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()
    if not args.pdf:
        ap.print_usage()
        return 2

    path = Path(args.pdf)
    if not path.is_file():
        print(f"kiwi_spec_tokens: no such file: {path}", file=sys.stderr)
        return 2
    text = extract_text(path)
    if not text.strip():
        print(f"kiwi_spec_tokens: no extractable text in {path}", file=sys.stderr)
        return 2

    if not args.checks:
        found = len(re.findall(r"(?<!\d)\d\.\d", text))
        print(f"{path}: {found} dotted tokens, {len(text)} chars of text")
        return 0

    missing = 0
    for item in args.checks:
        if "=" not in item:
            print(f"kiwi_spec_tokens: bad check {item!r} (need TOKEN=TITLE)",
                  file=sys.stderr)
            return 2
        token, title = item.split("=", 1)
        token, title = token.strip(), title.strip()
        present, snippet = find_snippet(text, token)
        ok = present and title_present(snippet, title)
        missing += 0 if ok else 1
        shown = snippet if present else "(token not found)"
        print(f"  {token:<8} {'OK' if ok else 'MISSING':<7} | {shown}")
    return 0 if missing == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
