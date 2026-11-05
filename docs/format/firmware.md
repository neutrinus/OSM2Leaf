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
- Section tables appear at `0x374000` and `0x3e0060` with 24-byte records and
  PE flags (`0x60000020`, `0x40000040`). Decoding them is the next step.

`HCXCmp`/`hcxcmp` strings exist, but no public documentation was found and the
map `.DAT` payloads themselves use plain zlib. Treat `HCXCmp` as a
firmware-side library, not as the map compression.

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

1. Decode the ROM section table (`0x374000`, `0x3e0060`) to get a stable
   `VA − rva` per module.
2. Find `inflate`/`uncompress` and its callers; expect references to
   `MAP_DATA READ START` and a buffer sized from `.ind`.
3. Brute-force `SUM4` against builds A, B and C.
4. Diff builds A/B/C to find the unit-ID → build selection logic.
5. Only then decide whether a custom QEMU machine is worth the effort.
