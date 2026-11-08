# IMF: the intermediate map format (OSM → ZE0 writer)

> **Status: design only.** Nothing in this document is validated on a card or
> in a car. IMF v1 is an offline contract between an OSM extractor and the
> ZE0 tile writer; the writer does not exist yet, so no file of this shape has
> been consumed by anything except `tools/imf_check.py`.

IMF is a **file-based, line-oriented intermediate representation**: the last
OSM-shaped artifact before the writer turns geometry and attributes into
`MAPAL001` pages, `DRSTR001.DAT`, `MMAIN001.DAT` and the attribute families.
It exists so that extraction, tiling, validation and writing can be built,
diffed and tested independently — and so that the writer's undocumented
decisions stay in the writer instead of leaking backwards into the extractor.

Related: [osm-pipeline.md](osm-pipeline.md) (source and measured sizes),
[osm-vertical-slice.md](osm-vertical-slice.md) (first end-to-end slice),
[build-profiles.md](build-profiles.md) (tile selection),
[data-coverage.md](data-coverage.md) (what the factory map actually holds),
[../format/map-tiles.md](../format/map-tiles.md) (grid and page layout).

## Pipeline position

```
Geofabrik .osm.pbf (pinned)
  -> osmium tags-filter                    # drop the planet early
  -> extractor (pyosmium / osmium export)  # tags + geometry + relations
  -> IMF  map.imf.jsonl                    # THIS DOCUMENT
  -> writer                                # MAPAL001 / DRSTR / MMAIN / ADDRE / POINT
  -> L1/L2 validation (cardcheck, l2check)
```

Rules that follow from that position:

- The writer **never reads OSM**. If it needs a tag IMF does not carry, the
  tag is added here and to the extractor first, in the same change.
- IMF is **not** the on-card format and not a routing-graph dump. It carries
  no page keys, no compressed streams, no level-of-detail split.
- IMF is **not** a lossless copy of the `.pbf`. Only the whitelisted tags and
  the selected feature classes survive.

## Design rules

1. **No writer-only decisions.** Road-class codes, speed-table steps, name
   offsets, page keys and section-4 layout are absent by design; see
   [Unknowns the writer still decides](#unknowns-the-writer-still-decides).
2. **Deterministic bytes.** Same input ⇒ same file: fixed record order,
   fixed field order, sorted `tiles`, UTF-8, no `NaN`/`Infinity`, and no
   timestamp other than the run's `generated` field and the values copied
   from the snapshot.
3. **Single streaming pass.** Nodes must appear before the ways that use
   them, so a validator only needs one dictionary (id → tile) and never
   rewinds. This is a schema rule, not a performance hint.
4. **Keep the raw tag, add the derived number.** `tags.maxspeed` stays the
   OSM string; `maxspeed_cms` is the integer the writer can use. When the two
   disagree the file is invalid.
5. **Whole cells only.** A record is assigned to a `BxxRyyR` cell, never to a
   polygon or a partial tile (decision recorded in
   [build-profiles.md](build-profiles.md)).

## Encoding

- **JSON Lines** (`*.imf.jsonl`): one JSON object per line, LF-terminated,
  UTF-8, no pretty-printing, no trailing commas, no BOM.
- Optional gzip: `*.imf.jsonl.gz`; the tool detects it by suffix and both
  encodings are equivalent.
- **Line 1 is the header** and is the only header. `imf` is repeated on
  every record so a truncated or concatenated file is detectable.
- **Record order:** header, all `node` records, all `way` records, all
  `relation` records. Nodes must precede every way that references them.
  Within a kind the extractor emits a deterministic order (id order is the
  simplest); the validator does not impose a sort, so a writer is free to
  regroup by tile.
- Unknown fields are **ignored, not rejected**, so the format can grow
  without invalidating old files. Unknown *types* are rejected (`E005`).
- Canonical field order (the order `--assign-tiles` emits):
  - node: `imf, type, id, lat, lon, tile, tags, addr, poi, name`
  - way: `imf, type, id, nodes, tile, tiles, tags, oneway, maxspeed_kmh, maxspeed_cms`
  - relation: `imf, type, id, members, tags`
- A blank line is ignored; any other non-JSON line is `E003`.

### Header

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `imf` | int | yes | format version, `1` |
| `type` | string | yes | `"header"` |
| `generated` | string | no | ISO-8601 UTC time of the extraction run |
| `generator` | string | no | tool and arguments that produced the file |
| `source.name` | string | **yes** | pinned snapshot filename |
| `source.url` | string | no | download URL |
| `source.md5` | string | no | Geofabrik checksum of the snapshot |
| `source.timestamp` | string | no | replication timestamp from the extract |
| `source.sequence` | int | no | replication sequence number |
| `license.database` | string | **yes** | must contain `ODbL` |
| `license.attribution` | string | **yes** | `© OpenStreetMap contributors` |
| `license.url` | string | no | licence or copyright URL |
| `license.attribution_file` | string | no | file shipped with the build output |
| `grid.tile` | string | no | restates the `BxxRyyR` formula |
| `grid.units` | string | no | `WGS84 degrees, 7 decimals` |
| `grid.speed` | string | no | `integer cm/s` |

`source` + `license` are what make the file an ODbL **Derivative Database**
record rather than an anonymous dump; both are validated (`E020`, `E021`).

### Node

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `imf`, `type` | int, string | yes | `1`, `"node"` |
| `id` | string | yes | `n<osm id>`, stable within the snapshot |
| `lat`, `lon` | number | yes | WGS84 decimal degrees, ≤ 7 decimals |
| `tile` | string | yes | cell containing the node (`BxxRyyR`) |
| `tags` | object | no | whitelisted OSM tags, string → string |
| `addr` | object | no | `street`, `housenumber`, `postcode`, `city`, `country` |
| `poi` | object | no | `category`, optional `name`, `brand`, `operator` |
| `name` | string | no | display name without the `tags` wrapper (the node's `name` tag) |

A node is kept when it is a way vertex, a `via` node, or a feature node: a POI
(`amenity`, `shop`, `tourism`, `leisure`, `office` or `healthcare` set), an
address (`addr:street` or `addr:housenumber` set) or a `place`. Every other OSM
node is dropped by the extractor: only 2.9 M of Dolnośląskie's 19.6 M nodes
are way vertices, and the rest carry nothing the card can store. A name alone,
a city alone or `highway=crossing` alone does not make a feature node.

Field rules (`tools/osm_ingest.py`, M5.1c):

- `tags` holds the whitelisted node tags (the POI, Address and Places rows of
  the table below), as a string map.
- `poi.category` is the first present of the six POI keys, written as
  `key=value` (`amenity=fuel`, `shop=bakery`). It is a free string in v1; the
  writer maps it to `POINT` (open question 11).
- `addr` keeps `street`, `housenumber`, `postcode`, `city` and `country` from
  the `addr:*` tags, and is present only when a street or house number is.
- `name` keeps the UTF-8 text. IMF never folds names; the writer does, once,
  with `imf_check.fold_cp1252`: CP1252 letters stay (`ó`), other diacritics
  are dropped (`Zażółć` becomes `Zazólc`), `ł`/`Ł` become `l`/`L`.
  A character with no base letter becomes `?` (`W009`). The folded name must
  fit 128 characters (`W010`), the county/city cap in
  [rdstm.md](rdstm.md#writer-rules-for-names-m39).
- Feature nodes get `W007` (POI without a name) and `W008` (address without a
  street) as warnings; `imf_check.py --strict` turns every warning into a
  failure, which is the gate the build should run.

### Way

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `imf`, `type` | int, string | yes | `1`, `"way"` |
| `id` | string | yes | `w<osm id>` |
| `nodes` | string[] | yes | ≥ 2 node ids, in OSM order, all defined earlier |
| `tile` | string | yes | **anchor cell**: the cell of `nodes[0]` |
| `tiles` | string[] | yes | sorted unique cells touched by `nodes` |
| `tags` | object | no | whitelisted OSM tags |
| `oneway` | string | no | `"yes"`, `"no"`, `"-1"` (only with `highway`) |
| `maxspeed_kmh` | int | no | parsed integer km/h, 1…300 |
| `maxspeed_cms` | int | no | `round_half_up(maxspeed_kmh * 250 / 9)` |

`tile` is derived, not chosen: `tile == tiles[0]` is **not** required (the
sorted list may start east of the anchor), but `tile` must equal the cell of
the first node (`E012`) and `tiles` must equal the exact set of its nodes'
cells (`E013`).

### Relation (subset)

Only three relation types are carried, because only three have a plausible
consumer in the ZE0 data model. `restriction` is checked strictly (`E017`);
`boundary` and `route` only need the tags IMF can map, because no writer
consumes them yet and their role completeness depends on data the card may
not store. The three types:

| `tags.type` | Why it is here | Members that carry the meaning |
| --- | --- | --- |
| `restriction` | turn restrictions, if `INTER`/`FRWAY` can store them | one `from` way, one `to` way, `via` node or way |
| `boundary` + `boundary=administrative` | region/city search, `ICADM`/section-4 index | `outer`/`inner` ways |
| `route` | `ref`/`int_ref` continuity for `FRWAY` | `forward`/`backward` ways |

| Field | Type | Required | Meaning |
| --- | --- | --- | --- |
| `imf`, `type` | int, string | yes | `1`, `"relation"` |
| `id` | string | yes | `r<osm id>` |
| `members` | object[] | yes | `{type, ref, role}`, `type ∈ node/way/relation` |
| `tags` | object | yes | must contain `type`; `restriction`/`boundary` fields as above |

Everything else (`multipolygon` landuse, `route_master`, public transport,
`site`, …) is outside IMF v1 and produces `W005`, not an error.

## Tags carried

The extractor copies these keys from OSM verbatim (values are always
strings). Anything not listed is dropped.

| Group | Keys | Consumer |
| --- | --- | --- |
| Road class | `highway` | writer maps to `LCTBL`/`RDSTM` code |
| Direction | `oneway`, `junction` | writer style bits |
| Speed | `maxspeed` (raw) | writer speed table |
| Access | `access`, `motor_vehicle`, `hgv`, `bus` | access flags / routing |
| Identity | `ref`, `int_ref`, `name`, `name:pl`, `name:en` | name/route tables |
| Physical | `surface`, `lanes`, `bridge`, `tunnel`, `width` | attributes, if a slot exists |
| Address | `addr:housenumber`, `addr:street`, `addr:city`, `addr:postcode` | `ADDRE` |
| POI | `amenity`, `shop`, `tourism`, `leisure`, `office`, `healthcare`, `fuel`, `brand`, `operator` | `POINT` |
| Places | `place`, `population` | section-4 / `ICODE` |
| Admin | `boundary`, `admin_level` | `ICADM` / section 4 |
| Restrictions | `restriction`, `restriction:<mode>` | `INTER`/`FRWAY`, if supported |

Deliberately **not** carried in v1: `building`, `landuse`, `natural`,
`waterway`, `power`, `man_made`, `source:*`, `note:*`, lifecycle prefixes.
The factory map has no proven polygon/area record family, so importing them
would create data with no destination (see
[data-coverage.md](data-coverage.md)).

## Coordinates, tiles and units

### Coordinates

- WGS84 decimal degrees as JSON numbers, at most **7 decimals** (≈ 1.1 cm).
  OSM's native precision is 1e-7°, so this is lossless.
- Out-of-range, `NaN` or `Infinity` is `E008`. JSON does not allow them, but
  Python's decoder accepts them, so the validator checks explicitly.
- No altitude, no node timestamps, no user metadata.

### Tile assignment

One cell is 8 × 8 grid units; B and R are **hexadecimal**:

```
lat_min = int(B, 16) * 2/3          lat_max = lat_min + 16/3
lon_max = 108 - int(R, 16)          lon_min = lon_max - 8
```

Cells are half-open: `[lat_min, lat_max)` × `[lon_min, lon_max)`. Because the
cell is 8 units wide, **B and R are multiples of 8** in every real cell; a
value like `R057` would overlap its neighbours and is rejected (`E010`).
Neighbouring columns therefore differ by 8 in R, e.g. `R058` (12…20 °E) and
`R050` (20…28 °E), not by 1.

Inverse used by the extractor and the validator:

```
B = 8 * floor(lat * 3 / 16)
R = 8 * (ceil((108 - lon) / 8) - 1)
```

| Example | lat | lon | cell |
| --- | --- | --- | --- |
| Wrocław | 51.110 | 17.030 | `B48R058R` |
| just west of 20 °E | 51.100 | 19.999 | `B48R058R` |
| just east of 20 °E | 51.100 | 20.001 | `B48R050R` |
| Cologne | 50.94 | 6.96 | `B48R060R` |
| Norwegian Sea | 60.00 | −6.00 | `B58R070R` |

Whole-cell assignment has one deliberate consequence: a way that crosses a
cell edge keeps **all** its vertices and lists both cells in `tiles`. It is
not clipped, not duplicated and not split by IMF; what the writer does at the
page boundary is a writer decision.

Dolnośląskie's land area (≈ 50.0–51.8 °N, 14.8–17.8 °E) falls inside the single
cell `B48R058R` by this arithmetic. `build-profiles.md` estimates "2–3 tiles";
that difference is a profile/buffer question, not an IMF rule, and is listed
under open questions rather than silently resolved here.

### Speed

`maxspeed` is the only numeric attribute with a physical unit, and the ZE0
firmware is integer-only. IMF stores **integer cm/s**:

```
maxspeed_cms = (kmh * 250 + 4) // 9      # round half up, km/h -> cm/s
maxspeed_kmh = (cms * 9 + 125) // 250    # cm/s -> nearest km/h
```

1 cm/s = 0.036 km/h, so rounding costs at most 0.018 km/h and every integer
km/h from 1 to 300 round-trips exactly (`--selftest` checks all 300). The
writer may quantise to its own table afterwards; IMF does not know the table.

`tags.maxspeed` keeps the raw OSM string (`"50"`, `"none"`, `"PL:urban"`,
`"walk"`). `maxspeed_kmh` is present **iff** the raw value is a plain integer;
if it is, the two must agree (`E015`).

### Lengths and geometry

No lengths, bearings or bounding boxes are stored. They are derived from the
node coordinates by the writer with whatever projection and rounding it uses.
This keeps IMF units to exactly two: degrees and cm/s.

## Stable IDs

- `id` is `n`/`w`/`r` + the positive OSM id, e.g. `w900000001`. The prefix is
  redundant with `type` on purpose: a record copied into the wrong section is
  rejected (`E007`), and OSM ids are only unique *within* a type.
- IMF never renumbers. Two builds from the same snapshot produce identical
  ids; a rebuild from a newer snapshot changes only features OSM changed.
- OSM ids are stable but **not permanent**: a way may be split or merged, and
  a POI node may be replaced. IMF therefore makes no cross-snapshot identity
  promise; it makes a *within-file* one.
- Attribute records that the card addresses by name (street + house number)
  cannot use the OSM id, because `ADDRE`/`POINT` ids are a separate space
  derived from coordinates. The writer generates those ids; IMF must not.

## Provenance and ODbL

IMF is an extract of an ODbL 1.0 database, so a build that ships it (or the
card image made from it) must attribute OpenStreetMap. The header carries the
minimum needed to do that mechanically:

```json
"source":  {"name": "dolnoslaskie-latest.osm.pbf", "md5": "0a78af…",
            "timestamp": "2026-11-03T21:24:23Z", "sequence": 4024},
"license": {"database": "ODbL-1.0",
            "attribution": "© OpenStreetMap contributors",
            "url": "https://www.openstreetmap.org/copyright",
            "attribution_file": "ODbL.txt"}
```

- Copy `source.*` into the build's `manifest.json` next to the output, so a
  card image can be traced back to a dated snapshot (`build-profiles.md`).
- `license.attribution_file` names the file that must travel with a
  distributed image. **Where** it lives on a FAT32 card without looking like
  vendor content is an open decision; this document only guarantees the
  string exists in every IMF file.
- Never strip the header to save bytes. A header-less IMF file is invalid
  (`E001`/`E020`/`E021`), which also prevents "anonymous" derivatives.
- `--sample` output is synthetic; its header names the real Dolnośląskie
  snapshot only as an example of the fields, not as a claim that the sample's
  geometry came from it.

## Validation: `tools/imf_check.py`

Standard library only, no vendor data:

```bash
python3 tools/imf_check.py map.imf.jsonl              # human report
python3 tools/imf_check.py map.imf.jsonl --json       # machine report
python3 tools/imf_check.py map.imf.jsonl --strict     # warnings fail too (build gate)
python3 tools/imf_check.py map.imf.jsonl.gz           # gzip is detected
python3 tools/imf_check.py in.imf.jsonl --assign-tiles -o out.imf.jsonl
python3 tools/imf_check.py --sample -o map.imf.jsonl
python3 tools/imf_check.py --sample > map.imf.jsonl    # report goes to stderr
python3 tools/imf_check.py --selftest
```

Without `-o`, `--sample` writes the JSONL to stdout and its validation report
to stderr, so a plain redirect produces a clean file.

Exit codes: `0` valid (warnings allowed), `1` validation errors, `2` usage or
I/O error. `--sample` and `--assign-tiles` validate their own output and
return that result. In the report, the tile inventory counts nodes by their
own cell and ways by their anchor cell, so a way that spans two cells appears
only under its anchor.

| Code | Rule |
| --- | --- |
| `E001` | first record is not the header, or a second header appears |
| `E002` | `imf` is missing or not `1` |
| `E003` | line is not valid JSON |
| `E004` | record is missing a required field |
| `E005` | unknown record `type` |
| `E006` | duplicate id within a kind |
| `E007` | malformed id, or prefix does not match `type` |
| `E008` | coordinate not finite or outside WGS84 |
| `E009` | node `tile` is not the cell of its coordinates |
| `E010` | malformed tile id, or a way with fewer than two nodes |
| `E011` | way node ref does not resolve (nodes must precede ways) |
| `E012` | way `tile` is not the cell of its first node |
| `E013` | way `tiles` is not the exact sorted set of its nodes' cells |
| `E014` | `oneway` not `yes`/`no`/`-1`, or set on a non-highway way |
| `E015` | `maxspeed` out of 1…300, or `maxspeed_cms` disagrees |
| `E016` | relation member reference does not resolve |
| `E017` | restriction relation lacks the tag or a `from`/`via`/`to` member |
| `E018` | `tags`/`addr`/`poi` is not a string → string object |
| `E019` | a way repeats the same node consecutively |
| `E020` | header lacks ODbL database/attribution |
| `E021` | header lacks `source.name` |
| `E022` | `access` value outside the supported set |

Warnings (printed, never fatal unless `--strict`): `W001` highway way without `name`, `W002`
highway way without numeric `maxspeed`, `W003` unknown `highway` value,
`W004` unused node, `W005` relation outside the subset, `W006` routing tag
without `highway`, `W007` POI node without a name, `W008` address node without
a street, `W009` node name with no CP1252 form, `W010` node name over 128
characters after folding.

`--selftest` builds one valid synthetic file, then one mutation per error
code, and fails if a code in `RULES` has no case. It also cross-checks the
tile inverse against `tools/mesh_grid.py`, the km/h ↔ cm/s round-trip for
1…300, that warnings stay non-fatal, and that `--assign-tiles` restores a
file with the derived fields stripped.

## Worked example: a Dolnośląskie motorway

Synthetic ids and coordinates, real tile: an `A8` segment west of Wrocław,
one address node, and a restriction relation on a street. The full file is
`python3 tools/imf_check.py --sample`; this is the relevant excerpt. Records
between the shown ones are elided — the real file is contiguous and each
`nodes`/member reference resolves.

```jsonl
{"imf":1,"type":"header","generated":"2026-11-05T00:00:00Z","generator":"tools/imf_check.py --sample","source":{"name":"dolnoslaskie-latest.osm.pbf","url":"https://download.geofabrik.de/europe/poland/dolnoslaskie-latest.osm.pbf","md5":"0a78af165163f38a1e22737888a9fd57","timestamp":"2026-11-03T21:24:23Z","sequence":4024},"license":{"database":"ODbL-1.0","attribution":"© OpenStreetMap contributors","url":"https://www.openstreetmap.org/copyright","attribution_file":"ODbL.txt"},"grid":{"tile":"BxxRyyR (hex): lat_min=int(B,16)*2/3, lon_max=108-int(R,16)","units":"WGS84 degrees, 7 decimals","speed":"integer cm/s"}}
{"imf":1,"type":"node","id":"n900000001","lat":51.109,"lon":16.88,"tile":"B48R058R"}
{"imf":1,"type":"node","id":"n900000002","lat":51.112,"lon":16.92,"tile":"B48R058R"}
{"imf":1,"type":"node","id":"n900000003","lat":51.115,"lon":16.96,"tile":"B48R058R"}
{"imf":1,"type":"node","id":"n900000004","lat":51.118,"lon":17.0,"tile":"B48R058R"}
{"imf":1,"type":"node","id":"n900000020","lat":51.11,"lon":16.9,"tile":"B48R058R","addr":{"street":"ul. Legnicka","housenumber":"7","postcode":"54-001","city":"Wrocław"}}
{"imf":1,"type":"way","id":"w900000001","nodes":["n900000001","n900000002","n900000003","n900000004"],"tile":"B48R058R","tiles":["B48R058R"],"tags":{"highway":"motorway","ref":"A8","name":"Autostrada A8","oneway":"yes","maxspeed":"140","lanes":"2","surface":"asphalt"},"oneway":"yes","maxspeed_kmh":140,"maxspeed_cms":3889}
{"imf":1,"type":"relation","id":"r900000100","members":[{"type":"way","ref":"w900000005","role":"from"},{"type":"node","ref":"n900000021","role":"via"},{"type":"way","ref":"w900000006","role":"to"}],"tags":{"type":"restriction","restriction":"no_left_turn"}}
```

Reading the way record:

- `id` `w900000001` — OSM way id, stable for this snapshot. The `w` prefix is
  checked against `type`.
- `nodes` — four vertices, already defined above (the schema requires it).
  `n900000020` is not one of them: it belongs to a different street and is
  kept because it carries `addr`, not because a way uses it.
- `tile` / `tiles` — both `B48R058R`, because every vertex is inside
  48.00–53.33 °N, 12–20 °E. `tile` is the *anchor* (first node) cell; `tiles`
  is what a whole-cell build must carry. A way from `n900000060` to
  `n900000061` (19.999 → 20.001 °E) has `tile: B48R058R` and
  `tiles: ["B48R050R","B48R058R"]`.
- `tags` — the raw OSM view, including `maxspeed:"140"` and `lanes:"2"`.
  `highway:"motorway"` is **not** turned into a numeric class: that mapping is
  the writer's (see below).
- `oneway` / `maxspeed_kmh` / `maxspeed_cms` — the derived, unit-bearing
  fields. 140 km/h → 3889 cm/s; 50 km/h → 1389 cm/s. `-1` would mean
  "reversed direction", not "no".
- The address node carries `addr` and no `highway`; POI nodes in the full
  file carry `poi.category` plus `addr`. That pair (street + house number) is
  how the card joins POIs to addresses — not a shared id.

## Unknowns the writer still decides

These are intentionally **absent** from IMF. The writer must resolve them
against the factory format, and each one should become its own claim before
it is implemented.

1. **Road class mapping.** `highway=motorway…residential` → the `LCTBL001`
   road-class column / `RDSTM001` code. Polish helper tags
   (`highway:category:pl` 1–4, `highway:class:pl` A/S/GP/G/Z/L/D) are the
   natural bridge and are carried in `tags`, but the numeric code is unknown.
   Link roads, `track`, `service` and `living_street` need an explicit
   include/drop rule per build profile.
2. **Speed table.** No speed field has been found in `RDSTM001`/`LCTBL001`
   ([data-coverage.md](data-coverage.md)). If the format stores speed at all,
   it is likely quantised; IMF gives exact cm/s and the writer picks the step
   and the fallback for the ~88 % of ways without `maxspeed`.
3. **Names.** Three separate unknowns: (a) does the unit render
   `ą ć ę ł ń ó ś ź ż` or is transliteration required; (b) how the name
   string table dedupes and what offset unit shape header word 4 uses;
   (c) which of `name`, `name:pl`, `ref` wins when several are present.
   `LCTBL001` holds Latin-2 strings, which suggests lossy Polish support.
4. **Intra-tile page key.** The `(A, B, tag)` stream key
   (`A = 32768 + lat*192`, `B = 52736 + lon*128`), the 4-unit sub-lattice and
   the even/odd record pair. IMF stops at the cell boundary; the writer
   decides page ownership and what happens to a shape that spans pages.
5. **Geometry quantisation.** The runtime bound is `0..2047` per mesh with
   bit-packed deltas, so the writer must choose the intra-page unit and
   rounding. IMF's 1e-7° is enough for any choice.
6. **Intersections.** `INTER0nn` records exist in the factory map; IMF has
   shared node ids, which is the join key, but no intersection record.
7. **One-way and style bits.** `0x201e` = two-way and `0x001e` = ferry are a
   hypothesis. IMF gives `yes`/`no`/`-1`; the bit encoding is unknown.
8. **Attributes with no known slot.** `lanes`, `surface`, `bridge`, `tunnel`,
   `width` are carried as tags but no record family is confirmed to hold
   them.
9. **Addresses.** `ADDRE`/`POINT` share ids and are joined by street + house
   number; the id derivation from coordinates is not decoded. Way addresses
   (two thirds of Polish addresses) need a point-on-building rule.
10. **Turn restrictions.** IMF carries the `restriction` relation; whether
    `INTER`/`FRWAY` can store it is unresolved. Do not delete the relation
    from IMF until that is answered — it is cheap and unrecoverable later.
11. **POI taxonomy.** `POINT` has category, sub-category, detailed code and a
    dndc id, plus icon ids from `BICON001`. `poi.category` is a free string in
    IMF v1; the writer needs the real taxonomy and a fallback icon.
12. **Admin/place index.** Section 4 is a name index, not geometry. IMF has
    `place` nodes and `boundary` relations; there is no section-4 encoder.
13. **Level of detail.** Which records appear at which zoom level
    (`0x1ac` table) is a writer decision driven by the factory tiles.

## Open questions

1. Dolnośląskie is one cell by bbox arithmetic (`B48R058R`) but
   `build-profiles.md` says 2–3 tiles. Confirm against a real polygon and the
   intended border buffer before the first multi-tile build.
2. Is JSON Lines fast enough for a Poland-wide extract (~165 MB raw roads,
   plus nodes)? If not, the same schema can be moved to a length-prefixed
   binary encoding without changing the fields; the tool would need a second
   reader.
3. Does gzip change the bytes of a build in a way that matters for
   reproducibility? Currently the two encodings are treated as equivalent
   inputs, and only the uncompressed form is hashed.
4. Should `place` nodes become `node` records with `tags.place` (as here) or
   their own type? v1 uses the tag; revisit if section 4 needs a stronger
   index.
5. Is `access` the right level of detail, or should IMF carry a computed
   `routable` boolean from the profile? Computing it early would hide the
   profile decision from the writer.

## References

- [osm-pipeline.md](osm-pipeline.md) — snapshot, measured sizes, tag coverage
- [build-profiles.md](build-profiles.md) — whole-tile selection, attribution
- [data-coverage.md](data-coverage.md) — what the factory map provably holds
- [../format/map-tiles.md](../format/map-tiles.md) — grid, page keys, section 4
- [../format/rdstm.md](../format/rdstm.md) — road attribute schema
- ODbL 1.0: <https://opendatacommons.org/licenses/odbl/1-0/>
- OSM attribution: <https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>
