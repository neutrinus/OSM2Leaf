# EXP-2026-11-05-15: Section-4 index, road names and streaming decoder

- **Status:** done (section-4 classified; road attributes partial)
- **Date:** 2026-11-05
- **Sample:** EU 2011 `MAPAL001`
- **Claims:** C-280…C-286
- **Supersedes:** the “section 4 is opaque geometry” status
- **Superseded by:** none

## Question

What is section 4, can road names/attributes be decoded, and can the 436 MB
tile be streamed and compared?

## Hypothesis

Section 4 is geometry (landuse/water/buildings); road names are in the tile;
a streaming decoder can avoid the object-graph OOM.

## Inputs

| File | SHA-256 |
| --- | --- |
| `B30R048R.DAT` | `09161015…eb28` |
| `B30R060R.DAT` | `8ca92bd5…b62d` |
| `B40R050R.DAT` | 73 MB streaming test |
| `B48R060R.DAT` | 436 MB streaming test |

Tools: `tools/ze0-viewer/` (`ze0_section4.py`, `stream_decode.py`,
`harness.py compare-tiles`).

## Observations

### Section 4 is an administrative/place-name index

`B30R048R`: section id 4, level 1, type `0x93`, directory kind `0x1146`,
256-byte bodies, 11 slots. **20 records / 68 names**, record word 2 = `0x0009`,
word 8 = ISO 3166 numeric country (`0x012c` = 300 = Greece).

Payload is packed binary plus `0=NAME` strings: `RODOS`, `LINDOS`,
`ARCHIPOLI:ELEOUSA`, `KALLITHEA`, `PARALIA AFANTOU`, …

It is **not** landuse, water, buildings or geometry. `ze0_section4.py` emits
GeoJSON points with `layer=400`, `section4=true`.

The 56-byte template in upstream `sec4_write.py` is the 2014/2017 variant;
ZE0 records are 84–684 bytes and carry names, so it is not a ZE0 encoder.

### Road names

A road shape's header word 4 is the word offset of its name entry in the
**odd partner record's names section**. `ze0_decode.py` now attaches `name`
and `ref`:

| Tile | Road lines | Named | One-way (hypothesis) |
| --- | --: | --: | --: |
| `B30R060R` | 1,195 | 297 | 14 |
| `B30R048R` | 10,667 | 1,972 | 958 |

Examples: `VIA NICÀ`, `VICOLO SCALO`, `CONTRADA ZIGHIDÌ`, `RODOS`.

Style/class is raw (`style, value, id` at level 1; `style, id` at level 2;
shape word 3 = `class_word`). Observed styles are mostly `0x201e`, ferries
`0x001e`. The one-way/speed rules follow the 2017 notes as a **HYPOTHESIS**:
speed if `style & 0x20`, `((style & 0x1f)+1)*5`; one-way if
`not (style & 0x3000)`. This needs a known one-way street/speed sign before it
is trusted.

### Streaming decoder

`stream_decode.py` walks the tile through mmap and decodes background/road
records one at a time:

| Tile | Size | Features | Time | Max RSS |
| --- | --: | --: | --: | --: |
| `B40R050R` | 73 MB | 696,470 | ~12 s | ~120 MB |
| `B48R060R` | 436 MB | 2,710,087 | ~40 s | 242 MB |

No OOM. Streaming mode does not attach road names yet (it does not cache the
odd partner record); object mode does.

### Acceptance feedback loop

```bash
python3 harness.py compare-tiles FACTORY.DAT BUILT.DAT --cell B30R060R --levels 1,2
```

Unchanged copy: **ZERO DIFF** (15,843 features). One-vertex mutation:
`added 1, removed 1, unchanged 15,842`, largest change ~67.9 m → `DIFFERS`.

### Regression

All five targets still rebuild byte-identically:
`B28R070R` 1,083,392; `B30R060R` 1,294,336; `B58R070R` 110,592;
`LEV3456R` 76,066,304; `B30R048R` 1,358,592.

## Evidence conflict (important)

The viewer agent reports a negative `RDSTM001`/`LCTBL001` cross-reference
(“LCTBL has 90 fixed 46-byte records, not a name list; RDSTM has 27 zlib
streams”). This **conflicts** with the dedicated RDSTM work
([EXP-2026-11-05-01…](README.md), `docs/format/rdstm.md`), which found:

- `LCTBL001` catalog at `0x1000` **plus 517 zlib streams from `0x316600`**
  with 328,628 Latin-2 names;
- `RDSTM001` has **no** zlib streams.

The viewer agent stopped at the LCTBL catalog and did not reach the stream
region. Treat `docs/format/rdstm.md` as authoritative; do not build on the
viewer's RDSTM/LCTBL negative.

## Interpretation

- **FACT:** section 4 is an administrative/place-name index, not geometry.
- **FACT:** road names are decodable from the odd partner record.
- **FACT:** the 436 MB tile can be streamed at 242 MB RSS.
- **FACT:** `compare-tiles` gives zero diff on unchanged input.
- **HYPOTHESIS:** one-way/speed mapping from style bits.
- **UNKNOWN:** section-4 binary fields between country and names, and a ZE0
  section-4 encoder.

## Follow-ups

- [ ] Map the section-4 binary fields and build a ZE0 encoder.
- [ ] Validate one-way/speed against a known street/sign.
- [ ] Attach names in streaming mode.
- [ ] Resolve the RDSTM/LCTBL cross-reference using the dedicated RDSTM work.
