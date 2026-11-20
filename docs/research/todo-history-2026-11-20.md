# TODO history — 2026-11-20 (PO grooming archive, 20th pass)

Done tasks moved from `TODO.md` on 2026-11-20: `Status: done`, the block's
ID named by no open or blocked task's text, and first ticked on `origin/main`
more than 24 h before this pass (`git log -S` on the `- [x] **ID — ` line).
Safe since H116: the fn_audit DOCS BASE cites only live TODO blocks.

Moved (16): `M1.2e`, `M1.2g`, `M1.16`, `M1.23`, `M1.29`, `M3.19`, `M4.20`, `M5.10`, `M5.12b`, `M5.28`, `M5.45`, `M5.46`, `M8.E1b`, `M8.E1c`, `M9.29`, `M9.30`.

- [x] **M1.2e — Try public CE ROM decoders on the two EXP-49 sections**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (needs GitHub/source downloads, rule 12)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: —
  - Goal: M1.2b/M1.3 rule out lzss, lzx, lznt1, xpress-huffman and plain XPRESS
    LZ77 (0/245). Before porting the kernel routine (M1.2c), test the decoders
    that public Windows CE ROM tools already carry.
  - Input: lead, unverified — Willem Hengeveld's `dumprom` / `eimgfs` (nlitsme on
    GitHub) and itsutils handle compressed CE ROM sections; the two EXP-49
    sections and the M1.2a/M1.2d header forms (`cerom.py comphdr`).
  - Done when: one decoder gives exactly the M1.2a lengths for both sections
    (then port it into `tools/cecompress.py` with licence and attribution checked
    and rerun M1.3), or the EXP lists each tool, version, URL, SHA-256 and the
    output it gave.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-2070–C-2079
- [x] **M1.2g — `decomp_oracle.py` fragment API + CE XIP LZXD reference vector harness (unblocks M1.2f verification)**
  - Status: done · Owner: — · Critical: no
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M1.2f (framing/tree landed), M8.E1b (VAs)
  - Goal: give M1.2f a verifiable oracle/reference path without guessing 245/245: a harness feeds block/section fragments and compares decoded bytes/hash to a trusted reference (QEMU/runtime oracle when available, or a pinned CE XIP LZXD reference output with licence/URL/SHA-256), proving the bitstream/tree variant.
  - Precheck: `python3 tools/cedecomp.py --selftest` passes; EXP-49 vectors and M8.E1b VAs recorded; `python3 tools/decomp_oracle.py --selftest` passes (contract implemented: `osm2leaf.decomp_oracle/v1`, pinned EXP-49 lengths/targets, `vectors --json`, `verify`; extend with `source`/`entry_va`/`input_hash` when wiring M8.E1c/M9.29 runtime output).
  - Scope: `tools/decomp_oracle.py` (stdlib, `--selftest`) schema/result verification for EXP-49/fragment mode + optional wiring to M8.E1c/M9.29 runtime output. No 245/245 claim; no vendor bytes committed.
  - Input: M1.2f `XipLzxd` framing, EXP-49, M8.E1b `DECOMP_SECT/BLK`, M8.E1c/M9.29 JSON when available; external reference requires recorded licence/URL/SHA-256 (non-Claude if download needed).
  - Done when: schema documented and `--selftest` has synthetic controls; EXP-49 sec1/sec2 reports `PASS` only with a trusted decoded reference hash, else `FAIL`/`NO_ORACLE` (never silent pass). M1.2f/M9.29/M9.30 consume the schema; at least one runtime or pinned-reference result is recorded in an EXP.
  - Stop: if no trusted reference obtainable (no QEMU, no licensed reference output), keep EXP-49 `NO_ORACLE` with blocker named and land/keep schema + synthetic selftest.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3240–C-3249
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
- [x] **M5.28 — Provisional OSM→Clarion road class/speed table v0 (compiler-unblocking, L2-testable)**
  - Status: done · Owner: task/m5.28-provisional-roadclass-v0 · Critical: yes
  - Depends: — (M4.2 blocked; M4.17/M5.23 are inputs, not blockers)
  - Goal: unblock the OSM compiler spine with an explicit, versioned *provisional* mapping from OSM `highway=*` (+`maxspeed`/access where available) to Clarion tile class/style/speed values, so generated tiles can be built and validated at L1+L2 without claiming firmware acceptance (rule 13).
  - Precheck: `python3 tools/imf_check.py --selftest` passes; M5.4/M5.22/M5.23 writer/field behavior readable from `tools/tilewriter.py` and EXP-2026-11-08-M5.23; list in-scope `highway=*` values from Dolnośląskie IMF/profile if available.
  - Scope: data/tool file (name stated in PR, stdlib, `--selftest`) consumed by `tilewriter.py`/compiler; covers every in-scope `highway=*` or reports unmapped explicitly. No firmware claim; no M4.2 row key.
  - Input: M5.4 provisional-class behavior, M5.23 `(layer, cls_hi)`, M4.17 negative (class_code hypothesis), IMF highway tags.
  - Done when: every in-scope `highway=*` mapped or explicitly `UNMAPPED` (never silent drop); `--selftest` has positive and unknown-value cases; compiler records `mapping=provisional-v0`; one synthetic L2 tile build using the table passes existing tile checks; EXP states provisional/not firmware-confirmed and the M4.2/M5.3 gap.
  - Stop: if no safe Clarion value can be chosen without inventing semantics, use explicit `UNMAPPED` and refuse to generate that class until resolved.
  - Result: EXP-2026-11-09-M5.28-provisional-roadclass-v0. `tools/roadclass_v0.py` (stdlib, `--selftest`) covers all 17 in-scope `DRIVABLE_HIGHWAYS` with `mapping=provisional-v0` (15 mechanism-confirmed buckets + `busway`/`road` auditable low-provisional placeholders, option a; unknown/OOS `UNMAPPED`+`refuse_generate`, no silent drop) and emits `ze0-road-class-table/1` consumable by `tilewriter.py --class-table`. Synthetic L2 emitted-table build/readback: 12/12 points within 1m, 2 parcels. Provisional, not firmware-confirmed (rule 13); M4.2/M5.3 gaps. C-3040–C-3042.
  - Claims: C-3040–C-3049
- [x] **M5.45 — Tile-writer idempotence and size budget: the same input twice must give the same bytes**
  - Status: done · Owner: task/m5.45-tilewriter-idempotence · Critical: no · Pair: required
  - Depends: M5.34 (done — the run that showed the growth), M5.4 (the 18-parcel run it compares to)
  - Goal: `splice_factory` writes a grown slot block by *appending* it and repointing the slot (`tools/tilewriter.py:927-935`, `clarion_tile.pad256`), so tile size is a monotone function of how many times a directory is spliced, not of the content: the M5.34 tile is +4,671,350 B over factory and its hypothesis is "the appended slot blocks for the parcels written". No test runs the same input twice, and nothing counts the bytes a *second* map update of the same directory adds — the failure mode the card's own M7.1 size budget inherits. A tile that grows on every rebuild cannot be shipped as one-variable cards, and a non-idempotent writer makes every diff larger than the change it carries.
  - Precheck: `python3 tools/tilewriter.py --selftest` passes and `grep -c 'superseded_bytes' tools/tilewriter.py` is `3` (the field is reported but never asserted); the M5.34 `report.json` `counts.tilewriter_stdout` carries `container.appended`; run the same `--parcel 76,940` build twice into two out dirs and `cmp` the tiles (the second pass needs a *fresh extract of the factory tile*, so this is the test to add, not a command that exists).
  - Scope: `tools/tilewriter.py` (one in-place/dedupe pass, name chosen in the PR, that writes a rebuilt slot block **in place** when it fits and refuses to append when the previous block of the same slot is identical) plus `tools/one_tile_pipeline.py` (`--selftest` case), `docs/format/map-tiles.md` (one paragraph: append semantics and the size consequence), and one measured number in the EXP: tile bytes after 1, 2, 3 splices of the same directory with the same input. No change to the record grammar or to the gate.
  - Input: `tools/tilewriter.py` (`splice_factory` `:819-940`, `pad256` `:929`, `superseded_bytes`), `tools/ze0-viewer/tools_ze0/clarion_tile.py` (`pad256`, `block_bytes`), EXP-2026-11-17-M5.34-parcel (§Observations tile_diff, the +4,671,350 B), M7.1 (the budget this feeds).
  - Hints: the second run must start from the *factory* tile and produce the same bytes as the first (determinism), and the *update* case must start from the generated tile and produce a bounded delta — say which of the two the task measured. `pad256` aligns to 256 B, so a tail of zeros is expected; the assertion is about the appended block, not about padding.
  - Done when: `one_tile_pipeline --selftest` contains a case where the same input built twice yields byte-identical tiles (determinism), and a case where a second splice over an already-spliced directory is bounded (the delta is recorded, not unbounded); `docs/format/map-tiles.md` states the append rule and the measured 1/2/3-splice sizes are in the EXP; `python3 tools/tilewriter.py --selftest` green.
  - Stop: if the container cannot rewrite a slot in place without moving the block (the shared-block case M5.4 found), record that case and make the *bounded* claim only for owned slots; do not claim in-place for blocks the reader shares.
  - Falsifier: two runs of the same input produce different tile bytes, or the second splice grows the tile by the first splice's superseded bytes again.
  - Claims: C-4460–C-4469
  - Result: EXP `docs/experiments/EXP-2026-11-18-M5.45-idempotence.md`. Full clipped corpus (907,969 nodes / 112,965 ways, 1,024 parcels): factory 289,319,168 -> 293,990,518 -> 293,990,518 -> 293,990,518 B (+4,671,350 B once, +0 B after; A0..A3 byte-identical, SHA-256 `b746427c…34c2ef`); the append-always mutant grows the second splice to 298,662,006 B (+4,671,488; `tilewriter --selftest` 69/73, `one_tile_pipeline --selftest` 3 FAIL); the (72,936) level-2 refusal is **physical aliasing** of the level-2 container at [5120,21644) by 9 level-1 preserve-only parsed spans (6 slots start at 5120), not a shared record key — the bounded claim covers level-1 owned slots only; the level-2 cause (parser phantom vs real write) is left to the Follow-up.
- [x] **M5.46 — P1 first slice: the profile-to-tile containment census (how many tiles a Dolnośląskie card needs, and which are whole)**
  - Status: done · Owner: task/m5.46-p1-containment-census · Critical: yes · Pair: required
  - Depends: — (the factory tile list and `mesh_grid.py` are on `main`; no write, no OSM extract)
  - Goal: **M5.38** (open) defines P1 as "all tiles of Dolnośląskie display-only", but `profiles/dolnoslaskie-test.json` pins exactly one tile (`include: ["B48R058R"]`, `max_tiles: 1`) and no block answers how many `MAPAL001` tiles the region's 14.0–17.9 E × 49.9–51.9 N box intersects or contains. Without that census the P0 card cannot be extended to P1 and the scale of the rest of the ladder is a guess. This is the rule-17 first slice: enumerate, no splice.
  - Precheck: `python3 tools/mesh_grid.py list <factory MAPAL001>` prints 45 tiles and `cell B48R058R` prints `48.00.. 53.33 N 12.00.. 20.00 E`; a bbox-intersection over those 45 rows is the census (no vendor bytes are read beyond tile names; `profiles/dolnoslaskie-test.json` is the box).
  - Scope: `tools/parcel_census.py` or `mesh_grid.py` gains one subcommand (name in the PR, e.g. `mesh_grid.py cover PROFILE_DIR`) that reads a profile's `region.bbox` and prints, per tile: lat/lon box, `intersects`/`contained`/`outside`, and the profile's `include` list; plus one paragraph in `docs/research/card-ladder.md` (or M5.38's page once it exists) stating P1's tile count and how many are whole (the rest are edge tiles the profile's `border_buffer_deg` decides). No tile is written; no OSM data is read. If M5.38 has not landed the page, put the paragraph in `profiles/README.md` and cross-link.
  - Input: `profiles/dolnoslaskie-test.json` (`region.bbox`, `tiles`, `limits`), `profiles/poland-full.json`, `tools/mesh_grid.py` (`list`, `tile_box`), the factory `MAPAL001` directory, M5.38's block.
  - Hints: the 45 `.DAT` names are the tile universe; a tile is `contained` when the profile's region box lies inside the tile box (the tile covers the whole region, a P1 copy-whole candidate); it is `intersects` when it only overlaps the region box widened by `border_buffer_deg`. At P1 every non-factory tile is a fresh splice and every factory one is either copied verbatim or spliced — say which in the census, because the P1 card's file count is what M7.1's size budget multiplies. Positive control: the bbox must select `B48R058R` (the P0 tile) and no other tile as contained; negative: a box moved into the Atlantic selects nothing.
  - Done when: the new subcommand prints one row per tile with its class and the profile's include list, `--selftest` covers a contained tile, an edge tile and an empty box; the repeated census on `profiles/dolnoslaskie-test.json` prints `contained=1` (`B48R058R`) and the page states P1's tile count; `python3 tools/selftest.py --only mesh_grid` (or the chosen tool) green.
  - Stop: if a profile has no `region.bbox`, report the missing field and the profile's `tiles.include` only — do not invent a box (that would be the P1 guess this task removes).
  - Falsifier: the census selects a tile whose `mesh_grid.py cell` box does not touch the profile bbox, or reports P0's tile as anything but `contained`.
  - Pair: required
  - Result: EXP-2026-11-18-M5.46-containment. `python3 tools/mesh_grid.py cover profiles/dolnoslaskie-test.json <MAPAL001>` prints `census: contained=1 intersects=0 outside=62 lattice=63 factory_tiles=45` (B48R058R the sole contained tile, so P1 is one factory tile copied verbatim); `cover profiles/poland-full.json` prints `contained=0 intersects=4 outside=59`; `--all` prints all 63 lattice rows; `mesh_grid --selftest` OK (16 ok). The task's Hints had the containment test inverted; the Done-when's contained=1 settles the direction (region inside tile). Claims C-4470–C-4475.
  - Claims: C-4470–C-4479
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
- [x] **M8.E1c — QEMU slice for nk.exe decompressor oracle (compatible SH-4 map, DECOMP_SECT, EXP-49)**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (needs `qemu-system-sh4` LE with compatible memory map/`-M ze0` build deps or container; M8.A2 host deps may be missing)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M8.E1b, M1.2g (M8.A2 unblocks `-M ze0`; a documented compatible-map fallback may proceed in parallel)
  - Goal: execute a verified decompressor slice under QEMU and emit `decomp_oracle`-compatible results, so M1.2f gets runtime evidence (decoded length/hash for EXP-49, then Navi.exe sec1/sec2) without guessing the CE-LZXD block codec.
  - Precheck: `python3 tools/cedecomp_run.py --selftest` and `python3 tools/decomp_oracle.py --selftest` pass; `qemu-system-sh4` (LE) available and version recorded; IMG256 present/verified (rule 11). Record whether `-M ze0` is available or a compatible map is used (stock QEMU 11.1.3 `-M none` fails P1 0x88/0x8c access for nk.exe VAs).
  - Scope: `tools/cedecomp_run.py`/small helpers to run `probe` and `exp49` for `DECOMP_SECT 0x88037464` (preferred, C-2293) with a constructed input frame and minimal kernel-context/heap stubs sufficient for the section-decode path; output hashed decoded bytes as `decomp_oracle` JSON (no vendor bytes committed). Excludes full nk boot, F1, and 245/245 claims until produced.
  - Input: M8.E1b VAs (`DECOMP_WRAP/SECT/BLK/ALLOC`), `cedecomp.py`, EXP-49 vectors (`decomp_oracle.py`), `tools/qemu-ze0/` (`-M ze0` when built), `tools/ce_qemu_probe.py` patterns.
  - Done when: `cedecomp_run.py exp49 --image IMG256 --entry 0x88037464 --json <out>` (or documented equivalent) produces `decomp_oracle verify` PASS for EXP-49 sec1 (`0x484`) and sec2 (`0xcc0`) with recorded decoded SHA-256s in the EXP; `probe` still passes; negative control: wrong entry/garbled buffer does not verify.
  - Stop: if DECOMP_SECT requires kernel/global state not stubbable without F1/registry context, record faulting PC/register state and reduce scope to DECOMP_BLK sub-fragment under M9.29 or a narrower hook, with a follow-up; do not guess decoded bytes.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3260–C-3269
- [x] **M9.29 — Ghidra headless micro-harness for decompressor sub-fragments (LE SH-4)**
  - Status: done · Owner: — · Critical: no · **Runner: non-Claude** (Ghidra 12.2+/JDK required; in-repo script/selftest runnable without Ghidra)
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M1.2g, M8.E1b (M9.2 project import helps but is not required for a targeted function run)
  - Goal: test `DECOMP_SECT`/`DECOMP_BLK` and helper sub-fragments on controlled buffers in Ghidra headless/pyghidra, emitting `decomp_oracle`-compatible results. Complements QEMU (M8.E1c) and isolates CE-LZXD block-codec behavior.
  - Precheck: `python3 tools/decomp_oracle.py --selftest` passes; harness script has `--selftest`/`--plan` with no Ghidra/vendor data. With Ghidra: `analyzeHeadless` found and processor is **SH-4 little-endian** (not BE) per M1.11/M8.E1b/C-2290; `ghidra_import.py`/`l3_run.py` BE references are a hazard to fix/guard.
  - Scope: script under `tools/l3_harness/ghidra/` (name in PR) to load nk.exe image B at base, map src/dest/stack, call chosen VA (DECOMP_SECT/BLK/helper) with r4-r7/stack per prototype, read dest/len/r0, write JSON for `decomp_oracle verify`. No full-reader wiring, no 245-section claim without evidence, no default PR CI.
  - Input: M8.E1b VAs, IMG256 nk.exe mapping via `cerom.py`, `decomp_oracle.py`, `ghidra_import.py` patterns (LE-corrected).
  - Done when: `--plan` prints headless command/processor/VA/memory/expected output; `--selftest` validates plan/result shape without Ghidra; with Ghidra (EXP, non-Claude) EXP-49 sec1 or a pinned DECOMP_BLK sub-fragment yields `decomp_oracle verify` PASS or a faulting-PC negative EXP localizing the codec gap.
  - Stop: if controlled-memory execution is not feasible in the available Ghidra version, record limitation and use Ghidra decompilation/disassembly as evidence feeding M1.2f (not runtime proof) with a follow-up.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3150–C-3159
- [x] **M9.30 — DECOMP_BLK sub-fragment map and test vectors (shift/LZXD-like, feeds M1.2f)**
  - Status: done · Owner: — · Critical: no
  - Note (H51, 2026-11-11): **superseded — do not take.** The kernel routine itself runs in PySh4 (`tools/nk_decomp.py`: 245/245 sections of build A decode, lengths equal `comphdr`); no codec port, QEMU or Ghidra oracle is needed. Closes as `done (superseded)` when **M1.19** merges.
  - Depends: M8.E1b, M1.2g (M9.29 and M8.E1c provide runtime oracles when available)
  - Goal: break `DECOMP_BLK 0x8803a384` / `DECOMP_SECT 0x88037464` into testable sub-fragments (bit reader, shifts/masks, E8/`0x8d80805b` block handling, length/distance decode) with pinned inputs/expected outputs, so `sh4dis.py` shift-encoding gaps and the CE-LZXD codec are resolved against evidence.
  - Precheck: `python3 tools/sh4dis.py IMG256 nk.exe --image-start 0x3e00200 --va 0x8803a384 --count 20` (or helper VAs) decodes as far as supported; `python3 tools/decomp_oracle.py --selftest` passes. IMG256 per rule 11.
  - Scope: analysis + small committed test-vector fixtures (hex/JSON, no vendor blobs beyond short bytes/hashes/offsets) and `sh4dis.py`/helper extensions for blocking shift encodings (SHAD/SHLD/rotcl etc.) with selftests; runtime sub-fragment results from M8.E1c/M9.29 when run. No guessed full codec.
  - Input: M8.E1b chain, `tools/sh4dis.py`, `tools/cecompress.py`/LZXD refs (attribution/licence checked), `decomp_oracle.py`, EXP-49 block structure (M1.2a/M1.2d).
  - Done when: `sh4dis.py` decodes the blocking shift/bit instructions in DECOMP_BLK/SECT (listed before/after in EXP) with selftests; vector file has >=3 sub-fragment cases each runtime-verified by M8.E1c/M9.29 or marked `HYPOTHESIS` with disassembly evidence and falsifier; M1.2f can cite vectors.
  - Stop: if a CE-specific LZXD variant cannot be split without a running oracle, name the minimal reproducible fragment needing QEMU/Ghidra and keep pure-Python porting blocked on M8.E1c/M9.29.
  - Result: superseded by H51/M1.19 — `tools/nk_decomp.py` decodes 245/245 build-A sections with lengths equal `comphdr` (C-3440, EXP-2026-11-10-M9.35-sec1-load-model), so the codec port/QEMU oracle this task asked for is moot; H81 closes it on the board (M1.19 re-opens nothing here).
  - Claims: C-3220–C-3229
