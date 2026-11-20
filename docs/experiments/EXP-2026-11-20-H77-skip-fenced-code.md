# EXP-2026-11-20-H77: `fn_audit` skips fenced code blocks; new l3 overlay

- **Status:** done (pair review pending)
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 IMG256, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`); the
  repository Markdown corpora at the branch head (395 l3 files).
- **Tools:** Python 3.13.18; `tools/fn_audit.py` (changed), `tools/gate.py`,
  `tools/selftest.py`
- **Claims:** C-4000, C-4001, C-4002, C-4003
- **Supersedes:** none
- **Superseded by:** none

## Question

If `fn_audit` treats a fenced code block in an EXP or a `docs/format` file as
quoted text rather than prose, what does it remove from the two frozen
corpora, and does a fenced `fn 0x…` then stop moving the gate while an
unfenced one still does?

## Hypothesis

The docs base has no fenced citations, so it does not change. The l3 overlay
loses exactly the citations that sit in fences. A fenced probe line leaves
both `--corpus` verdicts unchanged (exit 0), and an unfenced one gives
`CORPUS STALE: … 1 new` (exit 1). **Falsifier:** any of these is wrong:

- a docs-base row disappears;
- the fenced probe changes a verdict;
- the unfenced probe does not change a verdict.

## Inputs

| Item | Value |
| --- | --- |
| Image | `archive/head256.img`, SHA-256 above |
| Base snapshot | `docs/research/fn-audit-corpus-2026-11-16.json` (unchanged) |
| Old overlay | `docs/research/fn-audit-l3-corpus-2026-11-16.json` (1176 rows, SHA-256 `9929d9b79e47e0acdde177e44080f1d9b49eb80b7bd7a8c7a6aea8c91c553011`, kept frozen) |
| New overlay | `docs/research/fn-audit-l3-corpus-2026-11-20.json` (1017 rows, SHA-256 `c9e1b1544fb95a02eef0b7adad69172268c888a10b81effe1187806c60ab440d`) |
| Repo tool | `tools/fn_audit.py` (`fenced_lines`, `citations_markdown`) |

## Method

1. **Sample and hash** as above.
2. **Rule.** `fenced_lines(text)` marks the lines of every block that opens
   with three or more backticks or tildes (any indentation, because EXPs nest
   fences in numbered lists) and closes with the same character at least as
   long, with nothing else on that line. A backtick opener whose info string
   holds a backtick is not a fence. An **unclosed** fence hides nothing.
   `citations_markdown` drops the `fn`/`sub_` hits and the correction `ctx`
   hits on those lines in both disciplines (docs `strict=False`, l3
   `strict=True`). The `TODO.md` open-block scanner is unchanged.
3. **Commands** (worktree root):

```bash
python3 tools/fn_audit.py --selftest
python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-16.json --quiet
python3 tools/fn_audit.py archive/head256.img --scope l3 --write-snapshot docs/research/fn-audit-l3-corpus-2026-11-20.json
python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet
# done-when probes; each file is restored from a copy after the run
for f in docs/format/firmware.md docs/experiments/EXP-2026-11-16-H71-evidence-spans.md docs/format/map-tiles.md; do
  cp "$f" /home/user/scratch/bak.md
  printf '\n```\nGoal: fn 0x0041c7e8 probe\n```\n' >> "$f"
  python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet; echo "fenced exit=$?"
  cp /home/user/scratch/bak.md "$f"
  printf '\nGoal: fn 0x0041c7e8 probe\n' >> "$f"
  python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet; echo "unfenced exit=$?"
  cp /home/user/scratch/bak.md "$f"
done
python3 tools/gate.py
```

4. **Controls.**
   - *Positive* (still cited): the unfenced probe line; in the self-test, an
     unfenced `fn`, an inline code span and a line after an unclosed fence.
   - *Negative* (must not be cited): the fenced probe line; in the self-test,
     a backtick fence, a nested `~~~~` fence holding a shorter `~~~` line, and
     a correction pair inside a fence.
5. **Scope.**
   - Both corpora are covered: the docs base (`docs/format/*.md`, `TODO.md`,
     targets, `*_l3.py`) and the l3 overlay (targets, `firmware.md`, EXPs,
     open TODO blocks).
   - Unchanged: the `strict` kind rules, the US-build skip, the pin path and
     `claims_check` (H77's Scope names `fn_audit` only).
6. **Falsifier** stated above.

## Observations

- Before the change, the live scan matched both snapshots. The scan without
  fences, compared with the old snapshots: docs base `0 new / 0 gone / 156
  moved` (the moves are existing drift, exit 0); l3 overlay **`CORPUS STALE:
  L3 OVERLAY: 0 new / 159 gone / 22 moved`**, exit 1.
- Fenced citations by scope: docs 0 of 552, l3 **159 of 1176**, in 38 EXP
  files. By kind: `fn` 123, `sub_` 36. By class: START 126, GAP 18,
  INSIDE 10, UNMAPPED 5.
- The 10 INSIDE rows are all EXP quotes:
  - `0x004bda20` (M2.11), `0x003715a0` (M3.11), `0x0039ecf4` (M1.10b);
  - `0x003f52b4`, `0x003f5fc2`, `0x0040e4b2`, `0x00412bee` (M3.22);
  - `0x003f5fc2` (M3.13);
  - `0x0041c7e8` ×2 (M1.30).
- New overlay summary: files 395, citations 1017, unique VA 243, START 863,
  INSIDE 71, CORRECTED 9, GAP 67 (leaf 67), AMBIGUOUS 5, UNMAPPED 2. With it:
  `CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved`, exit 0.
- Probe results:

| Appended to | Fenced probe | Unfenced probe |
| --- | --- | --- |
| `docs/format/firmware.md` | base DRIFT 0 new, l3 OK 0 new, exit 0 | base `STALE 1 new`, l3 `STALE 1 new`, exit 1 |
| `EXP-2026-11-16-H71-evidence-spans.md` | base DRIFT 0 new, l3 OK 0 new, exit 0 | base DRIFT 0 new, l3 `STALE 1 new`, exit 1 |
| `docs/format/map-tiles.md` | base DRIFT 0 new, l3 OK 0 new, exit 0 | base `STALE 1 new`, l3 OK, exit 1 |

- `fn_audit --selftest`: 76 checks, 0 failed. The 4 new H77 checks are the
  fixture under both disciplines, the fence spans, and the backtick-info
  non-fence.
- The H77 Precheck regex prints `False` on the H71 EXP: H71's workaround
  (`$VA`) is still in place.

## Interpretation

- **FACT (C-4000):** `fn_audit` no longer cites a `fn`/`sub_`/correction VA
  inside a fenced block in any Markdown corpus. A fenced probe in
  `firmware.md`, an EXP or `map-tiles.md` leaves both `--corpus` verdicts at
  exit 0, while the same line unfenced gives `CORPUS STALE … 1 new` (exit 1).
- **FACT (C-4001):** the docs base is unchanged (0 fenced citations of 552).
  The l3 overlay loses 159 of 1176 rows (126 START, 18 GAP, 10 INSIDE,
  5 UNMAPPED; 38 EXP files).
- **OBSERVED (C-4002):** H77's Stop applies because frozen overlay rows
  change. So the scanner ships with a **new** overlay,
  `fn-audit-l3-corpus-2026-11-20.json` (1017 rows). `gate.py` and
  `selftest.py` now default to it. The 2026-11-16 overlay is kept unchanged
  as the pre-H77 record, not rewritten.
- **OBSERVED (C-4003):** the 10 removed INSIDE rows were quoted command or
  output text in EXPs, not prose claims that a VA is a function start. Their
  prose occurrences, where any exist, are still in the overlay (71 INSIDE
  remain).
- **HYPOTHESIS:** H71's `$VA` placeholder is no longer needed. Future EXPs can
  quote `fn 0x…` inside a fence.

## Conclusion

`tools/fn_audit.py` gains `fenced_lines` and applies it in
`citations_markdown`. The l3 overlay moves to a new frozen file with
before/after counts recorded here, and `gate.py`, `selftest.py`,
`tools/README.md` and the docstring name it. The old overlay is unchanged.
Still open for the navigator:

- whether to delete the 2026-11-16 overlay later;
- whether `claims_check` (named in the H77 title, not in its Scope) needs the
  same rule.

Agents that re-sync the l3 snapshot after a merge must now write the
`2026-11-20` file.

## Overtaken by a later commit

After `origin/main` was merged (new EXPs from other tasks, and `main`'s re-sync
of the 2026-11-16 overlay to 1187 rows), the l3 overlay was rewritten with the
same `--write-snapshot` command:

- the new overlay now has 1028 rows (SHA-256
  `0ad0300ff19057071999655ed2969e9be358b9f5a41e05cf2de826514e32be0c`);
- the old overlay still reports exactly `0 new / 159 gone` against the
  fence-aware scan, so the fenced set is unchanged;
- the new overlay gives `CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved`.

The 1176/1017 counts and the hash `c9e1b154…` above describe the branch before
that merge. C-4002 cites the current file.
