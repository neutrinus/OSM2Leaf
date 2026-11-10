#!/usr/bin/env python3
"""Reachability precondition gate for reopened L3 reader reruns (H45).

For a named L3 target (from tools/l3_harness/targets.json) or an ad-hoc
reader VA/module, report preconditions without executing firmware:

  * executable vs data bytes for the module/entry context (from image when
    available; from stated metadata when not);
  * compressed-sec1/data dependency (M1.2f) - present, absent, mitigated by
    declared input, or unknown;
  * import/input/binding reachability - known, unknown, or blocked, with
    reasons;
  * verdict READY | BLOCKED | UNKNOWN with reasons.

READY means the checked preconditions do not show a known blocker for a rerun
(given any declared inputs the target already carries). It is not a firmware
pass and does not claim the reader accepts data. BLOCKED means a known
blocker (e.g. M1.2f compressed data/imports unreachable, missing entry/mapping)
applies. UNKNOWN means metadata or image facts are insufficient to decide; the
missing fields are listed and the verdict is never guessed as READY.

No firmware execution. No vendor bytes committed. Stdlib only.

Usage:
  l3_precond.py --selftest
  l3_precond.py --target drstr_parser [--json]
  l3_precond.py --all-targets [--targets PATH] [--json]
  l3_precond.py --va 0x00419350 --module Navi.exe [--image IMG] [--json]

EXP: docs/experiments/EXP-2026-11-09-H45-l3-precond.md
Claims: C-3330-C-3339
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_TARGETS = HERE / "l3_harness" / "targets.json"

sys.path.insert(0, str(HERE))
import va_class  # noqa: E402
import cerom  # noqa: E402

# Verdicts.
READY = "READY"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"


class PrecondError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Target loading
# ---------------------------------------------------------------------------


def load_targets(path: Path | str | None = None) -> tuple[dict[str, dict], dict]:
    path = Path(path) if path else DEFAULT_TARGETS
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PrecondError(f"cannot read targets {path}: {exc}") from exc
    targets = doc.get("targets")
    if not isinstance(targets, list):
        raise PrecondError(f"targets.json has no 'targets' list: {path}")
    by_name: dict[str, dict] = {}
    for target in targets:
        name = target.get("name")
        if not isinstance(name, str) or not name:
            raise PrecondError(f"target missing name in {path}")
        if name in by_name:
            raise PrecondError(f"duplicate target name {name!r} in {path}")
        by_name[name] = target
    return by_name, doc


# ---------------------------------------------------------------------------
# Metadata classification helpers
# ---------------------------------------------------------------------------

_M1_2F_RE = re.compile(r"\bM1\.2f\b|compressed\s+sec1|compressed\s+\.?data|sec1\b.*compress", re.I)
_IMPORT_BIND_RE = re.compile(
    r"\bimport\b|\bCRT\b|\bcoredll\b|\bstub\b|\bIAT\b|\bthunk\b|\bbinding\b|\bCOM\b|runtime\s+COM",
    re.I,
)
_MISSING_MAP_RE = re.compile(
    r"no\s+(?:tile\s+reader\s+)?entry\s+point|no\s+entry\s+VA|not\s+been\s+recovered|"
    r"not\s+located|missing\s+mapping|no\s+runnable\s+target",
    re.I,
)
_INPUT_BIND_RE = re.compile(r"\binput\b|\bbuffer\b|\bfile\b|\bpath\b|\bCreateFile|\bReadFile|\bfopen\b", re.I)


def _join_text(*parts: Any) -> str:
    out = []
    for part in parts:
        if part is None:
            continue
        if isinstance(part, str):
            out.append(part)
        elif isinstance(part, (list, tuple)):
            out.extend(str(x) for x in part if x is not None)
        elif isinstance(dict, type(part)):
            out.append(json.dumps(part, sort_keys=True))
        else:
            out.append(str(part))
    return "\n".join(out)


def _entry(target: dict) -> dict:
    entry = target.get("entry")
    return entry if isinstance(entry, dict) else {}


def _has_declared_sec1_input(entry: dict) -> bool:
    sec1 = entry.get("sec1_table")
    if not isinstance(sec1, dict):
        return False
    # Must carry provenance/values/va - a declared input, not a silent default.
    return bool(sec1.get("values") or sec1.get("va")) and bool(sec1.get("provenance") or sec1.get("values"))


def _classify_m1_2f(target: dict) -> dict:
    entry = _entry(target)
    text = _join_text(entry.get("reason"), entry.get("note"), target.get("notes"),
                      target.get("what"), target.get("expect", {}).get("rule"))
    reason_l = text.lower()
    has_m1_2f = bool(_M1_2F_RE.search(text))
    mitigated = False
    mitigation = None
    if _has_declared_sec1_input(entry):
        # The real sec1 bytes are still M1.2f-open for verification in cmp_ind_reader's case,
        # but the rerun path is supplied with a declared input.
        if "sec1" in _join_text(entry.get("sec1_table", {}).get("provenance")).lower() or has_m1_2f:
            mitigated = True
            mitigation = "declared sec1_table input supplied (sec1 byte verification may remain M1.2f-open)"
        else:
            mitigated = True
            mitigation = "declared sec1_table input supplied"
    if has_m1_2f and not mitigated:
        return {"status": "present", "blocker": True, "detail": "M1.2f/compressed-sec1 data dependency stated in target metadata",
                "evidence": _first_match(text, _M1_2F_RE)}
    if has_m1_2f and mitigated:
        return {"status": "mitigated", "blocker": False, "detail": mitigation,
                "evidence": _first_match(text, _M1_2F_RE)}
    if mitigated:
        return {"status": "mitigated", "blocker": False, "detail": mitigation, "evidence": "sec1_table declared input"}
    # No explicit M1.2f mention - cannot claim absent without image/code analysis; be honest.
    if entry.get("kind") == "synthetic":
        return {"status": "absent", "blocker": False, "detail": "synthetic program, no firmware sec1/data dependency", "evidence": "entry.kind=synthetic"}
    return {"status": "unknown", "blocker": False, "detail": "no explicit M1.2f/compressed-sec1 dependency stated in metadata; image/code analysis not performed",
            "evidence": None}


def _first_match(text: str, pattern: re.Pattern[str]) -> str | None:
    m = pattern.search(text)
    if not m:
        return None
    start = max(0, m.start() - 30)
    end = min(len(text), m.end() + 60)
    snippet = " ".join(text[start:end].split())
    return snippet


def _classify_reachability(target: dict) -> dict:
    entry = _entry(target)
    text = _join_text(entry.get("reason"), entry.get("note"), target.get("notes"),
                      target.get("what"), target.get("stubs"))
    dims: dict[str, dict[str, Any]] = {}

    # Entry/mapping reachability.
    kind = entry.get("kind")
    va = entry.get("va")
    module = entry.get("module") or target.get("module")
    if kind == "blocked" and _MISSING_MAP_RE.search(text):
        dims["entry_mapping"] = {"status": "blocked", "detail": _first_match(text, _MISSING_MAP_RE) or "missing entry/mapping"}
    elif kind == "blocked" and not va:
        dims["entry_mapping"] = {"status": "blocked", "detail": "entry kind blocked with no VA"}
    elif va and module:
        dims["entry_mapping"] = {"status": "known", "detail": f"entry VA {va} in module {module} declared"}
    elif va:
        dims["entry_mapping"] = {"status": "known", "detail": f"entry VA {va} declared"}
    elif kind == "synthetic":
        dims["entry_mapping"] = {"status": "known", "detail": "synthetic program entry declared"}
    else:
        missing = []
        if not va:
            missing.append("entry.va")
        if not module and kind not in ("synthetic",):
            missing.append("entry.module/module")
        dims["entry_mapping"] = {"status": "unknown", "detail": "entry/mapping fields incomplete",
                                 "missing_fields": missing or ["entry metadata"]}

    # Import/binding reachability.
    if kind == "blocked" and _IMPORT_BIND_RE.search(text) and ("unmapped" in text.lower() or "compressed sec1" in text.lower() or "m1.2f" in text.lower()):
        dims["import_binding"] = {"status": "blocked", "detail": _first_match(text, _IMPORT_BIND_RE) or "import/binding blocked"}
    elif kind == "blocked" and re.search(r"runtime\s+COM|COM\s+object", text, re.I):
        dims["import_binding"] = {"status": "blocked", "detail": "runtime COM/binding; no static entry"}
    elif target.get("stubs") and kind in ("synthetic", "firmware_call"):
        dims["import_binding"] = {"status": "known", "detail": f"{len(target['stubs'])} stub(s)/bindings declared in target metadata"}
    elif kind == "synthetic":
        dims["import_binding"] = {"status": "known", "detail": "synthetic stubs declared"}
    elif kind == "firmware_call":
        # firmware_call may run with direct call setup; stubs may be empty.
        dims["import_binding"] = {"status": "known", "detail": "firmware_call entry; imports not listed as blockers in metadata (direct call path)"}
    elif _IMPORT_BIND_RE.search(text):
        dims["import_binding"] = {"status": "unknown", "detail": "import/binding mentioned but reachability not fully determined from metadata"}
    else:
        dims["import_binding"] = {"status": "unknown", "detail": "no import/binding facts stated"}

    # Input/binding reachability.
    corpus = target.get("corpus") if isinstance(target.get("corpus"), dict) else {}
    inputs = entry.get("inputs") if isinstance(entry.get("inputs"), dict) else {}
    if corpus.get("path") or corpus.get("guest_path") or inputs:
        parts = []
        if corpus.get("path"):
            parts.append(f"corpus.path={corpus['path']}")
        if inputs:
            parts.append("entry.inputs declared")
        if kind == "firmware_call" and not (target.get("stubs") or corpus.get("path")):
            pass
        dims["input_binding"] = {"status": "known", "detail": "; ".join(parts) if parts else "input metadata present"}
    elif kind == "synthetic":
        dims["input_binding"] = {"status": "known", "detail": "synthetic input path/corpus declared" if corpus else "synthetic target"}
    elif kind == "blocked" and _INPUT_BIND_RE.search(text) and "unmapped" in text.lower():
        dims["input_binding"] = {"status": "blocked", "detail": "input/buffer access blocked per metadata"}
    else:
        dims["input_binding"] = {"status": "unknown", "detail": "no explicit input/binding contract stated"}

    return dims


# ---------------------------------------------------------------------------
# Optional image enrichment
# ---------------------------------------------------------------------------


def _default_image() -> str | None:
    env = os.environ.get("OSM2LEAF_IMG")
    if env and os.path.isfile(env):
        return env
    for root in [REPO, Path(os.getcwd())]:
        cand = root / "archive" / "head256.img"
        if cand.is_file():
            return str(cand)
    return None


def _module_bytes_report(image: str, image_start: int, module: str) -> dict | None:
    try:
        import point_walk_l3 as pw  # type: ignore
        data = pw.load_image(image)
        _, secs = pw.module_sections(data, image_start, module)
    except Exception as exc:  # noqa: BLE001 - enrichment is optional
        return {"error": f"{type(exc).__name__}: {exc}"}
    exec_plain = exec_comp = data_plain = data_comp = 0
    exec_comp_secs = []
    for s, comp, _blob in secs:
        flags = s["flags"]
        is_exec = bool(flags & (getattr(pw, "CODE", 0x20) | getattr(pw, "EXEC", 0x20000000)))
        vsize = s["vsize"]
        if is_exec and comp:
            exec_comp += vsize
            exec_comp_secs.append({"realaddr": hex(s["realaddr"]), "vsize": vsize})
        elif is_exec:
            exec_plain += vsize
        elif comp:
            data_comp += vsize
        else:
            data_plain += vsize
    return {
        "module": module,
        "exec_decodable_bytes": exec_plain,
        "exec_compressed_bytes": exec_comp,
        "data_decodable_bytes": data_plain,
        "data_compressed_bytes": data_comp,
        "exec_compressed_sections": exec_comp_secs,
        "source": os.path.basename(image),
    }


def _va_section_report(image: str, image_start: int, module: str, va: int) -> dict | None:
    try:
        import point_walk_l3 as pw  # type: ignore
        data = pw.load_image(image)
        _, secs = pw.module_sections(data, image_start, module)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}
    for i, (s, comp, _blob) in enumerate(secs):
        start = s["realaddr"]
        if start <= va < start + s["vsize"]:
            is_exec = bool(s["flags"] & (getattr(pw, "CODE", 0x20) | getattr(pw, "EXEC", 0x20000000)))
            return {
                "va": hex(va),
                "module": module,
                "section_index": i,
                "section_realaddr": hex(start),
                "compressed": comp,
                "executable": is_exec,
                "kind": ("exec" if is_exec else "data") + ("-compressed" if comp else "-plain"),
            }
    return {"va": hex(va), "module": module, "section": None, "detail": "VA not found in module sections"}



# ---------------------------------------------------------------------------
# va_class enrichment (H50)
# ---------------------------------------------------------------------------


def _default_resolve_with(image_start: int, resolve_with: list[int] | None) -> list[int]:
    if resolve_with:
        return list(resolve_with)
    # Build-A Navi.exe ordinals resolve through build B (COREDLL, etc.) on the card.
    if image_start == 0x200200:
        return [0x3e00200]
    return []


def _load_va_context(image: str, image_start: int, module: str, resolve_with: list[int],
                     cache: dict) -> tuple[list, dict] | tuple[None, None]:
    key = (os.path.realpath(image), image_start, module, tuple(resolve_with))
    if key in cache:
        return cache[key]
    try:
        with open(image, "rb") as fh:
            data = fh.read()
        sections, slots = va_class.build_context(data, image_start, module, resolve_with)
        cache[key] = (sections, slots)
    except Exception:  # noqa: BLE001
        cache[key] = (None, None)
    return cache[key]


def _in_module_va(va: int, sections) -> bool:
    for s in sections or []:
        if s["start"] <= va < s["start"] + max(s["vsize"], s["psize"]):
            return True
    return False


def _classify_vas_for_report(vas, sections, slots):
    rows = []
    seen = set()
    for va in vas:
        if va in seen:
            continue
        seen.add(va)
        if not _in_module_va(va, sections):
            continue
        row = dict(va="0x%08x" % va, va_int=va, **va_class.classify(va, sections, slots))
        row["class_text"] = va_class.format_class(row)
        rows.append(row)
    return rows


def _va_class_dim(cls):
    if cls == "INIT":
        return {"status": "present", "blocker": True,
                "detail": "INIT (initialised compressed .data bytes; needs M1.2f)",
                "evidence": "va_class=INIT"}
    if cls == "IAT":
        return {"status": "iat", "blocker": False,
                "detail": "IAT import slot (loader-bound; needs import/binding/stub, not M1.2f)",
                "evidence": "va_class=IAT"}
    if cls == "BSS":
        return {"status": "bss", "blocker": False,
                "detail": "BSS (zero at load; find writer/runtime init, not M1.2f)",
                "evidence": "va_class=BSS"}
    return None


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------


def assess_target(target: dict, *, image: str | None = None, image_start: int = 0x200200,
                  resolve_with: list[int] | None = None, _va_cache: dict | None = None) -> dict:
    name = target.get("name", "?")
    entry = _entry(target)
    kind = entry.get("kind")
    va_raw = entry.get("va")
    module = entry.get("module") or target.get("module")
    va = None
    if isinstance(va_raw, str):
        try:
            va = int(va_raw, 0)
        except ValueError:
            va = None
    elif isinstance(va_raw, int):
        va = va_raw

    m1_2f = _classify_m1_2f(target)
    reach = _classify_reachability(target)
    reasons: list[str] = []
    missing_fields: list[str] = []

    bytes_info: dict[str, Any] = {"status": "unknown", "detail": "no image provided; byte counts not computed"}
    va_info = None
    if image and module:
        rep = _module_bytes_report(image, image_start, module)
        if rep and "error" not in rep:
            bytes_info = rep
        elif rep:
            bytes_info = {"status": "unknown", "detail": rep["error"]}
    if image and module and va is not None:
        va_info = _va_section_report(image, image_start, module, va)
        if va_info and "error" not in va_info and va_info.get("section_realaddr") is not None:
            bytes_info.setdefault("entry_location", va_info)
            # compressed-entry note handled below after va_class enrichment
    elif not image:
        note_text = _join_text(entry.get("note"), entry.get("reason"), target.get("notes"))
        if re.search(r"executable,?\s+uncompressed\s+sec0|lies in the executable, uncompressed", note_text, re.I):
            bytes_info = {"status": "metadata", "detail": "target metadata states entry is in executable uncompressed sec0; not verified against image here",
                          "metadata_hint": _first_match(note_text, re.compile(r"executable,?\s+uncompressed\s+sec0|lies in the executable, uncompressed", re.I))}

    # va_class enrichment (H50): classify entry VA and concrete in-module hex VAs
    # surfaced as compressed/unmapped/M1.2f-related when image+module available.
    va_classifications = []
    va_class_status = "unavailable"
    if image and module:
        if _va_cache is None:
            _va_cache = {}
        rw = _default_resolve_with(image_start, resolve_with)
        sections, slots = _load_va_context(image, image_start, module, rw, _va_cache)
        if sections is None:
            va_class_status = "error"
            va_classifications = []
        else:
            va_class_status = "image"
            cand_text = _join_text(entry.get("reason"), entry.get("note"), target.get("notes"),
                                   target.get("what"), json.dumps(target.get("expect", {}), sort_keys=True))
            cand_vas = []
            if va is not None:
                cand_vas.append(va)
            # include entry VA reported as compressed/unmapped by va_section
            if va_info and va_info.get("section_realaddr") and va_info.get("compressed"):
                try:
                    cand_vas.append(int(str(va_info.get("va", "0")), 0))
                except Exception:
                    pass
            for v in va_class.extract_hex_vas(cand_text):
                cand_vas.append(v)
            va_classifications = _classify_vas_for_report(cand_vas, sections, slots)
            # Apply M1.2f verdict semantics per VA class (H50).
            init_rows = [r for r in va_classifications if r["cls"] == "INIT"]
            override_rows = [r for r in va_classifications if r["cls"] in ("IAT", "BSS")]
            if init_rows:
                m1_2f = _va_class_dim("INIT").copy()
                m1_2f["detail"] = "; ".join(f"{r['va']} {r['class_text']}" for r in init_rows)
                m1_2f["evidence"] = "va_class"
            elif override_rows:
                # Remove M1.2f/compressed-sec1 blocker for IAT/BSS VAs; replace with correct concern.
                if m1_2f.get("blocker") or m1_2f.get("status") == "present":
                    m1_2f = {"status": "not_m1_2f", "blocker": False,
                             "detail": "compressed/unmapped VAs are IAT/BSS, not INIT; M1.2f not required for them",
                             "evidence": "va_class"}
                else:
                    # keep non-blocking status but expose class-derived note
                    m1_2f = dict(m1_2f)
                    if m1_2f.get("status") == "unknown":
                        m1_2f["detail"] = "no INIT VA classified; compressed/unmapped concerns resolved to IAT/BSS where classified"
                        m1_2f["evidence"] = "va_class"
            # Compressed entry mapping: if image classifies as IAT/BSS, it is not an M1.2f byte blocker.
            if va_info and va_info.get("compressed"):
                entry_cls_row = next((r for r in va_classifications if r.get("va_int") == va), None)
                if entry_cls_row and entry_cls_row["cls"] in ("IAT", "BSS"):
                    # do not add "maps to a compressed section" as M1.2f blocker reason
                    pass
                elif entry_cls_row and entry_cls_row["cls"] == "INIT":
                    reasons.append(f"entry VA {hex(va)} is INIT in compressed section ({va_info.get('kind')}): needs M1.2f")
                elif not entry_cls_row or entry_cls_row.get("cls") == "UNKNOWN":
                    reasons.append(f"entry VA {hex(va)} maps to a compressed section ({va_info.get('kind')})")
            # Replace metadata "unmapped/compressed sec1" import-binding blocker with class concern when IAT/BSS known.
            ib = reach.get("import_binding")
            if ib and ib.get("status") == "blocked" and override_rows and not init_rows:
                # If blocked reason was about unmapped/compressed sec1 data/imports and all classified are IAT/BSS
                txt = (ib.get("detail") or "") + " " + _join_text(entry.get("reason"))
                if re.search(r"unmapped|compressed\s+sec1|m1\.2f", txt, re.I):
                    kinds = sorted({r["cls"] for r in override_rows})
                    concerns = []
                    if "IAT" in kinds:
                        iats = [r for r in override_rows if r["cls"] == "IAT"]
                        concerns.append("import/binding/stub needed: " + ", ".join(r["va"] + " " + r["class_text"] for r in iats))
                    if "BSS" in kinds:
                        bss = [r for r in override_rows if r["cls"] == "BSS"]
                        concerns.append("find writer/runtime init (zero at load): " + ", ".join(r["va"] + " " + r["class_text"] for r in bss))
                    reach = dict(reach)
                    reach["import_binding"] = {"status": "blocked", "detail": "; ".join(concerns) or "IAT/BSS concern (not M1.2f)"}
            elif ib and ib.get("status") == "blocked" and override_rows and init_rows:
                # Mixed: keep/adjust to mention INIT still M1.2f plus other concerns
                reach = dict(reach)
                concerns = [f"INIT (M1.2f): " + ", ".join(r["va"] + " " + r["class_text"] for r in init_rows)]
                if any(r["cls"] == "IAT" for r in override_rows):
                    concerns.append("IAT needs import/binding/stub: " + ", ".join(r["va"] + " " + r["class_text"] for r in override_rows if r["cls"]=="IAT"))
                if any(r["cls"] == "BSS" for r in override_rows):
                    concerns.append("BSS needs writer/runtime init: " + ", ".join(r["va"] + " " + r["class_text"] for r in override_rows if r["cls"]=="BSS"))
                reach["import_binding"] = {"status": "blocked", "detail": "; ".join(concerns)}
    elif image and not module:
        va_class_status = "no-module"
    else:
        va_class_status = "no-image"

    # Verdict.
    blockers = []
    unknowns = []
    if m1_2f.get("blocker"):
        blockers.append("M1.2f/compressed-sec1 data dependency: " + m1_2f.get("detail", "present"))
    for dim, info in reach.items():
        if info.get("status") == "blocked":
            blockers.append(f"{dim}: {info.get('detail')}")
        elif info.get("status") == "unknown":
            unknowns.append(f"{dim}: {info.get('detail')}")
            missing_fields.extend(info.get("missing_fields") or [])

    if kind == "synthetic":
        verdict = READY
        reasons.append("synthetic pipeline target; not a firmware reader precondition case (runner/dispatcher fixture)")
    elif blockers:
        verdict = BLOCKED
        reasons.extend(blockers)
        if unknowns:
            reasons.append("additional unknowns: " + "; ".join(unknowns))
    elif kind == "blocked":
        reason_text = entry.get("reason") or "entry.kind=blocked"
        verdict = BLOCKED
        reasons.append(f"target metadata marks entry blocked: {reason_text}")
    elif unknowns and not _has_sufficient_ready_facts(target, entry, reach, m1_2f):
        verdict = UNKNOWN
        reasons.extend(unknowns)
        reasons.append("insufficient stable metadata for READY; do not guess")
    else:
        verdict = READY
        reasons.append("no known M1.2f/import/input/binding blocker in checked metadata")
        if m1_2f.get("status") == "mitigated":
            reasons.append(m1_2f["detail"])
        if m1_2f.get("status") == "unknown" and va_class_status == "image":
            reasons.append(m1_2f.get("detail") or "M1.2f/sec1 dependency not stated in metadata (image-derived classes shown)")
        elif m1_2f.get("status") == "unknown":
            reasons.append("M1.2f/sec1 dependency not stated in metadata (image/code analysis not performed)")
        elif m1_2f.get("status") in ("iat", "bss", "not_m1_2f"):
            reasons.append(m1_2f.get("detail", ""))
        for dim, info in reach.items():
            if info.get("status") == "unknown":
                reasons.append(f"{dim}: {info['detail']}")

    # Add va_class concerns as explicit reasons (correct concern, not M1.2f) when classified.
    if va_classifications:
        for r in va_classifications:
            if r["cls"] == "IAT":
                reasons.append(f"VA {r['va']} {r['class_text']}: import/binding/stub concern (not M1.2f)")
            elif r["cls"] == "BSS":
                reasons.append(f"VA {r['va']} {r['class_text']}: find writer/runtime init (zero at load), not M1.2f")
            elif r["cls"] == "INIT":
                reasons.append(f"VA {r['va']} {r['class_text']}: M1.2f blocker")

    # Stable fields check for UNKNOWN stop condition.
    if verdict == UNKNOWN and not missing_fields:
        if not va_raw and kind != "synthetic":
            missing_fields.append("entry.va")
        if not module and kind not in ("synthetic",):
            missing_fields.append("module/entry.module")
        if kind not in ("synthetic", "blocked", "firmware_call"):
            missing_fields.append("entry.kind (stable)")
        if not missing_fields:
            missing_fields.append("sufficient reachability/dependency metadata")

    return {
        "name": name,
        "reader": target.get("reader"),
        "entry_kind": kind,
        "module": module,
        "va": va_raw,
        "executable_vs_data_bytes": bytes_info,
        "compressed_sec1_data_dependency_m1_2f": m1_2f,
        "import_input_binding_reachability": reach,
        "va_classifications": va_classifications,
        "va_class_status": va_class_status,
        "verdict": verdict,
        "reasons": reasons,
        "missing_fields": missing_fields if verdict == UNKNOWN else [],
        "image_used": os.path.basename(image) if image else None,
    }


def _has_sufficient_ready_facts(target: dict, entry: dict, reach: dict, m1_2f: dict) -> bool:
    kind = entry.get("kind")
    if kind == "firmware_call" and entry.get("va") and (entry.get("module") or target.get("module")):
        # Need entry mapping known and no blocker; input/import may be "known enough" for firmware_call.
        em = reach.get("entry_mapping", {}).get("status")
        ib = reach.get("import_binding", {}).get("status")
        inp = reach.get("input_binding", {}).get("status")
        return em == "known" and ib in ("known", "unknown") and inp in ("known", "unknown") and not m1_2f.get("blocker")
    return False


# ---------------------------------------------------------------------------
# Ad-hoc VA/module assessment
# ---------------------------------------------------------------------------


def assess_adhoc(*, va: int | None, module: str | None, image: str | None = None,
                 image_start: int = 0x200200, resolve_with: list[int] | None = None,
                 _va_cache: dict | None = None) -> dict:
    reasons = []
    missing_fields = []
    bytes_info: dict[str, Any] = {"status": "unknown", "detail": "no image provided"}
    reach = {
        "entry_mapping": {"status": "unknown", "detail": "ad-hoc check", "missing_fields": []},
        "import_binding": {"status": "unknown", "detail": "no import/binding metadata provided"},
        "input_binding": {"status": "unknown", "detail": "no input/binding metadata provided"},
    }
    m1_2f = {"status": "unknown", "blocker": False, "detail": "ad-hoc check: no target metadata; M1.2f dependency not assessed", "evidence": None}
    va_classifications = []
    va_class_status = "no-image" if not image else ("no-module" if not module else "unavailable")
    if va is None:
        missing_fields.append("va")
    if not module:
        missing_fields.append("module")
    if va is not None and module:
        reach["entry_mapping"] = {"status": "known", "detail": f"VA {hex(va)} / module {module} supplied"}
    if image and module:
        rep = _module_bytes_report(image, image_start, module)
        if rep and "error" not in rep:
            bytes_info = rep
        elif rep:
            bytes_info = {"status": "unknown", "detail": rep["error"]}
    va_info = None
    if image and module and va is not None:
        va_info = _va_section_report(image, image_start, module, va)
        if _va_cache is None:
            _va_cache = {}
        rw = _default_resolve_with(image_start, resolve_with)
        sections, slots = _load_va_context(image, image_start, module, rw, _va_cache)
        if sections is not None:
            va_class_status = "image"
            va_classifications = _classify_vas_for_report([va], sections, slots)
            row = va_classifications[0] if va_classifications else None
            if row and row["cls"] == "INIT":
                m1_2f = _va_class_dim("INIT").copy()
                m1_2f["detail"] = f"{row['va']} {row['class_text']}"
                verdict = BLOCKED
                reasons.append(f"VA {hex(va)} is INIT in compressed section: M1.2f blocker")
                reach = dict(reach)
                reach["import_binding"] = {"status": "blocked", "detail": "INIT bytes need M1.2f (compressed .data)"}
                return {
                    "name": None, "reader": None, "entry_kind": "adhoc", "module": module, "va": hex(va),
                    "executable_vs_data_bytes": bytes_info, "va_section": va_info,
                    "compressed_sec1_data_dependency_m1_2f": m1_2f,
                    "import_input_binding_reachability": reach,
                    "va_classifications": va_classifications, "va_class_status": va_class_status,
                    "verdict": verdict, "reasons": reasons, "missing_fields": [], "image_used": os.path.basename(image),
                }
            if row and row["cls"] == "IAT":
                m1_2f = {"status": "iat", "blocker": False, "detail": f"{row['va']} {row['class_text']}: not M1.2f", "evidence": "va_class"}
                reach = dict(reach)
                reach["import_binding"] = {"status": "blocked", "detail": f"import/binding/stub needed: {row['va']} {row['class_text']} (not M1.2f)"}
                reasons.append(f"VA {hex(va)} {row['class_text']}: import/binding/stub concern (not M1.2f)")
                verdict = BLOCKED
                return {
                    "name": None, "reader": None, "entry_kind": "adhoc", "module": module, "va": hex(va),
                    "executable_vs_data_bytes": bytes_info, "va_section": va_info,
                    "compressed_sec1_data_dependency_m1_2f": m1_2f,
                    "import_input_binding_reachability": reach,
                    "va_classifications": va_classifications, "va_class_status": va_class_status,
                    "verdict": verdict, "reasons": reasons, "missing_fields": [], "image_used": os.path.basename(image),
                }
            if row and row["cls"] == "BSS":
                m1_2f = {"status": "bss", "blocker": False, "detail": f"{row['va']} {row['class_text']}: not M1.2f", "evidence": "va_class"}
                reach = dict(reach)
                reach["import_binding"] = {"status": "blocked", "detail": f"find writer/runtime init (zero at load): {row['va']} {row['class_text']} (not M1.2f)"}
                reasons.append(f"VA {hex(va)} {row['class_text']}: find writer/runtime init (zero at load), not M1.2f")
                verdict = BLOCKED
                return {
                    "name": None, "reader": None, "entry_kind": "adhoc", "module": module, "va": hex(va),
                    "executable_vs_data_bytes": bytes_info, "va_section": va_info,
                    "compressed_sec1_data_dependency_m1_2f": m1_2f,
                    "import_input_binding_reachability": reach,
                    "va_classifications": va_classifications, "va_class_status": va_class_status,
                    "verdict": verdict, "reasons": reasons, "missing_fields": [], "image_used": os.path.basename(image),
                }
        else:
            va_class_status = "error"
        if va_info and va_info.get("section_realaddr") and va_info.get("compressed") and not va_classifications:
            verdict = BLOCKED
            reasons.append(f"VA {hex(va)} is in compressed section {va_info.get('kind')}; class unknown without va_class context")
            m1_2f = {"status": "unknown", "blocker": True, "detail": reasons[0], "evidence": va_info}
            return {
                "name": None, "reader": None, "entry_kind": "adhoc", "module": module, "va": hex(va),
                "executable_vs_data_bytes": bytes_info, "va_section": va_info,
                "compressed_sec1_data_dependency_m1_2f": m1_2f,
                "import_input_binding_reachability": reach,
                "va_classifications": va_classifications, "va_class_status": va_class_status,
                "verdict": verdict, "reasons": reasons, "missing_fields": [], "image_used": os.path.basename(image),
            }
        if va_info and va_info.get("section_realaddr") and not va_info.get("compressed"):
            reasons.append(f"VA {hex(va)} is in {va_info.get('kind')} section (image-verified)")
    if missing_fields:
        return {
            "name": None, "reader": None, "entry_kind": "adhoc", "module": module,
            "va": hex(va) if va is not None else None,
            "executable_vs_data_bytes": bytes_info,
            "compressed_sec1_data_dependency_m1_2f": m1_2f,
            "import_input_binding_reachability": reach,
            "va_classifications": va_classifications, "va_class_status": va_class_status,
            "verdict": UNKNOWN,
            "reasons": ["ad-hoc assessment requires stable VA/module context; do not guess READY"],
            "missing_fields": missing_fields,
            "image_used": os.path.basename(image) if image else None,
        }
    verdict = UNKNOWN
    reasons.append("ad-hoc VA/module supplied but target metadata absent; import/input/binding and M1.2f data dependencies cannot be proven from VA alone")
    if va_info and va_info.get("section_realaddr") and not va_info.get("compressed"):
        reasons.append(f"entry bytes are {va_info.get('kind')} (necessary, not sufficient)")
    return {
        "name": None, "reader": None, "entry_kind": "adhoc", "module": module, "va": hex(va),
        "executable_vs_data_bytes": bytes_info, "va_section": va_info,
        "compressed_sec1_data_dependency_m1_2f": m1_2f,
        "import_input_binding_reachability": reach,
        "va_classifications": va_classifications, "va_class_status": va_class_status,
        "verdict": verdict, "reasons": reasons,
        "missing_fields": ["target metadata (entry kind, imports/bindings, declared inputs, known blockers)"],
        "image_used": os.path.basename(image) if image else None,
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _print_report(reports: list[dict], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps({"schema": "osm2leaf.l3_precond/v1", "targets": reports}, indent=2, sort_keys=False))
        return
    for rep in reports:
        label = rep.get("name") or f"adhoc {rep.get('va')} {rep.get('module')}"
        print(f"== {label} ==")
        print(f"verdict: {rep['verdict']}")
        print(f"reader: {rep.get('reader')}  entry_kind: {rep.get('entry_kind')}  module: {rep.get('module')}  va: {rep.get('va')}")
        b = rep.get("executable_vs_data_bytes") or {}
        if b.get("exec_decodable_bytes") is not None:
            print(f"bytes: exec_decodable={b['exec_decodable_bytes']} exec_compressed={b['exec_compressed_bytes']} "
                  f"data_decodable={b['data_decodable_bytes']} data_compressed={b['data_compressed_bytes']} (source={b.get('source')})")
        else:
            print(f"bytes: {b.get('status','unknown')} - {b.get('detail','')}")
        m = rep.get("compressed_sec1_data_dependency_m1_2f") or {}
        print(f"M1.2f/sec1-data: {m.get('status')} blocker={m.get('blocker')} - {m.get('detail')}")
        for dim, info in (rep.get("import_input_binding_reachability") or {}).items():
            print(f"reachability.{dim}: {info.get('status')} - {info.get('detail')}")
        vcs = rep.get("va_classifications") or []
        if vcs or rep.get("va_class_status") in ("image", "error"):
            print(f"va_class: status={rep.get('va_class_status','unknown')} ({len(vcs)} classified)")
        for vc in vcs:
            print(f"  va_class.{vc['va']}: {vc.get('class_text') or vc.get('cls')} - {vc.get('detail','')}")
        for r in rep.get("reasons") or []:
            print(f"  reason: {r}")
        if rep.get("missing_fields"):
            print(f"  missing_fields: {', '.join(rep['missing_fields'])}")
        print()


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def run_selftest() -> int:
    failures = []

    def check(name: str, cond: bool, detail: str = ""):
        if cond:
            print(f"PASS: {name}")
        else:
            failures.append((name, detail))
            print(f"FAIL: {name}{': ' + detail if detail else ''}")

    # Synthetic targets (no vendor data).
    t_blocked_m1_2f = {
        "name": "syn-drstr", "reader": "drstr", "module": "Navi.exe",
        "entry": {"kind": "blocked", "va": "0x00419350", "module": "Navi.exe",
                  "reason": "entry VA in executable uncompressed sec0, but coredll imports and buffer global sit in compressed sec1 (0x0055d000): the first read, 0x0055d8fc, is UNMAPPED; unblock: M1.2f, then M9.24"},
        "stubs": ["fopen"],
    }
    r = assess_target(t_blocked_m1_2f)
    check("blocked M1.2f -> BLOCKED", r["verdict"] == BLOCKED, r["verdict"])
    check("blocked M1.2f reports M1.2f", r["compressed_sec1_data_dependency_m1_2f"]["status"] == "present"
          or "M1.2f" in " ".join(r["reasons"]), json.dumps(r["compressed_sec1_data_dependency_m1_2f"]))
    check("blocked M1.2f has reasons", bool(r["reasons"]))

    t_missing = {
        "name": "syn-tile", "reader": "tile", "module": None,
        "entry": {"kind": "blocked", "program": None, "va": None,
                  "reason": "no tile reader entry point has been recovered (M3)"},
    }
    r = assess_target(t_missing)
    check("missing mapping -> BLOCKED", r["verdict"] == BLOCKED, r["verdict"])
    check("missing mapping reason mentions entry/mapping",
          any("entry" in x.lower() or "mapping" in x.lower() or "recovered" in x.lower() or "blocked" in x.lower() for x in r["reasons"]),
          str(r["reasons"]))

    t_firmware = {
        "name": "syn-cmp", "reader": "cmp_ind", "module": "Navi.exe",
        "entry": {"kind": "firmware_call", "program": "x", "va": "0x0041c7e8", "module": "Navi.exe",
                  "sec1_table": {"va": "0x00574de0", "values": ["0x0"], "provenance": "values from public source, not read from Navi.exe sec1 (M1.2f open); declared input"},
                  "inputs": {"offset": "0x1", "length": 1}},
        "corpus": {"path": "x.cmp"},
        "stubs": [],
    }
    r = assess_target(t_firmware)
    check("firmware_call with declared input -> READY", r["verdict"] == READY, f"{r['verdict']} {r['reasons']}")
    check("firmware_call reports mitigated/declared sec1",
          r["compressed_sec1_data_dependency_m1_2f"]["status"] in ("mitigated", "present", "unknown")
          and any("declared" in x.lower() or "sec1" in x.lower() or "M1.2f" in x for x in r["reasons"] + [r["compressed_sec1_data_dependency_m1_2f"]["detail"]]),
          json.dumps(r["compressed_sec1_data_dependency_m1_2f"]))

    t_synth = {
        "name": "syn-probe", "reader": "synthetic", "module": None,
        "entry": {"kind": "synthetic", "program": "p", "va": "0x8c100000"},
        "stubs": [{"id": "s"}], "corpus": {"path": "a"},
    }
    r = assess_target(t_synth)
    check("synthetic -> READY", r["verdict"] == READY, r["verdict"])

    # Ad-hoc missing fields -> UNKNOWN.
    r = assess_adhoc(va=None, module=None)
    check("adhoc missing fields -> UNKNOWN", r["verdict"] == UNKNOWN, r["verdict"])
    check("adhoc UNKNOWN lists missing fields", bool(r["missing_fields"]), str(r))

    r = assess_adhoc(va=0x1234, module="Navi.exe")
    check("adhoc VA+module without metadata -> UNKNOWN", r["verdict"] == UNKNOWN, r["verdict"])
    check("adhoc UNKNOWN does not guess READY", r["verdict"] != READY, r["verdict"])

    # Real targets.json load + assessment (metadata only, no image required).
    try:
        by_name, _doc = load_targets()
        loaded = True
    except Exception as exc:  # noqa: BLE001
        loaded = False
        check("load real targets.json", False, str(exc))
    if loaded:
        check("targets.json has expected targets", "cmp_ind_reader" in by_name and "drstr_parser" in by_name)
        r_cmp = assess_target(by_name["cmp_ind_reader"])
        check("real cmp_ind_reader -> READY (baseline-known)", r_cmp["verdict"] == READY,
              f"{r_cmp['verdict']} reasons={r_cmp['reasons']}")
        r_drs = assess_target(by_name["drstr_parser"])
        check("real drstr_parser -> BLOCKED (M1.2f/missing compressed sec1 reachability)", r_drs["verdict"] == BLOCKED,
              f"{r_drs['verdict']} reasons={r_drs['reasons']}")
        check("real drstr_parser mentions M1.2f or compressed sec1 or unmapped",
              any(("m1.2f" in x.lower()) or ("compressed sec1" in x.lower()) or ("sec1" in x.lower()) or ("unmapped" in x.lower())
                  for x in r_drs["reasons"] + [r_drs["compressed_sec1_data_dependency_m1_2f"].get("detail", "")]),
              str(r_drs["reasons"]))
        # A target with no VA / missing mapping.
        for name in ("tile_reader", "hddinfo_compare"):
            if name in by_name:
                rr = assess_target(by_name[name])
                check(f"real {name} -> BLOCKED", rr["verdict"] == BLOCKED, f"{rr['verdict']} {rr['reasons']}")

    # JSON output shape.
    r = assess_target(t_missing)
    blob = json.dumps({"schema": "osm2leaf.l3_precond/v1", "targets": [r]})
    parsed = json.loads(blob)
    check("JSON round-trips", parsed["targets"][0]["verdict"] == BLOCKED)

    # H50: IAT/BSS/INIT va_class cases (synthetic context, no vendor data).
    sec_plain = dict(index=0, start=0x00011000, vsize=0x1000, psize=0x1000, flags=0x60000020,
                     compressed=False, exec=True, init_len=0x1000)
    sec_comp = dict(index=1, start=0x0055d000, vsize=0x10000, psize=0x200, flags=0xc8002040,
                    compressed=True, exec=False, init_len=0x1000)
    syn_sections = [sec_plain, sec_comp]
    syn_slots = {0x0055d040: ("COREDLL", "memset")}
    # (0x0055e000 -> BSS >= init 0x1000, 0x0055d100 -> INIT < init 0x1000, not slot)

    orig_load = globals().get("_load_va_context")
    orig_mod = globals().get("_module_bytes_report")
    orig_va = globals().get("_va_section_report")
    def _fake_load(image, image_start, module, resolve_with, cache):
        return syn_sections, syn_slots
    def _fake_mod(image, image_start, module):
        return {"module": module, "exec_decodable_bytes": 0x1000, "exec_compressed_bytes": 0,
                "data_decodable_bytes": 0, "data_compressed_bytes": 0x10000,
                "exec_compressed_sections": [], "source": "synthetic"}
    def _fake_va(image, image_start, module, va):
        if 0x0055d000 <= va < 0x0056d000:
            return {"va": hex(va), "module": module, "section_index": 1,
                    "section_realaddr": "0x0055d000", "compressed": True,
                    "executable": False, "kind": "data-compressed"}
        if 0x00011000 <= va < 0x00012000:
            return {"va": hex(va), "module": module, "section_index": 0,
                    "section_realaddr": "0x00011000", "compressed": False,
                    "executable": True, "kind": "exec-plain"}
        return {"va": hex(va), "module": module, "section": None, "detail": "not found"}
    globals()["_load_va_context"] = _fake_load
    globals()["_module_bytes_report"] = _fake_mod
    globals()["_va_section_report"] = _fake_va
    try:
        # IAT: blocked by metadata M1.2f in target text but va_class says IAT -> not M1.2f-blocked.
        t_iat = {"name": "syn-iat", "reader": "iat", "module": "Navi.exe",
                 "entry": {"kind": "firmware_call", "va": "0x00011010", "module": "Navi.exe",
                           "reason": "accesses 0x0055d040 in compressed sec1 (M1.2f) UNMAPPED"}}
        ri = assess_target(t_iat, image="synthetic.img", image_start=0x200200)
        check("IAT va_class present", any(v.get("cls") == "IAT" for v in ri.get("va_classifications", [])),
              json.dumps(ri.get("va_classifications")))
        check("IAT not M1.2f-blocked", not ri["compressed_sec1_data_dependency_m1_2f"].get("blocker"),
              json.dumps(ri["compressed_sec1_data_dependency_m1_2f"]))
        check("IAT reason/concern shown", any("IAT" in x and ("import" in x.lower() or "stub" in x.lower() or "not M1.2f" in x)
              for x in ri.get("reasons", [])) or any(v.get("cls")=="IAT" for v in ri.get("va_classifications", [])),
              str(ri.get("reasons")))
        # overall verdict may still be BLOCKED for independent reasons? this case had metadata blocked entry? no, firmware_call
        # but import_binding may become blocked concern (not M1.2f) -> overall can be BLOCKED, which is correct (independent concern).

        # BSS
        t_bss = {"name": "syn-bss", "reader": "bss", "module": "Navi.exe",
                 "entry": {"kind": "firmware_call", "va": "0x00011010", "module": "Navi.exe",
                           "reason": "reads table at 0x0055e000 in compressed sec1 (M1.2f) UNMAPPED"}}
        rb = assess_target(t_bss, image="synthetic.img", image_start=0x200200)
        check("BSS va_class present", any(v.get("cls") == "BSS" for v in rb.get("va_classifications", [])),
              json.dumps(rb.get("va_classifications")))
        check("BSS not M1.2f-blocked", not rb["compressed_sec1_data_dependency_m1_2f"].get("blocker"),
              json.dumps(rb["compressed_sec1_data_dependency_m1_2f"]))
        check("BSS reason/concern shown", any("BSS" in x and ("writer" in x.lower() or "zero" in x.lower() or "not M1.2f" in x)
              for x in rb.get("reasons", [])), str(rb.get("reasons")))

        # INIT
        t_init = {"name": "syn-init", "reader": "init", "module": "Navi.exe",
                  "entry": {"kind": "firmware_call", "va": "0x00011010", "module": "Navi.exe",
                            "reason": "reads 0x0055d100 in compressed sec1 (M1.2f)"}}
        rn = assess_target(t_init, image="synthetic.img", image_start=0x200200)
        check("INIT va_class present", any(v.get("cls") == "INIT" for v in rn.get("va_classifications", [])),
              json.dumps(rn.get("va_classifications")))
        check("INIT M1.2f-blocked", rn["compressed_sec1_data_dependency_m1_2f"].get("blocker") is True,
              json.dumps(rn["compressed_sec1_data_dependency_m1_2f"]))
        check("INIT verdict BLOCKED", rn["verdict"] == BLOCKED, rn["verdict"])

        # adhoc IAT/BSS/INIT
        ra_iat = assess_adhoc(va=0x0055d040, module="Navi.exe", image="synthetic.img")
        check("adhoc IAT not M1.2f-blocked", not ra_iat["compressed_sec1_data_dependency_m1_2f"].get("blocker"),
              json.dumps(ra_iat["compressed_sec1_data_dependency_m1_2f"]))
        check("adhoc IAT classified", any(v.get("cls")=="IAT" for v in ra_iat.get("va_classifications", [])))
        ra_bss = assess_adhoc(va=0x0055e000, module="Navi.exe", image="synthetic.img")
        check("adhoc BSS not M1.2f-blocked", not ra_bss["compressed_sec1_data_dependency_m1_2f"].get("blocker"),
              json.dumps(ra_bss["compressed_sec1_data_dependency_m1_2f"]))
        check("adhoc BSS classified", any(v.get("cls")=="BSS" for v in ra_bss.get("va_classifications", [])))
        ra_init = assess_adhoc(va=0x0055d100, module="Navi.exe", image="synthetic.img")
        check("adhoc INIT M1.2f-blocked", ra_init["compressed_sec1_data_dependency_m1_2f"].get("blocker") is True,
              json.dumps(ra_init["compressed_sec1_data_dependency_m1_2f"]))
        check("adhoc classes in JSON", "va_classifications" in ra_iat and "class_text" in (ra_iat.get("va_classifications") or [{}])[0])

        # no-image honesty
        rn_no = assess_adhoc(va=0x0055d100, module="Navi.exe", image=None)
        check("no-image not guessed non-M1.2f READY", rn_no["verdict"] != READY and rn_no["va_class_status"] == "no-image", str(rn_no))
    finally:
        globals()["_load_va_context"] = orig_load
        globals()["_module_bytes_report"] = orig_mod
        globals()["_va_section_report"] = orig_va

    if failures:
        print(f"\n{len(failures)} FAILED:")
        for name, detail in failures:
            print(f"  - {name}: {detail}")
        return 1
    print("\nAll selftest checks passed.")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--selftest", action="store_true", help="run synthetic/metadata self-tests and exit")
    p.add_argument("--target", action="append", dest="targets", metavar="NAME", help="target name from targets.json (repeatable)")
    p.add_argument("--all-targets", action="store_true", help="assess every target in targets.json")
    p.add_argument("--targets", dest="targets_path", default=None, help=f"path to targets.json (default: {DEFAULT_TARGETS})")
    p.add_argument("--va", type=lambda s: int(s, 0), default=None, help="ad-hoc reader/entry VA")
    p.add_argument("--module", default=None, help="module name (with --va or to scope enrichment)")
    p.add_argument("--image", default=None, help="optional firmware image for byte/section enrichment")
    p.add_argument("--image-start", type=lambda s: int(s, 0), default=0x200200)
    p.add_argument("--resolve-with", action="append", type=lambda s: int(s, 0), default=None,
                   help="CE image start(s) whose exports resolve ordinal imports for va_class (repeatable; default 0x3e00200 for build-A)")
    p.add_argument("--json", action="store_true", dest="as_json", help="JSON output")
    args = p.parse_args(argv)

    if args.selftest:
        return run_selftest()

    image = args.image or (os.environ.get("OSM2LEAF_IMG") if not (args.targets or args.all_targets or args.va) else None)
    if image and not os.path.isfile(image):
        # For metadata-only checks, a missing image is fine; warn in JSON by omission.
        image = None
    elif image is None and (args.va or args.module) and os.environ.get("OSM2LEAF_IMG"):
        cand = os.environ.get("OSM2LEAF_IMG")
        if cand and os.path.isfile(cand):
            image = cand

    reports = []
    va_cache: dict = {}
    resolve_with = args.resolve_with
    if args.targets or args.all_targets:
        try:
            by_name, _doc = load_targets(args.targets_path)
        except PrecondError as exc:
            print(f"l3_precond: {exc}", file=sys.stderr)
            return 2
        names = list(by_name.keys()) if args.all_targets else args.targets
        for name in names:
            if name not in by_name:
                print(f"l3_precond: unknown target {name!r}", file=sys.stderr)
                return 2
            reports.append(assess_target(by_name[name], image=image, image_start=args.image_start,
                                         resolve_with=resolve_with, _va_cache=va_cache))
    elif args.va is not None or args.module is not None:
        reports.append(assess_adhoc(va=args.va, module=args.module, image=image, image_start=args.image_start,
                                    resolve_with=resolve_with, _va_cache=va_cache))
    else:
        p.error("give --selftest, --target/--all-targets, or --va/--module")

    _print_report(reports, as_json=args.as_json)
    # Exit 0 for a report (verdicts are in output); 2 was usage; selftest uses 0/1.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
