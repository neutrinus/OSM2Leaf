# EXP-2026-11-06-H18: Method audit of the 89 records dated 2026-11-06

- **Status:** done (review; no format fact created)
- **Date:** 2026-11-06
- **Sample:** none read in this task. The subjects are the 89 experiment records
  dated 2026-11-06 in `docs/experiments/`; every number below is a count over
  those files.
- **Tools:** `python3 3.14.4` (stdlib only), `grep`, `wc` — the audit script is
  in §Method and is four lines.
- **Claims:** none — a review creates no format claim.
- **Supersedes:** none
- **Superseded by:** none

## Question

Can each of the 89 records written in the last 24 h be **re-run by another
agent from the repository plus the named sample** — and where it cannot, is
that because the result is a tool/doc result with no sample, or because the
method was never written down precisely enough?

## Hypothesis

None / exploratory. After H17 (the ticket was under-specified) the same
question applies one level down: the records that a ticket produces. The
expected defects: scans pasted as prose or heredocs, samples without a hash,
and claims whose test could not have failed.

## Inputs

| Item | Value |
| --- | --- |
| Records | `docs/experiments/EXP-2026-11-06-*.md`, 89 files |
| Template | `docs/experiments/TEMPLATE.md` (before this task) |
| Board rules | `TODO.md` rules 11/13/14, `AGENTS.md` methodology 1–10 |
| Vendor data | none |

## Method

1. **Sample and hash:** the corpus is the 89 files dated 2026-11-06, listed by
   `ls docs/experiments/EXP-2026-11-06-*.md | wc -l`. No image is read.
2. **Commands:** one script over all 89 files, checking five properties by
   regex — a 64-hex or `SHA-256` field, a fenced command block, the word
   `control`, a `Scope`/`UNKNOWN` statement, a `tools/*.py` path — plus a
   literal search for an elided command (`# ...`):

   ```bash
   python3 - <<'PY'
   import glob, re, os
   for f in sorted(glob.glob('docs/experiments/EXP-2026-11-06-*.md')):
       t = open(f, encoding='utf-8').read(); n = os.path.basename(f)[:-3]
       print(n,
             bool(re.search(r'\b[0-9a-f]{64}\b', t) or 'SHA-256' in t),
             bool(re.search(r'^```(bash|sh|text)?\s*$', t, re.M)),
             bool(re.search(r'control', t, re.I)),
             bool(re.search(r'Scope|scoped|UNKNOWN', t)),
             bool(re.search(r'tools/[a-z0-9_]+\.py', t)),
             '# ...' in t)
   PY
   ```

3. **Controls:** the audit itself needs two. *Positive:* the same check must
   flag a record that is known to be thin (`EXP-2026-11-06-M3.5`, 19 lines) and
   must clear one that is known complete (`M5.13`, 341 lines with commands,
   hashes and refusals). *Negative:* a record with `# ...` must be caught
   (`M3.2b`) and no other file may be, otherwise the check is noise.
4. **Scope:** the five properties above are a proxy for reproducibility. A
   record can pass and still be wrong; the audit finds *missing method*, not
   wrong results. Files outside `EXP-2026-11-06-*` are out of scope.
5. **Falsifier:** if the 39 records that never say "control" turned out to be
   load-bearing measurements with no self-check, the finding would be "the
   records cannot be trusted", not "the wording is thin". They were read
   individually to test that.

## Observations

### 1. Counts over 89 records

| Property | Missing in |
| --- | --- |
| a fenced command block | 8 |
| a sample SHA-256 | 8 |
| the word "control" (or "controls") | 39 |
| a `Scope`/`UNKNOWN` statement | 27 |
| a `tools/*.py` reference | 7 |
| an elided command (`# ...`) | 1 (2 counting this record, which quotes it) |

The `Scope` and `tools/*.py` checks are a proxy: a record can state coverage
without the word "Scope", and the M8 records name a patch under
`tools/qemu-ze0/patches/` rather than a `.py`. Both are reported because the
old template asked for neither field.

### 2. The 8 records without a command block

| Record | Lines | Why | Disposition |
| --- | --- | --- | --- |
| `M2.6-mapupdate` | 32 | result moved to `firmware.md`; EXP is a pointer | **H19** re-verifies its VAs |
| `M3.5-tile-reader` | 19 | three VAs, no runnable check | **H19** |
| `M3.10-drstr-cmplst-fns` | 105 | VAs in prose, no block | **H19** |
| `M9.1-module-map` | 328 | counts only, commands implied | **H19** |
| `M8.E1-rom-decomp-tool` | 82 | corrected by M8.E1b; no block | **H19** |
| `H10-pm-review` | 63 | review of a board state | none needed (state is the sample) |
| `M6.3`/`M6.4` | 103/142 | planning documents, no measurement | none needed |

### 3. The 8 records without a sample hash

Six are tool-only tasks (`M7.4`, `M9.3`, `M9.4`, `M8.A7`, `M6.11`, `M6.11-2`):
there is no vendor sample, and the old template had no way to say that. The
remaining two (`M2.3-hddinfo-fields`, `M2.4-hddinfo-variants`) analyse an
`HDD_INFO.TXT` fixture whose hash appears in the parent record, not their own.

### 4. The 39 records that never say "control"

Read individually, most are **self-checking** and need no separate control:

- byte-identical rebuilds (`M5.10`, `M4.20`, `M4.11`, `M5.2`): the reference
  file is the control;
- round-trips (`M5.1`, `M5.4`, `M5.9`): decode→encode→compare;
- cross-year/cross-market comparison (`M4.14`, `M4.8c` with five landmarks);
- tool/docs records (`H1`, `H3`, `H4`, `H7`, `H9`, `M9.3`, `M9.4`, `M9.9`).

Two needed a closer look and hold up: `M3.12` (absence of `INDEX003`) shows the
same FAT walk finding `INDEX001` and `DRSTR` entries — an implicit positive
control — and `M1.3` (0/245 decodes) cites the decoders' own vector round-trip.
So the control gap is **wording, not substance**, and the template is the fix.

### 5. The one elided command

`M3.2b` writes `# ... anchor search over IMG256 ...` inside its Method block.
The result (14 zlib markers, a marker→module table) is therefore not
re-runnable. The same is true in prose form for M3.11 and M3.13, whose
tag/stride/mask scans exist only as descriptions: three correct negatives that
no one can reproduce.

### 6. Verification of this task's own change

```
$ python3 tools/selftest.py 2>&1 | tail -2
passed=45 failed=0 skipped=18 total=63
selftest: OK
```

## Interpretation

- **FACT:** 17 of 89 records (8 without commands, 8 without a hash, 1 elided)
  cannot be reproduced as written; a further 39 never state a control, but on
  inspection nearly all are self-checking by construction.
- **FACT:** the reproducibility defect is concentrated in the firmware-reading
  records, and specifically in the three scans behind the M3.11/M3.2b/M3.13
  negatives. That is also the work the next agent must repeat after M1.2f, so
  the cost is paid twice.
- **OBSERVED:** the old template's Method was one sentence ("Exact commands.
  Another person should be able to paste them.") and listed no controls, no
  scope and no falsifier — so the records are as precise as the template asked
  them to be. Same root cause as H17, one level down.
- **HYPOTHESIS:** with the five-part Method and a `Reproduction` block, the
  next batch will be re-runnable without a new review; M3.19 is the test of
  that hypothesis for the hardest case (a byte-pattern scan).
- **UNKNOWN:** whether any of the thin records' VAs are wrong. H19 checks that;
  this audit only measures the method, not the result.

## Conclusion

The method gap is real but narrow: three scans that no one can re-run, five
records that carry a result in prose, and a template that never asked for a
control, a scope or a falsifier. `docs/experiments/TEMPLATE.md` now carries the
five-part Method (sample+hash, runnable commands, controls, scope, falsifier),
a `Tools` field with versions, a `Reproduction` block, and an explicit
`none (tool-only task)` for records with no sample; **rule 16** makes it
binding. Two tasks finish the debt: **M3.19** commits the scanner and must
reproduce the published counts, **H19** re-verifies the five thinnest records'
VAs with committed tools.

## Reproduction

```bash
python3 - <<'PY'   # the audit; expected: 8 / 8 / 39 / 27 / 7 / 2
                   # (the last count includes this record, which quotes '# ...')
import glob, re, os
c = dict(cmd=0, sha=0, ctl=0, scope=0, tool=0, el=0)
for f in sorted(glob.glob('docs/experiments/EXP-2026-11-06-*.md')):
    t = open(f, encoding='utf-8').read()
    c['cmd'] += not re.search(r'^```(bash|sh|text)?\s*$', t, re.M)
    c['sha'] += not (re.search(r'\b[0-9a-f]{64}\b', t) or 'SHA-256' in t)
    c['ctl'] += not re.search(r'control', t, re.I)
    c['scope'] += not re.search(r'Scope|scoped|UNKNOWN', t)
    c['tool'] += not re.search(r'tools/[a-z0-9_]+\.py', t)
    c['el'] += '# ...' in t
print(c)   # {'cmd': 8, 'sha': 8, 'ctl': 39, 'scope': 27, 'tool': 7, 'el': 2}
PY
```

## Follow-ups

- [ ] **M3.19** — the committed scanner; reproduces 26/23 tag hits, 0 pairs,
      0 strides, the 282-section corpus and the 14 zlib markers.
- [ ] **H19** — the five thin records, one table, retract any VA that does not
      reproduce.
- [ ] After M3.19 merges, re-run this audit: `# ...` and "no command block"
      should be 0 for the new batch. If not, the template is not being read —
      that is a board problem, not an agent problem.