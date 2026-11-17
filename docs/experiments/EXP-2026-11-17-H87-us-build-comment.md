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
| Image / file | `none (docs-only task)`; `tools/fn_audit.py` lines 152–166 |
| SHA-256 | `none (docs-only task)` |
| Offset(s) / VA(s) | the 12 `US_BUILD_STARTS` entries |
| Tool / version | python3 3.15 |
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
   `0` after the edit, and the count of `US_BUILD_STARTS` must stay `12`.
4. **Scope.** The comment block only; no value, no code.
5. **Falsifier.** Stated in the Hypothesis.

## Observations

```
$ grep -n "will replace it" tools/fn_audit.py
157:# range guess; a per-build map (M1.22b) will replace it.
$ grep -c "0x0044219C\|…" tools/fn_audit.py
6
$ python3 -c "…; print(len(fa.US_BUILD_STARTS))"
12
```

After the edit: `will replace it` count `0`, `US_BUILD_STARTS` count `12`,
`fn_audit --selftest` `OK (70 checks, 0 failed)`, `todo_check` OK.

## Interpretation

- **FACT:** the comment promised a map M1.22b partially delivered (6 of 12
  entries are M1.22b's), and named M1.22b as an open replacer after it merged.
- **FACT:** the two places that now carry the map are `docs/format/firmware.md`
  (the EU→US table) and `tools/l3_harness/targets.json` (`build`); the comment
  now names them and says a per-module census is still M1.22's follow-up.
- **IMPLICATION:** no behaviour change; `fn_audit` still skips the same 12 US
  VAs.

## Conclusion

The comment describes the list as it is (12 verified US starts, the M1.28
fixture's US side plus M1.22b's six twins) and points at the two files that
carry the map. No value changed.

## Reproduction

```bash
grep -c "will replace it" tools/fn_audit.py   # 0
python3 tools/fn_audit.py --selftest          # OK (70 checks, 0 failed)
python3 tools/todo_check.py                   # todo_check: OK
```
