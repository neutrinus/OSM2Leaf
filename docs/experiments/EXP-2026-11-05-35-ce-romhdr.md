# EXP-2026-11-05-35: The CE ROM header (ROMHDR) and module TOC are present

- **Status:** done (positive; supersedes the "no XIP table" negative)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
  (full image SHA-256
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`);
  only the first 32 MiB were read (HTTP Range `0-33554431`), SHA-256 of
  that prefix
  `70dee680a0f2a8124fc563b5897e3ef76e6e624f713775a7b1654e785cd25fb3`
- **Claims:** C-516…C-523; retracts C-380, C-381; weakens C-382…C-386
- **Supersedes:** EXP-2026-11-05-24 (XIP part), EXP-2026-11-05-22
  (non-injective VA map)
- **Related:** EXP-2026-11-05-33/34 (`tools/ce_rom_parse.py`) reached the same
  TOC independently; this record adds the per-module/section checks and the
  cross-checks against the older anchors
- **Superseded by:** none

## Question

Is `ECEC` at `0x200240` the standard Windows CE ROM signature at
image start + `0x40`, so that `pTOC` gives a real `ROMHDR` and module TOC?

## Hypothesis

CE image start = `0x200200` (the Clarion wrapper header is `0x200` bytes).
`ECEC` is followed by `pTOC = 0x8e232978` and the `ROMHDR` offset from
image start `0x01751978`, so `ROMHDR` is at file `0x01951b78` and
`file = VA − 0x8cae1000 + 0x200200`.

## Inputs

| Item | Value |
| --- | --- |
| Image / file | first 32 MiB of the EU 2011 image |
| Offset(s) | `0x200240` (`ECEC`), `0x01951b78` (`ROMHDR`) |
| Tool version | `python3 tools/cerom.py` (stdlib only), this commit |

## Method

```bash
curl -r 0-33554431 -o head.bin \
  https://files.viaaq.eu/sd-images/LEAF_2011-2012_QSD-309-101_navi158_eu.img
# or: dd if=IMAGE of=head.bin bs=1M count=32
python3 tools/cerom.py head.bin romhdr
python3 tools/cerom.py head.bin modules
python3 tools/cerom.py head.bin files
python3 tools/cerom.py head.bin sections OBJDLL.dll
python3 tools/cerom.py head.bin va2file 0x03498d48
```

## Observations

### ECEC block

```
0x200240  45 43 45 43  78 29 23 8e  78 19 75 01   "ECEC" pTOC=0x8e232978 off=0x01751978
```

`pTOC − off = 0x8cae1000` = VA of image start `0x200200`.

### ROMHDR at file `0x01951b78`

| Field | Value | Check |
| --- | --- | --- |
| `dllfirst` / `dlllast` | `0x01a701a8` / `0x01f90000` | DLL data band, matches RW `realaddr` `0x01e5…0x01e7` |
| `physfirst` | `0x8cae1000` | = image VA base, exactly |
| `physlast` | `0x8e233c88` | > `pTOC`; image ends at file `0x1953e88` (data stops at `0x1953000`) |
| `nummods` | `149` (`0x95`) | plausible |
| `ulRAMStart` / `ulRAMFree` / `ulRAMEnd` | `0x89e40000` / `0x89e73000` / `0x8cae1000` | RAM ends where the ROM begins |
| `ulCopyEntries` / `ulCopyOffset` | `0` / `0` | no copy section in this region |
| `numfiles` | `1` | |
| `ulKernelFlags` | `0x2` | |
| `ulFSRamPercent` | `0x28` | |
| `usCPUType` | `0x01a6` | `IMAGE_FILE_MACHINE_SH4` |
| `pExtensions` | `0x880030a4` | points into a different (kernel) region |

Raw bytes:

```
a801a701 0000f901 0010ae8c 883c238e 95000000 0000e489 0030e789 0010ae8c
00000000 00000000 00000000 00000000 01000000 02000000 28000000 00000000
00000000 a6010000 a4300088 00000000 00000000
```

### TOC and FILES

- All **149/149** `TOCentry.lpszFileName` pointers resolve, through the
  formula, to clean NUL-terminated ASCII names. First: `gwes.exe`,
  `fatfsd.dll`, `diskcache.dll`, `fatutil.dll`, `shell.exe`, …; last:
  `EvNoticeCC.dll`, `InfoBarCC.dll`, `Vehicle.exe`, `multiskin.dll`.
  All `Navi*` modules, `Navi.exe`, `OBJDLL.dll`, `STDDLL.dll`,
  `NaviStateCC.dll`, `VerInfoCC.dll`, `BT_MGR.dll`, `oleaut32.dll` are present.
- `FILESentry[0]`: `ReleaseMain.skn`, 8224 bytes, at file `0x194fb58`.
- `e32_rom` is 112 bytes (layout with `e32_timestamp`); `o32_rom` 24 bytes.
- 527 `o32` sections, **245 with `IMAGE_SCN_COMPRESSED`** (`0x2000`), all of
  them writable data / RW sections. Every `o32_dataptr` is inside
  `physfirst…physlast`.
- `nk.exe`, `coredll.dll`, `filesys.exe`, `device.exe` are **not** in this
  TOC; there is only one `ECEC` in the first 32 MiB. Imports name
  `COREDLL.dll`, `Errlogdll.dll`, `SYS_INF.dll`, `commondll.dll`, which must
  live in another XIP region (kernel region, `pExtensions` in `0x88…`).

### Cross-check against earlier, independently derived anchors

| Earlier anchor | TOC result | Agrees? |
| --- | --- | --- |
| OBJDLL VA base `0x03480000`, file base `0x7dd200` (EXP-23) | `vbase 0x03480000`, `.text` at file `0x7de200` = base + `0x1000` | yes |
| `MAL_DataVol_getOffset` file `0x7f5f48` ↔ VA `0x03498d48` | `va2file(0x03498d48) = 0x7f5f48` (OBJDLL) | yes |
| OLEAUT32 `Vb = 0x03930000` | `vbase 0x03930000` | yes |
| VerInfoCC VA `0x031e0000`, file base `0xa15200` | `vbase 0x031e0000`, `.text` at `0xa16200` | yes |
| NaviStateCC file base `0xc32200` | `.text` at `0xc33200`, `vbase 0x02df0000` | yes |
| iPodCC file base `0x1709200`, link space `0x0260xxxx` | `.text` at `0x170a200`, `vbase 0x02620000` | yes |
| TFAT file base `0x28e200` | module is `fatfsd.dll`, `.text` at `0x28f200` | yes (name differs) |
| `0x6faeb0` is a Bluetooth/OPP handler (EXP-29) | `0x6faeb0` is in `BT_MGR.dll` `.text`, VA `0x03686cb0` | yes |

### Previously unresolved addresses, now resolved

| Address | Resolution |
| --- | --- |
| VA `0x0367b180` ("collision", C-384) | `BT_MGR.dll` code, file `0x6ef380`, starts with an SH-4 prologue (`862f 962f 224f`). File `0xe7b180` (the UTF-16 string) is `Navi.exe` VA `0x001fcf80`: different module, no collision. |
| VA `0x0369d400` ("UNMAPPED", C-385/C-386) | `BT_MGR.dll` file `0x711600`: an import thunk `mov.l @(4,pc),r0; jmp @r0` → IAT slot `0x01e72074` = BT_MGR import `COREDLL.dll` ordinal **719**. |
| `0x2e0xxxx` "thunk area / unknown shared library" (C-23x/C-25x) | `0x02df0000…0x02e0f000` is `NaviStateCC.dll` itself (e.g. `0x2e00eb8` → file `0xc430b8`). |
| `0x1d0f8a8` "RAM BSS never written by ROM" | inside `NaviStateCC.dll`'s **compressed** RW data section (`realaddr` `0x01d0…`): initialised data the loader decompresses. |
| `0x1ab9000` "navi IAT" | `UsbAudioCC.dll` compressed RW section. |
| "map module `.text` `0xc00000–0xc4b000`" | spans **three** modules: `NaviSetCC.dll`, `NaviDrawCC.dll`, `NaviStateCC.dll`. |
| `0x171e9e8` "shared COM helper" | `UsbAudioCC.dll` `.text` (VA `0x026047e8`). |
| "tail table" `0x1951ee0`, "RAM copy list" `0x1952b00` | both inside `TOCentry[149]` (`0x1951bcc–0x1952e6c`): kernel-space pointers, 2011 `ftTime`, sizes. |

### The real HDD_INFO / SD Import references are in `Navi.exe`

The UTF-16 `HDD_INFO.TXT` and `SD Import: …` strings (file `0xe5338e…`) are
in `Navi.exe` (`vbase 0x10000`, `.text` at file `0xc8f200` = VA `0x11000`).
Scanning `Navi.exe` `.text` for absolute literals to those string VAs:

| Literal at file | VA | → string |
| --- | --- | --- |
| `0x1165f28` | `0x004e7d28` | `\UserSD\VER_INFO\HDD_INFO.TXT` (`0x1d51a8`) |
| `0x1165f2c` | `0x004e7d2c` | `\SystemSD\VER_INFO\HDD_INFO.TXT` (`0x1d5168`) |
| `0x1166784…0x1166798` | `0x004e8584…` | `destination_id`, `manufacturer_id`, `userdata_type`, `finished not found`, `application type not correct` |
| `0x1167b5c…0x1167b70` | `0x004e995c…` | the same five messages (second comparator) |

## Interpretation

- **FACT:** `ECEC` at `0x200240` is the standard CE ROM signature; the CE
  image starts at file `0x200200` with VA `0x8cae1000`, and
  `file = VA − 0x8cae1000 + 0x200200` for the whole region.
- **FACT:** `ROMHDR`, 149 `TOCentry`, `e32_rom`/`o32_rom` and one
  `FILESentry` are intact and give exact per-section `o32_realaddr` (VA) and
  `o32_dataptr` (file) for every module in this region.
- **FACT:** the earlier per-module anchors that survived (OBJDLL, OLEAUT32,
  VerInfoCC, NaviStateCC, iPodCC) agree exactly with the TOC.
- **FACT:** the "builder" chain `0x6fab2c → 0x6faeb0 → 0x6fb05c` is in
  `BT_MGR.dll`; the `HDD_INFO` and `SD Import` strings are referenced from
  `Navi.exe` pools at VA `0x004e7d28` and `0x004e8584`/`0x004e995c`. The old
  link between them (data delta `0x02800000`) was a coincidence.
- **OBSERVED:** about half the sections are compressed RW data. This explains
  why RW globals looked "never written" and why some "tables" pointed into
  meaningless bytes.
- **HYPOTHESIS:** the kernel region (`nk.exe`, `coredll.dll`, `filesys.exe`)
  is a second XIP region outside this ROM (its `pExtensions` is `0x880030a4`);
  it is needed to name COREDLL ordinals such as 719.
- **UNKNOWN:** the CE ROM compression format of the `0x2000` sections (likely
  the standard CECompress/LZX "romimage" format; not tested).

## Conclusion

C-380 and C-381 are **retracted**. The address problem that blocked the
firmware track since EXP-22 is solved statically. `tools/cerom.py` provides
`romhdr`, `modules`, `files`, `sections`, `va2file`, `file2va` and raw
`extract`. `AGENTS.md`, `docs/format/firmware.md` and
`docs/research/roadmap.md` are updated.

## Follow-ups

- [ ] Repeat for builds B (`0x3e00000`) and C (`0x5200000`) and the copy of A
  at `0x2000000` (needs bytes beyond 32 MiB).
- [ ] Locate the kernel XIP region (`pExtensions 0x880030a4`) to name COREDLL
  ordinals (e.g. 719 behind `0x0369d400`).
- [ ] Decompress the `IMAGE_SCN_COMPRESSED` sections; rebuild each module as
  a PE or a Ghidra memory map (TODO Step 2).
- [ ] Disassemble around the `Navi.exe` pools `0x004e7d28` and
  `0x004e8584`/`0x004e995c`: these are the real `HDD_INFO` reader and
  `SD Import` comparator candidates.
- [ ] Re-check the `o32_rom`-shaped records at `0x374000`/`0x3e0060` and C-180,
  C-234, C-262 against the TOC.
