# EXP-2026-11-16-H81: Close the seven H51 "superseded" blocks

- **Status:** done
- **Date:** 2026-11-16
- **Sample:** `none (docs-only task)` — `TODO.md` only; no vendor bytes.
- **Tools:** python3 3.15; repo tools `tools/todo_check.py`
- **Claims:** C-4040–C-4049
- **Supersedes:** none
- **Superseded by:** none

## Question

Seven task blocks carry `Note (H51, 2026-11-11): **superseded — do not take.**`
(M1.2e, M1.2g, M8.E1c, M9.29, M9.30 open; M1.2f, M8.E1 blocked). The note says
`nk_decomp.py` (245/245 build-A sections) made them moot, and M1.19 promises to
close them on merge — but M1.19 is open and unowned. Does the board still count
five of them as takeable work, and what is the smallest honest fix?

## Hypothesis

The probe (a block walk that reads each block's `Status:` and its body) prints
all seven with their current status; five are `open`, so the open count is
inflated by five blocks nobody should take. **Falsifier:** if the five are not
`open` in the probe, or if closing them changes any board total by anything
other than `−5` open / `+5` done, the premise is wrong.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `TODO.md` at `2ebc631` (H80 merged) |
| SHA-256 | `none (docs-only task)` |
| Offset(s) / VA(s) | blocks M1.2e, M1.2f, M1.2g, M8.E1, M8.E1c, M9.29, M9.30 |
| Tool / version | python3 3.15 |
| Repo tool | `tools/todo_check.py` |

## Method

1. **Sample.** `TODO.md` at `origin/main` before this task (`2ebc631`).
2. **Commands.** The probe is H81's own Precheck (a block walk printing
   `ID status` for every block whose body contains the H51 note, excluding
   H81):
   ```bash
   python3 - <<'EOF'
   import re
   L=open('TODO.md').read().split('\n'); i=0
   while i<len(L):
       m=re.match(r'^- \[[ x]\] \*\*([A-Za-z0-9.]+)',L[i])
       if m:
           j=i+1; body=[]; st='?'
           while j<len(L) and not re.match(r'^- \[',L[j]):
               body.append(L[j])
               s=re.search(r'Status: (open|in progress|blocked|done)',L[j])
               if s and st=='?': st=s.group(1)
               j+=1
           if any('superseded — do not take' in b for b in body) and m.group(1)!='H81':
               print(m.group(1), st)
           i=j
       else: i+=1
   EOF
   echo "open=$(grep -cE '^  - Status: open' TODO.md) done=$(grep -cE '^  - Status: done' TODO.md) blocked=$(grep -cE '^  - Status: blocked' TODO.md)"
   python3 tools/todo_check.py
   python3 tools/todo_check.py --strict
   ```
3. **Controls.** *Positive*: the probe names all seven before the change.
   *Negative*: after the change the probe must show no `open` row among them,
   and the totals must move by exactly `−5` open / `+5` done with `blocked`
   unchanged; a task moved that the probe did not name would be a diff bug.
4. **Scope.** `TODO.md` only: the five open blocks go `done` with a
   `Result: superseded by H51/M1.19 …`; the two blocked ones keep `blocked`
   (their own `Unblock:` chains still point elsewhere). The history note is
   kept, no block deleted, M1.19 untouched. H81's own stale `grep -c` count
   (`11` → `10`) is corrected in its Precheck text.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

Before (probe, `2ebc631`):

```
M1.2e open
M1.2f blocked
M1.2g open
M8.E1 blocked
M8.E1c open
M9.29 open
M9.30 open
open=108 done=59 blocked=28
```

H81's Precheck text claimed `grep -c 'superseded — do not take' TODO.md`
prints `11`; it prints `10` (7 task notes + H81's own two prose lines + the
probe's literal, i.e. the raw grep is not a selector at all).

After (five closed, two left blocked, measured before H81's own block is
closed):

```
M1.2e done
M1.2f blocked
M1.2g done
M8.E1 blocked
M8.E1c done
M9.29 done
M9.30 done
open=103 done=64 blocked=28
todo_check: OK
```

Closing H81's own block then takes the final branch-head board to `open=103
done=65 blocked=28` (the reproduction below prints that).

`--strict` errors normalised by task ID go `69 → 66`: exactly the three
`M1.2e: firmware/search task missing Precheck/Scope/Stop` lines disappear
(a closed block is not checked for those), and nothing new appears.

## Interpretation

- **FACT:** five of the seven were `open`, so the board counted five
  non-takeable blocks as work; closing them moves `open 108 → 103` and
  `done 59 → 64`, with `blocked` unchanged at `28`.
- **FACT:** the two `blocked` ones keep their own `Unblock:` chain (M1.2f needs
  `sh4dis.py` shift encodings / a QEMU oracle; M8.E1 needs the same), so they
  stay `blocked` and visible rather than pointing at M1.19, which would be a
  false unblock.
- **IMPLICATION:** no measurement changed; this is board hygiene. The
  `--strict` count falling is a consequence of the closed block, not a new
  exemption.

## Conclusion

The seven H51 "superseded" blocks no longer inflate the open count: five are
`done · superseded by H51/M1.19`, two stay `blocked` with their real unblock
chain. H81's own stale `11` is corrected to the measured `10`.

## Reproduction

```bash
python3 tools/todo_check.py                # todo_check: OK
echo "open=$(grep -cE '^  - Status: open' TODO.md) done=$(grep -cE '^  - Status: done' TODO.md) blocked=$(grep -cE '^  - Status: blocked' TODO.md)"
# open=103 done=65 blocked=28   (65 counts H81 itself; the five-block move was 59->64)
```
