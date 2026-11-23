# Unit flash files for the emulator

Two things live here: the unit's kernel image NK1 (vendor code, an owner's
exception) and three files that make a complete, anonymous flash image
around it (M6.24). Together they let `-M ze0` run with no dump of a real
unit:

```bash
python3 tools/ze0_launch.py --card CARD.img --flash anon      # builds it for you
python3 tools/unitflash_anon.py build -o flash-anon.bin        # or build it by hand
```

## Kernel image NK1 (`nk1-QY7200ND.bin`)

**Exception to the no-vendor-data rule, decided by the repository owner
(Marek, 2026-11-22, M8.C1k): this directory holds proprietary firmware so
that `-M ze0` can be started without a dump of one's own unit.** Nothing
else from the unit dump is committed.

## What it is

The Windows CE XIP image that lives in the head unit's own NAND flash, not
on the map card. Image A on the card (Navi.exe, AuiApp and the controls)
imports modules that are only here, for example `HCXLog.dll`,
`HCXMemory.dll` and `AppTimerDll.dll`.

| field | value |
| --- | --- |
| file | `nk1-QY7200ND.bin`, 2 939 624 bytes |
| SHA-256 | `b4b3542bb95d336c55ed11e1a4854be2c5f3dce1b60e074629d2b185f3b9fb00` |
| source | LeafSDTools NAND dump (8 MiB) of a US LEAF 2011–2012 unit QY7200ND, Product ID `10 20 02 12`; bytes `0x40000`..`0x30dae8` |
| layout | `ECEC` at +0x40; ROMHDR at file +0x18e314; VA `0x88000000`..`0x882cdae8` |
| content | 51 modules, 10 files (`cerom.py firmware/unit-flash/nk1-QY7200ND.bin modules`) |

Modules: `nk.exe`, `coredll.dll`, `filesys.exe`, `device.exe`, the driver
set (`anwdrv.dll`, `CAN.dll`, `gdisubdrv.dll`, `SDHC.dll`, `flash.dll`,
`VSram.dll`, `serial_scif.dll`, …), `HCXLog.dll`, `HCXMemory.dll`,
`AppTimerDll.dll`, `Antitheft.exe`, `Camera.exe`, `Failsafe.exe`,
`DrawOi.exe`. Files: `boot.hv`, `default.hv`, `user.hv` (factory registry
hives, built 2011), `initobj.dat`, `initdb.ini`, `wince.nls`, a font and a
default image. `Cws_Apl.dll` is not in NK1.

## What is not here, and why

- The rest of the NAND (boot loaders at 0x0–0x3ffff, the regions after NK1,
  the crash log), and the real `SRAM`, `VFlash` and `PROD` of the unit.
  `PROD` holds the card-lock password and the serial; `SRAM` and `VFlash`
  hold phone books, call lists, destinations and positions. The `*-anon.bin`
  files below replace them.
- Before committing, the image was searched for the unit's serial number,
  the 4-byte unit key, the lock-password tail and VIN-shaped strings; none
  occur (M8.C1k).

## Use

```bash
python3 tools/ze0_ipl.py patch archive/head256.img -o ipl.txt \
    --prefer-app auiapp.exe,auirtdll.dll --copy-dlls unitflash
```

`--copy-dlls unitflash` copies the three modules above from this image into
image A's TOC (moved to free addresses, compressed sections stored
decompressed by the card kernel's own routine). `--nk1 PATH` takes another
NK1 image; `tools/nk1_extract.py` cuts one out of a NAND dump.

## The anonymous flash image (`prod-anon.bin`, `sram-anon.bin`, `vflash-anon.bin`)

Decided by the repository owner (Marek, 2026-11-23, M6.24). Record:
[`EXP-2026-11-23-M6.24-anonymous-unit-flash`](../../docs/experiments/EXP-2026-11-23-M6.24-anonymous-unit-flash.md).

| file | bytes | SHA-256 | goes to flash | what it is |
| --- | --- | --- | --- | --- |
| `prod-anon.bin` | 722 | `daf97a643400edc1d980b1c00dc1f9bd4a9f10373fbafb3a77fe77f0e0e9afc7` | `0x00A000` | product record with a fictitious serial (`00 01 23 45`) and card PIN (`12 34 56 78`), sum recomputed |
| `sram-anon.bin` | 1 048 576 | `04924b683dfe47702cf46cf569ac0c6a3dd5a20f1253e91c92709368db03ebb5` | `0x400000` | eight `SMST` stores with the firmware's default content |
| `vflash-anon.bin` | 3 014 656 | `915f3d923c5f29f6235f57326868de2720a4dbc47413648138c380b8b43e85b1` | `0x500000` | the firmware's default VFlash content |

The built image (erased flash + these + NK1 at `0x040000`) has SHA-256
`256a0bd32101b58fced753a836e8eaceedba51df1f02f345e500cc3669812b49`.

**Where the bytes come from.** `sram-anon.bin` and `vflash-anon.bin` were
not made by editing the dump. The emulator was booted on an erased flash
(only the fictitious `PROD` and NK1), and the two RAM buffers that the
drivers fill with defaults were saved and wrapped in the on-flash format.
No byte of the real unit's `SRAM`, `VFlash` or crash log is in them. From
the real `PROD` come only: the tag, Target ID `10 20 02 12`, the model
`QY7200ND`, 9 option bytes at `+0x90` (meaning unknown), the blank IMMO
code, a 5-character part-number suffix, two bytes before the long serial,
and two flag words.

**Checked.** `unitflash_anon.py scan` against the real dump: the serial,
the PIN, the password and every stored position word occur 0 times; the 22
strings both images share (version labels, keyboard tables, the CARWINGS
centre numbers and URL) are firmware defaults, present on an erased flash
too. On `-M ze0` the image boots NK1 + the US card to the map with one
`OBJ_BackUp_Load Error` (object 0x0A) where an erased flash gives eleven.

**What it is not.** A driven car's state. The car position is the firmware
default (Los Angeles airport), there is no learned locator data, no phone,
no destination. Work that needs those still needs your own dump.

To make the files again (for another kernel or card), follow the steps at
the top of `tools/unitflash_anon.py`.
