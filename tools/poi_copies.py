#!/usr/bin/env python3
"""Find every copy of a name in a card tree, in all three encodings (M5.12c).

A rename that edits one page is only complete if no other file still holds the
old text. This tool scans a tree for the same text in Latin-1, UTF-16LE and
UTF-16BE, and reports file, byte offset and the bytes that follow the match.
It scans decoded ``.cmp`` payloads (decode them first with ``cmpind.py extract``)
and the uncompressed files alike.

Usage
    python3 tools/poi_copies.py TREE --text "HANA HEALTH" --inner
    python3 tools/poi_copies.py TREE --text "WENDY'S" --text "HARDEE'S" --inner
    python3 tools/poi_copies.py TREE --text "HANA HEALTH" --json out.json
    python3 tools/poi_copies.py --selftest

Exit codes: 0 scan done (hits or none), 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cmpind_codec  # noqa: E402

ENCODINGS = ("latin-1", "utf-16-le", "utf-16-be")
CONTEXT = 16
ZLIB_HEADER = cmpind_codec.ZLIB_HEAD
INNER_LIMIT = 8 << 20


def find_all(data: bytes, needle: bytes) -> list[int]:
    out, pos = [], 0
    while True:
        hit = data.find(needle, pos)
        if hit < 0:
            return out
        out.append(hit)
        pos = hit + 1


def search(data: bytes, needle_by_enc: dict, path: Path, inner: int | None) -> list[dict]:
    hits = []
    for enc, needle in needle_by_enc.items():
        for off in find_all(data, needle):
            after = data[off + len(needle): off + len(needle) + CONTEXT]
            hit = {
                "file": path.as_posix(),
                "encoding": enc,
                "offset": off,
                "following": after.hex(),
            }
            if inner is not None:
                hit["inner_zlib_at"] = inner
            hits.append(hit)
    return hits


def inflate_at(data: bytes, off: int) -> bytes | None:
    """Return the complete zlib stream starting at ``off``, or None."""
    try:
        inner, _ = cmpind_codec.decompress_stream_at(data, off, window=INNER_LIMIT)
        return inner
    except cmpind_codec.FormatError:
        return None


def needles_for(texts: list[str]) -> dict:
    """One needle per (text, encoding); the key says which text matched."""
    return {(t, enc): t.encode(enc) for t in texts for enc in ENCODINGS}


def search_multi(data: bytes, needles: dict, path: Path, inner: int | None) -> list[dict]:
    hits = []
    for (text, enc), needle in needles.items():
        for h in search(data, {enc: needle}, path, inner):
            h["text"] = text
            hits.append(h)
    return hits


def scan_file(path: Path, text, inner: bool = False) -> list[dict]:
    texts = [text] if isinstance(text, str) else list(text)
    data = path.read_bytes()
    needles = needles_for(texts)
    hits = search_multi(data, needles, path, None)
    if inner:
        for m in ZLIB_HEADER.finditer(data):
            out = inflate_at(data, m.start())
            if out is not None:
                hits.extend(search_multi(out, needles, path, m.start()))
    return hits


def scan_tree(root: Path, text, inner: bool = False) -> tuple[list[dict], int]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    hits: list[dict] = []
    for path in files:
        hits.extend(scan_file(path, text, inner))
    return hits, len(files)


def selftest() -> int:
    failures = 0

    def check(name: str, ok: bool) -> None:
        nonlocal failures
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
        if not ok:
            failures += 1

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.DAT").write_bytes(b"xx" + "HANA HEALTH".encode("latin-1") + b"!")
        (root / "b.DAT").write_bytes("HANA HEALTH".encode("utf-16-le") + b"\0\0")
        (root / "c.DAT").write_bytes("HANA HEALTH".encode("utf-16-be"))
        (root / "d.DAT").write_bytes(b"nothing here")
        hits, n = scan_tree(root, "HANA HEALTH")
        check("four files scanned", n == 4)
        check("latin-1 hit in a.DAT at offset 2",
              any(h["file"].endswith("a.DAT") and h["encoding"] == "latin-1"
                  and h["offset"] == 2 for h in hits))
        check("utf-16-le hit in b.DAT", any(h["file"].endswith("b.DAT")
                                            and h["encoding"] == "utf-16-le" for h in hits))
        check("utf-16-be hit in c.DAT", any(h["file"].endswith("c.DAT")
                                            and h["encoding"] == "utf-16-be" for h in hits))
        check("no hit in d.DAT", not any(h["file"].endswith("d.DAT") for h in hits))
        check("following bytes start with the '!' of a.DAT",
              any(h["file"].endswith("a.DAT") and h["following"].startswith("21")
                  for h in hits))
        empty, _ = scan_tree(root, "NOT PRESENT ANYWHERE")
        check("absent text gives zero hits", empty == [])
        two, _ = scan_tree(root, ["HANA HEALTH", "NOT PRESENT"])
        check("several names: hits carry the text they matched",
              {h["text"] for h in two} == {"HANA HEALTH"})
        inner_pay = zlib.compress("xxHANA HEALTH CENTER".encode("latin-1"), 6)
        (root / "e.DAT").write_bytes(b"\0" * 7 + inner_pay + b"\0" * 5)
        flat, _ = scan_tree(root, "HANA HEALTH")
        deep, _ = scan_tree(root, "HANA HEALTH", inner=True)
        check("name inside a zlib stream is missed without --inner",
              not any(h["file"].endswith("e.DAT") for h in flat))
        check("name inside a zlib stream found with --inner at offset 7",
              any(h["file"].endswith("e.DAT") and h.get("inner_zlib_at") == 7
                  for h in deep))
    print(f"selftest: {'OK' if failures == 0 else f'{failures} failed'}")
    return 0 if failures == 0 else 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("tree", nargs="?", type=Path)
    ap.add_argument("--text", action="append", default=[],
                    help="text to look for (repeat for several names; each is "
                         "searched in Latin-1, UTF-16LE and UTF-16BE)")
    ap.add_argument("--json", type=Path, help="write hits as JSON")
    ap.add_argument("--inner", action="store_true",
                    help="also inflate zlib streams inside each file (pages of .DAT)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.tree is None or not args.text:
        ap.error("TREE and --text are required (or --selftest)")
    hits, n = scan_tree(args.tree, args.text, inner=args.inner)
    for h in hits:
        where = f" inner@0x{h['inner_zlib_at']:x}" if "inner_zlib_at" in h else ""
        print(f"{h['text']!r}  {h['file']}  {h['encoding']}  0x{h['offset']:x}{where}  next={h['following'][:32]}")
    print(f"files scanned: {n}  hits: {len(hits)}")
    if args.json:
        args.json.write_text(json.dumps(hits, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
