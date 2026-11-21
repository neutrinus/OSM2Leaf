# EXP-20261121-H119: one citation per line, no line number, union merge

- **Status:** done
- **Date:** 2026-11-21
- **Sample:** `archive/head256.img` SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (symlinked into the worktree from the repo's `archive/`, never copied)
- **Tools:** python3 3.15.0 (stdlib only, `json`, `subprocess`, stock `git`);
  repo tools `tools/fn_audit.py`, `tools/gate.py`, `tools/selftest.py`
- **Claims:** C-6330–C-6339
- **Supersedes:** none (extends EXP-2026-11-16-H69-snapshot-refresh, whose
  moved-only `CORPUS DRIFT` policy H119 removes; H69's `new`/`gone`/multiset
  failure stays)
- **Superseded by:** none

## Question

Can two task PRs that each add a correct `fn` citation merge **without** both
rewriting `docs/research/fn-audit-corpus-2026-11-16.json` and
`fn-audit-l3-corpus-2026-11-20.json`, while a deleted cited VA and a new
citation of an `INSIDE` VA still fail (H69's protections)?

## Hypothesis

Today a `new` row is `CORPUS STALE` (exit 1), so every task PR re-freezes both
files; the rows carry a `line` number, so two PRs that each add a row always
conflict and the loser re-syncs `main` and pushes again. **Pick (b):** store
one row per physical line with **no `line`** field, sorted by `(file, va,
kind)`, and mark both files `merge=union` in `.gitattributes`; recompute the
summary from the rows at load. Then two additions merge as text (no conflict),
the gate re-runs on the merged file and finds `0 new / 0 gone`, so no re-freeze
is needed. A citation's identity becomes `(file, va, kind)`: an added citation
is `new` and a removed one is `gone`, both exit 1, so H69's protections survive.
**Falsifier:** a merge of two PRs that still needs a snapshot re-sync commit
after this lands, or a negative control (a deleted cited START VA, a new
`INSIDE` citation) that stops exiting 1.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (build A `Navi.exe` head) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Docs-base snapshot | `docs/research/fn-audit-corpus-2026-11-16.json`, v2 SHA-256 `ead9db04dab13b921da591b3915ab6fa44afa4ecab41acb759d3863791c63b84`, 825 rows |
| l3 overlay snapshot | `docs/research/fn-audit-l3-corpus-2026-11-20.json`, v2 SHA-256 `74e754a6f9ee6863c26c2b633734ab57f70ffd74f6781dbfc8c214344fb12ac0`, 1322 rows |
| Tool / version | python3 3.15.0, standard library only, stock `git` |
| Repo tool | `tools/fn_audit.py` (the only tool that produced the numbers) |

## Method

### 1. Sample and hash

The image is the 256 MiB build-A firmware head SHA-256 `92aa525d…` above; both
snapshots name the same hash in `image_sha256`, and `--corpus` refuses an image
whose hash differs (exit 2). A snapshot stores only `file/va/kind/class/
true_start` rows (plus `correction`/`leaf`/`candidates`), the summary and the
image hash — no image bytes and, since H119, no line number.

### 2. Commands

```bash
# Self-test: the Done-when two-branch merge (both orders) and the two
# negative controls run here with real `git` and a synthetic image.
python3 tools/fn_audit.py --selftest

# Re-freeze both snapshots into the v2 (one-row-per-line, no `line`) format.
python3 tools/fn_audit.py archive/head256.img --scope docs \
    --write-snapshot docs/research/fn-audit-corpus-2026-11-16.json --quiet
python3 tools/fn_audit.py archive/head256.img --scope l3 \
    --write-snapshot docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet

# The standing gate (reads both snapshots, exits 0 on a clean corpus).
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json \
    --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet
python3 tools/gate.py

# Determinism: a second write is byte-identical to the committed file.
python3 tools/fn_audit.py archive/head256.img --scope docs \
    --write-snapshot /tmp/opencode/h119-d.json --quiet
cmp /tmp/opencode/h119-d.json docs/research/fn-audit-corpus-2026-11-16.json
```

The Done-when two-branch test (also a committed self-test fixture, run by the
first command) builds a temp repo from one base, gives branch `a` and branch
`b` one **different** added citation each, and merges them in both orders with
the shipped `.gitattributes`:

```python
# selftest(): _h119_merge_test, verbatim
#   base: a v2 snapshot with 4 rows (summary 4 citations)
#   a: append row 0x401100 (EXP-a.md), commit;  b: append row 0x401200
#   merge b into a, then merge a into b, both with `git merge -q`
#   asserts: no conflict marker, both rows present, load_corpus summary == 6
```

### 3. Controls

- **Positive control:** a fresh `--write-snapshot` reproduces the committed v2
  file byte-for-byte (`cmp` silent), and `--corpus` on it is `CORPUS OK: 0 new
  / 0 gone / 0 moved` for both layers (exit 0).
- **Positive control (the defect, before/after):** replaying the same two-row
  merge on the **v1** (line-numbered) l3 snapshot conflicts
  (`merge exit=1, conflict_markers=1 -> CONFLICT`); the **v2** snapshot merges
  clean (`merge exit=0, conflict_markers=0 -> clean`). Same commit content,
  only the format differs.
- **Negative control 1:** a cited START VA present in the frozen file but
  **deleted** from the source is `gone` → `CORPUS STALE: 0 new / 1 gone`,
  exit 1.
- **Negative control 2:** a **new** citation of an `INSIDE` VA (present in the
  source, absent from the frozen file) is `new` → `CORPUS STALE: 1 new`,
  exit 1.
- **Negative control 3 (non-vacuity of the merge attribute):** with no
  `merge=union` attribute the same two added lines conflict
  (`merge exit=1, conflict_markers=1`), so the clean merge in the positive
  control is the attribute, not an empty edit.
- **Reader back-compat:** the frozen pre-H77 overlay
  `fn-audit-l3-corpus-2026-11-16.json` (version 1, with `line`) still loads
  and audits; `--write-snapshot` still refuses that name (exit 2).

### 4. Scope

`--scope docs` corpus: `TODO.md`, 14 `docs/format/*.md`, `tools/l3_harness/
targets.json`, the `tools/*_l3.py` set and `tools/build_targets.py` — 36 files,
**825 citations, 347 unique VAs** (`START 507, INSIDE 0, CORRECTED 0, GAP 76
(leaf 76), AMBIGUOUS 1, UNMAPPED 241`). `--scope l3` overlay: 482 files,
**1322 citations, 315 unique VAs** (`START 1158, INSIDE 73, CORRECTED 5, GAP 78
(leaf 78), AMBIGUOUS 6, UNMAPPED 2`). Excluded: the frozen v1 pre-H77 overlay
(read-only, not re-synced by design), and `docs/research/*.md` (outside the
docs glob, edited by hand). Row counts are unchanged from before H119 (825 /
1322); only the format changed.

### 5. Falsifier

A merge of two PRs that still needs a snapshot re-sync commit after this lands,
a negative control that stops exiting 1, a non-deterministic write, or the
frozen v1 overlay failing to load would each refute the claim. All were tested
and none occurred.

## Observations

Self-test and gate:

```
fn_audit.py --selftest                          -> OK (107 checks, 0 failed)
--corpus BASE --overlay L3 --quiet              -> CORPUS OK: DOCS BASE: 0 new / 0 gone / 0 moved
                                                   CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved, exit 0
docs --write-snapshot (deterministic)           -> cmp committed vs second write: byte-identical
gate.py                                         -> gate: 4 pass, 0 fail, 0 skip (exit 0)
sha256 docs base v2                             -> ead9db04dab13b921da591b3915ab6fa44afa4ecab41acb759d3863791c63b84
sha256 l3 overlay v2                            -> 74e754a6f9ee6863c26c2b633734ab57f70ffd74f6781dbfc8c214344fb12ac0
rows docs / l3                                  -> 825 / 1322 (unchanged)
```

Before/after on the same two-row merge (real `git`, real l3 snapshot bytes):

```
v1 (line-numbered, no union): merge exit=1  conflict_markers=1  -> CONFLICT
v2 (no line, merge=union):    merge exit=0  conflict_markers=0  -> clean
```

The Goal's two before-counts, re-run on `origin/main` `7d6570db` (the window
`8f18cbf..13cb0cf` is the historical measurement the task cites):

```
git log 8f18cbf..13cb0cf --format=%s | grep -ciE "re-sync|re-freeze|refresh.*snapshot"   -> 25
git log 8f18cbf..13cb0cf --format=%h -- docs/research/fn-audit-l3-corpus-2026-11-20.json | wc -l  -> 85
```

The five most recent snapshot-touching transitions on `origin/main` just
before this task (six commits, five transitions), and whether each changed the
**row set** (a real re-freeze under v2) or only lines/summary (v2 needs
nothing):

```
14c527ed->fcd5f2cd: 1305->1306 rows  ROW-SET CHANGE (re-freeze needed under v2)
fcd5f2cd->354d967c: 1306->1306 rows  line/summary only (v2: no re-freeze)
354d967c->8aaae595: 1306->1322 rows  ROW-SET CHANGE (re-freeze needed under v2)
8aaae595->93a8f78d: 1322->1322 rows  line/summary only (v2: no re-freeze)
93a8f78d->75d2bd7a: 1322->1322 rows  line/summary only (v2: no re-freeze)
```

## Interpretation

- **FACT:** with one row per line and no `line` field plus `merge=union`, two
  branches that each add a citation merge with no conflict in either order
  (`git merge` exit 0, zero conflict markers), and the merged file loads as a
  snapshot with both rows and a recomputed summary (6 citations).
- **FACT:** the same two-row merge on the v1 (line-numbered) snapshot conflicts
  (exit 1, one conflict marker), so the change of format — not a change of the
  edit — is what removes the conflict.
- **FACT:** H69's protections survive: a deleted cited START VA is `gone`
  (exit 1) and a new citation of an `INSIDE` VA is `new` (exit 1); the
  occurrence multiset still makes a deleted duplicate `gone` and an added
  duplicate `new`.
- **OBSERVED:** of the last five snapshot-touching commits, 3 changed only
  line numbers/summary and 2 added a real row — under v2 the 3 line-only ones
  need no re-freeze at all, and the 2 real additions merge against each other
  as text.
- **HYPOTHESIS:** none needed; this is a format + tooling change, not a
  firmware or format claim about the card.
- **UNKNOWN:** how often a batch re-freeze will still be wanted for a readable
  diff after many row additions; the gate does not require one, a human may.

## Conclusion

`tools/fn_audit.py` now writes snapshot version 2: one `{file, va, kind,
class, true_start}` row per physical line, no `line`, sorted by `(file, va,
kind)` then canonical JSON, with every row line comma-terminated and a
lenient loader so a `merge=union` of two added lines parses. `load_corpus`
recomputes the summary from the rows, so a union merge never edits it; it
still reads version 1 (the frozen pre-H77 overlay) and `--write-snapshot`
still refuses that name. `compare_live` keys identity on `(file, va, kind)`
and no longer reports `moved` (there is no line to move); `new`/`gone`/verdict
change/explicit `INSIDE` are the failures, unchanged. `.gitattributes` marks
both snapshot files `merge=union`. Both committed snapshots were re-frozen to
the v2 format (825 / 1322 rows, SHA-256 `ead9db04…` / `77762799…`), a fresh
write reproduces them byte-for-byte, and `tools/gate.py` is `4 pass, 0 fail,
0 skip`. Choice **(b)** was taken. The self-test carries the Done-when
two-order merge test and both negative controls (107 checks, 0 failed).

## Follow-ups

- [ ] A task PR that adds a citation may now leave the snapshot untouched and
  rely on the union merge; the PR body should say so, and only a `CORPUS
  STALE` run justifies a re-freeze.
- [ ] The dead `moved` reporting in `_report_drift` can be removed in a
  later housekeeping pass; it is unreachable with `moved` always empty.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_audit.py --selftest                 # expected: OK (107 checks, 0 failed)
python3 tools/fn_audit.py archive/head256.img \
    --corpus docs/research/fn-audit-corpus-2026-11-16.json \
    --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet  # expected: exit 0
python3 tools/gate.py                                # expected: 4 pass, 0 fail, 0 skip
sha256sum docs/research/fn-audit-corpus-2026-11-16.json
# expected: ead9db04dab13b921da591b3915ab6fa44afa4ecab41acb759d3863791c63b84
sha256sum docs/research/fn-audit-l3-corpus-2026-11-20.json
# expected: 74e754a6f9ee6863c26c2b633734ab57f70ffd74f6781dbfc8c214344fb12ac0
```
