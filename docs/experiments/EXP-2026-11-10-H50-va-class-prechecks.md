# EXP-2026-11-10-H50: va_class in prechecks and audit of "compressed sec1" blockers

- **Status:** done
- **Date:** 2026-11-10
- **Sample:** `archive/head256.img` (IMG256, first 256 MiB of
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`), SHA-256
  `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`
  (`python3 tools/fetch_image.py --image IMG256 -o archive/head256.img`,
  verified). Build A at image start `0x200200`; ordinals resolved with build B
  at `0x3e00200` (default for build-A).
- **Tools:** python 3 (stdlib); repo tools `tools/va_class.py`,
  `tools/l3_precond.py`, `tools/reader_precheck.py`, `tools/cerom.py`,
  `tools/todo_check.py`, `tools/claims_check.py`, `tools/selftest.py`.
- **Claims:** C-3470–C-3479
- **Supersedes:** none (extends H49 EXP-2026-11-10-H49-pm-review application in prechecks/board)
- **Superseded by:** none

## Question

Do `l3_precond.py` and `reader_precheck.py` make loader class explicit for every
compressed/unmapped VA they report and gate M1.2f only on `INIT`? Which blocked
tasks citing sec1/compressed `.data`/M1.2f have cited blocker VAs that are `IAT`
or `BSS` (and must be reopened per rule 15), versus `INIT`, no concrete VA, or
non-Navi blocker addresses?

## Hypothesis

H49 classified cited `0x0055dxxx` blocker addresses as import slots (IAT) or
BSS, not INIT. If prechecks classify VAs via `va_class.classify` and apply
M1.2f only to `INIT`, IAT/BSS cases will be reported with correct concern
(import/binding/stub or writer/runtime init) and not as M1.2f blockers, while
INIT remains M1.2f-blocked. Falsifier: any IAT/BSS VA reported/gated as M1.2f,
any INIT VA not reported as M1.2f-blocked when applicable, or any audited
IAT/BSS blocker VA left closed / any INIT or no-VA task reopened.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | `archive/head256.img` (IMG256) |
| SHA-256 | `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` |
| Repo tools | `tools/va_class.py`, `tools/l3_precond.py`, `tools/reader_precheck.py` |
| Audit scope | mandatory: M3.2b, M3.14, M3.16, M4.26, M2.17, M1.12 follow-up; plus every blocked task whose text cites sec1/compressed `.data`/M1.2f |

## Method

1. **Sample and hash:** IMG256 fetched/verified as above.
2. **Commands (reproducible):**

```bash
python3 tools/fetch_image.py --image IMG256 -o archive/head256.img
python3 tools/va_class.py --selftest
python3 tools/l3_precond.py --selftest
python3 tools/reader_precheck.py --selftest
python3 tools/va_class.py archive/head256.img --module Navi.exe --resolve-with 0x3e00200 \
  0x0041a438 0x0055d040 0x00d53500 0x0055e000 0x0055d8f0 0x005628e8 0x00840ba0 \
  0x0055d8fc 0x00e23cc0 0x0055d000 0x00ff16ae
python3 tools/todo_check.py TODO.md
python3 tools/claims_check.py
python3 tools/selftest.py --only va_class --only l3_precond --only reader_precheck
python3 tools/selftest.py
```

3. **Controls.**
   - *Positive (va_class/tool):* `va_class --selftest` passes (CODE/IAT/INIT/BSS/UNKNOWN/OUTSIDE). On IMG256: `0x0041a438`→CODE sec0, `0x0055d040`→IAT `COREDLL!memset`, `0x00d53500`→BSS sec1, `0x0055e000`→INIT sec1 (control).
   - *Positive (prechecks):* `l3_precond --selftest` covers IAT,BSS,INIT (synthetic va_class context, no vendor data): IAT/BSS not M1.2f-blocked with correct concern/class shown, INIT M1.2f-blocked; adhoc and JSON expose classes. `reader_precheck --selftest` covers IAT,BSS,INIT in compressed/unmapped reporting (synthetic va_class context) and preserves real build-A pins when image found.
   - *Negative:* INIT VA remains M1.2f-blocked (`0x0055d100` synthetic / `0x0055e000` control). Unknown/no-image yields UNKNOWN/`va_class_status=no-image` and never guessed READY/non-M1.2f. No-VA blockers not classified, not invented, not reopened.
4. **Scope.** Build A / `Navi.exe` VA classification on IMG256 for every concrete hex VA cited in audited blocked tasks (classified via `va_class.py --module Navi.exe --resolve-with 0x3e00200`); kernel/build-B VAs and non-module markers classify OUTSIDE relative to Navi.exe as reported. Exhaustive audit over TODO blocked tasks whose text cites `sec1`, `compressed .data`, `compressed sec`, or `M1.2f` (see Observations). No vendor bytes committed.
5. **Falsifier.** Stated in Hypothesis; additionally `todo_check.py`, `claims_check.py`, or any of `va_class`/`l3_precond`/`reader_precheck`/`selftest.py` failing.

## Observations

### Tool integration (ce004bc)

- `tools/va_class.py`: added `build_context`, `extract_hex_vas`, `format_class` helpers for reuse (no IAT/INIT/BSS logic re-derived outside va_class).
- `tools/l3_precond.py`: imports va_class/cerom; builds va_class context once per module when image+module available (`--resolve-with`, default `0x3e00200` for build-A); classifies entry VA and concrete in-module hex VAs surfaced as compressed/unmapped/M1.2f-related; reports `va_classifications`/`va_class_status` in text/JSON. M1.2f dimension overridden by image-derived class: INIT => blocker; IAT/BSS => not M1.2f (replaced with import/binding/stub or writer/runtime-init concern), without flipping overall verdict to READY when independent blockers remain. Adhoc path classifies VAs the same way. No-image/metadata-only remains honest.
- `tools/reader_precheck.py`: imports va_class; computes sections/import slots per module (`--resolve-with`, default `0x3e00200` for build-A); prints class for COMPRESSED-ANCHOR anchor VAs and for edge/call targets and reported VAs in compressed/unmapped sections (`target_class` / `va_class=...`). Core scan semantics and verdict/exit-code meaning unchanged except explicit class detail.

### Check results

- `python3 tools/va_class.py --selftest` → OK (8 cases).
- `python3 tools/l3_precond.py --selftest` → all checks passed (existing + H50 IAT/BSS/INIT, adhoc, JSON, no-image honesty).
- `python3 tools/reader_precheck.py --selftest` → synthetic PASS, real build-A pins PASS (head256.img).
- `python3 tools/todo_check.py TODO.md` → `todo_check.py: OK (0 errors, 29 warnings, 90 tasks)`.
- `python3 tools/claims_check.py` → `claims_check.py: OK (no duplicate IDs, no referenced-but-unregistered claims, 687 definitions)`.
- `python3 tools/selftest.py` → `Total 91 — 76 passed, 0 failed, 15 skipped` (includes va_class/l3_precond/reader_precheck PASS).

### IMG256 control classifications (Navi.exe, --resolve-with 0x3e00200)

| VA | va_class | Detail |
| --- | --- | --- |
| 0x0041a438 | CODE | sec0 |
| 0x0055d040 | IAT | COREDLL.dll!memset |
| 0x00d53500 | BSS | sec1 +0x7f6500 >= init 0x1801a (zero at load; find the writer) |
| 0x0055e000 | INIT | sec1 +0x1000 < init 0x1801a (needs M1.2f) |

### Audit: mandatory set and every blocked task citing sec1/compressed `.data`/M1.2f

Mandatory set named by H50: **M3.2b, M3.14, M3.16, M4.26, M2.17, M1.12 follow-up**.
`M4.26` task block: **not found by ID/name in TODO.md** (stated explicitly).
`M2.17` task block: **not found by ID/name in TODO.md** (stated explicitly).
`M1.12 follow-up` task: **not found by that name as a TODO task block** (stated explicitly; H50 scope line 421 names it; "follow-up" text appears elsewhere but is not a task block of that name).

All blocked tasks with text matching sec1/compressed `.data`/M1.2f were audited (see table). Classes below are `tools/va_class.py` results on IMG256 for cited hex VAs (Navi.exe context where applicable; kernel/build-B/file-offset/marker VAs correctly OUTSIDE Navi.exe).

| Task | Status (pre) | Cited VAs (hex in block) | va_class result(s) + detail | Board action |
| --- | --- | --- | --- | --- |
| M3.2b | blocked | 0x00200200, 0x0041c7e8, 0xc8002040 | CODE sec0; CODE sec0; OUTSIDE no section (flag) | No concrete sec1 blocker VA cited (indirect slot location unnamed). **No-VA**: leave blocked, add note asking next owner for concrete VA. No reopen. |
| M3.14 | blocked | 0x00179338, 0x003f2cc0 | CODE sec0; CODE sec0 | No cited IAT/BSS/INIT blocker VA (metadata/signature blocker). Leave blocked. No reopen. |
| M3.16 | blocked | 0x00179338, 0x0017934c, 0x00179354, 0x003fbed8, 0x0040b358, 0x004125a8 | all CODE sec0 | No cited blocker VA in compressed/unmapped data. Leave blocked. No reopen. |
| M1.4 | blocked | 0x03e00200, 0x8d80805b | OUTSIDE (build-B start, LZXD marker) | CE-LZXD/INIT-bytes codec blocker, not Navi IAT/BSS VA. Leave blocked. No reopen. |
| M1.2f | blocked | 0x00200200, 0x01580ce0, 0x015aca7c, 0x03e00200, 0x88034d94, 0x88037464, 0x8803a248, 0x8803a384, 0x8d80805b | CODE sec0; others OUTSIDE Navi.exe (file offsets / nk.exe VAs / marker) | Codec task for real INIT bytes (per H49 note). No cited Navi IAT/BSS blocker VA. Leave blocked (non-critical). No reopen. |
| M3.2 | blocked | 0x00010000, 0x00418748 | OUTSIDE; CODE sec0 | No concrete sec1 blocker VA. Leave blocked. No reopen. |
| M3.11c | blocked | 0x0003ceac…0x003f9400 (many CODE), **0x0055d8f0**, **0x005628e8**, **0x00840ba0**, **0x00d53500** | CODE VAs; **IAT OSMDLL!taskIdSelf**; **INIT sec1 +0x58e8 < init 0x1801a (needs M1.2f)**; **BSS sec1 +0x2e3ba0 (zero at load)**; **BSS sec1 +0x7f6500 (zero at load)** | **Mixed (explicit per VA):** cited blocker VAs 0x0055d8f0 (IAT) and 0x00d53500 (BSS) => M1.2f not needed for them (H49/M9.35/M3.22). 0x005628e8 is INIT (real M1.2f concern if needed) but appears in result/fallback context, not stated as the HDLMAP blocker; 0x00840ba0 is BSS (page location in result). **Rule 15 reopen** because cited blocker VAs classify IAT/BSS; reopen note states IAT/BSS unblocked concerns and keeps original blocker, and explicitly notes INIT 0x005628e8 would remain M1.2f if required. |
| M3.13 | blocked | 0x00179338, 0x003f51e0, 0x003f56bc, 0x003f56ec, 0x003f5d98, 0x003f61bc, 0x003fbed8, 0x0040114e, 0x0040b358, 0x004125a8, **0x00d53500** | CODE VAs; **BSS sec1 +0x7f6500 (zero at load; find the writer)** | **Cited blocker/binding VA 0x00d53500 is BSS**. Rule 15 reopen with note (writer/runtime init, M9.35 context where relevant); keep original blocker. |
| M3.18 | blocked | 0x00178c60, 0x00178c68, 0x00178e08, 0x00179338, 0x003f1640, 0x003f2cc0, 0x003fbed8, 0x0040b358, 0x004125a8 | all CODE sec0 | No cited blocker VA in compressed/unmapped data. Leave blocked. No reopen. |
| M4.16b | blocked | 0x00200200, 0x003f51e0, 0x003f52b8, 0x003f56bc, 0x003f5e10, **0x0055d000** (range start), **0x00d53500**, **0x00ff16ae** (range end), 0x0154e6ae, 0xc8002040 | CODE VAs; **IAT COREDLL!Sleep** (sec1 start/boundary mention); **BSS sec1 +0x7f6500** (schema descriptor, cited blocker); **BSS sec1 +0xa946ae** (boundary); OUTSIDE/flag | **Cited blocker VA 0x00d53500 is BSS** (schema bytes not stored as INIT there). 0x0055d000/0x00ff16ae appear as section/range bounds; 0x0055d000 classifies IAT but is not the schema blocker. Rule 15 reopen on cited BSS blocker with explicit per-VA note. |
| M8.E1 | blocked | 0x00ff16ae, 0x08000000, 0x88037464, 0x88037590, 0x880385e4, 0x88038666, 0x8803a384, 0x8c010000 | BSS sec1 +0xa946ae (Navi VA present in text but not a cited decompressor blocker) and OUTSIDE kernel/QEMU VAs | Runtime decompressor/QEMU environment blocker; cited kernel VAs OUTSIDE Navi module. No Navi IAT/BSS cited as M1.2f-unblockable blocker in this task's sense. Leave blocked. No reopen. |
| M9.14 | blocked | 0x00200200, **0x0055d8fc** | CODE sec0; **IAT OSMDLL!OSM_Malloc** | **Cited blocker VA is IAT**. Rule 15 reopen (import/binding/stub via M9.35/M9.24 context; M1.2f not needed). |
| M9.17 | blocked | 0x00200200, 0x0041a438, 0x0041b780, 0x0041b954, **0x0055d040**, **0x00e23cc0** | CODE VAs; **IAT COREDLL!memset**; **BSS sec1 +0x8c6cc0 (zero at load)** | **Cited blocker VAs are IAT and BSS**. Rule 15 reopen (M9.35; M1.2f not needed). |

## Interpretation

- **FACT:** `l3_precond.py` and `reader_precheck.py` now classify VAs via `va_class` when image+module context is available, expose class+detail in text/JSON, and gate M1.2f only on `INIT`; IAT/BSS produce correct non-M1.2f concerns (import/binding/stub, writer/runtime init / zero at load). Unknown/no-image paths remain honest (UNKNOWN, no guessed READY/non-M1.2f).
- **FACT:** Selftests cover IAT/BSS/INIT (synthetic, no vendor data) in both tools and all required checks pass (`va_class`, `l3_precond`, `reader_precheck`, `todo_check`, `claims_check`, `selftest.py`).
- **FACT (audit):** M9.14 (IAT), M9.17 (IAT+BSS), M4.16b (BSS cited blocker 0x00d53500), M3.13 (BSS) have cited blocker VAs classifying IAT/BSS and were reopened per rule 15 with original blocker kept and H50 reopen note. M3.11c has cited blocker VAs IAT/BSS (0x0055d8f0, 0x00d53500) and was reopened with explicit mixed-class note (INIT 0x005628e8 remains M1.2f only if required; BSS 0x00840ba0 noted).
- **FACT (audit):** M3.2b, M3.2, M3.14, M3.16, M3.18 have no concrete cited IAT/BSS/INIT sec1 blocker VA (or only CODE/OUTSIDE markers) and were not reopened; M3.2b (no concrete sec1 VA named) received a note asking next owner for the VA. M1.4/M1.2f/M8.E1 remain blocked for codec/INIT-runtime reasons (no Navi IAT/BSS cited blocker VA to reopen on). Mandatory names M4.26, M2.17, and "M1.12 follow-up" task block not found in TODO.md (stated explicitly).
- **HYPOTHESIS:** none added beyond tool behavior; further reader reruns should follow va_class-classified preconditions.

## Conclusion

Prechecks now make loader class explicit and treat M1.2f as a blocker only for INIT, preventing "compressed sec1/.data" from masking IAT/BSS cases. The audit reopened five blocked tasks whose cited blocker VAs are IAT/BSS (M3.11c, M3.13, M4.16b, M9.14, M9.17) with rule-15 notes, left INIT/no-VA/codec/runtime blockers closed with explicit notes, and recorded missing mandatory task names. Claims C-3470–C-3479 registered; TODO and claims pass lint/checks.

## Reproduction

```bash
python3 tools/va_class.py archive/head256.img --module Navi.exe --resolve-with 0x3e00200 0x0055d040 0x00d53500 0x0055e000
# expect: IAT COREDLL!memset / BSS sec1 +0x7f6500 (zero at load) / INIT sec1 +0x1000 (needs M1.2f)
python3 tools/l3_precond.py --selftest && python3 tools/reader_precheck.py --selftest
```

## Follow-ups

- [ ] Next owners of reopened tasks (M3.11c, M3.13, M4.16b, M9.14, M9.17) rerun with va_class-aware preconditions (M9.35/M3.22 context as noted).
- [ ] M3.2b next owner: provide concrete sec1 VA for classification.
