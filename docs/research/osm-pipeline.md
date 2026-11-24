# OSM data pipeline

Recommended pipeline for this project's compiler. All numbers were measured
on a pinned Geofabrik snapshot on 2026-11-05.

## Recommendation

```
Geofabrik .osm.pbf (pinned dated snapshot)
  -> osmium tags-filter (roads, addresses, POIs, restrictions, boundaries)
  -> pyosmium / osmium encoder
  -> our compact binary records + manifest.json
```

No database, no Overpass, no tile server in the build path. The compiler only
needs tags + geometry; a routing engine can be added later if needed.

## Why this pipeline

- **Geofabrik `.osm.pbf`** gives a stable, dated snapshot with checksums and
  regional extracts.
- **`osmium tags-filter`** removes most of the planet early, so later stages
  are small and fast.
- **`pyosmium`** streams and gives direct access to tags/geometry without a
  PostGIS service.
- **Own binary records** keep the compiler independent of a rendering or
  routing stack.

Alternatives considered:

| Approach | Verdict |
| --- | --- |
| Overpass API | Rejected for builds: rate limits, no stable snapshot, 502s observed. Useful only for tiny ad-hoc queries. |
| `osm2pgsql` + PostGIS | Rejected for v1: adds a service and a second source of truth. Reconsider if spatial joins become painful. |
| `tilemaker` / `planetiler` | Rejected for routing: they produce lossy MVT, a rendering model, not a routing model. |
| `osmium` + own encoder | **Chosen**: minimal, reproducible, offline. |

## Measured data (Dolnośląskie)

Snapshot: `dolnoslaskie-latest.osm.pbf`, 182,090,350 bytes, md5
`0a78af165163f38a1e22737888a9fd57`, replication timestamp
`2026-11-03T21:24:23Z`, sequence 4024.

- 19,645,747 nodes / 2,601,698 ways / 24,235 relations
- 576,341 `highway` ways; **362,586 drivable ways = 94,123 km**
- 0 broken geometries; 3,389,296 vertices / 2,914,509 unique nodes
- all drivable roads encode to **18.8 MB raw / 13.7 MB zlib**
- motorway–secondary only: **1.0 MB**

Attribute coverage is the real constraint:

| Tag | Coverage of drivable ways |
| --- | --: |
| `name` | 20.3 % |
| `maxspeed` | 12.3 % |
| `surface` | 32.3 % |
| `lanes` | 10.7 % |
| `ref` | 4.7 % |

`name:pl` exists on only 581 ways — `name` is already Polish. Do not expect
the unit's map to be as complete as OSM; plan fallbacks.

Addresses: 193,913 node addresses but **374,718 way addresses** (taginfo).
Two thirds of Polish addresses are on buildings, so a node-only reader loses
most of them.

Polish helper tags are a good class bridge: `highway:category:pl`
(1 = krajowa … 4 = gminna) on 25,149 DS ways; `highway:class:pl`
(A/S/GP/G/Z/L/D) on 7,065.

Extrapolated sizes: Poland all roads ~165 MB; core Poland ~11 MB; Europe
motorway+trunk ~67 MB. These fit the card's ~2.35 GB free space easily.

## Commands

```bash
# Pin a snapshot
curl -O https://download.geofabrik.de/europe/poland-latest.osm.pbf
curl -O https://download.geofabrik.de/europe/poland-latest.osm.pbf.md5
md5sum -c poland-latest.osm.pbf.md5

# Small test fixture (city)
curl -O https://download.bbbike.org/osm/bbbike/Wroclaw/Wroclaw.osm.pbf

# Filter to what the compiler needs
osmium tags-filter poland-latest.osm.pbf \
  w/highway w/addr:* n/addr:* n/place w/boundary r/boundary \
  w/amenity n/amenity w/shop n/shop w/tourism n/tourism \
  -o pl-core.osm.pbf --overwrite

# Optional: a voivodeship cut for tests (not for the final build)
osmium extract -p dolnoslaskie.poly poland-latest.osm.pbf \
  -o dolnoslaskie.osm.pbf --strategy smart --overwrite
```

Use the **Poland** extract, not a voivodeship cut, for the final build:
Dolnośląskie borders Germany and Czechia, and a voivodeship cut severs the
cross-border roads that cross-border routing depends on.

## Polish glyph coverage (M4.87, EU2011)

The map text renderer does **not** draw all Polish letters. Evidence:
EXP-2026-11-22-M4.87-polish-glyphs (claims C-7880–C-7889).

- The named `xglXtpDrawXanaviCharacter` export of `XGLDLL.dll` is a 2-byte
  no-op (`rts; mov #0,r0` at VA `0x030fd118`) — it draws nothing. Real names go
  through `XGLDLL` → `RASTERIZER_DLL.dll` `DCW_Raster`; the name font is the
  FDL blob `dig_pfont_ucs_iso88591_hei_wx` at VA `0x03431020` (magic
  `FDL Font`), returned by `DCW_Font_getNamFontAddr` (`0x0344fb08`).
- Its cmap at VA `0x034310f4` covers **U+0001..U+011F only**. Per letter:

  | Keep (glyph present) | Transliterate (no glyph) |
  | --- | --- |
  | `Ą ą` U+0104/0105 | `Ł ł` U+0141/0142 → `L l` |
  | `Ć ć` U+0106/0107 | `Ń ń` U+0143/0144 → `N n` |
  | `Ę ę` U+0118/0119 | `Ś ś` U+015A/015B → `S s` |
  | `Ó ó` U+00D3/00F3 | `Ź ź` U+0179/017A → `Z z` |
  | | `Ż ż` U+017B/017C → `Z z` |

  A code point past U+011F is a cmap miss (notdef); `DCWx_findFontData`
  returns 0 at `0x03451ede`. Reproduce with
  `python3 tools/fdl_font.py archive/head256.img --font-va 0x03431020 --image-start 0x200200`.

**Compiler recommendation:** drive transliteration from this 10-letter table in
one place (M5.80), leave the 8 present letters unchanged, and keep the factory
strings' ISO-8859-2 encoding (M4.13). **Open risk:** the byte→Unicode conversion
between the card's single-byte text and this Unicode cmap was not located; until
an L3/L4 run confirms it, cmap presence does not prove the letter renders
correctly. The falsifier was checked — the factory `LCTBL001.DAT` does store
Polish diacritics (20,294 Polish-only letters), so the font, not the data, is
the limit for the 10 missing letters.

## Road numbers and shields: proposed Polish `ref` mapping (M4.90, EU2011)

Evidence: EXP-2026-11-22-M4.90-road-shields (claims C-7910–C-7919). The factory
map stores a road number only as the `2=` part of the `;`-separated text
`1=NAME;2=REF` of a name entry in the odd partner record's names section; the
even road-shape record's shape word `w4` is the word offset of that entry. The
entry words are constant (`00ff 2800 0000 0000 ln`), so there is **no separate
shield-type field**: the shield family is read from the reference syntax, and
the shape class/`w3` tracks the road category, not the national/European
choice. On the Polish part of the EU2011 cross-border tile `A4` and `E40`
together occur only as one colon-joined string `2=A4:E40` (129 occurrences;
bare `A4` 0, bare `E40` 0), while `94` (19) and `B6`/`S8` (4 each) occur bare
and `DK94` never does (0). **Compiler proposal:** write Polish `ref` as
`2=<digits>` with the `DK` prefix dropped (`DK94` → `2=94`); write motorway and
expressway refs with their letter (`A4` → `2=A4`, `S8` → `2=S8`); append an
`int_ref` European number to the national ref with a colon rather than
emitting it alone (`A4`+`E40` → `2=A4:E40`, `94`+`E40` → `2=94:E40`), using
further colon-separated terms for multiple E routes (the factory section 4
contains `2=A8:E56:E552`); keep `1=NAME` optional in the same text. This is a
data-side mapping, not a firmware-confirmed shield selection (rule 13): the
renderer's glyph choice for each family still needs an L3/L4 run.

### Writer implementation (M4.95, EU2011)

`tools/tilewriter.py` now emits that mapping as the names-section label of the
odd road partner: `road_label(tags)` composes `1=NAME`, `2=REF` or both, so a
nameless ref-bearing way still gets its reference (all 681 `A4` ways in the
Dolnośląskie extract are nameless). OSM `ref` is normalised (`DK94` → `94`,
whitespace and case folded) and `int_ref` E-routes are normalised before
composition (`E 40` → `E40`). **The E-route suffix is family-scoped**: it is
appended only where the factory shows a colon family (`A#`, `B#`, bare digits
→ `digit:E`), never for `S#`/`L#`/other families. In particular `S8` + `E 67`
stays `2=S8` — appending it would make `2=S8:E67`, which M4.90's family table
classifies `other-alpha` (no `S\d+:E\d+` family). Thus `A4`+`E 40` →
`2=A4:E40`, `S8` → `2=S8`, `94` → `2=94`. Evidence and controls:
EXP-2026-11-23-M4.95-ref-shield-writer. The firmware glyph choice remains an
L3/L4 question (rule 13); this is a data-side mapping only.

## OSM tag → POI category profile (M5.73, EU2011)

The POI writer (M5.18/M5.63) needs one byte-aligned `POINT` category code per
OSM object. `tools/osm_ingest.py` emits `poi.category = key=value` and keeps the
`brand`/`operator`/`name` tags; `profiles/poi-categories.json` is the ordered
rule set that resolves those to a code (first match by ascending priority).
`tools/poi_category_profile.py --selftest` validates every targeted code
against the generated M4.88 table (`docs/format/poi-categories.md`) and maps a
synthetic fixture of one object per rule; `validate` prints the cross-check as
JSON. Evidence: EXP-2026-11-24-M5.73-poi-category-profile, C-10140–C-10149.

| Required OSM category | Target code(s) | Status |
| --- | --- | --- |
| `amenity=fuel` | `0x0190` generic; brand `0x0193` BP, `0x01bc` Aral | mapped |
| `amenity=restaurant`/`cafe`/`fast_food`/`bar`/`pub` | `0x0391` | mapped |
| `tourism=hotel`/`motel`/`guest_house` | `0x0dac` generic; brand `0x0dad` Best Western, `0x0db7` Hilton, `0x0db8` Holiday Inn | mapped |
| `shop=supermarket` | brand `0x01a1` Carrefour, `0x01be` Intermarche, `0x0195` ASDA | brand-only |
| `amenity=charging_station` | — | UNMAPPED (separate REFER002 EV layer, M5.79) |
| `amenity=parking` | — | UNMAPPED (glyph 20 exists, code unknown — OQ-20) |
| `amenity=hospital`/`clinic`/`doctors` | — | UNMAPPED |
| `amenity=pharmacy` | — | UNMAPPED (glyph 19 exists, code unknown — OQ-20) |
| `amenity=bank`/`atm` | — | UNMAPPED |
| `railway=station`/`public_transport=station` | — | UNMAPPED |
| `aeroway=aerodrome`/`airport` | — | UNMAPPED |

Only four of the eleven categories have factory category codes; the other
seven are deliberately left `code: null` rather than guessed. The task
falsifier ("a rule targets a code with zero records on the factory card") is
enforced by `validate`: a fabricated or absent code fails the run. Generic
supermarket has **no** category code — the factory stores brand codes only —
so an unbranded `shop=supermarket` is also UNMAPPED.

**Tooling decision.** `tools/profile_validate.py` validates *build* profiles
(region/coverage/tiles, schema v2); it is not a validator for a tag→code
table and would reject this file with `E002` as it already rejects the
non-build `profiles/pl-glyphs.json`. The runnable gate for this profile is
therefore `tools/poi_category_profile.py --selftest` (picked up by
`tools/selftest.py`). The existing four build profiles remain unchanged.

This is a data-side mapping only (rule 13): no firmware reader VA for the
category→icon table is known (C-988), so nothing here claims `CONFIRMED`.

## Open questions

1. **Charset** — answered for the glyph table by M4.87 (8/18 present); still
   open: the byte→Unicode conversion into the FDL cmap (see above).
2. **Turn restrictions**: does the format have a slot for them? 3,987
   restriction relations exist in one voivodeship alone.
3. **Tile granularity**: profiles currently ship whole tiles. See
   [build-profiles.md](build-profiles.md).
4. **`track`/`service`**: 59 %/12 % of road kilometres. Keep them (card budget
   allows ~250–330 MB) or drop them for zoom-level reasons?
5. **ODbL attribution**: where does it live on a FAT32 card without looking
   like vendor content?

## Sources

- <https://download.geofabrik.de/europe/poland-latest.osm.pbf>
- <https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf>
- <https://download.openstreetmap.fr/extracts/europe/poland/>
- <https://download.bbbike.org/osm/bbbike/Wroclaw/>
- <https://taginfo.geofabrik.de/europe:poland:dolnoslaskie/>
- <https://osmcode.org/file-formats-manual/>
- <https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>
