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

## Open questions

1. **Charset**: can the unit render `ą ć ę ł ń ó ś ź ż`? This decides the
   string-table design and whether transliteration is needed.
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
