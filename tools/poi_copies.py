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
    python3 tools/poi_copies.py --image US.img --text "HANA HEALTH" --inner
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
    got = inflate_with_len(data, off)
    return None if got is None else got[0]


def inflate_with_len(data: bytes, off: int) -> tuple[bytes, int] | None:
    """``(inner, consumed)`` of the complete zlib stream at ``off``, or None."""
    try:
        return cmpind_codec.decompress_stream_at(data, off, window=INNER_LIMIT)
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


def scan_bytes(data: bytes, path: Path, text, inner: bool = False,
               stats: dict | None = None) -> list[dict]:
    """Search ``data`` and (``inner``) every complete zlib stream inside it.

    A candidate header that starts inside a stream already inflated is not
    tried again (its bytes are compressed data, not a second stream); this is
    what makes the multi-GB tile scan finish (M5.27).
    """
    texts = [text] if isinstance(text, str) else list(text)
    needles = needles_for(texts)
    hits = search_multi(data, needles, path, None)
    if inner:
        covered = 0
        for m in ZLIB_HEADER.finditer(data):
            if m.start() < covered:
                continue
            got = inflate_with_len(data, m.start())
            if got is None:
                continue
            out, consumed = got
            covered = m.start() + consumed
            if stats is not None:
                stats["streams"] = stats.get("streams", 0) + 1
                stats["inflated"] = stats.get("inflated", 0) + len(out)
            hits.extend(search_multi(out, needles, path, m.start()))
    return hits


def scan_file(path: Path, text, inner: bool = False, stats: dict | None = None) -> list[dict]:
    data = path.read_bytes()
    if stats is not None:
        stats["bytes"] = stats.get("bytes", 0) + len(data)
    return scan_bytes(data, path, text, inner, stats)


def scan_image(image: Path, text, inner: bool = False, skip_suffix=(".cmp", ".ind"),
               stats: dict | None = None) -> tuple[list[dict], int]:
    """Scan every file of the card image's map partition, read through FAT.

    Files whose name ends with one of ``skip_suffix`` are left out (the
    ``.cmp``/``.ind`` pairs are scanned decoded, with ``cmpind.py extract``).
    """
    import mkcard
    hits: list[dict] = []
    n = 0
    with image.open("rb") as h:
        _, geo, fat = mkcard.open_map_partition(h)
        todo = [""]
        while todo:
            d = todo.pop(0)
            for e in sorted(mkcard.img_list_dir(h, geo, fat, d), key=lambda e: e.name):
                if e.name in (".", ".."):
                    continue
                rel = f"{d}/{e.name}".strip("/")
                if getattr(e, "is_dir", False):
                    todo.append(rel)
                    continue
                if e.name.lower().endswith(tuple(x.lower() for x in skip_suffix)):
                    continue
                n += 1
                if stats is not None:
                    stats["bytes"] = stats.get("bytes", 0) + e.size
                data = mkcard.img_read(h, geo, fat, rel)
                hits.extend(scan_bytes(data, Path(rel), text, inner, stats))
    return hits, n


def scan_tree(root: Path, text, inner: bool = False,
              stats: dict | None = None) -> tuple[list[dict], int]:
    files = sorted(p for p in root.rglob("*") if p.is_file())
    hits: list[dict] = []
    for path in files:
        hits.extend(scan_file(path, text, inner, stats))
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
        # two streams back to back: both are inflated; a header-like byte pair
        # inside the first stream is not tried as a third
        second = zlib.compress(b"..HANA HEALTH CLINIC", 9)
        blob = b"\0" * 3 + inner_pay + second
        st: dict = {}
        both = scan_bytes(blob, Path("f.DAT"), "HANA HEALTH", inner=True, stats=st)
        check("back-to-back streams both inflated",
              sorted(h.get("inner_zlib_at") for h in both if "inner_zlib_at" in h)
              == [3, 3 + len(inner_pay)] and st.get("streams") == 2)
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
    ap.add_argument("--image", type=Path,
                    help="scan the files of this SD image (FAT) instead of a TREE")
    ap.add_argument("--skip-suffix", action="append", default=None,
                    help="with --image: leave out names ending so (default .cmp, .ind)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if (args.tree is None) == (args.image is None) or not args.text:
        ap.error("TREE or --image, and --text, are required (or --selftest)")
    stats: dict = {}
    if args.image is not None:
        skip = tuple(args.skip_suffix) if args.skip_suffix else (".cmp", ".ind")
        hits, n = scan_image(args.image, args.text, inner=args.inner,
                             skip_suffix=skip, stats=stats)
    else:
        hits, n = scan_tree(args.tree, args.text, inner=args.inner, stats=stats)
    for h in hits:
        where = f" inner@0x{h['inner_zlib_at']:x}" if "inner_zlib_at" in h else ""
        print(f"{h['text']!r}  {h['file']}  {h['encoding']}  0x{h['offset']:x}{where}  next={h['following'][:32]}")
    print(f"files scanned: {n}  hits: {len(hits)}  bytes: {stats.get('bytes', 0)}  "
          f"zlib streams inflated: {stats.get('streams', 0)} "
          f"({stats.get('inflated', 0)} B)")
    if args.json:
        args.json.write_text(json.dumps(hits, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
