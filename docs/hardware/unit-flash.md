# The head unit's own flash: what is in the 8 MiB

Status: **read from one real unit.** Marek dumped his US unit (`QY7200ND`,
Product ID `10 20 02 12`) with LeafSDTools on 2026-11-22. This page is the map
of that dump. Records:
[`EXP-2026-11-22-M6.18-unit-flash-backup`](../experiments/EXP-2026-11-22-M6.18-unit-flash-backup.md)
(files and hashes, C-5203–C-5206) and
[`EXP-2026-11-22-M6.19-unit-flash-map`](../experiments/EXP-2026-11-22-M6.19-unit-flash-map.md)
(content, C-5210–C-5219). The emulator tasks that ran in parallel call the
flash kernel **NK1** and already boot it: M8.C1k, M8.C1m, M8.C1r, M8.C1q
(C-8290–C-8297, C-8350–C-8358, C-8400–C-8416). This page uses both names.

The dump is **not in the repository** and must never be: it holds the SD PIN,
the unit serial, a phone book, Bluetooth device names and stored
destinations. Only offsets, sizes, checksums and firmware labels are written
here. Read a dump with `tools/unitflash.py`, which masks the private fields:

```bash
python3 tools/unitflash.py map DUMP       # erase-block table
python3 tools/unitflash.py images DUMP    # the six firmware images
python3 tools/unitflash.py prod DUMP      # product record, PIN and serial masked
python3 tools/unitflash.py stores DUMP    # user-data stores and the crash log
python3 tools/unitflash.py parts DIR      # sram/vflash/prod files against the full dump
```

## What this changes

1. **The unit has its own kernel.** The flash holds a complete Windows CE
   kernel image, `X110NBNI.147` (NK1; 51 modules, 2.9 MiB). In normal mode the unit
   boots this kernel from flash and then loads the application image A
   (`X210NBNI.147`, `Navi.exe` and 150 more modules) from the map card. Image B
   on the card (`UP10XXXX.500`) is the software-update kernel and image C
   (`PM10XXNI.021`) the test-mode kernel; neither runs in normal mode.
2. **The map-code check compares the card with the flash kernel's header.**
   `DIFFERENT MAP CODE` compares line 1 of the card's `HDD_INFO.TXT` with 11
   characters at header `+0x60` of the kernel that runs. In flash these are
   `QSD-301-100`, and the map-DB window at `+0x70` is 16..16. They are
   constant bytes of the image, not written at boot.
3. **The market byte is flash `0xA021`.** The kernel reads the product record
   at `0xA000A000` and returns `+0x20..+0x23` as the Target ID. Byte 1 is the
   area; this unit has `0x20` (USA).
4. **The flash is at physical address 0.** The boot loader is linked at
   `0xA0000000`, the kernel reads `PROD` at `0xA000A000`, and the sub-test
   program runs in place at `0x803A0000`.

## Layout

Blocks 0–7 are 8 KiB, blocks 8–`0x86` are 64 KiB; block `n ≥ 8` starts at
`(n − 7) × 0x10000` (C-5193, confirmed by C-5204).

| Offset | Blocks | Content | LeafSDTools name |
| --- | --- | --- | --- |
| `0x000000`–`0x0040AF` | 0–2 | `IP10XENI.017`, boot loader stage 1 (IPL), linked at `0xA0000000` | IPL |
| `0x006000` | 3 | zeros | |
| `0x008000` | 4 | erased | |
| `0x00A000`–`0x00A2D1` | 5 | product record `PROD` (see below) | PROD |
| `0x00C000` | 6–7 | erased | |
| `0x010000` | 8 | `BS10XENI.017`, monitor and memory test, linked at `0x8B000000` | BASE |
| `0x020000` | 9 | `EB10XENI.017`, Ethernet boot loader (download over LAN91C111), `0x8B010000` | EBOOT |
| `0x030000` | `0x0A` | `EH10XENI.017`, card unlock, flash writer and updater, `0x8B020000` | ENHANCE |
| `0x040000`–`0x30DAE7` | `0x0B`–`0x37` | `X110NBNI.147`, the normal-mode CE kernel, linked at `0x88000000` | APP X/W1 |
| `0x30DAE8`–`0x31FFFF` | `0x37`–`0x38` | bytes after the end of the kernel image; not covered by its size; content unknown | |
| `0x320000`–`0x35FFFF` | `0x39`–`0x3C` | erased | |
| `0x360000`–`0x38FFFF` | `0x3D`–`0x3F` | `ASLG` crash log (capacity `0x2FFE4`, `0x17C90` used) | |
| `0x390000` | `0x40` | erased | |
| `0x3A0000`–`0x3A52BF` | `0x41` | `PS10XXXX.009`, sub-test program, runs in place at `0x803A0000`; the rest of the block holds other bytes | PS+MEM |
| `0x3B0000` | `0x42` | `VEUP` record (6 bytes set besides the tag) | |
| `0x3C0000`–`0x3FFFFF` | `0x43`–`0x46` | erased | |
| `0x400000`–`0x4FFFFF` | `0x47`–`0x56` | "SRAM": four `SMST` stores, two copies each | SRAM |
| `0x500000`–`0x7DFFFF` | `0x57`–`0x84` | "VFlash": user data (written up to `0x74FFFF`, then erased) | VFlash |
| `0x7E0000`–`0x7FFFFF` | `0x85`–`0x86` | erased | |

## The six images

Every image starts with the same header as the CE images on the card:

| Offset | Field |
| --- | --- |
| `+0x00` | SH-4 jump to the entry (`nop nop mov.l nop jmp nop`), entry address at `+0x0C` |
| `+0x20` | label, 12 characters: two-letter kind, `10`, variant, `.`version |
| `+0x30` | u16: sum of all image bytes with this field as zero ("SUM2" in LeafSDTools Companion) |
| `+0x32` | u32: image size in bytes |
| `+0x40` | `ECEC`, then the address of the ROM header and its offset |
| `+0x50` | Clarion part number |
| `+0x60` | `VerInf`, 11 characters (kernel images only) |
| `+0x70` | map-DB window: minimum and maximum, two big-endian u16 |
| `+0x80` | `SUM4`, u32 value, u32 size (rule not derived here; LeafSDTools computes it) |

The `+0x30` sum verifies on all six images and on image B of the US card
(7 of 7); one flipped byte breaks it.

| Offset | Label | Part number | Linked at | Size | Built | What it is |
| --- | --- | --- | --- | --- | --- | --- |
| `0x000000` | `IP10XENI.017` | `470-3129-00` | `0xA0000000` | `0x40B0` | Dec 14 2010 | `BOOTIPL`: reads the mode switch (`DSW`), checks sums, starts the next stage |
| `0x010000` | `BS10XENI.017` | `470-3130-00` | `0x8B000000` | `0x71E0` | Dec 14 2010 | `BASE`: serial monitor, memory tests, "Jump EBOOT" |
| `0x020000` | `EB10XENI.017` | `470-3131-00` | `0x8B010000` | `0xB5F4` | Dec 14 2010 | Microsoft Ethernet boot loader (TFTP download, `JumpToOS`) |
| `0x030000` | `EH10XENI.017` | `470-3132-00` | `0x8B020000` | `0xF820` | Dec 14 2010 | `BOOTENHN`: unlocks the SD card, reads `PRODUCT.INF`, writes kernels to flash and card (`NK1`, `NK2`, `UPNK`, `PM`, `PS`) |
| `0x040000` | `X110NBNI.147` | `470-2817-33` | `0x88000000` | `0x2CDAE8` | | the kernel that runs in normal mode |
| `0x3A0000` | `PS10XXXX.009` | `470-2758-00` | `0x803A0000` | `0x52C0` | | `SUBTEST`: RAM and watchdog tests, in place in flash |

The label kinds that `ENHANCE` knows are `IP BS EB EH OI PS UP UE W1 X1 W2 X2
PM UT`. With the card images this gives the naming:

| Kind | Where | Image |
| --- | --- | --- |
| `X1` | unit flash `0x040000` | normal-mode kernel ("NK1") |
| `X2` | card `0x200200` and `0x2000200`; the label is in the 512-byte block before the image (`0x200016`) | applications, image A ("NK2", two copies) |
| `UP` | card `0x3E00200` and `0x4800200` | update kernel, image B ("UPNK", two copies) |
| `PM` | card `0x5200200` | test-mode kernel, image C ("PMNK") |

The boot loader strings name the start modes read from the switch: `MONI`,
`FACT`, `PROD` (aging), `SubT`, and four `NORMAL` variants. Which loader hands
over to which is not decompiled; the address literals fit IPL → BASE →
ENHANCE → kernel (IPL holds `0xA0010000` and `0x8B020000`; ENHANCE holds
`0xA0040000` and `0x88000000`).

## The kernel in flash and the card

Three independent checks say the flash kernel and card image A are one
system:

| Check | Flash kernel `X1` | Card A (US) | Card B (US) |
| --- | --- | --- | --- |
| Label | `X110NBNI.147` | `X210NBNI.147` | `UP10XXXX.500` |
| RAM end = start of A | `0x8CAE1000` | starts at `0x8CAE1000` | `0x8E600000` |
| DLL address range | `0x01F90000`–`0x02000000` | ends at `0x01F90000` | `0x01BF0000`–`0x02000000` (overlaps A) |

And the unit says so itself: the crash log in flash (one report, 2017-08-15)
ends with `Navi Version : X110NBNI-147` and lists modules of image A.

The emulator shows the same from the other side (M8.C1r): the flash kernel
loads image A from the card itself (`Read NK2. To 8cae1000h`, C-8403), and
before that its `AppLaunch.dll` compares its own label with the label of
card image A, characters 2–11 (`10NBNI.147`). The EU card (`X210ECNI.158`)
fails this with `NK Version Error`, `Error Proc<00000042>` (C-8401). This is
a region and version check that runs before the map-code check.

The kernel image has 51 modules and 10 files: `nk.exe`, `coredll.dll`,
`filesys.exe`, `device.exe`, the drivers (`SDHC`, `flash`, `VSram`,
`FlashManager`, `CAN`, `anwdrv`, `serial_*`, `GPIO`, `lcddrv`, `VIN`, …),
`commondll.dll`, `AppLaunch.dll`, and five programs that must work without a
card: `DrawOi.exe` (opening image), `Camera.exe`, `Antitheft.exe`,
`Failsafe.exe`, plus the registry hives. Its code differs from images B and C
of the card in every module (different link addresses and build), so
addresses found in B do not carry over; names and structure do.

`AppLaunch.dll` in this kernel has the launch table at `0x03E32490` (111
records of `0x310` bytes; `tools/applaunch_table.py --image-start 0x40000
DUMP dump`). Record 1 is `NK2` (type 5, normal mode): it loads image A from
the card. `Navi.exe` has one record per area with the same path
`\windows\Navi.exe` (record 79 USA, 80 Euro), so the area picks a record, not
a different program. The area also picks drivers: `TNR2:` (RDS) and `TMC1:`
start only for Euro, `TNR3:` (XM radio) and `TNR4:` (RBDS) only for USA.

## The product record (`PROD`, `0xA000`)

722 bytes are in use. Offsets from the LeafSDTools source, confirmed on the
dump; the kernel side is `nk.exe` `fn 0x88048724` (IOCTL `0x01013208`), which
first calls `fn 0x880485D4` (tag and sum check against flash `0xA000A000`) and
then returns fields of the RAM copy at `0x89E439B8`.

| Offset | Content | This unit |
| --- | --- | --- |
| `+0x000` | `PROD` | |
| `+0x020` | Target ID, 4 bytes; byte 1 is the area (`0x10` JP, `0x20` USA, `0x30` Euro, `0x40` RU, `0x50` CN) | `10 20 02 12` |
| `+0x040` | model | `QY7200ND` |
| `+0x050` | serial | not recorded |
| `+0x060` | unit half of the SD PIN, 4 bytes | never recorded |
| `+0x090` | 8 bytes returned by the same IOCTL; meaning unknown | |
| `+0x0A0` | IMMO code | `FF FF FF FF` |
| `+0x0B0` | 5 characters: suffix of the Nissan part number `25915-xxxxx` printed as `N #` on the type label (C-10141) | |
| `+0x100` | SD PIN as sent in CMD42, 16 bytes | never recorded |
| `+0x140` | 6 bytes: unit ID = `10 01` + serial (BCD), printed as `車載機 ID` on the type label (C-10120, [photos](head-unit.md#type-labels-community-pictures-not-mareks-unit)) | |
| `+0x180`, `+0x190` | 4 bytes each; `+0x193` is the IMMO check flag | flag `00` |
| `+0x2D0` | u16 sum of bytes `+0x000..+0x2CF` | verifies |

## User data

- **SRAM (`0x400000`, 1 MiB).** Four stores, each kept twice. A copy starts
  with `SMST`, a version (14), a generation counter and the copy number (1 or
  2); the two copies of a store differ by one generation, so the driver
  writes them in turn and the higher counter is the current one. Sizes in
  blocks: 3 + 3, 1 + 1, 1 + 1, 3 + 3. This is what `VSram.dll` mirrors in RAM.
  A store ends with a u32 sum of all little-endian u32 words before it (at
  `end − 0x10`), 8 zero bytes and `SMED`; `VSram.dll` checks start tag,
  version, end tag and sum (`CheckAreaData`), and one flipped bit gives
  `SUM NG` (M6.24, C-8860, C-8861). In RAM the four areas lie back to back
  at physical `0x09a40000` (work copy) and `0x09ac0000` (second copy).
- **VFlash (`0x500000`, 2.875 MiB).** No common header. It holds a POI and
  address store, a UTF-16 phone book and device names. Not decoded here.
- **Crash log (`0x360000`).** `ASLG` header, then text records from the
  kernel's exception reporter (`AstLog`): registers, stack, module list,
  memory, version, time.

## For the emulator

- The boot that matches the car is flash kernel + card image A. `-M ze0`
  does it with `nk=FILE` and `ze0_ipl.py --nk` (M8.C1r, M8.C1q); the kernel
  image alone is in `firmware/unit-flash/nk1-QY7200ND.bin` (the owner's
  exception to the vendor-data rule, bytes `0x040000`–`0x30DAE7` of the
  dump). It needs no `verinf=`/`mapdb=` option: its header has the values.
- `-M ze0,flash=FILE` maps a whole dump at physical 0, so the kernel reads
  `PROD` itself (`Target ID Code >> 10200212`, M8.C1m).
- The NOR model of M8.H18 can use the real layout: product record at
  `0xA000`, `SMST` stores at `0x400000`. An erased image is not what the
  drivers see on a car.
- An image with no data of a real unit is in the repository (M6.24):
  `tools/unitflash_anon.py build`, or `ze0_launch.py --flash anon`. Its user
  areas are the firmware's own defaults, taken from a boot on erased flash.
  It needs only `PROD` and the kernel; boot loaders, the crash log and
  `VEUP` are left erased and the boot does not miss them.
- A whole dump is private and stays out of Git. A shareable flash image
  needs the user areas (`0x360000`–`0x38FFFF`, `0x400000`–`0x7DFFFF`) erased
  and the PIN and serial fields of `PROD` replaced. Serial logs of a flash
  kernel boot are private too: its SD driver prints the lock password
  (C-8406).

## Not known

- Whether an EU unit holds the same kernel with `QSD-302-100`, or another
  build (`X110EC…`). Only one unit is dumped.
- The `SUM4` rule as a formula (LeafSDTools Companion recomputes it; not
  re-derived here), the `VEUP` fields, the bytes after the kernel image, the
  record formats inside SRAM and VFlash (the store frame and its sum are
  known, M6.24; the objects inside are not).
- The flash chip. `ENHANCE` selects between `SST64`, `SST16` and `NORMAL`
  write routines, which fits the SST 38VF6401 lead but does not prove it.
