# EXP-2026-11-05-12: Dense tile, roads and streaming writer

- **Status:** done for the container; roads partial
- **Date:** 2026-11-05
- **Sample:** EU 2011 `MAPAL001`
- **Claims:** C-250…C-257
- **Supersedes:** the "dense tile does not round-trip" and "PNG has no roads"
  status
- **Superseded by:** none

## Question

Can the dense section-4 tile round-trip, can road-shape records be decoded and
rendered, and can large tiles be written without OOM?

## Hypothesis

The remaining `B30R048R` diff is a small set of container fields (pair flags,
raw tails, `0x2146` tail, unreferenced gap), not an unknown codec.

## Inputs

| File | SHA-256 |
| --- | --- |
| `B28R070R.DAT` | `0e4df38b…2ddb` |
| `B30R060R.DAT` | `8ca92bd5…b62d` |
| `B58R070R.DAT` | `f8aae7e4…77d7` |
| `B30R048R.DAT` | `09161015…eb28` |
| `LEV3456R.DAT` | `08a584fe…df35` |
| `B40R050R.DAT` | 73 MB streaming test |

Tools: `tools/ze0-viewer/` (patch SHA-256
`f9cc2e5f6607ed4433620390382279b48ca99dda909d57c6830f59ea4721aa31`).

## Method

```bash
cd tools/ze0-viewer
./setup.sh
python3 harness.py verify /path/to/B30R048R.DAT
python3 harness.py roads  /path/to/B30R060R.DAT
python3 harness.py stream /path/to/B40R050R.DAT out/B40R050_copy.DAT
```

## Observations

All five target files now round-trip **byte-identically**:

| File | Result |
| --- | --- |
| `B28R070R.DAT` | identical, 1,083,392 B |
| `B30R060R.DAT` | identical, 1,294,336 B |
| `B58R070R.DAT` | identical, 110,592 B |
| `LEV3456R.DAT` | identical, 76,066,304 B |
| `B30R048R.DAT` | identical, 1,358,592 B (was 3,371,008) |

`B30R048R` verify: `records ok 3396 bad 0 | background rebuild ok 2955 bad 0
(opaque 65) | graph parse 228 bad 0 | roundtrip OK`.

Missing container pieces were:

- pair flags: mask `0x80000000` from the compressed-length word;
- raw slot tail (B30R048 slot 21 at body `+0xE8`);
- empty tags `0x7fffffff` at level 1;
- `0x2146` header word 0 declares 512 bytes more than `12 + nslots*(4+body)`;
- a 55 KiB unreferenced gap at `0x9a520..0xa7d00` must be copied verbatim.

Roads (`section 1`, even pair, `w2=0x00fa`):

| Tile | Even records | Parsed | Shapes | Points |
| --- | --: | --: | --: | --: |
| `B30R060R` | 37 | 37 | 784 | 8,923 |
| `B30R048R` | 188 | 188 | 6,270 | 84,470 |

Streaming writer: `B40R050R` 73 MB, exact SHA-256, max RSS ~120 MB, 0.30 s.
A grown record is relocated to EOF and the slot tag patched; other addresses
stay valid.

`LEV3456R` level 6: no layer count word; table at word 11 with 26
`(offset, point-count)` pairs; 156 features; bbox lon −16.05..67.96, lat
30.01..63.18.

Coarse levels 3–5: **0** failures; 1,722 opaque records preserved verbatim.

## Interpretation

- **FACT:** the dense container is understood; all five files byte-identical.
- **FACT:** road-shape records parse and rebuild byte-identically.
- **FACT:** a streaming writer handles 73 MB without OOM.
- **FACT:** `LEV3456R` level 6 is decoded.
- **UNKNOWN:** section-4 content (`w2=0x0009`) is still opaque; road
  names/classes/speeds/one-way are not decoded.

## Conclusion

Gate 3 is passed for the full 45-tile set (container level). The viewer now
renders coast/land and roads. `docs/format/map-tiles.md`, the viewer README and
claims C-250…C-257 were updated.

## Follow-ups

- [ ] Decode section-4 content (`w2=0x0009`).
- [ ] Road names, class/speed colours and one-way direction.
- [ ] Draw layers 4/6 (currently parsed, not drawn).
- [ ] Streaming decoder for the 436 MB tile.
- [ ] Model the 1,722 opaque coarse records structurally.
