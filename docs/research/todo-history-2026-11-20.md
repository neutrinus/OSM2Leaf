# TODO history — 2026-11-20 (cycle 17, PO archive pass)

Done task blocks moved out of `TODO.md` by the PO pass on 2026-11-20. Each is
completed, blocks no live task, and was more than 24 h old (commit date on
`origin/main`) with no live `Depends`/`Unblock`/`Re-opens` naming it. TODO.md
line count before/after this pass: **4807 → 4625** (9 blocks archived here; the
1500-line rule stays unmet because most done blocks are still named by live
tasks).

Selection rule: `grep` the task ID against every `open`/`in progress`/`blocked`
block; if no live block names it and its completion commit is >24 h old, it is
archivable. The script that produced the list searched for `- [x] **<ID>` with
`git log -S` over `TODO.md`.

Archived IDs: M1.16, M1.23, M1.29, M3.2, M3.19, M4.20, M5.10, M5.12b, M8.E1b.

- [x] **M1.16 — Unify `.cmp`/`.ind` chunk codec and inner-page helpers across tools**
  - Status: done · Owner: task/m1.16-cmpind-unify · Critical: no
  - Depends: — (M1.13 done: factory params pinned to stock zlib L6 / memLevel 8
    / wbits 15 / default strategy for POINT001–009)
  - Goal: reduce drift in the format we must generate correctly (rule 13).
    `cmpind.py`, `cmpind_writer.py`, `mutate_refer_poi.py`,
    `mutate_refer_page.py`, `poi_copies.py`, `slot_budget.py`, `lev3456.py`,
    `l2check.py` and others reimplement `CHUNK=0x10000`, `decompressobj` loops,
    `compressobj` params, pair read/write and inner-zlib-page iteration with
    slightly different defaults and error handling. M5.21 already noted slot/encode
    logic duplicated with M5.12c.
  - Precheck: `python3 tools/selftest.py` passes for the affected tools
    (baseline; record any current failures separately) and
    `grep -rn 'CHUNK = 0x10000\|decompressobj\|compressobj' tools/*.py | wc -l`
    shows the duplication surface.
  - Scope: add one shared module (extend `tools/cmpind.py` or add
    `tools/cmpind_codec.py`, name chosen in the PR) exposing decode/encode,
    changed-chunk repack, inner complete-zlib-page iteration, and a
    `factory_compress`/`factory_params` helper aligned with M1.13/C-2570–C-2579.
    Migrate the highest-risk writer tools first (`cmpind_writer`, `slot_budget`,
    `mutate_refer_poi`/page, `poi_copies`); leave read-only tools if migration
    risk is higher than benefit, but document the decision.
  - Done when: the shared module has `--selftest` (round-trip, changed-chunk
    repack preserves unchanged bytes, factory params reproduce a known vector),
    migrated tools keep their existing selftests green, and no migrated tool
    hardcodes conflicting default zlib params.
  - Stop: if a migration changes bytes produced for a real factory sample,
    record the before/after SHA-256 and stop that tool's migration until the
    difference is explained (encoder version vs logic bug).
  - Claims: C-2730–C-2739
  - Result: EXP-2026-11-08-M1.16-cmpind-unify. Added `tools/cmpind_codec.py`
    (factory params L6/m8/w15/default, outer decode/encode/changed-chunk repack,
    inner complete-zlib-page helpers; `--selftest` 21 checks). Migrated
    `cmpind_writer`, `slot_budget`, `mutate_refer_poi`/`mutate_refer_page`,
    `poi_copies`, `cmpind.py`, `lev3456.py`; all existing selftests green, no
    conflicting factory-param defaults. `selftest.py`: passed=67 failed=0
    skipped=15; `claims_check.py`: OK. `ind_mutate`/`l2check`/fit-fallback
    duplications left documented (C-2736).

- [x] **M1.23 — Finish M1.20: wire pdata into `cerom`/`sh4xref`/`sh4scan`/`reader_precheck` and register C-351x**
  - Status: done · Owner: task/m1.23-pdata-wireup · Critical: yes · Pair: required
  - Result: EXP-2026-11-15-M1.23-pdata-wireup; C-3610–C-3619 registered (corrected C-351x restatement). `pdata` labels are live in `sh4xref`/`sh4scan`/`reader_precheck`, `cerom.e32()` has `exception`; `sh4xref --to 0x0041c7dc` prints the pdata holder `fn 0x0041c990`; `selftest.py` 86 passed / 0 failed.
  - Depends: M1.20 (tool on `main`); M1.19 not required (compressed pdata already decodes)
  - Goal: `EXP-2026-11-12-M1.20-pdata-function-table` and its proposed C-3510–C-3519 describe behaviour that `777fb68` did not ship. Finish it so `fn 0x…` labels come from `.pdata` everywhere the EXP says, and the ledger matches the code.
  - Precheck: `python3 -c "import sys;sys.path.insert(0,'tools');import cerom;d=open('archive/head256.img','rb').read(128<<20);print(sorted(cerom.CERom(d,0x200200).e32(cerom.CERom(d,0x200200).module('Navi.exe')).keys()))"` must contain `exception`; `grep -c pdata tools/sh4xref.py tools/sh4scan.py tools/reader_precheck.py` must be non-zero for each.
  - Scope: (1) `cerom.e32()` returns `exception=(units[6], units[7])` (additive key; keep every existing caller/selftest green); (2) `sh4xref.py` `load_module` attaches `mem.fn_of` from `pdata.load_table` when an image+module are given, and `_load_line` prints the pdata start instead of the prologue guess; (3) `sh4scan.py dump` tags pdata STARTs; (4) `reader_precheck.py` `anchor_report(..., data=, image_start=, module=)` labels holder `fn`s from pdata; (5) register C-3510–C-3519, **corrected**: C-3510 asserts the `cerom.e32()` key, which exists only after this task; drop/rewrite its "no module lacks it" wording if the census cannot back it.
  - Input: `tools/pdata.py` (`load_table`, `locate`, `exec_sections`), `tools/cerom.py` `e32()` (`units` is `<18I` at `o+36`), `tools/sh4xref.py` `load_module`/`_load_line`, `tools/sh4scan.py` `cmd_dump`, `tools/reader_precheck.py` `anchor_report`, EXP-2026-11-12-M1.20 §§"Wire-ups", C-3510–C-3519 text at the end of that EXP.
  - Hints: do not re-derive the census; re-run the EXP's §2 commands and paste counts. `nk_decomp.parse_pdata`/`locate` already exist; `pdata.py` is the one to reuse, not a second copy. The EXP's fallback in `pdata.py exception_entry()` (`units[6:8]` when the key is absent) shows the intended contract — pull it up into `cerom` and let `pdata` keep the fallback for older callers.
  - Done when: the precheck grep is non-zero for all three tools; `python3 tools/sh4xref.py archive/head256.img Navi.exe --image-start 0x200200 --to 0x0041c7dc` prints a holder that equals pdata (`fn 0x0041c990`); `python3 tools/selftest.py` passes; C-3510–C-3519 are rows in `claims.md` whose evidence column names a command that now exists; an EXP (`EXP-YYYY-MM-DD-M1.23-pdata-wireup`) records the before/after label for 3 VAs.
  - Note (SE 2026-11-15, TEMPLATE method): the M1.20 EXP's §2 all-module census is a heredoc pinned to `/tmp/opencode/img/IMG256.img` — the only way to reproduce C-3512's totals (A 87,530 / B 21,930 / C 25,243). A claim whose command is a throwaway heredoc on an absolute path is not re-runnable from the repo. Before registering C-3512/C-3514, add a `pdata.py census IMG --json` subcommand (or a `tools/pdata_census.py` with `--selftest`) that prints `module / records / section / compressed` for A/B/C and paste *that* command into the claim evidence. If the census is too slow to run in CI, commit its JSON as a fixture (counts only, no vendor bytes) and make `census --check-fixture` fail on drift.
  - Stop: if a tool's selftest depends on the prologue heuristic in a way pdata cannot satisfy, leave that tool on the heuristic, list it in the EXP, and register only the claims the code backs.
  - Claims: C-3610–C-3619

- [x] **M1.29 — `fn_audit`: a documented correction (`0xMID → fn 0xSTART`) is resolved, not `INSIDE`**
  - Status: done · Owner: task/m1.29-fn-audit-corrections · Critical: yes · Pair: required
  - Depends: M1.25 (`fn_audit.py`, done)
  - Goal: M1.25's audit keeps bare VAs on a correction-marker line (`0x00542256 → fn 0x00542250`, `0x00413af4` on M3.22's H51 note) as `ctx` citations and classifies them `INSIDE`, so 3 of the 12 unique `INSIDE` VAs can never be "fixed" without deleting the corrective prose that is the record of the fix. H52's "re-run `fn_audit --fix-list` until empty" and M1.26's "exit 1 on any `INSIDE`" gate therefore cannot reach zero. Teach the audit to recognise a correction pair and stop counting it as an unresolved failure; keep a live mislabel (`fn 0xMID`) a failure.
  - Precheck: `python3 tools/fn_audit.py archive/head256.img --fix-list | wc -l` prints `12` today; `python3 tools/fn_audit.py archive/head256.img | grep -E '0x003f5fc2|0x00413af4|0x00542256'` shows all three as `INSIDE`; each sits on a line that already names its true start (`0x003f5fc2`→`0x003f5f48` on TODO.md:589, `0x00542256`→`0x00542250` on TODO.md:585/775), so a correct line is currently indistinguishable from a wrong one.
  - Scope: `tools/fn_audit.py` only, `--scope docs` corpus and its selftest. A `ctx` citation is `CORRECTED` (not a failure) when the same line also cites `fn 0x<same true start>`, or when the bare VA is immediately followed by `→ fn 0x<start>` where `<start>` equals `pdata.locate`'s start; a bare VA with no correct start on the line, or a `fn 0xVA` citation whose VA is mid-function, stays `INSIDE`. `--fix-list` and the exit code follow the same rule; add a `CORRECTED n` count to the summary. Do not touch the citations (H52) or widen the corpus (M1.26).
  - Input: `tools/fn_audit.py` (`citations_markdown`, `CORRECTION_RE`, `classify`, `Verdict.is_failure`, `fix_list`), `tools/pdata.py` `locate`; EXP-2026-11-15-M1.25-fn-audit §Scope/Observations; the three ctx-only VAs above.
  - Hints: the line already pairs the wrong and the right VA on purpose, so reuse that pairing rather than a new heuristic. Keep `0x0041c7e8`→`0x0041c7dc`, `0x0040e4b2`→`0x0040e28c`, `0x00412bee`→`0x00412ac0` a failure while a mid-function label for the corrected VA remains — they also appear as live `fn`/`const`/`target` citations, so the same VA can be both `CORRECTED` on one line and `INSIDE` elsewhere; report per-citation, not per-VA.
  - Done when: `python3 tools/fn_audit.py archive/head256.img --fix-list` drops the three ctx-only VAs (`0x003f5fc2`, `0x00413af4`, `0x00542256`) and keeps the nine live ones, exiting 1 while any live `INSIDE` remains; `--selftest` covers a correction line that passes and a bare mid-function label that still fails; the corrected count is printed; `selftest.py --only fn_audit` passes.
  - Stop: if the pairing cannot be told from a genuine mislabel without reading intent, record the three as an explicit `accepted INSIDE` allowlist in the tool with a comment and a claim, rather than a regex that can hide a real one.
  - Claims: C-3790–C-3799
  - Result: EXP-2026-11-15-M1.29-fn-audit-corrections.md (C-3790–C-3795; C-3796–C-3799 reserved). `tools/fn_audit.py` adds a `CORRECTED <start>` verdict for a `ctx` citation whose own `→`/`->` pair names `pdata.locate`'s start (repeated bare VA does not inherit it, cross-build map is not a correction) plus an explicit commented `CORRECTION_ONLY` pin for prose that names the start on another line; a live `fn`/`sub_`/target/const label is never corrected, `--fix-list` and the exit code follow `is_failure`, and the summary prints `CORRECTED 13` and the correction-only VAs. On `archive/head256.img` (`92aa525d…`) `--scope docs` is unchanged at 17 files / 297 citations / 112 unique VAs, `INSIDE` occurrences 46 → 33, `--fix-list` 12 → 9 and drops exactly `0x003f5fc2`, `0x00413af4`, `0x00542256`; nine live `INSIDE` VAs remain and exit stays 1. `fn_audit --selftest` 30/30 OK (pair, wrong start, live label, allowlist pin, cross-build map, repeated VA), `selftest.py --only fn_audit` PASS, `claims_check.py`/`todo_check.py` OK. `tools/README.md` documents the class.

- [x] **M3.2 — `.ind` handling: `chunk_size` and seek vs scan**
  - Status: done · Owner: — · Critical: yes
  - Note (M9.44, 2026-11-19): measured on the running layer: the `.ind` is read as a 16-byte header and then the offset table (one read of up to 2,048 bytes), and only the chunks covering the request are read from the `.cmp`, by seek (C-4643). `.ind` +4 is not compared with the `.cmp` size (C-4646).
  - Unblock: M3.2b's re-run (the chunk engine and its caller), or M1.2f when
    the `.ind` layer turns out to be in `Navi.exe` sec1.
  - Blocker: `.ind` chunk reader (chunk_count/chunk_size/chunk_offset consumer) not identified; `fn 0x00418748` is a resolver only. See EXP-2026-11-06-M3.2-ind-handling.
  - Depends: M3.1
  - Goal: answer from code whether `chunk_size` sizes a buffer or is
    compared against `0x10000`, and whether the reader seeks by offset or
    scans for `78 9c`.
  - Input: M3.1 functions; `docs/format/cmp-ind.md`; `tools/ind_mutate.py`.
  - Done when: both answers are in `cmp-ind.md` with VAs.
  - Claims: C-5330–C-5339 (was C-830–C-839; fresh block for this run)
  - Result: EXP-2026-11-20-M3.2-ind-handling-l3.md (done, C-5330–C-5334). EU2011 L3 run of the whole compressed layer (`tools/cmp_read_l3.py`: mount `0x41bc98`, open `0x41b780`, seek `0x41b8a4`, read `0x41b954`, host ops): (a) `chunk_size` compared with the mount word at `0x41c92a` (0x8000/0x20000 rejected before any `.cmp` read; mount word 0x20000 rejects the factory file; both 0x20000 -> 79,360 wrong bytes), sizes nothing; (b) seek to `chunk_offset[first]` + one read (POINT010 seek `0x234d7f`), `78 9c` decoy + shifted index still correct, `off_last_m1` -> -1, no scan. Factory ADDRE001/POINT010 byte-identical. Static answers were already in `cmp-ind.md` (M3.2b); L3 paragraph added.

- [x] **M3.19 — `tools/sh4scan.py`: commit the scan that produced the three negatives**
  - Status: done · Owner: task/m3.19-close-sh4scan · Critical: yes · Pair: pair
  - Note (rule 15, 2026-11-09 PO): M3.20 done (register-AND mask variant / M3.11 pattern text); re-opened. Counts verified 2026-11-09 incl `mask-pair --via-reg`=1 (immediate 0 recorded).
  - Note (rule 15, 2026-11-09 H48 #170): M1.12 import clause addressed by `tools/reader_precheck.py` importing/delegating to `tools/sh4scan.py` (H48, EXP-2026-11-09-H48-reader-precheck-sh4scan, C-3410–C-3411); re-opened for closure once PR #170 merges.
  - Depends: —
  - Blocker: — (former M1.12 import blocker addressed by H48 #170; counts/selftest/EXP addendum already verified per Result).
  - Goal: M3.11, M3.13 and M3.2b are correct negatives that **cannot be
    re-run**: the tag/stride/mask searches are prose plus heredocs, and M3.2b
    contains `# ... anchor search over IMG256 ...`. Rule 16 makes that a
    defect; this task fixes it and gives M1.12 its engine.
  - Precheck: the counts to reproduce are published — 527 build-A o32 sections,
    26 aligned `cmp/eq #0x60` and 23 `cmp/eq #0x68` hits in `Navi.exe` sec0,
    0 tag pairs, 1 `and #0x70`+`#0x60` mask hit, 0 `@(1)+2*L` stride
    candidates, 282 sections / 23.6 MB for the M3.13 corpus, 14 zlib markers.
    If the tool cannot reproduce them, the published numbers are the problem —
    report that, do not adjust the tool to fit.
  - Scope: build A (and B/C on `--image-start`); LE halfwords; uncompressed and
    compressed sections both listed, with the compressed share printed.
  - Input: EXP-2026-11-06-M3.11, -M3.13, -M3.2b (counts and patterns),
    `cerom.py memmap --json`, `sh4xref.py`; `capstone` must not be required
    (a pattern scan is halfword arithmetic, not disassembly).
  - Done when: `python3 tools/sh4scan.py IMG --image-start 0x200200 tags
    --module Navi.exe`, `--pattern <hex>`, `stride`, `mask-pair` and `anchors`
    run on `IMG256`, reproduce every count above, print the corpus in bytes and
    sections, and `--selftest` pins the pattern semantics on synthetic
    halfwords (including the misaligned false positives M3.11 rejected); M1.12
    imports it rather than duplicating the scan.
  - Stop: if the counts differ, record the discrepancy in an EXP and stop —
    the difference is the result.
  - Result: done (TL closure 2026-11-09). `docs/experiments/EXP-2026-11-08-M3.19-sh4scan.md` (verification addendum) reproduces all published counts on IMG256.head `92aa525d…` incl `mask-pair --via-reg`=1 @ Navi.exe `0x003715c8/ca/cc`; `sh4scan --selftest` OK; M1.12 import clause satisfied by H48 (`reader_precheck.py` imports/delegates to `tools/sh4scan.py`, EXP-2026-11-09-H48-reader-precheck-sh4scan, C-3410–C-3411). Claims C-2530–C-2539 remain as recorded.
  - Claims: C-2530–C-2539

- [x] **M4.20 — US `DRSTR001` round-trip diff at `0x1ae0`**
  - Status: done · Owner: task/m4.20-us-drstr-roundtrip · Critical: yes
  - Depends: —
  - Goal: M5.6 writes `DRSTR001.DAT` for generated cards, so the model must
    round-trip on both markets. On the untouched US factory tree
    `l2check.py` `drstr_roundtrip` fails at `0x1ae0` (EXP-2026-11-06-M5.12).
  - Input: US image (Shared inputs / M5.12), `tools/drstr.py`,
    `docs/format/drstr.md`, `l2check.py`.
  - Done when: the field at `0x1ae0` is explained in `drstr.md` and the
    rebuild is byte-identical for US (7,456 B) and EU, with a self-test case
    for the US form.
  - Result: EXP-2026-11-06-M4.20-us-drstr-roundtrip; `drstr_ze0.build()` preserves DRSTR-stored entry name case (US `XMD/ltntbl.dat` @0x1ae0); US+EU byte-identical, `drstr_ze0 --selftest` OK.
  - Claims: C-2100–C-2109

- [x] **M5.10 — Card image builder (`tools/mkcard.py`)**
  - Status: done · Owner: task/m5.10-mkcard · Critical: yes
  - Depends: — (M2.13 for the lock state; M3.8 for `MMAIN001`)
  - Goal: turn a card tree into an SD image the unit could read: the missing
    link between every writer and the first bench test (M6.5, S0/S1 of
    `card-test-plan.md`).
  - Input: the factory layout from `IMG` (MBR, FAT32 partition 0, 64 KiB
    clusters, label `QSD-309-101`, root order incl. `MMAIN001.DAT` in
    cluster 2, the `0x06000000` copy that `cardcheck.py --image` checks);
    `cardcheck.py`, `l2check.py`, `realcheck.py`; firmware partitions are
    copied verbatim from the source image, never committed.
  - Done when: `tools/mkcard.py --from-image IMG --tree ROOT -o out.img`
    rebuilds the map partition from an unchanged tree and the result is
    byte-identical to `IMG` (or every differing byte range is listed and
    explained: timestamps, free-cluster order); `cardcheck.py --image out.img`
    passes; synthetic self-test on a small FAT32 image; the EXP says what the
    tool cannot reproduce (SD lock state, CID).
  - Result: `tools/mkcard.py` rebuilds the FAT32 partition from a tree while
    copying MBR/pre-partition/tail verbatim; unchanged tree is byte-identical
    and the result passes L1 (EXP-2026-11-06-M5.10-mkcard); real IMG round-trip
    pending.
  - Claims: C-1910–C-1919
  - Result: EXP-2026-11-06-M5.10-mkcard.md — `mkcard.py` copies firmware/pre-partition/0x06000000 verbatim and rebuilds the FAT32 map partition from a tree. Real EU 2011 unchanged-tree rebuild: byte-identical to IMG (SHA-256 `105e2032…76307`, 0 diff ranges), `cardcheck.py --image` PASS (480 files, 194 pairs, 46 tiles). Synthetic self-test OK (sparse FAT32, 0x06000000 preserved, changed-tree fresh build reads back). Diff ranges explained; cannot reproduce SD lock state/CID. `selftest.py` 34 passed.

- [x] **M5.12b — `mkcard.py`: keep the volume label and factory root order on a fresh build**
  - Status: done · Owner: session-ZMxuBT · Critical: no
  - Depends: — (M5.13 is the path for the hardware cards; this is for M5.11)
  - Goal: a fresh build should not drop the root attr-`0x08` entry
    (`QSD-301-103` US, check the EU label) or reorder the root.
  - Input: `tools/mkcard.py` `build_fresh_partition`/`populate_dir`;
    `cardcheck.py` `_read_volume_label`.
  - Done when: the fresh build writes the source volume-label entry as root
    slot 0 and keeps the source directory order where names match; the
    self-test covers it; the M5.12 rebuild reports the label with no warning.
  - Claims: C-2030–C-2039
  - Result: EXP-2026-11-06-M5.12b-root-label.md (`9d37b5f`, `2fc7da7`); `mkcard.py` keeps root volume-label entry and source directory order on fresh builds; self-test/label warning covered per EXP.

- [x] **M8.E1b — Re-derive nk.exe ROM decompressor VA/prototype (M1.2c reverify)**
  - Status: done · Owner: task/m8.e1b-nk-decompressor-derive · Critical: yes
  - Depends: — (has IMG256; M1.2d framing known)
  - Goal: locate the real compressed-section loader/decompressor in nk.exe
    image B (IMG256, `--image-start 0x3e00200`) from actual bytes; correct
    M1.2c C-660–C-665.
  - Input: nk.exe sec0 (0x88001000, 0x4c800). Leads from M8.E1: 1 literal
    `0x00002000` at 0x88042298 (no PC-rel ref found); 5 `add #24,rN` o32-walk
    sites at 0x880128e4/0x88019b6c/0x8803a748/0x8803acbe/0x88047744; marker
    `0x8d80805b` bytes at 0x8804d786 (sec0 end, not code-referenced per M1.2c).
    Must handle M1.2a/M1.2d form 1/2 framing and LZXD-like `0x8d80805b` blocks.
  - Done when: verified VA+prototype recorded with capstone disassembly and a
    byte-level positive control (pattern found and reaches a decompressor call
    that takes src/psize/dest/vsize or equivalent); M1.2c EXP/claims
    retracted/corrected; M8.E1 unblocked.
  - Claims: C-2290–C-2299
  - Result: EXP-2026-11-06-M8.E1b-nk-decompressor-derive — M8.E1 refutation was a BE-vs-LE endianness artifact (C-1600/C-1603 superseded). **Verified (LE, IMG256 `92aa525d…`):** `fn 0x880385e4` o32 walk + `o32_flags & 0x2000` at `0x88038666`; compressed branch → `DECOMP_ALLOC 0x88034d94` then `DECOMP_WRAP 0x88037590(dataptr,psize,dest,vsize)`; chain `0x88037590`→`DECOMP_SECT 0x88037464`→`DECOMP_BLK 0x8803a384` (pool-confirmed). M1.2c C-660–C-663,C-665 restored (C-2290–C-2294). EXP-49 runtime decode not executed (needs `qemu-system-sh4` LE + DECOMP_WRAP kernel-context stubs, C-2294); M8.E1 unblocked (real VA/prototype known). Tools updated: `cedecomp.py`, `cedecomp_run.py`, README.

