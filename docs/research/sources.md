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
| <https://zelemar.eu/nissan-leaf-sd-card-protection-how-to-obtain-sd-card-password/> | SD CMD42 password / unit NOR "EEPROM" at `0x0000A000` (SST 38VF6401, SH-4A), 16 B password = 4 unit + `Clarion95321` | HYPOTHESIS (external lead) | Secondary/lead. Tail literal verified in firmware (EXP-M2.13, C-1880). NOR `0xA000` EEPROM area not present in available SD/CE images (negative, positive control; no unit NOR dump) — EXP-2026-11-08-M2.14, C-2000–C-2009. |
| <https://www.gtr.co.uk/threads/hack-the-hdd-for-euro-maps-on-us-car.249354/> | Same map tree on GT-R HDD / Renault Carminat | HYPOTHESIS | Secondary forum evidence. |
| <https://www.goingelectric.de/forum/viewtopic.php?t=71081> | Partitions, `dd` cloning | HYPOTHESIS | Secondary forum evidence; cloning is not reproduced by us. |
| <https://www.kiwi-w.org/index_eng.html> | KIWI/JIS mesh-code background | reference | Background for mesh codes, not Leaf-specific. The consortium's live site no longer serves the spec; which editions exist, their chapter lists and the V1.22-vs-JIS numbering are catalogued in [`kiwi-sources.md`](kiwi-sources.md) (M4.65). |
| <https://github.com/jharg/kiwiread> | C reader (GPL-3, 2014) for KIWI `ALLDATA.KWI`/`LOADING.KWI` from car-nav DVDs (Audi etc.): volume header `datavol_t`, 4-char-magic directory with `offset*2+0x800`, parcel data-management header `pdmdh_t`, Level Management Record, Road Distribution Header with multilinks, shapes/nodes; fields named after KIWI spec chapters | reference | Added 2026-11-21 (Marek); clones from the sandbox, commit `74741c5b`. Same concepts as our parcel/level/link records, different container — not ZE0 proof. Mapping is task M4.63, closed 2026-11-22 as **common concepts, different container** (`EXP-2026-11-22-M4.63-kiwi-map`): 0/4 header checks fit on three ZE0 files, road and background frames fail too; usable as a field-name/chapter glossary, not as a ZE0 reader or value oracle. No GPL code copied. Firmware vocabulary from the lineage scan is in [`kiwi-glossary`](../format/kiwi-glossary.md) (M4.64, C-7630–C-7636). M4.78 closes the per-family verdict on that page: 1 adopt (ch.1.2 `SWS`, already decoded by `tools/kiwi_types.py`), 3 partial (concept/name only), 6 unrelated; checked by `python3 tools/kiwi_verdict_check.py docs/format/kiwi-glossary.md` (`EXP-2026-11-24-M4.78-kiwi-verdict.md`). |
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
| <https://learn.microsoft.com/en-us/previous-versions/windows/embedded/aa451060(v=msdn.10)> | CE 5 `DBGPARAM` (`dbgapi.h`): `lpszName[32]`, `rglpszZones[16][32]`, `ulZoneMask` at struct +0x440. Basis for `tools/ce_dbgzones.py` (M8.H15). Checked 2026-11-24. | FACT |
| <https://rizin.re/> | Reverse-engineering framework used for SH-4 analysis | reference |
| <https://qemu.googlesource.com/qemu/+/refs/heads/master/hw/sh4> | QEMU SH-4 board/SoC code (`r2d.c`, `sh7750.c`); `sh_serial`/`sh_timer` in `hw/char`/`hw/timer`. Basis for a `ze0` machine (EXP-2026-11-05-37). | FACT (source) |
| Renesas SH-NaviJ press coverage (SH77721, 2008; SH77722) | SH-4A 333 MHz, 2D/3D graphics, USB, SD host, CAN, GPS baseband, FM multiplex; matches the driver set, part number unproven (C-531). | reference (secondary) |

## Android Auto / CarPlay on Leaf head units (M8.G3, checked 2026-11-24)

These are secondary/community sources, opened this revision, used only to
answer *how* AZE0 owners get Android Auto (firmware vs external box) and which
unit generation is involved. They are leads, not proof of our firmware facts.

| Source | What it is | Type | Note (checked 2026-11-24) |
| --- | --- | --- | --- |
| <https://nissanleaf.carhackingwiki.com/index.php/AV_Control_Unit> | Community wiki on the AV control unit | HYPOTHESIS | Opened. Lists "Android Auto and/or CarPlay via USB (in some models)" as a function; Gen 1 = QY7204/QY7224/QY7214/QY7254. Early Gen 2 runs CE, some later units (e.g. `25915 5SR0B`) run Linux. SD card holds CE firmware + maps + hidden `substance.skn`. |
| <https://mynissanleaf.com/threads/maintenance-of-your-navigation-unit.38356/> | My Nissan Leaf thread with LeafSDTools maintainer `dfj` | HYPOTHESIS | Opened. On backporting AA to a 2014 QY7xxx: "Technically it seems possible, needs some effort adapting it to Windows CE. But it won't ever be wireless, only via USB"; "better way would be to replace with newer Clarion QY8xxx, which has all the hardware for CarPlay&Android Auto, only missing the software." No external-box solution is claimed for the OEM screen. |
| <https://mynissanleaf.com/threads/translating-2014-jdm-leaf-qy7214nk-head-unit.39380/> | My Nissan Leaf thread on QY7214NK translation | HYPOTHESIS | Opened via search snippet. Reports Russian sellers distribute a hacked/English firmware with a unit-unique licence key and pirated maps; a cheaper "Leafhacker" option updates software only. This is a software/SD-card modification, not an external video box. |
| <https://mynissanleaf.ru/viewtopic.php?id=2917> | Russian Nissan Leaf club firmware-for-sale thread (`metori`) | HYPOTHESIS | Not opened (HTTP 403 on 2026-11-24); text read via search index. Lists Android Auto + CarPlay firmware for ZE1 2017-2020 and AZE0 30 kWh 12.2015-2017, with Russian maps/voice; explicitly **no** Android Auto offer for ZE0/AZE0 24 kWh 2010-2015 (only interface translation). AA is traded against the charge/climate timers. |
| <https://www.speakev.com/threads/leaf-24-2015-sd-card-fault.175163/> | Speak EV discussion of QY8xxx retrofit | HYPOTHESIS | Opened via search snippet. "Xanavi firmware comes in two flavours - original and CarPlay. The CarPlay one adds Apple CarPlay and Android Auto at the expense of climate timers, charge timers and the CD player"; a QY8xxx unit was retrofitted into a 2015 Leaf with a wiring change. Confirms the AA-capable hardware is the newer QY8xxx generation. |
| <https://www.reddit.com/r/leaf/comments/z3w7jr/android_autoapple_carplay_on_2011_nissan_leaf_sl/> | Reddit r/leaf, 2011 Leaf SL AA question | HYPOTHESIS | Opened via search snippet. Answer: only SD-card software sold by a third party, "mainly for the newer models (2015 etc)". No native ZE0 solution. |
| <https://www.goingelectric.de/forum/viewtopic.php?lang=en&t=52823> | German goingelectric forum, "Android Auto in old Leaf" | HYPOTHESIS | Opened via search snippet. For a 2014 ZE0 the consensus is no native AA; suggestions are phone-only AA via Bluetooth/aux or an external display. "Nobody has achieved anything significant" with the second SD slot. |
| <https://mynissanleaf.com/threads/does-my-leaf-support-android-auto.39276/> | My Nissan Leaf thread, 2015 QY-7210 | HYPOTHESIS | Opened via search snippet. Replies: no AA in 2015; support arrived in gen 2 (2019 wired CarPlay/AA); owners use external display units. |

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
