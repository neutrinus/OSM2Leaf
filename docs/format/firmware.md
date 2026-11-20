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
Call chain: chunked decompressor `fn 0x0041c7dc` (20-byte chunk table at
`@(28,ctx)`, direct compressed pointer, no seek/no `78 9c` scan, no `0x10000`
compare in this layer) → one-shot wrapper `0x542148` → inflate. `0x0041c7dc` has
no callers in any uncompressed A section (527 searched); Navi.exe sec1/sec2 are
compressed (M1.3 0/245, M1.2f open), so the `.ind` `chunk_offset[]` consumer /
M3.2a,b remain open. Dynamic breakpoints: `0x542148`, `0x0041c7dc`, `0x542256`.

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
mask walkers, 0 `@(1,ptr)→2*len2` stride sequences; `fn 0x00371594` (`&0x70==0x60`)
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

**M3.11c pass 2 (EXP-2026-11-19-M3.11c-point-name-accessor-l3, C-5110–C-5116, done):**
the "`.data` context" is the BSS slot table, and the M3.22 writer fills it. The resolver
`fn 0x003f51e0` maps `db` (= the page, slot `+0x1c`) to its companion slot `+0x20`,
which points to the file's **field dictionary** (one block per `POINT` `.DAT`:
`u16[0]=0xffff`, `D = C + 2*u16[C+2]`, `u16[D+26]` = 9 fields, chained entries with the
id at `+12`). `fn 0x003f56bc` finds the record's field area
(`rec + 2*(hi+lo+8)` of `u16[rec+10]` for header class 3/2). That area starts with one
length byte per field, in words, and `fn 0x003f5e10` adds them up to reach field 5. PySh4
(`tools/point_name_accessor.py run`) returns US2011 record 0 = `+0x5e`, 9 words,
`HANA HEALTH CENTER` (US2011 `0x0041ec8c`/`0x0041e7d8`). After the M5.12 rename it
returns `OSM2LEAF TEST POI1`. Name + field 6 (address) split the display text on
1000/1000 records per build. The returned offsets point into the swapped page;
the byte order of the text is M3.11b.

**M4.52 POINT chain locator reader (EXP-2026-11-20-M4.52-point-locator-reader, C-5397–C-5399):**
the header parser `fn 0x003f930c` (EU2011) / `fn 0x00421c3c` (US2011) decodes the
`.DAT` directory cells at `0x800` with the block-address leaf `0x0040f00c` /
`0x00436f58`; cell `0x82a` (field dictionary) goes to object `+24`. The POINT page loader
`fn 0x003fe2d4` / `fn 0x00426480` (caller `fn 0x003ffce0` / `fn 0x00427e1c`) reads the
dictionary record from header-table entry `+64` (`0x0040ee4c`), decodes the base
reference `D+4` with the same leaf, adds `start_w` and requests `2*comp_w` bytes through
`0x003f6c88` / `0x0041f5e8` (slot `+8` sector, `+12` offset, `+16` length). In PySh4 it
reads a `relocate`d name chain at its new base (6/6, both builds) and a stale reference at
the old base (`tools/point_locator_l3.py`).

**M3.13 (EXP-2026-11-06 pass 1, EXP-2026-11-08 pass 2, C-2180–C-2187, partial):**
`ADDRE`/`REFER001` access path confirmed (C-2180, Navi.exe sec0, A):
`fn 0x004125a8` maps type `0x14e8` → `REFER001`+`INDEX003.DAT` (C-880);
`fn 0x003fbed8`/`fn 0x0040114e` resolve `ADDRE0` (`0x0017935c`) via
`fn 0x0040b358`. Pass-1 byte-grammar search missed the reader (C-2129 class);
pass-2 mask/stride re-run finds `fn 0x003f56bc` (sec0, uncompressed,
`0x003f56ec`) — the sole `*r5 & 0xe000 >= 0xc000` (`cmp/hs` vs literal
`0xc000`) header-class gate in sec0 (1/82 `0xc000` loads), accepting ADDRE
`c0/c8/c1` native swapped-`u16` tags (C-973 tag-class mapped). It resolves via
`fn 0x003f51e0` (`0x00d53500` REFER buffer table, POINT family), walks a
sub-table (`+24/+26/+12`, 2-byte stride) and returns an entry pointer; called
by `fn 0x003f5d98`/`fn 0x003f61bc`. C-970–C-972, C-974–C-977 and the
sequential `2*L` record-stream cursor/token consumers remain **not mapped**
(fields not ruled "never read"; second signature family / `0x00d53500`-bound
L3 trace needed). Buffer-slot→ADDRE binding is `HYPOTHESIS`. L3 probe of
`0x0040b358`→`-1`, `0x0040114e`→FPU-unmodelled at `0x00401150` (no
COREDLL/state). Navi.exe sec1/sec2 are compressed *data* (C-2128), not a code
blocker. See `docs/format/refer.md` "Firmware reader (M3.13)".

**M3.22 (EXP-2026-11-10, C-3460–C-3468, blocked — provisional):** `0x00d53500`
is BSS in `Navi.exe` sec1 (C-3442/H49), so its contents are run-time written.
`sh4xref --to 0x00d53500` (IMG256 `92aa525d…`, build A) gives **33 loads / 20
functions**; all sites classified by store/read opcode evidence: **11 READ**
(dispatch/lookup incl. `fn 0x003f51e0`, `fn 0x003f5cdc`) and **22 STORE_WRITE**.
Writers (named VAs/functions): clear/init (zero constants over observed slots
~0x00–0xAC) — `fn 0x0040dfa8` (loads `0x0040e096,0x0040e110,0x0040e138,0x0040e152,
0x0040e16c,0x0040e1aa`), `fn 0x00415fe8` (`0x00416066,0x004161b2,0x004161fa,
0x0041624e,0x0041627e,0x004162aa`), `fn 0x0040e28c` (`0x0040e5c0`, slots
+136/+140). Populate/copy (context/call/handle values into specific slots,
e.g. +4,+12,+16,+20,+24,+28,+44,+56,+60,+124,+128,+156) — `fn 0x00412ac0`
(`0x00412d12`, copies handle/page-pointer words from r8 context; strongest
static populate evidence), `fn 0x003faf04` (`0x003fb018,0x003fb066`),
`fn 0x003fc9c8` (`0x003fcb84`, call result `0x0040f168`), `fn 0x003fcbf0`
(`0x003fd2ac,0x003fd2b8,0x003fd310`), `fn 0x003fd390` (`0x003fd448`), `fn
0x003fe774` (`0x003febca`). Stored-value back-trace: zero constants; context
struct fields `@(20/24,rX)` from `@r10/@r11/@r15`; computed word; global deref
`@(*0x014a9928)->+20`; no direct `fread`-into-table observed in sec0 (IAT
`0x0055d1a0` indirect). **Layout/entry size/count and per-field schema source
remain UNKNOWN**; Done-when unmet (no L3 run/writer-inverse reproducing >=1
entry, M9.35). Unblock: M9.35 IAT-bound L3 of populate writers to observe slot
mutations and derive schema (see EXP-2026-11-10-M3.22-bss-table-writer).

**M3.22 pass 2 (EXP-2026-11-19-M3.22-d53500-writer-l3, C-5120–C-5127, done):**
the "table" is **one structure of 4-byte page-pointer slots**, 46 words (`0xb8` B) at
`0x00d53500` in EU2011 and 44 words (`0xb0` B) at `0x00c81100` in US2011, not an array
of records. A reader finds a page's family by comparing the page pointer with the
slots; the POINT dispatcher `fn 0x003f5cdc` (EU2011) sends `[+0x0c]`/`[+0x14]`/`[+0x24]`
(n=0) back as the page, `[+0x2c]`/`[+0x70]` to `0x003f5b88`, `[+0x1c]`/`[+0x50]`/`[+0x60]`/
`[+0x80]`/`[+0x88]`/`[+0x90]` to the walker `0x003f5194`, the rest to `0x003f39c0`.
The populate writers are the cases of the task-message switch `fn 0x003ff6a0` (EU2011;
US2011 `0x0042780c`) on message type `@(ctx+104)`:

| type | writer EU2011 (US2011) | slots written (static + L3) |
| --- | --- | --- |
| `0x14cc`, `0x14d0`, `0x14d3` | `fn 0x003fc9c8` (`0x0042533c`) | `+0x04`, `+0x7c` |
| `0x14cd`, `0x14d1` | `fn 0x003fcbf0` (`0x004226f0`) | `+0x2c`, `+0x80`, `+0x9c` |
| `0x14e4` | `fn 0x003fd390` (`0x00425564`) | `+0x0c..+0x18`, `+0x2c`, `+0xb0` (u16), `+0xb4` |
| `0x14ef` | `fn 0x003faf04` (`0x00423ba8`) | `+0x1c` = `*(*(0x014a98e0)+20)` (L3), `+0x20` via `0x0040e9dc` |
| `0x14f0` | `fn 0x003faf04` (`0x00423ba8`) | `+0x38` = `*(*(0x0154ade0)+20)`, `+0x3c` |

Also `fn 0x003fe774` (`+0x2c`) and `fn 0x00412c60` (`+0x0c..+0x18`, `+0xb0`, `+0xb4`);
clear routines `fn 0x0040dfa8`, `fn 0x00415fe8`, `fn 0x0040e510` (EU2011). The global
in `*(G)+20` is chosen by the type leaf `0x0040e858` (EU2011; US2011 `0x004368b0`,
`0x14ef → 0x01319780`). PySh4 run (`tools/d53500_writer.py writer`): with
`G+0 → OBJ`, `OBJ+20 → factory POINT010 page`, the writer fills `+0x1c` and the real
dispatcher returns record 1 at `+0x4e` (EU2011) / `+0x80` (US2011), equal to the walker
alone. Pass-1 label corrections: load `0x00412d12` is in `fn 0x00412c60`, `0x0040e5c0`
in `fn 0x0040e510`, `0x003f601a` in `fn 0x003f600c` (pdata).

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

## EU→US function matches (2011 builds)

The EU 2011 and US 2011 cards carry different `Navi.exe` builds (C-3487):
EU2011 has 7,596 `.pdata` records, US2011 7,520, and **no function sits at the
same address**. `tools/fn_match.py` matches them by position-independent
content (C-3740). A frozen, vendor-free control table for the 13 cited readers
lives in [`tools/fixtures/fn_match_eu_us_2011.json`](../../tools/fixtures/fn_match_eu_us_2011.json);
it pins the head SHA-256s and every row's expected verdict, so a wrong image
fails with its hash rather than a `NOMATCH` (C-3741).

Replay (positive control, exit 0; `13 rows, 0 mismatch`, whose census is
5 `UNIQUE` / 7 `DIFFERENT` / 1 `NOMATCH`):

```bash
python3 tools/fn_match.py --fixture tools/fixtures/fn_match_eu_us_2011.json \
    --us archive/us256.img --module Navi.exe
```

| EU2011 VA | US2011 VA | Role | Status |
| --- | --- | --- | --- |
| `0x0041c7dc` | `0x00444540` | CMP chunk engine | VERIFIED (content match) |
| `0x0041c990` | `0x004446f4` | CMP chunk-table loop | VERIFIED (content match) |
| `0x0041c044` | `0x00443da8` | CMP/`.ind` opener | VERIFIED (content match) |
| `0x003f632c` | `0x0041ec8c` | POI name accessor | VERIFIED (content match) |
| `0x00542250` | `0x0056454c` | zlib `inflate` | VERIFIED (content match) |
| `0x0041a438` | `0x0044219c` | MMAIN | DIFFERENT (identical masked forms; literal pool moved) |
| `0x00419350` | `0x004410b4` | DRSTR | DIFFERENT (identical masked forms; literal pool moved) |
| `0x004125a8` | `0x0043a378` | REFER access path (`0x14e8`) | DIFFERENT (identical masked forms; literal pool moved) |
| `0x0040b358` | `0x00433458` | ADDRE0 resolve | DIFFERENT (identical masked forms; literal pool moved) |
| `0x003bc960` | `0x003ec274` | RDSTM | DIFFERENT (identical masked forms; literal pool moved) |
| `0x003f61bc` | `0x0041eb1c` | POI field accessor | DIFFERENT (identical masked forms; literal pool moved) |
| `0x003f5194` | `0x0041db44` | POINT page walker (`.pdata` GAP, leaf path) | DIFFERENT (one pool word `0x4e8`→`0x4d8`) |

The remaining cited reader is a genuine rewrite: the ADDRE resolve at
`0x003fbed8` has a different branch block at `+0x16c` (`bf` vs
`mov.l @(pc),r3`), 8 resolved calls in EU vs 7 in US, and no masked-form twin;
its US counterpart is reached only by call context (`0x00424850`, HYPOTHESIS).
M1.22b decided each of these (EXP-2026-11-16-M1.22b-eu-us-census, C-3622/C-3624):
7 of the 8 former `NOMATCH` were a matcher gap (relocated literal data), and
one is a rewrite.

## The US build at L3: the walkers and the chunk engine run on US code

M1.22 extended the runner past the 13 readers above: the `POINT` walker set
and the chunk engine now have `us2011` targets, located the same way, and both
were run on the US `POINT010` page `0x840ba0` (record 0..1000, 1000 records):

| Role | EU2011 VA | US2011 VA | How it was located |
| --- | --- | --- | --- |
| POINT nth reader | `0x003f5194` | `0x0041db44` | masked-form twin; one pool word `0x4e8`→`0x4d8` |
| POINT skip walker (globals) | `0x003f39c0` | `0x0041c370` | masked-form twin; same global offsets, moved page-base cell |
| POINT dispatcher | `0x003f5cdc` | `0x0041e63c` | identical body; its own pool names the two walkers in the same order, which is how the skip walker above was disambiguated from the nth reader |
| CMP chunk engine | `0x0041c7dc` | `0x00444540` | masked-form twin (111/111 halfwords); its own pool names the relocated helpers |
| zlib `inflate_mask[17]` | `0x00574de0` | `0x005987b0` | the `shll2 r2; mov.l @(pc),r3; mov.l @(r0,r3),r2; and r12,r2` site, unique per build; both slots are `INIT` and the 17 words read from the `nk_decomp`-decoded sec1 equal `2^n - 1` (`chunk_decoder_l3.py run … --sec1 read-mask`, M9.40) |
| zlib `zcalloc`/`zcfree` | `0x00543a98`/`0x00543aa8` | `0x00565d94`/`0x00565da4` | the 6-halfword trampoline shape, one calloc and one free hit per build |
| POINT globals base/count/page | `0x00d5e4c0`/`0x00d5e4d0`/`0x00d5e4e4` | `0x00c8c0c0`/`0x00c8c0d0`/`0x00c8c0e4` | the skip walker's own pool; same offsets inside the RW block, moved block |
| POINT escape record length (halfwords) | `0x4e8` | `0x4d8` | the nth reader's one differing pool word |
| chunk helpers memcpy/mod/mod31 | `0x003d146c`/`0x003d140c`/`0x003d1484` | `0x00400944`/`0x004008e4`/`0x0040098c` | the chunk engine's own pool slots (COREDLL thunks) |
| zlib inflate wrapper | `0x00542148` | `0x00564444` | the chunk engine's own pool slot |

The table is a checked copy, not a source: the values are owned by
[`tools/build_targets.py`](../../tools/build_targets.py) (M1.32), from which
`point_walk_l3`/`chunk_decoder_l3` `BUILD_TARGETS` and `fn_audit`'s
`US_BUILD_STARTS` are derived; `python3 tools/build_targets.py check` diffs
this table and `tools/l3_harness/targets.json` against it (`TOTAL
only-in-*: 0`).

Both runs `PASS`; the chunk engine's output is byte-identical to
`cmpind.decode`, and the walker reproduces `parse_page` offsets for all nine
sampled records. The controls are the interesting part: the US walker with the
**EU** global cells (or the EU walker VA on the US text) stops on an unmapped
access, and the US chunk engine with the EU helper stubs likewise blocks — so
the pass is not the old translation offset. The US pair is **not** the EU
pair: the US `POINT010` is `48812f8c…`/`7ac54e3b…` and the EU factory pair is
`d02a8d87…`/`3eaa47bb…`. Both builds read the **EU** page `0x6e06d0` (9/9
each) and both chunk engines decode the EU pair byte-identically, so the US
reader reproduces a card it did not come from (C-3537). An earlier draft of
this page said the pairs were identical; that was wrong — it had looked at a
partial EU extract with no `POINT010`.

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
(`0x004e84c4`, stored location, caller `fn 0x004e8f38` `jsr 0x004e91e6`) and
`sub_004e989c` (`0x004e989c`, home location, caller `fn 0x004ea288` `jsr 0x004ea502`).
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
| `0x20` | USA | `0x00040000` |
| `0x30` | Euro | `0x00020000` |
| `0x40` | Russia | `0x00080000` |
| `0x50` | China | `0x00100000` |
| other | WorldWide | `-1` |

Unknown areas fall back to `KernelIoControl(0x0101304C)` ("Env Variable").
(USA/Euro masks corrected by M1.34, C-5350; the table layout and the
`Navi.exe` records are in `docs/research/rom-registry.md`.)
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

## The map-file layer of `Navi.exe` (M3.26, EU2011 build A — names, not format)

Every map file the unit reads passes through one contiguous block of `Navi.exe`,
`0x00417d00…0x0041cab0` (EU2011 build A). This section names its functions so a
reader task can start from an entry instead of a search. It carries **no format
claim**: a role is what the code does, not what a byte means.

Evidence: `docs/experiments/EXP-2026-11-18-M3.26-file-layer.md`, claims
C-4440–C-4449. Every address below is an EU2011 build-A VA and was checked with
`python3 tools/nk_decomp.py pdata IMG256 --module Navi.exe --index 2 VA`
(START = a `.pdata` function entry; `leaf` = a `GAP` record start, i.e. a
no-prologue body `.pdata` attaches to the previous function).

### The 117 functions, in address order

A `leaf` row is **not** a function start: the address is a `GAP` start, i.e.
the start of a no-prologue body that `.pdata` attaches to the previous `fn`
(prologue 0 B at that boundary), ending exactly where the next `fn` begins.
All eight are called (`bsr`/`jsr`) and are either 12-`0x58`-byte accessors
(`0x419a9c`, `0x41a3b8`, `0x41a42c`, `0x41a600`, `0x41ac1c`, `0x41c0cc`) or
initialisers (`0x41a5cc`, `0x41abdc`); each holds its own `rts`. `Len` is the
pdata length for `fn` rows and `next fn start - this GAP` for `leaf` rows.

| VA | pdata | Len | Role (what the code does) |
| --- | --- | --- | --- |
| `0x00417d48` | fn | `0xdc` | map-file task dispatcher, 12 messages (`0x0017a888`) |
| `0x00417e24` | fn | `0x28` | memset 48 B `0x00e8d8e0`, clear `0x009cfbcc` |
| `0x00417e4c` | fn | `0x54` | volume teardown: release+close each mount, reset io table |
| `0x00417ea0` | fn | `0xc` | thunk: `0x41a600` volume-present test -> return |
| `0x00417eac` | fn | `0xdc` | volume record set: swap `u8` pairs in `r8+0x20`, warn |
| `0x00417f88` | fn | `0x58` | volume record get: `r4+42` kind -> 0/1/3 status |
| `0x00417fe0` | fn | `0x110` | open by name for a read: path `0x418dfc`; flag 0 -> `+".cmp"` plain, flag 1 -> `0x41b780(path,1)`; `"rb"` (C-5101) |
| `0x004180f0` | fn | `0x60` | lookup volume record `(hi:lo)` in `0x18d50`, state test |
| `0x00418150` | fn | `0x88` | lookup volume record variant, returns `u16` field |
| `0x004181d8` | fn | `0x244` | big open/dispatch: state `0x41a3b8`, `0x41aaf4`, `0x41a600` |
| `0x0041841c` | fn | `0xc` | external entry stub -> `0x4181d8` |
| `0x00418428` | fn | `0x6c` | external entry: OSMDLL #19/#20, `0x41a7e4` |
| `0x00418494` | fn | `0xc8` | debug dump via `0x417a5c` (stdio through it) |
| `0x0041855c` | fn | `0xd8` | read request: open `0x417fe0`, seek `(sector<<11)+off` `0x41b8a4`, loop `0x41b954` (C-5106) |
| `0x00418634` | fn | `0xc8` | serve one queued 48-B request (`0x00e8d8e0`): `0x41855c(+20..+36, flag u16 +46)`, reply `0x4179c8` |
| `0x004186fc` | fn | `0x4c` | clear volume index: memset `0x1c20` + `0x668a0` B, `0x009cfcd4` |
| `0x00418748` | fn | `0x2c8` | `.ind`/`.IND` `FindFirstFileW` scan, volume lookup |
| `0x00418a10` | fn | `0x7c` | read 40-byte record: seek `idx*40+40`, fread 40 |
| `0x00418a8c` | fn | `0x74` | memmove 40-byte record into volume table slot |
| `0x00418b00` | fn | `0x60` | read 32-byte record: seek `(idx<<5)+off`, fread 32 |
| `0x00418b60` | fn | `0x5c` | memmove 32-byte record into volume table slot |
| `0x00418bbc` | fn | `0x12c` | volume record fill from dir entry, alloc index slot |
| `0x00418ce8` | fn | `0x68` | volume record lookup -> slot pointer out-param |
| `0x00418d50` | fn | `0xac` | read by cluster: volume record -> `0x41855c` fill |
| `0x00418dfc` | fn | `0x290` | name -> volume record: 36-B table, path build, `0x18748` |
| `0x0041908c` | fn | `0x144` | volume table dump (`Dir list`, `dir cnt` strings) |
| `0x004191d0` | fn | `0xf0` | entry-table reader, `<15000` bound, per-entry loop |
| `0x004192c0` | fn | `0x90` | external REFER/LEV entry (5 callers), state `==2` test |
| `0x00419350` | fn | `0x334` | big file open/table loader: alloc 0x77220, read |
| `0x00419684` | fn | `0x210` | `DRSTR001.DAT` opener/parser (`0x419350`) + volume walk |
| `0x00419894` | fn | `0xa0` | mount-state dump: state `==3` gate then reset chain |
| `0x00419934` | fn | `0x30` | init slot table `0x00e24ce8`, clear `0x009cfce0` |
| `0x00419964` | fn | `0x64` | `STATUS INFOMATION` banner + version line |
| `0x004199c8` | fn | `0xd4` | handle-slot search over `0x00e24d00` (28-B stride) |
| `0x00419a9c` | leaf | `0x30` | LEAF: append `r4` to a slot list: index 28 B, count u16 at `+6` |
| `0x00419acc` | fn | `0xb4` | handle-table dump (`0x17ac2c` format rows) |
| `0x00419b80` | fn | `0x40` | reset handle table: zero 0x708 B, count `-1` |
| `0x00419bc0` | fn | `0x78` | close handle by slot, timer 0x7530 on overflow |
| `0x00419c38` | fn | `0x68` | 4 x 5 handler dispatch `0x17ab38`, `"UNKNOWN"` fallback |
| `0x00419ca0` | fn | `0x84` | mount-state dump: `DIR` table, state, `r4` arg (`0x41a3c4`) |
| `0x00419d24` | fn | `0xd4` | mount: `DRSTR`, MGR status, `writeDataVol`, timer |
| `0x00419df8` | fn | `0x58` | init: state probe, `0x418634`, state 2 or 1000 ms timer |
| `0x00419e50` | fn | `0x84` | media/event switch `0x81140051..0x81140060` |
| `0x00419ed4` | fn | `0x38` | reset 5 timer slots `0x00e24cc0` to -1 |
| `0x00419f0c` | fn | `0x78` | timer-id lookup in 5-slot table |
| `0x00419f84` | fn | `0xe8` | timer register: `SYS_Timer_setMsg`, slot fill |
| `0x0041a06c` | fn | `0xa4` | timer clear by id (`SYS_Timer_clear`) |
| `0x0041a110` | fn | `0x64` | timer clear-all over 5 slots |
| `0x0041a174` | fn | `0x7c` | event/timer dump (`EVENT`, `TIMERID` strings) |
| `0x0041a1f0` | fn | `0x54` | event dispatch: timer-id then clear then `0x419c38` |
| `0x0041a244` | fn | `0x48` | init `OBJ_DriveInfo_getObjID` into `0x009cfcec` |
| `0x0041a28c` | fn | `0x78` | `OBJ_DriveInfo_writeRecogSts`, kind -> `0x009cfce8` |
| `0x0041a304` | fn | `0x84` | `OBJ_DriveInfo_writeDataVol`, byte-swap 256 `u16` |
| `0x0041a388` | fn | `0x30` | set mount state `0x009cfce4` (0..2 only) |
| `0x0041a3b8` | leaf | `0xc` | LEAF: return mount state `*0x009cfce4` |
| `0x0041a3c4` | fn | `0x54` | volume-info dump (4 fields, `Info Show`) |
| `0x0041a418` | fn | `0x14` | memset 0x1000 B at `0x00e23cc0` (`MMAIN` buffer) |
| `0x0041a42c` | leaf | `0xc` | LEAF: return the `MMAIN` buffer `0x00e23cc0` |
| `0x0041a438` | fn | `0xf4` | `MMAIN001.DAT` opener + `0x419350` parse, slot ref |
| `0x0041a52c` | fn | `0xa0` | disc-volume/address dump (`%08x(+%04x)`, 4 x 8 B) |
| `0x0041a5cc` | leaf | `0x34` | LEAF: zero `0x009cfcf4..0x009cfd08` (handle list) |
| `0x0041a600` | leaf | `0x20` | LEAF: handle-list-present test (`*0x009cfcf4`, `…f8`) |
| `0x0041a620` | fn | `0xf0` | handle acquire: 48-B `0x003d13e8`, list insert |
| `0x0041a710` | fn | `0xd4` | handle release: unlink, `0x41b180` recycle |
| `0x0041a7e4` | fn | `0xa0` | handle release by id: scan list, unlink |
| `0x0041a884` | fn | `0x58` | calendar-end teardown: `0x41b240`, zero 5 cells |
| `0x0041a8dc` | fn | `0xec` | fd-table dump/list walk (`0x41a174`) |
| `0x0041a9c8` | fn | `0x12c` | iob/fd table dump (`0x17aeac` columns) |
| `0x0041aaf4` | fn | `0xe8` | alloc handle `0x009cfd04 < 199`, `0x41b0c4` |
| `0x0041abdc` | leaf | `0x1c` | LEAF: zero `0x009cfd0c/10/14` (io table) |
| `0x0041abf8` | fn | `0x24` | reset io chains `0x009cfd0c..14`, `0x41b240(0)` |
| `0x0041ac1c` | leaf | `0xc` | LEAF: return `*0x009cfd14` (io list head/count) |
| `0x0041ac28` | fn | `0x100` | io descriptor acquire, `0x009cfd14 < 50` |
| `0x0041ad28` | fn | `0xc4` | io descriptor release, unlink `0x009cfd0c` |
| `0x0041adec` | fn | `0xc4` | io descriptor release variant (write side) |
| `0x0041aeb0` | fn | `0xe8` | io descriptor release by id, scan `0x009cfd0c` |
| `0x0041af98` | fn | `0xc0` | io descriptor dump (`headp` string) |
| `0x0041b058` | fn | `0x6c` | class table `0x00e23c80` init (4 classes, `0x17b0c4`) |
| `0x0041b0c4` | fn | `0xbc` | class alloc check, `0x41b2a4` dump on failure |
| `0x0041b180` | fn | `0xc0` | free: return 48-B block to its class pool |
| `0x0041b240` | fn | `0x64` | class table reset by index, `0x41b3bc` probe |
| `0x0041b2a4` | fn | `0xf0` | class table debug dump (`%08x->` chain) |
| `0x0041b394` | fn | `0x28` | destroy: dump then `DeleteCriticalSection` |
| `0x0041b3bc` | fn | `0xb4` | `fopen`+`strcmp` wrapper (`"rb"` @`0x0017ab20`) |
| `0x0041b470` | fn | `0x88` | `fseek`/`ftell` wrapper (short seek -> error) |
| `0x0041b4f8` | fn | `0xac` | `fread` wrapper, `clearerr`/`ferror` |
| `0x0041b5a4` | fn | `0xac` | `fwrite` wrapper, `clearerr`/`ferror` |
| `0x0041b650` | fn | `0x4c` | `fclose` wrapper, release io descriptor |
| `0x0041b69c` | fn | `0x4c` | `ftell` wrapper, release io descriptor |
| `0x0041b6e8` | fn | `0x98` | block-size init (40<<8 / 50), `memSize` dump |
| `0x0041b780` | fn | `0x9c` | open wrapper `(path, flag)`: flag 0 -> `fopen` `"rb"`; else `.cmp` manager `0x41bed4` (C-5101) |
| `0x0041b81c` | fn | `0x88` | close/release, `.CMP` close path |
| `0x0041b8a4` | fn | `0xb0` | seek wrapper `(h, off, whence, flag)`: `fseek` or `.cmp` seek `0x41bfb4` |
| `0x0041b954` | fn | `0xd4` | read buffer via chunk engine (`0x41c044`) or fread |
| `0x0041ba28` | fn | `0x68` | file-size probe: ftell, seek 2, restore |
| `0x0041ba90` | fn | `0x15c` | mount: `CMP.LST` probe, `.cmp` manager config (50/20/`0x20000`/`0x10000`/`0x14000`, ops table) (C-5104) |
| `0x0041bbec` | fn | `0x74` | debug logger (`NKDbgPrintfW`, `ErrorLogMsg`) |
| `0x0041bc60` | fn | `0x38` | size round-up wrapper -> `0x41c0cc` |
| `0x0041bc98` | fn | `0xf0` | `.cmp` manager init: 50 handle slots of `0x118` B, ops copy, ctx `0x41c190` |
| `0x0041bd88` | fn | `0x98` | critical-section-wrapped `.cmp` manager create (`0x41bc98`) |
| `0x0041be20` | fn | `0x10` | `DeleteCriticalSection` only |
| `0x0041be30` | fn | `0xa4` | `.cmp` open: free slot, `CMP.LST` match `0x41c2e0` -> `0x41c524` or plain open; `u16 +0x116` = compressed (C-5101) |
| `0x0041bed4` | fn | `0x60` | CS-wrapped `.cmp` open -> `0x41be30` |
| `0x0041bf34` | fn | `0x80` | CS-wrapped `.cmp` close -> `0x41cae8` |
| `0x0041bfb4` | fn | `0x90` | CS-wrapped `.cmp` seek -> `0x41cab0` (logical position) |
| `0x0041c044` | fn | `0x88` | CS-wrapped `.cmp` read: `u16 +0x116` 0 -> plain read, 1 -> `0x41c990` |
| `0x0041c0cc` | leaf | `0x58` | LEAF: slot-size walk, `(count+16)*20` + 4-aligned fields |
| `0x0041c124` | fn | `0x6c` | read a whole file via ops (open/size/read/close): loads `CMP.LST` at mount (C-5103) |
| `0x0041c190` | fn | `0x150` | `.cmp` reader ctx init: entries, buffers `0x14000`/`0x10000`, `.IND` cache `0x41cb1c` (C-5104) |
| `0x0041c2e0` | fn | `0x124` | `CMP.LST` match: NUL-separated, `\`-terminated entry = directory, A-Z fold (C-5103) |
| `0x0041c404` | fn | `0x70` | whole `.IND` (`path+".IND"`) through the name-keyed cache `0x41d114`/`0x41d084` |
| `0x0041c474` | fn | `0xb0` | 16-byte `.IND` header: cache or ops open/read 16/close |
| `0x0041c524` | fn | `0xcc` | `.cmp` handle open: `.IND` header, `.ind` size `(count+4)*4`, `fopen(path+".CMP","rb")` (C-5101) |
| `0x0041c5f0` | fn | `0x1ec` | loop over `chunk_offset[]`: 20-B entries `+0` off, `+4` clen, `+8` `i*chunk`, `+12` extent; `chunk==0x10000` (C-5102) |
| `0x0041c7dc` | fn | `0xe8` | per-chunk one-shot zlib `0x00542148` + `memcpy` |
| `0x0041c8c4` | fn | `0xcc` | `.ind` header: `chunk==0x10000` check, first/last chunk index (`_divlu`/`_modlu`) |
| `0x0041c990` | fn | `0x120` | chunk read driver: index, entries `0x41c5f0`, seek+one read of the batch, inflate `0x41c7dc` (C-5102) |

### Block boundaries and the controls that bound it

- 117 nodes, 109 `START` + 8 `GAP`, 0 `INSIDE` (`pdata --index 2` on
  `Navi.exe` sec2: 7,596 `pdata` records, `0x32ed9c…0x558300`). The 117 VAs
  are the graph nodes in `[0x417d00, 0x41cab0)`, not a hand list; the sweep
  command is in the EXP. `Len` matches `pdata` for all 109 `fn` rows and
  `next fn - GAP` for all 8 `leaf` rows (checked, 0 mismatches).
- 13 block functions have a static outside caller (graph); the list below is
  the graph's `callers` for each, and `sh4xref.py --to` reproduces a pool load
  in the caller for all 13 (`0x417e24` <- `0x417924`, `0x4186fc` <-
  `0x417924`/`0x419894`/`0x419d24`, `0x419b80` <- `0x417924`/`0x41a388`,
  `0x419ed4` <- `0x417924`/`0x419350`/`0x41a620`, `0x41a244`, `0x41a418`,
  `0x41a5cc`, `0x41abdc`, `0x41b058` <- `0x417924` plus `0x41abf8`/`0x41af98`/
  `0x41b81c` for `0x41b058` and `0x419894` for `0x41a418`, the other eight
  from `0x417924`; `0x418428` <-
  `0x3f6f00`, itself called by `0x3f06a8`, `0x3f3dfc`, `0x3f3f90`, `0x3f7134`,
  `0x3f720c`, `0x3f81b0`, `0x40126c`, `0x40364c`, `0x4039c0`, `0x4055ac`,
  `0x40dfa8`, `0x40e510`; `0x41841c` <- `0x3f6c88`, itself called by
  `0x3f6bb0`/`0x3f7384`/`0x3f73dc`/`0x3f7438`/`0x3f7480`; `0x4192c0` <-
  `0x409ba0`, `0x409c28`, `0x409cc8`, `0x40a108`, `0x40b358`; `0x41a1f0` <-
  `0x41785c`, the `.cmp` open). `0x417924` itself has one static caller,
  `0x32efa8` (the task table), and has no imports. The graph also lists
  `0x4180f0`, but `sh4xref --to 0x00417924` does not resolve it, the full
  disassembly of `0x4180f0` loads only `0x418d50`/`0x41bbec`, and the literal
  `0x00417924` sits at one pool in the image (`0x32f45c`): graph false edge,
  not established.
- Two of the thirteen are the layer's **outside face**: `0x418428` is the
  `OSMDLL` #19/#20 request path (it calls `0x41a7e4`, a handle release by id,
  and `0x4179c8`), reached through `0x3f6f00`; `0x41841c` is a one-instruction
  jump to `0x4181d8`, the big open/dispatch, reached through the OBJDLL
  `DiscInfo` function `0x3f6c88`. Everything else external enters at
  `0x4192c0` (the `REFER`/`LEV` readers) or at the debug dispatcher.
- Inside the block the only access to the filesystem is through the stdio
  wrappers `0x41b3bc` (`fopen`), `0x41b470` (`fseek`/`ftell`), `0x41b4f8`
  (`fread`), `0x41b5a4` (`fwrite`), `0x41b650` (`fclose`), `0x41b69c`
  (`ftell`) and `0x418748` (`FindFirstFileW`/`FindNextFileW`). Non-file
  `COREDLL` helpers (`memset`, `memcpy`, `memmove`, `strcat`, `strcpy`,
  `_divlu`, `_modlu`, `_modls`) are called directly; only the stdio `f*` are
  wrapped.
- **Falsifier that did not fire (control):** of the 13 functions that import
  `ReadFile`/`MapViewOfFile`/`CreateFileMapping*`, none is reachable from
  `0x0040b358` (the `ADDRE` resolve, a map path) — `callgraph.py path` prints
  `no static path` for all 13. So no map file bypasses the block through the
  Win32 file API; a map path that did would refute "the block is the layer".

### The dispatcher: message number -> handler (`0x00417d48`)

`0x00417d48` takes the message in `r4`, prints `"IOM_CD DEBUG!!!"`
(`0x0017a894`) first, then `r8 = r4 - 1`; `cmp/hi #11` rejects `> 12`. The byte
table at `0x0017a888` holds 12 offsets `00 06 0c 12 18 1e 24 30 36 3c 46 4c`
(verified by direct read; the next bytes are the `IOM_CD DEBUG!!!` string).
`0x417d70` is `braf r0` (`0023`) and its delay slot is `0x417d72`, so the
branch lands on `target = 0x417d74 + offset` (byte offsets), giving
`0x417d74`, `7a`, `80`, `86`, `8c`, `92`, `98`, `a4`, `aa`, `b0`, `ba`, `c0`.
The `braf` delay slot at `0x417d72` is `nop`; a reader body is `mov.l` +
`bra 0x417dce` (message 7 runs two: `jsr` then `mov.l`+`bra`), and
`0x417dce` is `jsr @r3` + `nop` followed by the dispatcher epilogue (`rts`
at `0x417dda`). The ten handlers inside the block plus the default are
`jsr`-called, so they return here; the two outside ones are only named, not
described.

| Msg | Handler | What the handler is |
| --- | --- | --- |
| 1 | `0x0041908c` | volume table dump |
| 2 | `0x0041af98` | io-descriptor dump |
| 3 | `0x0041b2a4` | class-table debug dump |
| 4 | `0x0041a3c4` | mount-state dump |
| 5 | `0x0041a9c8` | iob/fd table dump |
| 6 | `0x00418494` | generic debug dump |
| 7 | `0x00419964` then `0x00419acc` | version banner, then handle-table dump |
| 8 | `0x004178e4` | (outside the block; `#### Task Info ####`) |
| 9 | `0x0041a174` | timer-id table dump |
| 10 | `0x0041a52c` with `r4 = 0` | disc-volume / volume-address dump |
| 11 | `0x00417ab4` | (outside the block; CD-ROM Manager dump) |
| 12 | `0x0041b6e8` with `r4`, `r5` | block-size init + `memSize` dump |
| other | `0x00417ca0` | banner/dump lines incl. `10/05/07` (outside the block) |

Two handlers are outside the 117-node block (`0x4178e4`, `0x417ab4`) and the
default is a third; they are named here because the map is not a map without
them.

The second-level dispatch `0x00419c38` is a **4 x 5** function table at
`0x0017ab38`, one row per state, five columns per kind (`kind = r4`,
`cmp/hs #5` at `0x00419c42` rejects `kind >= 5`; `state = *0x009cfce0` is read at
`0x00419c54`, multiplied by 5 at `0x00419c60`, and `(state*5 + kind)*4` indexes
the table). The `UNKNOWN` fallback (`0x00419c74`, string `0x0017ad2c`) is taken
only for `kind >= 5`. The table is exactly 20 *used* words: the string
`MEDIA MOUNT` starts at `0x17ab88`, right after `0x17ab38 + 20*4`. Read out of
the image it is

| state | kind 0 | kind 1 | kind 2 | kind 3 | kind 4 |
| --- | --- | --- | --- | --- | --- |
| 0 | `0x419ca0` | `0x419ca0` | no-op | `0x419894` | `0x419934` |
| 1 | `0x419d24` | `0x419d24` | no-op | `0x419894` | no-op |
| 2 | `0x419df8` | `0x419df8` | `0x419df8` | `0x419894` | no-op |
| 3 | `0x419894` | `0x419894` | `0x419894` | `0x419894` | `0x419934` |

where `no-op` is `0x42af34`, a `GAP` start (`rts` + `nop`, prologue 4 B of the
previous `fn`), i.e. an empty handler and not a function of this block.
`0x41a388` never stores a state above 2 (`cmp/hs` with 3 at `0x0041a38e`), so
states 0..2 are the ones the table is written for; the state-3 row is read from
the image too. The row names (a kind 0..4 format/slot change against a mount
state) are the role, not a byte meaning.

### M3.2 answers, read off `0x0041c990`

M3.2 asked two questions: (a) does `chunk_size` size a buffer or is it compared
against `0x10000`; (b) does the reader seek by `chunk_offset[]` or scan for
`78 9c`.

- **Chain.** `0x0041c044` (CS-wrapped chunk read) -> `0x0041c990` (driver) ->
  `0x0041c8c4` (index-header decode), `0x0041c5f0` (chunk-table walk),
  `0x0041c7dc` (per-chunk inflate). `0x41c404` builds the `*.IND` path and
  opens it through `0x41d114` (read) or `0x41d084` (write); the file slot it
  uses in the `0x41c404` context is at `+0x13c` (context word 79).
  `0x41c8c4` calls `0x41c404` (`0x41c8da`'s pool) and calls its return `head`
  (the 16-byte `.ind` header buffer `0x41c404` fills). From `head` it
  assembles two little-endian `u32`: A from `head+0x8..+0xb` (`0x41c8e6
  add #8`; `b[+0xb]<<24 | b[+0xa]<<16 | b[+0x9]<<8 | b[+0x8]`) and B from
  `head+0xc..+0xf` (`0x41c8fe add #4`, same order).
  It compares the context word `+0x138` with B (`cmp/eq r3,r8`, `r8` = B), not
  with A (A is compared only with the quotient at `0x41c962 cmp/gt r2,r9`),
  and divides a caller-supplied word by B — `_divlu(*r5, B)`, `_divlu(*r5 +
  r12, B)`, `_modlu(*r5 + r12, B)` (`0x003d140c`/`0x003d1484`, `r5` = the
  caller's second argument, `r12` its third). It returns
  `rem ? count-1 : count-2` in `r0`. `0x41c5f0` builds the 20-byte-stride
  chunk table: it opens the `.ind` through its own `0x41c404` call and reads
  the header itself (`r9` = LE u32 at `head+0`, `r10` = LE u32 at `head+4`,
  `0x41c616`/`0x41c62c`), then fills 20-byte entries over the caller's table;
  each entry gets `+4` (an offset difference), `+8` (source tag) and `+12`
  (end tag). `0x41c990` then fills each entry's `+0x10` with a running sum of
  the `+4` differences and loops `0x41c5f0`/`0x41c7dc`. `0x41c7dc` adds
  `+0x10` to a base pointer and hands `+4`/`+8`/`+12` to the one-shot zlib
  wrapper `0x00542148`, whose output `r12` is the uncompressed slice
  destination.
- **(a) `chunk_size`.** `0x0041c8c4` divides a caller word by B (`head+12`)
  and never compares either operand with a `0x10000` literal. The `.ind`
  itself does carry a `0x10000` **value**: in all **2,875** `.ind` files
  under `~/projekty/leafre-work` the four little-endian u32 are `(logical,
  compressed, ceil(logical/chunk), chunk)` with `chunk == 0x10000` and `count ==
  ceil(logical/chunk)` in every one, and the measured POINT010 pair reads
  A = `149` (u32 #2, the count) and B = `65536` (u32 #3, the chunk). So the
  layer meets the `0x10000` as a loaded **value** (B), never as an immediate
  `0x10000` **compare**. That is literal for this block:
  none of the **392 distinct
  literal-pool values** loaded in `0x417d00…0x41cab0` is `0x10000`, and
  `shll16` occurs only as twelve `1<<16` scale factors (`0x418272`,
  `0x4188b4`, `0x4188f8`, `0x418d8a`, `0x418db0`, `0x4190f4`, `0x41953c`,
  `0x4197a8` in the volume code; `0x41b712`, `0x41b716`, `0x41bafa`,
  `0x41bb00` for size fields; none is in the chunk code `0x41c000…0x41cab0`).
  The byte range `0x417d00…0x41cab0` (19,888 B at file `0x1095f00`) holds
  **0** occurrences of `78 9c` and **0** of the little-endian `u32 0x00010000`,
  so there is neither a zlib-header constant nor a `0x10000` compare anywhere
  in it, executed or not. B (`head+12`) is an **arithmetic divisor**, not a
  buffer size and not a validated constant.
- **(b) seek vs scan.** The reader walks the table `0x41c5f0` built;
  `0x41c7dc` gets the chunk's compressed pointer, two length words and the
  running offset and inflates without searching. No zlib-header scan exists in
  the block: `mov #78` occurs exactly twice (`0x41c690`, `0x41c924`) and both
  are `shll2` index steps to context word 78 (312). `0x41b470` (the
  `fseek`/`ftell` wrapper) is called by
  `0x418a10`/`0x418b00`/`0x419350`/`0x41ba28` for fixed-record reads and the
  size probe, not from the chunk engine. So the engine **does not scan for the
  zlib header**, and the offsets come from the `.ind`, through the descriptor
  callbacks at `0x41ca28`/`0x41ca38`. Both `0x41c690` and `0x41c924` compare a
  loaded word with `ctx+0x138` (context word 78); what `ctx+0x138` holds (a
  tag, or the chunk size itself) is UNKNOWN. The entry layout of the earlier
  M3.2b HYPOTHESIS (`+4` offset / `+8` uncompressed / `+12` compressed) is
  **refuted** — `0x41c7dc` adds `+0x10` to a base and never reads `+4` as an
  absolute offset.
- Where the divisor operands come from: both are read out of the 16-byte
  `head` that `0x41c404` returns (`0x41c8da` calls it), i.e. the `.ind` head
  that `0x41c404` reads through `0x41d114` into the caller's buffer, not from a
  `0x10000`-sized buffer. `0x41ba28` is the **size-probe** path (`ftell`, `fseek(0,2)`,
  restore) that fills the `uncompressed`/`compressed` pair the same header
  carries, but `0x41c8c4` reads both words itself.

### What this table does not say

The block names *where* a read happens, not *what a byte means*. The `.cmp`
chunk layout, the `DRSTR` 40/32-byte node encoding and the tile grammar stay in
their own format pages; a role here that is unread was left as read, not
guessed. `0x41c124` (the wrapper that calls the four ops in the `r7` struct)
keeps its `UNKNOWN` table; the eight `GAP` rows are marked `leaf`, not promoted
to `fn`. Two numeric facts are the block's own, not a format claim: no literal
`0x10000` is loaded and no zlib-header scan exists (the M3.2 answers above, and
the EXP's scan). The `+4`/`+8`/`+12`/`+0x10` chunk-entry fields are named by
what the stores and the inflate call do with them; *why* the `.ind` carries
those numbers is M3.2's format question and stays open.

## Function-pointer tables of `Navi.exe` (M3.24, EU2011 build A)

Who is called indirectly. A *table* is a run of at least three code pointers
(`.pdata` `START`, or a `GAP` leaf) at a fixed stride: stride 4 is a pointer
array (NULL slots allowed, as in a sparse state x event matrix), a larger
stride is an array of rows (`{id, fn}`, `{name, fn, help}`). An `INSIDE` word
ends a run. Scanned: sec0 rodata `0x00011000…0x0032ed9c` (`0x31dd9c` B) and the
stored bytes of sec1 `INIT` after the import table (`0x0055dd38…`, `0x172e4` B).
A *user* is a function whose literal pool holds the base or an entry address
(*exact*), or a value in the first row before the pointer column (*row prefix*:
the row's id/name column, but also any shared constant there, so a table whose
only users are prefix users is weaker).

Tool: `python3 tools/fptables.py scan IMG256 --graph g.json --json t.json`
(`--selftest`); edges for `callgraph.py` (M3.23) with `--edges`; reverse reach
with `fptables.py via g.json t.json VA`. Evidence:
`docs/experiments/EXP-2026-11-19-M3.24-fptables.md`, claims C-3550–C-3559.
All VAs are EU2011 build A; `0x42af34` is the empty `rts` leaf (M3.26).

Totals: **69 tables** (62 sec0, 7 sec1), 909 slots, 534 distinct targets, 48
with a code user, 1 with only a data reference, 20 unreferenced. **481 of the
1,167** functions with no static caller are table entries; 620 more are
loaded as a code literal (a callback passed as an argument), 66 are neither.
Only **21 of the 395** unresolved `jsr @Rn` sites sit in table users: most
indirect calls go through objects or arguments, not through these tables.

### The tables that matter for the map readers

- **`0x0017a0a4` — the REFER/LCTBL message dispatcher.** `fn 0x004124dc`
  scans up to 15 rows `{u32 msg, fn}` (14 used, NULL row ends it), compares
  the `u16` at `@(8, msg)` with the row id and calls `fn(msg)`. Messages
  `0x14cc…0x14f5`. Entries reach the access path in one or two static calls:
  `0x00413a6c` → `0x004125a8` (`LCTBL001`/`INDEX003` load) and `0x00412ac0`
  (the `0x00d53500` writer); `0x004003f4`/`0x004005f8` → `0x003fbed8`
  (POINT access path), `0x003fcbf0`, `0x003fd390` (both touch `0x00d53500`).
- **`0x00039d5c`, `0x00039e34`, `0x00039efc`, `0x00039f04`** — `{id, fn}`
  handler tables (users `0x0039cdcc`, `0x0039d18c`, `0x0039d2b8`,
  `0x0039d3e4`); entries reach the ADDRE path `0x003f56bc`/`0x003f51e0`
  through `0x003f5d98` in 3–4 calls and the POINT name lead `0x003d1150`
  through `0x003cd910` in 2.
- **`0x001796f8`** — entry `0x003f75e4` calls `0x0040b850`, the `MAPAL001`
  open path (C-4625).
- **No table holds a reader itself.** No aligned word in either area equals
  `0x003f5194` (POINT walk), `0x003fbed8`, `0x003f56bc`, `0x003f51e0`,
  `0x004125a8`, `0x0041c7dc` (chunk engine) or `0x003d1150`; they are called
  directly, below a table entry. `0x003f5194` and `0x0041c7dc` are reached
  from no table entry within four static calls.
- **sec1 `INIT`** holds 7 tables: the shell command table `0x0055ddfc`
  (`{name, fn, help}`, 39 rows, Shift-JIS help text) and three state x event
  matrices (`0x0055e348` 75 slots, `0x0055e4d0` 83, `0x0055e790` 35):
  `fn 0x003335c0` calls `table[*0x00618650 * 15 + event]` if non-NULL.
  The `Lv1_O`/`Lv2`/`Lv4`/`Lv1_D/TOP`/`Lv5` names (`0x0056084c…`) and the
  keyboard strings sit in data blocks with **no** code pointer; M3.11c's
  `0x005628e8` is a record of pointers into sec0 data, not a dispatch table.

### All 69 tables

| Area | Base VA | Stride | Slots (NULL) | START | Users (exact) | Users (row prefix) | Guessed role |
| --- | --- | --- | --- | --- | --- | --- | --- |
| sec0 | `0x000117a4` | 40 | 25 (0) | 20 | 7 functions | 15 functions | debug-shell commands `{id, fn, name[32]}` (`show srchinf!!`, `show route!!`, …) |
| sec0 | `0x0001d260` | 20 | 11 (0) | 8 | — | — | unknown |
| sec0 | `0x0001d368` | 20 | 4 (0) | 4 | — | — | unknown |
| sec0 | `0x0001d480` | 20 | 6 (0) | 4 | — | — | unknown |
| sec0 | `0x0001d520` | 20 | 14 (0) | 14 | — | — | unknown |
| sec0 | `0x0001d660` | 20 | 9 (0) | 9 | — | — | unknown |
| sec0 | `0x000380a0` | 12 | 9 (0) | 8 | — | — | unknown |
| sec0 | `0x00039d5c` | 8 | 26 (0) | 26 | — | `0x0039cdcc` | `{id, fn}` handlers; reaches the ADDRE path and the POINT name lead `0x003d1150` (C-3554) |
| sec0 | `0x00039e34` | 8 | 20 (0) | 20 | — | `0x0039d18c` | `{id, fn}` handlers; reaches the ADDRE path (`0x003f5d98`) (C-3554) |
| sec0 | `0x00039edc` | 24 | 15 (0) | 15 | — | — | unknown |
| sec0 | `0x00039efc` | 48 | 4 (0) | 4 | — | `0x0039d2b8` | unknown |
| sec0 | `0x00039f04` | 24 | 14 (0) | 14 | — | `0x0039d3e4` | unknown |
| sec0 | `0x00039fec` | 24 | 4 (0) | 4 | — | `0x0039d510` | unknown |
| sec0 | `0x00177fd4` | 8 | 43 (0) | 41 | — | `0x003ebee8` | unknown |
| sec0 | `0x00178c1c` | 8 | 7 (0) | 7 | — | `0x003f0368` | unknown |
| sec0 | `0x00178d64` | 8 | 20 (0) | 20 | — | `0x003f72e4` | unknown |
| sec0 | `0x001796c8` | 8 | 5 (0) | 5 | — | `0x0040335c` | unknown |
| sec0 | `0x001796f8` | 8 | 6 (0) | 5 | — | `0x004032e0` | `{id, fn}`; entry `0x003f75e4` calls the `MAPAL001` open path `0x0040b850` |
| sec0 | `0x0017a0a4` | 8 | 14 (0) | 14 | — | `0x004124dc` | **REFER/LCTBL message dispatcher** `{u16 msg, fn}`, 14 rows, msg `0x14cc…0x14f5` (C-3553) |
| sec0 | `0x0017ab38` | 4 | 20 (0) | 16 | `0x00419c38` | — | file-layer state × kind matrix (M3.26 positive control) |
| sec0 | `0x00185a28` | 16 | 6 (0) | 6 | — | — | unknown |
| sec0 | `0x00187ccc` | 12 | 11 (0) | 3 | — | — | unknown |
| sec0 | `0x00187d6c` | 12 | 11 (0) | 9 | — | — | unknown |
| sec0 | `0x00189fdc` | 8 | 7 (0) | 7 | — | `0x004b9174` | unknown |
| sec0 | `0x0018a01c` | 8 | 16 (0) | 15 | — | `0x004b9174` | unknown |
| sec0 | `0x0018a0ec` | 8 | 41 (0) | 41 | — | `0x004b9288` | unknown |
| sec0 | `0x0018a23c` | 8 | 29 (0) | 29 | — | `0x004b9370` | unknown |
| sec0 | `0x00191804` | 8 | 14 (0) | 14 | — | `0x004bd530` | unknown |
| sec0 | `0x001a6ccc` | 8 | 14 (0) | 14 | — | `0x004cdb64` | unknown |
| sec0 | `0x001cb83c` | 8 | 29 (0) | 28 | — | `0x004d0c98` | unknown |
| sec0 | `0x001cd214` | 8 | 8 (0) | 7 | — | `0x004d53c8` | unknown |
| sec0 | `0x001cdf44` | 8 | 4 (0) | 4 | — | `0x004dbebc` | unknown |
| sec0 | `0x001ce36c` | 8 | 5 (0) | 5 | — | `0x004dc08c` | unknown |
| sec0 | `0x001ce3e4` | 8 | 34 (0) | 34 | — | `0x004dc130` | unknown |
| sec0 | `0x001d69f4` | 44 | 3 (0) | 3 | — | — | unknown |
| sec0 | `0x001d6a54` | 8 | 5 (0) | 5 | — | — | unknown |
| sec0 | `0x001d6e24` | 52 | 3 (0) | 3 | — | — | unknown |
| sec0 | `0x0020618c` | 4 | 8 (0) | 8 | `0x0053a200`, `0x0053b598` | — | unknown |
| sec0 | `0x002064dc` | 4 | 7 (0) | 6 | `0x0053b870`, `0x0053babc` | — | unknown |
| sec0 | `0x00206624` | 4 | 5 (0) | 3 | `0x0053bb50`, `0x0053bbd0` | — | unknown |
| sec0 | `0x002066c8` | 4 | 10 (0) | 9 | 6 functions | — | unknown |
| sec0 | `0x00206bd8` | 4 | 4 (0) | 1 | `0x0053e018` | — | unknown |
| sec0 | `0x002080a8` | 4 | 7 (0) | 5 | `0x0053e624`, `0x0053e65c`, `0x0053eaa0` | — | unknown |
| sec0 | `0x00208168` | 52 | 5 (0) | 5 | — | — | unknown |
| sec0 | `0x00208348` | 4 | 8 (0) | 8 | `0x0053eefc`, `0x0053f14c` | — | unknown |
| sec0 | `0x0020852c` | 8 | 3 (0) | 3 | — | data `0x00208548` | unknown |
| sec0 | `0x00208574` | 8 | 4 (0) | 4 | `0x0053f390`, `0x0053f474` | — | unknown |
| sec0 | `0x002085cc` | 8 | 7 (0) | 7 | `0x0053f8d8`, `0x0053f908` | — | unknown |
| sec0 | `0x00208860` | 52 | 3 (0) | 3 | — | — | unknown |
| sec0 | `0x00208868` | 52 | 3 (0) | 3 | — | `0x0053f94c`, `0x0053f9b4`, `0x0053f9c4` | unknown |
| sec0 | `0x00208890` | 8 | 4 (0) | 4 | `0x0053fa08`, `0x0053fe78` | — | unknown |
| sec0 | `0x00208908` | 4 | 4 (0) | 4 | `0x0053ff34`, `0x0053ff58`, `0x00540538` | — | unknown |
| sec0 | `0x00208ab4` | 60 | 3 (0) | 3 | — | — | unknown |
| sec0 | `0x00208abc` | 60 | 3 (0) | 3 | — | `0x00540708`, `0x00540a14`, `0x00540a40` | unknown |
| sec0 | `0x00208ae4` | 4 | 3 (0) | 3 | `0x00540a98`, `0x00540b20`, `0x00540b30` | — | unknown |
| sec0 | `0x00208af4` | 8 | 3 (0) | 3 | — | — | unknown |
| sec0 | `0x00208b30` | 8 | 3 (0) | 3 | — | `0x00540b74`, `0x00540bfc`, `0x00540c0c` | unknown |
| sec0 | `0x00208b3c` | 8 | 4 (0) | 4 | — | — | unknown |
| sec0 | `0x00209894` | 4 | 7 (0) | 7 | `0x005416a8`, `0x00541984` | — | unknown |
| sec0 | `0x002098e4` | 4 | 7 (0) | 7 | `0x00541a10`, `0x00541c80` | — | unknown |
| sec0 | `0x0020a110` | 12 | 10 (0) | 10 | — | — | unknown |
| sec0 | `0x0024fef4` | 40 | 3 (0) | 3 | — | — | unknown |
| sec1 | `0x0055ddfc` | 12 | 39 (0) | 31 | — | `0x0032efa8`, `0x0032fe48` | shell command table `{name, fn, help}` (row 0 `help` → `0x0032fe48`), 39 rows; `0x0032efa8` passes `0x0055ddf8` to `0x0032fdf4` (C-3552) |
| sec1 | `0x0055e348` | 4 | 75 (38) | 37 | `0x003335c0` | — | state × event matrix, 5 × 15, `jsr table[state*15+event]` (C-3552) |
| sec1 | `0x0055e4d0` | 4 | 83 (45) | 38 | `0x00334b2c` | — | state × event matrix (same shape as `0x0055e348`) |
| sec1 | `0x0055e790` | 4 | 35 (20) | 15 | `0x00338224` | — | state × event matrix (same shape) |
| sec1 | `0x00561f80` | 4 | 11 (5) | 6 | `0x00377704` | — | unknown |
| sec1 | `0x005653f0` | 4 | 17 (12) | 5 | — | `0x004c6be8` | unknown |
| sec1 | `0x0056553c` | 12 | 5 (0) | 5 | — | `0x004bd83c`, `0x004bd8a4`, `0x004bd8e8`, `0x004da758` | unknown |

"unknown" means the role was not read; decoding what each callee does belongs
to the M3 family tasks. Excluded: tables in `.data` that is BSS (filled at run
time, e.g. `0x00d53500`), jump tables inside code (`braf`), C++ vtables whose
pointer is written by a constructor into BSS objects, and US2011 (the same scan
prints 150 tables there, not curated).

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

## The map-file layer running on a card (M9.44, EU2011 build A)
Measured by executing the layer in PySh4 against the factory EU card
(`tools/vcard_l3.py`, EXP-2026-11-19-M9.44-virtual-card, C-4630–C-4655). The
section above names the functions; this one says what they do when they run.

### Mount sequence
| Step | Call | What the firmware does on the card |
| --- | --- | --- |
| init | `0x00417924()` | builds tables and pools, state `0/0`; touches no file |
| event 1 | `0x00419c38(0)` → `0x00419ca0` | opens `\SystemSD\CMP.LST` twice, reads 19 bytes (the prefix `\SystemSD\REFER001\`), opens `MMAIN001.DAT`, reads exactly `0x1000` bytes into `0x00e23cc0`; state `1/1` |
| event 2 | `0x00419c38(0)` → `0x00419d24` | opens `DRSTR001.DAT`, reads it in **one** `fread` of its whole size (EU: `0x2ec0`), builds the volume table, writes recognition status 2; state `2/2` |
| later | `0x00419c38(n)` → `0x00419df8` | state-2 worker: serves queued read requests |

The state pair is `*0x009cfce0` (state machine) and `*0x009cfce4` (mount); `2/2`
is "mounted". The volume root is the wide string at `0x00049fd4`,
`\SystemSD`. Every file name the layer opens is that root plus a path from the
volume table.

What the mount checks, by experiment (each row is one changed card):

| Change | Result |
| --- | --- |
| `MMAIN001.DAT` absent | not mounted (`0/1`), recognition status 1, a retry timer is set |
| `MMAIN001.DAT` byte 0 flipped | mounted; the header bytes are not checked at mount |
| `MMAIN001.DAT` truncated to `0x800` | not mounted (`0/1`), error log from `0x0041a4c4`: the read must return `0x1000` bytes |
| `CMP.LST` absent | mounted, 2 error-log calls; afterwards **no** `.cmp` file opens (the layer looks for the plain `X.DAT` and retries forever) |
| `DRSTR001.DAT` absent | mounted by a **fallback**: `0x00418748` walks the card with `FindFirstFileW("\SystemSD\*")`, 40 directories, a different table (ids follow directory order) |
| `DRSTR001.DAT` truncated to `0x800` | not mounted (`1/1`), error log from `0x00419048` |
| root record: listing offset (`+0x24`) changed | not mounted (`1/1`), error log from `0x00419472` |
| root record: entry count (`+0x18`) changed 11 → 10 | mounted, one file fewer |
| byte `0x2f` (`/` + 0x2f) or a pad byte flipped | mounted, same table: not read |
| a directory record's name (`+0x28`, `BICON001`) flipped | mounted, same table: the name is taken from the parent's listing entry |
| a listing entry's name (`0x640`) flipped | mounted, different table |

### The volume table
After mount, `*0x009cfcd4` is the directory count (EU: 40) and `0x00e25420`
holds 36-byte directory records: name[20], `u16` id, `u16` parent id, `u16`
entry count, pad, `u32` size, `u32` pointer to 28-byte entries (name[20],
`u16` id, `u16` kind (2 = directory), `u32` size). A file is addressed as
`(directory id << 16) | file id`; both ids come from `DRSTR001.DAT` (EU:
`MAPAL001` = 3, `REFER001` = 6, so `MAPAL001/B28R070R.DAT` = `0x00030001`).
**The ids are positions**: a `DRSTR` rebuilt without the reference order
mounts, but gives the same files other ids. A writer must keep the order.

### The read API
`0x0041841c(file id, request *)` queues a read (it tail-calls `0x004181d8` with
flag 1). The request record:

| Offset | Field | Constraint (else `-11`) |
| ---: | --- | --- |
| +0 | destination buffer | non-zero, 4-aligned |
| +4 | start sector (2,048 bytes) | |
| +8 | byte offset | folded into the sector; the remainder must be 4-aligned |
| +12 | length | non-zero, multiple of 4, at most `0x100000` |
| +16 | kind | 1, 2 or 3 |
| +20 | byte order | 0 = swap every byte pair after the read, 1 = as stored |
| +32 | reply task | non-zero |
| +36 | out: request serial | |

Return `0` queued, `-10` queue full, `-11` refused (line number in the error
log says which check; range check `0x00418150`: `sector·2048 + offset + length`
must not exceed the file size in the volume table), `-12` not mounted. The
queued request is announced with `OSM_TaskSend(*0x011fffb8, …)`; the worker
`0x00418634` pops it, opens the file by name (`0x00417fe0` → `0x00418dfc`),
seeks, reads, and `0x00417eac` sends the completion to the reply task: message
id `0x04a0` at +8, status at +12, buffer at +16, length at +20. A failed open
does not complete: the request goes back on the queue.

**The byte swap asked about in M3.11b is here**: `0x00417eac` swaps each byte
pair of the buffer when request word +20 is 0 and the status is 0. With word
+20 = 0 the bytes of `POINT010.DAT` arrive pairwise swapped, with 1 as stored.

### The compressed-file layer
`0x0041b780(path, flag)` decides by the `CMP.LST` prefix (`0x0041c2e0`): a path
outside it is a plain `fopen`; a path under it opens `X.DAT.IND` and
`X.DAT.CMP` (upper-case extensions appended to the table's name), reads the
16-byte `.ind` header, then the offset table in reads of up to 2,048 bytes, then
only the compressed chunks that cover the request, and inflates them with the
firmware's zlib. The `.ind` field at +4 (total compressed size) is not compared
with the `.cmp` file's size: with that field lowered by 169 the first 64 KiB of
`ADDRE001.DAT` still read correctly and only the read that reaches the last
chunk fails (hypothesis: the field is the end of the last chunk). A changed
chunk offset or a changed compressed byte fails the read (error log from
`0x0041b9d2`), and the request is re-queued.

## Who names which file (M3.28, EU2011 build A)
From `tools/name_loaders.py` (static) and `tools/vcard_l3.py lookup` / `trace`
(the firmware's own code run on the EU card); EXP-2026-11-19-M3.28-file-openers,
C-4660–C-4679.

### The path from a name to bytes
| Step | Function | What it does |
| --- | --- | --- |
| path → directory id | `0x00409cc8(start id, path)` | walks the path components against directory entries with `strncmp`; a leading `/` or `\` is skipped |
| directory record | `0x004192c0(directory id, out *)` | returns the 36-byte record of the volume table |
| name → file id | `0x0040b358(directory path, file name)` | `strcmp` (case-sensitive) of the name with every non-directory entry; returns `(directory id << 16) \| file id` or `-1`. 13 callers: the openers below |
| range clamp | `0x00409ba0(file id, request *)` | length 0 becomes the file size, a length past the end is cut, a start past the end is `-1`. No I/O |
| read request | `0x003f6c88(slot *)` | builds the 40-byte request (word +20 stays 0, so the data comes back byte-swapped), calls the clamp and then `0x0041841c`; the only caller of the read API |
| slot fill | `0x003f6e40(tag, control block *, slot *)` | destination = block +20, sector = block +32 `>> 3`, offset = (block +32 `& 7`) `<< 8`, length = block +24 `<< 1`, file id = block +28: a client positions in 256-byte units and counts in 16-bit words |
| wrappers | `0x003f7384` (37 callers), `0x003f73dc` (11), `0x003f7480` (1) | take a free slot (`0x003f6e90`), fill it, issue the request |

So every map file a client reads goes: opener (name → id into a control block)
→ one of three wrappers → `0x003f6c88` → `0x0041841c` → the map-file task.

### Openers: one row per caller of the resolver
"Run" = what `vcard_l3.py trace` showed on the EU 2011 card; "static" = read
from the pool literals only.

| Opener | Names it builds | Evidence | Called by | Read requests one call away |
| --- | --- | --- | --- | --- |
| `0x003fbed8(ctx, bits, n)` | `REFER001/` + prefix + two digits of `n` + `.DAT`; prefix by the search type at ctx +124: 1 → `POINT0`, 2 → `ADDRE0`, 3 → `FRWAY0`, 4 → `INTER0`, 11 and 12 → `ZCODE0`; type 1 with ctx +104 = `0x14e4` → `RDSTM001/LCTBL0nn.DAT`; `REFER002` when a ctx flag is set (static) | run: `POINT001/003/030`, `ADDRE001/003/030`, `FRWAY003/030`, `INTER001/003/030`, `ZCODE001/002/003`, `LCTBL001` all resolve; `FRWAY001` is not on the card | 14 functions `0x003fc40c…0x004004e0` | `0x003fc0ec`, `0x003fc518` |
| `0x003f1640(n)` | `REFER001/ICADM0` + two digits of `n + 1` + `.DAT` | run: `n = 7` → `ICADM008.DAT`, id `0x00060044` | `0x003f2cc0` | `0x003efe10`, `0x003f0400`, `0x003f2828` |
| `0x003f2cc0` | `REFER001/ICODE001.DAT`, then `ICADM` through `0x003f1640` | static (the run needs search state) | `0x003f2df8`, `0x003f2f98`, `0x003f30ac` | `0x003efe10`, `0x003f0400`, `0x003f2828` |
| `0x004011a0(n)` | `REFER001/ADDRE0` + two digits of `n + 1` + `.DAT` | run: `n = 12` → `ADDRE013.DAT`, id `0x0006000d` | `0x00401ff8` | `0x00401ff8` |
| `0x00410500(n)` | `/REFER001/POINT` + three digits of `n` + `.DAT` (template in `.data`) | run: `n = 5` → `POINT005.DAT`, id `0x00060084` | `0x00410760` | `0x0040a558` |
| `0x003f7b20` | `REFER001/` + a name from its caller | static | `0x003f7b54`, `0x003f7c38` | the two callers |
| `0x0040b3e0` | the data-kind table `0x00179cf8` (18 rows of directory, file, `CDROM.DAT`) | run: resolves `RDSTM001/RDSTM001.DAT`, `REFER001/POINT001`, `ADDRE001`, `ICODE001`, `INTER001`, `ICADM001` (found) and `REFER001/REFER001.DAT` (not on the card), then stops on a null argument | `0x0040b850` | none: a presence probe |
| `0x004125a8` | `RDSTM001/LCTBL001.DAT`, `REFER001/INDEX003.DAT`, the `CHARA*`/`INDEX00n` table `0x0017a054` | static (the run stops at the import `OSM_isSender`) | `0x00413a6c` | none |
| `0x00413b90` | `BICON001/BICON001.DAT`, `BLND_MRK.DAT` | run: resolves `BICON001.DAT` to `0x00020001`, calls the clamp | `0x003f6b84` | itself |
| `0x00403828`, `0x004042ac`, `0x00404560` | `MSIZE001.DAT` and the table `0x00179730` (`SOUND001.DAT`, 19 × `DFRMR0nn.DAT`) | static | `0x004038b0`, `0x004039c0`; `0x00404308`; `0x00404770` | `0x004038b0`; none; `0x004043cc`, `0x00404560` |
| `0x003f817c` | no name literal: both strings come from its caller | static | `0x003f82e8` | none |

Not through the resolver: `MMAIN001.DAT` (`0x0041a438`), `DRSTR001.DAT`
(`0x00419684`), `CMP.LST` (`0x0041ba90`) are opened by path during the mount;
`MAPAL001/LEV3456R.DAT` is named in `0x0040a014` (it compares the name with
`strcmp`); tile names `BxxRyyR.DAT` have no string.

### Names in the firmware against files on the EU 2011 card
`vcard_l3.py lookup` of all 52 file-name strings in seven directories: **12
resolve** (`ADDRE001`, `BICON001`, `COORD001` in `REFER001` and `REFER002`,
`ICADM001`, `ICODE001`, `INTER001`, `LCTBL001`, `LEV3456R`, `MMAIN001`,
`POINT001`, `RDSTM001`, `ZIPFR001`), **40 do not**: `BLND_MRK`, `CDROM`,
7 × `CHARA*`, 19 × `DFRMR0nn`, `ETCID001`, `RNDID001`, 6 × `INDEX00n`,
`MSIZE001`, `REFER001.DAT`, `SOUND001`, and `DRSTR001.DAT`, which is not listed
in itself. A generated card needs none of the other 39.

`COORD001.DAT` and `ZIPFR001.DAT` exist on the card and have a name string but
no function loads the string and no table holds it: `Navi.exe` does not open
them by name. (Lookup tried: pool literals, rodata tables, and the built names
of the six `REFER` prefixes.)

## The data-access task (M3.25, EU2011 build A)
> **Status:** `VERIFIED` (run in PySh4 on the EU 2011 card, `tools/datask_l3.py`)
> for the tables, the handlers that ran and the bytes they loaded; `OBSERVED`
> for roles named from one run. EXP-2026-11-19-M3.25-tile-reader-entry,
> C-4680–C-4699. All VAs are EU2011 build A.

The client of the map-file layer is one task. Its entry `0x003ebfb4` calls
`0x003f6908()` and `0x003eba78()` (memory pools, saved settings, tables) and
then loops: receive a message, call the dispatcher `0x003ebee8(message)`.

### Messages
The dispatcher compares the `u16` at message `+8` with a 43-row table at data
VA `0x177fd0`: `{u16 id, u16 defer flag, u32 handler}`. A row with the defer
flag set is queued by `0x003ebd44` while the map is not ready and replayed by
`0x003ebf54`. `python3 tools/datask_l3.py tables IMG256` prints all rows; the
ones this page uses:

| Message | Handler | Role |
| --- | --- | --- |
| `0x07d0` | `0x004032e0` | second table at data VA `0x1796f4`, keyed by the `u16` at `+10`: sub `100` → `0x003f75e4` (map database ready: start the mount) |
| `0x04a0` | `0x003f72e4` | a read finished (the map-file layer's completion, C-4636) |
| `0x14b5` (deferred) | `0x004066ac` | reaches `0x0040d4a0` → `0x0040b6b0` → the tile read issuer `0x0040a474`; body not decoded |
| `0x00a0` | `0x0040335c` | second table at data VA `0x1796c4` (5 rows) |

### The mount, as run
`0x003f75e4` → `0x0040b850(message)`: `0x0040b258` reads the volume header
from the object store (`OBJ_DiscInfo_readDiscVol`), takes the map version
(`0x802` on this card, stored at data VA `0xd8ad20`) and date; `0x0040b3e0`
scans `MAPAL001` with `0x0040a108`/`0x0040a014` (46 tile files);
`0x0040b5ac` asks for the first `0x1000` bytes of `LEV3456R.DAT`, of one
`BxxRyyR.DAT`, of `RDSTM001.DAT` and of `POINT001.DAT`. Every later request
is made by the handler of an earlier completion.

### Read completions: tag class → handler
`0x003f72e4` looks the request tag (`u16` at message `+10`) up in a 20-row
table at data VA `0x178d60`: `{u16 class, u16 0, u32 handler}`; the first row
with a non-zero class equal to the tag in bits 8..14 wins. The handler gets
the message in `r4`; its return value is not used.

| Class | Handler | Seen serving |
| --- | --- | --- |
| `0x01`, `0x02` | `0x0040b8b4` | first `0x1000` bytes of a file (`MAPAL001`, `RDSTM001`, `POINT001`) |
| `0x06` | `0x0040c308` | tile section table (one per section, at the address in the header's section list) |
| `0x07`, `0x08` | `0x0041597c` | tile directory (the slot table of one parcel group) |
| `0x0d` | `0x003f72cc` | `REFER001/ICODE001`, `ICADM001` data |
| `0x09` | `0x00404ee4` | not run |
| `0x0a` | `0x004030f0` | not run |
| `0x0b` | `0x004007bc` | not run |
| `0x05` | `0x00404854` | not run |
| `0x10`, `0x11` | `0x003f4ecc` | not run |
| `0x15` | `0x003efdb4` | not run |
| `0x03` | `0x00404ebc` | not run |
| `0x1d` | `0x003f858c` | not run |
| `0x1b` | `0x00403b98` | not run |
| `0x20` | `0x003f7f94` | not run |
| `0x23`, `0x25` | `0x00413b64` | not run |

What the tile handlers do with the buffer is in
[map-tiles.md](map-tiles.md#reader-entry-the-read-completion-handlers-m325-eu2011-build-a).

### What the run needs that the unit provides
Models in `tools/datask_l3.py`: semaphores, `OSM_MemSize`/`OSM_MemGet` (one
4 MiB area), `OSM_SramGet`/`OSM_SramCheck` (empty, reported not valid),
`OBJ_DiscInfo_readDiscVol` (the volume header the map-file layer published),
eight `OBJ_CarPos_*`/`OBJ_Event_*`/`OBJ_RoutePntTbl_*` calls that return 0.
The two task-id globals (data VAs `0x11fff58`, `0x11fffb8`) are written by
the tool. One message is sent to a task that is not part of the run
(`0x1507` sub 1, receiver id 0); the mount state stays 2.
