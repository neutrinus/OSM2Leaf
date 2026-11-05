# L3: running the original readers under Ghidra

> **Status:** design / TODO. No L3 harness exists yet. This is the plan for a
> complete L3, not a claim that the readers are already located.

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

The unresolved module base is the current blocker. L3 can start with functions
whose VA is known or with a local harness that maps code at a chosen base and
patches absolute literals; the latter is a research step, not a general
solution.

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

## Risks

- The navi/map modules have no export/import anchor; static VA recovery is
  exhausted. Relative call-graph tracing may not reach every reader.
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
  [`feedback-loop.md`](feedback-loop.md).

## First steps

- [ ] Trace the `CMP.LST` opener and map-path function from the known anchors.
- [ ] Build a minimal Ghidra headless harness for one function with a fake
      `CreateFile`/`ReadFile`.
- [ ] Add the `.cmp`/`.ind` reader and its corpus.
- [ ] Add the `DRSTR` parser and its corpus.
- [ ] Add the tile reader and its corpus.
- [ ] Record every run as an `EXP-...` with the exact memory map and stubs.

