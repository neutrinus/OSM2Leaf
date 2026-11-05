# EXP-2026-11-05-44: IMF definition and its validator

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** none (synthetic only; no vendor data). Generated sample
  `sample.imf.jsonl`, 23 lines (header + 15 nodes / 5 ways / 2 relations),
  SHA-256 `aea27532b1a036b19e595a41bc03d9ea752e2d0749add0f2c4a2c7cdae079bb1`.
  Tool: `tools/imf_check.py`, SHA-256
  `942f1b1c44958c95a702298dce569deaf147ade49c4a3a5f2d6182f06dea7f4f`.
- **Claims:** C-542 (design only; ledger row proposed, not added by this
  change)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the intermediate format between OSM and the ZE0 writer be specified
precisely enough that a standard-library validator rejects the mistakes the
writer would otherwise inherit — wrong tile, unresolved node, unit confusion,
lost licence — without deciding anything that belongs to the writer?

## Hypothesis

Yes. A JSON Lines schema with derived-but-checked fields (cell per record,
integer cm/s, sorted `tiles`) plus one rule per failure class is sufficient.
The rule set can be shown complete by pairing every error code with a synthetic
failure case, so the document and the tool cannot drift apart silently.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none — synthetic sample from `--sample` |
| SHA-256 | `aea27532b1a036b19e595a41bc03d9ea752e2d0749add0f2c4a2c7cdae079bb1` |
| Offset(s) | n/a |
| Tool version | `Python 3.14.4`, repo HEAD (no commit made) |

Reference geometry in the sample is invented; only the `BxxRyyR` cell is real
(the A8 example sits in `B48R058R`, Wrocław's cell). The header names the
pinned Dolnośląskie snapshot only to exercise the provenance fields.

## Method

```bash
# 1. Rule set, grid inverse, units, one failure case per rule
python3 tools/imf_check.py --selftest

# 2. Generate the synthetic file and validate it in the same run
python3 tools/imf_check.py --sample -o /tmp/opencode/imf/sample.imf.jsonl

# 3. Plain and JSON validation of the generated file
python3 tools/imf_check.py /tmp/opencode/imf/sample.imf.jsonl
python3 tools/imf_check.py /tmp/opencode/imf/sample.imf.jsonl --json

# 4. One planted error (maxspeed_cms not consistent with maxspeed_kmh)
#    bad.imf.jsonl = sample with w900000005.maxspeed_cms = 1000
python3 tools/imf_check.py /tmp/opencode/imf/bad.imf.jsonl --json
echo $?

# 5. Strip derived fields, let the tool recompute them
python3 tools/imf_check.py /tmp/opencode/imf/notiles.imf.jsonl --assign-tiles \
  -o /tmp/opencode/imf/assigned.imf.jsonl
cmp /tmp/opencode/imf/assigned.imf.jsonl /tmp/opencode/imf/sample.imf.jsonl

# 6. Registry integration and the repository self-test
python3 tools/selftest.py --only imf_check
python3 tools/selftest.py
```

The one planted-error file and the tile-stripped file were produced with:

```bash
python3 - <<'EOF'
import json
src = "/tmp/opencode/imf/sample.imf.jsonl"
objs = [json.loads(l) for l in open(src, encoding="utf-8")]
for o in objs:
    if o.get("id") == "w900000005":
        o["maxspeed_cms"] = 1000
open("/tmp/opencode/imf/bad.imf.jsonl", "w", encoding="utf-8").write(
    "".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) + "\n"
            for o in objs))

objs = [json.loads(l) for l in open(src, encoding="utf-8")]
for o in objs:
    o.pop("tile", None)
    o.pop("tiles", None)
open("/tmp/opencode/imf/notiles.imf.jsonl", "w", encoding="utf-8").write(
    "".join(json.dumps(o, ensure_ascii=False, separators=(",", ":")) + "\n"
            for o in objs))
EOF
```

## Observations

`--selftest`, exit code 0:

```text
imf_check selftest
  grid inverse                 OK
  speed round-trip             OK 1..300 km/h
  valid sample                 OK nodes=15 ways=5 relations=2
  sample warnings              OK []
  every rule has a case        OK
  failure cases                OK 22/22
  warnings are non-fatal       OK
  --assign-tiles round-trip    OK issues=0
selftest: OK
```

`--sample -o …`, exit code 0:

```text
file        /tmp/opencode/imf/sample.imf.jsonl
records     nodes=15 ways=5 relations=2
attributes  named=4 maxspeed=4 oneway=1 addresses=2 pois=1
tiles       B48R050R(1n/0w) B48R058R(14n/5w)
errors      0
result      PASS
```

Validation of the planted error, `--json`, exit code 1:

```json
{
  "ok": false,
  "errors": [
    {
      "code": "E015",
      "line": 18,
      "severity": "error",
      "message": "way: maxspeed_cms=1000 != 1389 for 50 km/h"
    }
  ],
  "warnings": []
}
```

Other exit codes observed: malformed second line (`{"imf":1,"type":node`)
→ `E003` line 2, exit 1; nonexistent path → `error: … No such file or
directory`, exit 2; no arguments → argparse usage error, exit 2.

`--assign-tiles` on a file with every `tile`/`tiles` removed: exit 0 and

```text
cmp /tmp/opencode/imf/assigned.imf.jsonl /tmp/opencode/imf/sample.imf.jsonl
# no output: files are byte-identical
```

Registry integration:

```text
$ python3 tools/selftest.py --only imf_check
tool:imf_check  PASS  0.06s
passed=1 failed=0 skipped=0 total=1 time=0.06s
selftest: OK

$ python3 tools/selftest.py
passed=9 failed=0 skipped=19 total=28 time=0.39s
selftest: OK
```

(The per-run times differ between invocations — 0.06–0.10 s for the tool —
which is why only the pass/fail counts are treated as the result.)

Tile inverse, spot checks (cell → box via `tools/mesh_grid.py`, agreed with
the local inverse):

```text
B48R058R  48.00..53.33 N   12..20 E
B48R050R  48.00..53.33 N   20..28 E
B48R060R  48.00..53.33 N    4..12 E
B58R070R  58.67..64.00 N  -12..-4 E
```

A record at 51.100 N, 19.999 E maps to `B48R058R`; at 20.001 E to
`B48R050R`. A `R057` id is rejected (`E010`) because R must be a multiple of
8 for the 8-unit cell, so neighbouring columns differ by 8, not by 1.

## Interpretation

- **FACT:** 22 error rules and 6 warning rules are defined; `--selftest`
  triggers each error code exactly once and fails if a code has no case
  (`22/22`, and `tools/selftest.py` discovers the tool automatically).
- **FACT:** the generated sample validates clean, and `--assign-tiles`
  reproduces it byte-for-byte from a file with the derived fields removed.
  The assignment is therefore a pure function of coordinates and node refs.
- **OBSERVED:** integer cm/s round-trips every integer km/h from 1 to 300
  under `(kmh*250+4)//9` and `(cms*9+125)//250`; 140 km/h = 3889 cm/s,
  50 km/h = 1389 cm/s.
- **OBSERVED:** the `BxxRyyR` inverse agrees with `tools/mesh_grid.py` on the
  five checked cells and with the documented boxes; B and R are multiples of
  8 in every real cell, which the validator now requires.
- **HYPOTHESIS:** this schema is sufficient for the first Dolnośląskie build.
  It has not been exercised on a real extract, so the size and the ordering
  rules are untested at 2.9 M nodes.
- **UNKNOWN:** whether the writer needs any tag or relation that IMF v1 drops;
  the whitelist is derived from the factory families, not from a working
  writer.

## Conclusion

Created `docs/research/intermediate-format.md` (IMF v1: records, tags, tile
assignment, units, IDs, provenance, worked example, writer unknowns) and
`tools/imf_check.py` (validator, `--assign-tiles`, `--sample`, `--json`,
`--selftest`). No other doc or tool was changed, so the claim ledger row and
the `TODO.md` P5 checkbox are left for the coordinating session.

Proposed claim (status **design only**, not verified against any writer):

> **C-542** — IMF v1 is a UTF-8 JSON Lines file (`imf=1`) with one header
> (pinned source + ODbL attribution), then nodes, ways and the
> restriction/boundary/route relation subset. Each record carries a stable
> `n|w|r<osm id>` id and a whole `BxxRyyR` cell; a way's `tile` is its first
> node's cell and `tiles` is the sorted set of all its nodes' cells. Speeds
> are integer cm/s, coordinates are WGS84 degrees at 1e-7. `tools/imf_check.py`
> enforces 22 schema/consistency rules (`E001`–`E022`) with one synthetic
> failure case per rule, plus `--assign-tiles` and `--sample`.
> **Status: design only.** Evidence: this experiment.

## Follow-ups

- [ ] Add C-542 to `docs/research/claims.md` (design-only section) and tick
      "Define the intermediate format" in `TODO.md` P5.
- [ ] Add `EXP-2026-11-05-44` to the `docs/experiments/README.md` index.
- [ ] Run the extractor on the pinned Dolnośląskie snapshot and validate the
      real file; record node/way counts, file size and peak RSS. The ordering
      rule (nodes before ways) must survive the extractor.
- [ ] Resolve the tile-count discrepancy: bbox arithmetic puts all of
      Dolnośląskie in `B48R058R`, `build-profiles.md` says 2–3 tiles.
- [ ] Decide the writer's road-class, speed-table and name/charset mappings
      (the 13 open items at the end of the format doc).
