# Unit-flash kernel image NK1 (`nk1-QY7200ND.bin`)

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

- The rest of the NAND (boot loaders at 0x0–0x3ffff, the regions after NK1),
  `SRAM` and `VFlash` (user data) and `PROD` (unit record). `PROD` holds the
  card-lock password; the others may hold personal data.
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
