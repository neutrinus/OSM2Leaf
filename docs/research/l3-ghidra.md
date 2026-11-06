# L3: running the original readers under Ghidra

> **Status:** as of 2026-11-06 the harness is **implemented and runnable without
> Ghidra** — `tools/l3_harness/` (M9.1, M9.2 plan, M9.3, M9.4, M9.5, M9.7).
> One **synthetic** target (`probe-zlib-cmf`) runs end to end on the
> pure-Python SH-4 reference engine; that proves the runner, dispatcher and
> virtual-FS path, **not** a firmware reader. **No firmware reader has run
> under L3 yet:** every reader target in `targets.json` is `blocked`, the
> Ghidra P-code harness (`tools/l3_harness/ghidra/l3_run.py`) does not exist,
> so **no L3 result is claimed**. `tools/l3check.py` (M9.8) now prints the
> per-target ladder, but every reader row in it is still `BLOCKED`; card mode
> (`--card`) is M9.12.
>
> **History.** The 2026-11-05 blockers ("unresolved module base", "no harness
> exists", "design-only") are gone: `tools/cerom.py` gives every section's
> real VA (EXP-2026-11-05-35/36), code is never compressed (C-530), stock
> QEMU's SH-4A CPU runs this firmware (EXP-2026-11-05-37), and the skeleton
> landed as EXP-2026-11-05-38. What remains is not scaffolding but content:
> turn a located reader VA into a firmware target, run it on a positive
> control, then on a corpus. The working instructions are in
> [How to use L3](#how-to-use-l3-target-workflow); the tool-level contract is
> [`tools/l3_harness/README.md`](../../tools/l3_harness/README.md).

## Goal

Use the original firmware code as a **second reader** for the map data, without
booting the unit and without a full-system emulator. A complete L3 means:

1. the `CMP.LST`/map-path opener, `.cmp`/`.ind` reader, `DRSTR` parser and tile
   reader are **located as VAs and runnable** through the runner. Today the
   `HDD_INFO` read/compare, `DRSTR` and tile functions and the `.ind` wrapper
   have VAs; the `.cmp` chunk reader is not located, and **none of them is
   runnable** because the runner has no firmware entry kind — see the matrix
   below;
2. they run headlessly on an SH-4 engine with mocked WinCE I/O;
3. they agree with the Python readers on a fixed test corpus;
4. the harness and corpus are reproducible from a clean checkout plus the
   external image.

L3 is a **contract oracle**, not an acceptance test. It cannot prove SD-lock,
map-code in context, rendering, routing or CAN behaviour; that is L4.

## Why Ghidra

- Ghidra 12.2 already decodes SH-4 and can run P-code headlessly.
- It gives per-function control: map memory, set registers, intercept calls,
  stop at a return, and inspect buffers.
- `qemu-sh4` linux-user expects a Linux ELF and a Linux syscall ABI; the
  engine therefore drives `qemu-system-sh4` (bare metal, gdbstub), not
  linux-user. A custom SH-4 harness remains the fallback if P-code emulation
  hits an unsupported instruction or a timing-sensitive path.
- The engine is pluggable, so the same target can move between Ghidra (to
  understand a function), QEMU (to run corpora) and PySh4 (the reference).
  See [Engine back ends](#engine-back-ends).

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
| VA | `0x00419684` (from `cerom.py`, never a fitted delta) |
| module / section | `Navi.exe` `.text` (via `cerom.py va2file`) |
| file offset | derived from the section, for reading bytes only |
| callers / callees | relative `bsr`/`jsr` targets |
| I/O calls | file open/read/seek, zlib, allocator |
| test vector | input file and expected output |

Do not assume a global `VA = file + constant`; the ROM uses section placement.
`tools/cerom.py` now resolves the placement from the CE ROM TOC, so a VA is
read from the section table, never fitted. A bare file offset (`0x6fab2c`) is
not a runnable address and never becomes a target.

### 2. Memory map

The engine needs:

- ROM code and `.rdata` at the VAs the function expects;
- a writable stack and heap;
- file buffers for the input corpus;
- stubs for the WinCE API and any imported library functions.

`tools/cerom.py IMG memmap` emits the section table, `tools/l3_harness/rommap.py`
normalises it, and `tools/l3_harness/ghidra_import.py` turns it into Ghidra
blocks (one program per CE build). Map **every** section of the build at its
`o32_realaddr`, not just the target module: the ROM is pre-bound, so
cross-module calls already point at real VAs; calls into `COREDLL` land on its
export VAs in build B, which is where the stubs go.

Compressed RW data sections need the CE decompressor (M1.2) before globals have
their initial values; until then `cerom.py memmap --exclude-compressed` and
`rommap.py convert/ghidra_import.py --skip-compressed` map a smaller,
incomplete image and the run must say so. A zero-stored-size BSS section (`psize` 0,
`CNT_UNINITIALIZED_DATA`) is a known `rommap.py` limitation (C-1632, M9.1);
`ghidra_import.py` maps it zero-filled, `rommap.py convert` currently rejects
it, so keep those sections out of the `runner.py check/plan` map or fix the
converter.

### 3. API stubs

The single source of truth is `tools/l3_harness/stubs.py` (24 entries: 22
`modeled`, 2 `planned`), executed by `tools/l3_harness/dispatch.py`:

- `CreateFileW` / `CreateFileA`, `ReadFile`, `SetFilePointer`, `GetFileSize`,
  `CloseHandle` — one handle table and cursor per virtual file;
- `LocalAlloc` / `LocalFree` / `HeapAlloc` / `HeapFree` — guest-region heap,
  zero on `ZEROINIT`, poisoned `0xcd` otherwise;
- `memset`, `memcpy`, `strlen`, `sprintf` — `sprintf` models the documented
  subset and rejects any other conversion;
- `InitializeCriticalSection` / `Enter` / `Leave` / `Delete` — recursion depth
  per pointer, wrong order is a loud fault;
- `RegOpenKeyExW` / `RegQueryValueExW` / `RegCloseKey` — values from a JSON
  fixture, never the host registry;
- `OSM_Printf` (modeled), `OSM_LogMsg` and `StatusData` (`planned`).

`stubs.py` holds the declarations (prototype, return rule, side effects,
`modeled`/`planned`); `dispatch.py` holds the implementations and keyed lookup
by `module!export` or `module!#ordinal` (for example `coredll!#719` =
`sprintf`, C-527). Each call is logged with its arguments and return value. An
export the table does not model, or a `planned` one, stops the run with exactly
`missing stub: NAME` — never a guessed return value.

Determinism: no wall clock, no host paths in results, no screen output.
Allocations are zeroed or poisoned and logged. Unknown calls stop the run.

### 4. Harness

`tools/l3_harness/runner.py` is the harness entry point. In target mode it:

1. resolves the input from `--input FILE` or the target's corpus entry under
   `--corpus DIR`;
2. maps the program (synthetic today; firmware blocks once the target kind
   exists), stack, data and heap on the chosen engine;
3. installs the stub dispatcher through `on_exec` hooks;
4. sets `PC`/`PR`/`r15`/argument registers and runs to the return sentinel;
5. reads back `r0`, output buffers and the stub log;
6. prints a JSON result with `status`, `verdict`, `accepted`, `returned`,
   `instructions`, `stub_calls`, output digests and `expect`.

The result is deterministic: no wall-clock value, no uninitialised guest
memory and no host path in the JSON. `--dry-run` prints the plan and
explicitly claims no verdict (`status: DRY_RUN`).

### 5. Test corpus

`tools/l3_harness/corpus.py` builds a **self-contained** corpus (no vendor
bytes) and its manifest; `tools/l3_harness/manifest.py` records the expected
verdict per file. Today: **108 entries** (EXP-2026-11-06-M9.7-corpus).

| Case family | Entries | Purpose |
| --- | --- | --- |
| `factory` | 1 (+ skipped vendor slot) | baseline; the real pair is used only when dropped into `factory/` |
| `noop_rebuild` | 1 | container identity |
| `recompressed` | 1 | zlib and size tolerance |
| `poi_rename` | 1 | same-length content change accepted |
| `corrupt_ind` | 8 | `ind_mutate.py` variants, rejection |
| `truncated_cmp` | 1 | rejection |
| `drstr_factory` / `drstr_size_mismatch` | 2 / 1 | tree parse and rejection |
| `tile_factory` / `tile_edited` | 1 / 1 | factory decode and one-vertex mutation |
| `hdd_info_factory` / `hdd_info_mismatch` | 67 / 23 | reference base + 89 variants (66 accept, 23 reject under model M0) |

Verdicts come from the committed Python readers (`cmpind.py`, `drstr.py`,
`hddinfo.py`, and the synthetic tile reader), never from the generator. The
manifest holds names, sizes and SHA-256 only, never data.

Normalise outputs before comparison: sizes, offsets, record counts and a
stable digest of parsed records. Do not compare raw pointers or heap addresses.

### 6. Acceptance criteria for "complete L3"

- All four readers (path/`CMP.LST`, `.cmp`/`.ind`, `DRSTR`, tile) run under the
  harness as firmware targets.
- The corpus produces the same accept/reject and the same normalised output as
  the Python tools.
- At least one generated `.cmp` and one generated tile are accepted by the
  firmware reader.
- The memory map, VAs, stubs and corpus are documented.
- `python3 tools/selftest.py` passes, and the L3 runner is independent of
  vendor data paths.
- Negative results are recorded: any function we cannot run is marked
  `BLOCKED` with the exact blocker, never `PASS`.

## Interface contract (implemented)

`tools/l3_harness/` is the executable contract between the firmware report,
the corpus and the engine. It needs no vendor data and no Ghidra for
`check`, `plan`, `targets`, the corpus build and every self-test.

```text
cerom.py memmap JSON ──rommap.py──> memory map JSON ──> ghidra_import.py
   (CE ROM TOC, real VAs)          (osm2leaf.l3.rommap/v1)   (Ghidra blocks)

corpus.py build ──> manifest JSON ──runner.py run──> result JSON
   (synthetic fixtures)  (path/sha256/size/verdict)   (status + verdict)

stubs.py ──> stub table + JSON Schema ──> dispatch.py ──> runner.py / engine.py
```

| Boundary | Produced by | Consumed by | Contract |
| --- | --- | --- | --- |
| ROM section table | `cerom.py memmap` | `rommap.py`, `ghidra_import.py` | `segments[].modules[].sections[]` with `name`, `va`, `file_offset`, `size`, `vsize`, `characteristics`, `compressed`, `rwx`; `o32_rom` aliases accepted |
| Memory map | `rommap.py convert` | `runner.py check/plan`, Ghidra loader | `osm2leaf.l3.rommap/v1`: `source`, `processor` (`verified: false`), `ram`, `blocks[]` with `address`/`size`/`file_offset`/`permissions`/`loadable`; sorted, non-overlapping |
| Corpus manifest | `corpus.py build` / `manifest.py build` | `runner.py`, harness | `osm2leaf.l3.manifest/v1`: `id`, `case`, `reader`, `path`, `sha256`, `size`, `expected` (`ACCEPT`/`REJECT`) |
| Stub table | `stubs.py` | `dispatch.py`, `runner.py plan`, harness | `osm2leaf.l3.stubs/v1`: signature, args, returns, binding, ordered side effects, `modeled`/`planned` |
| Targets | `targets.json` | `runner.py run` | `osm2leaf.l3.targets/v1`: `name`, `reader`, `what`, `entry`, `stubs`, `corpus`, `expect` |
| Run result | `runner.py run` | humans, `l3check.py` | JSON with `status`, `verdict`, `returned`, `stub_calls`, `expect`; a missing case is a mismatch, never a pass |

`rommap.py` never imports `cerom.py`; the JSON contract is the only coupling.
Compressed sections are rejected by `rommap.py` because no CE decompressor is
wired into the map, so a build containing them needs an explicit
`--skip-compressed` (smaller, incomplete map) or `ghidra_import.py`'s
zero-fill/omit handling.

### Component status

| Component | State | Notes |
| --- | --- | --- |
| `cerom.py memmap` + `rommap.py` | implemented | every section of the selected CE build at its real VA (one segment per run); compressed sections skipped explicitly; zero-size BSS converter limitation (C-1632) |
| `ghidra_import.py` | implemented, `--plan` only here | 13 self-test checks; real import exits `3` `MISSING_GHIDRA` |
| `stubs.py` + `dispatch.py` | implemented | 24 stubs (22 modeled, 2 planned); 14 dispatcher self-test checks |
| `engine.py` | implemented | PySh4 verified; Ghidra/QEMU adapters written, `verified: false`, absent here |
| `targets.json` + `runner.py run` | implemented for `synthetic`/`blocked` | one synthetic target PASS; **no firmware entry kind yet** |
| `corpus.py` + `manifest.py` | implemented | 108 entries, hashes verified |
| `tools/l3check.py` | implemented | 12 self-test checks; one row per target; card mode (`--card`) is M9.12 |
| Ghidra P-code script (`ghidra/l3_run.py`) | not written | next code step after a firmware target exists |
| Real vendor corpus | blocked | vendor data absent from this checkout; only synthetic files exercised |
| L3 verdict | **not claimed** | no reader has run under L3 |

## How to use L3 (target workflow)

> Everything in this section was executed on 2026-11-06 except the commands
> that need Ghidra or the vendor image; those print `MISSING_GHIDRA`/`BLOCKED`
> and are marked *(needs Ghidra)*. Exact console output is in
> `EXP-2026-11-06-M9.9-l3-docs`.

### Tool layout (real paths)

| Path | Job | State |
| --- | --- | --- |
| `tools/cerom.py memmap` | JSON of the CE build's sections at their VAs | implemented (M9.1) |
| `tools/l3_harness/rommap.py` | normalise/validate the memory map for the loader | implemented (M9.1) |
| `tools/l3_harness/ghidra_import.py` | headless Ghidra project: blocks at VAs, export names, thunk labels, SH-4 calling convention; `--plan` | implemented, real run needs Ghidra (M9.2) |
| `tools/l3_harness/stubs.py` | declarative WinCE stub table, keyed by `module!export`/ordinal | implemented, 24 entries (M9.3) |
| `tools/l3_harness/dispatch.py` | stub implementations: virtual FS, heap, critical sections, registry | implemented (M9.3) |
| `tools/l3_harness/engine.py` | one engine interface, three SH-4 back ends (PySh4, Ghidra, QEMU) | implemented (M9.4) |
| `tools/l3_harness/targets.json` | named targets: entry VA/kind, prototype, stubs, corpus, expected verdict | implemented (M9.5) |
| `tools/l3_harness/runner.py` | `check`, `plan`, `targets`, `run FUNC` | implemented (M9.5) |
| `tools/l3_harness/corpus.py` | build/check the 108-file synthetic corpus and manifest | implemented (M9.7) |
| `tools/l3_harness/manifest.py` | manifest build/refresh/validate/schema | implemented (M9.7) |
| `tools/l3check.py` | L3 rung of the verification ladder: one status per target; `--corpus`, `--build-corpus`, `--target`, `--engine`, `--json` | implemented (M9.8); `--root`/`--image` recorded only, card mode is M9.12 |
| `tools/l3_harness/ghidra/l3_run.py` | Ghidra P-code harness script | **not written** |

There is **no `tools/l3/` directory**; the harness lives in
`tools/l3_harness/`. The package README documents each module:
[`tools/l3_harness/README.md`](../../tools/l3_harness/README.md).

### One-time setup *(needs the vendor image; Ghidra only for the import)*

```bash
# image slice: the firmware lives in the first ~110 MB; never commit the image
curl -r 0-109999999 -o fw.img \
  https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img

# 1. section table for one CE build (auto-detected; force with the global
#    option before the subcommand: cerom.py fw.img --image-start 0x200200 memmap)
python3 tools/cerom.py fw.img memmap --out work/memmap.json --pretty

# 2. normalise it for runner.py check/plan
python3 tools/l3_harness/rommap.py convert \
  --report work/memmap.json --segment 0 --skip-compressed --out work/rommap.json
python3 tools/l3_harness/rommap.py validate work/rommap.json

# 3. inspect the Ghidra import without Ghidra (nothing is written)
python3 tools/l3_harness/ghidra_import.py fw.img work/memmap.json \
  --plan --skip-compressed --json

# 4. real import: one program per build, two analyzeHeadless phases (needs Ghidra)
export GHIDRA_INSTALL_DIR=/opt/ghidra_12.2_PUBLIC
python3 tools/l3_harness/ghidra_import.py fw.img work/memmap.json \
  --skip-compressed --exports OBJDLL.dll=objdll.txt \
  --thunks work/thunks.json \
  --project /tmp/opencode/l3-ghidra --report work/ghidra-import.json
```

`analyzeHeadless` is looked up via `--headless`, `$GHIDRA_INSTALL_DIR`,
`$GHIDRA_HOME`, `$PATH`, then `ghidra*` under `/opt`, `/usr/local`,
`/usr/share` and `$HOME`; a failed lookup lists every candidate. Without it,
step 3 still works and step 4 exits `3` with `MISSING_GHIDRA`.

### Corpus and manifest (no vendor data)

```bash
# build the 108-entry synthetic corpus and its manifest.json
python3 tools/l3_harness/corpus.py build /tmp/opencode/l3/corpus --json
python3 tools/l3_harness/corpus.py check /tmp/opencode/l3/corpus

# validate the manifest, including size/SHA-256 against the staging tree
python3 tools/l3_harness/manifest.py validate \
  /tmp/opencode/l3/corpus/manifest.json --root /tmp/opencode/l3/corpus

# add a staging tree of your own (one --case per file; repeatable)
python3 tools/l3_harness/manifest.py build \
  --root /tmp/opencode/l3/corpus --out /tmp/opencode/l3/manifest.json \
  --case factory:cmp_ind:cmp/factory/ADDRE001.DAT.cmp \
  --case corrupt_ind:cmp_ind:cmp/corrupt-ind/count_m1/ADDRE001.DAT.cmp
```

`corpus.py build` writes `manifest.json` inside the corpus root, so
`runner.py --corpus DIR` finds it. `manifest.py build` is for an arbitrary
staging tree; `refresh` re-hashes an existing manifest. `manifest.py schema`
and `stubs.py schema` print the JSON Schemas.

### Validate, list, plan

```bash
python3 tools/l3_harness/runner.py check \
  --manifest /tmp/opencode/l3/corpus/manifest.json \
  --rommap work/rommap.json --root /tmp/opencode/l3/corpus

python3 tools/l3_harness/runner.py plan \
  --manifest /tmp/opencode/l3/corpus/manifest.json --rommap work/rommap.json

python3 tools/l3_harness/runner.py targets          # the target table
python3 tools/l3_harness/runner.py selftest         # 19 checks, no Ghidra
```

### Run one target

```bash
# synthetic pipeline target: PASS on the reference engine
python3 tools/l3_harness/runner.py run probe-zlib-cmf \
  --corpus /tmp/opencode/l3/corpus --engine pysh4 --json

# one explicit file instead of the corpus entry
python3 tools/l3_harness/runner.py run probe-zlib-cmf \
  --input /tmp/opencode/l3/corpus/cmp/factory/ADDRE001.DAT.cmp --json

# a reader that is not located: BLOCKED, exit 4, no verdict
python3 tools/l3_harness/runner.py run cmp_ind_reader --json

# print a real engine's plan without starting it; claims nothing
python3 tools/l3_harness/runner.py run probe-zlib-cmf \
  --input FILE --engine ghidra --dry-run --json

# legacy whole-manifest run through Ghidra's analyzeHeadless (needs Ghidra)
python3 tools/l3_harness/runner.py run \
  --manifest M.json --rommap R.json --image fw.img --json
```

A target-mode result looks like (abridged from the executed run):

```json
{"target": "probe-zlib-cmf", "engine": "pysh4", "status": "PASS",
 "verdict": "ACCEPT", "accepted": true, "returned": "0x00000001",
 "instructions": 68, "finished": "return",
 "stub_calls": [{"stub": "coredll!sprintf", "args": ["0x8c200300", "…"]},
                {"stub": "coredll!CreateFileW", "returned": "0x00000010"},
                {"stub": "coredll!ReadFile", "returned": "0x00000001"}],
 "expect": {"verdict": "ACCEPT", "python_verdict": "ACCEPT"},
 "l3_claim": true}
```

### The ladder: `l3check.py`

```bash
# build a throwaway corpus and run every declared target on pysh4
python3 tools/l3check.py --build-corpus

# run a corpus built earlier; one row per target, blocked targets cost nothing
python3 tools/l3check.py --corpus /tmp/opencode/l3/corpus --json

# only one target, or another engine
python3 tools/l3check.py --corpus /tmp/opencode/l3/corpus --target probe-zlib-cmf
python3 tools/l3check.py --corpus /tmp/opencode/l3/corpus --engine ghidra

python3 tools/l3check.py --selftest          # 12 checks, no Ghidra
```

Output on the synthetic corpus (executed):

```text
target              reader     entry      claims         RESULT
probe-zlib-cmf      synthetic  synthetic  C-1670,C-1690  PASS
hddinfo_compare     hdd_info   blocked    C-521          BLOCKED
cmp_ind_reader      cmp_ind    blocked    -              BLOCKED
tile_reader         tile        blocked    -              BLOCKED
drstr_parser        drstr      blocked    -              BLOCKED
mapcode_comparator  hdd_info   blocked    C-520,C-528    BLOCKED
counts   pass=1 fail=0 skip=0 blocked=5 runnable=1/6
RESULT: PASS (every runnable target passed; 5 blocked, 0 skipped)
```

Exit `0` when every **runnable** target passed, `1` on a FAIL or invalid
input, `2` usage, `3` when nothing was runnable (`NO_RUNNABLE`). A synthetic
PASS proves the pipeline, not the firmware. See
`EXP-2026-11-06-M9.8-l3check` for the tool's own record. `--root` and `--image` are
accepted and recorded but are **not evidence** until M9.12 adds `--card`; the
tool says so in its report.

### Engine back ends

```bash
python3 tools/l3_harness/engine.py --probe            # readiness of all three
python3 tools/l3_harness/engine.py --selftest         # 13 checks, absent back ends SKIP
python3 tools/l3_harness/engine.py --demo --engine pysh4 [--json]
```

| `--engine` | What it is | `verified` | Absent/misconfigured |
| --- | --- | --- | --- |
| `pysh4` | pure-Python SH-4 interpreter; the **reference**, implements the subset a function probe needs and raises `IllegalInstruction` on anything else | `true` | never absent |
| `ghidra` | lazy `pyghidra`/`EmulatorHelper` adapter; needs Ghidra 12.2+ and a JDK | `false` | `SKIP`, exit `3`, `MISSING_GHIDRA` |
| `qemu` | `qemu-system-sh4 -M none -cpu sh7785` plus gdbstub | `false` | `SKIP`, exit `3`, `MISSING_QEMU` |

Pick **Ghidra** to understand a function (single-step, inspect P-code and
structs; slow), **QEMU** to run corpora and whole call chains (native speed;
the breakpoint fast path is still M9.5 work), and **PySh4** as the reference
that needs nothing installed. Disagreement between back ends on the same
target is a bug in a stub or an engine; record it, do not average it.
`pysh4`/`ghidra`/`qemu` all enforce the same overlap, unmapped-access and
read/write-permission rules.

### Adding a stub

Stubs are Python functions registered under `module!export` (or
`module!#ordinal`) in `dispatch.py` and declared in `stubs.py`. Each one logs
its arguments and result. File stubs work on a virtual FS rooted at the card
tree under test (`\Storage Card\…` → `--root`/corpus root). Keep stubs
deterministic: fixed tick count, fixed time, no host paths in results. An
unknown export must stop the run with `missing stub: NAME`; run
`python3 tools/l3_harness/dispatch.py --selftest` (14 checks) after a change.

## Status vocabulary

Two different things are called a "verdict"; keep them apart.

1. **Reader verdict** — `ACCEPT` / `REJECT`, what the Python reader and later
   the firmware reader say about one file.
2. **Harness status** — whether the run was allowed to decide, and whether it
   agreed with `expect`.

| Status | Emitted by | Meaning | Exit |
| --- | --- | --- | --- |
| `PASS` | `runner.py run`, `check`, `plan`, `l3check.py`, self-tests | for `run`: the expected reader verdict and every precondition (stubs called, return reached); for `check`/`plan`/self-tests: the inputs validated or the checks passed. **Only a real engine run can prove a reader** | `0` |
| `FAIL` | `check`/`plan`/`rommap`/`manifest`/`corpus` validation, `l3check.py` | an input is invalid, a corpus entry disagrees, or a runnable target failed; this is **not** a firmware reject (a reader reject is `verdict: REJECT` and can still be `PASS`) | `1` |
| `INVALID` | `runner.py run` | bad/unknown target input, unknown engine, unreadable file | `1` |
| `SKIP` | target mode | the chosen back end is absent (`MISSING_GHIDRA`, `MISSING_QEMU`); `l3_claim: false`, never a pass | `3` |
| `MISSING_GHIDRA` | legacy `run` | no `analyzeHeadless` found; prints the install candidates | `3` |
| `BLOCKED` | target mode / legacy `run` | the reader entry point is not located, the harness script/firmware image is missing, or a stub/engine error stopped the run; `l3_claim: false` | `4` |
| `MISMATCH` | target mode / result comparison | an engine ran and produced a verdict that differs from `expect`, or a manifest case is missing from the result | `5` |
| `DRY_RUN` | `--dry-run` | the plan was printed and nothing ran; explicitly claims no verdict | `0` |
| `NO_RUNNABLE` | `l3check.py` | every target was `BLOCKED` or `SKIP`; the report says nothing was claimed | `3` |

`UNVERIFIABLE` is **not an L3 status** today. In this repo it belongs to
`tools/zlibinfo.py` and `tools/lev3456.py` (exit `3`): the compressor build
cannot reproduce the reference bytes, so a byte-identity result is decided
neither way. The L3 analogue is `SKIP` (no engine here) or `BLOCKED` (no
located reader/script) — also exit `3`/`4` and also never `PASS`. Do not
launder a zlib-build ambiguity into an L3 pass: re-run on stock zlib or record
the case as undecided.

## Current targets (`tools/l3_harness/targets.json`)

`python3 tools/l3_harness/runner.py targets` prints this table; the names below
are exactly the `name` fields.

| Target | Reader | Entry kind | Expect | State today |
| --- | --- | --- | --- | --- |
| `probe-zlib-cmf` | synthetic (`cmp_ind` input) | `synthetic`, `probe_zlib_cmf_v1` at `0x8c100000` | `ACCEPT` | **PASS on `pysh4`** (68 steps, 5 stubs). A pipeline fixture: ACCEPT iff the served first byte is the zlib CMF `0x78`, **not** a reader verdict |
| `hddinfo_compare` | `hdd_info` | `blocked` | `ACCEPT` | **blocked** (M9.6): parser behind a runtime COM object; `HDD_INFO_read` is located at `Navi.exe` `0x004e7b8c` (M2.1) and the comparator at AppLaunch B `0x03bd2ad8` (M2.5), but no target entry exists |
| `cmp_ind_reader` | `cmp_ind` | `blocked` | `ACCEPT` | **blocked** (M9.11): only the `.ind` wrapper `0x00377870`/`0x00377ae0` is located (M3.1); the chunk reader is open (M3.2b) |
| `tile_reader` | `tile` | `blocked` | `ACCEPT` | **blocked** (M9.13): reader VAs `0x0041f26c`/`0x004259bc`/`0x0042757a` are located (M3.5) but the target entry still says "no entry point recovered" |
| `drstr_parser` | `drstr` | `blocked` | `ACCEPT` | **blocked** (M9.14): parser `0x00419684` → `sub_00419350` is located (M3.4/M3.10) but the target entry still says "no entry point recovered" |
| `mapcode_comparator` | `hdd_info` | `blocked` | `REJECT` | **blocked on purpose**: the `0x6fab2c`/`0x6faeb0`/`0x6fb05c` chain is `BT_MGR.dll` code (C-520, C-528); kept so it cannot be revived as a reader |

The `hddinfo_compare`, `tile_reader` and `drstr_parser` rows show the current
gap: **located statically is not "runnable as an L3 target"**. `targets.json`
has only two entry kinds (`synthetic` and `blocked`) and `runner.py`
validates/maps only those, so a reader with a known VA still reports
`BLOCKED`. Adding a firmware entry kind is the next runner step (M9.5
extension, first used by M9.6).

### Readers located vs still blocked

Static VAs are from the CE ROM TOC (`cerom.py`); the claims are in
`docs/research/claims.md` and the EXPs named.

| Reader | Located | Evidence | L3 target |
| --- | --- | --- | --- |
| `HDD_INFO.TXT` read | `Navi.exe` `0x004e7b8c` (`HDD_INFO_read`) | EXP-2026-11-06-M2.1 | `hddinfo_compare`, blocked |
| map-code compare | AppLaunch B `0x03bd2ad8`, router `0x03bd2ecc`, dispatcher `0x03bcafb8` | EXP-2026-11-06-M2.5 | `hddinfo_compare`, blocked |
| `CMP.LST` opener | `Navi.exe` `0x0041ba90` — `fopen`/`fclose` only, an existence check | EXP-2026-11-06-M3.10 | none |
| `.ind` wrapper above `MAL_DataVol_getOffset` | `0x00377870` (vols 3/4/7/8), `0x00377ae0` (vol 7 `memcpy`) | EXP-2026-11-06-M3.1 | `cmp_ind_reader`, blocked |
| `.cmp` chunk/zlib reader | **not located** | M3.2b open | `cmp_ind_reader`, blocked |
| `DRSTR001.DAT` parser | `Navi.exe` `0x00419684` → `sub_00419350`, bounds helper `sub_004191d0` | EXP-2026-11-06-M3.4/-M3.10 | `drstr_parser`, blocked |
| tile reader / level table | `Navi.exe` `0x0041f26c`, `0x004259bc`, `0x0042757a` | EXP-2026-11-06-M3.5 | `tile_reader`, blocked |
| `POINT` record reader | **not located** | M3.11 open | M9.10 |
| `ADDRE`, `ZCODE`/`ICODE`/`COORD`, `LCTBL`, `INTER`/`FRWAY` | **not located** | M3.13–M3.16 open | M9.15 |

A located VA is enough to *plan* a target, not to claim one. The positive
control (factory input, AGENTS.md rule 2) is mandatory before any corpus run.

## Adding an M3 reader as an L3 target

This is the exact sequence; steps 1–3 need no Ghidra, step 4 needs the runner
extension, step 5 needs the firmware image.

1. **Locate the entry and record it.** From `cerom.py`, never a fitted delta:
   ```bash
   python3 tools/cerom.py fw.img sections Navi.exe
   python3 tools/cerom.py fw.img va2file 0x00419684
   ```
   Add a claim (the task's reserved IDs) and an EXP with the VA, module,
   section, prototype (`r4`–`r7`, stack args), I/O calls and callers. A file
   offset alone is not an entry.

2. **Give the corpus an entry with a verdict from the Python reader.**
   Add fixtures/verdicts to `corpus.py` (or a new family), rebuild:
   ```bash
   python3 tools/l3_harness/corpus.py build /tmp/opencode/l3/corpus --json
   python3 tools/l3_harness/manifest.py validate \
     /tmp/opencode/l3/corpus/manifest.json --root /tmp/opencode/l3/corpus
   ```
   The firmware target's `corpus.case`/`reader` and `expect.verdict` must match
   that manifest entry; `runner.py` validates this.

3. **Make the stubs complete.** `python3 tools/l3_harness/runner.py plan`
   lists `READER_STUBS` gaps. Add any missing export to `stubs.py` +
   `dispatch.py`; an unknown call must stop with `missing stub: NAME`. Run
   `python3 tools/l3_harness/dispatch.py --selftest` (14 checks).

4. **Add the target entry — and the firmware entry kind.** In
   `targets.json`, add a target with `name`, `reader`, `what`, `module`, an
   `entry` carrying the VA and prototype/argument setup, the stub list, the
   corpus entry and `expect`. **Today only `entry.kind` `synthetic` and
   `blocked` are accepted** (`runner.py` validator and `SYNTHETIC_PROGRAMS`);
   a real reader needs a `firmware` (or equivalent) kind that maps the image
   blocks at their VAs, sets `PC`/`PR`/`r15`/arguments and reads the outputs.
   That runner extension is the missing piece shared by M9.6 and every reader
   target. Until it lands, keep the entry `blocked` with the real VA and the
   reason, and say so in the EXP.

5. **Positive control first, then the corpus.** Run the factory input alone
   on `pysh4` (if the reader's instruction subset is modelled), then `ghidra`
   and/or `qemu`:
   ```bash
   python3 tools/l3_harness/runner.py run NEW_TARGET --input FACTORY_FILE --json
   python3 tools/l3_harness/runner.py run NEW_TARGET --corpus /tmp/opencode/l3/corpus --json
   ```
   A missing engine is `SKIP`; a verdict different from `expect` is
   `MISMATCH`; neither is a pass. Run a second engine when it is available; a
   disagreement is a recorded finding, not something to average.

6. **Record the EXP and update this file.** Include the image SHA-256, the
   memmap/rommap hashes, the stub log, instruction count and every verdict.
   Update the target table and the reader matrix above in the same commit. Do
   not claim L3 until the run is reproducible from the repo plus the named
   image.

7. **Feed the ladder.** `l3check.py` discovers targets from `targets.json`,
   so a new target appears there automatically; run
   `python3 tools/l3check.py --corpus DIR` and add the row to the EXP. Card
   mode (`--card`, M9.12) and the `tools/verify.py` L3 rung are still open.

## Risks

- Pre-bound WinCE ROM calls may be direct, so "intercept the import" is not
  enough; breakpoints on stub addresses or patched call sites are needed.
- MMU/cache behaviour, self-modifying code and indirect calls may not be
  modelled by P-code.
- Some readers may depend on global state initialised during boot (registry,
  locale, buffers, the runtime COM objects of `NaviStateCC`); the harness must
  stub or initialise it.
- The PySh4 reference implements only a subset of SH-4; a reader with an
  unmodelled instruction stops loudly and needs Ghidra/QEMU.
- A function that passes the corpus is evidence, not proof that the unit
  accepts the whole card.

## Fallbacks

- QEMU `-M none -cpu sh7785` + gdbstub is now an engine back end, not just a
  fallback; `qemu-system-sh4` needs `apt install qemu-system-misc`.
- A custom SH-4 harness if P-code emulation hits an unsupported instruction.
- Full-system emulation (L5) only as a timeboxed spike; see
  [`full-system-emulation.md`](full-system-emulation.md) and TODO M8. A
  running kernel can also produce initialised process images for L3 (M8.E3).

## First steps (history and remaining work)

- [x] Skeleton: manifest, stub table, ROM report -> memory map, `check`/`plan`
      runner and a synthetic self-test (`EXP-2026-11-05-38`).
- [x] Module map on the real image (`cerom.py memmap`, `rommap.py`,
      EXP-2026-11-06-M9.1); Ghidra project builder with a validated `--plan`
      (M9.2, C-1640); stubs bound to real exports/ordinals (M9.3); engine
      interface with three back ends (M9.4); `runner.py run` end to end on the
      synthetic target (M9.5); 108-entry corpus (M9.7).
- [x] Trace the readers from the CE ROM TOC: `CMP.LST` `0x0041ba90`, DRSTR
      `0x00419684`, tile `0x0041f26c`/`0x004259bc`/`0x0042757a`, `.ind`
      `0x00377870`/`0x00377ae0` (M3.1/M3.4/M3.5/M3.10).
- [ ] Extend `runner.py`/`targets.json` with a firmware entry kind (the gap in
      step 4 above).
- [ ] First real target: the map-code compare, M9.6.
- [ ] `.cmp` chunk reader (M3.2b) and the `cmp_ind_reader` target (M9.11).
- [ ] Write `tools/l3_harness/ghidra/l3_run.py` and run one function under
      Ghidra P-code.
- [x] `tools/l3check.py` (M9.8): one status per target on a corpus.
- [ ] `--card` / `--factory` (M9.12) and the `tools/verify.py` L3 rung.
- [ ] Record every run as an `EXP-...` with the exact memory map and stubs.

## What L3 cannot tell you

Acceptance by the unit (SD lock, map code in context, rendering, routing,
CAN). Those need the full system (M8, F4+) or the bench (M6).
