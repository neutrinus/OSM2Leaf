# Research sources

External material used or worth checking. Add new sources here with a short
note about what they contain and how reliable they are.

## Primary community projects

| Source | What it is | Status |
| --- | --- | --- |
| <https://github.com/developerfromjokela/leafsdtools> | Community tooling for reading/unlocking/updating Nissan Leaf map SD cards | Primary reference; link only, do not copy code |
| <https://github.com/developerfromjokela/leafsdtools/wiki/Updating-Map-Data> | Step-by-step map update instructions and screenshots | Read; confirms update workflow and newer directory contents (e.g. `TFTBL001`) |

## Map images

| Source | What it is | Status |
| --- | --- | --- |
| <https://files.viaaq.eu/maps/> | Mirror of map data archives | Used for cross-version comparison |
| <https://files.viaaq.eu/sd-images/> | Full SD card images | Source of `LEAF_2011-2012_QSD-309-101_navi158_eu.img` |

## Format, region and teardown sources

| Source | What it is | Status |
| --- | --- | --- |
| <https://github.com/albertbm/osm2clarion> | Closest prior art: QY8x Clarion format, tile grid, zlib record tree, `DRSTR001`, `REFER001`, `LEV3456R` | Primary lead; verify against ZE0 |
| <https://www.drive2.com/l/676021531272284166/> | ZE0/QY7 teardown, full map tree, `VER_INFO`, "Different map code" | Secondary evidence |
| <https://4pda.to/forum/index.php?showtopic=808016&st=120> | `NAVI VERSION NG`, firmware offsets, `SUM4`, PROD block | Secondary evidence |
| <https://github.com/developerfromjokela/leafsdtools/issues/3> | Report of a US unit booting EU map files | Secondary evidence |
| <https://zelemar.eu/nissan-leaf-sd-card-protection-how-to-obtain-sd-card-password/> | SD CMD42 password / protection | Secondary evidence |
| <https://www.gtr.co.uk/threads/hack-the-hdd-for-euro-maps-on-us-car.249354/> | Same map tree on GT-R HDD / Renault Carminat | Secondary evidence |
| <https://www.goingelectric.de/forum/viewtopic.php?t=71081> | Partitions, `dd` cloning | Secondary evidence |
| <https://www.kiwi-w.org/index_eng.html> | KIWI/JIS mesh-code background | Reference |
| <https://gist.github.com/developerfromjokela/0acf80b6292c22f7a2aa7a3227883e82> | Mesh-ID converter notes | Secondary evidence |
| <https://gist.github.com/developerfromjokela/de143f2a0b05cd34c2e210b6edd6c650> | `.cmp` decompressor + `DRSTR` notes | Secondary evidence |

## Emulation / verification tooling

These are assessed in [`feedback-loop.md`](feedback-loop.md). None of them is
a ready-made Leaf ZE0 emulator.

| Source | What it is | Status |
| --- | --- | --- |
| <https://github.com/qemu/qemu/blob/master/hw/sh4/Kconfig> | QEMU system-mode SH-4 machine list (`r2d` only); `linux-user/sh4` exists but targets Linux ELF | Checked; not sufficient for WinCE |
| <https://github.com/mamedev/mame/blob/master/src/devices/cpu/sh/sh4.cpp> | MAME SH-4/SH7750-family CPU core (BSD-3-Clause); no CETUS_SH4 board, on-board peripherals incomplete | Checked; fallback only |
| <https://github.com/Gadgetoid/sh3-emu> | MIT SH-3 Windows CE 1.x/2.x emulator; includes a Clarion AutoPC 310C machine | Closest architectural prior art; not SH-4/CE5 |
| <https://github.com/gweslab/cerf> | Universal Windows CE emulator; ARM/StrongARM/XScale/MIPS only, no SH core; custom non-commercial licence | Checked; not suitable |
| <https://www.hackaday.io/project/19783-sd-card-emulation> | FPGA SD card emulation, including 4-bit conversion | Reference for a possible SD emulator |
| <https://github.com/ZipCPU/sdspi> | SD-card controller RTL (SPI/SDIO) | Reference only |
| <https://www.winehq.org/about> | Wine: Win32 compatibility layer, not a CPU emulator; no SH-4/WinCE | Checked; rejected |

## Standards and licensing

| Source | What it is |
| --- | --- |
| <https://www.openstreetmap.org> | OSM data source |
| <https://wiki.openstreetmap.org/wiki/Map_features> | OSM tagging reference |
| <https://opendatacommons.org/licenses/odbl/1-0/> | ODbL 1.0, license for OSM-derived data |
| <https://www.gnu.org/licenses/gpl-3.0.html> | GPL-3.0, license for this project's code |
| <https://www.gnu.org/licenses/gpl-3.0.txt> | Plain-text GPL-3.0 used for `LICENSE` |

## Format-adjacent references

These are not Leaf-specific but are potentially useful for the mesh-code
and Windows CE/SH-4 parts of the work.

| Source | What it is |
| --- | --- |
| <https://www.stat.go.jp/english/data/mesh/> | Japanese grid/mesh code reference (JIS X 0410) |
| <https://learn.microsoft.com/en-us/windows/win32/debug/pe-format> | PE/COFF format reference |
| <https://rizin.re/> | Reverse-engineering framework used for SH-4 analysis |

## Pending research

The following are being collected and will be added with notes:

- Forum threads on Nissan Leaf map formats (mynissanleaf.com, speakEV,
  forums, Reddit).
- Any public reverse engineering of Clarion/Hitachi `CLA-NAVI` map databases
  on other Nissan/Infiniti models.
- Documentation of the `HCXCmp` compression library.
- Details of the map activation / "different map code" check and SD card
  identity (CID) binding.
- Legal analysis of interoperability reverse engineering in the relevant
  jurisdictions.

> When adding a source, say whether it is **primary evidence** (format dumps,
> official docs, source code) or **secondary** (forum post, anecdote), and
> whether it agrees with our own observations.
