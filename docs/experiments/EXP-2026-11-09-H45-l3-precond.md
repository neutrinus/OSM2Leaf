# EXP-2026-11-09-H45-l3-precond: L3 reader-rerun reachability precondition gate

- **Status:** done
- **Date:** 2026-11-09
- **Sample:** `none (tool-only task)` — verdicts are computed from
  `tools/l3_harness/targets.json` metadata and optional image enrichment; no
  vendor bytes committed.
- **Tools:** `python3` (repo runtime) / stdlib; repo tools `tools/l3_precond.py`
  (new), reads `tools/l3_harness/targets.json`; optional image enrichment uses
  `tools/point_walk_l3.py`/`tools/cerom.py` when an image is supplied.
- **Claims:** C-3330, C-3331, C-3332, C-3333
- **Supersedes:** none
- **Superseded by:** none

## Question

Before a reopened L3 reader rerun is claimed, can the M1.2f + import/input/
binding preconditions be made explicit and machine-checkable from target
metadata (and optional image facts), producing a `READY|BLOCKED|UNKNOWN`
verdict with reasons without executing firmware?

## Hypothesis

`tools/l3_precond.py` can classify real target definitions into expected
precondition verdicts: a runnable/baseline-known firmware target with declared
inputs as `READY` (with caveats where M1.2f byte verification is open but
mitigated by declared input), and a target known blocked on M1.2f/missing
compressed-sec1 reachability as `BLOCKED` with reasons. `UNKNOWN` must be
reported (never guessed as `READY`) when stable VA/section/metadata fields are
insufficient.

**Falsifier:** the tool reports `READY` for `drstr_parser` (known M1.2f +
compressed-sec1 import/buffer blocker per `targets.json` /
EXP-2026-11-08-M9.14-reopen), or reports `BLOCKED` for `cmp_ind_reader` in a
way that contradicts its runnable/baseline-known status without a metadata
blocker, or reports `READY` for an ad-hoc/metadata-insufficient case.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none required; optional firmware image for byte/section enrichment |
| SHA-256 | n/a |
| Offset(s) / VA(s) | from `tools/l3_harness/targets.json` (e.g. `cmp_ind_reader` 0x0041c7e8, `drstr_parser` metadata mentions 0x00419350) |
| Tool / version | Python 3 stdlib |
| Repo tool | `tools/l3_precond.py` |

## Method

1. **Sample and hash.** No vendor sample; tool-only. Real target definitions are
   the committed `tools/l3_harness/targets.json` entries.
2. **Commands.** Runnable as written from the repository root:
   ```bash
   python3 tools/l3_precond.py --selftest
   python3 tools/l3_precond.py --target cmp_ind_reader --target drstr_parser --json
   python3 tools/l3_precond.py --all-targets
   ```
3. **Controls.** *Positive (synthetic/metadata):* a synthetic `firmware_call`
   target with declared `sec1_table` input and entry VA/module is assessed
   `READY`; a synthetic pipeline target is `READY`. *Negative/blocking:* a
   synthetic blocked target whose reason states M1.2f/compressed sec1 imports/
   buffer/unmapped access is `BLOCKED` with M1.2f reasons; a target with no
   entry VA/missing mapping is `BLOCKED`; an ad-hoc check missing VA/module or
   lacking target metadata is `UNKNOWN` and never `READY`.
4. **Scope.** Metadata classification covers all entries in
   `tools/l3_harness/targets.json` (6 targets at time of writing: `probe-zlib-cmf`,
   `hddinfo_compare`, `cmp_ind_reader`, `tile_reader`, `drstr_parser`,
   `mapcode_comparator`). Byte/section enrichment is image-dependent and not
   required by `--selftest`; no firmware execution performed.
5. **Falsifier.** `drstr_parser` assessed `READY`; `cmp_ind_reader` assessed
   `BLOCKED` absent a real metadata blocker; or any metadata-insufficient case
   assessed `READY`.

## Observations

`--selftest` output (all passed):

```text
PASS: blocked M1.2f -> BLOCKED
PASS: blocked M1.2f reports M1.2f
PASS: blocked M1.2f has reasons
PASS: missing mapping -> BLOCKED
PASS: missing mapping reason mentions entry/mapping
PASS: firmware_call with declared input -> READY
PASS: firmware_call reports mitigated/declared sec1
PASS: synthetic -> READY
PASS: adhoc missing fields -> UNKNOWN
PASS: adhoc UNKNOWN lists missing fields
PASS: adhoc VA+module without metadata -> UNKNOWN
PASS: adhoc UNKNOWN does not guess READY
PASS: targets.json has expected targets
PASS: real cmp_ind_reader -> READY (baseline-known)
PASS: real drstr_parser -> BLOCKED (M1.2f/missing compressed sec1 reachability)
PASS: real drstr_parser mentions M1.2f or compressed sec1 or unmapped
PASS: real tile_reader -> BLOCKED
PASS: real hddinfo_compare -> BLOCKED
PASS: JSON round-trips

All selftest checks passed.
```

Real target run (`--target cmp_ind_reader --target drstr_parser --json`):

- `cmp_ind_reader` (`firmware_call`, `Navi.exe` 0x0041c7e8): verdict `READY`;
  `compressed_sec1_data_dependency_m1_2f` status `mitigated`, blocker `false`,
  detail reports declared `sec1_table` input supplied (sec1 byte verification
  may remain M1.2f-open); entry/import/input reachability `known`; reasons
  include "no known M1.2f/import/input/binding blocker in checked metadata" and
  declared-input mitigation.
- `drstr_parser` (`blocked`, `drstr`): verdict `BLOCKED`; M1.2f/sec1-data
  dependency `present` (blocker true) from target metadata; `entry_mapping`
  `blocked` (entry kind blocked with no structured VA in metadata),
  `import_binding` `blocked` (compressed sec1 imports/buffer context),
  `input_binding` `known` (corpus path present). Bytes reported as metadata hint
  only (no image): target metadata states executable uncompressed sec0 for the
  mentioned entry; not image-verified.

TODO L3 rerun guidance updated: `TODO.md` L3 (virtual) line references
`python3 tools/l3_precond.py --target <name>` (H45) before reruns.

## Interpretation

- **FACT:** `tools/l3_precond.py --selftest` passes; on real target definitions
  from `targets.json` it reports `cmp_ind_reader` as `READY` and `drstr_parser`
  as `BLOCKED` with M1.2f/compressed-sec1 reasons (C-3330, C-3333).
- **FACT:** The tool reports executable/data byte context (image-enriched when
  an image is supplied, otherwise unknown/metadata-hinted), M1.2f/sec1-data
  dependency, and import/input/binding reachability dimensions with a
  `READY|BLOCKED|UNKNOWN` verdict and reasons (C-3331, C-3332).
- **OBSERVED:** `drstr_parser`'s structured `entry.va` is null in
  `targets.json` while its reason text names the VA; the tool reports the
  structured entry-mapping as blocked and keeps the verdict `BLOCKED`, which is
  conservative and does not guess `READY`.
- **UNKNOWN:** Image-verified byte/section facts for these targets in this EXP
  (no image supplied); M1.2f sec1 byte verification for `cmp_ind_reader`'s
  declared `sec1_table` remains open (declared input mitigates rerun
  precondition, not the hypothesis about sec1 bytes).

## Conclusion

H45 delivers a machine-checkable precondition gate for reopened L3 reader
reruns: `tools/l3_precond.py` (`--selftest`, `--json`) classifies target
metadata (and optional image facts) into `READY|BLOCKED|UNKNOWN` with explicit
M1.2f, byte-context, and import/input/binding reachability reasons. It does not
execute firmware and does not claim firmware acceptance. TODO L3 rerun guidance
references it. Reopened L3 reruns should be rejected as "same blocker" when the
tool reports `BLOCKED` for unchanged prerequisites, or treated as `UNKNOWN`
(not `READY`) when required fields are missing.

## Reproduction

```bash
python3 tools/l3_precond.py --selftest
python3 tools/l3_precond.py --target cmp_ind_reader --target drstr_parser --json
```

## Follow-ups

- [ ] M9.33 can consume `l3_precond` verdicts to map reopened-target rerun
  prerequisites (depends on H45).
- [ ] When M1.2f/M9.24 land, update target metadata and re-run preconditions;
  a `BLOCKED`→`READY` transition is a metadata/precondition change, not a
  firmware verdict.
