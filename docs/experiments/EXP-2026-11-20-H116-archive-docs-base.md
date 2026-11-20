# EXP-2026-11-20-H116: the DOCS BASE cites only live TODO blocks

- **Status:** done (navigator reviewed; see "Corrections after navigator review")
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` (EU 2011 IMG256, SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`); the
  repository `TODO.md` and Markdown corpora at the branch head.
- **Tools:** Python 3.15.0; `tools/fn_audit.py` (changed), `tools/gate.py`,
  `tools/selftest.py`, `tools/claims_check.py`, `tools/todo_check.py`
- **Claims:** C-5740, C-5741, C-5742, C-5743
- **Supersedes:** none
- **Superseded by:** none

## Question

Does the DOCS BASE corpus (`--corpus docs/research/fn-audit-corpus-2026-11-16.json`)
stop pinning VAs that sit only in a *done* `TODO.md` block, so that archiving a
finished task to a history page leaves `0 new / 0 gone`, while moving an *open*
block's VA out of the board is still detected and exits 1?

## Hypothesis

`collect("docs")` reads `TODO.md` whole-file and so cites every block, done or
not. Narrowing the `TODO.md` pass to the live blocks (`open`/`in progress`/
`blocked`, the same definition the l3 open-block scan wants per H115) and
re-freezing the corpus once makes archiving a done block a no-op for the
corpus identity set, and keeps an open block's citations protected.
**Falsifier:** moving the nine done blocks of the cycle-17 PO attempt changes
the corpus verdict (not `0 new / 0 gone`), **or** moving an open block's only
VA out no longer prints a `gone` row and exits 1.

## Inputs

| Item | Value |
| --- | --- |
| Image | `archive/head256.img`, SHA-256 `92aa525d…a007f9` (above) |
| Frozen docs base (before) | `docs/research/fn-audit-corpus-2026-11-16.json` at the branch base `d2fb7b4` (= `origin/main` at claim time), 609 rows, SHA-256 `0970f663c2af46dfcc4bddb9acf7578baca013d6657d4f721d74f649e4e75fad` |
| Frozen docs base (after) | same path, re-frozen once (this task), 466 rows, SHA-256 `a07fd7624ea5e1ece030cd70bce7d8559e062e66ad4e73f2f9478d8678a5fbea` |
| `TODO.md` | 144 done, 99 open, 21 blocked, 1 in progress blocks (0 with no `Status:` line) at the branch head; the 99 "open" include the fenced task-field template at `TODO.md:209`, whose `Status: open \| in progress \| …` enum matches `open` but whose fenced body yields no citation |
| Repo tool | `tools/fn_audit.py` (`live_todo_lines`, `citations_markdown(mask=…)`, `collect("docs")`) |

## Method

1. **Sample and hash** as above. The control image is the one the frozen
   corpus names (`image_sha256` in the JSON), so `--corpus` re-classifies every
   row against the same bytes.
2. **Rule.** `live_todo_lines(lines)` marks the lines of every block whose
   header matches `^- \[[ x]\] \*\*<ID>` and whose first `Status:` is
   `open`, `in progress` or `blocked`; a block ends at the next header, a
   `- [` item or a `## ` section (the `_open_blocks` span). `collect("docs")`
   passes the complement of that set as `citations_markdown(mask=…)` for
   `TODO.md` only, so docs/EXP/target/const corpora stay whole-file. A block
   with no matching `Status:` token stays live (so the fenced task-field template
   at `TODO.md:209`, whose enum matches `open`, stays live; its fenced body is
   still dropped by `fenced_lines`), and H77/H115 fence behaviour is untouched.
3. **Commands** (worktree root; the move is reversed in a `finally`):

```bash
python3 tools/fn_audit.py --selftest
# before (main): delete the nine done blocks and audit the old corpus
python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
# re-freeze once against the narrower definition
python3 tools/fn_audit.py archive/head256.img --write-snapshot docs/research/fn-audit-corpus-2026-11-16.json
# positive control: the nine done blocks of the cycle-17 PO attempt
python3 - <<'PY'
import re, subprocess, sys
ids = "M1.16 M1.23 M1.29 M3.2 M3.19 M4.20 M5.10 M5.12b M8.E1b".split()
todo = "TODO.md"; text = open(todo, encoding="utf-8").read(); lines = text.split("\n")
HEAD = re.compile(r"^- \[[ x]\] \*\*([A-Za-z0-9.]+)\b")
starts = [i for i, l in enumerate(lines) if HEAD.match(l)]
drop = set()
for want in ids:
    hit = [s for s in starts if HEAD.match(lines[s]).group(1) == want]
    assert len(hit) == 1, (want, len(hit))
    s = hit[0]; e = s + 1
    while (e < len(lines) and not HEAD.match(lines[e])
           and not lines[e].startswith("- [") and not lines[e].startswith("## ")):
        e += 1
    drop.update(range(s, e))
open(todo, "w", encoding="utf-8").write("\n".join(l for i, l in enumerate(lines) if i not in drop))
try:
    p = subprocess.run([sys.executable, "tools/fn_audit.py", "archive/head256.img",
                        "--corpus", "docs/research/fn-audit-corpus-2026-11-16.json",
                        "--quiet"], capture_output=True, text=True)
    print("\n".join(l for l in p.stdout.splitlines() if "CORPUS" in l or "gone " in l))
    print("exit=%d" % p.returncode)
finally:
    open(todo, "w", encoding="utf-8").write(text)
PY
# negative control: the same script with "M3.13" (a blocked block)
```
4. **Controls.** *Positive:* the nine done blocks the cycle-17 PO pass wanted
   to archive — they carry VAs, so if the fix did not narrow the scan the
   payload would go `gone`. *Negative:* the blocked `M3.13` block, whose unique
   VAs must still be reported `gone` and exit 1; the pre-fix precheck below is
   the same method before the change (must go stale).
5. **Falsifier** stated in Hypothesis, before the result.

**Precheck (before the fix, branch base `d2fb7b4` = `origin/main` at claim
time, 9 done blocks removed):**

```text
CORPUS STALE: 0 new / 17 gone / 151 moved
exit=1
```

Run in a detached worktree at `d2fb7b4` (corpus blob unchanged from `a1efe85`,
SHA-256 `0970f663…`): the `moved` count is TODO-revision-dependent — `d2fb7b4`
gives 151 moved, `a1efe85` alone gives 149 moved (both `17 gone`, exit 1). The
corpus identity change, `17 gone`, is the same at either revision.

## Observations

`python3 tools/fn_audit.py --selftest` → `selftest: OK (93 checks, 0 failed)`
(89 before this task; +4 H116 checks: done block not cited, open/in progress/
blocked cited, unmasked scan is the control, the enum-`Status` template stays live).

Corpus counts, writer before → after (both on IMG256):

```text
before: rows 609  unique VA 243  TODO rows 168  TODO classes START 139 CORRECTED 20 GAP 9
after:  rows 466  unique VA 217  TODO rows  25  TODO classes START  23 CORRECTED  0 GAP 2
before summary: files 25 citations 609 unique_va 243 START 397 INSIDE 0 CORRECTED 20 GAP 56 (leaf 56) AMBIGUOUS 0 UNMAPPED 136
after  summary: files 25 citations 466 unique_va 217 START 281 INSIDE 0 CORRECTED  0 GAP 49 (leaf 49) AMBIGUOUS 0 UNMAPPED 136
```

Only `TODO.md` rows changed: the 311 non-`TODO.md` `(file, va, kind)` keys are
identical before and after (`added [] gone []`, no file added or removed).
Where the old 168 `TODO.md` rows sat, measured against `git show a1efe85:TODO.md`
(the freeze revision, not the moved head board): 142 in done blocks, 14 in
blocked, 10 in open, 1 in progress, 1 on a section header/prose line. Mapping
the same 168 rows to the *head* board (whose headings and line numbers moved)
re-classifies a few rows into shifted blocks, so the 25 rows the re-frozen
corpus keeps (head board) are 18 open + 7 blocked (23 START + 2 GAP); 0 of
them falls outside `live_todo_lines` at the head.

Positive control (nine done blocks moved out, after the re-freeze):

```text
CORPUS DRIFT: 0 new / 0 gone / 25 moved
exit=0
```

The `25 moved` are the live-block rows shifting up when the done blocks leave
the file; the identity set `(file, va, kind, class)` is unchanged (H69 moved-only
drift, exit 0).

Negative control (blocked `M3.13` block moved out, after the re-freeze):

```text
CORPUS STALE: 0 new / 5 gone / 16 moved
fn_audit:   gone TODO.md:1794 0x003f56bc
fn_audit:   gone TODO.md:1815 0x0040114e
fn_audit:   gone TODO.md:1825 0x003f56bc
fn_audit:   gone TODO.md:1892 0x003fbed8
fn_audit:   gone TODO.md:1892 0x004125a8
exit=1
```

"Only home is a done block": 0 of the 25 re-frozen `TODO.md` rows falls
outside `live_todo_lines` (`corpus TODO rows: 25 outside live blocks: 0`,
checked with `fn_audit.live_todo_lines` against the committed JSON).

Standing gate on the image host:

```text
selftest      PASS     82.35
claims_check  PASS      5.16
todo_check    PASS      0.04
fn_audit      PASS      3.87
gate: 4 pass, 0 fail, 0 skip
```

## Interpretation

- **FACT:** The old docs base carried 168 `TODO.md` rows; at the freeze
  revision 142 sat in done blocks, 14 in blocked, 10 in open, 1 in progress, 1
  on a section header/prose. The nine done blocks of the cycle-17 set alone
  produced `0 new / 17 gone` before the change (Precheck).
- **FACT:** After the change and the single re-freeze, moving exactly those
  nine done blocks gives `0 new / 0 gone / 25 moved`, exit 0; moving the open
  `M3.13` block (a *blocked* block, still live) gives `0 new / 5 gone / 16 moved`, exit 1.
- **OBSERVED:** The non-`TODO.md` corpus is byte-for-byte the same identity
  set (311 keys), so the change is confined to the `TODO.md` pass.
- **FACT:** All 20 old `CORRECTED` rows sit in done blocks (20 done / 0 live
  at the freeze revision `a1efe85`): M1.29 8, H52 7, M1.26 2, M3.22 2, H63 1.
  The three `CORRECTION_ONLY` pins (`0x003f5fc2`, `0x00413af4`,
  `0x00542256`) are named by M1.29, H52, H63, M1.26 and M3.22 (all done); the
  narrower scan finds none of them in a live block and the l3
  `citations_open_tasks` scan (which reads only `- [ ]` blocks) yields none
  either, so the `CORRECTED 20 → 0` drop is exactly those 20 rows. The pins
  keep their `--selftest` coverage (M1.29's `CORRECTION_ONLY` pin tests).
- **UNKNOWN:** Whether the PO archive pass will find that no *live* block
  names the moved VAs; this task only makes the archive safe, it does not
  perform it.

## Conclusion

The DOCS BASE scan now cites only live `TODO.md` blocks (`live_todo_lines`,
the `_open_blocks` span), and the corpus was re-frozen
once: 609 → 466 rows, `TODO.md` 168 → 25 rows, non-`TODO.md` rows unchanged
(311 keys). Archiving the cycle-17 done set is `0 new / 0 gone` (exit 0),
while an open block's removal is still `gone` (exit 1). `tools/selftest.py`
(137 pass, 0 fail, 23 skip) and `tools/gate.py` (4 pass, 0 fail, 0 skip) are
green on the image host. `docs/format/` is unchanged; the claimed policy is in
`docs/research/claims.md` C-5740–C-5743. The PO archive itself stays a separate
pass (rule 9 of this task's Done when).

## Corrections after navigator review

The navigator re-ran the controls and required five record/count fixes; the
code fix is unchanged.

- **CORRECTED rows:** the 20 old `CORRECTED` rows are 20 done / 0 live at the
  freeze revision `a1efe85` (M1.29 8, H52 7, M1.26 2, M3.22 2, H63 1); the
  earlier "18 done / 2 in the open H41 block" was a head-offset artifact.
- **Pin attribution:** the three `CORRECTION_ONLY` pins are named by M1.29,
  H52, H63, M1.26 and M3.22 (all done); M1.16, H61 and M1.22b are not names
  the pins rely on.
- **Board breakdown:** re-measured at the branch head `2bf36c7`: 144 done,
  99 open, 21 blocked, 1 in progress, 0 blocks with no `Status:` line; the
  99 include the fenced task-field template at `TODO.md:209`.
- **Negative-control label:** `M3.13` is `blocked`, not `open`; the mask still
  cites it (blocked is live), so the control is unchanged.
- **Precheck revision:** the `0 new / 17 gone / 151 moved` precheck was run in
  a detached worktree at the branch base `d2fb7b4` (= `origin/main` at claim
  time); `a1efe85` alone gives 149 moved with the same 17 gone.

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_audit.py --selftest                      # expected: selftest: OK (93 checks, 0 failed)
python3 tools/fn_audit.py archive/head256.img --corpus docs/research/fn-audit-corpus-2026-11-16.json --quiet
# expected: exit 0 against this branch's TODO.md; the two controls in Method
# reproduce 0 new / 0 gone (nine done blocks) and 0 new / 5 gone (blocked M3.13)
```

## Follow-ups

- [ ] The PO archive pass (cycle 18) may now move the >24 h done blocks to
  `docs/research/todo-history-2026-11-20.md`; the corpus must stay at
  0 new / 0 gone after each batch.
