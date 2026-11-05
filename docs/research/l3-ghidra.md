# L3: running the original readers under Ghidra

> **Status:** design plus a runnable skeleton (`tools/l3_harness/`). The
> manifest, stub table and memory map can be validated today; the runner
> refuses to claim a pass without Ghidra and a located reader. No reader is
> located and no Ghidra harness script exists yet, so **no L3 result is
> claimed**.
>
> **Update 2026-11-05:** the old blocker ("unresolved module base") is gone.
> `tools/cerom.py` gives every module section's real VA (EXP-2026-11-05-35/36),
> code is never compressed (C-530), and stock QEMU's SH-4A CPU runs this
> firmware (EXP-2026-11-05-37), so QEMU is a second engine next to Ghidra.
> The planned tool layout and the day-to-day workflow are in
> [How to use L3](#how-to-use-l3-target-workflow) below.

## Goal

Use the original firmware code as a **second reader** for the map data, without
booting the unit and without a full-system emulator. A complete L3 means:

1. the `CMP.LST`/map-path opener, `.cmp`/`.ind` reader, `DRSTR` parser and tile
   reader are located and runnable;
2. they run headlessly in Ghidra P-code with mocked WinCE I/O;
3. they agree with the Python readers on a fixed test corpus;
4. the harness and corpus are reproducible from a clean checkout plus the
   external image.

L3 is a **contract oracle**, not an acceptance test. It cannot prove SD-lock,
map-code, rendering, routing or CAN behaviour; that is L4.

## Why Ghidra

- Ghidra 12.2 already decodes SH-4 and can run P-code headlessly.
- It gives per-function control: map memory, set registers, intercept calls,
  stop at a return, and inspect buffers.
- `qemu-sh4` linux-user exists, but it expects Linux ELF and a Linux syscall
  ABI; a Ghidra harness is simpler for individual functions.
- A custom SH-4 harness is the fallback if P-code emulation hits an
  unsupported instruction or a timing-sensitive path.

## Architecture

### 1. Function discovery

Start from the known anchors and walk relative calls/returns:

- `CMP.LST` opener and map-path construction;
- the `.cmp`/`.ind` reader (zlib calls, descriptor fields);
- the `DRSTR001.DAT` parser (40-byte nodes, 32-byte entries);
- the tile reader (`MESH_ID`/`DIVID`, `0x1ac` level table, tile section table).

For each function record:

| Field | Example |
| --- | --- |
| file offset | `0xc438a4` |
| VA | depends on the module delta |
| code/data delta | local to the module |
| callers / callees | relative `bsr`/`jsr` targets |
| I/O calls | file open/read/seek, zlib, allocator |
| test vector | input file and expected output |

Do not assume a global `VA = file + constant`; the ROM uses section placement.
Accept a delta only when several pointers/strings agree.

### 2. Memory map

The harness needs:

- ROM code and `.rdata` at the VAs the function expects;
- a writable stack and heap;
- file buffers for the input corpus;
- stubs for the WinCE API and any imported library functions.

Use `cerom.py` (TODO M9.1 `memmap`) for all of it: map **every** section of
images A and B at its `o32_realaddr`, not just the target module. The ROM is
pre-bound, so cross-module calls already point at real VAs; calls into
`COREDLL` land on its export VAs in image B, which is where the stubs go.
Compressed RW data sections need M1.3 (or a dump from the running kernel,
M8.E1/M8.E3) before globals have their initial values; until then, map them
zero-filled and treat any read of them as a finding to record.

### 3. API stubs

At minimum:

- `CreateFileW` / `CreateFileA` — return a fake handle and bind it to a host
  file or an in-memory buffer;
- `ReadFile`, `SetFilePointer`, `GetFileSize`, `CloseHandle`;
- `LocalAlloc` / `LocalFree` / `malloc` / `free`;
- `memset`, `memcpy`, `strlen`, `sprintf` where the compiler did not inline
  them;
- `OSM_Printf`, `OSM_LogMsg`, `StatusData` — capture diagnostics;
- registry/COM only if a reader needs the path or configuration.

Each stub must log its arguments and return value. Unknown calls should stop
the run with a clear error, not guess.

### 4. Harness

A headless Ghidra script (or pyghidra) should:

1. load the firmware/ROM slice and apply the memory map;
2. set the PC/stack/registers for the target function;
3. run until return or a stub breakpoint;
4. capture return value, output buffers, diagnostics and memory writes;
5. emit a JSON result with `accepted`, `output_size`, `records`, `errors`.

The harness must be deterministic: no wall-clock, no uninitialised memory, no
host paths in the result.

### 5. Test corpus

Run the same corpus through the firmware function and the Python reader:

| Case | Purpose |
| --- | --- |
| factory `.cmp`/`.ind` | baseline accept |
| no-op preserved rebuild | container identity |
| recompressed `.cmp` | zlib and size tolerance |
| same-length POI rename | content change accepted |
| corrupted `.ind` offset/size | rejection |
| truncated `.cmp` | rejection |
| factory tile | baseline decode |
| generated/edited tile | writer acceptance |
| factory `DRSTR001.DAT` | tree parse |
| `DRSTR` with one changed size | mismatch/rejection |
| `HDD_INFO` variants | map-code comparator (when its parser is found) |

Normalise the outputs before comparison: sizes, offsets, record counts, and a
stable digest of parsed records. Do not compare raw pointers or heap addresses.

### 6. Acceptance criteria for "complete L3"

- All four readers (path/`CMP.LST`, `.cmp`/`.ind`, `DRSTR`, tile) run under the
  harness.
- The corpus produces the same accept/reject and the same normalised output as
  the Python tools.
- At least one generated `.cmp` and one generated tile are accepted by the
  firmware reader.
- The memory map, deltas, stubs and corpus are documented.
- `python3 tools/selftest.py` still passes, and the L3 runner is independent of
  vendor data paths.
- Negative results are recorded: any function we cannot run is marked
  `UNKNOWN` with the exact blocker.

## Interface contract (implemented skeleton)

`tools/l3_harness/` is the executable contract between the firmware report,
the corpus and Ghidra. It needs no vendor data and no Ghidra for `check` and
`plan`.

```text
ce_rom_parse.py JSON + sections[] ──rommap.py──> memory map JSON ──> Ghidra loader
   (sections filled by tools/cerom.py)                 (one segment per build)

corpus staging root ──manifest.py──> manifest JSON ──runner.py run──> result JSON
   (factory + mutated files)            (path/sha256/size/verdict)      (verdicts)

stubs.py ──> stub table + JSON Schema ──> plan output and the Ghidra script
```

| Boundary | Produced by | Consumed by | Contract |
| --- | --- | --- | --- |
| ROM section table | `tools/cerom.py` (next step) | `rommap.py` | `segments[].modules[].sections[]` with `name`, `va`, `file_offset`, `size`, `characteristics`, `compressed`; `o32_rom` aliases (`realaddr`, `dataptr`, `vsize`, `psize`, `flags`) accepted |
| Memory map | `rommap.py` | Ghidra script | `osm2leaf.l3.rommap/v1`: `source`, `processor` (`verified: false`), `ram`, `blocks[]` with `address`/`size`/`file_offset`/`permissions`/`loadable`; sorted, non-overlapping |
| Corpus manifest | `manifest.py build` | `runner.py`, Ghidra script | `osm2leaf.l3.manifest/v1`: `id`, `case`, `reader`, `path`, `sha256`, `size`, `expected` (`ACCEPT`/`REJECT`) |
| Stub table | `stubs.py` | `runner.py plan`, Ghidra script | `osm2leaf.l3.stubs/v1`: signature, args, returns, binding, ordered side effects, `modeled`/`planned` |
| Run result | Ghidra script | `runner.py` | `{"cases": [{"id", "verdict"}]}`; a missing case is a mismatch, never a pass |

`rommap.py` never imports `tools/cerom.py`; the JSON contract is the only
coupling. Compressed sections are rejected because no CE decompressor exists,
so a build containing them needs an explicit `--skip-compressed` and has a
smaller, incomplete map.

### Status

| Component | Status | Notes |
| --- | --- | --- |
| corpus manifest (`manifest.py`) | **implemented** | build/validate/refresh/schema; synthetic self-test |
| stub table (`stubs.py`) | **implemented, 14 modeled / 3 planned** | `sprintf`, `OSM_LogMsg`, `StatusData` are deliberately `planned`/`unresolved` |
| ROM report -> memory map (`rommap.py`) | **implemented** | overlaps, zero size, compressed sections and out-of-image ranges rejected; real section table still needs `tools/cerom.py` |
| `runner.py check` | **implemented** | validates manifest (+ hashes with `--root`) and memory map |
| `runner.py plan` | **implemented** | prints trace targets, per-reader stubs and blockers |
| `runner.py run` | **blocked** | exit `3` without Ghidra, exit `4` without the harness script/reader/image; never `0` |
| Ghidra P-code script (`ghidra/l3_run.py`) | **not started** | next code step after a reader is located |
| Reader entry points | **UNKNOWN** | only the map-code comparator chain has file offsets (`0x6fab2c` -> `0x6faeb0` -> `0x6fb05c`); it is a helper, not a file reader |
| Real corpus | **blocked** | vendor data is absent from this checkout; only synthetic files were used |

### What the first real run needs

1. `tools/cerom.py` emitting one build's section table with `va`,
   `file_offset`, `size`, `characteristics` and `compressed` (empty or
   explicitly skipped compressed sections).
2. One located reader entry point, with its VA taken from the memory map, not
   from a global delta. Candidates remain the `.cmp`/`.ind` reader, the tile
   reader, the `DRSTR` parser and the `HDD_INFO` parser.
3. Ghidra 12.2 or newer with a supported JDK and `analyzeHeadless`; export
   `GHIDRA_INSTALL_DIR` or pass `--headless`.
4. `tools/l3_harness/ghidra/l3_run.py`: map the blocks, place the stubs, set
   PC/stack/registers, run to return or a stub breakpoint, emit the result
   JSON.
5. A corpus staging root that matches the manifest, including the factory
   baseline, the no-op rebuild, a recompressed file, the same-length POI
   rename and the negative `.ind`/truncated cases.
6. The vendor image for `-import` (never committed) and a writable project
   directory such as `/tmp/opencode/l3-ghidra`.
7. An `EXP-...` record with the exact memory map, stub set, hashes and
   commands. Until then every reader stays `UNKNOWN`.

Quick check of the skeleton:

```bash
python3 tools/l3_harness/selftest.py
python3 tools/l3_harness/runner.py check --manifest <m.json> --rommap <r.json>
python3 tools/l3_harness/runner.py plan  --manifest <m.json> --rommap <r.json>
```

## Risks

- ~~The navi/map modules have no export/import anchor; static VA recovery is
  exhausted.~~ Resolved by the CE ROM TOC (`cerom.py`). Locating the reader
  functions is still work (M2/M3).
- Pre-bound WinCE ROM calls may be direct, so "intercept the import" is not
  enough; breakpoints on stub addresses or patched call sites are needed.
- MMU/cache behaviour, self-modifying code and indirect calls may not be
  modelled by P-code.
- Some readers may depend on global state initialised during boot (registry,
  locale, buffers); the harness must stub or initialise it.
- A function that passes the corpus is evidence, not proof that the unit
  accepts the whole card.

## Fallbacks

- `qemu-sh4` linux-user with a static SH-4 ELF harness.
- QEMU `r2d` bare-metal or MAME SH-4 for instruction-level probes.
- Full-system emulation (L5) only as a timeboxed spike; see
  [`full-system-emulation.md`](full-system-emulation.md) and TODO M8. A running
  kernel can also produce initialised process images for L3 (M8.E3).

## First steps

- [x] Skeleton: manifest, stub table, ROM report -> memory map, `check`/`plan`
      runner and a synthetic self-test
      ([`tools/l3_harness/`](../../tools/l3_harness/README.md),
      `EXP-2026-11-05-38`).
- [ ] Trace the `CMP.LST` opener and map-path function from the known anchors.
- [ ] Build a minimal Ghidra headless harness for one function with a fake
      `CreateFile`/`ReadFile`.
- [ ] Add the `.cmp`/`.ind` reader and its corpus.
- [ ] Add the `DRSTR` parser and its corpus.
- [ ] Add the tile reader and its corpus.
- [ ] Record every run as an `EXP-...` with the exact memory map and stubs.


## How to use L3 (target workflow)

> Planned interface (TODO M9). Commands below do not exist yet; they define
> what M9 must deliver. Update this section when a tool lands.

### Tool layout

| Path | Job | TODO |
| --- | --- | --- |
| `tools/cerom.py memmap` | JSON of all A+B sections at their VAs | M9.1 |
| `tools/l3/ghidra_import.py` | headless Ghidra project with the memory map, export names, IAT labels | M9.2 |
| `tools/l3/coredll_stubs.py` | host implementations of `COREDLL` exports, keyed by name | M9.3 |
| `tools/l3/engine.py` | one interface, two back ends: Ghidra P-code, QEMU + gdbstub | M9.4 |
| `tools/l3/targets.json` | named firmware functions: VA, prototype, setup, outputs | M9.5 |
| `tools/l3/run.py` | run one target on one input; JSON verdict | M9.5 |
| `tools/l3/corpus.py` | mutation corpora with the Python reader's expected verdict | M9.7 |
| `tools/l3check.py` | L3 rung of the verification ladder for a card root | M9.8 |

### One-time setup

```bash
# image slice: the firmware lives in the first ~110 MB
curl -r 0-109999999 -o fw.img https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
python3 tools/cerom.py fw.img memmap --image A,B -o work/memmap.json
python3 tools/l3/ghidra_import.py fw.img work/memmap.json --project work/ghidra   # analysis
```

### Daily loop

```bash
# one function, one input
python3 tools/l3/run.py hddinfo_compare --input card/HDD_INFO.TXT --json
# a whole corpus, firmware vs Python
python3 tools/l3/run.py hddinfo_compare --corpus hddinfo
# all targets against a built card tree (after L1/L2)
python3 tools/l3check.py --root out/card
```

A result looks like:

```json
{"target": "hddinfo_compare", "input": "HDD_INFO.TXT", "engine": "qemu",
 "returned": 0, "accepted": true, "insns": 18234,
 "stubs": [["CreateFileW", "\\Storage Card\\HDD_INFO.TXT", "0x10"],
           ["ReadFile", "0x10", 512, 512]],
 "outputs": {"struct_digest": "sha256:…"}, "python_verdict": true, "agree": true}
```

### Adding a target

1. Locate the function (M2/M3) and give it a claim + EXP.
2. Add an entry to `targets.json`: VA (from `cerom.py`, never a fitted
   delta), prototype (`r4`–`r7` arguments, stack args), how to build the
   arguments (buffers, `this` objects), what to read back.
3. Run it on the factory input first (positive control, AGENTS.md rule 2),
   then on the corpus.
4. If it stops with `missing stub: NAME`, add the stub (next section) and
   re-run; never let an unknown call return a guessed value.

### Adding a stub

Stubs are Python functions named after the `COREDLL` export, taking the SH-4
argument registers and the engine, returning `r0`. Each one logs its arguments
and result. File stubs work on a virtual file system rooted at the card tree
under test (`\Storage Card\…` → `--root`). Keep stubs deterministic: fixed
`GetTickCount`, fixed time, no host paths in results.

### Choosing the engine

- **Ghidra** to understand a function: single-step, watch P-code, inspect
  structs. Slow; fine for parsers of a few KB.
- **QEMU** to run corpora and whole call chains: native-speed SH-4A, stubs
  via gdbstub breakpoints on export VAs. Use it for anything that inflates
  zlib or walks a whole tile.
- Disagreement between the two engines on the same target is a bug in a stub
  or in the engine; record it.

### What L3 cannot tell you

Acceptance by the unit (SD lock, map code in context, rendering, routing,
CAN). Those need the full system (M8, F4+) or the bench (M6).
