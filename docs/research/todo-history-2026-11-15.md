# TODO history — 2026-11-15 (PO grooming archive)

Done tasks moved from `TODO.md` on 2026-11-15: `Status: done`, block no
open/in-progress/blocked task's `Depends:` or `Unblock:` (checked by script
against every live block), and completed on `origin/main` more than 24 h ago
(commit dates on `origin/main` are the authority; completion dates below are
the last TODO change of each block). Earlier archives:
`todo-history-2026-11-05.md`, `-06.md`, `-09.md`, `-13.md`.

M1.23 (done 2026-11-15) is **not** archived: live blocks name it in `Depends:`.
H55 is **not** archived: it is less than 24 h old.

## H

- [x] **H50 — Put `va_class` into the prechecks and audit the remaining "sec1" blockers**
  - Status: done · Owner: task/h50-va-class-prechecks · Critical: yes
  - Depends: H49
  - Goal: no task may again say "blocked: compressed sec1/.data" for an import slot or a BSS address.
  - Precheck: `python3 tools/va_class.py --selftest`; `python3 tools/l3_precond.py --selftest`; `python3 tools/reader_precheck.py --selftest`.
  - Scope: (1) `tools/l3_precond.py` and `tools/reader_precheck.py` import `va_class.classify` and print the class of every VA they report as compressed/unmapped (`IAT DLL!name` / `BSS` / `INIT`); `l3_precond` returns `BLOCKED` on M1.2f only for `INIT`. (2) Audit the blockers of **M3.2b, M3.14, M3.16, M4.26, M2.17, M1.12 follow-up** and any other `blocked` task whose text says sec1/compressed `.data`/M1.2f: run `va_class` on each cited VA, and per rule 15 re-open (with a note) every task whose cited address is IAT or BSS.
  - Input: EXP-2026-11-10-H49-pm-review; `tools/va_class.py`; the listed EXPs.
  - Done when: both selftests cover an IAT, a BSS and an INIT case; an EXP lists each audited task, its cited VAs, their classes and the board action; `todo_check.py` and `claims_check.py` pass.
  - Stop: if a cited "sec1" blocker has no VA at all, write that in the EXP and leave the task as is with a note asking its next owner for the VA; do not invent one.
  - Result: docs/experiments/EXP-2026-11-10-H50-va-class-prechecks.md (C-3470–C-3479). va_class integrated into l3_precond/reader_precheck (IAT/BSS not M1.2f, INIT M1.2f); audit reopened M3.11c,M3.13,M4.16b,M9.14,M9.17 per rule 15 (IAT/BSS cited blockers), left no-VA/INIT/codec/runtime blockers closed with notes; M4.26/M2.17/M1.12-follow-up task blocks not found (stated in EXP).
  - Claims: C-3470–C-3479


Done: M1.1 (synthetic self-test, EXP-47), M1.5 (`cerom.py memmap`/`ghidra`,
EXP-48; the real Ghidra open is M9.2), M1.6 (`cerom.py imports`, EXP-50,
PR #5). Tool half of M1.2b: `tools/cecompress.py` (4 KiB LZSS and LZX
stored blocks, verbatim/aligned refused; synthetic only, EXP-52, C-570).

## M1

- [x] **M1.10b — Spot-check two resolved import names at their call sites**
  - Status: done · Owner: task/m1.10b-import-spotcheck · Critical: no
  - Depends: — (M1.10 done)
  - Goal: M1.10 named 846/846 `Navi.exe` slots by export-table lookup. Two of
    the newly named exporters (`XGLDLL`, `OSMDLL`) should be confirmed where
    they are **called**, so the resolution is not just a plausible name.
  - Precheck: `cerom.py imports Navi.exe --resolve-with 0x200200 --resolve-with
    0x3e00200 --resolve-with 0x5200200` must list both names.
  - Scope: two slots, one call site each; no new naming pass.
  - Done when: for one `XGLDLL!` and one `OSMDLL!` name, `sh4xref.py --calls`
    (or the thunk table) shows the call site and the argument shape matches the
    export's role; recorded in an EXP with the slot VAs.
  - Stop: if a call site cannot be found, say so and stop — a name without a
    caller stays `OBSERVED`.
  - Claims: C-2600–C-2609
  - Result: EXP-2026-11-08-M1.10b-import-spotcheck. `OSMDLL!OSM_Printf` slot `0x0055d954` confirmed at `fn 0x0039c978`/`0x0039c9ba` (4 args, printf-style-consistent; 88 loads/24 pools); `XGLDLL!xglDisable` slot `0x0055db94` at `fn 0x003da074`/`0x003da0aa` (2 args, `r5=0x00800000`, capability-consistent; 42 loads/21 pools). Names via M1.10 export resolution; exact prototypes UNKNOWN. Selftest/claims_check green.

