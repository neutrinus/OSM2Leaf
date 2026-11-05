# Firmware and pre-partition area

> **Evidence status:** byte offsets, strings and the SH-4 code recovery are
> `VERIFIED` on the EU 2011 image; `SUM4`, `ECEC`, the section-to-VA mapping
> and the role of the duplicated builds are `OBSERVED`/`HYPOTHESIS`.

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
present in all payloads; reading it as the WinCE `0x43454345` ROM signature is
a **HYPOTHESIS**.

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
`MZ`+`e_lfanew`+`PE\0\0`; also 0 `B000FF` and 0 `ROMHDR`. Modules are in
WinCE ROM/XIP form (section bodies, headers stripped).

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

### Still open

Module U references only suffixes of the `HDD_INFO` path; the path-start
literal has **zero** references. Linker suffix merging is the working
hypothesis. The six-line mapping remains a ranked hypothesis: line 4
`SDC08-EVEUR` → manufacturer + destination; QSD lines → `userdata_type`;
line 6 part number; lines 3/5 version/date.

**Next direction:** the `USR_Convert_*` family, especially
`Set finished mark (file=%s)` at `0xe4dc18` — the one function that takes a
path and opens it. Locate its module with a ≥3-string cluster, then walk
backwards from the path argument. Do not infer a module from a single
`V − S` match again.

### Test package

`tools/hddinfo_variants.py` generates 73 length-preserving variants (all 72 B)
for a spare-card matrix: one line per card, `0…5` sweeps on numeric runs, and
uppercase-word replacements. A debug console prints the exact
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

1. **Find the `0x2e0xxxx` module export table** (`exports.py`). Its RVA range
   must cover `0x2e00f98`–`0x2e533e4`; once it does, every `jsr @Rn` target
   becomes a named API and the reader chain closes.
2. **`.ind` mutation matrix on a spare card** (cheapest empirical test):
   change `chunk_size` (4th dword) to `0x20000`/`0x8000`, change `chunk_count`
   by ±1, shift one `chunk_offset`. Accept/reject reveals the `0x10000`
   compare, count trust and seek-vs-scan.
3. **SD bus capture** (CLK/CMD/DAT0-3) during boot/map entry; decode
   CMD17/CMD18 and record the LBA order of `DRSTR001.DAT` vs `.cmp`/`.ind`.
4. **`USR_Convert_*` path opener** at `0xe4dc18`; multi-string cluster, then
   walk from the path argument.
5. Spare-card `HDD_INFO` matrix for the six-line mapping.
6. Use `0..2047` and `MESHMAX_LEV1` as runtime/bit-packed tile constraints.
