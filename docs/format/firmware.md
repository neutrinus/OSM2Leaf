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

- Ghidra project: `/tmp/opencode/research-firmware/ghidra-project`, processor
  `SuperH4:LE:32:default`, base `0x02200000`.
- For the map module's data, `VA = file_offset + 0x02000000` (verified with 21
  independent pointer literals). Code literals use at least one other delta,
  so the ROM has section-based (not linear) address placement. This is the
  main caveat for further analysis.
- **Verified map path:** the function at `0xc438a4` builds `"\CMP.LST"`, walks
  the UTF-16 directory string and opens `\SystemSD\REFER001\`. The map
  module's string pool at `0xdf6000`–`0xdfb000` documents `MESH_ID`/`DIVID`
  tile reads, `.cmp`/`.ind`, `HCXCmp` file descriptors and map filenames.
### Section table is a dead end

The 24-byte records at `0x374000`/`0x3e0060` are `o32_rom`-shaped (a clean
record at `0x3221b0` has `psize == round_up(vsize, 0x200)`), but the table is
**not usable as a file map**: its `dataptr` fields point into pure `0xff`
fill (stale build-time offsets), and consecutive records do not share a
`realaddr − rva` delta. Do not build on it.

### Two deltas that do work

For the map module:

- code: file `0xc00000–0xc4b000` ↔ VA `0x02e00000–0x02e4b000`,
  `VA = file + 0x02200000`;
- `.rdata`: file `0xdf6000–0xe10000`, `VA = file + 0x02000000`.

Ghidra recovered 136 functions at `0x02e00000` and 84 at `0x02e10000`; code
density collapses after `0xc4b000`.

The deltas are **local to this module**, not global. Other modules map the
same shared `.rdata` at other VAs. A 10-slot pointer array at
`0xa9cf8c..0xa9cfb8`, minus `0x02200000`, resolves to real UTF-16 strings
(`\UserSD\VER_INFO\HDD_INFO.TXT`, `SD Import: userdata_type is different
Sys[0x%x] SD[0x%x]`, …). Accept a new module delta only when at least four
pointer slots resolve to real strings.

### Reader-related functions found

| Address | Role |
| --- | --- |
| `0xc438a4` | opens `\CMP.LST` (only such site) and returns the handle |
| `0xc42520` | file-descriptor dump; `+0xC4` is a **type tag** (switch 7…15), not `hcxcmp` |
| `0xc426a4` | directory-info dump (`dir cnt`, `file cnt`) |
| `0xc48380` | writes message-catalogue strings (`MAP_DATA READ`, `DBgetLnk`, …), **not** a DB vtable |
| `0xc0ebf8` | allocates `0x1ac` (the level-table size) |

**Retraction:** `obj+0x78…+0x9c` is a **message catalogue**, not a vtable; every
stored value is a string pointer. The four functions `0xc412ca`/`0xc42a7a`/
`0xc42ba6`/`0xc42e30` are read-only classifiers, not fd writers. The struct is
a state descriptor keyed by `(0xAC,0xB4,0xB8)`; `+0xC4` is a separate type tag.
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

**Next anchor:** the ROM module table at `0x15271c8`
(`NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviStateCC.dll` back-to-back as
16-byte-stride names), a self-name literal
(`0x15271c8 − filebase + Vt`), and the shared-`.rdata` clusters.

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

The image embeds a byte-identical `HDD_INFO.TXT` at `0x06000000`; it is
probably the system-side reference. The exact line↔field mapping is unknown.
The comparison function is not located; the `shll2`-scaled index into
`0xa9cf8c` is missing, and the best candidate caller is `0x132e06c`
(delta `0x2180000`, unproven). The literal `"DIFFERENT MAP CODE"` is absent
from build A; nearest hits are unrelated.

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
round-trip validator for the whole-card feedback loop.

## Next steps

1. **Decode the ROM module table at `0x15271c8`** (16-byte-stride names).
   Success = `{name, VA, size}` with a 64 KiB-aligned VA matching a
   prologue-dense file range.
2. **Self-name anchor:** the literal pointing at `0x15271c8` is
   `0x15271c8 − filebase + Vt`; score `Vt` against string-pointer clusters.
3. **Shared-`.rdata` clusters:** enumerate them under the known deltas; `Vt`
   follows if `.text` is adjacent to `.rdata` in VA.
4. Then re-run the reader search and the format cross-check.
5. Only then decide whether a custom QEMU machine is worth the effort.
