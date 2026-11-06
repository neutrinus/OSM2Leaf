# L3 harness skeleton

Runnable scaffolding for the L3 contract oracle described in
[`docs/research/l3-ghidra.md`](../../docs/research/l3-ghidra.md). It makes the
plan executable **without vendor data and without Ghidra**: everything except
the final `run` works on synthetic files, and `run` reports
`MISSING_GHIDRA`/`BLOCKED` instead of pretending to pass.

L3 is a **contract oracle**, not an acceptance test. Nothing here proves that
the unit accepts a card; that is L4.

## Files

| File | Purpose |
| --- | --- |
| `manifest.py` | build/validate the corpus manifest (paths, SHA-256, size, reader, case, verdict) |
| `corpus.py` | build/check a synthetic corpus (cmp, DRSTR, tile, hdd_info) and its manifest; `build DIR`, `check DIR`, `--selftest` |
| `stubs.py` | declarative WinCE stub table with signatures, side effects and notes; emits JSON Schema |
| `dispatch.py` | `module!export`/ordinal dispatcher and deterministic hosts: virtual FS, heap, critical sections, registry; see [`EXP-2026-11-06-M9.3-stub-bind.md`](../../docs/experiments/EXP-2026-11-06-M9.3-stub-bind.md) |
| `rommap.py` | `ce_rom_parse.py` JSON -> Ghidra loader memory-map JSON |
| `ghidra_import.py` | headless Ghidra project from a `cerom.py memmap`: sections at their VAs, export/thunk labels, SH-4 calling convention; `--plan`, `--json`, `--selftest` — see [`EXP-2026-11-06-M9.2-ghidra-import.md`](../../docs/experiments/EXP-2026-11-06-M9.2-ghidra-import.md) |
| `runner.py` | `check`, `plan`, `targets`, `run FUNC --input FILE [--engine pysh4|ghidra|qemu]`; stable exit codes, never fakes a pass — see [`EXP-2026-11-06-M9.5-runner.md`](../../docs/experiments/EXP-2026-11-06-M9.5-runner.md) |
| `engine.py` | one engine interface, three SH-4 back ends (`PySh4`, Ghidra, QEMU); `--selftest`, `--probe`, `--demo` — see [`EXP-2026-11-06-M9.4-engine.md`](../../docs/experiments/EXP-2026-11-06-M9.4-engine.md) |
| `selftest.py` | 19 synthetic checks (no network, no vendor data, no Ghidra) |
| `__init__.py` | package marker |

## Quick start

```bash
# 1. self-test: no inputs required
python3 tools/l3_harness/selftest.py

# 2. schema and stub table
python3 tools/l3_harness/manifest.py schema
python3 tools/l3_harness/stubs.py list
python3 tools/l3_harness/stubs.py schema

# 3. build a corpus manifest for a staging tree
python3 tools/l3_harness/manifest.py build \
  --root /tmp/l3/corpus --out /tmp/l3/manifest.json \
  --case factory:cmp_ind:REFER001/ADDRE001.DAT.cmp \
  --case corrupt_ind:cmp_ind:REFER001/ADDRE001.DAT.cmp.bad-ind \
  --case tile_factory:tile:MAPAL001/B28R070R.DAT \
  --case drstr_factory:drstr:DRSTR001.DAT \
  --case hdd_info_factory:hdd_info:VER_INFO/HDD_INFO.TXT

# 4. memory map from a CE ROM report
python3 tools/l3_harness/rommap.py convert \
  --report /tmp/opencode/ce-rom-report.json \
  --segment 0 --out /tmp/l3/rommap.json

# 5. validate, then print the plan
python3 tools/l3_harness/runner.py check \
  --manifest /tmp/l3/manifest.json --rommap /tmp/l3/rommap.json \
  --root /tmp/l3/corpus
python3 tools/l3_harness/runner.py plan \
  --manifest /tmp/l3/manifest.json --rommap /tmp/l3/rommap.json
```

`runner.py run` needs Ghidra; without it the command exits `3` and prints
where it looked and how to install it.

The package lives one level below `tools/`, and `tools/selftest.py` only
discovers `tools/*.py`, so this self-test is **not** picked up by the repo
runner yet. Run it explicitly.

## Corpus manifest

```json
{
  "schema": "osm2leaf.l3.manifest/v1",
  "generator": "tools/l3_harness/manifest.py",
  "corpus": [
    {
      "id": "factory-refer001-addre001-dat-cmp",
      "case": "factory",
      "reader": "cmp_ind",
      "path": "REFER001/ADDRE001.DAT.cmp",
      "sha256": "…64 lowercase hex…",
      "size": 1234,
      "expected": "ACCEPT",
      "notes": "optional"
    }
  ]
}
```

Rules enforced by `manifest.validate`:

- `path` is relative, uses `/`, never escapes the root; the manifest holds no
  data, only names and hashes;
- with `--root`, every file must exist with the recorded size and SHA-256;
- `expected` is exactly `ACCEPT` or `REJECT`; `MAYBE`, `accept` or `true` are
  errors, and the verdict must match the case's rule;
- `reader` and `case` must be known, and the case must apply to the reader;
- ids and `(path, reader)` pairs must be unique; unknown keys (for example
  `sha_256`) are rejected.

Cases: `factory`, `noop_rebuild`, `recompressed`, `poi_rename`, `corrupt_ind`,
`truncated_cmp`, `tile_factory`, `tile_edited`, `drstr_factory`,
`drstr_size_mismatch`, `hdd_info_factory`, `hdd_info_mismatch`.

Readers: `cmp_lst`, `cmp_ind`, `drstr`, `tile`, `hdd_info`.

`build` computes hashes from a staging tree; mutated copies live there under
the corpus root. `refresh` re-hashes an existing manifest, `validate` checks
one, `schema` prints the JSON Schema.

## Stub table

`stubs.py` is the single source of truth for the mocked calls: `coredll`
file I/O and allocators, `memset`/`memcpy`/`strlen`/`sprintf`, and the Clarion
`OSM_Printf`/`OSM_LogMsg` diagnostics. Every entry carries the prototype,
argument list, return rule, interception binding, ordered side effects, a
`modeled`/`planned` status and honest notes.

Determinism rules baked into the table:

- no wall clock, no host paths, no screen or terminal output;
- uninitialised allocations are zeroed or poisoned (`0xcd`) and logged, never
  left to host memory;
- an unknown call, an unbounded `sprintf` conversion, an asynchronous read or
  a `StatusData` call stops the run with a clear error instead of guessing;
- `READER_STUBS` lists the stubs each reader needs, so `runner plan` can show
  what is missing for `cmp_ind`, `drstr`, `tile`, `hdd_info` and `cmp_lst`.

`stubs.py schema` emits the JSON Schema; `stubs.py json` dumps the table.

## Memory map

`rommap.py` accepts the plain JSON report of `tools/ce_rom_parse.py` with a
section table per module:

```json
{"segments": [{"segment_base": "0x200200", "phys_base": "0x8cae1000",
  "romhdr": {"ulRAMStart": "0x8c000000", "ulRAMEnd": "0x8c100000"},
  "modules": [{"name": "Navi.exe", "sections": [
    {"name": ".text", "va": "0x8cae1000", "file_offset": 4096,
     "size": 8192, "characteristics": "0x60000020", "compressed": false}]}]}]}
```

It never imports `tools/cerom.py`. Section fields also accept the `o32_rom`
aliases (`realaddr`, `dataptr`, `vsize`, `psize`, `flags`), so the map can be
generated directly once `tools/cerom.py` exists. Output has one segment per
document (a Ghidra program is one build), blocks sorted by address, plus:

- `source` — image basename and SHA-256, segment base, physical base, `pTOC`,
  `ROMHDR` bounds; no host path;
- `processor` — `SuperH:BE:32:SH-4`, with `verified: false` until a real run
  confirms the language id;
- `ram` — `ROMHDR.ulRAMStart..ulRAMEnd` for the heap/stack;
- `skipped` — compressed sections omitted with `--skip-compressed`.

Rejected: compressed sections (`IMAGE_SCN_COMPRESSED`, `0x2000`) because no CE
decompressor exists yet, overlapping sections, zero-sized sections, sections
outside the 32-bit address space, file ranges past `image_size`, unknown
segment indices and duplicate module names. A BSS section (`0x80`, `psize` 0)
is kept with `file_backed: false` and `file_offset: null`.

`--text` prints the diagnostic `start end name permissions` listing. It is not
a Ghidra loader file format.

## Runner

| Command | Without Ghidra | With Ghidra but incomplete |
| --- | --- | --- |
| `check` | validates both inputs; exit 0/1 | same |
| `plan` | prints targets, stubs, blockers; exit 0/1 | same |
| `run` | `MISSING_GHIDRA`, exit 3 | `BLOCKED`, exit 4 |

Exit codes: `0` pass, `1` invalid inputs, `2` usage, `3` Ghidra missing,
`4` blocked, `5` result mismatch. `run` returns `0` only after a real
`analyzeHeadless` run wrote a result JSON whose verdicts match **every**
manifest entry; a missing case is a mismatch. `--dry-run` prints the command
and explicitly claims no verdict.

`analyzeHeadless` is looked up in this order: `--headless`, `$GHIDRA_INSTALL_DIR`,
`$GHIDRA_HOME`, `$PATH`, then `ghidra*` under `/opt`, `/usr/local`,
`/usr/share` and `$HOME`. A failed lookup lists every candidate it tried.

## Status

| Component | Status |
| --- | --- |
| corpus manifest format + build/validate | **implemented**, synthetic test passes |
| stub table + JSON Schemas | **implemented**, `modeled`/`planned` per call |
| `ce_rom_parse.py` JSON -> memory map | **implemented** for the documented schema; real section table still needs `tools/cerom.py` |
| `runner check` / `plan` | **implemented** |
| `runner run` | **blocked**: no Ghidra in this environment, no P-code harness script, no located reader |
| Ghidra P-code harness (`ghidra/l3_run.py`) | **not started** |
| Locatable reader entry points | **UNKNOWN**: `.cmp`/`.ind`, tile, DRSTR and the `HDD_INFO` parser are not located; only the map-code comparator chain has file offsets |
| Real corpus (factory files) | **blocked**: vendor data is not available in this checkout; only synthetic corpus was exercised |

## License

GPL-3.0-or-later, like the rest of `tools/`. No vendor data is committed.
