# EXP-2026-11-22-H40: the generated-fixture contract (H103 tree + H105 break) is covered

- **Status:** done (2026-11-22: re-ran the done-when — `l1l2_fixtures.py
  --selftest` OK (32 checks); `--require-covered` rc=0; a good `cardcheck
  --generate-fixture` tree is 6 PASS / 2 SKIP and byte-identical over two
  runs; the H105 `--break tile-level-not-in-mmain` tree is rc=1 with `mmain`
  FAIL; `tools/gate.py` 5 pass / 0 fail / 0 skip)
- **Date:** 2026-11-22
- **Sample:** none (tool-only task) — no vendor bytes; the fixtures are
  generated in a temp dir by `cardcheck --generate-fixture`.
- **Tools:** `python3 3.15.0`; `tools/l1l2_fixtures.py`,
  `tools/cardcheck.py` (H103 `--generate-fixture`, H105 `--break`),
  `tools/gate.py`.
- **Claims:** C-3270–C-3276
- **Supersedes:** none (this is the H26 registry row H40 was waiting on)
- **Superseded by:** none

## Question

Is H40's generated-fixture contract actually in place — a vendor-free,
deterministic ZE0 tree that `cardcheck` runs (L1) and a synthetic L2
round-trip, with a **negative control** (a broken tree fails and names the
check the good tree passed) — or is the board row still `open` only because
its evidence was never written down?

## Hypothesis

H103 (the `--generate-fixture` builder) and H105 (the `--break` control)
landed after H40 was written, and `tools/l1l2_fixtures.py` already runs them
as the `l1.synthetic.cardcheck` registry row. So H40's Done-when is met on
`origin/main` and the remaining work is to prove it (the good+break pair, the
L2 round-trips, CI determinism) and record it — not to write a new builder.
**Falsifier:** `l1l2_fixtures.py --require-covered` exits 1, or the good tree
does not pass, or the broken tree does not fail naming the good tree's check.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `tools/l1l2_fixtures.py`, `tools/cardcheck.py`, `.github/workflows/l1l2-fixtures.yml` |
| SHA-256 | n/a (generated tree; determinism checked by diffing two runs) |
| Offset(s) / VA(s) | n/a |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/l1l2_fixtures.py`, `tools/cardcheck.py`, `tools/gate.py` |

## Method

1. **Sample and hash.** `cardcheck --generate-fixture DIR --json OUT` writes a
   vendor-free tree in a temp dir; H105's `--break tile-level-not-in-mmain`
   writes its broken sibling. No vendor bytes are read.
2. **Commands.**

   ```bash
   # the good tree: 6 PASS / 2 SKIP
   python3 tools/cardcheck.py --generate-fixture /tmp/good --json /tmp/g.json

   # the H105 negative control: rc=1, names 'mmain' (the id the good tree passed)
   python3 tools/cardcheck.py --generate-fixture /tmp/bad \
     --break tile-level-not-in-mmain --json /tmp/b.json

   # determinism: two runs are byte-identical
   python3 tools/cardcheck.py --generate-fixture /tmp/good2 --json /tmp/g2.json
   diff -r /tmp/good /tmp/good2

   # the H26 registry row and its coverage gate
   python3 tools/l1l2_fixtures.py --selftest          # OK (32 checks)
   python3 tools/l1l2_fixtures.py --require-covered   # rc=0
   python3 tools/gate.py                              # 5 pass / 0 fail
   ```

3. **Controls.** *Positive:* the good tree is 6 PASS / 2 SKIP and byte-identical
   over two runs; the L2 rows (`l2.drstr.build-roundtrip`,
   `l2.cmpind.preserve-roundtrip`, `l2.tile.class-roundtrip`,
   `l2.poi.mutation.imgpatch-selftest`) all PASS. *Negative:* the broken tree
   is rc=1 with `mmain` FAIL, so a checker that stopped checking cannot go
   green.
4. **Scope.** Verification only — no new builder, no vendor data, no firmware
   acceptance claim (rule 13). The honest `NOT COVERED` rows
   (`l2.tile.harness-selftest`, real-tile round-trips) stay `NOT COVERED` with
   their reasons.
5. **Falsifier.** `--require-covered` rc=1, or the good tree not passing, or
   the broken tree not naming the good tree's check.

## Observations

The good tree:

```
$ python3 tools/cardcheck.py --generate-fixture /tmp/good --json /tmp/g.json
rc=0
good checks: {'SKIP': 2, 'PASS': 6} total 8
$ python3 tools/cardcheck.py --generate-fixture /tmp/good2 --json /tmp/g2.json
$ diff -r /tmp/good /tmp/good2      # byte-identical over two runs
```

The negative control:

```
$ python3 tools/cardcheck.py --generate-fixture /tmp/bad \
    --break tile-level-not-in-mmain --json /tmp/b.json
rc=1
break FAIL checks: ['mmain']      # the id the good tree passed
```

Registry and gate:

```
$ python3 tools/l1l2_fixtures.py --selftest
l1l2_fixtures self-test: OK (32 checks)
$ python3 tools/l1l2_fixtures.py --require-covered ; echo $?
0
$ python3 tools/gate.py
selftest PASS  claims_check PASS  todo_check PASS  board_check PASS  fn_audit PASS
gate: 5 pass, 0 fail, 0 skip
```

The registry rows:

```
| L1 synthetic | l1.synthetic.cardcheck | PASS | yes | good rc=0 (6 PASS, 0 FAIL);
  tile-level-not-in-mmain: rc=1, FAIL includes mmain |
| L2 DRSTR      | l2.drstr.build-roundtrip        | PASS | yes | built 176 bytes, 2 nodes |
| L2 tile       | l2.tile.class-roundtrip         | PASS | yes | 2 parcels, 3 shapes |
| L2 tile       | l2.tile.harness-selftest        | NOT COVERED | no | needs a tile arg |
```

## Conclusion

H40's generated-fixture contract is in place on `origin/main`: the H103
`--generate-fixture` tree is vendor-free, deterministic (byte-identical over
two runs) and runs 6 PASS / 2 SKIP under `cardcheck`; the H105 `--break
tile-level-not-in-mmain` tree is rc=1 and names `mmain` — the check the good
tree passed — so the L1 CI row cannot go green on a checker that stopped
checking; and the L2 rows (`drstr`, `cmpind` preserve, `tile` class,
`imgpatch`) PASS on synthetic fixtures. `l1l2_fixtures.py --selftest` is OK
(32 checks) and `--require-covered` exits 0, so the H26 registry row
`l1.synthetic.cardcheck` is now runnable. The honest `NOT COVERED` rows
(real-tile harness, factory streams) keep their reasons. No vendor data, no
firmware claim. All Done-when conditions hold; the Falsifier does not fire.

## Reproduce

```bash
git clone <repo> && cd <repo>
python3 tools/l1l2_fixtures.py --selftest
python3 tools/l1l2_fixtures.py --require-covered   # rc=0
python3 tools/cardcheck.py --generate-fixture /tmp/good --json /tmp/g.json
python3 tools/cardcheck.py --generate-fixture /tmp/bad \
  --break tile-level-not-in-mmain --json /tmp/b.json    # rc=1, 'mmain'
python3 tools/gate.py                                # 5 pass, 0 fail
```
