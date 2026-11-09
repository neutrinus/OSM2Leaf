#!/usr/bin/env python3
"""Versioned schema contract for progress_report inputs/outputs (H47).

Extends H27's ``osm2leaf.progress_report/v2`` contract to accept H41 per-file/
per-feature generated-fixture matrices and H43 generated-corpus L3 evidence
without guessing unfinished key names.

Design (H47 stop condition honored): H41/H43 final keys were not fixed when
this landed, so the contract is versioned, tolerant of unknown keys, and marks
H41/H43-specific fields as provisional/TBD in the EXP where needed. Producers
may include extra fields; consumers must ignore unknown keys.

Schemas
-------
Output: ``osm2leaf.progress_report/v3`` (adds ``l1l2_matrix``, richer ``l3``
corpus classification; keeps all v2/v1-compatible top-level fields).
Legacy output schemas remain documented as ``schema_legacy_chain``.

Accepted L1/L2 inputs (auto-detected, unknown-key tolerant):
- Legacy H26 ``l1l2_fixtures``: ``{summary, checks:[...]}``
- H41 matrix (provisional): ``{schema: osm2leaf.l1l2_matrix/*, rows:[...]}
  or {matrix:[...]} or {checks:[{level,file,feature,status,...}]}``
  Row keys (H41 spec): ``level,file,feature,status,command,reason``.
  Statuses: PASS|FAIL|SKIP|NOT_COVERED|NOT_RUNNABLE.

Accepted L3 inputs (auto-detected, unknown-key tolerant):
- Legacy l3check: ``osm2leaf.l3check/v1`` ``{targets:[...], counts,...}``
- H43 corpus-aware (provisional): l3check-like with optional per-target/entry
  fields ``ran_on_our_generated_data``, ``corpus_kind``, ``corpus``,
  ``evidence_kind``.  Corpus kinds normalized to:
  ``synthetic|vendor|factory|generated_fixture|unknown``.
  Evidence kinds normalized to: ``firmware_proof|harness_only|unknown``.

Rule 13 / L1-L5 (2026-11-09 mapping):
- L1/L2 generated-fixture matrix is offline evidence only.
- L3 firmware proof requires explicit non-synthetic ``l3_claim`` PASS (or an
  explicit ``firmware_proof`` marker on a non-synthetic target). Generated-
  fixture corpus runs are reported separately and are never promoted to
  firmware proof unless explicitly marked.
- L4 emulator (M8) and L5 bench/car (M6) remain explicit manual states;
  PASS requires recorded evidence and is never auto-assigned.
"""
from __future__ import annotations

from typing import Any

SCHEMA_V3 = "osm2leaf.progress_report/v3"
SCHEMA_V2 = "osm2leaf.progress_report/v2"
SCHEMA_V1 = "osm2leaf.progress_report/v1"
SCHEMA_L1L2_LEGACY = "osm2leaf.l1l2_fixtures/* (H26)"
SCHEMA_L1L2_MATRIX = "osm2leaf.l1l2_matrix/* (H41 provisional, H47 contract)"
SCHEMA_L3_LEGACY = "osm2leaf.l3check/v1"
SCHEMA_L3_CORPUS = "osm2leaf.l3_corpus/* (H43 provisional, H47 contract)"

L1L2_STATUSES = ("PASS", "FAIL", "SKIP", "NOT_COVERED", "NOT_RUNNABLE")
CORPUS_KINDS = ("synthetic", "vendor", "factory", "generated_fixture", "unknown")
EVIDENCE_KINDS = ("firmware_proof", "harness_only", "unknown")

# H41 stable keys from TODO spec; unknown keys are preserved/tolerated.
H41_ROW_KEYS = ("level", "file", "feature", "status", "command", "reason")
# H43 fields named in TODO spec / H47 scope; provisional.
H43_TARGET_KEYS = ("ran_on_our_generated_data", "corpus_kind", "corpus",
                   "status", "synthetic", "l3_claim", "reason", "evidence_kind")

CONTRACT = {
    "schema": SCHEMA_V3,
    "schema_legacy_chain": [SCHEMA_V2, SCHEMA_V1],
    "backward_compatible": True,
    "auto_detect": True,
    "unknown_keys": "tolerated (preserved where practical; ignored by aggregators)",
    "level_mapping_effective": "2026-11-09",
    "l1l2_legacy_input": {
        "flags": ["--l1l2-json"],
        "detect": "object with summary/checks and no matrix rows",
        "schema": SCHEMA_L1L2_LEGACY,
    },
    "l1l2_matrix_input": {
        "flags": ["--l1l2-json", "--l1l2-matrix-json"],
        "detect": "object with rows/matrix, or schema contains l1l2_matrix, or checks have level+file+feature",
        "row_keys_required": ["status"],
        "row_keys_h41_stable": list(H41_ROW_KEYS),
        "statuses": list(L1L2_STATUSES),
        "schema": SCHEMA_L1L2_MATRIX,
    },
    "l3_legacy_input": {
        "flags": ["--l3-json"],
        "detect": "targets/counts, no corpus classification fields",
        "schema": SCHEMA_L3_LEGACY,
    },
    "l3_corpus_input": {
        "flags": ["--l3-json", "--l3-corpus-json"],
        "detect": "targets/entries contain ran_on_our_generated_data/corpus_kind/corpus/evidence_kind, or schema contains l3_corpus",
        "target_keys_h43_provisional": list(H43_TARGET_KEYS),
        "corpus_kinds": list(CORPUS_KINDS),
        "evidence_kinds": list(EVIDENCE_KINDS),
        "schema": SCHEMA_L3_CORPUS,
    },
    "manual_layers": {
        "L4": {"flag": "--l4-emulator-status", "auto_pass": False, "evidence_required_for_pass": True},
        "L5": {"flags": ["--l5-status", "--l4-status (v1 compat alias)"], "auto_pass": False, "evidence_required_for_pass": True},
    },
}


def normalize_status(value: Any, allowed: tuple[str, ...] = L1L2_STATUSES) -> str:
    s = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    aliases = {
        "NOTCOVERED": "NOT_COVERED",
        "NOT_COVERED": "NOT_COVERED",
        "NOTRUNNABLE": "NOT_RUNNABLE",
        "NOT_RUNNABLE": "NOT_RUNNABLE",
        "NOT_RUN": "NOT_RUNNABLE",  # manual layers use NOT RUN separately
    }
    s = aliases.get(s, s)
    return s if s in allowed else "UNKNOWN"


def normalize_corpus_kind(value: Any, *, synthetic: bool = False,
                         ran_on_generated: Any = None) -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "synthetic": "synthetic",
        "probe": "synthetic",
        "vendor": "vendor",
        "vendor_factory": "vendor",
        "factory": "factory",
        "stock": "factory",
        "generated": "generated_fixture",
        "generated_fixture": "generated_fixture",
        "generated_data": "generated_fixture",
        "our_generated": "generated_fixture",
        "our_generated_data": "generated_fixture",
        "h40": "generated_fixture",
    }
    if raw in mapping:
        return mapping[raw]
    if ran_on_generated is True or str(ran_on_generated).lower() == "true":
        return "generated_fixture"
    if synthetic:
        return "synthetic"
    return "unknown"


def normalize_evidence_kind(value: Any, *, firmware_proof: bool = False,
                            l3_claim: bool = False, synthetic: bool = False,
                            status: str = "") -> str:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    mapping = {
        "firmware_proof": "firmware_proof",
        "firmware": "firmware_proof",
        "l3_firmware": "firmware_proof",
        "harness_only": "harness_only",
        "harness": "harness_only",
        "synthetic_probe": "harness_only",
        "synthetic": "harness_only",
        "offline": "harness_only",
    }
    if raw in mapping:
        kind = mapping[raw]
    elif firmware_proof or (status == "PASS" and l3_claim and not synthetic):
        kind = "firmware_proof"
    else:
        kind = "unknown"
    # Rule 13: never promote synthetic/harness to firmware proof.
    if synthetic and kind == "firmware_proof":
        return "harness_only"
    return kind
