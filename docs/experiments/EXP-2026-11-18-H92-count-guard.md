# EXP-2026-11-18-H92: `--prose-counts` — a claim quoting a count the tree no longer prints

- **Status:** done
- **Date:** 2026-11-18
- **Sample:** `none (tool-only task)` — the claim ledger `docs/research/claims.md`
  (`2221` rows) and `tools/fixtures/fn_match_eu_us_2011.json` at `origin/main`
  `a48bbf9` (branch base; the work tree is `97c4945`). No vendor bytes.
- **Tools:** python3 3.15.0; `tools/claims_check.py` (`--selftest`,
  `--prose-counts`), `tools/gate.py`, `tools/selftest.py`, `tools/todo_check.py`
- **Claims:** C-4150–C-4155
- **Supersedes:** none
- **Superseded by:** none

## Question

`claims_check --count-check` fails only when a claim's *selftest* count matches
the wrong tool revision. Can a mode catch the other direction — a claim quoting
any other count the tree no longer prints — without guessing at prose?

## Hypothesis

The safe shapes are few and mechanical: a `grep -c`/`python3 -c` command the
cell already quotes followed by `prints N`, a `stays N` next to such a command,
and the exact selftest footer `OK (N checks`. Re-running only those, and only
when H78 gives the claim a measurement revision, turns H87's defect red without
a false positive on a legitimate `N at <sha>`.
**Falsifier:** a seeded stale `stays 12` over a command that prints 15 is not
`STALE COUNT` with exit 1, or a correct `N at <sha>` row goes red.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (tool-only task)`; the claim ledger, one checked-in fixture |
| SHA-256 | `none (tool-only task)` |
| Offset(s) / VA(s) | none |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/claims_check.py` (`--prose-counts`, `--selftest`) |

## Method

1. **Sample and hash.** The 2221-row ledger and
   `tools/fixtures/fn_match_eu_us_2011.json`; every shape is counted and every
   allowlisted command is run. No image, no vendor bytes.
2. **Commands.**
   ```bash
   python3 tools/claims_check.py --prose-counts
   python3 tools/claims_check.py --prose-counts --json
   python3 tools/claims_check.py --selftest
   python3 tools/gate.py
   grep -c '"eu_va"' tools/fixtures/fn_match_eu_us_2011.json
   python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
   # the mutation (restore with git checkout afterwards):
   sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
   python3 tools/claims_check.py --prose-counts
   git checkout -- docs/research/claims.md
   # the `stays N` shape over a real command (the H87 form, injected):
   python3 - <<'PY'
   import sys; sys.path.insert(0, "tools"); import claims_check as cc
   row = ("| C-9999 | The fixture stays `12` rows. | VERIFIED (tool) | H | "
          "EXP-2026-11-18-H92-precheck-repoint; at `334f092`; "
          "`grep -c '\"eu_va\"' tools/fixtures/fn_match_eu_us_2011.json` |\n")
   print(cc.prose_count_problems(cc.parse_claim_rows(row)))
   PY
   ```
3. **Controls.** *Positive*: the injected `stays 12` row over a `grep -c` that
   prints `13` must be `STALE COUNT` (exit 1 path). *Negative*: the real ledger,
   whose only allowlisted `prints` count is correct (`C-3740` `13 5`), must
   print `stale prose counts: 0`; a `stays 15` row and a revision-less row must
   be clean (the selftest's `r20`/`r21`/`r27`/`r28`).
4. **Scope.** `tools/claims_check.py` only: the `--prose-counts` flag, three
   regex shapes, one allowlist (`grep -c`, `python3 -c`) and one re-runner.
   Excluded: every other claim row (read, never edited), every EXP
   `Observations` block and task `Result` (not parsed — see "Rejected
   shapes"), and enforcement in `tools/gate.py` (off by default).
5. **Falsifier.** Stated in the Hypothesis, before the result.

## Observations

```
$ python3 tools/claims_check.py --selftest
claims_check selftest: OK (37 checks)          # was 28

$ python3 tools/claims_check.py --prose-counts
...
stale prose counts: 0
claims_check: OK
$ echo $?
0

$ python3 tools/claims_check.py --prose-counts                 # shape census
rows 2221
prints ['C-3740']
stays ['C-927', 'C-1023', 'C-4171']
footer []

$ grep -c '"eu_va"' tools/fixtures/fn_match_eu_us_2011.json
13
$ python3 -c "import json;d=json.load(open('tools/fixtures/fn_match_eu_us_2011.json'));print(len(d['rows']),sum(r['expect']=='UNIQUE' for r in d['rows']))"
13 5

# positive control: seeded stale count -> red
$ sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
$ python3 tools/claims_check.py --prose-counts | grep -E 'stale prose|STALE'
stale prose counts: 1
  STALE COUNT C-3740: claims 12, command prints 13 (8bc8fd91d408a87d318e950c690af4938f8d8992)
$ echo $?
1
$ git checkout -- docs/research/claims.md

# the `stays N` shape over a real command -> red
$ python3 - <<'PY'  (the injected row above)
[{'id': 'C-9999', 'shape': 'stays', 'claimed': 12, 'got': 13,
  'rev': '334f092', 'how': 'command',
  'detail': 'grep -c \'"eu_va"\' tools/fixtures/fn_match_eu_us_2011.json'}]

# a shallow checkout says so instead of a false 0
$ git clone --depth 1 file://$PWD <scratch>/shallow && cd <scratch>/shallow
$ python3 tools/claims_check.py --prose-counts | tail -3
claim/EXP count conflicts: 0
prose count check: skipped (shallow clone; fetch the full history to run it)
claims_check: OK

$ python3 tools/gate.py | tail -1
gate: 4 pass, 0 fail, 0 skip
$ python3 tools/selftest.py | tail -2
passed=93 failed=0 skipped=23 total=116 time=48.50s
selftest: OK
```

`git status --short` is clean after the mutation is restored.

## Interpretation

- **FACT:** the guard turns a seeded stale count red with exit 1 in both the
  `prints` shape (`C-3740` 12 vs 13) and the `stays` shape (an injected 12 vs a
  `grep -c` that prints 13), and the real ledger is green
  (`stale prose counts: 0`).
- **FACT:** the real ledger carries one allowlisted `prints` shape (`C-3740`,
  correct: `13 5`) and three unmeasurable `stays` shapes (`C-927` `1,358,592`,
  `C-1023` `45`, `C-4171` `0`; no cell command, no cell selftest), so 3 of 4
  real prose shapes are not re-runnable — H92's `Stop:` applies: ship the
  allowlist, list the rejects, stay off by default.
- **FACT:** `--selftest` grows 28 → 37 checks, all in the H92 block, and the
  gate stays `4 pass, 0 fail, 0 skip`; a depth-1 clone prints the skip, never a
  false zero.
- **OBSERVED (defect left in place):** C-3894's evidence row says
  `parse_tasks` returns `176` while the tree prints `228`. The guard does not
  see it: the row quotes `176` as prose after a backticked tool name (no
  `grep -c`/`python3 -c` command, no footer), which is exactly the "do not
  parse arbitrary prose" line. Recorded as a follow-up, not fixed here (Scope
  is the tool; H92's Precheck names it — see
  EXP-2026-11-18-H92-precheck-repoint).
- **REJECTED shapes** (not re-run, by design): a `Result:` line or an EXP
  `Observations` block (append-only records, not the ledger); a `prints N`
  whose command is not `grep -c`/`python3 -c` (C-4100's `US_BUILD_STARTS`
  length is `python3 -c`, but many are prose-only); any command with an
  `archive/…` input (a vendor fetch is not a gate's price); a bare `stays N`
  with no command or selftest (C-927/C-1023/C-4171 — unmeasurable, skipped).
- **LIMITATION:** the mode is not in `tools/gate.py`; enforcement is a
  follow-up once the unmeasurable `stays` rows are resolved or allowlisted.

## Conclusion

`tools/claims_check.py --prose-counts` adds the other direction of the count
rule: three mechanical shapes re-run only through an allowlist and only when
H78's measurement revision exists, printing `STALE COUNT … claims N, command
prints M` with exit 1. On the current ledger it is green (`0` stale) and one
shape is measurable (`C-3740`); the seeded mutation and the injected `stays`
row both go red, the `N at <sha>` and revision-less rows stay clean, and the
standing gate is unchanged (`4 pass`). Enforcement stays off by default per the
task's `Stop:`; the three unmeasurable shapes and the C-3894 defect are
follow-ups.

## Reproduction

```bash
python3 tools/claims_check.py --selftest                    # claims_check selftest: OK (37 checks)
python3 tools/claims_check.py --prose-counts                # stale prose counts: 0, exit 0
sed -i 's/prints `13 5`/prints `12 5`/' docs/research/claims.md
python3 tools/claims_check.py --prose-counts                # STALE COUNT C-3740 ... exit 1
git checkout -- docs/research/claims.md
python3 tools/gate.py                                       # gate: 4 pass, 0 fail, 0 skip
```

## Follow-ups

- [ ] Wire `--prose-counts` into `tools/gate.py` after C-927/C-1023/C-4171
  are pinned or allowlisted (the mode is off by default today).
- [ ] C-3894's `176` vs `228` is a document defect for a record pass; H92's
  guard deliberately does not parse that prose shape.

## Corrections after navigator review

(empty until the navigator round returns)
