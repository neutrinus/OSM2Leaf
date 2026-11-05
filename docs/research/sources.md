# Research sources

External material used or worth checking. Add new sources here with a short
note about what they contain and how reliable they are.

## How to read this page

- **FACT** — primary or authoritative source; the cited statement is confirmed
  by a claim in [`claims.md`](claims.md), or the page is the artifact itself
  (license text, file index, source code).
- **HYPOTHESIS** — secondary or community claim; not independently reproduced
  by this repository. Treat it as a lead, not proof.
- **reference** — background or tooling; not evidence for the ZE0 format.
- **Checked 2026-11-05** means the URL was opened for this revision. The other
  links are retained from the previous version of this page and were **not
  re-opened**; their notes are the repository's earlier assessment, not a new
  check.
- README's external-source list is fully represented below: LeafSDTools and
  its `Updating-Map-Data` wiki, both `files.viaaq.eu` indexes, OSM, ODbL and
  GPL. No missing README entry was found, and no new URL was added.

## Primary community projects

| Source | What it is | Type | Status / note |
| --- | --- | --- | --- |
| <https://github.com/developerfromjokela/leafsdtools> | Community tooling for reading/unlocking/updating Nissan Leaf map SD cards | reference | Retained; not re-opened 2026-11-05. Link only; do not copy code. |
| <https://github.com/developerfromjokela/leafsdtools/wiki/Updating-Map-Data> | Step-by-step map update instructions and screenshots | HYPOTHESIS | Checked 2026-11-05: reachable; last edited 2025-11-02, 4 revisions. Workflow: delete everything except `VER_INFO`, copy new files except `VER_INFO`, then re-lock the SD. Links to `files.viaaq.eu/maps/`. Warns that cross-region swaps are untested and "most likely won't work". The page text does not name `TFTBL001`; only its screenshot shows a directory tree. |

## Map images

The two `files.viaaq.eu` indexes are labelled **FACT** for availability and
filenames only: they are the authoritative record of what the mirror currently
hosts, not a validation of the vendor data.

| Source | What it is | Type | Status / note |
| --- | --- | --- | --- |
| <https://files.viaaq.eu/maps/> | Mirror of map data archives | FACT | Checked 2026-11-05: reachable. Index lists `EU_MAPDATA_13-14.7z`, `EU_MAPDATA_14-15.7z`, `EU_MAPDATA_16-17.7z`, all Last-Modified 2025-09-17. Server sizes are rounded (`5.7G`/`5.8G`/`6.2G`); exact bytes are in [EXP-30](../experiments/EXP-2026-11-05-30-image-matrix.md). |
| <https://files.viaaq.eu/sd-images/> | Full SD card images | FACT | Checked 2026-11-05: reachable. Index lists `ENV200_2016_EU_QSD-390-100.img` (2025-09-17), `ENV200_2019_25920-6WX1C-EUR.img` (2025-09-24), `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (2025-11-03), `LEAF_2014_EU_QSD-357-101.img` (2025-09-17). Exact bytes are in EXP-30. |

## Format, region and teardown sources

| Source | What it is | Type | Status / note |
| --- | --- | --- | --- |
| <https://github.com/albertbm/osm2clarion> | Closest prior art: QY8x Clarion format, tile grid, zlib record tree, `DRSTR001`, `REFER001`, `LEV3456R` | reference | Prior art for the QY8x family, not ZE0 proof. Not re-opened 2026-11-05. |
| <https://www.drive2.com/l/676021531272284166/> | ZE0/QY7 teardown, full map tree, `VER_INFO`, "Different map code" | HYPOTHESIS | Secondary teardown; not reproduced by us. |
| <https://4pda.to/forum/index.php?showtopic=808016&st=120> | `NAVI VERSION NG`, firmware offsets, `SUM4`, PROD block | HYPOTHESIS | Secondary forum evidence; not reproduced by us. |
| <https://github.com/developerfromjokela/leafsdtools/issues/3> | Report of a US unit booting EU map files | HYPOTHESIS | Secondary report; C-080 says it was not reproduced. |
| <https://zelemar.eu/nissan-leaf-sd-card-protection-how-to-obtain-sd-card-password/> | SD CMD42 password / protection | HYPOTHESIS | Secondary; the CMD42 password claim is not tested by us. |
| <https://www.gtr.co.uk/threads/hack-the-hdd-for-euro-maps-on-us-car.249354/> | Same map tree on GT-R HDD / Renault Carminat | HYPOTHESIS | Secondary forum evidence. |
| <https://www.goingelectric.de/forum/viewtopic.php?t=71081> | Partitions, `dd` cloning | HYPOTHESIS | Secondary forum evidence; cloning is not reproduced by us. |
| <https://www.kiwi-w.org/index_eng.html> | KIWI/JIS mesh-code background | reference | Background for mesh codes, not Leaf-specific. |
| <https://gist.github.com/developerfromjokela/0acf80b6292c22f7a2aa7a3227883e82> | Mesh-ID converter notes | reference | Notes/code; not independently verified. |
| <https://gist.github.com/developerfromjokela/de143f2a0b05cd34c2e210b6edd6c650> | `.cmp` decompressor + `DRSTR` notes | reference | Cross-check against `tools/cmpind.py`; not used as proof. |

## Emulation / verification tooling

These are assessed in [`feedback-loop.md`](feedback-loop.md). None of them is
a ready-made Leaf ZE0 emulator.

| Source | What it is | Type | Status / note |
| --- | --- | --- | --- |
| <https://github.com/qemu/qemu/blob/master/hw/sh4/Kconfig> | QEMU system-mode SH-4 machine list (`r2d` only); `linux-user/sh4` exists but targets Linux ELF | FACT | C-510: not sufficient for WinCE. |
| <https://github.com/mamedev/mame/blob/master/src/devices/cpu/sh/sh4.cpp> | MAME SH-4/SH7750-family CPU core (BSD-3-Clause); no CETUS_SH4 board, on-board peripherals incomplete | FACT | C-511: fallback only. |
| <https://github.com/Gadgetoid/sh3-emu> | MIT SH-3 Windows CE 1.x/2.x emulator; includes a Clarion AutoPC 310C machine | FACT | C-512: closest architectural prior art; not SH-4/CE5. |
| <https://github.com/gweslab/cerf> | Universal Windows CE emulator; ARM/StrongARM/XScale/MIPS only, no SH core; custom non-commercial licence | FACT | C-513: not suitable. |
| <https://www.hackaday.io/project/19783-sd-card-emulation> | FPGA SD card emulation, including 4-bit conversion | reference | Possible SD-emulator reference; not tested on the Leaf. |
| <https://github.com/ZipCPU/sdspi> | SD-card controller RTL (SPI/SDIO) | reference | RTL reference only. |
| <https://www.winehq.org/about> | Wine: Win32 compatibility layer, not a CPU emulator; no SH-4/WinCE | FACT | C-509: rejected. |

## Standards and licensing

| Source | What it is | Type |
| --- | --- | --- |
| <https://www.openstreetmap.org> | OSM data source | reference |
| <https://wiki.openstreetmap.org/wiki/Map_features> | OSM tagging reference | reference |
| <https://opendatacommons.org/licenses/odbl/1-0/> | ODbL 1.0, license for OSM-derived data | FACT |
| <https://www.gnu.org/licenses/gpl-3.0.html> | GPL-3.0, license for this project's code | FACT |
| <https://www.gnu.org/licenses/gpl-3.0.txt> | Plain-text GPL-3.0 used for `LICENSE` | FACT |

## Format-adjacent references

These are not Leaf-specific but are potentially useful for the mesh-code
and Windows CE/SH-4 parts of the work.

| <https://www.stat.go.jp/english/data/mesh/> | Japanese grid/mesh code reference (JIS X 0410) | reference |
| <https://learn.microsoft.com/en-us/windows/win32/debug/pe-format> | PE/COFF format reference | FACT |
| <https://rizin.re/> | Reverse-engineering framework used for SH-4 analysis | reference |
| <https://qemu.googlesource.com/qemu/+/refs/heads/master/hw/sh4> | QEMU SH-4 board/SoC code (`r2d.c`, `sh7750.c`); `sh_serial`/`sh_timer` in `hw/char`/`hw/timer`. Basis for a `ze0` machine (EXP-2026-11-05-37). | FACT (source) |
| Renesas SH-NaviJ press coverage (SH77721, 2008; SH77722) | SH-4A 333 MHz, 2D/3D graphics, USB, SD host, CAN, GPS baseband, FM multiplex; matches the driver set, part number unproven (C-531). | reference (secondary) |

## Pending research

The following are being collected and will be added with notes. They are leads,
not sources, and no URL is asserted here.

- Forum threads on Nissan Leaf map formats (mynissanleaf.com, speakEV,
  forums, Reddit).
- Any public reverse engineering of Clarion/Hitachi `CLA-NAVI` map databases
  on other Nissan/Infiniti models.
- Documentation of the `HCXCmp` compression library.
- Details of the map activation / "different map code" check and SD card
  identity (CID) binding.
- Legal analysis of interoperability reverse engineering in the relevant
  jurisdictions.

> When adding a source, say whether it is **FACT** (primary evidence: format
> dumps, official docs, source code), **HYPOTHESIS** (secondary: forum post,
> anecdote) or **reference** (background/tooling), and whether it agrees with
> our own observations.

## Open issues

1. **README firmware claim vs the claim ledger.** [`README.md`](../../README.md)
   says Ghidra "recovered the code path that opens `\CMP.LST` and
   `\SystemSD\REFER001\`". C-330/C-331/C-396 say the real `\CMP.LST` has zero
   pointer references, map filenames have zero literal references, and the
   reader is not located. The README wording overstates the evidence.
2. **README "fully decoded" containers.** README says the compressed
   address/POI containers are fully decoded. C-026 and C-139 say the
   compression/index layer is decoded, but the record layouts inside
   `ADDRE`/`POINT` are not; C-215 still cannot anchor the POI field block. The
   word "container" is doing too much work in README.
3. **Wiki vs issue #3 on cross-region cards.** The LeafSDTools wiki (checked
   2026-11-05) says mismatching regions are untested and "most likely won't
   work"; C-080 records a US QY7210NN reportedly booting EU map files. C-080 is
   unreproduced secondary evidence, so the contradiction is unresolved.
4. **`TFTBL001` provenance.** The wiki page text does not name `TFTBL001`;
   only its screenshot shows a directory tree. C-071 still cites the wiki
   screenshot and asks for confirmation, while C-122 records `TFTBL001` in the
   2014/2016 images. C-071 should point at C-122 instead of the wiki.
5. **2019 card label.** `485-3651-01` appears only in the pre-rebuild
   [`image-versions.md`](image-versions.md) prose; EXP-30 and C-123 do not
   record it. The rebuilt table marks it `unverified` (it is mentioned only to
   preserve the open question). Add the raw observation to an EXP or leave it
   unverified.
6. **Census gaps.** No record gives the `.7z` map-tree byte totals, the three
   map-tree tile counts, or the 2019 directory/byte/`.cmp` counts. The rebuilt
   table marks these `unverified` rather than inferring them. No US sample is
   in the examined set either; C-070 leaves the US layout unverified.
7. **`0x1ac` semantics.** README says tiles have "descriptor tables at
   `0x1ac`/`0x2ac`", and `docs/format/map-tiles.md` still calls `0x1ac` the
   level-of-detail table. C-296 retracts that: `0x1ac` is a 428-byte
   per-object OSM buffer (`obj+0x40`), not the tile level table. C-041/C-052
   still describe the old structure. The docs need one reconciled statement.
8. **Scope terminology.** README targets the Leaf ZE0 2011–2012, but the
   examined set includes 2014/2016 (AZE0/e-NV200) and 2019 (QY8x). EXP-30
   separates "same navigation format family" from "same vehicle generation";
   the `Engine` column in `image-versions.md` means the format family, not the
   car model. This is a terminology risk, not a factual contradiction.
