# EXP-2026-11-16-H73: evidence spans on `fn_audit` claims must be repo commands

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (docs-only task)` — E2 then reads `archive/head256.img`,
  the EU 2011 firmware head (256 MiB), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`; E3
  reads only the committed `docs/research/fn-audit-corpus-2026-11-16.json`
  (`ddd113f8…`). E4's vendor tile is named by SHA-256 only and is **not**
  re-read. No vendor bytes are committed.
- **Tools:** python3 3.13.1; repo `tools/fn_audit.py`,
  `tools/one_tile_pipeline.py`, `git` (no repo change)
- **Claims:** C-3900, C-3903, C-3912 (evidence column only; claim text
  unchanged, no new C row registered)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the evidence spans in C-3900, C-3903 and C-3912 be re-run from a
checkout, instead of naming the uncommitted `/tmp/opencode/*.json` scratch
files and a `leafre-work/` path that no repo command produced?

## Hypothesis

The `/tmp` snapshots were the review artifact, not the evidence: the old
snapshot is recoverable byte-for-byte from `git show 3fdbab2^:…` and the
class flip is a one-liner over the committed file through the tool's own
`row_fingerprint`, so both spans become commands. C-3912's concrete
`B48R058R` fields are only printable with the vendor tile present, so they
stay `OBSERVED (sample on this machine)` with the tile SHA-256, while the
repo command (`--selftest`) is what the evidence column cites.

**Falsifier:** `git show 3fdbab2^:docs/research/fn-audit-corpus-2026-11-16.json`
does not hash to `4606aa2a…78fe38`, or the recovered snapshot does not print
`CORPUS DRIFT: 0 new / 0 gone / 125 moved` at exit 0, or the one-liner does
not exit 1 on the frozen `START`→`INSIDE` flip, or the selftest does not
assert the four field classes C-3912 names.

## Inputs

| Item | Value |
| --- | --- |
| Image (E2 only) | `archive/head256.img`, 268,435,456 B |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Old snapshot | `git show 3fdbab2^:docs/research/fn-audit-corpus-2026-11-16.json`, `4606aa2a…78fe38` |
| Committed snapshot | `docs/research/fn-audit-corpus-2026-11-16.json`, `ddd113f8…0102a1a` |
| Vendor tile (E4, not re-read) | `B48R058R.DAT`, 289,319,168 B, `e9c9cb22…8af3ff52` |
| Repo tools | `tools/fn_audit.py`, `tools/one_tile_pipeline.py` |

## Method

1. **Sample and hash.** Docs-only edit of three `claims.md` evidence cells.
   The only bytes read are E2's `archive/head256.img` (hash above) and E3/E4's
   committed JSON/tool source. The vendor tile is named by its recorded
   SHA-256, not read.
2. **Commands** (runnable as written, from the repo root):

```bash
# Precheck: the three rows still name scratch paths, the scratch file is not tracked.
grep -nE '/tmp/opencode|leafre-work' docs/research/claims.md | grep -E 'C-3900|C-3903|C-3912'
git ls-files /tmp/opencode/h69-old-snapshot.json          # fatal: outside repository
git show 3fdbab2^:docs/research/fn-audit-corpus-2026-11-16.json | sha256sum

# C-3900 evidence: recreate the old snapshot from git, run it, expect moved-only exit 0.
git show 3fdbab2^:docs/research/fn-audit-corpus-2026-11-16.json > /tmp/se-old.json
python3 tools/fn_audit.py archive/head256.img --corpus /tmp/se-old.json --quiet   # exit 0

# C-3903 evidence (a): a write at the snapshot's own tree reproduces it byte-for-byte.
mkdir -p /tmp/se-tree && git archive 9b4e6d7 | tar -x -C /tmp/se-tree
ln -sf "$PWD/archive/head256.img" /tmp/se-tree/archive/head256.img
(cd /tmp/se-tree && python3 tools/fn_audit.py archive/head256.img --scope docs \
   --write-snapshot /tmp/se-fresh.json --quiet && \
 cmp /tmp/se-fresh.json docs/research/fn-audit-corpus-2026-11-16.json)        # cmp silent, exit 0

# C-3903 evidence (b): class flip through the tool's own row_fingerprint, expect exit 1.
python3 -c "import json,sys;sys.path.insert(0,'tools');import fn_audit as f;\
d=json.load(open('docs/research/fn-audit-corpus-2026-11-16.json'));\
r=next(x for x in d['rows'] if x['class']=='START');\
r.update({'class':'INSIDE','true_start':'0x00401000','class_sha256':f.row_fingerprint('INSIDE','0x00401000')});\
d['summary']['start']-=1;d['summary']['inside']+=1;json.dump(d,open('/tmp/se-classflip.json','w'))"
python3 tools/fn_audit.py archive/head256.img --corpus /tmp/se-classflip.json --quiet --no-live-check   # exit 1

# C-3912 evidence: the repo command whose selftest asserts the same fields.
python3 tools/one_tile_pipeline.py --selftest

# Gate.
python3 tools/claims_check.py
python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
```

3. **Controls.** Positive: each rewritten command prints the value the claim
   names (C-3900 `CORPUS DRIFT: 0 new / 0 gone / 125 moved` at exit 0; C-3903
   `frozen=INSIDE/0x00401000 image=START/None` at exit 1; C-3912 the selftest
   `ok` lines for the four field classes). Negative: the old scratch path is
   not tracked (`git ls-files` fatal) and after the rewrite
   `grep -E 'C-3900|C-3903|C-3912' docs/research/claims.md` finds no
   `/tmp/opencode` path and no `leafre-work` path outside the one
   `OBSERVED (sample on this machine)` sentence in C-3912.
4. **Scope.** `docs/research/claims.md`, three evidence cells only: C-3900,
   C-3903, C-3912. Excluded: the claim text, every other row, all EXPs
   (append-only), and the vendor tile run (not re-executed).
5. **Falsifier** (stated before the run): any of the four commands above
   prints a different value or exit code, or the grep still finds a raw
   scratch path, or `claims_check`/the live corpus gate fails.

## Observations

- Precheck grep printed C-3900 (`/tmp/opencode/h69-old-snapshot.json`) and
  C-3903 (`/tmp/opencode/h69-classflip.json`); C-3912 already carried no
  `/tmp` or `leafre-work` string (its evidence was `override command in the
  EXP`).
- `git show 3fdbab2^:… | sha256sum` = `4606aa2aff292d72ec9651cfff0660c246bf1d23255fc59cab3348ea0878fe38`
  (matches the claim text's `4606aa2a…`).
- C-3900 recovered run: `CORPUS DRIFT: 0 new / 0 gone / 125 moved`,
  `fn_audit: warning: line-only drift; …`, exit 0.
- C-3903 (a): at `9b4e6d7` the fresh write is `ddd113f8…0102a1a` and `cmp` is
  silent (exit 0). Note on `main`: `9b4e6d7` is the "record the post-rebase
  H69 snapshot hash" commit, **not** `3fdbab2` — `3fdbab2` wrote `2db48be1…`,
  which the rebase message in `9b4e6d7` itself records as superseded.
- C-3903 (b): `START 228, INSIDE 1, …`, `row class disagrees with the image:
  TODO.md:132 0x0041c7dc frozen=INSIDE/0x00401000 image=START/None`, exit 1.
- C-3912: `one_tile_pipeline.py --selftest` prints `ok honest factory tile
  parsed (provenance=factory-tile-parsed)`,
  `ok factory_tile_sha256 equals sha256sum of MAPAL001/<cell>.DAT`,
  `ok factory_tile_size equals tile size`,
  `ok honest tile is bound to its cell (box table within bounds)`,
  `ok --factory-tile: run reached tilewriter …`, `selftest: OK (0 failure(s))`.
- `claims_check: OK` (exit 0); live corpus gate on the committed snapshot:
  exit 0 with the unchanged summary (`START 229, INSIDE 0, CORRECTED 23,
  GAP 29 (leaf 29), AMBIGUOUS 0, UNMAPPED 32`).

## Interpretation

- **FACT:** C-3900 and C-3903 are reproducible from a checkout: the old
  snapshot is `git show 3fdbab2^:…`, and both the write and the class flip
  run through committed files and `row_fingerprint`.
- **FACT:** C-3912's evidence is now a repo command that asserts the same
  fields; its concrete `B48R058R` values (sha, size, binding string,
  `mode=factory-backed`, `tilewriter_rc=2`) are `OBSERVED (sample on this
  machine)`, not `VERIFIED (tool)`, because the selftest cannot reprint them
  without the vendor tile.
- **OBSERVED:** the C-3903 byte-identity baseline is the snapshot's final
  tree `9b4e6d7`, not the intermediate write `3fdbab2`.
- **UNKNOWN:** whether a future change to the prose will need another
  snapshot refresh; that remains the `tools/README.md` procedure.
- **HYPOTHESIS:** none — this is a docs-only evidence rewrite.

## Conclusion

Three evidence cells in `docs/research/claims.md` no longer name uncommitted
scratch. C-3900 cites the `git show` recovery and a `CORPUS DRIFT … 125
moved` run; C-3903 cites the `9b4e6d7` archive write + `cmp` and a
`row_fingerprint` class-flip one-liner; C-3912 cites
`one_tile_pipeline.py --selftest` and marks the vendor fields `OBSERVED
(sample on this machine)` with the tile SHA-256. Claim text is unchanged and
no new claim row was registered.

## Reproduction

```bash
git show 3fdbab2^:docs/research/fn-audit-corpus-2026-11-16.json > /tmp/se-old.json
python3 tools/fn_audit.py archive/head256.img --corpus /tmp/se-old.json --quiet
# expected: CORPUS DRIFT: 0 new / 0 gone / 125 moved, exit 0
```

## Follow-ups

- [ ] H71 rewrites the same evidence class for C-3860/C-3861/C-3864; use the
  `git show` recovery and the `OBSERVED` marking convention here.
- [ ] If the snapshot is refreshed again, C-3903's byte-identity baseline
  moves with it — cite the refresh commit, not `9b4e6d7`.
