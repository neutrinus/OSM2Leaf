# OSM2Leaf

OpenStreetMap map compiler research for the **Nissan Leaf ZE0 (2011–2012)**
navigation unit.

> **Status: research only.** This project currently reverse-engineers the
> factory map SD card format. Nothing here is installed in a car, and no
> modified map has been validated on real hardware yet.

The long-term goal is to determine whether a usable map database can be
generated from OpenStreetMap and written back to a Leaf map SD card. The first
milestone is not a full compiler — it is a verified, reproducible description
of the existing format and a small toolset that can read it.

## Target hardware

| Item | Value |
| --- | --- |
| Car | Nissan Leaf ZE0, model years 2011–2012 (US and EU) |
| Head unit | Clarion/Hitachi `CLA-NAVI05-01` |
| OS | Windows CE 5.0 |
| CPU | Hitachi SH-4 (SH775x class, `CETUS_SH4` board support) |
| Map medium | SD card, FAT32, volume label like `QSD-309-101` |
| Factory format | `FORMAT VERSION X08-02-00` |

The primary research sample is the EU 2011 image
`LEAF_2011-2012_QSD-309-101_navi158_eu.img` because it matches the ZE0
generation. The project owner's car is a **US 2011 Leaf**; the US SD dump will
be the ground truth for market-specific layout and version checks.

## Scope

Target data coverage, in priority order:

1. **Dolnośląskie voivodeship** — fully detailed (all roads, addresses,
   names, POIs as far as the format permits).
2. **All of Poland** — complete road network.
3. **Europe** — rough motorway/trunk network for cross-border routing.

Roads and routing come first. Addresses, POIs and names are investigated as
the format allows.

## Verified findings

These are facts checked against the EU 2011 image, not guesses. Details and
offsets live in [`docs/format/`](docs/format/).

- **Image layout.** The `.img` is a raw 8,057,257,984-byte SD card image with
  an MBR. Exactly one partition: type `0x0b` (FAT32), start sector `204802`
  (byte offset `0x06400400`, 104,858,624), 14,745,600 sectors
  (7,549,747,200 bytes), label `QSD-309-101`.
- **Filesystem contents.** 480 files / 39 directories, 5,173,965,667 bytes.
  Top level: `MMAIN001.DAT`, `DRSTR001.DAT`, `CMP.LST`, `MAPAL001/`,
  `REFER001/`, `REFER002/`, `RDSTM001/`, `BICON001/`, `OPNG/`, `SPEECH/`,
  `TMC/`, `VER_INFO/`.
- **Version file.** `VER_INFO/HDD_INFO.TXT` contains `QSD-302-100`,
  `QSD-309-101`, `02-110100-00`, `SDC08-EVEUR`, `11-05`, `470323501005`.
  The same 72-byte block appears byte-identically at image offset `0x06000000`.
- **Firmware version string.** `\x82FX210ECNI.158` starts at `0x00200014`; the
  digits `158` start at `0x0020001f`.
- **Common file header.** Most map files start with a 512-byte header of
  UTF-16**BE** strings: `CLARION`, `HITACHI`, `CLA-NAVI05-01`,
  `FORMAT VERSION X08-02-00`, `DATA VERSION 11/06/27/01`, `V05.00.00`,
  followed by a binary block at `0x180`.
- **`REFER001/*.cmp` + `.ind`.** The compressed address/POI containers are
  fully decoded. `.ind` is a little-endian index:
  `u32 uncompressed_size, u32 compressed_size, u32 chunk_count,
  u32 chunk_size (0x10000), u32 chunk_offset[chunk_count]`.
  Each chunk is an independent zlib stream inside `.cmp`.
  **All 194 `.ind`/`.cmp` pairs in the EU 2011 image decode with exactly the
  declared uncompressed size.**
- **`MAPAL001/` map tiles.** 46 files named `BxxRyyR.DAT` (mesh-like tile
  IDs) plus `LEV3456R.DAT`. Each has the common 512-byte header followed by a
  tile-specific index/descriptor area and many small independent zlib streams.
  The tile-to-latitude/longitude mapping is not yet decoded.
- **`DRSTR001.DAT`.** The only manifest: no header, root node `/` at `0x0000`,
  40 name-first 40-byte node records, then 32-byte directory entries (13-byte
  name + metadata, logical size at `+0x1c`). Each node's listing matches its
  own directory; see [`docs/format/drstr.md`](docs/format/drstr.md).
- **Firmware is packed, not a plain WinCE image.** The 100 MB before the FAT
  partition contains Clarion boot sectors and a firmware container starting
  at `0x00200000` with the strings `82FX210ECNI.158`, `SUM4`,
  `470-2824-34`, `NKOK` and the marker `ECEC`. No valid PE files can be carved
  without unpacking it. Firmware strings reference `HCXCmpLib` / `hcxcmp`
  and SH-4 WinCE binaries such as `Navi.exe`, `NaviAPL`,
  `NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviRouteCC.dll`.
- **Post-partition tail.** The last 402,652,160 bytes of the image are not
  part of the FAT partition and are almost entirely non-zero. Purpose unknown.

## Repository layout

```
README.md                  this overview and documentation index
AGENTS.md                  working rules for contributors and AI agents
TODO.md                    backlog and open tasks
LICENSE                    GPL-3.0
docs/format/               reverse-engineered on-disk formats
docs/research/             external sources, comparisons, open questions
tools/                     small standard-library Python analysis tools
archive/                   git-ignored vendor images and extracts
```

## Tools

All tools are read-only unless an explicit output path is given.

```bash
# Show MBR partition layout of a raw SD image
python3 tools/leafimg.py info /path/to/leaf2011.img

# Dump the common 512-byte map-file header
python3 tools/leafimg.py header REFER001/COORD001.DAT.cmp

# Inspect one .ind index
python3 tools/cmpind.py info REFER001/ADDRE001.DAT.ind

# Decompress a .cmp using its .ind
python3 tools/cmpind.py extract REFER001/ADDRE001.DAT.cmp \
    -o /tmp/ADDRE001.DAT

# Verify every .cmp/.ind pair in a directory
python3 tools/cmpind.py verify REFER001

# Parse DRSTR001.DAT as a directory tree
python3 tools/drstr.py parse DRSTR001.DAT
```

## Documentation

- [SD card and image layout](docs/format/sd-card-layout.md)
- [Common 512-byte file header](docs/format/file-header.md)
- [`.cmp` / `.ind` compressed containers](docs/format/cmp-ind.md)
- [`DRSTR001.DAT` directory index](docs/format/drstr.md)
- [`MAPAL001` map tiles](docs/format/map-tiles.md)
- [`RDSTM001` / `LCTBL001` road data](docs/format/rdstm.md)
- [Firmware and pre-partition area](docs/format/firmware.md)
- [Research sources and external links](docs/research/sources.md)
- [Claims and evidence ledger](docs/research/claims.md) — **start here when
  checking whether something is a fact or a hypothesis**
- [US unit in Europe: region gates](docs/research/us-eu-region.md)
- [Open questions](docs/research/open-questions.md)
- [Data handling and licensing](docs/legal.md)

## External sources

Community and reference material used by this research:

- **LeafSDTools** — community tooling for Leaf map SD cards:
  <https://github.com/developerfromjokela/leafsdtools>
- **LeafSDTools wiki — Updating Map Data**:
  <https://github.com/developerfromjokela/leafsdtools/wiki/Updating-Map-Data>
- **Map image mirror (`files.viaaq.eu`)**:
  - <https://files.viaaq.eu/maps/>
  - <https://files.viaaq.eu/sd-images/>
- **OpenStreetMap** — data source and tagging reference:
  <https://www.openstreetmap.org>
- **ODbL 1.0** — license for OSM-derived data:
  <https://opendatacommons.org/licenses/odbl/1-0/>
- **GNU GPL-3.0** — license for this project's code:
  <https://www.gnu.org/licenses/gpl-3.0.html>

Additional sources, including forum threads, issue trackers and any prior
reverse-engineering work, are collected in
[`docs/research/sources.md`](docs/research/sources.md).

## Data handling and licensing

- **Code:** GPL-3.0-or-later. See [`LICENSE`](LICENSE).
- **OSM-derived data:** ODbL-1.0, with attribution to OpenStreetMap
  contributors.
- **Vendor data:** original Nissan/Clarion/Hitachi images and extracted files
  are **not** distributed with this repository. They live in the git-ignored
  `archive/` directory or outside the repo. Only scripts, documentation,
  hashes and small analysis notes are committed.
- Reverse engineering is done for interoperability and research. Do not
  redistribute proprietary map data.

See [`docs/legal.md`](docs/legal.md) for the full policy.

## Safety

- Always back up the original SD card before touching it, and verify the
  backup hash.
- Test only on a spare SD card.
- A rejected or malformed map can leave the navigation unit unable to boot its
  map application. Treat every write to a card as potentially destructive.
- Nothing in this repository is warranted to work in a car.

## Roadmap

1. Finish the format description: tile grid, `MMAIN001.DAT`, `RDSTM001`,
  `LDTBL`/lookup tables, address/POI record layouts.
2. Decode the firmware container enough to inspect `Navi.exe` and confirm the
  reader/decompressor logic, especially `HCXCmpLib`.
3. Obtain and compare the US 2011 SD dump; document market differences.
4. Build a minimal offline toolchain: read maps → export to an intermediate
  format → regenerate byte-identical containers for unchanged tiles.
5. Only then attempt a synthetic tile and a first on-car test with a spare SD.
