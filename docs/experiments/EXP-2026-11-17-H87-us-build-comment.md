# EXP-2026-11-17-H87: The `US_BUILD_STARTS` comment is not a placeholder

- **Status:** done
- **Date:** 2026-11-17
- **Sample:** `none (docs-only task)` — one comment in `tools/fn_audit.py`.
- **Tools:** python3 3.15; repo tools `tools/fn_audit.py` (`--selftest`),
  `tools/todo_check.py`
- **Claims:** C-4100–C-4109
- **Supersedes:** none
- **Superseded by:** none

## Question

The comment above `US_BUILD_STARTS` said "a per-build map (M1.22b) will replace
it". M1.22b merged. Does the comment now name an open task that is done, and
what should it say instead?

## Hypothesis

M1.22b merged and added six US VAs to the list, so the comment's promise is
already partly kept; a reader who greps `M1.22b` sees a task that looks open.
**Falsifier:** if the comment already names the map's new homes, the task is
no-op and should be closed without an edit.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `none (docs-only task)`; `tools/fn_audit.py` `US_BUILD_STARTS` block |
| SHA-256 | `none (docs-only task)` |
| Offset(s) / VA(s) | the 12 `US_BUILD_STARTS` entries at `381879b`; 15 at `398db35` (H91) |
| Tool / version | python3 3.15.0 |
| Repo tool | `tools/fn_audit.py --selftest` |

## Method

1. **Sample.** `tools/fn_audit.py` at `origin/main` `857c9a7`.
2. **Commands.**
   ```bash
   grep -n "will replace it" tools/fn_audit.py          # 1 line -> the rot
   grep -c "0x0044219C\|0x004410B4\|0x0043A378\|0x00433458\|0x003EC274\|0x0041EB1C" tools/fn_audit.py  # 6
   python3 -c "import sys; sys.path.insert(0,'tools'); import fn_audit as fa; print(len(fa.US_BUILD_STARTS))"  # 12
   python3 tools/fn_audit.py --selftest
   python3 tools/todo_check.py
   ```
3. **Controls.** *Positive*: the six M1.22b VAs are present, so the list did get
   the promised extension. *Negative*: `grep -c "will replace it"` must go to
   `0` after the edit, and the count of `US_BUILD_STARTS` must stay `12` at
   `381879b` (the revision H87 measured). It is not `12` on `main`: H91 measured
   `15` at `398db35`, because `e199373` added the three POINT-walker starts and
   four pool slots (`19`) and `398db35` removed the four slots.
4. **Scope.** The comment block only; no value, no code.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

At `381879b` (H87's record commit; the sample `857c9a7` prints the same
numbers):

```
$ grep -n "will replace it" tools/fn_audit.py
157:# range guess; a per-build map (M1.22b) will replace it.
$ grep -c "0x0044219C\|…" tools/fn_audit.py
6
$ python3 -c "…; print(len(fa.US_BUILD_STARTS))"
12
```

After the edit, at `381879b`: `will replace it` count `0`, `US_BUILD_STARTS`
count `12`, `fn_audit --selftest` `OK (70 checks, 0 failed)`, `todo_check` OK.

At `398db35` (the merged M1.22 record, what `main` `9beb6a4` ships, H91):
`US_BUILD_STARTS` count `15`, `fn_audit --selftest`
`OK (72 checks, 0 failed)`.

## Interpretation

- **FACT:** the comment promised a map M1.22b partially delivered (6 of the 12
  entries at `381879b` are M1.22b's, `grep -c` of the six VAs prints `6`), and
  named M1.22b as an open replacer after it merged.
- **FACT:** the two places that now carry the map are `docs/format/firmware.md`
  (the EU→US table) and `tools/l3_harness/targets.json` (`build`); the comment
  now names them and says a per-module census is still M1.22's follow-up.
- **IMPLICATION:** no behaviour change at `381879b`: `fn_audit` still skips the
  same 12 US VAs there. The list later grew to 15 (four pool slots added at
  `e199373`, removed at `398db35`) — H91 pins that, not H87.

## Conclusion

At `381879b` the comment describes the list as it is (12 verified US starts,
the M1.28 fixture's US side plus M1.22b's six twins — `git show
381879b:tools/fn_audit.py | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x0044219C\|0x004410B4\|0x0043A378\|0x00433458\|0x003EC274\|0x0041EB1C'`
prints `6`) and points at the two files that carry the map. No value changed.
At `main` the list is 15 entries; EXP-2026-11-18-H91 records that move.

## Reproduction

The record's own result, at its revision `381879b` (not at `main`; `main` ships
15 entries and 72 checks, see EXP-2026-11-18-H91):

```bash
git show 381879b:tools/fn_audit.py | grep -c "will replace it"   # 0
git show 381879b:tools/fn_audit.py \
  | sed -n '/^US_BUILD_STARTS/,/^})/p' | grep -c '0x[0-9A-Fa-f]\{8\}'   # 12
```
