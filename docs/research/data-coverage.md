# Data coverage: what the factory map contains vs what OSM has

This is a two-column question:

1. **What is actually in the factory ZE0 map?**
2. **What does OpenStreetMap have that could fill the same slot?**

Do not assume that “OSM has buildings” means “the unit can display buildings”.

> **Evidence status:** the “factory map” column is based on decoded files and
> is `VERIFIED` where a record family is named; `UNKNOWN` means we have not
> found the data, not that it is absent. The OSM column is measured for
> Dolnośląskie where noted, otherwise general OSM coverage.

## Matrix

| Category | Factory ZE0 map | Evidence | OSM | Notes |
| --- | --- | --- | --- | --- |
| Road network | **Yes** | `MAPAL001` geometry + `RDSTM001` attributes; `LCTBL001` 12-column road schema | Yes (`highway=*`) | Core target. |
| Street/place names | **Yes** | `LCTBL001` 328,628 Latin-2 strings; `ICODE001` place names | Yes, but only 20.3 % of drivable DS ways have `name` | `name` is already Polish; `name:pl` is rare. |
| Road numbers / route refs | **Yes** | `LCTBL001` `road no` column; `FRWAY` route refs (`A1`, `E70`) | Yes (`ref`, `int_ref`) | Only 4.7 % of DS ways have `ref`. |
| Addresses | **Likely yes** | `ADDRE0nn` family; layout not yet decoded | Yes (`addr:*`), but 2/3 are on **ways/buildings**, not nodes | 374,718 way addresses vs 193,913 node addresses in DS. |
| POIs | **Yes** | `POINT0nn`: name, address, category/sub-category, detailed code, dndc-id | Yes (`amenity`, `shop`, `tourism`, …) | POINT has **no coordinates**; the join to geometry is unknown. |
| Intersections | **Yes** | `INTER0nn` 12-byte records + node refs | Implicit in OSM ways | The unit has explicit intersection records. |
| Freeways / route network | **Yes** | `FRWAY0nn` route refs + mesh ids | Yes (`highway=motorway/trunk`, route relations) | Mesh-id encoding unresolved. |
| Administrative areas | **Yes** | `ICADM0nn` 33 country blocks + admin terminology | Yes (`boundary=administrative`, `admin_level`) | Country-level terminology is clear; lower levels unknown. |
| Postal codes | **Yes** | `ZCODE0nn` tries; `ZIPFR001` masks | Yes (`addr:postcode`, postal boundaries) | ZCODE stores tries, not strings. |
| Buildings | **Unknown / not found** | No building/footprint record family identified; tile grammar not decoded | Yes (`building=*`) | Very likely too large for a 2011 navi and maybe not rendered. |
| Land use / forest | **Unknown / not found** | No polygon/landcover record family identified | Yes (`landuse=forest`, `natural=wood`) | May exist as background polygons inside `MAPAL001`; unproven. |
| Water / coastline | **Unknown / not found** | No explicit water record family identified | Yes (`natural=water`, `waterway`) | The display almost certainly has a coastline/water background, but we cannot yet point to a record. |
| Speed limits | **Not found** | No speed field in `RDSTM001`/`LCTBL001` so far | Partial (12.3 % of DS drivable ways) | May be in `INTER`/`FRWAY`; unknown. |
| Turn restrictions | **Not found** | Not in `RDSTM001`/`LCTBL001`; `INTER`/`FRWAY` unresolved | Yes (relations) | Critical for routing quality; 3,987 relations in DS alone. |
| Icons / symbols | **Yes** | `BICON001`, `OPNG`, `BASSW7C` asset container | Icons are rendering assets, not OSM data | Needed for POI display. |
| Voice / TTS | **Yes** | `SPEECH/*` AGM/TTS/GID archives | Not OSM | Out of scope for the map compiler. |
| Traffic / TMC | **Yes** | `TMC/reception.dat` | Separate data source | Not a map-compile input. |

## What is proven vs merely plausible

**Proven present in the factory map:**

- roads and their attributes/names (`MAPAL001`, `RDSTM001`, `LCTBL001`)
- addresses and POIs (`ADDRE`, `POINT` families exist; records partly decoded)
- intersections, freeways, admin terminology, postal tries
- icons and voice assets

**Not found yet (do not promise):**

- building footprints
- forest/landuse polygons
- explicit water polygons
- speed limits
- turn restrictions

These may be inside the undecoded `MAPAL001` tile grammar. The tile payloads
are vector records, not raster, so polygons are technically possible. But we
have no record type or field that maps to them yet.

## What OSM has

OSM has **all** of the categories above, but completeness varies strongly:

- roads: good coverage, especially the national/voivodeship network
- names: only ~20 % of drivable ways in Dolnośląskie
- addresses: good, but mostly on building ways, not nodes
- POIs: good
- buildings/landuse/water: present, but completeness and granularity vary;
  importing all of them could exceed the unit's data model and card budget
- turn restrictions: present as relations; whether the format can store them
  is unknown
- speed limits: present on only ~12 % of drivable ways

## Practical conclusion

The safe first target is a **road + name + address + POI** map, because those
slots are confirmed in the factory format. Buildings, forest and water should
be treated as a **second phase**: first prove that the format has a polygon/
area record and that the unit renders it, then decide whether to import them.

The single highest-value experiment is to decode one dense tile (e.g.
`B48R060R`, Cologne/Benelux) and identify the non-default record types. If
that tile contains area/polygon records, buildings/landuse/water become
plausible; if it contains only road shapes, the factory map is a road map and
OSM landcover is out of scope.

## Open questions

1. Does `MAPAL001` contain polygon/area record types, or only road geometry?
2. Where are POI/address coordinates stored, if not in `POINT`/`ADDRE`?
3. Can `INTER`/`FRWAY` express turn restrictions and speed limits?
4. Does the unit render Polish diacritics, or is transliteration required?
5. What is the real data budget per tile once the record grammar is known?
