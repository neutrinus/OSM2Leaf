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

---

## Pass 2026-11-15 (third PO pass)

21 more done blocks moved this pass by the dependency-safe fixpoint rule:
no block remaining on the board (any status) names the ID in `Depends:`
or `Unblock:`, and its `Status: done` commit is > 24 h old. H54 is kept
on the board (< 24 h). The fixpoint matters: M3.5, M2.3, M2.5 and M2.15
were named only as `Depends:` of other done blocks (M3.6, M2.18), so
removing those first is what freed them. Every block below is still
cited in live prose; the citing task names the archived ID, so this
history file is the lookup, not a pointer per workstream.

## H

- [x] **H11 — Reader-coverage matrix: one row per file type we generate**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: one page that shows, for every file the OSM compiler must write,
    how far we are from "the firmware reads it correctly" (rule 13).
  - Input: `docs/format/sd-card-layout.md` (top-level tree), `docs/format/*.md`,
    `claims.md`, `tools/l3_harness/targets.json`, the M3/M9/M8 tasks below.
    Rows at least: `MAPAL001` tiles (`B*R.DAT`), `LEV3456R.DAT`, `REFER001`
    `POINT*`, `ADDRE*`, `ZCODE*`, `ICODE001`, `COORD001`, `LCTBL001`,
    `INTER*`, `FRWAY*`, `INDEX003`, the `.cmp`/`.ind` container, `DRSTR001`,
    `CMP.LST`, `MMAIN001`, `VER_INFO/HDD_INFO.TXT`, `RDSTM001`, and the
    verbatim-copy set (`BICON001`, `OPNG`, `SPEECH`, `TMC`, `REFER002`).
  - Result: `docs/research/reader-coverage.md` (H11 commit / session-ZMxuBT).
  - Done when: `docs/research/reader-coverage.md` has the matrix with
    columns *generate or copy* · format doc · writer tool · offline
    round-trip (L1/L2) · firmware reader VA (M3 task) · L3 target (M9 task) ·
    L3 result · full-system result (M8 F4) — each cell a link, a task ID or
    `—`; every row whose reader or L3 target has no task gets one (next
    free IDs) in the same PR.
  - Claims: C-2170–C-2179

- [x] **H49 — PM twelfth pass: re-classify the "compressed sec1" blockers**
  - Status: done · Owner: claude/project-thread-sjt02x · Critical: yes
  - Depends: —
  - Goal: check whether the nine tasks waiting on M1.2f really need the CE codec.
  - Precheck: `python3 tools/fetch_image.py --verify archive/head256.img` (IMG256 pin).
  - Scope: every `0x0055dxxx`/sec1 blocker address cited in `TODO.md` and the 2026-11-08/09 EXPs (13 distinct + 6 BSS); build A 245 compressed sections.
  - Done when: each cited address has a loader class (CODE/IAT/INIT/BSS) from a committed tool, and the board follows it (rule 15).
  - Stop: —
  - Claims: C-3440–C-3449
  - Result: EXP-2026-11-10-H49-pm-review. `tools/va_class.py` (selftest 8 cases). All seven `0x0055dxxx` blockers are import slots (memset, OSM_Malloc, taskIdSelf, OSM_isSender, OSM_Printf, OSM_SramSet, wcsstr); `0x00d53500`/`0x00e23cc0`/RGD tables are BSS; 0 cited addresses are `INIT`. Only 5.5 % of build A's compressed bytes are stored data. Board: M3.15 re-opened; M9.14/M9.17/M9.24 → M9.35; M4.16b/M3.11c → M3.22; M1.2f non-critical; H50 added; AGENTS.md rule.

- [x] **H51 — PM thirteenth pass: the kernel's decompressor runs in PySh4; function starts from `.pdata`; the US card has its own `Navi.exe`**
  - Status: done · Owner: claude/project-thread-n1nund · Critical: yes
  - Depends: —
  - Goal: say where the project stands, what it is stuck on and what it missed, and put the next tasks on the board with hints (Marek, 2026-11-11).
  - Done when: the EXP records every finding with a command that reproduces it on IMG256/US256, and each finding has a task with hints on the board.
  - Result: `docs/experiments/EXP-2026-11-11-H51-pm-review.md` (C-3480–C-3489). `tools/nk_decomp.py` (new) runs `nk.exe` `DECOMP_SECT 0x88037464` in PySh4 with its three stack arguments: EXP-49 sec1 → `0x484`, sec2 → `0xcc0`, `Navi.exe` sec1 → `0x1801a`, sec2 → `0xed60`; `check` result in the EXP. Three PySh4 decode defects fixed (`mov.b/mov.w R0,@(disp,Rn)` used `r0` as base; `mul.l` only for `Rm=r0`; `movca.l` missing). `Navi.exe` sec2 is `.pdata` (7,596 function records): `0x0041c7e8` is 12 bytes inside `fn 0x0041c7dc`, which has a static caller. The US card's build A is a different `Navi.exe` (entry `0x0035d894`); build B is byte-identical.
  - Claims: C-3480–C-3489

## M1

- [x] **M1.2a — Parse the compressed-section header**
  - Status: done · Owner: session-ZMxuBT · Critical: yes
  - Depends: —
  - Goal: know where the compressed payload starts and how long it is.
  - Input: EXP-49 bytes. Section 1 (`NaviMapCC.dll` rva `0x13000`, psize
    `0x2c6`, vsize `0x5b8`) starts `84 04 00 | c6 02 00 | 10 00 00 00 |
    84 04 00 00 | b0 02 00 00 | 84 04 00 00 | 5b 80 …`; section 2 (psize
    `0x68c`, vsize `0xcc0`) starts `c0 0c 00 | 8c 06 00 | 10 00 00 00 |
    c0 0c 00 00 | 76 06 00 00 | c0 0c 00 00 | …`. Hypothesis to test: a
    22-byte header (`0x2c6 − 0x2b0 = 0x68c − 0x676 = 22`), a 24-bit
    uncompressed and compressed length, then per-block records
    (uncompressed size, compressed size); `0x484` would be the real data
    length of section 1 with the rest of vsize zero-filled. All 245
    compressed sections via `cerom.py sections`.
  - Done when: `cerom.py comphdr MODULE|--all` prints the parsed header for
    every compressed section and the hypothesis holds (or is refuted) on all
    245, with a count of exceptions; a synthetic self-test pins the parser.
  - Result: `cerom.py comphdr`; both recorded prefixes HOLDS, 0 exceptions;
    243 sections unmeasured (EXP-2026-11-05-M1.2a-comphdr, C-640/C-641).
  - Claims: C-640–C-649

- [x] **M1.2d — The second compressed-section header form (58 sections)**
  - Status: done · Owner: task/m1.2d-comphdr-form2 · Critical: yes
  - Depends: —
  - Goal: `comphdr` parses all 245 sections, so M1.3 knows every payload.
  - Input: `cerom.py --image-start 0x200200 IMG256 comphdr --all` (58
    REFUTED rows, e.g. `InfoBarCC.dll/sec2`, `Vehicle.exe/sec1`/`sec2`);
    hypothesis C-1713: flag word `0x10000000 | psize`, perhaps a multi-block
    or stored form.
  - Done when: `comphdr` recognises the second form (synthetic self-test for
    it) and reports `245 HOLDS` or lists the exceptions with their bytes;
    the EXP says whether form 2 is multi-block, stored, or another codec.
  - Claims: C-1740–C-1749
  - Result: `comphdr` parses 245/245 (187 form 1, 58 form 2 multi-block
    `[u24×n][0x10,0x1000,X,0x1000]+0x8d80805b`, `n-1` blocks, `u24[-1]==psize`;
    not stored), 0 exceptions; IMG256 245 HOLDS (EXP-2026-11-06-M1.2d-comphdr-form2,
    C-1740–C-1746). `realcheck` 8/8, `selftest` 34/0/19, `cerom --selftest` 411.

- [x] **M1.11c — `sh4dis.py`: MOVT, SHAR, SHLD, SHAD opcodes**
  - Status: done · Owner: task/m1.11c-sh4dis-opcodes · Critical: no
  - Depends: M1.11 (done)
  - Goal: decode the dynamic and single-bit shift opcodes and `movt` that the
    RDSTM directory walk (`0x003f56bc`, `0x003f5e10`) uses, so an offline walk
    can be run faithfully (M4.16b unblock).
  - Done when: `sh4dis.py --selftest` pins the four encodings (`0x0n29`,
    `0x4n21`, `0x4n0d`, `0x4n0c`) and a real-image window shows no undecoded
    opcode at the five M4.16b addresses; EXP recorded.
  - Claims: C-2650–C-2652
  - Result: EXP-2026-11-08-M1.11c-sh4dis-opcodes — `sh4dis.py` decodes MOVT/SHAR/SHLD/SHAD (LE pinned); selftest pins the four encoding forms and the five M4.16b instruction words; Navi.exe IMG256 `--check-real` shows no `.word` at `0x003f52dc,0x003f56fe,0x003f5746,0x003f5e1a,0x003f5e1e` (`movt r0, shad r1,r3, shad r3,r2, movt r3, shar r2`). `0x014a@0x003f52e2` stays `.word` (out of scope). C-2302 decoder gap closed for these forms; M4.16b walk/join remain open.

## M2

- [x] **M2.3 — `HDD_INFO.TXT` text → fields**
  - Status: done · Owner: task/m2.3-hddinfo-fields · Critical: yes
  - Result: EXP-2026-11-06-M2.3-hddinfo-fields (tools/hddinfo.py FieldDef/HDD_INFO_FIELDS + field_layout; validation.md table; selftest 43 checks)
  - Depends: M2.1
  - Goal: the line order, separators and the six-line mapping.
  - Input: the M2.1 function `0x004e7b8c` itself (C-1711: `fgetws` loop,
    `wcschr` split, `wcsncpy` copy) and the buffer M2.1 names;
    `tools/hddinfo.py`. Can start now on the `fgetws` loop; M2.1 gives the
    struct base.
  - Done when: a `line → field → type → struct offset` table is in
    `docs/format/validation.md` and `hddinfo.py` follows it (self-test
    updated).
  - Claims: C-740–C-749

- [x] **M2.5 — Source of `DIFFERENT MAP CODE`**
  - Status: done · Owner: task/m2.5-different-map-code · Critical: yes
  - Depends: M2.2 (M2.9 helps)
  - Goal: which input decides the message: line 1, the `0x06000000` copy,
    or a NAND/system record.
  - Input: the message string (M2.9), M2.2 comparator.
  - Done when: the deciding input is named with the code path VA.
  - Claims: C-760–C-769
  - Result: EXP-2026-11-06-M2.5-different-map-code (IMG256 `92aa525d…`). `DIFFERENT MAP CODE` = AppLaunch B dispatcher `0x03bcafb8` error code `0x50`, produced by router `fn 0x03bd2ecc` (B, `0x03bd2ed4/0x03bd2eda–0x03bd2ee2`; C mirror pools `0x03bb2c54`→`0x03bb2858`, `0x03bb2c64`→`0x03bb2a64`) when `fn 0x03bd2ad8` (B; C `0x03bb2858`) returns 0. Deciding input: **NAND/system kernel target-info** `KernelIoControl(0x0101302C)` output `+0x60` (11 bytes) vs **card `\SystemSD\VER_INFO\HDD_INFO.TXT` parsed line-1/`base_code`** (11 bytes), byte-for-byte (`0x03bd2c1e–0x03bd2c3e`); logs `VerInf:%s / HddInf:%s`. **Not** the `0x06000000` copy, **not** an HDD_INFO text record in NAND (C-766).

- [x] **M2.12 — `HDD_CHK.ATT` CRC16 attestation (`SilentAuthenticate`)**
  - Status: done · Owner: task/m2.12-hdd-chk-att · Critical: yes
  - Depends: — (M1.9 helps)
  - Goal: know whether the unit requires a CRC16 attestation file on the card,
    and how it is computed, because a generated card must reproduce or satisfy
    it.
  - Input: `MapUpdate.exe` `SilentAuthenticate` `0x0001c210` and
    `CApi_MakeCRC16` (EXP-2026-11-06-M2.6, `docs/format/firmware.md`
    "MapUpdate.exe"); search `HDD_CHK.ATT` (ASCII and UTF-16) across A/B/C
    with a positive control; `sh4xref.py --calls`.
  - Done when: the EXP states which modules read `HDD_CHK.ATT`, the CRC16
    polynomial/seed and the byte range it covers, and whether `Navi.exe`
    (not just the updater) checks it at boot; `docs/format/validation.md`
    updated.
  - Claims: C-1870–C-1879
  - Result: docs/experiments/EXP-2026-11-06-M2.12-hdd-chk-att.md (HDD_CHK.ATT UTF-16LE only in MapUpdate.exe/B; Navi.exe has no ref, HDD_INFO.TXT control found in A; `SilentAuthenticate` 0x0001c210 reads 0x80 bytes, decodes 20 hex chars from ctx+120 → 10 bytes, `CApi_MakeCRC16`/commondll 0x03c04214 = CRC-16/CCITT reflected/KERMIT seed 0 poly 0x8408 must yield 0, then `sub_0001e3f4` verifies 128 bytes; C-1870–C-1879; validation.md updated)

- [x] **M2.15 — The exact `HDD_INFO` bytes behind `DIFFERENT MAP CODE` and `MAP DATA BASE UNMATCH`**
  - Status: done · Owner: task/m2.15-hddinfo-bytes-mapcode · Critical: yes
  - Depends: — (M2.5, M2.3 done)
  - Goal: for the Poland card we must know which `HDD_INFO.TXT` bytes the
    unit compares, and against what. M2.5 found the two launcher checks but
    left the parsed line/offset of the 11-byte compare and the `0x03bd2ce4`
    range check open.
  - Input: `AppLaunch.dll` B `fn 0x03bd2ad8` / C `0x03bb2858` (11-byte compare
    vs target-info `+0x60`), B `fn 0x03bd2ce4` / C `0x03bb2a64` (MapDBVer
    range, target-info `+112/+114`), the HDD_INFO parse state machine (`*r9`
    global `0x1f74b30`); EXP-2026-11-06-M2.5, `validation.md`, `hddinfo.py`.
  - Done when: `validation.md` names, for both checks, the HDD_INFO line,
    byte offset and length and the unit-side source, with VAs; `hddinfo.py
    classify` follows it (self-test pins one pass and one fail per check);
    the 89 M2.4 variants are re-classified with the new model.
  - Result: EXP-2026-11-06-M2.15-hddinfo-bytes-mapcode. Check 1 (0x50, B
    `fn 0x03bd2ad8`/C `0x03bb2858`): HDD_INFO line 1 `base_code` slot 0 bytes
    0-10, file off `0x00` len 11 vs `KernelIoControl(0x0101302C)` +0x60 (11 B).
    Check 2 (0x51, B `fn 0x03bd2ce4`/C `0x03bb2a64`): line 3 `build` pos 5,6,7
    (file off 31-33 factory) → 3 nibbles `MapDBVer=((d5*16)+d6)*16+d7` (fn
    `0x03bd2a40`, `0-9a-fA-F`→0-15) vs target +112 min/+114 max (u16 BE);
    parse cache global `0x01f74b30` (16-byte slots). `validation.md` and
    `hddinfo.py classify` (M2.15 model, self-test 44 checks, pass+fail per
    check) updated. 89 M2.4 variants reclassified (M2.15): check 1 69 PASS /
    20 `DIFFERENT MAP CODE`, check 2 89 `BOUNDS_UNKNOWN` (unit bounds unknown),
    10 MapDBVer changes noted.
  - Claims: C-2080–C-2089

- [x] **M2.18 — Offline HDD_INFO / MAP CODE acceptance predictor (pre-L3 gate)**
  - Status: done · Owner: task/m2.18-hddinfo-predictor · Critical: yes
  - Depends: M2.3, M2.5, M2.15 (done)
  - Goal: give M5.11/M5.15 and card builders an L2-adjacent, offline verdict for the two known acceptance checks (M2.5 `DIFFERENT MAP CODE`: 11 bytes `KernelIoControl(0x0101302C)+0x60` vs `HDD_INFO` line 1; M2.15 `MAP DATA BASE UNMATCH`: `MapDBVer` range) without waiting for a runnable M9.6 firmware target. This does **not** replace M9.6/M2.4 firmware verdicts (rule 13).
  - Precheck: `python3 tools/hddinfo.py --selftest` passes and pins the M2.15 model; `tools/hddinfo_variants.py` corpus is present. If factory `+0x60` or range bounds cannot be stated from recorded EXPs/claims, report `BOUNDS_UNKNOWN` (never pass).
  - Scope: extend `hddinfo.py` or add a small stdlib tool (name stated in PR, `--selftest`) to classify `HDD_INFO.TXT` as `ACCEPT`/`DIFFERENT MAP CODE`/`MAP DATA BASE UNMATCH`/`BOUNDS_UNKNOWN`; re-classify the 89 variants offline. No firmware run.
  - Input: EXP-2026-11-06-M2.5, EXP-2026-11-06-M2.15, `tools/hddinfo.py`, `tools/hddinfo_variants.py`, `docs/format/validation.md`.
  - Done when: per-variant table (89 rows) with positive/negative control per check; unknown bounds never produce a pass verdict; M5.11 can call it on a candidate `HDD_INFO.TXT`; EXP states which verdicts still require M9.6/M2.4.
  - Stop: if `+0x60`/bounds inputs cannot be stated from recorded evidence (not guessed), stop short of a pass verdict.
  - Claims: C-3030–C-3039
  - Result: docs/experiments/EXP-2026-11-09-M2.18-hddinfo-predictor.md

## M3

- [x] **M3.5 — Tile reader entry and the level table**
  - Status: done · Owner: task/m3.5-tile-reader-final · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: find the `MESH_ID`/`DIVID` code and confirm the six-level table
    (`VTb Tp;Lv;…`).
  - Input: `NaviMapCC.dll` strings and exports; `docs/format/map-tiles.md`.
  - Done when: the reader VA and the level-table layout are recorded in
    `map-tiles.md`.
  - Claims: C-860–C-869
  - Result: EXP-2026-11-06-M3.5-tile-reader (reader VAs 0x0041f26c/0x004259bc/0x0042757a in Navi.exe; six-level table `VTb Tp;Lv;St;F#|L1..L6|Sz;Adr`; NaviMapCC.dll has no reader code)

- [x] **M3.6 — Which tile sections the renderer reads**
  - Status: done · Owner: task/m3.6-tile-sections-renderer · Critical: no
  - Depends: M3.5
  - Done when: each tile section has "read by VA" or "ignored" in
    `map-tiles.md` (section 4 especially).
  - Result: EXP-2026-11-06-M3.6-tile-sections-renderer (MAP_DATA `0x00425f40`=renderer, RGD_DATA `0x004266ec`=router, shared `0x0041ee14`; LEV sec1→MAP, sec2→RGD; grid sec1→MAP; sec4 no read VA in MAP/RGD paths, C-870–C-876).
  - Claims: C-870–C-879

- [x] **M3.7 — How the router reads `RDSTM001` / `REFER` road records**
  - Status: done · Owner: — · Critical: no
  - Depends: — (M1.8 helps)
  - Goal: the record fields the router uses (graph tuples, speed, one-way,
    restrictions).
  - Input: route/guide modules in A (`cerom.py modules`), `RDSTM` strings,
    `docs/format/rdstm.md`.
  - Done when: a field list with VAs is in `rdstm.md`; it feeds M4.1–M4.3.
  - Claims: C-880–C-889
  - Result: EXP-2026-11-06-M3.7-router-rdstm (`RDSTM001` is the TMC location
    record: volume+`LCTBL001.DAT` under type `0x14e4`, twelve fields with
    getters/VAs, per-record field directory; routing is mesh-keyed and no
    speed/one-way/restriction accessor exists — M4.2 must not look here)

- [x] **M3.8 — Does the firmware read `MMAIN001.DAT`?**
  - Status: done · Owner: task/m3.8-mmain-read · Critical: no
  - Depends: — (M1.9 helps)
  - Goal: decide whether M5.6 must regenerate `MMAIN001.DAT` (the 4 KiB
    database header, C-1720) or can copy it.
  - Input: string search for `MMAIN` (ASCII and UTF-16) in all A/B/C modules
    with a positive control (`HDD_INFO.TXT` must be found the same way);
    `sh4xref.py --to` on the hits.
  - Done when: the EXP lists every reference with module/VA and what the code
    checks (label, record count, cluster), or shows no reference with the
    control; `docs/format/` and M5.6 input updated.
  - Result: EXP-2026-11-06-M3.8-mmain-read — one ASCII literal in
    `Navi.exe` `0x0017adac` (fn `0x0041a438`), no B/C reference; the reader
    requires exactly `0x1000` bytes and checks no label/count; the file is
    big-endian on the card. `tools/ce_strfind.py` added.
  - Claims: C-1780–C-1789

- [x] **M3.12 — `INDEX003.DAT`: is it the POI name search index?**
  - Status: done · Owner: task/m3.12-index003-poi-search · Critical: yes
  - Depends: — (M5.12c overlaps: coordinate the scan)
  - Goal: know whether the unit finds a POI by name through a second copy
    of the name (then the S2 rename must update it too) or through pointers
    into the `POINT` pages.
  - Input: `REFER001/INDEX003.DAT` on the EU and US images (`cmpind.py
    extract` if it is a `.cmp` pair); C-880 (`0x14e8` resolves `REFER001` +
    `INDEX003.DAT`); M3.11 output.
  - Done when: `refer.md` describes the `INDEX003` record layout well enough
    to say, for the US POI `HANA HEALTH CENTER` (`POINT010`, page `0x840ba0`,
    record 0), which `INDEX003` entry refers to it and whether that entry
    holds name bytes; the EXP gives counts and offsets only.
  - Result: `INDEX003.DAT` absent from EU 2011 and US 2011 stock FAT/DRSTR
    (EU REFER001 388/0 INDEX*, US 116/only INDEX001; firmware string refs at
    US 14679280/46136560, EU 14648088/46105368, no FAT file). No `INDEX003`
    entry refers to HANA HEALTH CENTER on these images; S2 POI rename does
    not need to update `INDEX003` on these images. Record layout UNKNOWN
    (needs an image that ships the file). EXP-2026-11-06-M3.12-index003-poi-search.
  - Claims: C-2130–C-2139

## M4

- [x] **M4.8d — Sub-unit field for POI/ADDRE positions**
  - Status: done · Owner: task/m4.8d-subunit-field · Critical: no
  - Depends: —
  - Goal: find a sub-unit position field in `POINT`/`ADDRE` records (a
    `0..2047`-class local value) so M4.8b can test local scale 1 vs 2.
  - Done when: the field is decoded (or `UNKNOWN` with the method) and the
    local-scale test is in an EXP that re-opens M4.8b.
  - Result: EXP-2026-11-08-M4.8d-subunit-field.md. No 0..2047-class geographic
    sub-unit *position* field found in zlib-framed POINT name records (50k
    US+EU) or ADDRE: `(v6&0x7ff,v8)` are 11-bit 2047-class but not local
    positions (0/50k pair matches to `local(A)`, 41–681 km on 16 M4.8b refs);
    `v16/v20` discrete; no 11-bit bitfield match above noise; ADDRE XX/YY are
    0..255 (M4.19). `tools/poi_subunit.py` added. M4.8b re-opened (local scale
    still unanswered; bit-packed POINT pages out of scope).
  - Claims: C-2930–C-2935 (was C-1908–C-1909, overlap with M4.8b fixed by H24; C-2936–C-2939 used by M4.8b re-attempt)

- [x] **M4.12 — `COORD001`/`ZCODE`/`ICODE001` remaining fields**
  - Status: done · Owner: task/m4.12-coord-zcode-icode-fields · Critical: no
  - Depends: —
  - Goal: `COORD001` `level`, the `ZCODE` offset base, `ICODE001` trie roots.
  - Done when: each is decoded with a test, in `coord-zcode-icode.md`.
  - Claims: C-1000–C-1009
  - Result: COORD001 `level` = 48-bit region bitmask `M=(level_u32<<16)|pad_u16`, one-hot `0x400000000000>>(i-1)` for non-last, last `level_u32==guard` (EU 33/US 11, verified). ZCODE: form A (018/033) offset base = ADDRE `unaddr(rec_addr_enc@0x1012)`, trie `crec` @0x1100 halfword-indexed, 16B recs (ZCODE018 rec0 verified); form B (31 files) `>HHBBHI` dir+ladder, no uniform offset base (OBSERVED). ICODE001 ISO header `>HH(hw,countries)`, 7 EU + 2 US per-language country-chain root byte offsets located by chain tracing; root-pointer index table not found. `tools/coord_zcode_icode.py` (--selftest + --verify-*), EXP-2026-11-06-M4.12-coord-zcode-icode-fields, C-1000–C-1009.

## M5

- [x] **M5.20 — `mkcard.py --reconcile`: minimal-diff build for a changed tree**
  - Status: done · Owner: claude/m5.20-mkcard-reconcile · Critical: no
  - Depends: M5.13b
  - Goal: EXP-2026-11-06-M5.10 follow-up. `imgpatch.py` gives one-variable
    cards, but the compiler path still rebuilds the whole FAT, so a generated
    card differs from the factory in hundreds of ranges and one bad byte is
    invisible.
  - Input: `tools/mkcard.py` (`build_fresh_partition`, the M5.12b label/order
    preservation), `tools/imgpatch.py` (chain writer), `mkcard.diff_ranges`.
  - Done when: on the US and EU trees, a tree with one changed file yields an
    image whose diff against the factory lies only in that file's clusters and
    its directory entry (the property `imgpatch.py` gives), the unchanged-tree
    build stays byte-identical, and `--selftest` covers the reconcile path.
  - Claims: C-2460–C-2469
  - Result: EXP-2026-11-08-M5.20-mkcard-reconcile. Same-length changes on US and EU: one 16 B range, cardcheck PASS. Resize: 0 ranges outside the envelope, cardcheck PASS, but the DRSTR001.DAT value bytes are part of the diff (cardcheck requires them); the done status counts those bytes as the file's directory entry. Unchanged-tree copy on a real image not re-run (disk; C-1911 covers it). Fresh-build contrast not re-measured. Found and fixed the FAT NT case-flag gap (C-2466).

- [x] **M5.24 — `imgpatch` diff check: derive cluster ranges from BPB, not the write offset**
  - Status: done · Owner: task/m5.24-imgpatch-diff-bpb · Critical: no
  - Depends: M5.13b (done)
  - Goal: M5.13b's byte-diff check derived the cluster base from the `imgpatch`
    write offset, not from an independent BPB/FAT read. Harden the check so the
    "one variable" guarantee is verified against the filesystem's own layout.
  - Precheck: `python3 tools/imgpatch.py --selftest`.
  - Scope: the verification path in `imgpatch.py`/the M5.13b check script; no
    change to how bytes are written.
  - Done when: the diff-range check resolves each replaced file's clusters from
    an independent BPB+FAT read and reports a mismatch, and it still passes on
    the S1/S2 images (SHA-256s from M5.13b).
  - Stop: if the BPB read disagrees with the recorded S1/S2 ranges in a way
    that implies the earlier check was wrong, treat that as the finding (do not
    "fix" the result).
  - Claims: C-2830–C-2839 (was "next free block at claim time", fixed by H23)
  - Result: `tools/imgpatch.py --check-diff` resolves cluster/dir-entry ranges
    from an independent BPB+FAT read (not write offsets) and reports mismatches;
    selftest 59/59 OK; S2 vs factory (M5.13b SHA-256s) gives 17,737 ranges, 0
    outside, independently resolving cmp clusters 78193–78257/dir `0xb3bb7e80`
    and ind 78258/dir `0xb3bb7ee0`. EXP-2026-11-08-M5.24-imgpatch-diff-bpb.md,
    C-2830/C-2831.

## M9

- [x] **M9.21 — `PySh4`: little-endian mode and `bt/s`/`bf/s`**
  - Status: done · Owner: claude/m9.21-pysh4-le · Critical: yes
  - Depends: —
  - Goal: the L3 interpreter can run `Navi.exe` code as it is in the ROM.
    Today `PySh4` fetches, loads and stores big-endian and rejects
    `bt/s`/`bf/s` (C-2546); `Navi.exe` is little-endian and uses `bf/s` in
    the POINT path (`0x3f39c0`, `0x3cd910`).
  - Precheck: `python3 tools/point_walk_l3.py walk …` passes with its local
    LE subclass (EXP-2026-11-07-M3.11-point-reader-2).
  - Scope: add little-endian fetch/load/store mode to `PySh4` with default
    unchanged, model `bt/s`/`bf/s` delay-slot behavior with self-test
    vectors, switch `point_walk_l3.py` to the shared engine, and verify the
    POINT path on the US page.
  - Input: `tools/l3_harness/engine.py` (`_load`/`_store`/`_fetch`,
    `cmp/str`, the `bt/s`/`bf/s` refusal), SH-4 manual for the delay-slot
    rule; `point_walk_l3.le_engine()` as the reference.
  - Done when: `PySh4(endian="little")` (default unchanged for the existing
    self-tests), `bt/s`/`bf/s` modelled with a self-test vector each,
    `point_walk_l3.py` uses it instead of its subclass, and `0x3f39c0` runs
    on the US page with the globals `0x00d5e4e4`/`0x00d5e4d0` set.
  - Stop: if delay-slot semantics or endianness could not be validated by a
    self-test vector against the SH-4 manual behavior, keep the change out
    and record the failing case.
  - Claims: C-2550–C-2559
  - Result: EXP-2026-11-08-M9.21-pysh4-le; `PySh4(endian="little")` and
    `bt/s`/`bf/s` in `tools/l3_harness/engine.py`; `0x3f39c0` runs on the US
    page with the globals set and matches `parse_page` (C-2550–C-2557).
