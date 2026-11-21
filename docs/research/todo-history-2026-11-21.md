# TODO history — 2026-11-21

Done tasks moved from `TODO.md` on 2026-11-21 with `tools/board.py archive`.

- [x] **M4.15 — `RDSTM001` framing and node reciprocity**
  - Status: done · Owner: task/m4.15-rdstm-framing · Critical: yes
  - Result: EXP-2026-11-06-M4.15-rdstm-framing — 16-byte rows from 0x1000 give 0/10 reciprocity; drift at 0x10a0; schema prefers 2-byte record (0.371). Negative on the 16-byte hypothesis.
  - Depends: M4.1
  - Goal: prove the record size and the `src`/`dst` reading on the whole
    file, not 10 rows.
  - Input: `tools/rdstm_record.py`, `rdstm_schema.py`, `rdstm_scan.py`;
    `RDSTM001.DAT` from `IMG` (SHA-256 `f822044c…`, EXP-M4.1); the framing
    drift at `0x10a0`; rows below `0x1a700`; `docs/format/rdstm.md` ranked
    unknowns 1–3.
  - Done when: the EXP explains the drift (header, variable record, block
    boundary), gives the row count per region, and reports a reciprocity
    test (every `dst` appears as a `src`, or the share that does) against a
    shuffled-field control; `rdstm.md` updated.
  - Claims: C-1800–C-1809

- [x] **M4.18 — `LCTBL001` record framing**
  - Status: done · Owner: task/m4.18-lctbl-framing · Critical: no
  - Depends: —
  - Goal: per-field name counts and lengths (M4.13 could only count per
    stream).
  - Input: the 517 zlib streams (`tools/name_strings.py`), NUL-separated
    pieces (1,329,518), `rdstm.md` notes on `LCTBL`, `tools/lctbl_names.py`.
  - Done when: the record layout inside a stream is decoded (or `UNKNOWN`
    with method), a parser round-trips one stream byte-identically, and the
    EXP gives counts and max length per field.
  - Claims: C-1830–C-1839
  - Result: EXP-2026-11-06-M4.18-lctbl-framing — 16-byte header + four
    even-padded name slots + opaque footer; 247,089 records, per-field
    non-empty/max 36,461/10, 66,189/85, 243,907/99, 109,944/64;
    `tools/lctbl_records.py` round-trips all 517 streams byte-identically and
    the 2014/2016 controls use the same layout.

- [x] **M1.13 — Find the encoder that reproduces the factory `.cmp` streams**
  - Status: done · Owner: claude/m1.13-factory-encoder · Critical: yes
  - Depends: — (M3.2b names Navi.exe's static zlib 1.1.3, C-2061)
  - Goal: M5.12c renamed 131 of 136 POI records. The five left sit on pages
    whose edited stream is larger than the original slot: stock zlib 1.3.x at
    levels 1–9 is 0.8 % larger than the factory encoder on the same bytes. No
    slot-fit strategy works until an encoder reproduces the factory bytes.
  - Input: `tools/mutate_refer_poi.py` (`page_encoder` tries zlib levels and
    memLevels on the original stream; none matches), the M5.12c EXP on branch
    `claude/m5.12c-poi-copies` (`POINT001–009` factory pages; not yet merged),
    the `REFER001/POINT0xx.DAT.cmp`
    of the US card (`archive/sd-images/LEAF_2011-2012_US.img`), C-2061.
    Candidates: zlib 1.1.3, zlib 1.2.x, zlib-ng, libdeflate, zopfli-style optimal
    parsing.
  - Done when: a tool reproduces the factory inner stream byte-for-byte for at
    least 20 pages of `POINT001–009` (count and list in the EXP), with a
    negative control (a changed byte gives a different stream), and the
    candidate that matches is named with its version. If none matches, the EXP
    lists every candidate's byte difference and the status is `blocked`.
  - Result: EXP-2026-11-08-M1.13-factory-encoder. 471/471 inner pages of POINT001–009 reproduced exactly by stock zlib L6/memLevel 8 (release-indistinguishable, 1.1.3 to 1.3.2); zlib-ng 0/471; `tools/factory_zlib.py` added. The "0.8 % larger" premise is not reproduced (C-2575).
  - Claims: C-2570–C-2579

- [x] **M5.21 — Slot budget for generated pages: reject or re-pack, never overrun**
  - Status: done · Owner: claude/m5.21-slot-budget · Critical: yes
  - Result: EXP-2026-11-08-M5.21-slot-budget. `tools/slot_budget.py` (calibrate/build/verify, selftest 14/14). 4 % headroom (portability margin over the measured zlib-ng excess 3.64 %); US card: 19 pages fit with 13,749 names, 8,210 refused and listed, verify PASS, cardcheck PASS. 8,113 of 8,229 edited pages abut their neighbour, so more names need page relocation (separate task).
  - Depends: M5.13b (real-image batch path). M1.13 is **done**: stock zlib
    L6/memLevel 8 reproduces 471/471 factory `POINT001–009` pages
    (release-indistinguishable, C-2570), so the encoder is not the missing
    piece.
  - Goal: a generated page has a fixed slot (the factory stream, abutting the
    next page, C-2355 / M5.12c EXP). Edited content can compress worse than the
    original slot allows even with the factory-equivalent encoder (M5.12c: 5
    unfit edited pages). The compiler must know the slot before it writes, and
    either keep the page inside it with a stated headroom or refuse the page, so
    a card never gets a silent overrun or a broken neighbour.
  - Input: `tools/factory_zlib.py` (M1.13), `tools/mutate_refer_poi.py`
    (`refit_page`, `FitError`, the skip list in `*.skipped.json`),
    `tools/imgpatch.py`, the M5.12c EXP (**on branch
    `claude/m5.12c-poi-copies`, not yet merged**; slot rule: padding only over
    zero bytes; a stream may abut the next page), the M5.12c `plans.json`
    pattern. The slot rule will live in M5.12c's block C-2040–C-2049, **not**
    in C-2355 (that row is the imgpatch EOC fix).
  - Done when: (a) the compiler writes a per-page budget table (slot bytes,
    stream bytes, encoder used) and refuses a page whose stream exceeds
    its slot minus the headroom, with a `--selftest` on a synthetic abutting
    page; (b) on the US card, a generated edit set of at least 1000 POI names
    of mixed lengths either applies with every page inside its slot, or lists
    each refused page; no page is written past its slot (checked by
    `mkcard.diff_ranges` against the factory); (c) the EXP states the headroom
    chosen and the measured ratio that justifies it.
  - Stop: if no headroom keeps pages inside their slots on the real card, record
    the page-count and byte overflow in the EXP and set `blocked`: the next step
    is a page-relocation design (pointer tables), a separate task.
  - Claims: C-2580–C-2589

- [x] **M9.39 — A POINT010 page whose *records* differ: the L3 corpus M1.22 left to M9.10**
  - Status: done · Owner: task/m9.39-point010-mutant · Critical: no · Pair: required
  - Result: EXP-2026-11-17-M9.39-point010-mutant; C-4170–C-4178 — a +4 B rewrite of record 500 moves `n=501`/998/999 by +4 on both builds and both pages (US `0xfe4e→0xfe52`, `0x1fb82→0x1fb86`, `0x1fc0a→0x1fc0e`; EU `0xbe82→0xbe86`, `0x17af6→0x17afa`, `0x17b40→0x17b44`), count stays 1,000, `n=1000` is `None`, one outer stream of 149/151 differs; a same-length control leaves every offset at the factory value.
  - Depends: M1.22 (both walkers run on US + EU pages; done), `tools/mutate_refer_poi.py` (for the record edit)
  - Goal: M1.22's cross-build run uses two *different factory cards*, which proves the reader is not tuned to one card but not that it reads *our* bytes. The L3 corpus still has no POINT page whose record contents (name offset, coordinates, icon) were changed on purpose, so a reader that ignored the record bytes would still pass. Produce one mutated page and run all four combinations (EU/US code × factory/mutated page) so the mutation is visible in the output, not just "PASS".
  - Precheck: `python3 tools/mutate_refer_poi.py --selftest` passes; `python3 tools/point_walk_l3.py walk archive/us256.img --cmp <US>/POINT010.DAT.cmp --ind <US>/POINT010.DAT.ind --page 0x840ba0 --page-len 42848 --build us2011 | tail -1` prints `result: PASS` (the M1.22 baseline this task must not regress).
  - Scope: one mutated `POINT010` pair written outside the repo (`archive/` only; commit hashes, offsets and the record diff, never bytes), the four L3 runs, and the OP-level observation that a moved name/coordinate changes the firmware's returned offset but not the record count. No map-format claim and no writer change.
  - Input: `tools/mutate_refer_poi.py` (record name/offset edit), `tools/point_walk_l3.py` (`walk`, `skip`, `--build`), `tools/cmpind.py`/`cmpind_writer.py` to rebuild the pair, `archive/us256.img` + `archive/head256.img`, a `POINT010` pair from either factory tree.
  - Hints: mutate a record the walker already samples (`n=500` or `n=998`) so the change lands in the printed table; run the unmutated page first as the positive control and the mutated page second; a reader that returns the factory offset for the mutated record is the failure this task exists to expose. Rebuild only the 64 KiB chunk that holds the record (AGENTS "Writing data back"), keep the other streams verbatim, and record the `.ind` offset change.
  - Done when: an EXP table `code build / page / sampled records / result` shows the mutated record's firmware offset differs from the factory one in all four runs (or a named, justified case where it does not), the record count is unchanged, and the mutated pair's `.cmp`/`.ind` SHA-256 and the record's byte offset are in the record; `python3 tools/gate.py` green.
  - Stop: if the mutation changes the record count or the walker stops before the sampled record, treat it as a corrupt page, record the stop, and pick a record whose length does not change rather than resizing the page.
  - Falsifier: every run prints the same offsets for the mutant and the factory page (the reader ignored the record bytes).
  - Claims: C-4170–C-4179

- [x] **M8.A2 — Machine skeleton** `hw/sh4/ze0.c`: `sh7785`, RAM at phys
  `0x08000000` (128 MiB), P1/P2 aliases, unimplemented-device catch-all over
  `0xff800000`–`0xffffffff` and areas 4/6, `select SH4_CCN` with
  `sh4_ccn_iomem()` at `0xff000000` and `sh4_ccn_arrays()` at `0xf0000000`,
  and one `ze0-stubs` instance.
  - Status: done · Owner: task/m8.a2-reprobe · Critical: yes
  - Re-probe (2026-11-17): `build.sh --force --jobs 8` applies all five
    sorted patches on pristine 8.2.7, builds `qemu-system-sh4` and `-M help`
    lists `ze0` (C-4310). `-M ze0` boots `archive/head256.img` the full 10 s
    wall clock with `exceptions: 0` and one unmodelled access, `write 0x38`
    (C-4311). The patch shipped with two bugs, each fixed and each reproduced
    by its own negative control: a second `ze0.ram` block beside
    `default_ram_id` (`RAMBlock "ze0.ram" already registered, abort!`) and
    `config ZE0` without `UNIMP` (`unknown type 'unimplemented-device'`).
    The old access-list clause is **withdrawn as a board defect**, not failed:
    a machine that maps `sh4-ccn` at `0xff000000` cannot emit the `-M none`
    invalid list, and it already differs with the same `run.sh` extents
    (1 vs 8, C-4312), so the clause contradicted the task's own purpose.
    The exempted `final pc`/"2 854 passes" numbers were **samples**, not
    results (`run.sh:542-548` polls HMP on a wall clock; 6 ze0 runs gave 6
    PCs); the record now carries only the stable observables plus a
    repeat-run table.
  - Depends: — (M8.A1, M8.A4 and M8.A5 are merged)
  - Note (PM 2026-11-06): the three series were never built together. M8.A1 saw
    `m8a4-0002/0003` rejected on 8.2.7; M8.A4/M8.A5 report them applying (the
    0003 banner says "Base: QEMU 8.2.7"). Settled: one clean
    `build.sh --force` over `patches/*.patch` applies all five in `LC_ALL=C`
    order (C-4310).
  - Note (2026-11-17, former blocker): the `write 0x38` null store on the
    declared-length load (`nk.exe 0x8802ec46`, `r2 = 0`) and the
    `0x040 [tlb_miss] pc=0x00005bd0` chain on the probe's full extents are
    follow-ups for **M8.A3** (loader/root cause), not gates of this task.
    The oracle is version-sensitive: `ce_qemu_probe.py` must be given
    `--qemu <8.2.7 build>` (PATH is 11.1.3, which yields 0 accesses).
  - Done when: `bash tools/qemu-ze0/build.sh --force` applies every patch,
    builds, and `qemu-system-sh4 -M help` lists `ze0`; `-M ze0` boots
    `archive/head256.img` for ≥10 s wall clock with 0 CPU exceptions and a
    stable access list (1 unmodelled access, `write 0x38`); that residual
    store is attributed to a named instruction; the run log and the final
    patch order are in the EXP. (The earlier clause "`-M ze0` reproduces the
    `ce_qemu_probe.py` access list" is withdrawn: see C-4312.)
  - Result: EXP-2026-11-17-M8.A2-machine-skeleton-reprobe (C-4310 build,
    C-4311 boot, C-4312 machine-vs-extent; C-1240 corrected). Patch:
    `tools/qemu-ze0/patches/ze0-0001-hw-sh4-ze0-machine.patch`
    (SHA-256 `59a47b7f…a9792`).
  - Claims: C-1240–C-1249

- [x] **M8.A10 — Bump the QEMU pin 8.2.7 → 8.2.10**
  The pin is 8.2.7 (2024-09-18) while 8.2.10 (2025-03-26) is the last release
  of the same branch and the whole series applies to it unchanged. Move the
  pin, make the hash table per-version, and add `--check-version` so the next
  bump is a probe rather than a heroic edit.
  - Status: done · Owner: task/m8.a10-bump-qemu-8210 · Critical: no
  - Depends: — (M8.A2 merged)
  - Goal: the default build is 8.2.10 and an unpinned version can be probed
    without being built.
  - Precheck: `diff -r` of `hw/sh4`, `configs/devices/sh4-softmmu` and
    `include/hw/sh4` between 8.2.7 and 8.2.10 must be empty, and all five
    patches must apply to pristine 8.2.10 without an edit. Both measured:
    trees byte-identical, 5/5 apply (C-4330).
  - Scope: `QEMU_PINS` table (8.2.7 kept, 8.2.10 default), a full build that
    refuses an unpinned version, `--check-version V` that verifies/extracts/
    applies/reports and builds nothing, README pin table and the "8.2 LTS"
    wording (8.2 is EOL), `--selftest` coverage for the table and the probe.
  - Done when: `build.sh --force` builds 8.2.10, `-M help` lists `ze0`, and
    `-M ze0` boots `archive/head256.img` with the same stable observables as
    the 8.2.7 build (0 exceptions, one `write 0x38`); `--selftest` passes;
    `--check-version 11.1.3` prints a per-patch verdict without building.
  - Stop: if any patch needs an edit for 8.2.10, that is a porting delta, not
    a bump — stop, keep the 8.2.7 pin, and record it as input for M8.A9.
  - Result: EXP-2026-11-17-M8.A10-bump-8210 (C-4330).
  - Claims: C-4330–C-4339
