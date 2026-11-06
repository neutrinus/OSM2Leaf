# Experiments

This directory is the **append-only record of what we tried**. It exists so a
future researcher can reproduce a result, challenge it, or avoid redoing it.

The repo uses two layers:

| Layer | Location | Changes |
| --- | --- | --- |
| Current knowledge | `docs/format/*.md`, `docs/research/claims.md` | Updated continuously; reflects the best current answer |
| Experiment log | `docs/experiments/EXP-*.md` | Append-only; one record per experiment, not rewritten after completion |

If the current knowledge changes, update the format doc and the claim ledger.
Do **not** rewrite the old experiment; add a new one and link
`Supersedes: EXP-...`.

## Naming

```
EXP-YYYY-MM-DD-<TASK>-short-slug.md
```

Example: `EXP-2026-11-06-M1.2a-comp-header.md`, where `<TASK>` is the
`TODO.md` task ID the experiment belongs to. A second record for the same
task adds `-2`, `-3`. Many agents work in parallel and each task has one
owner, so the task ID keeps names unique; sequential numbers collided
(two `EXP-2026-11-05-48` drafts). Records made before 2026-11-06 keep their
old `EXP-YYYY-MM-DD-NN-slug.md` names. Claim IDs come from the task's
reserved block (see `TODO.md` "ID allocation").

## Status values

| Status | Meaning |
| --- | --- |
| `planned` | Question and method defined, not run |
| `running` | In progress |
| `done` | Ran to completion; conclusion recorded |
| `inconclusive` | Ran, but the result does not answer the question |
| `failed` | Could not run (missing sample, tool, hardware) |
| `refuted` | Ran and disproved the hypothesis |

## What every record must contain

Start from [`TEMPLATE.md`](TEMPLATE.md). At minimum:

1. **Question** — one question, not a topic.
2. **Hypothesis** — what you expect, or `none / exploratory`.
3. **Inputs** — sample name + SHA-256, file offsets, tool versions.
4. **Method** — exact commands, rerunnable by another person.
5. **Observations** — raw outputs, hexdumps, counts. Do not mix interpretation
   into this section.
6. **Interpretation** — `FACT` / `OBSERVED` / `HYPOTHESIS` / `UNKNOWN`.
7. **Conclusion** — which claims and format docs changed.
8. **Follow-ups** — new questions, with links to `TODO.md`.

## Reproducibility checklist

- Pin the input by SHA-256, not just a filename.
- Use a command that works from a clean checkout + the external sample.
- Prefer `tools/` over ad-hoc one-liners; add a small tool if needed.
- Record negative results; they prevent repeated dead ends.
- Never commit vendor data. Put images/extracts in `archive/` or `/tmp` and
  record only hashes, offsets and tiny non-vendor outputs.
- If the experiment depends on hardware (car/unit/card), say so and mark the
  status honestly.

## Linking

```
format doc  ->  claim ID  ->  EXP record  ->  tool command
```

- Format docs cite claim IDs, not experiment narratives.
- `claims.md` evidence should cite the `EXP-...` ID and/or a command.
- Experiment records list the claims they created or changed.

## Index

| ID | Title | Status |
| --- | --- | --- |
| [EXP-2026-11-05-01](EXP-2026-11-05-01-drstr-node-table.md) | Correct DRSTR001.DAT node table | done |
| [EXP-2026-11-05-02](EXP-2026-11-05-02-refer-poi-rename.md) | Same-length POI rename in REFER001 | done offline; hardware pending |
| [EXP-2026-11-05-03](EXP-2026-11-05-03-checksums.md) | Firmware checksums and per-file integrity | done |
| [EXP-2026-11-05-04](EXP-2026-11-05-04-tile-roundtrip.md) | ZE0 tile round-trip and viewer | done for clean tiles; dense tiles open |
| [EXP-2026-11-05-05](EXP-2026-11-05-05-firmware-crosscheck.md) | Firmware section table and reader cross-check | done (readers not located) |
| [EXP-2026-11-05-06](EXP-2026-11-05-06-cmp-writer.md) | `.cmp`/`.ind` writer and byte-identity | done |
| [EXP-2026-11-05-07](EXP-2026-11-05-07-firmware-readers.md) | Dual-base Ghidra and reader search | done (negative; strategy changed) |
| [EXP-2026-11-05-08](EXP-2026-11-05-08-poi-joins.md) | POI page mapping, point roles and icons | done (icon-id mapping open) |
| [EXP-2026-11-05-09](EXP-2026-11-05-09-firmware-round4.md) | Firmware round 4: retractions and Lib.out32 | done (readers still not located) |
| [EXP-2026-11-05-10](EXP-2026-11-05-10-firmware-round5.md) | Firmware round 5: section placement is the blocker | done (readers still not located) |
| [EXP-2026-11-05-11](EXP-2026-11-05-11-firmware-exports.md) | Export anchors and the RAM copy list | done (26 modules mapped; navi modules open) |
| [EXP-2026-11-05-12](EXP-2026-11-05-12-tile-dense-roads.md) | Dense tile, roads and streaming writer | done (container); roads partial |
| [EXP-2026-11-05-13](EXP-2026-11-05-13-firmware-import-anchor.md) | Import anchor fails; ROM module table next | done (navi base still open) |
| [EXP-2026-11-05-14](EXP-2026-11-05-14-firmware-static-va.md) | Static VA recovery is exhausted | done (method change) |
| [EXP-2026-11-05-15](EXP-2026-11-05-15-tile-section4-roads.md) | Section-4 index, road names and streaming decoder | done (attributes partial) |
| [EXP-2026-11-05-16](EXP-2026-11-05-16-mapcode-tile-contract.md) | Map-code comparator and tile contract | done (parser still missing) |
| [EXP-2026-11-05-17](EXP-2026-11-05-17-mapcode-test-package.md) | Comparator corrected; HDD_INFO test package | done (parser behind COM) |
| [EXP-2026-11-05-18](EXP-2026-11-05-18-verinfo-com.md) | VerInfoCC is not the HDD_INFO parser | done (missing link 0x30f008) |
| [EXP-2026-11-05-19](EXP-2026-11-05-19-usrextract.md) | The 0x30f008 trail is false; follow USR_Convert_* | done (false trail closed) |
| [EXP-2026-11-05-20](EXP-2026-11-05-20-reader-trace.md) | Container reader trace: corrections and new anchors | done (readers not found) |
| [EXP-2026-11-05-21](EXP-2026-11-05-21-hddinfo-builder.md) | Three-filter literals and the HDD_INFO builder | done (parser one hop away) |
| [EXP-2026-11-05-22](EXP-2026-11-05-22-va-not-injective.md) | The VA map is not injective; XIP table is the key | done (structural blocker) |
| [EXP-2026-11-05-23](EXP-2026-11-05-23-import-thunks.md) | 0x2e0xxxx is an import-thunk area | done (new anchors) |
| [EXP-2026-11-05-24](EXP-2026-11-05-24-no-xip-table.md) | No XIP table; module bases are wrong | done (static VA exhausted) |
| [EXP-2026-11-05-25](EXP-2026-11-05-25-navi-com.md) | No import descriptor; NaviStateCC is COM | done (reader not located) |
| [EXP-2026-11-05-26](EXP-2026-11-05-26-com-relocation.md) | COM framework, relocation wall and breakpoint | done (dynamic path identified) |
| [EXP-2026-11-05-27](EXP-2026-11-05-27-ipodcc-vtable.md) | The 175-method vtable is iPodCC, not NaviStateCC | done (wrong module corrected) |
| [EXP-2026-11-05-28](EXP-2026-11-05-28-initializer-runtime-vtable.md) | Initializer found; vtable built at runtime | done (reader still unknown) |
| [EXP-2026-11-05-29 (static-closed)](EXP-2026-11-05-29-static-closed.md) | Static is closed for the NaviStateCC vtable | done (dynamic guide ready) |
| [EXP-2026-11-05-29 (l1-l2-validators)](EXP-2026-11-05-29-l1-l2-validators.md) | L1/L2 validators for the offline feedback loop | done |
| [EXP-2026-11-05-30](EXP-2026-11-05-30-image-matrix.md) | Complete map-image archive and cross-year L1 matrix | done |
| [EXP-2026-11-05-31](EXP-2026-11-05-31-cross-year-l2.md) | Cross-year L2 for the 2014 and 2016 cards | done |
| [EXP-2026-11-05-32](EXP-2026-11-05-32-cross-year-differential.md) | Cross-year differential of the 2011/2014/2016 images | done |
| [EXP-2026-11-05-33](EXP-2026-11-05-33-ce-rom-segment.md) | CE ROM segment recovery with `ce_rom_parse.py` | done |
| [EXP-2026-11-05-34](EXP-2026-11-05-34-ce-rom-segment-parser.md) | CE ROM segment parser | done |
| [EXP-2026-11-05-35 (ce-romhdr)](EXP-2026-11-05-35-ce-romhdr.md) | CE ROM header and module TOC are present | done (C-380/C-381 retracted) |
| [EXP-2026-11-05-35 (us-card-validator)](EXP-2026-11-05-35-us-card-validator.md) | US 2011 card: L1/L2 validator quirks | done |
| [EXP-2026-11-05-36](EXP-2026-11-05-36-all-ce-images.md) | Three CE images; B/C are kernel regions; COREDLL ordinals | done |
| [EXP-2026-11-05-37](EXP-2026-11-05-37-qemu-boot-probe.md) | QEMU SH-4 boot probe (full-system emulation F0) | done (probe) |
| [EXP-2026-11-05-38](EXP-2026-11-05-38-l3-harness-skeleton.md) | L3 emulation harness skeleton | done (synthetic) |
| [EXP-2026-11-05-40](EXP-2026-11-05-40-header-block-tool.md) | Header `0x180` block tool and field inventory | done (synthetic) |
| [EXP-2026-11-05-41](EXP-2026-11-05-41-hddinfo-model.md) | HDD_INFO parser and offline map-code model M0 | done (model unvalidated) |
| [EXP-2026-11-05-42](EXP-2026-11-05-42-section4-tool.md) | Section-4 parse/preserve tool | done (preserve only) |
| [EXP-2026-11-05-43](EXP-2026-11-05-43-rdstm-schema-tool.md) | RDSTM layout hypothesis harness | done (synthetic) |
| [EXP-2026-11-05-44](EXP-2026-11-05-44-imf-definition.md) | Intermediate map format (IMF v1) and validator | done (design) |
| [EXP-2026-11-05-45](EXP-2026-11-05-45-profile-validator.md) | Build-profile schema validator and dry-run builder | done (design) |
| [EXP-2026-11-05-53](EXP-2026-11-05-53-cerom-decompress.md) | `cerom.py decompress` for compressed sections (M1.3) | done (synthetic) |
| [EXP-2026-11-05-M1.2b](EXP-2026-11-05-M1.2b-decoder-probe.md) | Public LZ decoders and offset probe (M1.2b) | blocked: no real payload |
| [EXP-2026-11-05-M1.6b](EXP-2026-11-05-M1.6b-thunks.md) | Full import-thunk resolver (M1.6b) | done (synthetic; real coverage UNKNOWN) |
| [EXP-2026-11-05-M1.2a](EXP-2026-11-05-M1.2a-comphdr.md) | Compressed-section header parser (M1.2a) | done (2 real prefixes) |
| [EXP-2026-11-06-M6.3](EXP-2026-11-06-M6.3-card-plan.md) | Spare-card test plan (M6.3) | done (planning) |
| [EXP-2026-11-06-M6.8](EXP-2026-11-06-M6.8-bench-kit.md) | Bench kit and access plan (M6.8) | done (planning; no hardware) |
| [EXP-2026-11-05-55](EXP-2026-11-05-55-filesentry-extract.md) | Compressed FILESentry extraction (M1.4) | done (synthetic) |
| [EXP-2026-11-05-54](EXP-2026-11-05-54-kernel-select.md) | Kernel B/C selection criteria (M1.7) | done (synthetic; real image gives UNKNOWN) |
| [EXP-2026-11-05-52](EXP-2026-11-05-52-cecompress-decoder.md) | CE ROM section codec candidates (LZSS/LZX) | done (synthetic symmetry only) |
| [EXP-2026-11-05-48](EXP-2026-11-05-48-cerom-memmap.md) | `cerom.py memmap` / Ghidra memory map (M1.5) | done (synthetic) |
| [EXP-2026-11-05-47](EXP-2026-11-05-47-cerom-selftest.md) | `cerom.py` synthetic self-test (M1.1) | done (synthetic) |
| [EXP-2026-11-05-46](EXP-2026-11-05-46-diff-years-tool.md) | Cross-year differential tool (`diff_years.py`) | done (synthetic) |
| [EXP-2026-11-05-M1.8](EXP-2026-11-05-M1.8-sh4xref.md) | SH-4 literal/xref helper `sh4xref.py` (M1.8) | done |
| [EXP-2026-11-05-M2.1](EXP-2026-11-05-M2.1-hddinfo-fn.md) | `Navi.exe` `HDD_INFO.TXT` function `0x004e7b8c` (M2.1) | partial; blocker refuted by EXP-2026-11-06-H5 |
| [EXP-2026-11-05-M2.9](EXP-2026-11-05-M2.9-error-catalogue.md) | Error-screen catalogue (M2.9) | done |
| [EXP-2026-11-05-M2.10](EXP-2026-11-05-M2.10-testmode.md) | `TestMode.exe` diagnostics (M2.10) | done |
| [EXP-2026-11-05-M4.1](EXP-2026-11-05-M4.1-rdstm-record.md) | One `RDSTM001` row, decode and round-trip (M4.1) | done (semantics HYPOTHESIS) |
| [EXP-2026-11-05-M4.2](EXP-2026-11-05-M4.2-rdstm-link-attrs.md) | `RDSTM001` link attributes vs OSM (M4.2) | blocked (no OSM access, no coordinates) |
| [EXP-2026-11-05-M4.5](EXP-2026-11-05-M4.5-mmain001.md) | `MMAIN001.DAT` is a FAT root-directory log (M4.5) | done |
| [EXP-2026-11-05-M4.6](EXP-2026-11-05-M4.6-b30r048r-diff.md) | `B30R048R` 2013–2016 rebuild difference (M4.6) | done |
| [EXP-2026-11-05-M4.13](EXP-2026-11-05-M4.13-strings.md) | Name strings: charset, lengths, Polish letters (M4.13) | done (collation UNKNOWN) |
| [EXP-2026-11-05-M5.8](EXP-2026-11-05-M5.8-tile-diff.md) | One-tile diff report `tile_diff.py` (M5.8) | done |
| [EXP-2026-11-06-H5](EXP-2026-11-06-H5-pm-review.md) | Board review; real-image checks of synthetic-only results (H5) | done |
