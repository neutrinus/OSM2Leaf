# Firmware and pre-partition area

> **Evidence status:** byte offsets, strings and the SH-4 code recovery are
> `VERIFIED` on the EU 2011 image, and so is the CE ROM header / section-to-VA
> mapping (EXP-2026-11-05-35); `SUM4` and the role of the duplicated builds
> are `OBSERVED`/`HYPOTHESIS`. Sections below written before EXP-35 that rely
> on delta fitting are historical; check them with `tools/cerom.py`. Field
> tables and per-section status: [`cerom.md`](cerom.md).

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
0x00200000  u32 0x01752c88        ROM payload length == physlast-physfirst
0x00200014  "\x82FX210ECNI.158"   Clarion version string
0x0020002c  "SUM4" + u32 0xcdf87db0
0x00200034  "470-2824-34"         Clarion part number
0x002001fc  "NKOK"
0x00200200  CE segment base: 0x40-byte boot block (SH-4 entry)
0x00200240  "ECEC"                bytes 45 43 45 43, not 43 45 43 45
0x00200244  u32 0x8e232978        pTOC = VA of ROMHDR
0x00200248  u32 0x01751978        ROMHDR offset from segment base
```

`SUM4` is a tagged checksum field. CRC-32, Adler-32 and plain word sums were
computed and rejected; the algorithm is **UNKNOWN**. `ECEC` is a fixed field
present in all payloads.

### CE ROM header (VERIFIED, EXP-2026-11-05-35)

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
and file location (`o32_dataptr`); 245 of 527 sections are compressed RW data
(framing: M1.2a form 1 22 B / M1.2d form 2 `u24` table + `0x8d80805b` LZXD-like
blocks; codec CE variant, block type 4 in cecompress terms). The nk.exe loader
(build B, `0x3e00200`) tests `o32_flags & 0x2000` at `0x88038666` (`fn
0x880385e4`) and calls decompressor chain `0x88037590`→`0x88037464`→
`0x8803a384` (EXP-2026-11-06-M1.2c, `tools/cedecomp.py`; M8.E1 call target).
Use `tools/cerom.py`. The kernel (`nk.exe`, `coredll.dll`) is not in this
region. **Many conclusions below that were reached by delta fitting are
superseded** (C-516…C-523); in particular the `0x6fab2c`/`0x6faeb0`/`0x6fb05c`
chain is in `BT_MGR.dll`, and the real `HDD_INFO`/`SD Import` literals are in
`Navi.exe` at VA `0x004e7d28` and `0x004e8584`/`0x004e995c`.

Field tables and per-section status: [`cerom.md`](cerom.md).

## Payloads and builds

> EXP-2026-11-05-36: each payload is a complete CE ROM. A (VA `0x8cae1000`, 149
> modules) is the application layer; B and C (VA `0x88000000`) are kernel
> regions with `nk.exe`/`coredll.dll`; B adds the updater set, C the test mode.
> Use `tools/cerom.py --image-start`.

Five payloads, three distinct builds:

| Build | Part number | Offsets |
| --- | --- | --- |
| A | `470-2824-34` | `0x200000` and `0x2000000` (byte-identical over 24.5 MB) |
| B | `470-2759-01` | `0x3e00000` and `0x4800000` |
| C | `470-3142-00` | `0x5200000` |

A/B/C use slightly different wrapper layouts: B/C put the ID at `+0x220` and
the part number at `+0x250`, i.e. CE segment `+0x20`/`+0x50`, while A keeps them
inside the `0x200`-byte wrapper. The CE anchor (`ECEC` at segment base `+0x40`)
is identical for all builds — see [`cerom.md`](cerom.md) §1. The selection logic
is **UNKNOWN**.

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
(`file ↔ VA ↔ size`) — recovered since; the per-section map and its domain are
in [`cerom.md`](cerom.md) §5 and §7.

### Section table is a dead end

**Superseded for builds A–C by the TOC** ([`cerom.md`](cerom.md) §4–§5). Both
offsets lie inside build A's segment (`0x00200200`–`0x01952e88`), and
`0x3e0060` is **not** in build B's wrapper (B starts at `0x03e00000`), so these
are probably genuine `o32_rom` arrays reached through a module's
`ulO32Offset`. The historical claim below stands only for the ad-hoc table:

> The 24-byte records at `0x374000`/`0x3e0060` are `o32_rom`-shaped (a clean
> record at `0x3221b0` has `psize == round_up(vsize, 0x200)`), but the table is
> **not usable as a file map**: its `dataptr` fields point into pure `0xff`
> fill (stale build-time offsets), and consecutive records do not share a
> `realaddr − rva` delta. Do not build on it.

Use the per-module `ulO32Offset` instead.

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

**M3.2b (EXP-2026-11-06, C-2060–C-2066, partial):** zlib 1.1.3 is statically
linked in `Navi.exe` uncompressed sec0 (A). Inflate API:
`inflateInit2_ 0x542256`, `inflate 0x54233c` (tramp `0x54232c`),
`inflateEnd 0x54220c`, `inflateReset 0x5421c4`, `inflate_blocks 0x54332a`.
Call chain: chunked decompressor `fn 0x41c7e8` (20-byte chunk table at
`@(28,ctx)`, direct compressed pointer, no seek/no `78 9c` scan, no `0x10000`
compare in this layer) → one-shot wrapper `0x542148` → inflate. `0x41c7e8` has
no callers in any uncompressed A section (527 searched); Navi.exe sec1/sec2 are
compressed (M1.3 0/245, M1.2f open), so the `.ind` `chunk_offset[]` consumer /
M3.2a,b remain open. Dynamic breakpoints: `0x542148`, `0x41c7e8`, `0x542256`.

**M3.11 (EXP-2026-11-06, C-2120–C-2127, blocked):** `POINT`/`REFER001` access
path anchors in uncompressed Navi.exe sec0 (A): file-name builder
`fn 0x003fbed8` selects the `POINT0` volume id (`0x00179364`, C-881; pools
`0x003fc050`/`0x003fc05e`) and calls volume lookup `fn 0x0040b358` (`0x003fc084`;
28-byte entries, count `+24`, list `+32`); descriptor switch `fn 0x004125a8`
maps type `0x14e8` → `REFER001` `0x00178c68` + `INDEX003.DAT` `0x0017a118`
(and `0x14e4` → `LCTBL001.DAT`/`RDSTM001`, C-880). The decoded-`POINT0xx`
name-page record walker (`tag 0x60|0x68`, `len2` at `+1`, stride `2*len2`,
refer.md C-952/C-953) and the POI name-copy function were **not located** in
any uncompressed build-A o32 section (527 searched): 0 aligned tag pairs, 0
mask walkers, 0 `@(1,ptr)→2*len2` stride sequences; `fn 0x003715a0` (`&0x70==0x60`)
is a single-record consumer, not the walker. **Blocker:** Navi.exe sec1 is
`IMAGE_SCN_COMPRESSED` (vsize `0xff16ae`, M1.3 0/245, M1.2f/M8.E1 open), so the
walker/name-copy (VAs/args/output) remain **UNKNOWN** — likely in sec1; decode
sec1 or trace dynamically to answer M9.10.

**M3.11 pass 2 (EXP-2026-11-07, C-2128, C-2129, C-2540–C-2546):** the
"likely in sec1" above is refuted — sec1 is `.data` (`0xc8002040`), and build A
has no compressed executable section. **POINT page walker:
`fn 0x003f5194(r4 = page, r5 = n)` → pointer to record n, or 0.** Header =
one native u16 `w` (file bytes `tag,len2` big-endian): `len = w & 0x3ff`
words, `(w & 0xfc00) == 0xfc00` → escape of `0x4e8` words, `len 0` → end,
at most 20000 records, advance `2*len`. Dispatcher `fn 0x003f5cdc` (buffer
table `0x00d53500`; also `0x3f5b88`), skip-n `fn 0x003f39c0` (globals page
base `0x00d5e4e4`, count `0x00d5e4d0`; getter `fn 0x003f3314`), escape test
`fn 0x003f8a0c`, body `rec+4` `fn 0x003f5c40`, 8-byte trailer
`fn 0x003f5c90`. Executed in PySh4 (LE) on the US `POINT010` page `0x840ba0`
(swapped to native u16) it returns `parse_page`'s offsets; the unswapped page
does not (`tools/point_walk_l3.py walk`).

**M3.11c name accessor (EXP-2026-11-08, C-2920–C-2927):** the HDLMAP-level POI
name accessors are **`fn 0x003f632c(r4=db,r5=rec)→r0=name ptr`** and
**`fn 0x003f5e78(r4=db,r5=rec)→r0=name len`** (Navi.exe sec0). `0x003f8a0c(rec)`
classifies escape (`&0xfc00==0xfc00` → 0 = escape; else -1 = normal; PySh4 on
0x6040 rec0 returns -1). Normal 0x60xx records dispatch to **field index 5**
(facility/name) via `fn 0x003f61bc(r4,rec,r6=5)` (ptr) /
`fn 0x003f5d98(r4,rec,r6=5)` (len) → `0x003f51e0` (handle resolve vs
`0x00d53500`; indirect `*0x0055d8f0` in `.data`) → `0x003f56bc` (locate field
in page field-descriptor table) → `0x003f5e10` (extract). Escape records use
`fn 0x003f8a80(rec)=rec+25` / `fn 0x003f8a90(rec)`. `sdl_poi_get_data_recorde`
`fn 0x003cd910(db,ref,out)` uses them on the status-1 path (`0x3cdc30`/
`0x3cdc1a`, `out+16` ptr / `out+12` `extu.w(len)*2`). SDL `fn 0x003d1150(ctx,
rec,&ptr)` (`rec[14]`/`rec+21`, fallback `fn 0x003d09a0` splits on
`*0x005628e8`) and `fn 0x003d1188` operate on **SDL-decoded** layout, **not**
raw 0x60xx POINT bytes (refuted for raw display name, PySh4 rec0 length 0;
C-2545). Raw display name is the `ff ff`-delimited suffix (penultimate→trailing
marker; rec0 at `+0x5e`, 999/1000 on page `0x840ba0`).
Open: M3.11b (byte order / page swap). Full end-to-end PySh4 of field 5 on
rec0 requires HDLMAP page context in compressed `.data` (M1.2f/M8.E1) → M9.10.

**M3.13 (EXP-2026-11-06, C-2180–C-2183, blocked):** `ADDRE`/`REFER001` access
path confirmed as the same REFER001 family mechanism (Navi.exe sec0, A):
`fn 0x004125a8` maps type `0x14e8` → `REFER001`+`INDEX003.DAT` (C-880);
`fn 0x003fbed8` selects from the volume-id table `0x00179338` including `ADDRE0`
`0x0017935c` and calls `fn 0x0040b358` (`0x003fc084`); `fn 0x0040114e` resolves
`ADDRE0` (`r5` at `0x00401216`) via `jsr 0x0040b358` at `0x0040123c`. The
decoded-`ADDRE0xx` record parser consuming the M4.9 grammar (C-970–C-979:
`c0/c8/c1` `2*L` framing, name `TT LL 00 ff`, point `TT 40 XX YY`, range tokens,
trailer TOC) was **not located** in any uncompressed build-A o32 section
(282 sections / 23.6 MB): 0 `c0/c8` tag pairs, 0 mask/`2*L`/point-marker
walkers; non-Navi stride/marker hits (Speech*/IOLIB) rejected. No reader VA and
no C-970–C-979 consuming-instruction mapping can be named; fields not ruled
"never read". **Blocker:** Navi.exe sec1 `IMAGE_SCN_COMPRESSED` (vsize
`0xff16ae`, M1.3 0/245, M1.2f/M8.E1 open) — decode sec1 or trace dynamically.
See `docs/format/refer.md` "Firmware reader (M3.13)".

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

OBJDLL VA base `0x03480000` is proven by three literal sites. In OBJDLL, three
sites call `MAL_DataVol_getOffset/getSize` (`0x7f6694`, `0x7f6aa4`,
`0x7f6b84`). In `Navi.exe` (CE A, `--image-start 0x200200`), two wrapper
functions call them via thunks `0x003d1bb0`/`0x003d1ba4` (C-820–C-826,
EXP-2026-11-06-M3.1): `fn 0x00377870` probes volume ids `{3,4,7,8}` with
`getOffset/getSize(id,&u16)` and `memcmp`s `*2`-scaled (off,size) windows
(status `0x03f1`/`0x03f7`; args `r4=ctx, r5=baseA, r6=baseB`; only caller
found `fn 0x00377ae0` at `0x00377ce4`); `fn 0x00377ae0` reads into mapped base
`0x01205040` (`OBJ_DriveInfo_readDataVol`), queries **volume 7** and
`memcpy`s `base + off*2`, `size*2` to a local buffer, then runs disc/version
checks (`SYS_CdVerCmp`, `OBJ_DiscInfo_*`) and calls `fn 0x00377870`. The
`*2` unit and `fn 0x00377ae0`'s caller (none in uncompressed `.text`;
`.rdata`/`.data` compressed) remain open.

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

**Superseded (structure mis-identified).** `0x1951ee0` and `0x1952b00` both sit
at `TOC + idx*0x20 + 0x14`, i.e. inside build A's TOC entries (24 and 121) at
the `ulE32Offset` field. The "≈2011 timestamp" is `ftTime`, the "size" is
`nFileSize`, and the `0x8C…0x8E` pointers are the name/e32/o32/load VAs of
consecutive `TOCentry` records. The real RAM copy table is a 16-byte
`COPYentry` array at `ulCopyOffset` ([`cerom.md`](cerom.md) §6).

The 32-byte records were described as a **RAM copy list** (`srcVA`,
`srcVA+0x70`, page-aligned `dstVA`, flags, timestamp ≈2011, size, VA). There is
no file offset, sizes do not tile, and the value is not a CRC32. Retracted as
a section-map lead — and as a copy-list identification (superseded above).

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
SD Import : finished not found.
```

### SD Import location-record comparators (Navi.exe, build A, M2.2 — VERIFIED)

The `Sys[0x%x] SD[0x%x]` message emitters (task literals `0x004e8584` /
`0x004e995c`, both → `0x001d5438` "destination_id is different") are in
`Navi.exe` build A (IMG256 `92aa525d…`, `--image-start 0x200200`): `sub_004e84c4`
(`0x004e84c4`, stored location, caller `fn 0x004e90c8` `jsr 0x004e91e6`) and
`sub_004e989c` (`0x004e989c`, home location, caller `fn 0x004ea402` `jsr 0x004ea502`).
Both validate a 256-byte record read by `sub_004df31c` (`0x004df31c`,
CreateFileW + ReadFile 0x100 bytes) from a `\UserSD\userdata\*` file:
`\UserSD\userdata\storedlocation.slc` (`"userdata"` `0x19a2bc` + `"storedlocation.slc"`
`0x19a294`, format `\UserSD\%s\%s` @ `0x001cf504`) or
`\UserSD\userdata\homelocation.hlc` (`"homelocation.hlc"` `0x19a2a8`). C-730–C-732.

| SD record (base `r8`, `sub_004df31c` dest) | check | SD source | Sys/reference source |
| --- | --- | --- | --- |
| `+0x0c` u16 `destination_id` | equality `extu.w` vs `r15_comp+0x18` | `\UserSD\userdata\*.{slc,hlc}` (0x100 B) | caller stack `r15_comp+0x18` (0x85fc); **upstream producer unresolved** (C-733/C-738) |
| `+0x0e` u16 `manufacturer_id` | equality vs `r15_comp+0x1a` | same file | caller stack `r15_comp+0x1a` (0x85fd); **upstream unresolved** |
| `+0x12` u16 `userdata_type` | **equality to constant** (`cmp/eq`), not a dynamic Sys field: `0x1010` (`0x004e84c4`, EA `0x004e857e`) / `0x1011` (`0x004e989c`, EA `0x004e9956`) | same file | **code constant** (printf `Sys` arg = const), C-734 |
| `+0x03` u8 `finished` | must be nonzero (`tst`/`bf`) | same file | validity flag |
| `+0x02` u8 `application type` | must be in `{0x01,0x21,0x31}` (`cmp/eq #1,#0x21,#0x31`) | same file | value-set check |

On any failure `*r9=0` (and fail return `r0=0xff`); on pass `*r9=1`, `r0=0` (C-736).
**`0 < userdata_type < 6` is refuted in this module** (C-735): `r8+0x12` is checked
by `cmp/eq` to `0x1010`/`0x1011` only; no range test. `r8+0x02` accepts `{1,0x21,0x31}`,
not `1..5`. This is the SD location-record (`.slc`/`.hlc`) comparator — distinct from
the `HDD_INFO.TXT` line field mapping in `tools/hddinfo.py` M0 (HYPOTHESIS) and from the
retired BT_MGR comparator chain (C-301, C-520/C-528/C-611). The Sys-ref producer for
`+0x0c`/`+0x0e` and the full `.slc`/`.hlc` layout remain open (C-738, C-739).
See `EXP-2026-11-06-M2.2-sd-import-comparator.md`.

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

### Runtime consistency check in `Navi.exe` (M2.11)

This is a second, separate `HDD_INFO` path from the updater's
`Sys[0x%x]`/`SD[0x%x]` ID comparison above. `fn 0x004e7b8c`
(`Navi.exe` build A, `0x004e7b8c..0x004e7cfc`, args `r4` ignored, `r5` selector,
`r6` output @`r8`) opens the path selected by `r5` — `0` =
`\SystemSD\VER_INFO\HDD_INFO.TXT` (pool `0x004e7d2c`), `1` =
`\UserSD\VER_INFO\HDD_INFO.TXT` (pool `0x004e7d28`) — via
`COREDLL!_wfopen` (mode @`0x004e7d34`), reads ≤6 lines with
`COREDLL!fgetws(r15+0x40, 0x20 wchar, FILE*)` (line buffer `r15+0x40`,
`memset(r15+0x42,0,0x3e)`), strips CR/LF (`wcschr 0x0d/0x0a`), and
`wcsncpy`s into inline wchar fields at `r8+0`, `+0x18`, `+0x30`, `+0x4a`,
`+0x62`, `+0x7a` with maxima 12/12/13/12/12/13 `wchar_t`; `fclose` on exit.
Callers (complete): `0x004dd15e`,`0x004dd16c` in `fn 0x004dd028` only (pool
`0x004dd1e4`; EXP-2026-11-06-M2.1-hddinfo-fn-complete, C-721–C-728).
`fn 0x004dd028` reads both copies into two stack structs, compares field 0
(line 1) with `wcsncmp(..., 11)`, then compares the numeric tail of field 0
through `fn 0x004e7d4c` (literal `L"000"` at `0x001d51e4`); it accepts when
the SystemSD value is greater than the UserSD value and sets the validation
flag `0x00b00228`.

The reader is driven by a COM request (no boot-time or SD-insertion path to it
was found): `NaviSetCC.dll` routine `0x02e3eef8` (function-pointer table
entries `0x02e335b4` and `0x02e34494`) sends message `0x841000f7`;
`Navi.exe`'s dispatcher `0x004bda44` routes it to `0x004beae0`, which runs
init (`0x004dd61c`) → read/compare (`0x004dd270`) → validate (`0x004dd700`) →
teardown (`0x004dd214`). `SDC1:` is polled with `DeviceIoControl`
`0x80032004` every 100 ms for decoded state 4 (six attempts, each retried
4×50 ms); `DSK8:` is queried with `0x80032010`. See
EXP-2026-11-06-M2.11-hddinfo-trigger, C-1770–C-1779.

### Still open

The six parser lines map one-to-one to the six fields in `fn 0x004e7b8c`
(line *i* → field *i*, C-1779), but the semantic name of each field is still
guessed, and the numeric helper requires 12 wchar of field 0 while every
factory file has an 11-wchar line 1 (C-1779). Card vs `0x06000000` has no code
link. The `SD Import: ...` ID comparison is the updater side (C-775), not this
runtime check.

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

> **Update (EXP-2026-11-05-37):** superseded in part. Stock QEMU's `sh7785`
> CPU on the `none` machine runs the real kernel into the scheduler; the SoC
> peripheral map and a staged plan (F0–F5) are in
> [`../research/full-system-emulation.md`](../research/full-system-emulation.md).
> The `r2d` points below remain true; the conclusion "not realistic" now holds
> only for stages F4–F5 (app and screen).

Original verdict (before the ROM TOC): full-system QEMU is **not realistic** today:

- QEMU has one SH-4 machine, `r2d` (SH7751R + SM501), not this board.
- `hw/sh4/sh7750.c` calls `abort()` on an unknown register; a custom BSP dies
  in early `OEMInit`.
- DMA, USB, LCD, CMT, ADC, WDT, NAND/SD host and CAN are missing.
- QEMU SH-4 user mode is upstream TODO; Unicorn has no SH-4.

What works: QEMU `r2d` as a bare-metal SH-4 bench, and Ghidra 12.2 SuperH4
P-code emulation headlessly. Use those for selected routines; use the Python
round-trip validator for the whole-card feedback loop. The full option matrix
is in [`../research/feedback-loop.md`](../research/feedback-loop.md).

## CE ROM segment (pointer)

The full layout — wrapper header, `ROMHDR` field table, TOC, `e32`/`o32`,
`IMAGE_SCN_COMPRESSED`, RAM copy table, VA↔file formula, commands and the
discrepancy list — is in [`cerom.md`](cerom.md). This section used to duplicate
it; the authoritative version moved.

In one paragraph: the ~24.5 MB Clarion payload is an uncompressed Windows CE 5
/ SH-4 XIP image. Build A starts at `0x00200200`, `ECEC` at `+0x40`,
`pTOC = 0x8e232978`, `size = 0x01751978`, `ROMHDR` at file `0x01951b78`,
149 modules / 1 file, physical span `0x8cae1000`–`0x8e233c88`. The TOC resolves
`Navi.exe`, `NaviStateCC.dll`, `OBJDLL.dll`, `STDDLL.dll` and more among the
149 module names.
`tools/ce_rom_parse.py` finds five segments (A, A copy, B, B copy, C); B and C
are smaller (91/88 modules, 7.2/6.7 MB) and are probably a separate XIP image.

This supersedes the old "no XIP/section table" negative (C-380/C-381, now
RETRACTED; C-088/C-089). It does **not** mean the map readers are located —
[`cerom.md`](cerom.md) §9 lists what remains unknown. Raw runs:
`EXP-2026-11-05-33` and `EXP-2026-11-05-34`.

## MapUpdate.exe (image B, M2.6)

`MapUpdate.exe` is module #81 of image B: 65536 bytes, `load=0x88a9b000`,
`vbase=0x00010000`, entry `0x0001e0d4`; three sections, the last one
(`rva 0x12000`, vsize `0x358`) is `IMAGE_SCN_COMPRESSED` and is **not**
decoded (M1.2). Imports `COREDLL.dll`, `CEDDK.dll` (`MmMapIoSpace`/
`MmUnmapIoSpace`) and `commondll.dll` (`CApi_GetSramVirtualAddress`,
`CApi_CommitSram`, `CApi_GetModelCode`, `CApi_MakeCRC16`); it loads
`fatutil.dll` dynamically for `FormatVolume`. Function VAs below come from
the `sh4xref.py` prologue heuristic on the uncompressed code section.

### Entry points

| VA | Role |
| --- | --- |
| `0x0001e0d4` | process entry: calls `0x0001e15c`, `0x0001988c`, `0x0001e264` |
| `0x0001988c` | main: creates `MUTEX_MAP_UPDATE` (errors if already running), allocates the manager, calls `ManageInit` |
| `0x00019b70` | `CMapUpdate::MapUpdateInit`: opens `SDC1:`/`FMD1:`/`CEN1:` stores, loads `fatutil.dll`/`FormatVolume`, maps flash with `MmMapIoSpace`, opens event `RCV_FLAP_OPERATE_STATUS` |
| `0x0001d888` | `ManageInit` (thread creation + `ClassCreate`) |
| `0x0001d170` | `ClassCreate` (allocates `CMapUpdate` + `CMapUpIpc`) |
| `0x0001c980` | `MapUpIpcInit` / `IpcClassCreate` (queues `MSG_QUEUE_MAP_UPDATE`, `MSG_QUEUE_MNGER`, `MSG_QUEUE_PRG_UPDATE_CC`) |
| `0x0001d71c` | `MapUpSequenceMain` (dispatches check / proc / format) |
| `0x0001d3a4` | `MapUpdateProc` (copy-user-data path) |
| `0x0001d57e` | `MapUpSdCardFormat` (delete/create partitions, security release) |

### Validation / checks

| VA | Method |
| --- | --- |
| `0x0001a8c0` | `SdCardExists` (`IOCTL_SDC_GET_SDCARD_STATUS` on `DSK1:`/`DSK8:`) |
| `0x0001a9b2` | `CheckSdInfoBuban` |
| `0x0001aa78` | `CheckNK1HeaderDBVer` / `CheckNK1HeaderBuban` |
| `0x0001ab64` | `ValidateReplaceMapCard` |
| `0x0001acac` | `ValidateRewritedCard` |
| `0x0001aec8` | `FlashTargetInfRead` (`IOCTL_FMD_READ`) |
| `0x0001ac78` / `0x0001adfc` | `FlashVerUpInfRead` |
| `0x0001b0fa` | `GetAdmSdInfo` (`\UserSD\HDD_ADM.TXT` / `\SystemSD\HDD_ADM.TXT`) |
| `0x0001b292` | `GetTxtSdInfo` (`\UserSD\VER_INFO\HDD_INFO.TXT` / `\SystemSD\...`) |
| `0x0001a314` | `CheckFlashNK1Code` (checksum / size / end mark) |
| `0x0001c210` | `SilentAuthenticate` (CRC16 attestation over `HDD_CHK.ATT`); calls `sub_0001e3f4` (`0x1e3f4`, CRLF+8B parse via `sub_1e330`/`sub_1e2d4`, partially decoded M2.16 C-2092–2096) |
| `0x0001b3a0` | `SecurityUnLock` |
| `0x0001b572` | `SecurityLockSet` |
| `0x0001b8dc` | `SecurityRelease` / `GetSecurityStatus` |
| `0x0001bfe6` / `0x0001c0ac` | `GetVSramCompleteFlag` / `SetVSramCompleteFlag` |
| `0x0001d268` | `MapUpSdCardCheck` |

### Install / copy / partition work

| VA | Method |
| --- | --- |
| `0x0001a3cc` | `MapUpCopyFile` (src/dst copy, size limit, canonical paths) |
| `0x0001bad0` | `CopyFile` |
| `0x0001bcf2` | `UpdateDisk` (partition enumeration, fail-safe) |
| `0x0001c74c` | `DeleteAndCreatePartition` / `DeleteAllPartition` |
| `0x0001c58c` | `DriveFormat` (`FormatVolume`) |
| `0x0001c3ec` | `CopyUserData` (`\UserSD2\PRIVATE` / `\SystemSD2\PRIVATE`) |
| `0x0001a044` | `UnmountAllPart` |
| `0x0001a11c` | `GetFileCount` (`MPFFFFFF.FFF`) |
| `0x0001c060` | `AllocCopyBuffer` (`VirtualAlloc`) |
| `0x0001cc74` | `MapUpThreadEnd` |
| `0x0001ccfc` | `CheckForReplace` (recovery) |
| `0x0001d7c8` | `MapUpProcessThread` |
| `0x0001d800` | `MapUpCreateThread` |

### Files it opens

- Stores: `SDC1:`, `FMD1:`, `CEN1:`, `DSK1:`, `DSK8:` (and `DSK%d:`).
- SD card: `\UserSD\VER_INFO\HDD_INFO.TXT`, `\SystemSD\VER_INFO\HDD_INFO.TXT`,
  `\UserSD\HDD_ADM.TXT`, `\SystemSD\HDD_ADM.TXT`,
  `\UserSD\HDD_CHK.ATT`, `\SystemSD\HDD_CHK.ATT` (updater attestation; **absent
  as files on factory EU/US cards**, M2.16 C-2090–2091),
  `\UserSD\ClarionUpdate.key`, `\SystemSD\ClarionUpdate.key`,
  `\SystemSD\MapFinish.key`, `\UserSD2\PRIVATE`, `\SystemSD2\PRIVATE`.
- IPC queues: `MSG_QUEUE_MAP_UPDATE`, `MSG_QUEUE_MNGER`,
  `MSG_QUEUE_PRG_UPDATE_CC`.
- Event: `RCV_FLAP_OPERATE_STATUS`; mutex: `MUTEX_MAP_UPDATE`.
- Dynamic library: `fatutil.dll` (`FormatVolume`).
- Patterns: `MPFFFFFF.FFF`, `Part%02d`.

### Summary

`MapUpdate.exe` is the card-install/update agent. It does not parse map tile
geometry; it checks SD card presence, attestation and header/version data,
then formats partitions and copies files, signalling progress over message
queues. Acceptance of a rebuilt card depends on the attestation files above
and the flash/NK version checks, together with the runtime `Navi.exe`
comparator (M2.1/M2.2). The byte-level attestation algorithm and the
compressed section remain unknown.

## Model area and Target ID (market, M2.7)

`commondll.dll` exports `CApi_GetModelArea` (build B `0x03c0398c`, C
`0x03be3994`, ordinal 39; next to `CApi_GetModelCode`/`GetModelBaseType`).
The stub dispatches to a runtime model-info object; build B's object is built
in `0x03c070d8` and the area binder reaches the target-ID object
`vtable 0x03c032dc`, slot 2 `0x03c0c908`, which returns byte `+5` (build C:
vtable `0x03be32e4`, slot 2 `0x03beca64`). There is no `CApi_SetModelArea`
export.

The object is filled lazily in B `0x03c0c830` / C `0x03bec98c` by
`KernelIoControl` (coredll ordinal 557) with IOCTL `0x01013208`, a 4-byte
input `{1}` and a 4-byte output. Byte `+4` must be non-zero and not `0xFF`;
the four bytes are logged as `Target ID Code >> %02X%02X%02X%02X`
(B `0x03c03328`). Byte `+5` is the model area.

`AppLaunch.dll` turns it into a market name and a launch-table mask
(B `0x03bcba58` / C `0x03bab580`):

| Area | Name | Mask |
| --- | --- | --- |
| `0x10` | Japan | `0x00010000` |
| `0x20` | USA | `0x00020000` |
| `0x30` | Euro | `0x00040000` |
| `0x40` | Russia | `0x00080000` |
| `0x50` | China | `0x00100000` |
| other | WorldWide | `-1` |

Unknown areas fall back to `KernelIoControl(0x0101304C)` ("Env Variable").
The mask filters the launcher table (B `0x03bcc5b0`/`0x03bcc564`), i.e. it
selects processes/drivers, not the map database. The map/navigation modules do
not import the area API. The card's `HDD_INFO.TXT` is checked against unit-side
target info read by `KernelIoControl(0x0101302C)` (11-byte record at `+96`,
map-DB bounds at `+112`/`+114`); no card value sets the area.

Details and the negative controls: `EXP-2026-11-06-M2.7` and C-780–C-789.

## Compression budget per module (M1.12)

Measured with `python3 tools/reader_precheck.py IMG --table` on build A
(`archive/head256.img`, SHA-256 `92aa525d…`; the first 256 MiB of the EU 2011
image, which is byte-identical). Sizes are section vsize, the runtime extent.
"Executable" means CODE or EXEC flagged. The edge columns count call-like
edges from decodable code into a compressed section: `bsr` is a direct call;
`literal direct` is a literal that is the jump target; `literal indirect` is a
literal that is a slot, so the code calls the pointer stored in compressed
bytes; the target is not readable from decodable bytes, and whether it is plain
code is UNKNOWN. These are lower bounds (claims
C-2510–C-2519; `Navi.exe` detail in C-2511 and C-2513).

| module | sections | vsize (B) | compressed (B) | share | executable compressed (B) | bsr into compressed | literal direct | literal indirect |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `gwes.exe` | 4 | 613288 | 39044 | 6.4% | 0 | 0 | 0 | 259 |
| `fatfsd.dll` | 3 | 69190 | 2492 | 3.6% | 0 | 0 | 0 | 90 |
| `diskcache.dll` | 3 | 7239 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `fatutil.dll` | 4 | 31885 | 3952 | 12.4% | 0 | 0 | 0 | 55 |
| `shell.exe` | 3 | 69874 | 9164 | 13.1% | 0 | 0 | 0 | 125 |
| `toolhelp.dll` | 3 | 2819 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `commctrl.dll` | 4 | 322671 | 10212 | 3.2% | 0 | 0 | 0 | 303 |
| `mspart.dll` | 3 | 13949 | 312 | 2.2% | 0 | 0 | 0 | 0 |
| `waveapi.dll` | 4 | 89734 | 3760 | 4.2% | 0 | 0 | 0 | 146 |
| `audevman.dll` | 3 | 21663 | 2388 | 11.0% | 0 | 0 | 0 | 48 |
| `ppp.dll` | 4 | 96816 | 6024 | 6.2% | 0 | 0 | 0 | 127 |
| `asyncmac.dll` | 3 | 11145 | 1128 | 10.1% | 0 | 0 | 0 | 61 |
| `cxport.dll` | 3 | 22319 | 6208 | 27.8% | 0 | 0 | 0 | 56 |
| `iphlpapi.dll` | 3 | 45848 | 3056 | 6.7% | 0 | 0 | 0 | 68 |
| `winsock.dll` | 3 | 2765 | 264 | 9.5% | 0 | 0 | 0 | 0 |
| `ws2.dll` | 3 | 28908 | 2208 | 7.6% | 0 | 0 | 0 | 51 |
| `ws2instl.dll` | 3 | 4982 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `wspm.dll` | 3 | 5298 | 296 | 5.6% | 0 | 0 | 0 | 0 |
| `nspm.dll` | 3 | 6514 | 340 | 5.2% | 0 | 0 | 0 | 28 |
| `afd.dll` | 3 | 70309 | 3200 | 4.6% | 0 | 0 | 0 | 101 |
| `ndis.dll` | 3 | 116877 | 7252 | 6.2% | 0 | 0 | 0 | 120 |
| `dhcp.dll` | 3 | 21674 | 568 | 2.6% | 0 | 0 | 0 | 0 |
| `tcpstk.dll` | 3 | 287778 | 35572 | 12.4% | 0 | 0 | 0 | 111 |
| `tapi.dll` | 4 | 53273 | 2128 | 4.0% | 0 | 0 | 0 | 0 |
| `unimodem.dll` | 3 | 34593 | 1744 | 5.0% | 0 | 0 | 0 | 70 |
| `usbd.dll` | 3 | 15562 | 1048 | 6.7% | 0 | 0 | 0 | 39 |
| `mmtimer.dll` | 3 | 4385 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `ole32.dll` | 3 | 140234 | 10756 | 7.7% | 0 | 0 | 0 | 75 |
| `oleaut32.dll` | 4 | 147918 | 7648 | 5.2% | 0 | 0 | 0 | 79 |
| `atlce400.dll` | 5 | 54658 | 4536 | 8.3% | 0 | 0 | 0 | 130 |
| `SpeechCC.dll` | 4 | 165245 | 20792 | 12.6% | 0 | 0 | 0 | 151 |
| `Speech.exe` | 3 | 1951433 | 422489 | 21.7% | 0 | 0 | 0 | 262 |
| `auirtdll.dll` | 4 | 1077725 | 626352 | 58.1% | 0 | 0 | 0 | 155 |
| `auiapp.exe` | 4 | 21579 | 1325 | 6.1% | 0 | 0 | 0 | 110 |
| `ddddifull.dll` | 3 | 183948 | 72768 | 39.6% | 0 | 0 | 0 | 74 |
| `Bolero.dll` | 3 | 18630 | 1796 | 9.6% | 0 | 0 | 0 | 87 |
| `wavessi1.dll` | 3 | 38023 | 952 | 2.5% | 0 | 0 | 0 | 0 |
| `wavessi2.dll` | 3 | 38023 | 952 | 2.5% | 0 | 0 | 0 | 0 |
| `UsbOhci.dll` | 3 | 48436 | 2120 | 4.4% | 0 | 0 | 0 | 0 |
| `FOMAB.dll` | 3 | 17370 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `COMD.dll` | 3 | 50539 | 704 | 1.4% | 0 | 0 | 0 | 0 |
| `COMH.dll` | 3 | 41219 | 632 | 1.5% | 0 | 0 | 0 | 0 |
| `IOLIB.dll` | 3 | 33523 | 1424 | 4.2% | 0 | 0 | 0 | 0 |
| `ThreadStackMonitor.dll` | 3 | 2014 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `BT_MGR.dll` | 3 | 502510 | 119232 | 23.7% | 0 | 0 | 0 | 86 |
| `BT_Modem.dll` | 3 | 22032 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `AntitheftCCWrapper.dll` | 3 | 4883 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `AntitheftCC.dll` | 4 | 89456 | 7032 | 7.9% | 0 | 0 | 0 | 106 |
| `CddaCC.dll` | 4 | 46767 | 3036 | 6.5% | 0 | 0 | 0 | 97 |
| `CdrCC.dll` | 4 | 69742 | 4556 | 6.5% | 0 | 0 | 0 | 164 |
| `RDSCC.dll` | 4 | 70238 | 5344 | 7.6% | 0 | 0 | 0 | 163 |
| `AuxCC.dll` | 4 | 40190 | 2484 | 6.2% | 0 | 0 | 0 | 86 |
| `AVSettingCC.dll` | 4 | 71032 | 4600 | 6.5% | 0 | 0 | 0 | 112 |
| `Audio.exe` | 3 | 233851 | 20525 | 8.8% | 0 | 0 | 0 | 244 |
| `CameraCC.dll` | 4 | 91073 | 9292 | 10.2% | 0 | 0 | 0 | 278 |
| `MultiLineTextCC.dll` | 4 | 40460 | 2380 | 5.9% | 0 | 0 | 0 | 66 |
| `OSM_MSGDLL.dll` | 4 | 13277 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `OSMDLL.dll` | 4 | 29722 | 4652 | 15.7% | 0 | 0 | 0 | 84 |
| `SYS.dll` | 3 | 4542 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `OBJDLL.dll` | 4 | 502323 | 151660 | 30.2% | 0 | 0 | 0 | 396 |
| `STDDLL.dll` | 4 | 109440 | 2844 | 2.6% | 0 | 0 | 0 | 16 |
| `RASTERIZER_DLL.dll` | 3 | 157553 | 848 | 0.5% | 0 | 0 | 0 | 0 |
| `AvSipCC.dll` | 4 | 59012 | 3252 | 5.5% | 0 | 0 | 0 | 97 |
| `Marquee.dll` | 4 | 37176 | 2392 | 6.4% | 0 | 0 | 0 | 90 |
| `AvStringSipCCJP.dll` | 4 | 165984 | 25816 | 15.6% | 0 | 0 | 0 | 107 |
| `IconDrawCC.dll` | 4 | 205883 | 85088 | 41.3% | 0 | 0 | 0 | 109 |
| `ICLDLL.dll` | 3 | 11307 | 432 | 3.8% | 0 | 0 | 0 | 17 |
| `ScreenState.dll` | 3 | 340285 | 17924 | 5.3% | 0 | 0 | 0 | 48 |
| `AvCCWrapper.dll` | 3 | 18946 | 2768 | 14.6% | 0 | 0 | 0 | 191 |
| `OSCL.dll` | 3 | 13378 | 656 | 4.9% | 0 | 0 | 0 | 0 |
| `BT_DB.dll` | 3 | 12839 | 1036 | 8.1% | 0 | 0 | 0 | 24 |
| `BT_WRPENG.dll` | 3 | 81067 | 3680 | 4.5% | 0 | 0 | 0 | 50 |
| `DCM_API.dll` | 3 | 13086 | 1016 | 7.8% | 0 | 0 | 0 | 0 |
| `BT_ENG.dll` | 3 | 425598 | 35656 | 8.4% | 0 | 0 | 0 | 607 |
| `ComMid.exe` | 3 | 126704 | 11141 | 8.8% | 0 | 3 | 0 | 144 |
| `CPF.exe` | 3 | 114411 | 16641 | 14.5% | 0 | 0 | 0 | 52 |
| `DiagnosisCC.dll` | 4 | 222828 | 24956 | 11.2% | 0 | 0 | 0 | 201 |
| `ScreenTouchCC.dll` | 4 | 37126 | 2356 | 6.3% | 0 | 0 | 0 | 82 |
| `VerInfoCC.dll` | 4 | 37142 | 2332 | 6.3% | 0 | 0 | 0 | 86 |
| `Consult.exe` | 3 | 58681 | 4053 | 6.9% | 0 | 1 | 0 | 85 |
| `XGLDLL.dll` | 4 | 946350 | 737368 | 77.9% | 0 | 0 | 0 | 112 |
| `NaviCCIpcMsg.dll` | 3 | 6004 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `NaviDestCC.dll` | 4 | 79243 | 12096 | 15.3% | 0 | 0 | 0 | 199 |
| `NaviDestDLL.dll` | 3 | 8397 | 344 | 4.1% | 0 | 0 | 0 | 0 |
| `NaviEvCC.dll` | 4 | 148073 | 16452 | 11.1% | 0 | 0 | 0 | 175 |
| `NaviGbpDLL.dll` | 3 | 10096 | 648 | 6.4% | 0 | 0 | 0 | 0 |
| `NaviGeneralCC.dll` | 4 | 57650 | 3920 | 6.8% | 0 | 0 | 0 | 149 |
| `NaviGuideCC.dll` | 4 | 118304 | 6108 | 5.2% | 0 | 0 | 0 | 126 |
| `NaviMapCC.dll` | 4 | 87094 | 4728 | 5.4% | 0 | 0 | 0 | 273 |
| `NaviMapScrollCC.dll` | 4 | 67652 | 4472 | 6.6% | 0 | 0 | 0 | 196 |
| `NaviMlaDLL.dll` | 3 | 16306 | 600 | 3.7% | 0 | 0 | 0 | 0 |
| `NaviRegCC.dll` | 4 | 127890 | 6128 | 4.8% | 0 | 0 | 0 | 423 |
| `NaviRegDLL.dll` | 3 | 3802 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `NaviRouteCC.dll` | 4 | 280572 | 8380 | 3.0% | 0 | 0 | 0 | 349 |
| `NaviRouteDLL.dll` | 3 | 20635 | 756 | 3.7% | 0 | 0 | 0 | 92 |
| `NaviSearchCC.dll` | 4 | 622137 | 17996 | 2.9% | 0 | 0 | 0 | 311 |
| `NaviSetCC.dll` | 4 | 228578 | 22304 | 9.8% | 0 | 0 | 0 | 317 |
| `NaviDrawCC.dll` | 4 | 73267 | 7944 | 10.8% | 0 | 0 | 0 | 156 |
| `NaviStateCC.dll` | 4 | 110708 | 5488 | 5.0% | 0 | 0 | 0 | 103 |
| `NaviTrfCC.dll` | 4 | 256502 | 48332 | 18.8% | 0 | 0 | 0 | 305 |
| `NaviUserInfoCC.dll` | 4 | 59555 | 3864 | 6.5% | 0 | 0 | 0 | 121 |
| `Navi.exe` | 3 | 22331684 | 16778254 | 75.1% | 0 | 0 | 0 | 3560 |
| `PhoneCC.dll` | 4 | 204060 | 11700 | 5.7% | 0 | 0 | 0 | 265 |
| `BtAudioCC.dll` | 4 | 46258 | 3204 | 6.9% | 0 | 0 | 0 | 97 |
| `PhoneBTA.exe` | 3 | 707816 | 55060 | 7.8% | 0 | 0 | 0 | 312 |
| `ScreenStateCC.dll` | 4 | 2320286 | 245228 | 10.6% | 0 | 0 | 0 | 222 |
| `SystemEXE.exe` | 3 | 78271 | 6077 | 7.8% | 0 | 0 | 0 | 216 |
| `SystemCC.dll` | 4 | 121809 | 7388 | 6.1% | 0 | 0 | 0 | 274 |
| `MaintenanceCC.dll` | 4 | 74418 | 4012 | 5.4% | 0 | 0 | 0 | 120 |
| `AuiMonitoringCC.dll` | 4 | 50932 | 4764 | 9.4% | 0 | 0 | 0 | 249 |
| `TelemaCCWrapper.dll` | 3 | 4376 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `TelemaAutoplayCCLib.dll` | 3 | 1511 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `TelemaDLCCLib.dll` | 3 | 1723 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `TelemaAdjCC.dll` | 4 | 43440 | 2904 | 6.7% | 0 | 0 | 0 | 114 |
| `TelemaAdjHisCC.dll` | 4 | 45683 | 2976 | 6.5% | 0 | 0 | 0 | 122 |
| `TelemaAdjSetCC.dll` | 4 | 46883 | 3040 | 6.5% | 0 | 0 | 0 | 121 |
| `TelemaAutoplayCC.dll` | 4 | 73629 | 4444 | 6.0% | 0 | 0 | 0 | 204 |
| `TelemaCarwingsCC.dll` | 4 | 49561 | 3308 | 6.7% | 0 | 0 | 0 | 136 |
| `TelemaCntsListCC.dll` | 4 | 41597 | 2864 | 6.9% | 0 | 0 | 0 | 111 |
| `TelemaCPCC.dll` | 4 | 42163 | 2928 | 6.9% | 0 | 0 | 0 | 125 |
| `TelemaDCMSetCC.dll` | 4 | 51531 | 3308 | 6.4% | 0 | 0 | 0 | 125 |
| `TelemaDLCC.dll` | 4 | 57927 | 3524 | 6.1% | 0 | 0 | 0 | 158 |
| `TelemaDLSetCC.dll` | 4 | 43622 | 2928 | 6.7% | 0 | 0 | 0 | 116 |
| `TelemaFvtCC.dll` | 4 | 41968 | 2864 | 6.8% | 0 | 0 | 0 | 111 |
| `TelemaFvtRegCC.dll` | 4 | 47663 | 3064 | 6.4% | 0 | 0 | 0 | 126 |
| `TelemaRegPntCC.dll` | 4 | 41711 | 2880 | 6.9% | 0 | 0 | 0 | 119 |
| `TelemaRouteCC.dll` | 4 | 46966 | 3528 | 7.5% | 0 | 0 | 0 | 149 |
| `TelemaTelCallCC.dll` | 4 | 88640 | 5000 | 5.6% | 0 | 0 | 0 | 154 |
| `TelemaImageDrawCC.dll` | 4 | 2192486 | 2019088 | 92.1% | 0 | 0 | 0 | 108 |
| `Cws_Apl.dll` | 3 | 23488 | 2180 | 9.3% | 0 | 0 | 0 | 24 |
| `Prb_Apl.dll` | 3 | 6553 | 0 | 0.0% | 0 | 0 | 0 | 0 |
| `TelemaAppWrapper.dll` | 3 | 20222 | 2768 | 13.7% | 0 | 0 | 0 | 190 |
| `Telema.exe` | 3 | 8086203 | 6994649 | 86.5% | 0 | 0 | 0 | 637 |
| `iPodCC.dll` | 4 | 68011 | 4636 | 6.8% | 0 | 0 | 0 | 165 |
| `UsbAudioCC.dll` | 4 | 76087 | 6012 | 7.9% | 0 | 0 | 0 | 265 |
| `BOLERODLL.dll` | 3 | 128675 | 6056 | 4.7% | 0 | 0 | 0 | 192 |
| `Usb.exe` | 3 | 159235 | 8069 | 5.1% | 0 | 0 | 0 | 280 |
| `VehicleCCWrapper.dll` | 3 | 5913 | 308 | 5.2% | 0 | 0 | 0 | 23 |
| `UnitMainteCC.dll` | 4 | 50401 | 3052 | 6.1% | 0 | 0 | 0 | 106 |
| `VehicleMainCC.dll` | 4 | 35030 | 2284 | 6.5% | 0 | 0 | 0 | 83 |
| `EtcsCC.dll` | 4 | 131435 | 15640 | 11.9% | 0 | 0 | 0 | 152 |
| `ComfortCC.dll` | 4 | 47810 | 3208 | 6.7% | 0 | 0 | 0 | 102 |
| `HvacCC.dll` | 4 | 43771 | 3024 | 6.9% | 0 | 0 | 0 | 103 |
| `DriveComputerCC.dll` | 4 | 78704 | 6612 | 8.4% | 0 | 0 | 0 | 115 |
| `EvTimerCC.dll` | 4 | 97730 | 3872 | 4.0% | 0 | 0 | 0 | 112 |
| `EvNoticeCC.dll` | 4 | 359359 | 58320 | 16.2% | 0 | 0 | 0 | 120 |
| `InfoBarCC.dll` | 4 | 428374 | 70284 | 16.4% | 0 | 0 | 0 | 147 |
| `Vehicle.exe` | 3 | 1435509 | 1030123 | 71.8% | 0 | 0 | 1 | 293 |
| `multiskin.dll` | 4 | 33622 | 2164 | 6.4% | 0 | 0 | 0 | 80 |

    modules 149, with a compressed section 133; compressed sections 245
    total vsize 53725980, compressed 30212810 (56.2 %), executable compressed 0, executable decodable 22767466

## Next steps

Next is `TODO.md` Step 2: fix the file-TOC stride, add `e32`/`o32` and the copy
table to the parser, then build `tools/cerom.py` and a Ghidra memory map — see
[`cerom.md`](cerom.md) §11. Firmware RE remains the primary path.

1. **Static global-VA guessing is closed; static TOC extraction is open.** The
   reader is still unlocated and the dynamic guide (break on MAL
   `getOffset/getSize`, then fd methods, then fd thunks) remains the fallback
   when hardware is available.
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
