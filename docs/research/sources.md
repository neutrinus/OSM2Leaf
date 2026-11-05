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
