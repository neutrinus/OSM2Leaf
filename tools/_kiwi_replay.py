#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private source/REPLAY helper for the four KIWI probe tools (M4.94).

Not a tool: the leading underscore keeps ``tools/selftest.py`` from discovering
this module.  It only resolves ``--tree``/``--card`` + ``--tile`` to a real
file path and pins the REPLAY line to the SHA-256 quoted by the source EXP.

``--card`` reads one file's cluster chain with ``cardcheck.Fat32Image.read``;
it deliberately does NOT run ``verify.py --image``'s 7z extraction of the whole
~7.5 GB card.  This is a mechanism deviation, not a weakened replay: the bytes
are the same FAT32 file and the REPLAY SHA must still equal the EXP SHA.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

SCRATCH = Path.home() / "projekty" / "leafre-work" / "scratch" / "M4.94"

# SHA-256 quoted by EXP-2026-11-22-M4.67/68/69/70/72.  These are identity
# pins: a REPLAY line whose SHA differs is a hard failure, never a "pass".
EXP_SHA = {
    "MMAIN001": "240e7c9774197fff0ea85276d463658d1291f4147970ccd5fdec60ffd23e9a05",
    "B48R058R": "e9c9cb2236f6b53ad4fe9687a18a351afe80a46a63c0a1f18dc46d6c8af3ff52",
    "B48R0C0R": "d86f754b3dfbefd1f475b9d05e7c6bb91d7a4fa7dc2af5f8d1d263159f1cf746",
    "B30R048R": "0916101547246d6c6ed240aeb4724b4cd6e826c97a6b782e2b649fbe09a5eb28",
    "B30R060R": "8ca92bd5601e33bd97ab3bbab62b4394448cbe0e2adf31ba6046eebb52b8b62d",
    "B28R070R": "0e4df38b659e99129c1e55f1ad16219d73e713677edd4ee3756b8ce7e74b2ddb",
}


class SourceError(RuntimeError):
    """A named, loud failure to resolve a --tree/--card source."""


def norm_tile(name: str) -> str:
    return name[:-4] if name.upper().endswith(".DAT") else name


def rel_path(name: str) -> str:
    n = norm_tile(name)
    return "MMAIN001.DAT" if n.upper().startswith("MMAIN") else f"MAPAL001/{n}.DAT"


def add_source_args(ap) -> None:
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--tree", metavar="ROOT", help="extracted factory tree root")
    group.add_argument(
        "--card", metavar="IMG",
        help="raw FAT32 SD image; read one file's cluster chain (no 7z extraction)",
    )
    ap.add_argument("--tile", metavar="NAME", help="tile name, e.g. B48R058R or MMAIN001")


class Source:
    def __init__(self, path: Path, display: str, sha: str, expected: str):
        self.path = Path(path)
        self.display = display
        self.sha = sha
        self.expected = expected

    def close(self) -> None:
        pass


def resolve(args):
    """Return a Source for --tree/--card, or None for the ordinary CLI."""
    if not args.tree and not args.card:
        return None
    if not args.tile:
        raise SourceError("--tree/--card needs --tile NAME")
    name = norm_tile(args.tile)
    if name not in EXP_SHA:
        raise SourceError(f"--tile {args.tile}: no EXP SHA-256 pinned for this tile")
    rel = rel_path(name)
    expected = EXP_SHA[name]

    if args.tree:
        path = Path(args.tree).expanduser() / rel
        if not path.is_file():
            raise SourceError(f"--tree {args.tree}: missing {rel}")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        # Do not fail here on SHA: the mutant negative control must reach the
        # REPLAY line, which prints the differing SHA and exits non-zero.
        return Source(path, str(path), sha, expected)

    import cardcheck  # imported lazily: selftest and ordinary CLI need no image

    card = Path(args.card).expanduser()
    if not card.is_file():
        raise SourceError(f"--card {card}: image not found")
    try:
        image = cardcheck.Fat32Image(card)
    except (OSError, ValueError) as exc:
        raise SourceError(f"--card {card}: cannot open FAT32 image: {exc}") from exc
    try:
        try:
            data = image.read(rel)
        except (OSError, ValueError) as exc:
            raise SourceError(f"--card {card}: cannot read {rel}: {exc}") from exc
        if not data:
            raise SourceError(f"--card {card}: {rel} reads 0 bytes")
        sha = hashlib.sha256(data).hexdigest()
        if sha != expected:
            raise SourceError(
                f"--card {card}: {rel} sha256 {sha} != EXP SHA-256 {expected}"
            )
        out = SCRATCH / "card" / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        return Source(out, f"{card}!{rel}", sha, expected)
    finally:
        image.close()


def replay_line(source: Source, exp_id: str, summary: str) -> int:
    """Print the pinned REPLAY line; return 0 on SHA match, 1 on mismatch."""
    ok = source.sha == source.expected
    print(
        f"REPLAY {exp_id} {summary} sha256 {source.sha} "
        f"{'OK' if ok else 'MISMATCH'}"
    )
    if not ok:
        print(
            f"error: {exp_id} pins sha256 {source.expected}, got {source.sha}",
            file=sys.stderr,
        )
        return 1
    return 0
