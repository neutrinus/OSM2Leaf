# EXP-2026-11-20-H115: fn_audit open-block scan is fence-aware

- **Status:** done
- **Date:** 2026-11-20
- **Sample:** `archive/head256.img` SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (only used to run the real l3 gate; the fix itself is pure text parsing)
- **Tools:** `python3 3.15.0` (`zlib 1.3.1.zlib-ng`, irrelevant here — no
  recompression), `tools/fn_audit.py`
- **Claims:** C-5720–C-5729
- **Supersedes:** none
- **Superseded by:** none

## Question

Does `tools/fn_audit.py`'s l3 open-block corpus (`_open_blocks`,
`citations_open_tasks`) treat the fenced task-field template in `TODO.md` as a
live task and a `0x…` quoted inside a fenced example as a live citation?

## Hypothesis

H77 made the Markdown corpora skip fenced code, but `_open_blocks` still scans
`TODO.md` line by line, so the `- [ ] **ID — title**` header inside the
```text``` template fence (line 209) is parsed as a real open block, and any
`0x…` in a fence under a live block is cited. Falsifier: if the pre-fix code
already excludes the fenced template and fenced VAs, the task is a no-op.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Offset(s) / VA(s) | `TODO.md` fences at lines 208–221 and 313–340; template header `- [ ] **ID — title**` at line 209 |
| Tool / version | `python3 3.15.0` |
| Repo tool | `tools/fn_audit.py` (`_open_blocks`, `citations_open_tasks`, `fenced_lines`) |

## Method

1. **Sample and hash.** `archive/head256.img` above; the text corpus is the
   committed `TODO.md` at this branch.
2. **Commands.** From the repo root:

   ```bash
   # fences in TODO.md
   grep -n '^```\|^~~~' TODO.md

   # pre-fix open-block census on the real board
   git show HEAD:tools/fn_audit.py > /tmp/fn_audit_old.py   # or the base SHA
   python3 - <<'PY'
   import sys; sys.path.insert(0, 'tools')
   import fn_audit
   t = open('TODO.md').read().split('\n')
   print('open blocks', len(fn_audit._open_blocks(t)))
   print('counts', fn_audit.open_block_counts('\n'.join(t)))
   PY

   # the l3 scan and the image gate
   python3 tools/fn_audit.py archive/head256.img --scope l3 --quiet
   python3 tools/fn_audit.py archive/head256.img --corpus \
     docs/research/fn-audit-corpus-2026-11-16.json \
     --overlay docs/research/fn-audit-l3-corpus-2026-11-20.json --quiet

   # selftest and gate
   python3 tools/fn_audit.py --selftest
   python3 tools/selftest.py --only fn_audit
   python3 tools/gate.py
   ```

3. **Controls.**
   - *Positive:* a synthetic board whose top-level ```text``` fence holds the
     template header and whose open block fences a live label
     (`0x0041c005`); unfenced, the same VA is cited (proves the fence hides it,
     not the VA shape).
   - *Negative (mandatory pair-review, gate task):* a real, valid START VA
     (`0x004125a8`) injected inside a fence in the live H115 block body of
     `TODO.md`; the old code cites it and the fix does not. Complete script:

     ```python
     import sys, importlib.util
     sys.path.insert(0, 'tools')

     def load(name, path):
         spec = importlib.util.spec_from_file_location(name, path)
         mod = importlib.util.module_from_spec(spec)
         sys.modules[name] = mod
         spec.loader.exec_module(mod)
         return mod

     # pre-fix tool from the branch base
     import subprocess
     base = subprocess.check_output(
         ['git', 'show', '2e683be:tools/fn_audit.py'], text=True)
     open('/tmp/fn_audit_old.py', 'w').write(base)
     old = load('fn_audit_old', '/tmp/fn_audit_old.py')
     import fn_audit as new

     lines = open('TODO.md', encoding='utf-8').read().split('\n')
     for i, line in enumerate(lines):
         if line.startswith('- [ ] **H115 —'):
             ins = i + 3
             break
     lines[ins:ins] = ['  ```text',
                       '  example fn 0x004125a8 quoted in a fence',
                       '  ```']
     text = '\n'.join(lines)
     for label, mod in (('OLD', old), ('NEW', new)):
         hits = [c.where for c in mod.citations_open_tasks(text)
                 if c.va == 0x004125a8]
         print(label, hits)   # OLD names TODO.md:1428, NEW does not
     ```
   - *Negative:* a done block's `0x0041c004` is not cited (H116 control
     still holds).
4. **Scope.** Todo-text parsing only: `TODO.md` open blocks. The docs base and
   EXP corpora already follow `fenced_lines` (H77); no TODO text was edited.
5. **Falsifier.** Stated in the Hypothesis: if the pre-fix scan already
   excluded both the fenced template header and the fenced VA, the report would
   show no before/after change.

## Observations

`grep -n '^```\|^~~~' TODO.md`:

```
208:```text
221:```
313:```bash
340:```
```

Pre-fix, `_open_blocks` on the real `TODO.md`: `open blocks 116`, and the
template header at line 209 is one of them
(`any(s == 208 for s, e in blocks)` is `True`). The template block spans lines
209–250 (42 lines) because a fenced `## ` / `- [` line is also treated as a
boundary.

`open_block_counts` before: `(116, 7, 14)`; after: `(115, 7, 14)` — one block
gone, the same 7 contributing blocks and 14 citation lines. Measured at the
branch base `2e683be` (= `origin/main` at claim time). After rebasing onto
`origin/main` `3d263f9` (the H97 merge changed the live set) the same pair is
`old (115, 6, 13) → new (114, 6, 13)`: one block gone at either revision, the
`7/14` → `6/13` drop is H97's own merge, not this change.

Synthetic mutation control (template fenced at column 0, a VA fenced inside a
real open block):

```
OLD: open blocks [(2, '- [ ] **ID — title**'), (7, '- [ ] **H999 — real open task**')]
     citations include (0x0041c002, 'TODO.md:4') and (0x0041c002, 'TODO.md:11')
NEW: open blocks [(7, '- [ ] **H999 — real open task**')]
     citations (0x0041c001, ':9'), (0x0041c003, ':13') only
```

Live-board negative mutation (inject the real START VA `0x004125a8` in a fence
at what becomes `TODO.md:1428` inside the H115 block):

```
OLD fenced 0x004125a8 citations: ['TODO.md:1246', 'TODO.md:1428', 'TODO.md:1810', 'TODO.md:1911']
NEW fenced 0x004125a8 citations: ['TODO.md:1246', 'TODO.md:1810', 'TODO.md:1911']
```

Real gate on the unchanged board (pre-rebase, base `2e683be`):

```
fn_audit: open blocks 115, contributing 7, citation lines 14
L3 OVERLAY: 417 file(s) scanned, 1076 citation(s), 263 unique VA(s)
CORPUS OK: DOCS BASE: 0 new / 0 gone / 0 moved
CORPUS OK: L3 OVERLAY: 0 new / 0 gone / 0 moved
```

`tools/fn_audit.py --selftest`: `OK (99 checks, 0 failed)` (was 93 before
H115's 6 checks). `tools/selftest.py --only fn_audit`: `PASS`. `tools/gate.py`:
`gate: 4 pass, 0 fail, 0 skip` (fn_audit `PASS`, not `SKIP`, with the image
present).

After rebasing onto `origin/main` `3d263f9` (H97 merge), the l3 scan reads
`open blocks 114, contributing 6, citation lines 13` (one block gone at this
revision too; `7/14 → 6/13` is H97's merge). The frozen corpora still compare
as line-only drift:

```
CORPUS DRIFT: DOCS BASE: 0 new / 0 gone / 22 moved
CORPUS DRIFT: L3 OVERLAY: 0 new / 0 gone / 16 moved
```

`gate.py` remains `4 pass, 0 fail, 0 skip` at this revision.

Corpus row counts unchanged: l3 overlay `1076` rows, docs base `521` rows — no
re-freeze was required because no cited row was ever fenced on the real board
(17 open-block citations at `2e683be`, 0 on fenced lines pre-fix).  The H115
claim/`Result` lines added a line to `TODO.md`, so the frozen corpora show a
line-only drift (`DOCS BASE 22 moved`, `L3 OVERLAY 15 moved` at `2e683be`,
`16 moved` after the `3d263f9` rebase); a line move is prose drift (H69) and
exits 0, not a re-freeze.

**Correction (gate retry):** the first EXP draft quoted the two control VAs as
a live `fn` label and the gate named them as three new l3 rows
(`EXP-…-H115…md:72`, `:75`, `:111`); the prose above now writes them as bare
`0x…` ctx values, which the l3 discipline skips (no correction-marker word).
The complete control script in §Method still spells the VA it injects, inside
a fence, exactly as the injected fence does.

## Interpretation

- **FACT:** the pre-fix `_open_blocks` counted the fenced template header as a
  block (116 blocks at `2e683be`, one of them line 209); post-fix it is 115
  (114 at `3d263f9` after the H97 merge).
- **FACT:** the pre-fix `citations_open_tasks` cites a `fn 0x…` inside a fence
  under a live block; post-fix it does not. Both are proven by the mutation
  control (old reports `TODO.md:1428`, new does not).
- **OBSERVED:** no real board row moved — the template block carries no
  citation and no live block currently fences a VA, so the frozen l3 and docs
  corpora keep their identity (`0 new / 0 gone`, 1076 / 521 rows); only line
  moves (the claim/`Result` prose) show, as H69 prose drift.
- **HYPOTHESIS:** the counted extra block was harmless today only because the
  template spells no cited VA; the H115 Stop rule (an unbalanced fence hides
  nothing) is satisfied — all four fences are balanced.
- **UNKNOWN:** none.

## Conclusion

`tools/fn_audit.py` `_open_blocks` now uses `fenced_lines` so a fenced
`- [ ]`/`## ` line is never a block start or a boundary, and
`citations_open_tasks` skips fenced lines. Reported open blocks on the real
board drop by exactly one (the template) at either measured revision
(`116 → 115` at `2e683be`, `115 → 114` at `3d263f9`); contributing blocks and
citation lines are unchanged by this change, and both frozen corpora
(`1076` l3 / `521` docs rows) show line-only drift, so no snapshot re-freeze was
needed. Selftest grows to 99 checks; `gate.py` is `4 pass, 0 fail, 0 skip`. No
`docs/format` change (this is gate plumbing).

## Overtaken by a later commit

none

## Reproduction

```bash
python3 tools/fn_audit.py --selftest     # expected: OK (99 checks, 0 failed)
python3 tools/fn_audit.py archive/head256.img --scope l3 --quiet \
  | grep 'open blocks'                    # expected: open blocks 115, contributing 7, citation lines 14
python3 tools/gate.py                     # expected: gate: 4 pass, 0 fail, 0 skip
```

## Follow-ups

- [ ] none — the H115 Stop rule was not needed (fences balanced).
