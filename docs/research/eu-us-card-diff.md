# EU 2011 card vs US 2011 card: what differs

Marek (2026-11-22) asked what differs between the EU and the US 2011 map
cards, radio aside, now that an EU card can pass both region checks of a US
unit ([eu-card-on-us-unit.md](../hardware/eu-card-on-us-unit.md)). This page
is the answer, file by file. Record: EXP-2026-11-22-M1.54-eu-us-card-diff,
claims C-8450–C-8455.

| Card | Image | Files on the FAT partition | Bytes in files |
| --- | --- | --- | --- |
| EU | `LEAF_2011-2012_QSD-309-101_navi158_eu.img` | 480 | 5,173,965,667 |
| US | `LEAF_2011-2012_US.img` | 248 | 5,182,407,132 |

Both images are 8,057,257,984 bytes with the same partition table (one FAT32
partition at LBA 204802). SHA-256 of the whole images: EU
`105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`, US
`53342430a1bb58d3ed6eb68c5563f079c710a400134d522e6192489b324c5383`. The file lists with sizes and SHA-256 (no file
content) are in [`card-manifests/`](card-manifests/); `tools/card_diff.py`
makes and compares them.

## Short answer

- **System area (first 100 MiB):** the kernels (ROM B and C) are the same
  bytes. Only ROM A (the applications) differs, and the two cards' A are
  separate builds of nearly every module. Three small records differ besides:
  the `HDD_INFO` copy, padding, and 39 stray bytes after ROM C.
- **Map partition:** only one file is the same on both cards (`CMP.LST`). Every
  other file is either regional (map tiles, search data, voices, traffic) or
  the same name with other bytes.
- **What an EU card on a US unit still lacks** after `card_mapcode.py`: the
  US voices (`SPEECH/US`, `SPEECH/CF`) and the XM data (`XMD`). Whether the
  US unit then asks for a voice folder the EU card does not have is open
  (see "Open" below).

## System area (before the FAT partition)

Compared in 1 MiB blocks, then byte runs.

| Offset | Content | EU vs US |
| --- | --- | --- |
| `0x00000000` | MBR | same |
| `0x00200000`, copy `0x02000000` | ROM A (`Navi.exe` and app DLLs) | **differs**: build name `X210ECNI.158` (EU) vs `X210NBNI.147` (US); of the modules, only `atlce400.dll` is the same bytes (M1.36b atlas). US-only modules are radio (`RBDS_CC`, `XMCC`, `XMStatusCC`), EU-only `RDSCC`. `Navi.exe` is a different build (7,596 vs 7,520 functions, M1.22) |
| `0x03e00000`, copy `0x04800000` | ROM B (kernel, updaters) | same |
| `0x05200000` | ROM C (kernel, TestMode) | same up to ROM C's end (`physlast`, file `0x058685d8`). The EU card has 39 more bytes right after it (`0x058685d9`–`0x058685ff`), the US card zeros. They are outside every ROM C module and file. |
| `0x05c00000` | `BASSB` blob | same up to `0x05d88600`; after it the EU card pads with `0x00`, the US card with `0xff` |
| `0x06000000` | raw `HDD_INFO` copy | **differs** (below). The launcher reads the file on the FAT partition, not this copy (C-8356). |

## Map partition, by folder

| Folder | EU | US | What it is |
| --- | --- | --- | --- |
| `VER_INFO/HDD_INFO.TXT` | `QSD-302-100`, `QSD-309-101`, `02-110100-00`, `SDC08-EVEUR`, `11-05`, `470323501005` | `QSD-301-100`, `QSD-301-103`, `02-100100-00`, `SDC08-EVNAM`, `10-30`, `470282203030` | unit map code, card map code, map DB version, product, date (YY-MM), part number. `card_mapcode.py` rewrites line 1. |
| `MAPAL001` | 46 files, 3,521 MB | 113 files, 2,870 MB | map tiles. No tile name is shared except `LEV3456R.DAT` (the coarse levels for the whole area, incl. routing), whose bytes differ. |
| `REFER001` | 388 files, 1,422 MB | 116 files, 2,216 MB | search data (addresses, POI, intersections, postcodes) in `.cmp`/`.ind` pairs, numbered per country or state. 110 names exist on both, with other bytes. EU only: `ZCODE*` (33), `ZIPFR001`, and more `ADDRE`/`ICADM`/`INTER`/`POINT` numbers. US only: `INDEX001`, `FRWAY001`, `FRWAY006`. |
| `REFER002` | `COORD001` + 15 `POINT0nn` | `COORD001` + `POINT001` | small POI tables. `COORD001` has the same size, other bytes. |
| `SPEECH` | `BE`, `DU`, `FR`, `GE`, `IT`, `PT`, `SP` | `US`, `CF` | voices: per language `GID/S??00000.GID` (prompts), `TTS/T??00000.TTS` (text to speech), `VR/V??00000.AGM` (voice recognition). `BE` is British English, `CF` Canadian French. **No language folder is on both cards.** |
| `OPNG/MKR_OPNG/NISSAN` | `OIXXEVNI.001` | `OIXXNVNI.001` | opening image, same size (1,606,224 B). Kernel B looks the file up by the pattern `OIXXXXXX`, so the name difference does not matter (the NK1 + EU card run showed the opening logo, M8.C1r). |
| `RDSTM001` | `LCTBL001`, `RDSTM001` | same names | RDS-TMC (EU) / traffic location tables; other bytes and sizes |
| `TMC/reception.dat` | yes | — | EU TMC reception settings |
| `XMD` | — | `bsaidxtbl.dat`, `bsatbldata.dat`, `LTNTBL.DAT` | XM satellite radio data (radio, out of scope) |
| `BICON001.DAT` | 114,598 B | 110,068 B | POI and brand icons (PNG container) |
| `DRSTR001.DAT` | 11,968 B | 7,456 B | directory index |
| `MMAIN001.DAT` | 4,096 B | 4,096 B | master header / database manifest; other bytes (other dates) |
| `CMP.LST` | 19 B | 19 B | **same** (`\SystemSD\REFER001\`) |

## What this means for an EU card in a US unit

1. The two region checks are handled: the map code in `HDD_INFO.TXT` and
   the build name in the ROM A header (`card_mapcode.py set --from-nk1`).
2. The kernels on the card are the unit's own family (B and C are the same
   bytes on both cards), so nothing changes at that level.
3. The applications come from the EU card's ROM A, but the unit's area
   (USA) chooses which launch records start (`us-eu-region.md`). The EU
   ROM A has the USA record of `Navi.exe` too.
4. The voices on the EU card are all European. A US unit set to US English
   or Canadian French would look for a folder the card does not have.
   Copying `SPEECH/US` from the US card onto the EU card, or choosing a
   European language, are the two ways round it. Neither is tested.

## Open

- How the firmware picks the `SPEECH` folder: from the unit's language
  setting, from a list on the card, or from the area. The strings found so
  far are only the voice-recognition work paths (`\UserSD\SPEECH\VR\...`).
  Follow-up task M1.55.
- Which language list the setup screen offers on a US unit with the EU
  card.
