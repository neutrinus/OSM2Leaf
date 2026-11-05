# Firmware and pre-partition area

> **Evidence status:** byte offsets, strings and the SH-4 code recovery are
> `VERIFIED` on the EU 2011 image, and so is the CE ROM header / section-to-VA
> mapping (EXP-2026-11-05-32); `SUM4` and the role of the duplicated builds
> are `OBSERVED`/`HYPOTHESIS`. Sections below written before EXP-32 that rely
> on delta fitting are historical; check them with `tools/cerom.py`.

The ~100 MB before the FAT partition contains the navigation firmware. It is
**not** a plain PE image and it is **not** a compressed container: it is an
uncompressed Clarion update wrapper around a Windows CE 5 / SuperH-4 ROM
image.

## Clarion identification records

At `0x000001c0` and `0x000003c0` there are 512-byte records ending in
`0x55 0xaa`, with MBR-like partition entries. ASCII `CLARION ID` sits at
`0x00000200`.

## Firmware container at `0x00200000`

```
0x00200000  u32 0x01752c88        payload length (24,456,328 bytes)
0x00200014  "\x82FX210ECNI.158"   Clarion version string
0x0020002c  "SUM4" + u32 0xcdf87db0
0x00200034  "470-2824-34"         Clarion part number
0x002001fc  "NKOK"
0x00200200  15 x u32 table
0x00200240  "ECEC" (43 45 43 45)
0x00200248  u32 0x01751978
```

`SUM4` is a tagged checksum field. CRC-32, Adler-32 and plain word sums were
computed and rejected; the algorithm is **UNKNOWN**. `ECEC` is a fixed field
present in all payloads.

### CE ROM header (VERIFIED, EXP-2026-11-05-32)

`ECEC` is the Windows CE ROM signature at CE image start + `0x40`. The CE
image starts at file `0x200200` (after the `0x200`-byte Clarion header):

```
0x00200240  "ECEC"  pTOC = 0x8e232978  ROMHDR offset = 0x01751978
image VA base = 0x8cae1000  ->  file = VA - 0x8cae1000 + 0x200200
0x01951b78  ROMHDR: physfirst 0x8cae1000, physlast 0x8e233c88,
            nummods 149, numfiles 1, usCPUType 0x01a6 (SH-4)
0x01951bcc  TOCentry[149] (32 B), then FILESentry[1] (ReleaseMain.skn)
```

Every module's `e32_rom`/`o32_rom` gives exact section VA (`o32_realaddr`)
and file location (`o32_dataptr`); 245 of 527 sections are compressed RW data.
Use `tools/cerom.py`. The kernel (`nk.exe`, `coredll.dll`) is not in this
region. **Many conclusions below that were reached by delta fitting are
superseded** (C-516…C-523); in particular the `0x6fab2c`/`0x6faeb0`/`0x6fb05c`
chain is in `BT_MGR.dll`, and the real `HDD_INFO`/`SD Import` literals are in
`Navi.exe` at VA `0x004e7d28` and `0x004e8584`/`0x004e995c`.

## Payloads and builds

Five payloads, three distinct builds:

| Build | Part number | Offsets |
| --- | --- | --- |
| A | `470-2824-34` | `0x200000` and `0x2000000` (byte-identical over 24.5 MB) |
| B | `470-2759-01` | `0x3e00000` and `0x4800000` |
| C | `470-3142-00` | `0x5200000` |

A/B/C use slightly different header layouts (B/C put the ID at `+0x220` and
the part number at `+0x250`). The selection logic is **UNKNOWN**.

## The payload is uncompressed SH-4 code

- Entropy ≈ 6.03 bit/B with ~27 % zero bytes.
- Capstone decodes clean SH-4 (`jsr @r3`, `rts`, `lds.l @r15+,pr`) from
  `0xd108` onward.
- Strings include `VS_VERSION_INFO`, `.rgs` COM scripts, `MSFT` CodeView,
  `TFAT.dll`, `FSDMGR_*`, `CORDLL`, `nk.exe`, `filesys.exe`, `gwes.exe`,
  `device.exe`, `coredll.dll`.
- UTF-16LE module names sit around `0x2023b0`; a `RSDS`/PDB path with
  `CETUS_SH4` appears around `0x205c4a`.

There are **no PE files**. A byte-by-byte scan of all 104,858,624
pre-partition bytes found 255 `MZ`, 188 `PE\0\0`, and **0** valid
`MZ`+`e_lfanew`+`PE\0\0`; also 0 `B000FF` strings. Modules are in
WinCE ROM/XIP form; the `ROMHDR`/TOC is a binary struct (see above).

## Recovered code and map path

- **Retraction:** `0xc438a4` is a **memory/fd statistics formatter**, not the
  `CMP.LST` opener. Its pool `0xc439d0 = 0x02df9450` → file `0xdf9450` =
  `"ize  :%d\r\n"`. The real `"\CMP.LST"` is at `0xdf945d` and has **zero**
  pointer references in build A.
- For the map module's `.rdata`, `VA = file_offset + 0x02000000` (21 pointer
  literals). This is a **data** mapping only.
- **Code delta is not `+0x02200000`.** A per-instruction `{VA, flag}` table at
  `0x12fa000–0x132d200` lists all nine known function entries in the
  **`0x02b0xxxx–0x02b5xxxx`** band; best fit is `VA = file + 0x01f07d5c`
  (band certain, exact value has a small even alias).
- **Never apply the data delta to a `jsr` target:** it collides with shared
  `.rdata` and produces string fragments.
- The map module `.text` is file `0xc00000–0xc4b000`; its string pool
  `0xdf6000–0xdfb000` documents `MESH_ID`/`DIVID`, `.cmp`/`.ind`, `HCXCmp`
  descriptors and map filenames.

### The VA map is not injective

A VA does **not** identify a file offset:

- `VA 0x0367b180` is both a `jsr` target in the builder (`0x6faf7e`) and the
  UTF-16 string `" Debug Common Version 0.1 …"` at file `0xe7b180` under data
  delta `0x02800000` (one occurrence in the image);
- `0x0369d400` and `0x036922cc` map onto `0x7c`-pipe string data.

The `0x0360–0x036a` band is a library layer: 1,899 code-target VAs, no export
directory, no `MSFT`, no `.rgs`; the best delta for its 13 helper VAs reaches
only 7/13 prologues (need ≥11/13). Cross-module calls therefore **cannot** be
resolved by literal arithmetic. They need the `romimage` **XIP section table**
(`file ↔ VA ↔ size`).

### Section table is a dead end

The 24-byte records at `0x374000`/`0x3e0060` are `o32_rom`-shaped (a clean
record at `0x3221b0` has `psize == round_up(vsize, 0x200)`), but the table is
**not usable as a file map**: its `dataptr` fields point into pure `0xff`
fill (stale build-time offsets), and consecutive records do not share a
`realaddr − rva` delta. Do not build on it.

### New anchors: OBJDLL, STDDLL and zlib copies

- **`OBJDLL.dll`**: file base `0x7dd200`, export dir `0x82816c`, **1294
  named exports**. Map Access Layer API: `MAL_DataVol_getSize` (`0x7f5f28`),
  `MAL_DataVol_getOffset` (`0x7f5f48`), `MAL_DataVol_getAreaRect`
  (`0x7f5f68`), `OBJ_DiscInfo_readDiscVol` (`0x7f65d8`),
  `writeDiscVol` (`0x7f710c`), `readPublicLv` (`0x7f66f8`).
- **`STDDLL.dll`**: file base `0x834200`, **310 exports**.
- **Six zlib copies** (1.1.3/1.1.4, lbase/dbase, `z_errmsg`):
  `0x5e5f98`, `0x8b5f10`, `0xa34f48`, `0xe88f78`, `0x15c7e88`, `0x1619848`.

The 10-slot table at `0xa9cf8c` resolves under data delta `0x02200000`; that is
a data mapping, not a code delta.

### `0x2e0xxxx` is an import-thunk area

A corrected export scan (export directory is **9 dwords**, timestamp first)
finds **135 export modules**, but **no module's RVA range covers
`0x2e00f98–0x2e533e4`**. The band is the navi modules' import-thunk area:

- 86-entry table at `0x1724eb8–0x17252c0`;
- 12-byte thunks `mov.l @(disp,PC),r0; mov.l @r0,r0; jmp @r0; nop;
  .long iat_slot`, best delta `0x16e248c`;
- IAT slots are RAM `0x1ab9000–0x1ab9440`; the loader writes the pointers;
- import names at `0x1708000–0x170a200` (`COREDLL.dll`, `BT_DB`, `WS2`,
  `OBJDLL`, `STDDLL`, `ICLDLL`, `DCM_API`, `Cws_Apl`, `TelemaDLCCLib`).

The underlying non-exporting shared library is at file
≈`0x171c000–0x1724eb8`, VA ≈`0x2e00000`; its name is unknown.

### No import descriptor; NaviStateCC is COM

A standard 20-byte import descriptor with `FirstThunk = 0x1ab9000` is
**absent**: 219 descriptor-shaped records, none matching. `0x1ab9000` occurs
only as an IAT slot/pool/EH value. The navi IAT is **pre-bound**; the 86 thunks
remain unnamed (140 ordinal-ILT runs exist, none matching the navi IAT).

`NaviStateCC.DLL` (file base `0xc32200`) is a **COM DLL** with only four
exports: `DllCanUnloadNow`, `DllGetClassObject`, `DllRegisterServer`,
`DllUnregisterServer`.

`DllGetClassObject` (`0xc434cc`) loads `0x2e00eb8` and jumps; the real entry is
the prologue at **file `0x171e9e8`** (not `0x171ea2c`). Its pool holds
link-time VAs `0x0260xxxx`, while the called thunk table is runtime-placed in
`0x02e0xxxx` (different section delta `0x16e64d0`). The `0x2e0xxxx` band is
therefore **not purely thunks**.

`0x1d0f8a8` is a **RAM global context** used 23× in NaviStateCC; no store
exists in that module, so the framework/loader initializes it.

The constructed vtable at `0x170f100–0x170f2b0` is **iPodCC's, not
NaviStateCC's**: `iPodCC.DLL` file base `0x1709200`, link-time space
`0x0260xxxx` (symbols `CiPodIPC`, `SetTrackTotalNum`, `ReadListCategory`, …).
`0x2e00eb8` is therefore a **shared COM runtime helper**, not NaviStateCC's
class factory; the round-4 COM branch led to the wrong module.

Slot tables: constructor A 18 slots, constructor B 14 slots. 158/175 method
VAs map under some delta (`0x11a3xxxx`/`0x1182xxxx` → file
`0x145xxxx–0x14axxxx`), but the assignment is non-unique (low confidence).
The vtable contains **no** MAL/fd/zlib/DRSTR/tile methods.

There is **no NaviStateCC vtable** as a contiguous pointer table under
`0x1f07d5c`: a ≥8-pointer prologue-target run scan found 0. The fd/IOB layer
functions are COM methods reached through a runtime-materialized vtable; no
static `bsr`/vtable reference reaches them. Structural scan: `0xc42e48` debug
dumper, `0xc49f98` virtual dispatcher, `0xc438a4` stats formatter. There is
**no `0x10000` pool literal or `mov #1; shll16`** near the fd layer, so the
`.ind` reader likely uses `chunk_size` as a buffer size rather than a
comparison.

**Initializer found at `0xc43430`** (NaviStateCC). It writes `0x1d0f720`,
`0x1d0f898=obj`, type tag `0x84`, `+88=0x300`, and the 16-byte class ID to
`0x1d0f888…894`. But:

- `0x1d0f8a8` itself is **never written by the ROM**; the only direct store is
  destructor `0xc4ac6a` zeroing `+96/+100/+104`;
- `0xc43430` has **no static caller** (only a per-instruction table entry at
  `0x1302760`); invocation is dynamic;
- the `0x1952b00` RAM copy list does not cover this block;
- **no static vtable** contains the fd methods: `0x2b4a27c`/`0x2b4a400`/
  `0x2b4b600` occur once in the per-instruction table, never in a ≥8-pointer
  run.

The object vtable is built at runtime by the shared COM helper `0x171e9e8` /
loader. Reader address and slot layout are not in the ROM.

### Static is closed

`0x171e9e8` is a **COM type-library registration/lookup routine**, not a
class factory/vtable builder: GUIDs `44ec053b-400f-11d0-9dcd-00a0c90391d3` /
`44ec053a-400f-11d0-9dcd-00a0c90391d3`, strings `LoadTypeLib`,
`RegisterTypeLib`, `UnRegisterTypeLib`, `REGISTRY`, `Module`,
`oleaut32.dll`, `.tlb`; callees are `oleaut32`/`ole32` thunks and the
indirect calls are `ITypeLib`/`ITypeInfo` methods.

There is no slot table, no constructor table and no memcpy from a ROM template.
No static vtable contains `0xc42520`/`0xc426a4`/`0xc438a4`; each fd VA occurs
once in the per-instruction table. `0x1d0f8a8` is RAM BSS, never written by the
ROM; COM resolution goes through the registry.

**Static is closed for the vtable and the reader.** The exact dynamic capture
plan is in [`../research/dynamic-break-guide.md`](../research/dynamic-break-guide.md).

**Negative lead:** `0x6faf30` is not the reader — it is a `jsr @r3` in the
Bluetooth/OPP handler at `0x6faeb0` (`OppAccess::msg_opp_comp_ind` at
`0x6c7e98`).

### MAL volume chain and NaviStateCC

```
OBJ_DiscInfo_readDiscVol (0x7f65d8, VA 0x034993d8)
  -> MAL_DataVol_getOffset (0x7f5f48, VA 0x03498d48)
  -> MAL_DataVol_getSize   (0x7f5f28, VA 0x03498d28)
  -> read at base + offset*2, length size*2
```

OBJDLL VA base `0x03480000` is proven by three literal sites. Only three sites
call `MAL_DataVol_getOffset/getSize`, all in OBJDLL (`0x7f6694`, `0x7f6aa4`,
`0x7f6b84`); the map module uses a higher-level wrapper still missing.

The fd/IOB layer is in `NaviStateCC.DLL`, file base `0xc32200` (`0xc42520`,
`0xc426a4`, `0xc438a4`), table-dispatched.

### Reader-related functions found

| Address | Role |
| --- | --- |
| `0xc438a4` | memory/fd statistics formatter (not CMP.LST) |
| `0xc42520` | IOB/fd dump; type tag **`+0xC0`** (7–15), fields `+0xAC…+0xC4` |
| `0xc426a4` | directory/disc dump; type tag **`+0xB4`** (2, 18/19), second field `+0xBC` |
| `0xc48380` | writes message-catalogue strings (`MAP_DATA READ`, `DBgetLnk`, …), **not** a DB vtable |
| `0xc0e998` | true entry of the function containing `0xc0ebf8`; `0x1ac` is an argument to `0x2e533e4`, also called with negative values |

**Retraction:** `obj+0x78…+0x9c` is a **message catalogue**, not a vtable; every
stored value is a string pointer. The four functions `0xc412ca`/`0xc42a7a`/
`0xc42ba6`/`0xc42e30` are read-only classifiers, not fd writers. The struct is
a state descriptor keyed by `(0xAC,0xB4,0xB8)`; `+0xC4` is not the type tag.
Image-wide, 28 dispatches through `+0x78…+0x9c` exist, but zero in the map
module; the map module dispatches through `+0x04/+0x08/+0x18`.

### New anchor: `Lib.out32.dll`

File `0x877740` holds UTF-16 `Lib.out32.dll` and a string-pointer table with
data delta `0x01e00000`. Four entries land on a zlib copy's `z_errmsg` strings
(`need dictionary`, `file error`, `stream error`, `buffer error`). The module's
**code delta is not pinnable**: its pool is only data-referenced, and prologue
scoring over 473 targets is flat (a Lib module imports from many modules). The
module identity is weakened, not refuted.

### Section placement is the root blocker

ROM sections use independent `(file offset, VA)` pairs, and the shared
`.rdata` is mapped under at least three deltas (`0x01e00000`, `0x02000000`,
`0x02200000`). Isolated literal→string hits are therefore meaningless; only
clusters of ≥4 pointer slots are trustworthy. Heavily-importing modules also
make call-target statistics useless for delta recovery.

### Export-directory anchor works

PE export directories give a stable file base. A directory at `0x29f26c`
solves to **`TFAT.dll`, file base `0x28e200`**: 35/35 name-RVAs resolve and
34/35 exports are SH-4 prologues. Therefore `file = file_base + RVA` holds
throughout a module.

`module_scan.py` maps **26 modules** (TFAT, DISKCACHE, FATUTIL, OLEAUT32, …).
VA base is recovered by constant `V − RVA` across exports; OLEAUT32
(`Vb = 0x03930000`) is verified with 282 literal sites, 166 of them `jsr`.

### `0x1952b00` is not a section map

The 32-byte records are a **RAM copy list** (`srcVA`, `srcVA+0x70`, page-aligned
`dstVA`, flags, timestamp ≈2011, size, VA). There is no file offset, sizes do
not tile, and the value is not a CRC32. Retracted as a section-map lead.

### Navi modules: neither export nor import anchor

The navi/map modules are EXEs or non-exporting DLLs; there is no export
directory in `0x44xxxx–0x1952c88`.

The hardened import anchor (aligned base, clean DLL name, ≥4 thunks, IAT run
into a mapped module) returns **0 candidates**. Cause: this is a **pre-bound
WinCE ROM** — `romimage` turns imports into direct calls, so import
directories are stripped. Only 1,222 descriptor-shaped records exist and
almost none are coherent; the earlier 380 candidates were coincidental.

The section table does not cover these modules either (no `dataptr` matches a
known module base). Builds B/C differ by 4 bytes but lack build A's map code,
so they cannot pin A's map module.

What is pinned down:

- map module `.text` = file `0xc00000–0xc4b000`;
- map module `.rdata` = file `0xdf6000` = VA `0x02df6000`;
- therefore `Vt < 0x02df6000`; the `jsr` targets at `0x02e0xxxx` belong to a
  different module (file `0xc00000`, delta `0x02200000`).

### Static VA recovery is exhausted

The three remaining static routes also fail:

- `0x15271c8` is **not** a module table: it is 4-byte-aligned packed
  module-name strings in a resource blob (padding was mistaken for a stride);
- the self-name anchor cannot apply because the navi names belong to a
  different module;
- adjacency (`Vt = 0x02dab000`) is wrong — 830 literals there point at embedded
  PNG data — and the call-target scan is flat (18/1122 prologues).

The map module's placement metadata is not present in a statically
recoverable form in this image. The method changes to **relative call-graph
tracing from known functions** and, if needed, hardware/dynamic tracing. QEMU
does not help: the blocker is placement metadata, not instruction semantics.

**Decision (2026-11-05): firmware RE is the primary path.** The reader code
defines the data contract, so the module-base search continues until the
readers are understood. Data-side round-trips and hardware tests continue in
parallel but do not replace this work.

### Readers are name-driven

The `.ind`/`.cmp` reader, `DRSTR` parser and tile reader are **not located
yet**, and filename-xref search cannot find them:

- map filenames (`REFER001.DAT`, `MAPAL001`, `LEV3456R.DAT`,
  `DRSTR001.DAT`, `.ind`) have **zero literal references** anywhere in the
  payload, for every plausible delta;
- names are supplied at runtime by the `DRSTR001.DAT` directory tree, with
  `CMP.LST` giving the root directory;
- the 16-byte table at `0xdf8120` is reporting/update-tool data, not the
  runtime selector;
- constants such as `0x10000`, `40` and `0x1ac` are built from
  immediates+shifts.

Anchor instead on the descriptor struct (`obj+0x78…+0x9c`) and the fd field
setters.

`HCXCmp`/`hcxcmp` strings exist, but no public documentation was found and the
map `.DAT` payloads themselves use plain zlib. Treat `HCXCmp` as a
firmware-side library, not as the map compression.

## Map-code check

The check is **textual/field-based, not cryptographic**. Strings at
`0xe53368`/`0xe533a8`:

```
\SystemSD\VER_INFO\HDD_INFO.TXT
\UserSD\VER_INFO\HDD_INFO.TXT
SD Import: userdata_type is different Sys[0x%x] SD[0x%x]
SD Import: manufacturer_id is different Sys[0x%x] SD[0x%x]
SD Import: destination_id is different Sys[0x%x] SD[0x%x]
SD Import : application type not correct.
```

The comparator chain is **located** (data delta `0x02800000`):

| Address | Role |
| --- | --- |
| `0x6fab2c` | entry wrapper → `0x6faeb0` |
| `0x6faeb0` | mode/path selector (`*(obj+0x10)`; modes 0/10 → path A; status selects `+68/+76/+80`) |
| `0x6fb05c` | field comparison: `manufacturer_id`, `userdata_type`, `destination_id`, `Sys[0x%x]` vs `SD[0x%x]` |

- **`userdata_type` is the range-checked field** (`0 < v < 6`);
  `manufacturer_id` and `destination_id` are arbitrary `u16`.
- The unit selects among multiple `HDD_INFO` locations by mode/status:
  `\SystemSD\…` vs `\UserSD\…` plus three object-relative paths.
- `0x6fafe4` is only a 0x18-byte teardown stub (retracted as the comparator).

A second module (SD format/validate) has data delta `0x1130000` and code file
`0x30d000–0x315000`. FATUTIL is not the parser.

### VerInfoCC is a version provider, not the parser

The COM class reached nearby is **`VerInfoCC.DLL`**, CoClass `VerInfoCtrl`
(CLSID `{408BB0AC-…}`), file base `0xa15200`, code delta `0x027cae00`
(VA `0x031e0000`, proven by vptr `0x031e14e4`). Its embedded type library
exposes only:

```
GetVersionInfo(LONG dwType, VARIANT* pVal)
```

There is **no setter and no path parameter**. “Property 17 carries the
`HDD_INFO` path” and “VerInfoCC parses `HDD_INFO`” are **retracted/refuted**:
the call site is `obj->method#1(17, 0, path)` on a different object; VerInfoCC
reads a compiled-in constant table.

The comparator module's data delta `0x02800000` is settled by its string pool
and the `sprintf` at `0x6fb0d8`.

### The `0x30f008` trail is false

`0x30efcc` is a **free function** `f(obj, mode, flag)`, not a parser: it masks
arg2, requires arg3 == 1, and calls `obj->vtable[0](3,&out)` /
`obj->vtable[1](17,0,*global)`. The object comes from the caller; there is no
`bsr` to it and no absolute literal under any base.

`0x01f83368` is a **writable global**, not the `HDD_INFO` path: the code
stores into it at `0x31098c`–`0x310996`. The code range is `mspart.dll`
(base `0x309200`) / `WAVEAPI.dll` (base `0x30d200`).

**Module attribution warning:** those bases overlap, so
`base ≤ file < base+size` is invalid. Export dirs/names live in the shared
`.rdata` blob addressed via each module's base+RVA. This was the inference
error behind round 10.

Round-10 “SD module delta `0x1130000` / property 17” is **retracted**; the
five string hits were store targets to globals.

`0x6fb05c` is a **message builder**, not a parser: it memsets two buffers,
fills two 16-byte descriptors, formats `SD Import: …` via `sprintf`, branches
on field id `0x00A2`, applies `0..5` in `userdata_type`, and calls
`obj->vtable[5]`.

### Three-filter literal analysis

Literal-pool work needs filters in this order:

1. **F1** — code pages only (≥4 prologues / 4 KiB);
2. **F2** — reject loads whose register is used as a `jsr`/`jmp` target within
   8 bytes;
3. **F3** — reject import thunks.

Candidates fall from 236,765 to **95,758**. Without F2/F3, an IAT slot aligned
against a dense string set manufactures false “clusters”.

Retractions:

- “`USR_Convert` module at `0x0101e408`” — false; those are 12-byte import
  stubs / IAT slots (`0x1e6c020 − 0xe4dc18 = 0x0101e408`); same for
  `0x01011478`.
- “The map module references `VER_INFO\HDD_INFO.TXT`” — false;
  `0xc0dbda`/`0xc1078c`/`0xc10800` are `jsr` targets.

### The only HDD_INFO builder

Under data delta `0x02800000`, the clean data references are exactly:
`0x6faf28` (`mSD\VER_INFO\HDD_INFO.TXT`), `0x6faf0e` (`TXT`),
`0x6faf52` (`til.dll`), `0x6faeee` (`%u`), `0x6fb0ce`
(`manufacturer_id` format).

`0x6faeb0` builds the path from fragments:

- `mode = *(obj+16)`;
- modes `0`/`10` append `mSD\VER_INFO\HDD_INFO.TXT` to a buffer holding
  `\Syste`;
- other modes append `TXT`;
- the DLL branch appends `til.dll`;
- status `2…6` selects `obj+68/76/80`;
- `0x0367b180` logs `Debug Common Version 0.1`.

The `+12` literal is a fragment, not a suffix pointer. The builder does **no
I/O** (`memset`, append, status probe, switch).

### Still open

Six-line mapping remains unknown; constraints are numeric `Sys[0x%x] SD[0x%x]`,
`0 ≤ v < 6`, field enum `0x00A2`. Card vs `0x06000000` has no code link.

The parser is one indirection away: `0x0369d400`, `0x036922cc`, `0x0367b180`,
`0x0369d3dc` in the `0x0367–0x0369xxxx` module receive the built path.

**Next direction:** pin that module with the three-filter index and a cluster
anchored on a string it prints itself; then walk from the helper to the
open/split/parse. Do not infer a module from a single `V − S` match.

### Test package

`tools/hddinfo_variants.py` generates **89** length-preserving variants (all
72 B): content edits, `0…5` sweeps, uppercase-word replacements, pairwise line
swaps and a reverse. A debug console prints the exact
`SD Import: <field> is different Sys[0x%x] SD[0x%x]` message.

### Tile contract from diagnostics

The map layer's own strings pin the contract:

- intra-mesh coordinates are **`0..2047` (11-bit)** at runtime
  (`RGD_JLocGet : t_start_x = 0,2047`, …). This is **not** a storage rule:
  raw `REFER001` bodies contain 4–7 % non-fill `u16` values in `2048–4095`
  and 23–26 % ≥ 4096, so coordinates are bit-packed/masked;
- `MESHMAX_LEV1` exists and mesh numbers are validated;
- per-mesh structures `area_link`, `cvdata`, `rgd_t`, `RGD_commem`;
- link fields `subl->lseg.sttpos/.endpos`, `links_p->linkp`;
- turn/curve enums `RGD_DIRTYPE_*` (9), `RGD_CRSTYPE_*` (14),
  `RGD_DIRSUBTYPE_*`, `RGD_TMTYPE_*` at `0xcc90c4`+;
- dump headers document a six-level table (`VTb Tp;Lv;…|L1..L6|Sz;Adr`,
  `0xdf65a1`) and the file descriptor (`HFile;FileID;Tp;Lv;V#;la Lo`,
  `0xdf6621`).

**Retraction:** the `0x1ac` allocation is **not** the tile level table; it is
a 428-byte per-object OSM buffer for `obj+0x40` (allocator at `0xc0eba0`).

No runtime map-content checksum was found beyond zlib Adler-32. A generic
ASN.1/crypto provider exists (`0x1668070`, `md5WithRSASignature`, `desEDE`, …)
but nothing links it to the map path.

## TFAT16 volume

Immediately after the FAT32 partition, at image offset `0x1C8400400`, there is
a FAT16/TFAT volume:

- boot sector OEM `MSWIN4.1`, filesystem type `TFAT16`
- WinCE TFAT hidden root with `DONT_DEL*` files
- the remaining ~375 MB of the tail is `0xff`

It is probably a WinCE transactional overlay, not map data. Do not modify it
without understanding the recovery path.

## Emulation verdict

Full-system QEMU is **not realistic** today:

- QEMU has one SH-4 machine, `r2d` (SH7751R + SM501), not this board.
- `hw/sh4/sh7750.c` calls `abort()` on an unknown register; a custom BSP dies
  in early `OEMInit`.
- DMA, USB, LCD, CMT, ADC, WDT, NAND/SD host and CAN are missing.
- QEMU SH-4 user mode is upstream TODO; Unicorn has no SH-4.

What works: QEMU `r2d` as a bare-metal SH-4 bench, and Ghidra 12.2 SuperH4
P-code emulation headlessly. Use those for selected routines; use the Python
round-trip validator for the whole-card feedback loop. The full option matrix
is in [`../research/feedback-loop.md`](../research/feedback-loop.md).

## Next steps

Firmware RE remains the primary path.

1. **Static is closed for the reader.** Use the dynamic guide when hardware is
   available: break on MAL `getOffset/getSize`, then fd methods, then fd
   thunks.
2. **While waiting:** build the compiler/offline validators so the first
   hardware session can test a real card immediately.
3. **Dynamic break on the MAL chain (deferred, no hardware):**
   `MAL_DataVol_getOffset` (VA `0x03498d48`, file `0x7f5f48`) or `getSize`
   (VA `0x03498d28`, file `0x7f5f28`); caller is the `.ind` wrapper.
4. **`.ind` mutation matrix (deferred, no hardware):** `size_8000` answers
   buffer size vs `0x10000` compare; `off_last_m1` answers exact seek vs
   `78 9c` scan.
5. **SD bus capture (deferred):** CLK/CMD/DAT0-3 during boot/map entry.
6. Spare-card `HDD_INFO` matrix for the six-line mapping (89 variants; deferred).
7. Use `0..2047` and `MESHMAX_LEV1` as runtime/bit-packed tile constraints.
