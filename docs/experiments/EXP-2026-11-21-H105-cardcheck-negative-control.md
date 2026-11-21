# EXP-2026-11-21-H105: `cardcheck --break`, the negative control for H103's fixture

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** none (tool-only task) — every input is generated in-process from
  committed modules (`tilewriter`, `ze0_tile_header`, `drstr_ze0`,
  `cmpind_writer`, `mkcard`); the tools read no image and no vendor file. Per-file
  SHA-256s of the generated good tree are in Observations so the fixture is
  pinned.
- **Tools:** python3 3.15.0 / zlib 1.3.1 (`zlib-ng` build) for the primary run;
  python3.13 3.13.17 / zlib 1.3.2 (stock) as the cross-build control. Repo tools:
  `tools/cardcheck.py` (extended here), `tools/l1l2_fixtures.py` (the L1
  registry row), `tools/selftest.py`, `tools/claims_check.py`,
  `tools/todo_check.py`.
- **Claims:** C-4360–C-4369
- **Supersedes:** none
- **Superseded by:** none

## Question

Does a card tree that `cardcheck` accepts actually *fail* when a structural
field is deliberately broken — i.e. can the H40 L1 row prove the checker is
checking, not degraded to `return PASS`?

## Hypothesis

Each of H105's five break kinds trips an **existing** `cardcheck` rule on the
H103 tree, so `--generate-fixture DIR --break KIND` exits 1 and the JSON names
the same check id the good tree passed: `mmain-missing-tile-level` →
`mmain`, `drstr-size-mismatch` → `drstr`, `tile-level-not-in-mmain` → `mmain`,
`header-magic` → `headers`, `fat-cluster-out-of-range` → `fat`. The FAT kind
needs real clusters, so it runs on a new `--generate-fixture-image` (a
vendor-free FAT32 image) and must also yield a "cluster out of range" message
from an existing check, not a new rule. **Falsifier:** the good tree passes and
a `--break` kind also exits 0 (the checker never distinguishes them), or a kind
passes only because a *new* validator rule was added.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | none — good tree under `/tmp/opencode/h105-good2`, break tree under `/tmp/opencode/h105-break2` |
| SHA-256 | per-file hashes in Observations; no image sample |
| Offset(s) / VA(s) | tile level table `0x1AC`, MMAIN level table `0x1AC`, DRSTR entry `+0x1C`, common-header magic `0x00`, MBR root DIRENT cluster u16 at `+0x14/+0x1A` |
| Tool / version | `python3 3.15.0` / `zlib 1.3.1`; control `python3.13 3.13.17` / `zlib 1.3.2` |
| Repo tool | `tools/cardcheck.py` (`--generate-fixture`, `--generate-fixture-image`, `--break`, `--selftest`), `tools/l1l2_fixtures.py` |

## Method

1. **Sample and hash.** There is no input sample: the tool writes its own tree
   (H103) and, for the FAT kind, its own image. The generated files' SHA-256s
   are recorded in Observations.
2. **Commands.** Runnable as written, in one block:

   ```bash
   # good tree, then the same tree with the primary break kind (H105 Done-when)
   rm -rf /tmp/opencode/h105-good2 /tmp/opencode/h105-break2
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h105-good2 \
       --json /tmp/opencode/h105-good2.json --json-only;  echo "good rc=$?"   # 0
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h105-break2 \
       --break tile-level-not-in-mmain \
       --json /tmp/opencode/h105-break2.json --json-only; echo "break rc=$?"  # 1
   python3 - <<'PY'
   import json
   good = json.load(open('/tmp/opencode/h105-good2.json'))
   bad = json.load(open('/tmp/opencode/h105-break2.json'))
   print(sorted(c['id'] for c in good['checks'] if c['status'] == 'PASS'))
   print(sorted(c['id'] for c in bad['checks'] if c['status'] == 'FAIL'))
   PY

   # every break kind (tree kinds via --generate-fixture, FAT via image)
   for k in mmain-missing-tile-level drstr-size-mismatch \
            tile-level-not-in-mmain header-magic; do
     python3 tools/cardcheck.py --generate-fixture "/tmp/opencode/b-$k" \
         --break "$k" --json-only; echo "$k rc=$?"
   done
   python3 tools/cardcheck.py --generate-fixture-image /tmp/opencode/b-fat.img \
       --break fat-cluster-out-of-range --json-only; echo "fat rc=$?"

   # the unbroken image passes all 8 (mbr/fat PASS, not SKIP)
   python3 tools/cardcheck.py --generate-fixture-image /tmp/opencode/good.img \
       --json-only; echo "good image rc=$?"

   # guards: a tree break cannot run on --root, the FAT kind needs an image
   python3 tools/cardcheck.py --root /tmp/opencode/h105-good2 --break header-magic; echo "guard1 rc=$?"
   python3 tools/cardcheck.py --generate-fixture /tmp/opencode/g1 \
       --break fat-cluster-out-of-range; echo "guard2 rc=$?"

   # determinism: two image builds are byte-identical
   python3 tools/cardcheck.py --generate-fixture-image /tmp/opencode/det-a.img --json-only
   python3 tools/cardcheck.py --generate-fixture-image /tmp/opencode/det-b.img --json-only
   sha256sum /tmp/opencode/det-a.img /tmp/opencode/det-b.img

   # selftests
   python3 tools/cardcheck.py --selftest
   python3 tools/l1l2_fixtures.py --selftest
   python3 tools/selftest.py --only cardcheck --only l1l2_fixtures
   ```

3. **Controls.** *Positive:* the unbroken tree passes `tree`, `headers`, `cmp`,
   `drstr`, `mmain`, `version` and the unbroken image passes all eight checks
   (`mbr`/`fat` PASS, not SKIP). *Negative (the point of the task):* each
   `--break` kind must exit 1 with its target id among the FAILs; the L1
   registry row runs the good tree and a broken tree in the same call, so a
   checker that stopped checking cannot pass the row.
4. **Scope.** `tools/cardcheck.py` (five break kinds, the image builder, the
   `fat` cluster-range probe), `tools/l1l2_fixtures.py` (the
   `l1.synthetic.cardcheck` row). No new validator rule: every kind trips an
   existing error message. The `fat` kind is deliberately lane-limited — a
   root tree has no FAT, so it only runs on the image. No vendor bytes; no OSM
   input.
5. **Falsifier.** Stated in the Hypothesis: the good tree passes while a
   `--break` kind also exits 0, or a kind is only caught by a newly added rule.

## Observations

Primary run, python3 3.15.0 / zlib 1.3.1:

- Good tree: `rc=0`, `counts={"pass":6,"fail":0,"skip":2}`, PASS ids
  `['cmp', 'drstr', 'headers', 'mmain', 'tree', 'version']`, `mbr`/`fat` SKIP
  with a reason.
- Broken tree (`--break tile-level-not-in-mmain`): `rc=1`,
  `counts={"pass":5,"fail":1,"skip":2}`, FAIL ids `['mmain']`; the failure
  message is `MMAIN section 4 level 1: count 1 != tile sum 7`. The id equals
  one the good tree passed (`mmain`).
- Tree break kinds (`--generate-fixture DIR --break KIND`), each `rc=1`:

  | kind | target | FAIL ids | first error |
  | --- | --- | --- | --- |
  | `mmain-missing-tile-level` | `mmain` | `mmain` | `tile table has section 4 level 1 not in MMAIN` |
  | `drstr-size-mismatch` | `drstr` | `drstr` | `//CMP.LST: DRSTR size 20 != actual 19` |
  | `tile-level-not-in-mmain` | `mmain` | `mmain` | `MMAIN section 4 level 1: count 1 != tile sum 7` |
  | `header-magic` | `headers` | `headers` | `MAPAL001/B48R058R.DAT: header field 0x00 is 'XARION', expected 'CLARION'` |

- FAT/card image break (`--generate-fixture-image IMG --break
  fat-cluster-out-of-range`): `rc=1`, `counts={"pass":4,"fail":4,"skip":0}`,
  FAIL ids `['fat', 'tree', 'drstr', 'mmain']`; `fat` reports
  `cluster 1601 out of range (data area holds clusters 2..1584)` and the other
  failures are the empty `MAPAL001` the out-of-range read produces. The `fat`
  id is the good image's target and is among the FAILs (the Stop rule: a kind
  that trips several checks asserts only "the target id is among the FAILs").
- Unbroken image (`--generate-fixture-image IMG`): `rc=0`,
  `counts={"pass":8,"fail":0,"skip":0}` — `mbr`/`fat` PASS, no SKIP, so the FAT
  break is not passing only because images fail anyway.
- Guards: `--root DIR --break header-magic` exits 2 (`--break needs
  --generate-fixture or --generate-fixture-image`); `--generate-fixture …
  --break fat-cluster-out-of-range` exits 2 (`needs --generate-fixture-image`);
  an unknown kind is rejected by `argparse` (`invalid choice`, exit 2).
- Determinism: two full image builds are byte-identical —
  `sha256 1b652fe5…be18b2` for both `/tmp/opencode/det-a.img` and `det-b.img`;
  the image is ~100 MiB but sparse (~8 MiB of blocks) and holds no vendor
  bytes.
- `cardcheck --selftest`: `PASS (0 failure(s))`, `30` `ok` lines (18 from H103 +
  12 added here: 5 kinds × 2 assertions + 2 for the unbroken image; counted by
  `python3 tools/cardcheck.py --selftest | grep -c '^  ok'` → `30`).
  `l1l2_fixtures --selftest`: `OK (32 checks)`
  including `L1 synthetic row PASSes the good+break pair (good rc=0 (6 PASS, 0
  FAIL); tile-level-not-in-mmain: rc=1, FAIL includes mmain …)`.
  `selftest.py --only cardcheck --only l1l2_fixtures`: `2 passed, 0 failed`.
- Registry: `python3 tools/l1l2_fixtures.py --json …` → `l1.synthetic.cardcheck`
  is `PASS` (runnable) and `coverage_gaps` is `[]` (the L1 gap H26/H97 reported
  is closed on this host).
- Per-file SHA-256 of the good tree (`h105-good2`): `MAPAL001/B48R058R.DAT`
  `0d997f18…6a56d3f0`, `MMAIN001.DAT` `c06462c8…a711c59079`, `DRSTR001.DAT`
  `ed9f4d1f…f9a4f8`, `REFER001/POINT001.DAT.cmp` `878adbd5…c24942441`.
- Cross-build control (python3.13 3.13.17 / zlib 1.3.2): the good tree and
  `--break tile-level-not-in-mmain` reproduce `rc=0` / `rc=1`. `MMAIN001.DAT`
  and `DRSTR001.DAT` are byte-identical to the primary run
  (`c06462c8…`, `ed9f4d1f…`); the tile and the `.cmp` differ
  (`ced1a8ec…`, `2e16eccc…`) because zlib versions differ — the verdicts, not
  the bytes, are the contract (H9).

## Interpretation

- **FACT:** every one of the five `--break` kinds makes `cardcheck` exit 1 and
  names its target check among the FAILs, while the unbroken tree (6 PASS /
  2 SKIP) and the unbroken image (8 PASS / 0 SKIP) pass.
- **FACT:** the `--break tile-level-not-in-mmain` failure id (`mmain`) is one
  the good tree passed; this is the exact `good rc=0 → break rc=1 → same id`
  contract H105's Done-when asks for.
- **OBSERVED:** two kinds (`header-magic`, `fat-cluster-out-of-range`) trip more
  than one check because a rewritten header or an unreadable directory changes
  a derived value (DRSTR size, MMAIN tile sum). The target id is always among
  the FAILs, which the Stop rule allows.
- **OBSERVED:** the FAT kind cannot run on a `--root` tree; the task's named
  kind therefore comes with a vendor-free image builder so the check it targets
  is reachable at all.
- **UNKNOWN:** firmware acceptance of the fixture — out of scope (rule 13); this
  is an L1 structural control only.

## Conclusion

`tools/cardcheck.py` gains `--break KIND` (five kinds) and
`--generate-fixture-image`; the H103 tree keeps its six PASS and two SKIP, and
each break trips an existing rule, so the H40 L1 row now has a real negative
control (H105). `tools/l1l2_fixtures.py`'s `l1.synthetic.cardcheck` runs the
good tree and the broken tree in one row and only PASSes if the broken tree
fails on the id the good tree passed; `coverage_gaps` is empty on this host.
Claims C-4360–C-4369 record the kinds and the FAT-lane limit. What is still
open: H40 wires this row into `l1l2-fixtures.yml`, H104 pins the baseline.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h105-good2 \
    --json /tmp/opencode/h105-good2.json --json-only; echo rc=$?      # 0
python3 tools/cardcheck.py --generate-fixture /tmp/opencode/h105-break2 \
    --break tile-level-not-in-mmain \
    --json /tmp/opencode/h105-break2.json --json-only; echo rc=$?     # 1
python3 tools/l1l2_fixtures.py --selftest                            # OK (32 checks)
```

## Follow-ups

- [ ] H40: run `l1.synthetic.cardcheck` from `l1l2-fixtures.yml` so a checker
      that stops failing the broken tree turns CI red.
- [ ] H104: pin the per-check baseline of the good tree/image.
