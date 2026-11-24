#!/usr/bin/env python3
"""L3 rung of the verification ladder: run every declared L3 target.

``l3check.py`` is the L3 counterpart of ``cardcheck.py`` (L1) and
``l2check.py`` (L2).  It takes a corpus built by
``tools/l3_harness/corpus.py`` (or one supplied with ``--corpus``), asks
``tools/l3_harness/runner.py`` to run every target declared in
``tools/l3_harness/targets.json``, and reports one status per target:

============  ==============================================================
``PASS``      the engine's verdict matched the target's expectation
``FAIL``      a mismatch, an invalid input, or a target that could not run
``SKIP``      the requested back end is absent; nothing is claimed
``BLOCKED``   the reader has no located entry point; nothing is claimed
============  ==============================================================

Exit codes: ``0`` every runnable target passed (blocked/skipped targets are
counted, not failed), ``1`` a target failed or the corpus/inputs were invalid,
``2`` usage error, ``3`` nothing was runnable (every target blocked or
skipped; no verdict is claimed).

The tool never fakes a pass.  A reader that is not located is ``BLOCKED`` no
matter how good the corpus is, an absent back end is ``SKIP``, a missing
corpus file is a ``FAIL``, and a synthetic PASS proves only that the
runner/dispatcher path works -- not that the firmware accepts a card.  Every
row carries its reader ID and the claim IDs its evidence rests on.

Card gate (M9.12): ``--card OUT.img --factory IMG`` finds files that differ
from the factory image and reports every relevant L3 target as ``pass`` /
``fail`` / ``not-yet-available``.  It exits non-zero on any fail.  Targets
whose reader is not runnable are reported honestly as ``not-yet-available``
(e.g. the POI reader / M9.10); the gate never synthesizes a pass.

The header names the *card* build (from its firmware prefix).  A verdict row
names the *firmware/VA* build that actually ran: the M9.11 chunk decoder uses
the EU2011 head and fn 0x0041c7dc even when the card under test is US2011, so
that row is EU2011 and the card build stays in the header (H51, M9.31).  A row
where no firmware ran has no build attribution at all.

Baseline gate (M9.31): ``--card IMG --factory IMG --baseline`` handles the
no-diff case (S0/S1 are byte-identical to the factory).  Instead of a bare
``NO_DIFFS`` it runs the registered runnable baselines on the factory's own
files: M9.11 ``cmp_ind_reader`` on a REFER001 ``.cmp/.ind`` pair and M9.6
``applaunch_mapcode_compare`` on ``HDD_INFO.TXT``.  Each row names the build
whose firmware/VA it uses; an EU function is never reported on a US-card
baseline.  A row counts as ``pass`` only when the runner returned status
``PASS`` *and* real firmware data (``r0``/``insns``): ``DRY_RUN`` (exit 0),
``SKIP``, ``BLOCKED`` and a missing input are ``not-yet-available``.  Result
``PASS``/exit 0 needs at least one real pass; no runnable baseline gives
``NO_RUNNABLE_BASELINE_TARGETS``/exit 3, never a fake pass.

Card gate, first slice (M9.60): ``--card IMG --factory IMG [--position LAT,LON]``
runs the firmware's own mount and file sweep and makes the exit code the
verdict -- three rows, each printed ``PASS`` / ``FAIL`` / ``NOT RUN``:

==============  ===========================================================
``boot``        the firmware mounts the card and logs no error call
``sweep``       every file in the firmware's volume table reads back
                byte-identical through the firmware
``mount``       at every position no tile read has a negative status and the
                firmware's error-log count equals the factory run's
==============  ===========================================================

The sweep is skipped on a card that differs from the factory in any
``REFER001`` pair or ``DRSTR001.DAT`` (a changed file would fail against its
own host-side decode); it is run and reported ``SAME`` only when the card
claims to be a no-op -- when the card and factory directory tables are
identical -- and is otherwise ``NOT RUN (diff)`` and does not by itself fail
or pass the gate.
EU2011 build only: a card whose head bytes are the US or the 2014/2016 EU
build is ``NOT RUN (build)``, never ``PASS``.  Without a card image the rows
are ``NOT RUN`` and the exit is ``3``.  Exit codes: ``0`` three rows PASS,
``1`` a row FAILs (the read is named), ``3`` nothing runnable (missing card,
wrong build, or a row that did not run), ``2`` usage error.

Usage::

    python3 tools/l3check.py --build-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --target probe-zlib-cmf
    python3 tools/l3check.py --card LEAF_EU.img --factory LEAF_EU.img --position 51.70,17.45
    python3 tools/l3check.py --card us_S2.img --factory LEAF_US.img
    python3 tools/l3check.py --card LEAF_EU.img --factory LEAF_EU.img --baseline \\
        --baseline-dir /home/marek/projekty/leafre-work/scratch/m9.31/eu --json
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --json
    python3 tools/l3check.py --corpus /tmp/opencode/l3-corpus --json out.json
    python3 tools/l3check.py --selftest
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from l3_harness import corpus as corpus_mod  # noqa: E402
from l3_harness import engine as engine_mod  # noqa: E402
from l3_harness import manifest as manifest_mod  # noqa: E402
from l3_harness import runner as runner_mod  # noqa: E402
from l3_harness import runs as runs_mod  # noqa: E402

SCHEMA = "osm2leaf.l3check/v1"

#: Reservation from TODO M9.8 (C-1700-C-1709); this tool uses C-1700.
TOOL_CLAIM = "C-1700"
EXP_RECORD = "EXP-2026-11-06-M9.8-l3check"
#: Reservation from TODO M9.12 (C-2160-C-2169); card gate uses C-2160.
CARD_CLAIM = "C-2160"
CARD_EXP = "EXP-2026-11-08-M9.12-l3check-card"

#: The firmware/VA build the card-mode chunk-decoder adapter executes.
#: ``chunk_decoder_l3.py`` defaults to ``--build eu2011`` and ``_find_img256()``
#: is the EU2011 head; targets.json declares the same build for
#: ``cmp_ind_reader``.  A verdict row names THIS build, never the card's
#: (H51/M9.31): the S2 card is US2011 but its PASS row ran EU2011 firmware.
CARD_FIRMWARE_BUILD = "eu2011"

#: M9.31 baseline/no-diff gate.  Reservation C-3320-C-3329.
BASELINE_CLAIM = "C-3320"
BASELINE_EXP = "EXP-2026-11-23-M9.31-baseline-no-diff-verdicts"

#: The only targets allowed to declare a *safe* baseline corpus.  Both use
#: EU2011 VAs that are already in the frozen fn_audit corpora (base:689/730,
#: overlay:1418-1422); no new VA is cited.  ``build`` is declared per row so an
#: EU function is never reported as a verdict on a US-card baseline (M9.31).
BASELINE_TARGETS = (
    {
        "name": "cmp_ind_reader",
        "build": "eu2011",
        "reader": "cmp_ind",
        "label": ".cmp/.ind chunk decoder (M9.11, EU2011 fn 0x0041c7dc)",
        "inputs": ("cmp", "ind"),
    },
    {
        "name": "applaunch_mapcode_compare",
        "build": "eu2011",
        "reader": "hdd_info",
        "label": "map-code compare (M9.6, EU2011 build B fn 0x03bd2ad8)",
        "inputs": ("hddinfo",),
    },
)

#: M9.60 card gate, first slice: the firmware's own mount and file sweep as
#: three rows whose exit code is the verdict.  Reservation C-6720-C-6729.
CARD_GATE_CLAIM = "C-6720"
CARD_GATE_EXP = "EXP-2026-11-21-M9.60-card-gate-first-slice"

#: Row words of the M9.60 gate (the task says ``PASS``/``FAIL``/``NOT RUN``).
ROW_PASS, ROW_FAIL, ROW_NOT_RUN = "PASS", "FAIL", "NOT RUN"

#: The build the three rows run: EU2011 ``Navi.exe`` (build A).  The card's
#: first 96 MiB are the firmware (the map partition starts at 100 MiB and the
#: `HDD_INFO` copy at ``0x06000000``): that prefix, not the whole 256 MiB head,
#: names the build, because a card edit inside the map partition changes the
#: rest of the head.  A US or a 2014/2016 EU card is ``NOT RUN (build)``,
#: never ``PASS``.
CARD_GATE_BUILD = "eu2011"
CARD_GATE_FIRMWARE_BYTES = 0x06000000
#: SHA-256 of the first 96 MiB (the firmware region) of each build's head.
CARD_GATE_FIRMWARE_SHA256 = {
    "eu2011": "5b07f40e51ddad14aa82f9f66b956de5d32b74aa660219439c1e0802d7ee687d",
    "us2011": "f2eb2c8f70329ca9d6853a32e530878964cd1a30dad475a398a7b5a57e4cfc77",
}

#: One row per target in ``targets.json``: the reader under test and the claim
#: IDs its evidence rests on.  C-1670 is the runner, C-1690 the corpus (both
#: pipeline evidence); a blocked row names the claims that describe its
#: blocker, and C-520/C-528 mark the retired map-code comparator.  The table is
#: validated against ``targets.json`` on every run: a target added or renamed
#: there makes this tool FAIL instead of silently dropping it.
TARGET_EVIDENCE = {
    "probe-zlib-cmf": {
        "reader": "synthetic",
        "claims": ("C-1670", "C-1690"),
        "note": "runner and corpus claim; the probe is a pipeline fixture",
    },
    "hddinfo_compare": {
        "reader": "hdd_info",
        "claims": ("C-521",),
        "note": "HDD_INFO literals are located; the parser is behind a COM object",
    },
    "cmp_ind_reader": {
        "reader": "cmp_ind",
        "claims": (),
        "note": "no .cmp/.ind reader entry point yet",
    },
    "cmp_ind_reader_us2011": {
        "reader": "cmp_ind",
        "claims": ("C-3630",),
        "note": "US build of the same engine (fn 0x00444540); M1.22",
    },
    "point_walk_us2011": {
        "reader": "point_walk",
        "claims": ("C-5770", "C-5771", "C-5772"),
        "note": "US POINT walker fn 0x0041db44; runner point_walk_v1 (M9.55); framing only, not names (C-4178)",
    },
    "poi_record_decode": {
        "reader": "point_name",
        "claims": ("C-2140", "C-2141", "C-2142"),
        "note": "US POINT name accessor fn 0x0041ec8c; runner point_name_v1 (M9.10); names, not the .cmp layer",
    },
    "tile_reader": {
        "reader": "tile",
        "claims": (),
        "note": "no tile reader entry point yet",
    },
    "lev3456_reader": {
        "reader": "tile",
        "claims": ("C-2440", "C-2441", "C-2443", "C-2446"),
        "note": "LEV3456R directories at mount via datask_l3.py + mount_dirs_l3.py (M9.18); records: M9.53",
    },
    "tile_section4_reader": {
        "reader": "tile",
        "claims": ("C-2441", "C-2442", "C-2444", "C-2446"),
        "note": "tile section-4 directory at mount, parser 0x00415330 (M9.18); name list: M9.53",
    },
    "mmain_reader": {
        "reader": "tile",
        "claims": ("C-5970", "C-5971", "C-5972"),
        "note": "MMAIN001 reader inside the firmware mount via tools/mmain_l3.py (M9.17)",
    },
    "drstr_parser": {
        "reader": "drstr",
        "claims": ("C-2640", "C-2641", "C-2642"),
        "note": "Navi.exe fn 0x00419350 (EU2011) via tools/drstr_l3.py; needs --image/--input (M9.24)",
    },
    "mapcode_comparator": {
        "reader": "hdd_info",
        "claims": ("C-520", "C-528"),
        "note": "retired BT_MGR.dll chain; kept blocked on purpose",
    },
    "applaunch_mapcode_compare": {
        "reader": "hdd_info",
        "claims": ("C-5140", "C-5141", "C-5146"),
        "note": "AppLaunch.dll fn 0x03bd2ad8 (EU2011 build B), check 1; unit +0x60 declared; M9.6",
    },
}

STATUSES = ("PASS", "FAIL", "SKIP", "BLOCKED")

#: ``runner.py`` status -> ladder status.  A missing entry means the runner
#: returned something this tool does not understand, which is a FAIL.
_RUNNER_STATUS = {
    "PASS": "PASS",
    "SKIP": "SKIP",
    "BLOCKED": "BLOCKED",
    "MISMATCH": "FAIL",
    "INVALID": "FAIL",
}

_CLAIM_RE = re.compile(r"^C-\d+$")


class UsageError(ValueError):
    """The command line cannot be turned into a run."""


# --------------------------------------------------------------------------
# Corpus
# --------------------------------------------------------------------------


def _temp_corpus_root() -> Path:
    return Path(tempfile.mkdtemp(prefix="l3check-corpus-"))


def _resolve_corpus(args) -> tuple[dict, dict | None]:
    """Build or validate the corpus; never invent one that was not asked for."""

    if getattr(args, "corpus", None) and getattr(args, "build_corpus", False):
        raise UsageError("pass either --corpus DIR or --build-corpus, not both")

    built = None
    if getattr(args, "corpus", None):
        root = Path(args.corpus).expanduser()
        source = "supplied"
    else:
        root = _temp_corpus_root()
        source = "built"
        try:
            built = corpus_mod.build_corpus(root)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            return (
                {
                    "root": str(root),
                    "manifest": str(root / "manifest.json"),
                    "source": source,
                    "entries": 0,
                    "problems": [f"corpus build failed: {exc}"],
                    "kept": True,
                },
                None,
            )

    manifest_path = root / "manifest.json"
    info = {
        "root": str(root),
        "manifest": str(manifest_path),
        "source": source,
        "entries": 0,
        "problems": [],
        "kept": source == "built",
    }
    if built is not None:
        info["build"] = {
            "entries": built["entries"],
            "skipped": list(built["skipped"]),
        }

    try:
        doc = manifest_mod.load(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        info["problems"].append(f"cannot read {manifest_path}: {exc}")
        return info, None

    info["entries"] = len(doc.get("corpus", []))
    info["problems"] = manifest_mod.validate(doc, root=root)
    return info, doc


def _card_info(args) -> dict | None:
    """Legacy --root/--image (recorded only). M9.12 uses --card/--factory."""
    if getattr(args, "card", None) or getattr(args, "factory", None):
        return None
    if not (getattr(args, "root", None) or getattr(args, "image", None)):
        return None
    return {
        "status": "NOT_IMPLEMENTED",
        "checked": False,
        "task": "M9.12",
        "root": getattr(args, "root", None),
        "image": getattr(args, "image", None),
        "note": (
            "card-level L3 uses --card/--factory (M9.12); these paths are "
            "recorded, not checked, and are not evidence"
        ),
    }


# --------------------------------------------------------------------------
# Card gate (M9.12): diff card vs factory, run available targets per diff
# --------------------------------------------------------------------------


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _7z_listing(image: Path) -> dict[str, int]:
    """Return {path: size} for regular files in a FAT image via 7z l -slt."""
    proc = subprocess.run(
        ["7z", "l", "-slt", str(image)],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if proc.returncode not in (0, 1):  # 1 = warnings
        raise UsageError(f"7z l failed for {image}: {proc.stderr.strip()[:200]}")
    files: dict[str, int] = {}
    current: str | None = None
    is_folder = False
    size: int | None = None
    for line in proc.stdout.splitlines():
        if line.startswith("Path = "):
            if current and not is_folder and size is not None and "/" in current:
                # skip archive/partition pseudo-paths (no slash or special)
                files[current] = size
            current = line[7:]
            is_folder = False
            size = None
        elif line.startswith("Folder = "):
            is_folder = line[9:].strip() == "+"
        elif line.startswith("Size = "):
            try:
                size = int(line[7:].strip())
            except ValueError:
                size = None
    if current and not is_folder and size is not None and "/" in current:
        files[current] = size
    return files


def _7z_extract(image: Path, paths: list[str], dest: Path) -> None:
    if not paths:
        return
    dest.mkdir(parents=True, exist_ok=True)
    cmd = ["7z", "e", "-y", f"-o{dest}", str(image), *paths]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if proc.returncode not in (0, 1):
        raise UsageError(f"7z e failed for {image}: {proc.stderr.strip()[:300]}")


def _files_content_differ(card: Path, factory: Path, paths: list[str],
                          tmp: Path) -> list[str]:
    """Extract *paths* from both images and return those with different bytes."""
    if not paths:
        return []
    card_dir = tmp / "card"
    fact_dir = tmp / "factory"
    _7z_extract(card, paths, card_dir)
    _7z_extract(factory, paths, fact_dir)
    differ: list[str] = []
    for rel in paths:
        name = Path(rel).name
        a = card_dir / name
        b = fact_dir / name
        if not a.exists() or not b.exists():
            differ.append(rel)
            continue
        if a.read_bytes() != b.read_bytes():
            differ.append(rel)
    return differ


#: Card-relevant patterns: files that may have an L3 target mapping.
_CARD_RELEVANT_PREFIXES = (
    "VER_INFO/HDD_INFO.TXT",
    "DRSTR001.DAT",
    "REFER001/",
    "MAPAL001/",
)


def _is_card_relevant(path: str) -> bool:
    p = path.replace("\\", "/")
    return any(p == pre or p.startswith(pre) for pre in _CARD_RELEVANT_PREFIXES)


def diff_card_files(card: Path, factory: Path) -> dict:
    """Find card-relevant files that differ between two images.

    Returns a report dict with ``differing`` (sorted paths), ``method``,
    ``identical_images`` and any ``problems``.  Uses 7z listings (size) plus
    content comparison for REFER001/*.ind and size-matched relevant files, so
    same-size content changes are caught for the small/critical set.
    """
    result = {
        "card": str(card),
        "factory": str(factory),
        "method": "7z listing size+content compare (REFER001/ind and size-matched relevant files)",
        "identical_images": False,
        "differing": [],
        "problems": [],
        "card_files": 0,
        "factory_files": 0,
    }
    if not card.exists():
        result["problems"].append(f"card image not found: {card}")
        return result
    if not factory.exists():
        result["problems"].append(f"factory image not found: {factory}")
        return result

    # Fast path: identical files.
    if card.resolve() == factory.resolve() or (
            card.stat().st_size == factory.stat().st_size
            and card.stat().st_size < 512 * 1024 * 1024
            and card.read_bytes() == factory.read_bytes()):
        result["identical_images"] = True
        return result
    # For large identical images, SHA-256 comparison is expensive but correct;
    # S1==factory is a real case. We compare by streaming hash only when sizes
    # match and the caller didn't short-circuit above.
    if card.stat().st_size == factory.stat().st_size:
        try:
            if _sha256_file(card) == _sha256_file(factory):
                result["identical_images"] = True
                result["method"] = "streaming SHA-256 (identical)"
                return result
        except OSError as exc:
            result["problems"].append(f"hash compare failed: {exc}")
            return result

    try:
        card_list = _7z_listing(card)
        fact_list = _7z_listing(factory)
    except (UsageError, FileNotFoundError) as exc:
        result["problems"].append(str(exc))
        return result
    result["card_files"] = len(card_list)
    result["factory_files"] = len(fact_list)

    differing: set[str] = set()
    to_check: list[str] = []
    all_paths = set(card_list) | set(fact_list)
    for rel in sorted(all_paths):
        p = rel.replace("\\", "/")
        if not _is_card_relevant(p):
            continue
        cs, fs = card_list.get(rel), fact_list.get(rel)
        if cs is None or fs is None:
            differing.add(p)
        elif cs != fs:
            differing.add(p)
        elif p.upper().endswith(".IND") or p in (
                "VER_INFO/HDD_INFO.TXT", "DRSTR001.DAT"):
            # Same size but content may differ (.ind is 612 B, critical files).
            to_check.append(rel)

    if to_check:
        with tempfile.TemporaryDirectory(prefix="l3check-diff-") as tmp:
            try:
                differing.update(p.replace("\\", "/") for p in
                                 _files_content_differ(card, factory, to_check,
                                                       Path(tmp)))
            except (UsageError, OSError) as exc:
                result["problems"].append(f"content compare: {exc}")

    result["differing"] = sorted(differing)
    return result


# Card target mapping: (path predicate) -> (target name, adapter, note).
# ``adapter``: "targets.json" = run via runner; "chunk_decoder" = M9.11
# firmware path via chunk_decoder_l3.py (cmp_ind_reader not registered, M9.11b);
# "not-yet-available" = report honestly (M9.10 POI reader).
_CARD_TARGETS = [
    {
        "name": "hddinfo_compare",
        "label": "map-code/HDD_INFO compare (M9.6)",
        "applies": lambda p: p.upper() == "VER_INFO/HDD_INFO.TXT",
        "adapter": "targets.json",
        "unavailable_note": "hddinfo_compare is blocked in targets.json (no entry VA; M2.1-M2.3). The M9.6 runnable map-code target is applaunch_mapcode_compare (fn 0x03bd2ad8, EU2011 build B) and is registered; this row is not it.",
    },
    {
        "name": "cmp_ind_reader",
        "label": ".cmp/.ind chunk decoder (M9.11)",
        "applies": lambda p: p.upper().startswith("REFER001/") and p.upper().endswith((".CMP", ".IND")),
        "adapter": "chunk_decoder",
        "unavailable_note": "cmp_ind_reader blocked in targets.json (M9.11b); chunk_decoder_l3.py adapter used when .cmp/.ind pair available",
    },
    {
        "name": "poi_record_decode",
        "label": "POI record reader (M9.10)",
        "applies": lambda p: p.upper().startswith("REFER001/POINT") and p.upper().endswith(".DAT.CMP"),
        "adapter": "not-yet-available",
        "unavailable_note": "POI reader not yet available in --card mode: the target exists since M9.10 (runner.py run poi_record_decode --image US256 --cmp PAIR.cmp --ind PAIR.ind --expect-name NAME) but this gate does not yet find the changed page of a POINT pair (M9.12)",
    },
    {
        "name": "drstr_parser",
        "label": "DRSTR001 parser (M9.14)",
        "applies": lambda p: p.upper() == "DRSTR001.DAT",
        "adapter": "targets.json",
        "unavailable_note": "drstr_parser is a firmware_call (M9.24): run it with runner.py run drstr_parser --image IMG --input DRSTR001.DAT",
    },
    {
        "name": "tile_reader",
        "label": "tile reader (M9.13)",
        "applies": lambda p: p.upper().startswith("MAPAL001/") and p.upper().endswith(".DAT"),
        "adapter": "targets.json",
        "unavailable_note": "tile_reader blocked (M9.13; runner/module entry constraints)",
    },
]


def _norm_cmp_pair(path: str) -> tuple[str, str] | None:
    """For a .cmp or .ind path return (cmp, ind) base names in REFER001, else None."""
    p = path.replace("\\", "/")
    up = p.upper()
    if not up.startswith("REFER001/"):
        return None
    if up.endswith(".DAT.CMP"):
        return p, p[:-4] + ".ind"
    if up.endswith(".DAT.IND"):
        return p[:-4] + ".cmp", p
    return None


def _chunk_decoder_cmd() -> list[str]:
    return [sys.executable, str(TOOLS_DIR / "chunk_decoder_l3.py")]


def _run_chunk_decoder(card: Path, factory: Path, cmp_rel: str, ind_rel: str,
                       tmp: Path) -> dict:
    """Run M9.11 firmware path on the card's differing .cmp pair vs reference."""
    work = tmp / "chunk"
    _7z_extract(card, [cmp_rel, ind_rel], work / "card")
    _7z_extract(factory, [cmp_rel, ind_rel], work / "factory")
    # chunk_decoder_l3.py needs Navi.exe from IMG256 head (archive) by default
    # or via --image; find it.
    img256 = _find_img256()
    if img256 is None:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "IMG256 (Navi.exe head) not found for chunk decoder; rule 11",
                "l3_claim": False}
    # Run against the card's pair as --cmp/--ind, reference is cmpind.decode of
    # the same pair (chunk_decoder compares to reference). For a correct S2 edit,
    # the firmware should decode the card pair byte-identically to cmpind.decode
    # of that pair.
    cmp_path = work / "card" / Path(cmp_rel).name
    ind_path = work / "card" / Path(ind_rel).name
    cmd = _chunk_decoder_cmd() + [
        "run", str(img256),
        "--cmp", str(cmp_path), "--ind", str(ind_path),
        "--sec1", "zero-mask",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                          timeout=600)
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode == 0 and "verdict: PASS" in out:
        return {"status": "pass", "verdict": "PASS", "detail": out.strip()[-400:],
                "l3_claim": False,
                "note": "M9.11 firmware path via chunk_decoder_l3.py (not targets.json; M9.11b registers cmp_ind_reader)"}
    if proc.returncode == 1 or "FAIL" in out:
        return {"status": "fail", "verdict": "FAIL", "detail": out.strip()[-400:],
                "l3_claim": False}
    if proc.returncode == 4 or "BLOCKED" in out:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "BLOCKED: " + out.strip()[-300:], "l3_claim": False}
    if proc.returncode == 3:
        return {"status": "not-yet-available", "verdict": None,
                "detail": "missing input: " + out.strip()[:200], "l3_claim": False}
    return {"status": "not-yet-available", "verdict": None,
            "detail": f"exit {proc.returncode}: " + out.strip()[:300],
            "l3_claim": False}


def _find_img256() -> Path | None:
    candidates = [
        TOOLS_DIR.parent / "archive" / "head256.img",
        Path(os.environ.get("IMG256", "")),
        Path("/home/marek/projekty/OSM2Leaf/archive/head256.img"),
        Path("/home/marek/projekty/leafre-work/leaf2011.img"),
    ]
    for p in candidates:
        if p and str(p) and p.is_file():
            return p
    return None


def _find_us256() -> Path | None:
    candidates = [
        TOOLS_DIR.parent / "archive" / "us256.img",
        Path(os.environ.get("US256", "")),
        Path("/home/marek/projekty/OSM2Leaf/archive/us256.img"),
    ]
    for p in candidates:
        if p and str(p) and p.is_file():
            return p
    return None


#: ``build`` -> the head image whose firmware the target's VAs belong to.  A
#: wrong pairing still yields a verdict (``FAIL (unmapped ...)``, M9.42), so a
#: missing image is never silently swapped for the other build's.
BUILD_IMAGES = {
    "eu2011": _find_img256,
    "us2011": _find_us256,
}


def _card_status_norm(status: str) -> str:
    """M9.12 terminology: pass / fail / not-yet-available."""
    if status in ("pass", "PASS"):
        return "pass"
    if status in ("fail", "FAIL", "MISMATCH", "INVALID"):
        return "fail"
    return "not-yet-available"


def _card_firmware_build(name: str) -> str | None:
    """Firmware/VA build a card-mode verdict row executed, or None.

    Only a row that actually ran firmware gets a build: the chunk decoder is
    EU2011 (see CARD_FIRMWARE_BUILD).  A ``not-yet-available`` row ran nothing
    and is not attributed to a build.  This is deliberately NOT the card's
    build from ``_card_head_build()`` (H51/M9.31).
    """
    return CARD_FIRMWARE_BUILD if name == "cmp_ind_reader" else None


def build_card_report(card: Path, factory: Path, *, by_name: dict,
                      engine: str = "pysh4") -> dict:
    """M9.12 card gate: diff, then per-target pass/fail/not-yet-available."""
    diff = diff_card_files(card, factory)
    # Header: the build of the card under test.  Verdict rows below name the
    # firmware/VA build that ran instead -- they are not the same thing.
    card_build = _card_head_build(card) if card.is_file() else None
    rows: list[dict] = []
    problems = list(diff.get("problems") or [])

    differing = diff.get("differing") or []
    if diff.get("identical_images"):
        differing = []
    seen_targets: set[tuple[str, str]] = set()

    # Always report POI reader availability when POINT files differ, and also
    # include it once as not-yet-available if no POINT diffs but M9.12 requires
    # the POI reader to be reported as "not yet available" where applicable.
    # We report per applicable target for differing files.
    with tempfile.TemporaryDirectory(prefix="l3check-card-") as tmp:
        tmpdir = Path(tmp)
        for ct in _CARD_TARGETS:
            applicable = [p for p in differing if ct["applies"](p)]
            if not applicable and ct["name"] != "poi_record_decode":
                continue
            # Report POI reader once, as not-yet-available, when applicable by
            # spec (M9.12 done-when requires reporting it). Also report when
            # POINT files differ.
            if ct["name"] == "poi_record_decode" and not applicable:
                # "where applicable" - report its availability status once.
                rows.append({
                    "name": ct["name"],
                    "label": ct["label"],
                    "status": "not-yet-available",
                    "files": [],
                    "detail": ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue

            if ct["adapter"] == "not-yet-available":
                rows.append({
                    "name": ct["name"],
                    "label": ct["label"],
                    "status": "not-yet-available",
                    "files": applicable,
                    "detail": ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue

            if ct["adapter"] == "chunk_decoder" and ct["name"] == "cmp_ind_reader":
                # Run on each differing .cmp pair (dedup).
                pairs = []
                for p in applicable:
                    pair = _norm_cmp_pair(p)
                    if pair and pair not in pairs:
                        pairs.append(pair)
                for cmp_rel, ind_rel in pairs:
                    res = _run_chunk_decoder(card, factory, cmp_rel, ind_rel,
                                             tmpdir)
                    rows.append({
                        "name": ct["name"],
                        "label": ct["label"],
                        "status": _card_status_norm(res["status"]),
                        "files": [cmp_rel, ind_rel],
                        "detail": res.get("detail", ""),
                        "l3_claim": res.get("l3_claim", False),
                        "note": res.get("note"),
                    })
                if not pairs:
                    rows.append({
                        "name": ct["name"], "label": ct["label"],
                        "status": "not-yet-available", "files": applicable,
                        "detail": "no .cmp/.ind pair resolved from diff",
                        "l3_claim": False,
                    })
                continue

            # targets.json adapter
            target = by_name.get(ct["name"])
            if target is None:
                rows.append({
                    "name": ct["name"], "label": ct["label"],
                    "status": "not-yet-available", "files": applicable,
                    "detail": f"target {ct['name']} not in targets.json",
                    "l3_claim": False,
                })
                continue
            entry_kind = (target.get("entry") or {}).get("kind")
            if entry_kind == "blocked":
                rows.append({
                    "name": ct["name"], "label": ct["label"],
                    "status": "not-yet-available", "files": applicable,
                    "detail": (target.get("entry") or {}).get("reason")
                              or ct["unavailable_note"],
                    "l3_claim": False,
                })
                continue
            # Runnable target - but we need to supply the right input for the
            # differing file. The generic runner uses corpus; card mode would
            # need per-file input wiring. Report honestly if not wired.
            rows.append({
                "name": ct["name"], "label": ct["label"],
                "status": "not-yet-available", "files": applicable,
                "detail": f"target {ct['name']} is runnable but card-mode per-file input wiring not implemented for this target kind",
                "l3_claim": False,
            })

    for row in rows:
        row.setdefault("build", _card_firmware_build(row["name"]))

    counts = {"pass": 0, "fail": 0, "not-yet-available": 0, "total": len(rows)}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    has_fail = counts["fail"] > 0
    runnable = counts["pass"] + counts["fail"]
    if has_fail:
        result_status, exit_code = "FAIL", 1
    elif runnable == 0 and not diff.get("identical_images") and differing:
        # Diffs exist but nothing runnable -> report clearly; not a fake pass.
        result_status, exit_code = "NOT_YET_AVAILABLE", 3
    elif diff.get("identical_images") and runnable == 0:
        # No diffs, nothing to fail on; but also nothing verified.
        result_status, exit_code = "NO_DIFFS", 3
    elif runnable > 0 and counts["fail"] == 0:
        result_status, exit_code = "PASS", 0
    else:
        result_status, exit_code = "NO_DIFFS" if not differing else "NOT_YET_AVAILABLE", 3

    return {
        "schema": SCHEMA,
        "command": "l3check --card",
        "claim": CARD_CLAIM,
        "exp": CARD_EXP,
        "card": str(card),
        "factory": str(factory),
        "card_build": card_build,
        "diff": diff,
        "targets": rows,
        "counts": counts,
        "result": result_status,
        "exit": exit_code,
        "problems": problems,
        "note": (
            "M9.12 card gate: per-target pass/fail/not-yet-available on files "
            "that differ from factory. POI reader reported as not yet available "
            "where applicable (M9.10). A not-yet-available target is not a pass."
        ),
    }


def _print_card_report(report: dict) -> None:
    print(f"l3check --card: software gate before car test (claim {CARD_CLAIM})")
    print(f"exp      {report['exp']}")
    print(f"card     {report['card']}")
    print(f"factory  {report['factory']}")
    print(f"build    {report.get('card_build') or 'unknown (no card image)'} "
          "(card; verdict rows name the firmware build that ran)")
    diff = report.get("diff") or {}
    if diff.get("identical_images"):
        print("diff     identical images (no differing files)")
    else:
        differing = diff.get("differing") or []
        print(f"diff     {len(differing)} differing card-relevant file(s) [{diff.get('method','')}]")
        for p in differing[:30]:
            print(f"         {p}")
        if len(differing) > 30:
            print(f"         ... ({len(differing)-30} more)")
    for problem in report.get("problems", []):
        print(f"PROBLEM  {problem}")
    print()
    if not report["targets"]:
        print("targets  (none applicable)")
    else:
        for row in report["targets"]:
            files = ", ".join(row.get("files") or []) or "-"
            build = row.get("build") or "-"
            print(f"  [{row['status']}] {row['name']} (firmware {build}): {row['label']}")
            print(f"           files: {files}")
            print(f"           {row.get('detail','')}")
            if row.get("note"):
                print(f"           note: {row['note']}")
    counts = report["counts"]
    print()
    print(f"counts   pass={counts.get('pass',0)} fail={counts.get('fail',0)} "
          f"not-yet-available={counts.get('not-yet-available',0)} total={counts['total']}")
    if report["result"] == "PASS":
        print("RESULT: PASS (every runnable target passed)")
    elif report["result"] == "FAIL":
        print(f"RESULT: FAIL ({counts.get('fail',0)} target(s) failed; exit 1)")
    elif report["result"] == "NO_DIFFS":
        print("RESULT: NO_DIFFS (no differing files or nothing runnable; exit 3, not a pass)")
    else:
        print(f"RESULT: {report['result']} (exit {report['exit']}; not-yet-available is not a pass)")


# --------------------------------------------------------------------------
# M9.31 baseline gate: explicit verdicts on a no-diff card/factory pair
# --------------------------------------------------------------------------

#: The three small baseline files, either in --baseline-dir (scratch, never the
#: repo) or extracted from the factory image into a temp dir.  Only offsets,
#: sizes and hashes of these files belong in the EXP.
_BASELINE_FILES = {
    "cmp": "POINT010.DAT.cmp",
    "ind": "POINT010.DAT.ind",
    "hddinfo": "HDD_INFO.TXT",
}
_BASELINE_CORPUS_PATHS = {
    "cmp": "REFER001/POINT010.DAT.cmp",
    "ind": "REFER001/POINT010.DAT.ind",
    "hddinfo": "VER_INFO/HDD_INFO.TXT",
}


def _baseline_verdict(spec: dict, payload: dict) -> dict:
    """Map one runner payload to a baseline row, never fabricating a pass.

    A ``pass`` needs status PASS **and** real firmware data (r0/insns).  The
    runner's ``DRY_RUN`` status carries exit 0 but no verdict; SKIP/BLOCKED and
    missing inputs are ``not-yet-available``.  Only MISMATCH/FAIL/INVALID (an
    actual run that rejected the factory baseline) is a ``fail``.
    """
    status = str(payload.get("status") or "").upper()
    fw = payload.get("firmware")
    real_fw = (isinstance(fw, dict) and fw.get("r0") is not None
               and fw.get("insns") is not None)
    verdict = payload.get("verdict")
    detail = "; ".join(str(p) for p in (payload.get("problems") or [])) \
        or str(payload.get("reason") or "")
    if verdict:
        detail = (detail + " | " if detail else "") + str(verdict)
    if real_fw:
        detail += (" | " if detail else "") + "firmware r0=%s insns=%s" \
                  % (fw["r0"], fw["insns"])
    row = {
        "name": spec["name"],
        "label": spec["label"],
        "build": spec["build"],
        "reader": spec["reader"],
        "claims": list(TARGET_EVIDENCE.get(spec["name"], {}).get("claims", ())),
        "verdict": verdict,
        "firmware": fw if real_fw else None,
        "detail": detail,
        "l3_claim": bool(payload.get("l3_claim")),
    }
    if status == "PASS" and real_fw:
        row["status"] = "pass"
    elif status in ("MISMATCH", "FAIL", "INVALID"):
        row["status"] = "fail"
    else:
        row["status"] = "not-yet-available"
    return row


def _baseline_counts(rows: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "not-yet-available": 0, "total": len(rows)}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    return counts


def baseline_result(rows: list[dict]) -> tuple[str, int]:
    """Pure aggregation: a FAIL wins, else one real PASS, else exit 3."""
    counts = _baseline_counts(rows)
    if counts["fail"]:
        return "FAIL", 1
    if counts["pass"]:
        return "PASS", 0
    return "NO_RUNNABLE_BASELINE_TARGETS", 3


def _unavailable_baseline_row(spec: dict, reason: str) -> dict:
    return {
        "name": spec["name"], "label": spec["label"], "build": spec["build"],
        "reader": spec["reader"],
        "claims": list(TARGET_EVIDENCE.get(spec["name"], {}).get("claims", ())),
        "status": "not-yet-available", "verdict": None, "firmware": None,
        "detail": reason, "l3_claim": False,
    }


def _default_baseline_runners() -> dict:
    """The registered firmware_call targets, via runner.py's own dispatcher.

    A runner is only called after the caller has checked build pairing, head
    presence and corpus presence; it never guesses a head or an input.
    """
    def firmware_runner(extra_args):
        def run(spec, files, head):
            by_name, _doc = runner_mod.load_targets()
            target = by_name.get(spec["name"])
            if target is None:
                return {"status": "BLOCKED", "reason": "target not in targets.json"}
            ns = argparse.Namespace(
                engine="pysh4", input=None, corpus=None,
                max_insns=engine_mod.DEFAULT_MAX_INSNS, dry_run=False,
                image=str(head), cmp=None, ind=None, offset=None, length=None,
                mutate="none", expect=None, expect_name=None,
                unit_from=None, unit_code=None,
            )
            for key, value in extra_args(files).items():
                setattr(ns, key, value)
            try:
                return runner_mod.run_target(target, ns)
            except Exception as exc:  # noqa: BLE001 - a crashed runner is no pass
                return {"status": "BLOCKED",
                        "reason": "runner crashed: %s: %s"
                                  % (type(exc).__name__, str(exc)[:200])}
        return run

    return {
        "cmp_ind_reader": firmware_runner(
            lambda files: {"cmp": str(files["cmp"]), "ind": str(files["ind"])}),
        "applaunch_mapcode_compare": firmware_runner(
            lambda files: {"input": str(files["hddinfo"]),
                           "unit_from": str(files["hddinfo"]),
                           "expect": "ACCEPT"}),
    }


def build_baseline_report(card: Path, factory: Path, *, files: dict,
                          heads: dict, runners: dict | None = None,
                          card_build: str | None = None) -> dict:
    """M9.31: real firmware verdicts on a no-diff card/factory pair.

    ``files`` maps ``cmp``/``ind``/``hddinfo`` to Paths; ``heads`` maps a build
    name to its firmware head Path.  ``runners`` is injectable for the
    selftest.  A missing input/head, a build mismatch, an absent runner or a
    DRY_RUN/SKIP row is ``not-yet-available`` with its reason -- never a pass.
    """
    diff = diff_card_files(card, factory)
    build = card_build or _card_head_build(card)
    active_runners = _default_baseline_runners() if runners is None else runners
    rows: list[dict] = []
    for spec in BASELINE_TARGETS:
        if spec["build"] != build:
            rows.append(_unavailable_baseline_row(
                spec, "build mismatch: card/factory is %s, baseline uses %s (%s); "
                      "an EU function is never a verdict on a US-card baseline (M9.31)"
                      % (build, spec["build"], spec["label"])))
            continue
        head = heads.get(spec["build"])
        if head is None or not Path(head).is_file():
            rows.append(_unavailable_baseline_row(
                spec, "no %s firmware head for %s (rule 11)"
                      % (spec["build"], spec["label"])))
            continue
        missing = [key for key in spec["inputs"]
                   if files.get(key) is None or not Path(files[key]).is_file()]
        if missing:
            rows.append(_unavailable_baseline_row(
                spec, "missing baseline input(s): %s" % ", ".join(sorted(missing))))
            continue
        runner = active_runners.get(spec["name"])
        if runner is None:
            rows.append(_unavailable_baseline_row(
                spec, "no runner registered for %s" % spec["name"]))
            continue
        try:
            payload = runner(spec, files, head)
        except Exception as exc:  # noqa: BLE001
            rows.append(_unavailable_baseline_row(
                spec, "runner crashed: %s: %s"
                      % (type(exc).__name__, str(exc)[:200])))
            continue
        rows.append(_baseline_verdict(spec, payload))
    result, exit_code = baseline_result(rows)
    return {
        "schema": SCHEMA,
        "command": "l3check --card --baseline",
        "claim": BASELINE_CLAIM,
        "exp": BASELINE_EXP,
        "card": str(card),
        "factory": str(factory),
        "card_build": build,
        "diff": diff,
        "targets": rows,
        "counts": _baseline_counts(rows),
        "result": result,
        "exit": exit_code,
        "problems": list(diff.get("problems") or []),
        "note": (
            "M9.31 baseline gate: real firmware verdicts on the factory's own "
            "files when the card is byte-identical to it. PASS needs status PASS "
            "and real firmware r0/insns; DRY_RUN/SKIP/BLOCKED are "
            "not-yet-available, never a pass. Build is declared per row."
        ),
    }


def _baseline_corpus_files(factory: Path, baseline_dir: str | None,
                           tmp: Path) -> tuple[dict, list[str]]:
    """Locate the three small baseline files (scratch dir or 7z extraction)."""
    if baseline_dir:
        root = Path(baseline_dir).expanduser()
        files = {key: root / name for key, name in _BASELINE_FILES.items()}
        return files, [str(p) for p in files.values() if not p.is_file()]
    dest = tmp / "baseline"
    try:
        _7z_extract(factory, list(_BASELINE_CORPUS_PATHS.values()), dest)
    except (UsageError, OSError) as exc:
        return {}, ["cannot extract baseline corpus: %s" % exc]
    files = {key: dest / name for key, name in _BASELINE_FILES.items()}
    return files, [str(p) for p in files.values() if not p.is_file()]


def _print_baseline_report(report: dict) -> None:
    print(f"l3check --card --baseline: no-diff firmware verdicts (claim {BASELINE_CLAIM})")
    print(f"exp      {report['exp']}")
    print(f"card     {report['card']}")
    print(f"factory  {report['factory']}")
    print(f"build    {report.get('card_build')} (EU rows only; never mix builds)")
    diff = report.get("diff") or {}
    if diff.get("identical_images"):
        print("diff     identical images (no differing files)")
    else:
        print(f"diff     {len(diff.get('differing') or [])} differing card-relevant file(s)")
    for problem in report.get("problems") or []:
        print(f"PROBLEM  {problem}")
    print()
    for row in report["targets"]:
        print(f"  [{row['status']:>17}] {row['name']} ({row['build']}): {row['label']}")
        print(f"           claims: {', '.join(row['claims']) or '-'}")
        print(f"           {row['detail']}")
    counts = report["counts"]
    print()
    print(f"counts   pass={counts['pass']} fail={counts['fail']} "
          f"not-yet-available={counts['not-yet-available']} total={counts['total']}")
    if report["result"] == "PASS":
        print("RESULT: PASS (at least one real firmware baseline passed; exit 0)")
    elif report["result"] == "FAIL":
        print(f"RESULT: FAIL ({counts['fail']} baseline(s) failed; exit 1)")
    else:
        print("RESULT: NO_RUNNABLE_BASELINE_TARGETS "
              "(no real firmware verdict; exit 3, not a pass)")


# --------------------------------------------------------------------------
# M9.60 card gate, first slice: the firmware's own mount and file sweep
# --------------------------------------------------------------------------


def _vcard_boot(image: Path, card: Path) -> dict:
    """Run ``vcard_l3.py boot`` and return its ``--json`` boot document.

    The document is what the firmware's own mount built; a JSON read failure is
    an error (never a silent pass).  ``returncode`` is kept for the caller to
    cross-check, not used as the verdict by itself.
    """
    import vcard_l3
    report, _session = vcard_l3.boot_report(str(image), vcard_l3.make_card(None, str(card)))
    return report


def _vcard_sweep(image: Path, card: Path) -> dict:
    """Run ``vcard_l3.py sweep`` in-process and return its rows document."""
    import io as _io
    import contextlib as _contextlib
    import vcard_l3
    buffer = _io.StringIO()
    with tempfile.TemporaryDirectory(prefix="l3check-gate-sweep-") as tmp:
        out = Path(tmp) / "sweep.json"
        argv = ["sweep", str(image), "--card-image", str(card), "--json", str(out)]
        with _contextlib.redirect_stdout(buffer):
            rc = vcard_l3.main(argv)
        doc = json.loads(out.read_text()) if out.is_file() else {}
        doc["returncode"] = rc
        doc["log"] = buffer.getvalue().strip().splitlines()[-1:] if buffer.getvalue() else []
    return doc


def _datask_mount(image: Path, card: Path, position) -> tuple[dict, str]:
    """Run the data-access task's mount on *card* and return (summary, end).

    ``summary`` carries ``state``, ``reads``, ``rows`` (with ``status`` per
    read) and ``other`` (the ``ErrorLogMsg`` entries).  A ``Blocked``/engine
    stop is returned as ``{"blocked": "..."}`` so the row can be honest.
    """
    import datask_l3
    import vcard_l3
    try:
        task = datask_l3.DataTask(str(image), vcard_l3.make_card(None, str(card)),
                                  position=position)
        end = task.run(0, False, None, ())
    except (vcard_l3.Blocked, vcard_l3.EngineError) as exc:
        return {"blocked": "%s: %s" % (type(exc).__name__, str(exc)[:300])}, ""
    summary = task.summary()
    summary["other"] = list(task.other)
    summary["rows"] = list(task.rows)
    summary["end"] = end
    return summary, end


def _error_log_args(summary: dict) -> list:
    """The ``ErrorLogMsg`` argument tuples the firmware logged in a mount."""
    return [tuple(o.get("args") or []) for o in summary.get("other") or []
            if o.get("kind") == "ErrorLogMsg"]


def _negative_reads(summary: dict) -> list[dict]:
    """Every row whose read status is negative (the firmware refused the read)."""
    return [{"file": r.get("file"), "pos": r.get("pos"), "length": r.get("length"),
             "status": r.get("status")} for r in summary.get("rows") or []
            if r.get("status") not in (0, None)]


def _tile_reads(summary: dict) -> int:
    return len([r for r in summary.get("rows") or []
                if str(r.get("file", "")).upper().startswith("MAPAL001/")])


def _head_prefix_sha256(path: Path, length: int = CARD_GATE_FIRMWARE_BYTES) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        remaining = length
        while remaining:
            block = fh.read(min(1 << 20, remaining))
            if not block:
                break
            h.update(block)
            remaining -= len(block)
    return h.hexdigest()


def _card_head_build(card: Path) -> str:
    """The build whose firmware the card's first 96 MiB carry.

    ``eu2011`` when that prefix's SHA-256 equals the EU2011 firmware prefix's,
    ``us2011`` for the US prefix, else ``unknown (<sha12>…)``.  The prefix is
    fixed data below the map partition (``100 MiB``), so a card edit inside the
    map cannot move it, and no 256 MiB head image is needed to name the build.
    """
    digest = _head_prefix_sha256(card)
    for name, want in CARD_GATE_FIRMWARE_SHA256.items():
        if digest == want:
            return name
    return "unknown (%s…)" % digest[:12]


def _verdict_boot(report: dict) -> dict:
    """The ``boot`` row from a ``vcard_l3.boot_report`` document (pure)."""
    verdict = report.get("verdict")
    errors = len(report.get("fwlog") or [])
    row = {"row": "boot", "verdict": verdict,
           "dirs": report.get("dirs"), "files": report.get("files"),
           "tree_sha256": report.get("tree_sha256"), "error_log_calls": errors}
    if verdict == "ACCEPT" and errors == 0:
        row.update(status=ROW_PASS,
                   detail="mount ACCEPT; %d directories, %d files; %d error-log call(s)"
                          % (report.get("dirs", 0), report.get("files", 0), errors))
    elif verdict == "ACCEPT":
        row.update(status=ROW_FAIL,
                   detail="mount ACCEPT but %d error-log call(s): %s"
                          % (errors, report.get("fwlog")))
    else:
        row.update(status=ROW_FAIL,
                   detail="mount %s (%s); %d error-log call(s)"
                          % (verdict, report.get("blocked") or "no verdict", errors))
    return row


def _verdict_sweep(doc: dict) -> dict:
    """The ``sweep`` row from a ``vcard_l3`` sweep document (pure)."""
    rows = doc.get("rows") or []
    bad = [r for r in rows if r.get("status") != "OK"]
    row = {"row": "sweep", "files": len(rows), "not_ok": len(bad)}
    if doc.get("blocked"):
        row.update(status=ROW_FAIL, detail="BLOCKED at " + str(doc["blocked"]))
    elif doc.get("returncode") == 3:
        row.update(status=ROW_NOT_RUN, detail="NOT RUN (no run): the card did not mount")
    elif bad:
        first = bad[0]
        row.update(status=ROW_FAIL,
                   detail="%d/%d file(s) not OK; first: %s %s"
                          % (len(bad), len(rows), first.get("path"), first.get("status")))
    elif rows:
        row.update(status=ROW_PASS,
                   detail="%d/%d file(s) OK; %d bytes compared through the firmware"
                          % (len(rows), len(rows),
                             sum(int(r.get("checked") or 0) for r in rows)))
    else:
        row.update(status=ROW_NOT_RUN, detail="NOT RUN (no files read)")
    return row


def _verdict_mount(card_run: dict, factory_run: dict | None, end: str = "",
                   position=None) -> dict:
    """The ``mount`` row from two data-access mount summaries (pure).

    A negative read status or more error-log calls than the factory run fails
    the row and names the read; an identical run is ``SAME`` (a PASS).  A run
    that parsed no tile read is ``NOT RUN`` (nothing was mounted), never PASS.
    """
    row = {"row": "mount", "position": position}
    if "blocked" in card_run:
        row.update(status=ROW_FAIL, detail="BLOCKED: " + card_run["blocked"])
        return row
    if factory_run is None:
        row.update(status=ROW_NOT_RUN, detail="NOT RUN (no factory control)")
        return row
    if "blocked" in factory_run:
        row.update(status=ROW_NOT_RUN,
                   detail="NOT RUN (no factory control): " + factory_run["blocked"])
        return row
    neg = _negative_reads(card_run)
    card_errors = _error_log_args(card_run)
    base_errors = _error_log_args(factory_run)
    row.update(reads=card_run.get("reads"), factory_reads=factory_run.get("reads"),
               state=card_run.get("state"), end=end,
               error_log_calls=len(card_errors),
               factory_error_log_calls=len(base_errors),
               tile_reads=_tile_reads(card_run))
    if not row["tile_reads"]:
        row.update(status=ROW_NOT_RUN, detail="NOT RUN (no tile read parsed)")
        return row
    if neg:
        first = neg[0]
        row.update(status=ROW_FAIL,
                   detail="read with negative status: %s pos %#x len %#x status %d"
                          % (first["file"], first["pos"] or 0, first["length"] or 0,
                             first["status"]),
                   negative_reads=neg)
        return row
    if len(card_errors) > len(base_errors):
        row.update(status=ROW_FAIL,
                   detail="%d error-log call(s) vs %d on the factory card"
                          % (len(card_errors), len(base_errors)))
        return row
    if (card_run.get("state"), card_run.get("mesh_count"), card_run.get("reads")) != \
            (factory_run.get("state"), factory_run.get("mesh_count"), factory_run.get("reads")):
        row.update(status=ROW_FAIL,
                   detail="run differs from factory: state %s/%s reads %s/%s"
                          % (card_run.get("state"), factory_run.get("state"),
                             card_run.get("reads"), factory_run.get("reads")))
        return row
    row.update(status=ROW_PASS,
               detail="SAME as factory: %s read(s), %d tile read(s), %d error-log call(s), state %s"
                      % (card_run.get("reads"), row["tile_reads"], len(card_errors),
                         card_run.get("state")))
    return row


def _card_row_boot(image: Path, card: Path) -> dict:
    return _verdict_boot(_vcard_boot(image, card))


def _card_row_sweep(image: Path, card: Path) -> dict:
    return _verdict_sweep(_vcard_sweep(image, card))


def _card_row_mount(image: Path, card: Path, factory_card: Path, position) -> dict:
    card_run, end = _datask_mount(image, card, position)
    if "blocked" in card_run:
        return _verdict_mount(card_run, None, end, position)
    factory_run, _fend = _datask_mount(image, factory_card, position)
    return _verdict_mount(card_run, factory_run, end, position)


def _gate_verdict(rows: list[dict]) -> dict:
    """PASS/FAIL/NOT RUN + exit from the three row statuses (pure).

    ``PASS`` only when every row passed; a FAIL row wins over a not-run row;
    anything not run is ``NOT RUN`` and exit 3 -- never a pass.
    """
    statuses = [r["status"] for r in rows]
    fails = [r for r in rows if r["status"] == ROW_FAIL]
    not_runs = [r for r in rows if r["status"] == ROW_NOT_RUN]
    counts = {"pass": statuses.count(ROW_PASS), "fail": len(fails),
              "not_run": len(not_runs), "total": len(rows)}
    out = {"counts": counts}
    if fails:
        out.update(result="FAIL", exit=1,
                   failed_reads=[r["detail"] for r in fails])
    elif not_runs:
        out.update(result="NOT RUN", exit=3)
    else:
        out.update(result="PASS", exit=0)
    return out


def _safe_row(name: str, func, *args) -> dict:
    """Run a row builder; an unexpected stop is a FAIL naming it, not a crash."""
    try:
        return func(*args)
    except Exception as exc:  # noqa: BLE001 - a crashed row is a failed row
        return {"row": name, "status": ROW_FAIL,
                "detail": "row crashed: %s: %s" % (type(exc).__name__, str(exc)[:240])}


def build_card_gate_report(card: Path | None, factory: Path | None, *,
                           positions: list[tuple[float, float]],
                           image: Path | None = None) -> dict:
    """M9.60: run ``boot`` / ``sweep`` / ``mount`` and make the exit the verdict."""
    report = {
        "schema": SCHEMA,
        "command": "l3check --card-gate",
        "claim": CARD_GATE_CLAIM,
        "exp": CARD_GATE_EXP,
        "build": CARD_GATE_BUILD,
        "card": str(card) if card else None,
        "factory": str(factory) if factory else None,
        "positions": [list(p) for p in positions],
        "rows": [],
        "result": None,
        "exit": None,
        "problems": [],
    }

    def not_run(reason: str, *, problems=()) -> dict:
        report["problems"] = list(problems)
        report["rows"] = [
            {"row": name, "status": ROW_NOT_RUN, "detail": "NOT RUN (%s)" % reason}
            for name in ("boot", "sweep", "mount")
        ]
        report["result"] = "NOT RUN"
        report["exit"] = 3
        return report

    if card is None or not card.is_file():
        return not_run("no card image", problems=["card image not found: %s" % card])
    if factory is None or not factory.is_file():
        return not_run("no factory image", problems=["factory image not found: %s" % factory])
    if image is None or not image.is_file():
        return not_run("no firmware head image",
                       problems=["firmware head image not found: %s" % image])

    found_build = _card_head_build(card)
    report["card_build"] = found_build
    if found_build != CARD_GATE_BUILD:
        return not_run("build: card is %s, the gate runs %s"
                       % (found_build, CARD_GATE_BUILD))

    factory_build = _card_head_build(factory)
    if factory_build != CARD_GATE_BUILD:
        return not_run("build: factory is %s, the gate runs %s"
                       % (factory_build, CARD_GATE_BUILD))

    rows = [_safe_row("boot", _card_row_boot, image, card),
            _safe_row("sweep", _card_row_sweep, image, card)]
    for position in positions:
        rows.append(_safe_row("mount", _card_row_mount, image, card, factory, position))
    report["rows"] = rows
    report.update(_gate_verdict(rows))
    return report


def _print_card_gate_report(report: dict) -> None:
    print(f"l3check --card-gate: the firmware's own mount and file sweep (claim {CARD_GATE_CLAIM})")
    print(f"exp      {report['exp']}")
    print(f"card     {report['card']}")
    print(f"factory  {report['factory']}")
    print(f"build    {report.get('card_build', '?')} (gate runs {report['build']})")
    for problem in report.get("problems") or []:
        print(f"PROBLEM  {problem}")
    print()
    for row in report["rows"]:
        name = row["row"]
        if name == "mount":
            pos = row.get("position")
            name = "mount %s" % ("%.3f,%.3f" % pos if pos else "default")
        print(f"  [{row['status']:>7}] {name}: {row.get('detail', '')}")
    counts = report.get("counts") or {}
    print()
    print(f"counts   pass={counts.get('pass', 0)} fail={counts.get('fail', 0)} "
          f"not-run={counts.get('not_run', 0)} total={counts.get('total', 0)}")
    result = report["result"]
    if result == "PASS":
        print("RESULT: PASS (all gate rows passed; exit 0)")
    elif result == "FAIL":
        print(f"RESULT: FAIL ({counts.get('fail', 0)} row(s) failed; exit 1)")
    else:
        print(f"RESULT: NOT RUN ({report.get('problems') or 'a gate row did not run'}; exit 3)")


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


def _evidence_problems(by_name: dict[str, dict]) -> list[str]:
    """Return every drift between ``TARGET_EVIDENCE`` and ``targets.json``."""

    problems: list[str] = []
    declared = set(by_name)
    known = set(TARGET_EVIDENCE)
    for name in sorted(declared - known):
        problems.append(
            f"target {name!r} has no reader/claim row in TARGET_EVIDENCE"
        )
    for name in sorted(known - declared):
        problems.append(
            f"TARGET_EVIDENCE lists {name!r}, which targets.json does not declare"
        )
    for name in sorted(declared & known):
        row = TARGET_EVIDENCE[name]
        target = by_name[name]
        if row["reader"] != target["reader"]:
            problems.append(
                f"{name}: evidence reader {row['reader']!r} != target reader "
                f"{target['reader']!r}"
            )
        for claim in row["claims"]:
            if not _CLAIM_RE.match(claim):
                problems.append(f"{name}: {claim!r} is not a claim ID")
    return problems


def _select_targets(by_name: dict[str, dict], requested) -> list[dict]:
    if not requested:
        return list(by_name.values())
    unknown = [name for name in requested if name not in by_name]
    if unknown:
        raise UsageError(
            f"unknown target(s) {', '.join(repr(n) for n in unknown)}; known: "
            f"{', '.join(sorted(by_name))}"
        )
    selected: list[str] = []
    for name in requested:
        if name not in selected:
            selected.append(name)
    return [by_name[name] for name in selected]

def _corpus_firmware_inputs(target: dict, corpus_root: Path) -> dict:
    """Corpus-mode ``--image/--cmp/--ind`` for a ``point_walk_v1`` row (M9.55).

    The image comes from the target's ``build`` (``BUILD_IMAGES``), the pair
    from ``entry.inputs.source`` under the corpus root.  A build with no head
    image is reported by the caller as BLOCKED (nothing claimed), never
    swapped for the other build's image.
    """
    entry = target.get("entry") or {}
    if entry.get("program") not in ("point_walk_v1", "point_name_v1"):
        return {}
    source = (entry.get("inputs") or {}).get("source")
    if not isinstance(source, str) or not source:
        return {}
    build = target.get("build") or "eu2011"
    finder = BUILD_IMAGES.get(build)
    image = finder() if finder else None
    cmp_path = corpus_root / source
    ind_path = cmp_path.with_suffix(".ind")
    inputs = {
        "corpus_source": str(cmp_path),
        "image_missing": image is None,
    }
    if image is not None:
        inputs["image"] = str(image)
    # M9.10: the synthetic corpus page declares record 0's name; a card run
    # passes its own --expect-name to runner.py instead.
    corpus_name = (entry.get("inputs") or {}).get("corpus_name")
    if entry.get("program") == "point_name_v1" and isinstance(corpus_name, str):
        inputs["expect_name"] = corpus_name
    if cmp_path.is_file():
        inputs["cmp"] = str(cmp_path)
    if ind_path.is_file():
        inputs["ind"] = str(ind_path)
    return inputs



def _run_one(target: dict, corpus_root: Path, engine: str) -> dict:
    """Run one target through ``runner.run_target``; never raise at the caller."""

    evidence = TARGET_EVIDENCE[target["name"]]
    firmware_inputs = _corpus_firmware_inputs(target, corpus_root)
    namespace = argparse.Namespace(
        engine=engine,
        input=None,
        corpus=str(corpus_root),
        max_insns=engine_mod.DEFAULT_MAX_INSNS,
        dry_run=False,
        image=firmware_inputs.get("image"),
        cmp=firmware_inputs.get("cmp"),
        ind=firmware_inputs.get("ind"),
        offset=None,
        length=None,
        mutate="none",
        expect=None,
        expect_name=firmware_inputs.get("expect_name"),
    )
    try:
        payload = runner_mod.run_target(target, namespace)
    except Exception as exc:  # noqa: BLE001 - one target must not abort the run
        payload = {
            "status": "INVALID",
            "exit": runner_mod.EXIT_INVALID,
            "problems": [f"runner error: {type(exc).__name__}: {exc}"],
            "reason": None,
            "l3_claim": False,
        }

    if firmware_inputs.get("image_missing"):
        payload = {
            **payload,
            "status": "BLOCKED",
            "exit": runner_mod.EXIT_BLOCKED,
            "problems": [],
            "reason": (
                f"firmware head for build {target.get('build')!r} not found "
                f"({', '.join(sorted(p for p in BUILD_IMAGES if p))} candidates); "
                "rule 11, rerun with the archive head present"
            ),
            "l3_claim": False,
        }

    status = _RUNNER_STATUS.get(payload.get("status"), "FAIL")
    problems = list(payload.get("problems") or [])
    if payload.get("status") not in _RUNNER_STATUS:
        problems.append(f"runner returned unknown status {payload.get('status')!r}")
    # A registered firmware_call target may need external inputs (--image/--cmp/
    # --ind) that corpus-only `l3check run` does not supply; M9.12 --card feeds
    # it via its own adapter. Report as BLOCKED in this mode (not a firmware
    # rejection / FAIL). M9.11b registered cmp_ind_reader as firmware_call.
    entry_kind = (target.get("entry") or {}).get("kind")
    if entry_kind == "firmware_call" and status == "FAIL":
        joined = " ".join(problems + ([payload.get("reason")] if payload.get("reason") else []))
        if "firmware_call needs" in joined or "--image" in joined or "--cmp" in joined:
            status = "BLOCKED"
            problems = []
            payload["reason"] = (
                payload.get("reason")
                or "firmware_call target needs --image/--cmp/--ind (not provided in corpus-only run); use --card or runner.py directly"
            )
    expect = (target.get("expect") or {}).get("verdict")
    input_info = payload.get("input") or None

    return {
        "name": target["name"],
        "reader": target["reader"],
        "entry": (target.get("entry") or {}).get("kind"),
        "claims": list(evidence["claims"]),
        "claim_note": evidence["note"],
        "expected": expect,
        "status": status,
        "verdict": payload.get("verdict"),
        "accepted": payload.get("accepted"),
        "reason": payload.get("reason"),
        "problems": problems,
        "engine": payload.get("engine") or engine,
        "backend": payload.get("backend"),
        "synthetic": payload.get("synthetic"),
        "l3_claim": payload.get("l3_claim", False),
        "steps": payload.get("cycles"),
        "stub_calls": len(payload.get("stub_calls") or []),
        "input": input_info,
        "runner_exit": payload.get("exit"),
    }


def _counts(rows: list[dict]) -> dict:
    counts = {"pass": 0, "fail": 0, "skip": 0, "blocked": 0}
    for row in rows:
        counts[row["status"].lower()] += 1
    counts["runnable"] = counts["pass"] + counts["fail"]
    counts["total"] = len(rows)
    return counts


def _result(counts: dict) -> tuple[str, int]:
    if counts["fail"]:
        return "FAIL", 1
    if counts["runnable"] == 0:
        return "NO_RUNNABLE", 3
    return "PASS", 0


def build_report(args) -> dict:
    """Build the whole report; the CLI and the self-test share this path."""

    try:
        by_name, targets_doc = runner_mod.load_targets(
            getattr(args, "targets", None)
        )
    except runner_mod.TargetError as exc:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": [f"targets.json: {problem}" for problem in exc.problems],
            "note": "no target ran; a broken target table is not a pass",
        }

    problems = _evidence_problems(by_name)
    if problems:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": None,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": problems,
            "note": "the reader/claim table is out of step with targets.json",
        }

    # M9.31 no-diff baseline gate (before the plain M9.12 diff gate)
    if getattr(args, "baseline", False):
        if not (getattr(args, "card", None) and getattr(args, "factory", None)):
            raise UsageError("--baseline needs --card and --factory together")
        with tempfile.TemporaryDirectory(prefix="l3check-baseline-") as tmp:
            files, problems = _baseline_corpus_files(
                Path(args.factory), getattr(args, "baseline_dir", None), Path(tmp))
            report = build_baseline_report(
                Path(args.card), Path(args.factory), files=files,
                heads={"eu2011": _find_img256(), "us2011": _find_us256()})
            report["problems"].extend(problems)
            return report

    # M9.12 card gate mode
    if getattr(args, "card", None) or getattr(args, "factory", None):
        if not (getattr(args, "card", None) and getattr(args, "factory", None)):
            raise UsageError("--card and --factory must be passed together")
        return build_card_report(Path(args.card), Path(args.factory),
                                 by_name=by_name,
                                 engine=getattr(args, "engine", "pysh4"))

    corpus_info, corpus_doc = _resolve_corpus(args)
    if corpus_info["problems"]:
        return {
            "schema": SCHEMA,
            "command": "l3check",
            "claim": TOOL_CLAIM,
            "exp": EXP_RECORD,
            "engine": getattr(args, "engine", "pysh4"),
            "corpus": corpus_info,
            "card": _card_info(args),
            "targets": [],
            "counts": {"pass": 0, "fail": 0, "skip": 0, "blocked": 0,
                       "runnable": 0, "total": 0},
            "result": "FAIL",
            "exit": 1,
            "problems": list(corpus_info["problems"]),
            "note": "the corpus is invalid, so no target was run",
        }

    selected = _select_targets(by_name, getattr(args, "target", None) or [])
    engine = getattr(args, "engine", "pysh4")
    root = Path(corpus_info["root"])
    rows = [_run_one(target, root, engine) for target in selected]
    counts = _counts(rows)
    result, exit_code = _result(counts)
    gen_rows, gen_problems = generated_rows(
        {row["name"]: by_name[row["name"]] for row in rows},
        _parse_generated(getattr(args, "generated", None)))
    if gen_problems:
        result, exit_code = "FAIL", 1

    return {
        "schema": SCHEMA,
        "command": "l3check",
        "claim": TOOL_CLAIM,
        "exp": EXP_RECORD,
        "engine": engine,
        "corpus": corpus_info,
        "card": _card_info(args),
        "targets": rows,
        "counts": counts,
        "result": result,
        "exit": exit_code,
        "problems": list(gen_problems),
        "generated_corpus": gen_rows,
        "target_count": len(targets_doc.get("targets", [])),
        "note": (
            "a PASS on a synthetic target proves the runner/dispatcher path, "
            "not that the firmware accepts a card; BLOCKED and SKIP claim "
            "nothing and are counted, not failed"
        ),
    }


# --------------------------------------------------------------------------
# Generated corpus (H106): which of *our* files a target ran on
# --------------------------------------------------------------------------

#: Status words of a ``generated_corpus`` row.  None of them is a target
#: result: the rows are listed next to the targets and never change
#: ``counts`` (H107: two names for one reader would read as progress).
GEN_RAN = "RAN (recorded)"   # printed as "RAN (recorded: <verdict>)"
GEN_STALE = "STALE (file differs from the recorded run)"
GEN_NOT_RUN_TREE = "NOT RUN (no tree)"
GEN_NOT_RUNNABLE = "NOT RUNNABLE in runner.py (run it with the 'run' command)"
GEN_BAD_FILE = "NOT RUN (file is not the listed tile)"

GEN_KEYS = {"id", "what", "generator", "path", "size", "sha256", "run",
            "recorded", "ran_on_our_generated_data"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _parse_generated(specs) -> dict[str, Path]:
    out = {}
    for spec in specs or []:
        ident, sep, path = spec.partition("=")
        if not sep or not ident or not path:
            raise UsageError(f"--generated wants ID=PATH, got {spec!r}")
        out[ident] = Path(path).expanduser()
    return out


def generated_rows(by_name: dict, files: dict[str, Path] | None = None) -> tuple[list, list]:
    """One row per ``generated_corpus`` entry; ``(rows, problems)``.

    A row is ``RAN`` only when a run is recorded **for the listed SHA-256**
    (the run's own log names the file it served, ``datask_l3.py mount
    --json`` ``card.overlay``); with ``--generated ID=PATH`` the local file
    is hashed and a mismatch is ``STALE`` (recorded) or ``NOT RUN`` (no
    record).  Without a file and without a record the row is ``NOT RUN (no
    tree)``.  Nothing here runs the firmware.
    """
    files = dict(files or {})
    rows, problems, seen = [], [], set()
    for name, target in by_name.items():
        for i, entry in enumerate(target.get("generated_corpus") or []):
            where = f"{name}.generated_corpus[{i}]"
            if not isinstance(entry, dict):
                problems.append(f"{where}: not an object")
                continue
            unknown = sorted(set(entry) - GEN_KEYS)
            if unknown:
                problems.append(f"{where}: unknown key(s) {unknown}")
            ident = entry.get("id")
            sha = entry.get("sha256")
            if not isinstance(ident, str) or not ident:
                problems.append(f"{where}: missing id")
                continue
            if not (isinstance(sha, str) and len(sha) == 64):
                problems.append(f"{where}: sha256 must be 64 hex digits")
            recorded = entry.get("recorded")
            if recorded is not None and recorded.get("sha256") != sha:
                problems.append(f"{where}: recorded run is for another file")
            if bool(entry.get("ran_on_our_generated_data")) != (recorded is not None):
                problems.append(f"{where}: ran_on_our_generated_data disagrees with recorded")
            seen.add(ident)
            local = files.get(ident)
            local_sha = None
            if local is not None:
                if not local.is_file():
                    problems.append(f"--generated {ident}: no such file {local}")
                    local = None
                else:
                    local_sha = _sha256_file(local)
            if recorded is not None and local_sha not in (None, sha):
                status = GEN_STALE
                reason = (f"recorded {recorded.get('verdict')} applies to {sha[:16]}..., "
                          f"not this file ({local} has {local_sha[:16]}...); re-run: "
                          + (entry.get("run") or "-"))
                problems.append(f"{where} ({ident}): {status}: {reason}")
            elif recorded is not None:
                status = f"{GEN_RAN[:-1]}: {recorded.get('verdict')})"
                reason = f"{recorded.get('verdict')}: {recorded.get('detail')} ({recorded.get('exp')})"
            elif local_sha is None:
                status = GEN_NOT_RUN_TREE
                reason = "no run recorded and no file given (--generated ID=PATH); generator: " \
                    + (entry.get("generator") or "not committed")
            elif local_sha != sha:
                status = GEN_BAD_FILE
                reason = f"{local} has sha256 {local_sha[:16]}..., listed {sha[:16]}..."
                problems.append(f"{where} ({ident}): {status}: {reason}")
            else:
                status = GEN_NOT_RUNNABLE
                reason = "no run recorded; " + (entry.get("run") or "-")
            rows.append({
                "target": name,
                "id": ident,
                "status": status,
                "reason": reason,
                "sha256": sha,
                "size": entry.get("size"),
                "file": str(local) if local is not None else None,
                "file_sha256": local_sha,
                "ran_on_our_generated_data": status.startswith(GEN_RAN[:-1]),
                "recorded_verdict": None if recorded is None else recorded.get("verdict"),
                "recorded": recorded,
            })
    for ident in sorted(set(files) - seen):
        problems.append(f"--generated {ident}: no generated_corpus entry has this id")
    return rows, problems


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def _detail(row: dict) -> str:
    if row["status"] == "PASS":
        text = f"{row['verdict']} (expected {row['expected']})"
        extra = []
        if row["steps"] is not None:
            extra.append(f"{row['steps']} steps")
        if row["engine"]:
            extra.append(row["engine"])
        if row["input"] and row["input"].get("path"):
            extra.append(row["input"]["path"])
        return text + (", " + ", ".join(extra) if extra else "")
    if row["status"] in ("SKIP", "BLOCKED"):
        return row["reason"] or "-"
    return "; ".join(row["problems"]) or row["reason"] or "no detail"


def _print_report(report: dict) -> None:
    print(f"l3check: L3 rung of the verification ladder (claim {TOOL_CLAIM})")
    print(f"exp      {EXP_RECORD}")
    if report["corpus"] is None:
        print("corpus   -")
    else:
        corpus = report["corpus"]
        print(
            f"corpus   {corpus['root']} ({corpus['source']}"
            f"; {corpus['entries']} entries"
            + (", kept" if corpus.get("kept") else "")
            + ")"
        )
    if report["card"]:
        print("card     not checked (--root/--image recorded; card mode is M9.12)")
    print(f"engine   {report['engine']}")

    for problem in report.get("problems", []):
        print(f"FAIL {problem}")
    if not report["targets"]:
        print(f"RESULT: {report['result']} (no target ran; exit {report['exit']})")
        return

    header = ("target", "reader", "entry", "claims", "RESULT")
    rows = [
        (
            row["name"],
            row["reader"],
            row["entry"] or "-",
            ",".join(row["claims"]) or "-",
            row["status"],
        )
        for row in report["targets"]
    ]
    widths = [len(item) for item in header]
    for row in rows:
        widths = [max(width, len(cell)) for width, cell in zip(widths, row)]
    print()
    print("  ".join(cell.ljust(width) for cell, width in zip(header, widths)))
    for row in rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))

    details = [
        (row["name"], row["status"], _detail(row))
        for row in report["targets"]
        if row["status"] != "PASS"
    ]
    if details:
        print()
        for name, status, detail in details:
            print(f"  {status} {name}: {detail}")

    gen = report.get("generated_corpus") or []
    if gen:
        print()
        print("generated corpus (H106; listed, not counted):")
        for row in gen:
            print(f"  {row['target']}  {row['id']}  {row['status']}")
            print(f"      sha256 {row['sha256']}; {row['reason']}")

    counts = report["counts"]
    print()
    print(
        f"counts   pass={counts['pass']} fail={counts['fail']} "
        f"skip={counts['skip']} blocked={counts['blocked']} "
        f"runnable={counts['runnable']}/{counts['total']}"
    )
    if report["result"] == "PASS":
        print(
            "RESULT: PASS (every runnable target passed; "
            f"{counts['blocked']} blocked, {counts['skip']} skipped)"
        )
    elif report["result"] == "NO_RUNNABLE":
        print(
            "RESULT: NO_RUNNABLE (exit 3; every target is blocked or skipped, "
            "nothing was claimed)"
        )
    else:
        print(f"RESULT: FAIL ({counts['fail']} target(s) failed; exit 1)")




# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (UTF-8, temp file + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="L3 rung of the verification ladder (M9.8) and card gate (M9.12)",
        epilog=(
            "Exit codes: 0 every runnable target passed, 1 a target failed or "
            "an input was invalid, 2 usage error, 3 nothing was runnable "
            "(or card mode found no runnable verdict)."
        ),
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--root", help="card tree (recorded only; use --card/--factory for M9.12)")
    source.add_argument("--image", help="card image (recorded only; use --card/--factory for M9.12)")
    source.add_argument("--card", help="M9.12/M9.60: card image to check against --factory")
    parser.add_argument(
        "--factory",
        help="M9.12/M9.60: factory/baseline card image (required with --card)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="M9.31: with --card/--factory, run the registered runnable baselines "
             "on a no-diff pair instead of reporting bare NO_DIFFS",
    )
    parser.add_argument(
        "--baseline-dir",
        metavar="DIR",
        help="M9.31: directory with pre-extracted POINT010.DAT.cmp/.ind and "
             "HDD_INFO.TXT (scratch, never the repo); default extracts from --factory",
    )
    parser.add_argument(
        "--card-gate",
        action="store_true",
        help="M9.60: run the firmware's boot/sweep/mount rows; the exit code is the verdict",
    )
    parser.add_argument(
        "--position",
        action="append",
        default=[],
        metavar="LAT,LON",
        help="M9.60 --card-gate: a car position for the mount row (repeatable)",
    )
    parser.add_argument(
        "--corpus",
        help="corpus root built by tools/l3_harness/corpus.py (needs manifest.json)",
    )
    parser.add_argument(
        "--build-corpus",
        action="store_true",
        help="build a fresh corpus in a new temporary directory",
    )
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        metavar="NAME",
        help="run only this target (repeatable; default: every declared target)",
    )
    parser.add_argument(
        "--engine",
        default="pysh4",
        help="back end for every target: %s (default: pysh4)"
        % ", ".join(sorted(engine_mod.BACKENDS)),
    )
    parser.add_argument(
        "--targets",
        help="path to targets.json (default: tools/l3_harness/targets.json)",
    )
    parser.add_argument(
        "--json",
        nargs="?",
        const="-",
        metavar="PATH",
        help="machine-readable report: bare flag or '-' prints to stdout, "
        "PATH writes the same document to that file (atomic, UTF-8)",
    )
    parser.add_argument(
        "--generated",
        action="append",
        metavar="ID=PATH",
        help="H106: a local copy of a generated_corpus file (hashed and "
        "compared with the listed SHA-256; nothing is run)",
    )
    parser.add_argument(
        "--runs",
        action="store_true",
        help="M9.62: re-run the card-level L3 runs in tools/l3_harness/runs.json "
             "(needs vendor images; local/weekly only, never in PR CI)",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="ROW",
        help="M9.62 --runs: re-run only this reader-coverage matrix row (repeatable)",
    )
    parser.add_argument(
        "--run-manifest",
        help="M9.62 --runs: alternate runs.json (default: tools/l3_harness/runs.json)",
    )
    parser.add_argument(
        "--runs-scratch",
        help="M9.62 --runs: scratch dir for extracted card files and work dirs",
    )
    parser.add_argument(
        "--runs-timeout",
        type=int,
        default=900,
        help="M9.62 --runs: per-row subprocess timeout in seconds (default: 900)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="synthetic self-test: probe target, blocked target, FAIL/SKIP/card paths",
    )
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    if args.runs:
        matrix = TOOLS_DIR.parent / "docs" / "research" / "reader-coverage.md"
        manifest_path = Path(args.run_manifest) if args.run_manifest else runs_mod.MANIFEST
        try:
            doc = runs_mod.load(manifest_path)
        except runs_mod.RunsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        problems = runs_mod.validate(doc) + runs_mod.coverage_problems(doc, matrix)
        scratch = Path(args.runs_scratch) if args.runs_scratch else None
        try:
            rows = runs_mod.run_rows(doc, only=args.only, scratch=scratch,
                                     timeout=args.runs_timeout)
        except runs_mod.RunsError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        verdict, exit_code = runs_mod.result(rows)
        report = {
            "schema": runs_mod.SCHEMA, "command": "l3check --runs",
            "manifest": str(manifest_path), "matrix": str(matrix),
            "matrix_rows": runs_mod.matrix_row_ids(matrix),
            "problems": problems, "counts": runs_mod.counts(rows),
            "result": verdict, "exit": exit_code, "rows": rows,
        }
        if problems:
            report["result"], report["exit"] = "FAIL", 1
        if args.json is not None:
            document = json.dumps(report, indent=2)
            if args.json in ("", "-"):
                print(document)
            else:
                _write_atomic(Path(args.json), document + "\n")
        else:
            runs_mod.print_report(rows, report)
            for problem in problems:
                print(f"FAIL {problem}")
        return report["exit"]

    if args.card_gate:
        if not (args.card and args.factory):
            print("error: --card-gate needs --card and --factory", file=sys.stderr)
            return 2
        positions = []
        for spec in args.position:
            lat, _, lon = spec.partition(",")
            try:
                positions.append((float(lat), float(lon)))
            except ValueError:
                print(f"error: --position {spec!r} is not LAT,LON", file=sys.stderr)
                return 2
        if not positions:
            positions = [(51.70, 17.45)]        # the P1 tile's own position (M5.49)
        head = _find_img256()
        report = build_card_gate_report(
            Path(args.card), Path(args.factory), positions=positions, image=head)
        if args.json is not None:
            document = json.dumps(report, indent=2)
            if args.json in ("", "-"):
                print(document)
            else:
                _write_atomic(Path(args.json), document + "\n")
        else:
            _print_card_gate_report(report)
        return report["exit"]

    if args.engine not in engine_mod.BACKENDS:
        print(
            f"error: unknown engine {args.engine!r} "
            f"(known: {', '.join(sorted(engine_mod.BACKENDS))})",
            file=sys.stderr,
        )
        return 2

    try:
        report = build_report(args)
    except UsageError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json is not None:
        document = json.dumps(report, indent=2)
        if args.json in ("", "-"):
            print(document)
        else:
            _write_atomic(Path(args.json), document + "\n")
    else:
        if report.get("command") == "l3check --card --baseline":
            _print_baseline_report(report)
        elif report.get("command") == "l3check --card":
            _print_card_report(report)
        else:
            _print_report(report)
    return report["exit"]


# --------------------------------------------------------------------------
# Self-test: synthetic target + blocked target + honest FAIL/SKIP paths
# --------------------------------------------------------------------------

CHECKS: list[tuple[str, callable]] = []
SKIPS: list[str] = []
_SELFTEST_CORPUS: Path | None = None
_SELFTEST_TMP: Path | None = None


def check(name):
    def register(func):
        CHECKS.append((name, func))
        return func

    return register


def _cli(argv) -> tuple[int, str]:
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        code = main(argv)
    return code, buffer.getvalue()


def _json_cli(argv) -> tuple[int, dict]:
    code, output = _cli([*argv, "--json"])
    try:
        return code, json.loads(output)
    except json.JSONDecodeError:
        raise AssertionError(f"not JSON (exit {code}): {output}") from None


def _corpus() -> Path:
    assert _SELFTEST_CORPUS is not None
    return _SELFTEST_CORPUS


@check("targets: targets.json and the reader/claim table agree")
def test_evidence_table():
    by_name, _doc = runner_mod.load_targets()
    problems = _evidence_problems(by_name)
    assert not problems, problems
    assert TOOL_CLAIM == "C-1700"
    assert TARGET_EVIDENCE["probe-zlib-cmf"]["reader"] == "synthetic"
    assert TARGET_EVIDENCE["mapcode_comparator"]["claims"] == ("C-520", "C-528")
    # H51/M9.31: a card-verdict row names the firmware build that ran.  The
    # chunk-decoder adapter's build must stay in step with targets.json, or a
    # US card row could silently acquire an EU fn attribution (and vice versa).
    assert by_name["cmp_ind_reader"]["build"] == CARD_FIRMWARE_BUILD
    assert _card_firmware_build("cmp_ind_reader") == CARD_FIRMWARE_BUILD
    assert _card_firmware_build("poi_record_decode") is None  # no firmware ran
    for row in TARGET_EVIDENCE.values():
        for claim in row["claims"]:
            assert _CLAIM_RE.match(claim), claim


@check("run: the synthetic target PASSes and non-corpus-runnable readers are BLOCKED")
def test_full_run():
    code, report = _json_cli(["--corpus", str(_corpus())])
    assert code == 0, report
    assert report["result"] == "PASS", report
    assert report["claim"] == "C-1700"
    assert report["engine"] == "pysh4"
    assert report["corpus"]["source"] == "supplied", report["corpus"]
    assert report["corpus"]["entries"] == 111, report["corpus"]
    rows = {row["name"]: row for row in report["targets"]}
    probe = rows["probe-zlib-cmf"]
    assert probe["status"] == "PASS", probe
    assert probe["verdict"] == "ACCEPT" and probe["expected"] == "ACCEPT", probe
    assert probe["claims"] == ["C-1670", "C-1690"], probe
    assert probe["synthetic"] is True and probe["l3_claim"] is False, probe
    assert probe["input"]["manifest_sha256_match"] is True, probe["input"]
    assert probe["steps"] and probe["steps"] > 0, probe
    # M9.55: the POINT walker row is runnable from the corpus alone when the
    # us2011 head is present (image from the target's build, pair from the
    # corpus); without the archive head it is honestly BLOCKED, not FAIL.
    point = rows["point_walk_us2011"]
    us_head = (BUILD_IMAGES.get("us2011") or (lambda: None))()
    if us_head is not None:
        assert point["status"] == "PASS", point
        assert point["verdict"] == "ACCEPT" and point["expected"] == "ACCEPT", point
        assert point["claims"] == ["C-5770", "C-5771", "C-5772"], point
        assert point["l3_claim"] is True, point
        expected_blocked = [
            "applaunch_mapcode_compare",
            "cmp_ind_reader",
            "cmp_ind_reader_us2011",
            "drstr_parser",
            "hddinfo_compare",
            "lev3456_reader",
            "mapcode_comparator",
            "mmain_reader",
            "tile_reader",
            "tile_section4_reader",
        ]
        # M9.10: the name accessor row runs on the synthetic corpus page too
        name = rows["poi_record_decode"]
        assert name["status"] == "PASS", name
        assert name["verdict"] == "ACCEPT" and name["l3_claim"] is True, name
        assert name["claims"] == ["C-2140", "C-2141", "C-2142"], name
        expected_counts = {"pass": 3, "fail": 0, "skip": 0, "blocked": 10,
                           "runnable": 3, "total": 13}
    else:
        assert point["status"] == "BLOCKED", point
        assert point["verdict"] is None and point["accepted"] is None, point
        assert point["l3_claim"] is False and point["reason"], point
        assert "firmware head for build 'us2011' not found" in point["reason"], point
        assert point["claims"] == ["C-5770", "C-5771", "C-5772"], point
        expected_blocked = [
            "applaunch_mapcode_compare",
            "cmp_ind_reader",
            "cmp_ind_reader_us2011",
            "drstr_parser",
            "hddinfo_compare",
            "lev3456_reader",
            "mapcode_comparator",
            "mmain_reader",
            "poi_record_decode",
            "point_walk_us2011",
            "tile_reader",
            "tile_section4_reader",
        ]
        assert rows["poi_record_decode"]["status"] == "BLOCKED", rows["poi_record_decode"]
        expected_counts = {"pass": 1, "fail": 0, "skip": 0, "blocked": 12,
                           "runnable": 1, "total": 13}
    blocked = sorted(name for name, row in rows.items() if row["status"] == "BLOCKED")
    # The firmware_call readers (EU cmp_ind_reader, US cmp_ind_reader_us2011)
    # need external --image/--cmp/--ind, so a corpus-only run reports them
    # BLOCKED in this mode (M9.11b, M1.22); so does the AppLaunch map-code
    # compare, which needs --image/--input/--unit-from (M9.6), and the
    # DRSTR001 parser, which needs --image/--input (M9.24).
    assert blocked == expected_blocked, blocked
    for name in blocked:
        row = rows[name]
        assert row["verdict"] is None and row["accepted"] is None, row
        assert row["l3_claim"] is False and row["reason"], row
        assert row["claims"] == list(TARGET_EVIDENCE[name]["claims"]), row
    assert report["counts"] == expected_counts, report["counts"]


@check("run: --target selects exactly one target (PASS)")
def test_single_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf"]
    )
    assert code == 0, report
    assert [row["name"] for row in report["targets"]] == ["probe-zlib-cmf"], report
    assert report["counts"]["total"] == 1, report["counts"]
    assert report["targets"][0]["status"] == "PASS", report["targets"]


@check("run: a blocked target is exit 3 and claims no verdict")
def test_blocked_target():
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "hddinfo_compare"]
    )
    assert code == 3, report
    assert report["result"] == "NO_RUNNABLE", report
    row = report["targets"][0]
    assert row["status"] == "BLOCKED" and row["verdict"] is None, row
    assert row["l3_claim"] is False and row["reason"], row
    assert report["counts"]["runnable"] == 0, report["counts"]
    assert report["counts"]["blocked"] == 1, report["counts"]


@check("run: a blocked target needs no corpus input (nothing is invented)")
def test_blocked_needs_no_input():
    missing = Path(_SELFTEST_TMP) / "no-such-corpus"
    by_name, _doc = runner_mod.load_targets()
    row = _run_one(by_name["hddinfo_compare"], missing, "pysh4")
    assert row["status"] == "BLOCKED", row
    assert row["verdict"] is None and row["input"] is None, row
    assert row["l3_claim"] is False, row

@check("run: a firmware_call target is BLOCKED in corpus-only mode (needs --image/--cmp/--ind)")
def test_firmware_call_blocked_without_inputs():
    missing = Path(_SELFTEST_TMP) / "no-such-corpus"
    by_name, _doc = runner_mod.load_targets()
    row = _run_one(by_name["cmp_ind_reader"], missing, "pysh4")
    assert row["status"] == "BLOCKED", row
    assert row["verdict"] is None and row["l3_claim"] is False, row
    assert row["reason"] and ("--image" in row["reason"] or "firmware_call" in row["reason"]), row


@check("run: a tampered corpus makes the probe FAIL (never a pass)")
def test_tampered_corpus():
    target = Path(_SELFTEST_TMP) / "tampered"
    shutil.copytree(_corpus(), target)
    relative = "cmp/factory/ADDRE001.DAT.cmp"
    victim = target / relative
    data = bytearray(victim.read_bytes())
    data[0] = 0x00                      # no longer the zlib CMF 0x78
    victim.write_bytes(bytes(data))

    manifest_path = target / "manifest.json"
    doc = json.loads(manifest_path.read_text(encoding="utf-8"))
    import hashlib

    digest = hashlib.sha256(bytes(data)).hexdigest()
    for entry in doc["corpus"]:
        if entry["path"] == relative:
            entry["sha256"] = digest
            entry["size"] = len(data)
    manifest_path.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    code, report = _json_cli(
        ["--corpus", str(target), "--target", "probe-zlib-cmf"]
    )
    assert code == 1, report
    assert report["result"] == "FAIL", report
    row = report["targets"][0]
    assert row["status"] == "FAIL", row
    assert row["verdict"] == "REJECT", row
    assert any("expects ACCEPT" in problem for problem in row["problems"]), row
    assert row["input"]["manifest_sha256_match"] is True, row["input"]


@check("run: a corpus without manifest.json is invalid and runs nothing")
def test_missing_manifest():
    empty = Path(_SELFTEST_TMP) / "empty-corpus"
    empty.mkdir()
    code, report = _json_cli(["--corpus", str(empty)])
    assert code == 1, report
    assert report["result"] == "FAIL" and report["targets"] == [], report
    assert any("manifest.json" in problem for problem in report["problems"]), report


@check("run: an absent back end is SKIP, never PASS")
def test_backend_skip():
    available = next(
        item for item in engine_mod.probe_all(["ghidra"])
    )
    code, report = _json_cli(
        ["--corpus", str(_corpus()), "--target", "probe-zlib-cmf",
         "--engine", "ghidra"]
    )
    row = report["targets"][0]
    if not available.available:
        assert available.code == "MISSING_GHIDRA", available.as_dict()
        assert code == 3, report
        assert row["status"] == "SKIP" and row["verdict"] is None, row
        assert row["l3_claim"] is False, row
        assert "MISSING_GHIDRA" in row["reason"], row
        SKIPS.append(f"ghidra: {available.code} - {available.detail}")
        return
    assert row["status"] != "SKIP", row


@check("run: --build-corpus builds into a temporary directory")
def test_build_corpus():
    code, report = _json_cli(
        ["--build-corpus", "--target", "probe-zlib-cmf"]
    )
    try:
        assert code == 0, report
        corpus = report["corpus"]
        assert corpus["source"] == "built" and corpus["kept"] is True, corpus
        assert corpus["entries"] == 111, corpus
        assert Path(corpus["root"]).is_dir(), corpus
        assert (Path(corpus["root"]) / "manifest.json").is_file(), corpus
        assert report["targets"][0]["status"] == "PASS", report["targets"]
    finally:
        root = (report.get("corpus") or {}).get("root")
        if root:
            shutil.rmtree(root, ignore_errors=True)


@check("cli: an unknown --target is a usage error (exit 2)")
def test_unknown_target():
    code, output = _cli(
        ["--corpus", str(_corpus()), "--target", "no-such-target"]
    )
    assert code == 2, output
    assert "unknown target" in output, output


@check("cli: --corpus together with --build-corpus is a usage error")
def test_conflicting_corpus_flags():
    code, output = _cli(["--corpus", str(_corpus()), "--build-corpus"])
    assert code == 2, output
    assert "not both" in output, output


@check("run: two runs give the same verdicts")
def test_determinism():
    first = _json_cli(["--corpus", str(_corpus())])[1]
    second = _json_cli(["--corpus", str(_corpus())])[1]
    assert first == second, "two runs differ"


@check("cli: --json PATH writes the same document as bare --json")
def test_json_path():
    out = Path(_SELFTEST_TMP) / "nested" / "report.json"
    code, output = _cli(["--corpus", str(_corpus()), "--json", str(out)])
    assert code == 0, output
    assert output.strip() == "", f"--json PATH should not print: {output!r}"
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n"), "file should end with a newline"
    written = json.loads(text)
    bare_code, bare = _json_cli(["--corpus", str(_corpus())])
    assert bare_code == 0, bare
    assert written == bare, "file document differs from bare --json stdout"
    assert written["schema"] == SCHEMA, written.get("schema")

    dash_code, dash_out = _cli(["--corpus", str(_corpus()), "--json", "-"])
    assert dash_code == 0, dash_out
    assert json.loads(dash_out) == bare, "'-' must print the same document"


@check("cli: --json PATH still writes the report when the run fails")
def test_json_path_on_failure():
    empty = Path(_SELFTEST_TMP) / "empty-corpus-json"
    empty.mkdir(exist_ok=True)
    out = Path(_SELFTEST_TMP) / "failed.json"
    code, output = _cli(["--corpus", str(empty), "--json", str(out)])
    assert code == 1, output
    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["result"] == "FAIL", report


@check("card: --card without --factory is a usage error")
def test_card_requires_factory():
    code, output = _cli(["--card", "/no/such.img"])
    assert code == 2, output
    assert "--card and --factory" in output or "factory" in output.lower(), output


@check("card: missing images produce honest problems (no fake pass)")
def test_card_missing_images():
    code, report = _json_cli(["--card", "/no/such-card.img",
                              "--factory", "/no/such-factory.img"])
    assert code in (1, 3), report
    assert report["command"] == "l3check --card", report
    assert report["claim"] == CARD_CLAIM, report
    probs = report.get("problems") or []
    assert any("not found" in p for p in probs), report
    assert report["result"] != "PASS", report


@check("card: identical small files short-circuit to no diffs (no 7z)")
def test_card_identical_shortcircuit():
    p = Path(_SELFTEST_TMP) / "tiny.img"
    p.write_bytes(b"\x00" * 1024)
    code, report = _json_cli(["--card", str(p), "--factory", str(p)])
    assert code == 3, report  # no diffs / nothing runnable = not a pass
    assert report["diff"]["identical_images"] is True, report["diff"]
    assert report["diff"]["differing"] == [], report["diff"]
    assert report["result"] in ("NO_DIFFS", "NOT_YET_AVAILABLE"), report
    assert report["counts"]["fail"] == 0, report["counts"]


@check("card: target mapping reports POI reader as not-yet-available (M9.10)")
def test_card_poi_not_yet_available():
    by_name, _ = runner_mod.load_targets()
    # Simulate report structure for a POINT diff by calling the label logic.
    ct = next(c for c in _CARD_TARGETS if c["name"] == "poi_record_decode")
    assert ct["applies"]("REFER001/POINT010.DAT.cmp"), ct
    assert not ct["applies"]("REFER001/ADDRE001.DAT.cmp"), ct
    assert "not yet available" in ct["unavailable_note"].lower(), ct["unavailable_note"]
    assert "M9.10" in ct["unavailable_note"], ct["unavailable_note"]


@check("card: cmp pair normalization")
def test_card_cmp_pair():
    assert _norm_cmp_pair("REFER001/POINT010.DAT.cmp") == (
        "REFER001/POINT010.DAT.cmp", "REFER001/POINT010.DAT.ind")
    assert _norm_cmp_pair("REFER001/POINT010.DAT.ind") == (
        "REFER001/POINT010.DAT.cmp", "REFER001/POINT010.DAT.ind")
    assert _norm_cmp_pair("DRSTR001.DAT") is None


def _baseline_fixture():
    """Small identical card/factory pair plus documented baseline file names."""
    root = Path(_SELFTEST_TMP) / "baseline-fixture"
    root.mkdir(parents=True, exist_ok=True)
    files = {}
    for key, name in _BASELINE_FILES.items():
        path = root / name
        path.write_bytes(("fixture:" + name).encode("utf-8"))
        files[key] = path
    card = Path(_SELFTEST_TMP) / "baseline-card.img"
    card.write_bytes(b"\x00" * 1024)
    return card, files


@check("baseline: a pass needs status PASS and real firmware r0/insns")
def test_baseline_verdict_mapping():
    spec = BASELINE_TARGETS[0]
    real = _baseline_verdict(spec, {"status": "PASS", "verdict": "ACCEPT",
                                    "firmware": {"r0": 42848, "insns": 100}})
    assert real["status"] == "pass" and real["firmware"]["r0"] == 42848, real
    for status in ("DRY_RUN", "SKIP", "BLOCKED"):
        row = _baseline_verdict(spec, {"status": status, "exit": 0})
        assert row["status"] == "not-yet-available" and row["firmware"] is None, row
    bad = _baseline_verdict(spec, {"status": "MISMATCH",
                                   "firmware": {"r0": 0, "insns": 5}})
    assert bad["status"] == "fail", bad
    assert baseline_result([real]) == ("PASS", 0)
    assert baseline_result([bad]) == ("FAIL", 1)
    assert baseline_result([_baseline_verdict(spec, {"status": "DRY_RUN"})]) == (
        "NO_RUNNABLE_BASELINE_TARGETS", 3)


@check("baseline: identical fixture with injected runners gives explicit PASS rows")
def test_baseline_pass():
    card, files = _baseline_fixture()
    def pass_runner(spec, f, head):
        return {"status": "PASS", "verdict": "ACCEPT",
                "firmware": {"r0": 42848 if spec["name"] == "cmp_ind_reader" else 1,
                             "insns": 1905}, "l3_claim": True}
    report = build_baseline_report(
        card, card, files=files, heads={"eu2011": card},
        runners={spec["name"]: pass_runner for spec in BASELINE_TARGETS},
        card_build="eu2011")
    assert (report["result"], report["exit"]) == ("PASS", 0), report
    assert report["counts"] == {"pass": 2, "fail": 0,
                                "not-yet-available": 0, "total": 2}, report["counts"]
    assert all(r["status"] == "pass" and r["firmware"] for r in report["targets"]), report


@check("baseline: FAIL exits 1; DRY_RUN/SKIP are not-yet-available with zero passes")
def test_baseline_fail_and_dry_run():
    card, files = _baseline_fixture()
    fail_payload = {"status": "MISMATCH", "firmware": {"r0": 0, "insns": 10},
                    "problems": ["firmware verdict REJECT"]}
    report = build_baseline_report(
        card, card, files=files, heads={"eu2011": card},
        runners={spec["name"]: (lambda s, f, h: dict(fail_payload))
                 for spec in BASELINE_TARGETS},
        card_build="eu2011")
    assert (report["result"], report["exit"]) == ("FAIL", 1), report
    assert report["counts"]["pass"] == 0, report["counts"]
    payloads = iter(({"status": "DRY_RUN", "exit": 0}, {"status": "SKIP"}))
    report2 = build_baseline_report(
        card, card, files=files, heads={"eu2011": card},
        runners={spec["name"]: (lambda s, f, h: next(payloads))
                 for spec in BASELINE_TARGETS},
        card_build="eu2011")
    assert report2["result"] == "NO_RUNNABLE_BASELINE_TARGETS" and report2["exit"] == 3, report2
    assert report2["counts"]["pass"] == 0, report2["counts"]
    assert all(r["status"] == "not-yet-available" for r in report2["targets"]), report2


@check("baseline: build mismatch / missing head / no runner never fabricate a verdict")
def test_baseline_no_runnable():
    card, files = _baseline_fixture()
    us = build_baseline_report(card, card, files=files, heads={}, card_build="us2011")
    assert us["exit"] == 3 and us["result"] == "NO_RUNNABLE_BASELINE_TARGETS", us
    assert all("build mismatch" in r["detail"] and "US-card" in r["detail"]
               for r in us["targets"]), us["targets"]
    nohead = build_baseline_report(card, card, files=files,
                                   heads={"eu2011": Path("/no/head")},
                                   card_build="eu2011")
    assert nohead["exit"] == 3 and "no eu2011 firmware head" in nohead["targets"][0]["detail"], nohead
    norunner = build_baseline_report(card, card, files=files,
                                     heads={"eu2011": card},
                                     runners={}, card_build="eu2011")
    assert norunner["exit"] == 3 and "no runner registered" in norunner["targets"][0]["detail"], norunner


@check("cli: --baseline needs --card/--factory; plain --card on identical files stays NO_DIFFS")
def test_baseline_cli():
    code, output = _cli(["--baseline"])
    assert code == 2 and "--baseline needs" in output, output
    card, _files = _baseline_fixture()
    code, report = _json_cli(["--card", str(card), "--factory", str(card)])
    assert code == 3 and report["result"] == "NO_DIFFS", report
    code, report2 = _json_cli(["--card", str(card), "--factory", str(card), "--baseline"])
    assert code == 3 and report2["result"] == "NO_RUNNABLE_BASELINE_TARGETS", report2
    assert report2["command"] == "l3check --card --baseline", report2


@check("generated corpus (H106): tile_reader lists our tiles with a status, counts unchanged")
def test_generated_corpus_listed():
    code, report = _json_cli(["--corpus", str(_corpus())])
    assert code == 0, (code, report.get("problems"))
    rows = {r["id"]: r for r in report["generated_corpus"]}
    for ident in ("generated:m5.11:B48R058R", "synthetic:one_tile_pipeline"):
        assert ident in rows and rows[ident]["target"] == "tile_reader", rows.keys()
        assert rows[ident]["status"].startswith(GEN_RAN[:-1]) \
            or rows[ident]["status"] == GEN_NOT_RUN_TREE, rows[ident]
    assert rows["synthetic:one_tile_pipeline"]["status"] == "RAN (recorded: DIFFERENT)", rows
    assert rows["generated:m5.11:B48R058R"]["status"] == "RAN (recorded: SAME)", rows
    assert rows["generated:m5.34:B48R058R"]["status"] == GEN_NOT_RUN_TREE
    assert not rows["generated:m5.34:B48R058R"]["ran_on_our_generated_data"]
    names = [t["name"] for t in report["targets"]]
    assert names.count("tile_reader") == 1, names
    assert report["counts"]["total"] == len(names) == report["target_count"]


@check("generated corpus (H106): a STALE file makes the run FAIL (exit 1), never PASS")
def test_generated_corpus_stale_fails():
    bad = Path(_SELFTEST_TMP) / "gen-stale.DAT"
    bad.write_bytes(b"not the M5.11 tile")
    code, report = _json_cli(["--corpus", str(_corpus()),
                              "--generated", f"generated:m5.11:B48R058R={bad}"])
    assert code == 1 and report["result"] == "FAIL", (code, report["result"])
    row = next(r for r in report["generated_corpus"] if r["id"] == "generated:m5.11:B48R058R")
    assert row["status"] == GEN_STALE and "applies to 1927c3a9" in row["reason"], row
    assert any(GEN_STALE in p for p in report["problems"]), report["problems"]


def _gen_fixture(recorded: bool, data: bytes = b"our tile"):
    sha = hashlib.sha256(data).hexdigest()
    entry = {"id": "generated:test:T", "path": "MAPAL001/T.DAT", "sha256": sha,
             "run": "datask_l3.py mount --replace MAPAL001/T.DAT=FILE",
             "recorded": ({"exp": "EXP-x", "sha256": sha, "verdict": "SAME", "detail": "d"}
                          if recorded else None),
             "ran_on_our_generated_data": recorded}
    return {"tile_reader": {"name": "tile_reader", "generated_corpus": [entry]}}, sha


@check("generated corpus (H106): status follows the file's SHA-256, not its name")
def test_generated_corpus_status():
    good = Path(_SELFTEST_TMP) / "gen-good.DAT"
    bad = Path(_SELFTEST_TMP) / "gen-bad.DAT"
    good.write_bytes(b"our tile")
    bad.write_bytes(b"another tile")
    by_name, _sha = _gen_fixture(False)
    rows, probs = generated_rows(by_name)
    assert not probs and rows[0]["status"] == GEN_NOT_RUN_TREE, (rows, probs)
    rows, probs = generated_rows(by_name, {"generated:test:T": good})
    assert not probs and rows[0]["status"] == GEN_NOT_RUNNABLE, rows
    assert not rows[0]["ran_on_our_generated_data"]
    rows, probs = generated_rows(by_name, {"generated:test:T": bad})
    assert rows[0]["status"] == GEN_BAD_FILE and any(GEN_BAD_FILE in p for p in probs), (rows, probs)
    by_name, _sha = _gen_fixture(True)
    rows, probs = generated_rows(by_name)
    assert not probs and rows[0]["status"] == "RAN (recorded: SAME)" and rows[0]["ran_on_our_generated_data"]
    rows, probs = generated_rows(by_name, {"generated:test:T": good})
    assert not probs and rows[0]["status"] == "RAN (recorded: SAME)", (rows, probs)
    rows, probs = generated_rows(by_name, {"generated:test:T": bad})
    assert rows[0]["status"] == GEN_STALE and not rows[0]["ran_on_our_generated_data"], rows
    assert any(GEN_STALE in p for p in probs), probs
    assert "applies to" in rows[0]["reason"] and not rows[0]["reason"].startswith("SAME"), rows
    # negative: a record for another file, or a flag that disagrees, is a problem
    by_name["tile_reader"]["generated_corpus"][0]["recorded"]["sha256"] = "0" * 64
    _rows, probs = generated_rows(by_name)
    assert any("another file" in p for p in probs), probs
    by_name, _sha = _gen_fixture(False)
    by_name["tile_reader"]["generated_corpus"][0]["ran_on_our_generated_data"] = True
    _rows, probs = generated_rows(by_name)
    assert any("disagrees" in p for p in probs), probs
    _rows, probs = generated_rows(by_name, {"generated:nope": good})
    assert any("no generated_corpus entry" in p for p in probs), probs


@check("card gate (M9.60): the verdict table is PASS/FAIL/NOT RUN, never a fake pass")
def test_card_gate_verdict_table():
    pass_rows = [{"row": n, "status": ROW_PASS, "detail": "x"} for n in ("boot", "sweep", "mount")]
    v = _gate_verdict(pass_rows)
    assert (v["result"], v["exit"]) == ("PASS", 0), v
    assert v["counts"] == {"pass": 3, "fail": 0, "not_run": 0, "total": 3}, v
    # a FAIL row wins over a not-run row
    mixed = [{"row": "boot", "status": ROW_PASS, "detail": "x"},
             {"row": "sweep", "status": ROW_NOT_RUN, "detail": "NOT RUN (diff)"},
             {"row": "mount", "status": ROW_FAIL, "detail": "read ... status -1"}]
    v = _gate_verdict(mixed)
    assert (v["result"], v["exit"]) == ("FAIL", 1), v
    assert v["failed_reads"] and "status -1" in v["failed_reads"][0], v
    # anything not run, and nothing failed, is NOT RUN (exit 3)
    notrun = [{"row": n, "status": ROW_NOT_RUN, "detail": "NOT RUN (build)"}
              for n in ("boot", "sweep", "mount")]
    v = _gate_verdict(notrun)
    assert (v["result"], v["exit"]) == ("NOT RUN", 3), v
    assert v["counts"]["pass"] == 0, v


@check("card gate (M9.60): boot row -- 0 error-log calls PASSes, a REJECT fails")
def test_card_gate_boot_row():
    ok = _verdict_boot({"verdict": "ACCEPT", "dirs": 40, "files": 285, "fwlog": []})
    assert ok["status"] == ROW_PASS and ok["error_log_calls"] == 0, ok
    noisy = _verdict_boot({"verdict": "ACCEPT", "fwlog": [(0x1, 2, 3, 4)]})
    assert noisy["status"] == ROW_FAIL and "error-log" in noisy["detail"], noisy
    reject = _verdict_boot({"verdict": "REJECT", "states": [(1, 1)]})
    assert reject["status"] == ROW_FAIL and "REJECT" in reject["detail"], reject


@check("card gate (M9.60): sweep row -- one bad file fails and names it")
def test_card_gate_sweep_row():
    good = _verdict_sweep({"rows": [{"path": "A", "status": "OK", "checked": 4}],
                           "returncode": 0})
    assert good["status"] == ROW_PASS, good
    bad = _verdict_sweep({"rows": [{"path": "A", "status": "OK"},
                                   {"path": "MAPAL001/B48R058R.DAT",
                                    "status": "READ-ERROR 0x1ff at 0x113e6800"}],
                          "returncode": 1})
    assert bad["status"] == ROW_FAIL and "MAPAL001/B48R058R.DAT" in bad["detail"], bad
    assert bad["not_ok"] == 1 and bad["files"] == 2, bad
    blocked = _verdict_sweep({"blocked": "MAPAL001/X.DAT: no model", "rows": []})
    assert blocked["status"] == ROW_FAIL and "BLOCKED" in blocked["detail"], blocked
    none = _verdict_sweep({"rows": [], "returncode": 0})
    assert none["status"] == ROW_NOT_RUN, none


@check("card gate (M9.60): mount row -- a negative read fails and names it; SAME passes")
def test_card_gate_mount_row():
    base = {"state": 2, "mesh_count": 46, "reads": 2,
            "rows": [{"file": "MAPAL001/B48R058R.DAT", "status": 0, "readers": [1]}],
            "other": [{"kind": "ErrorLogMsg", "args": [2, 10, 0, 11]}]}
    same = _verdict_mount(dict(base), dict(base))
    assert same["status"] == ROW_PASS and "SAME as factory" in same["detail"], same
    neg = dict(base)
    neg["rows"] = [{"file": "MAPAL001/B48R058R.DAT", "pos": 0x1100, "length": 0x8100,
                    "status": 0xFFFFFFFF, "readers": []}]
    row = _verdict_mount(neg, dict(base))
    assert row["status"] == ROW_FAIL, row
    assert "MAPAL001/B48R058R.DAT" in row["detail"] and "status 4294967295" in row["detail"], row
    # a noisy card (an extra error-log call) fails against the factory's one
    noisy = dict(base)
    noisy["other"] = [{"kind": "ErrorLogMsg", "args": [2, 40, 7, 11]},
                      {"kind": "ErrorLogMsg", "args": [2, 10, 0, 11]}]
    assert _verdict_mount(noisy, dict(base))["status"] == ROW_FAIL
    # no tile read parsed is NOT RUN, not a pass
    empty = dict(base)
    empty["rows"] = [{"file": "REFER001/X.DAT", "status": 0, "readers": [1]}]
    assert _verdict_mount(empty, dict(base))["status"] == ROW_NOT_RUN
    # a blocked card is a FAIL that names the stop; a blocked factory is NOT RUN
    assert _verdict_mount({"blocked": "the card did not mount"}, dict(base))["status"] == ROW_FAIL
    assert _verdict_mount(dict(base), {"blocked": "no control"})["status"] == ROW_NOT_RUN


@check("card gate (M9.60): missing card/factory/head are NOT RUN (exit 3), never PASS")
def test_card_gate_missing_inputs():
    head = Path(_SELFTEST_TMP) / "no-head.img"
    for card, factory, image in (
            (None, None, None),
            (Path("/no/such-card.img"), Path("/no/such-factory.img"), None),
            (Path("/no/such-card.img"), Path("/no/such-factory.img"), head)):
        report = build_card_gate_report(card, factory, positions=[(51.70, 17.45)],
                                        image=image)
        assert report["result"] == "NOT RUN" and report["exit"] == 3, report
        assert all(r["status"] == ROW_NOT_RUN for r in report["rows"]), report["rows"]
        assert report["problems"], report


@check("card gate (M9.60): a 96 MiB firmware prefix -- unknown is not the gate build")
def test_card_gate_build_prefix():
    # a small file cannot equal the EU2011 firmware prefix
    p = Path(_SELFTEST_TMP) / "not-a-card.img"
    p.write_bytes(b"\x00" * 4096)
    assert _card_head_build(p) not in ("eu2011", "us2011")
    assert "unknown" in _card_head_build(p) and "…" in _card_head_build(p)


@check("runs (M9.62): manifest has one entry per l3-running matrix row")
def test_runs_coverage():
    matrix = TOOLS_DIR.parent / "docs" / "research" / "reader-coverage.md"
    doc = runs_mod.load()
    assert not runs_mod.validate(doc), runs_mod.validate(doc)
    problems = runs_mod.coverage_problems(doc, matrix)
    assert not problems, problems
    agreement = runs_mod.count_agreement(doc, matrix)
    assert agreement["agree"], agreement
    assert agreement["matrix"] == 9 and agreement["manifest"] == 9, agreement
    # negative mutation: a matrix row with no manifest entry is named
    doc2 = {"rows": [r for r in doc["rows"] if str(r["row"]) != "17"]}
    gone = runs_mod.coverage_problems(doc2, matrix)
    assert any("row 17" in p for p in gone), gone


@check("runs (M9.62): no images -> every row NOT RUN, exit 3")
def test_runs_no_images():
    doc = runs_mod.load()
    rows = runs_mod.run_rows(doc, only=["5"], scratch=_SELFTEST_TMP,
                             extra={"IMG": "/no/such-head.img",
                                    "CARD": "/no/such-card.img"})
    assert rows[0]["status"] == runs_mod.NOT_RUN, rows[0]
    verdict, exit_code = runs_mod.result(rows)
    assert (verdict, exit_code) == ("NOT RUN", 3), (verdict, exit_code)


@check("runs (M9.62): a wrong expected verdict FAILs (exit 1)")
def test_runs_wrong_expect():
    import sys as _sys
    synth = {
        "schema": runs_mod.SCHEMA, "placeholders": {},
        "rows": [{"row": "S", "what": "synthetic", "reader": "x",
                  "build": "eu2011", "tool": "x",
                  "argv": [_sys.executable, "-c", "print('hello')"],
                  "expect": "goodbye", "source_exp": "x", "claim": "C-1",
                  "need": [], "firmware_pass": False}],
    }
    rows = runs_mod.run_rows(synth, scratch=_SELFTEST_TMP)
    assert rows[0]["status"] == runs_mod.FAIL, rows[0]
    verdict, exit_code = runs_mod.result(rows)
    assert (verdict, exit_code) == ("FAIL", 1), (verdict, exit_code)


def run_selftest() -> int:
    global _SELFTEST_CORPUS, _SELFTEST_TMP

    failures = 0
    with tempfile.TemporaryDirectory(prefix="l3check-selftest-") as tmp:
        _SELFTEST_TMP = Path(tmp)
        _SELFTEST_CORPUS = Path(tmp) / "corpus"
        try:
            corpus_mod.build_corpus(_SELFTEST_CORPUS)
        except (corpus_mod.CorpusError, manifest_mod.ManifestError, OSError) as exc:
            print(f"FAIL corpus fixture: {exc}")
            print("\nl3check selftest: FAILED (0/1 checks)")
            return 1

        for name, func in CHECKS:
            try:
                func()
            except Exception as exc:  # noqa: BLE001 - report, do not abort
                failures += 1
                print(f"FAIL {name}: {exc}")
                if "--verbose" in sys.argv[1:]:
                    import traceback

                    traceback.print_exc()
            else:
                print(f"ok   {name}")
        for skip in SKIPS:
            print(f"skip {skip}")

    total = len(CHECKS)
    print()
    if failures:
        print(f"l3check selftest: FAILED ({failures}/{total} checks)")
        return 1
    print(
        f"l3check selftest: OK ({total} checks"
        + (f", {len(SKIPS)} skipped" if SKIPS else "")
        + ")"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
