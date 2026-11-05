# Common 512-byte file header

> **Evidence convention:** field offsets below are `VERIFIED` against the
> listed samples; the meaning of the `0x180` block is partly `HYPOTHESIS`.
> See [`../research/claims.md`](../research/claims.md).

Most map data files begin with the same 512-byte header. Verified on
`MMAIN001.DAT`, `MAPAL001/*.DAT`, `RDSTM001/*.DAT`, `BICON001.DAT`,
`REFER002/*.DAT` and on the decompressed `REFER001/*.cmp` output.

## Text fields

The strings are **UTF-16 big-endian**, padded with `0xffff`. They are not
length-prefixed; each field occupies a fixed slot.

| Offset | Content |
| --- | --- |
| `0x000` | `CLARION` |
| `0x040` | `HITACHI` |
| `0x080` | `CLA-NAVI05-01` |
| `0x0a0` | `FORMAT VERSION X08-02-00` |
| `0x0e0` | `DATA VERSION 11/06/27/01` |
| `0x160` | `V05.00.00` (preceded by `16 00`) |

The exact slot boundaries are slightly irregular (for example
`CLA-NAVI05-01` ends at `0x09a`, then `0xffff` padding, and
`FORMAT VERSION X...` begins at `0x0a0`). Treat the header as a sequence of
`0xffff`-terminated UTF-16BE strings rather than as a packed struct.

## Binary field block at `0x180`

The UTF-16BE text ends at `0x17f`. Bytes `0x180`–`0x1ff` are a 128-byte
**little-endian** binary block; they are not UTF-16 and must not be decoded
with the text rules. The block is per-file, not per-format: two files of the
same class can differ in it, and the same class can share it.

> **Status legend.** `VERIFIED` means the layout was reproduced on the files
> named in the row by the cited experiment or claim. `OBSERVED` means the bytes
> were seen on those files but are not proven universal. `HYPOTHESIS` marks a
> fitted interpretation. `UNKNOWN` means there is no evidence; it carries an
> explicit TODO and the tool emits it as unknown rather than guessing.

All multi-byte values below are read **little-endian**. Only the byte layout
and the descriptor *structure* are established; no field has a proven
semantic meaning beyond the class patterns.

### Common prefix and class area

| Offset | Size | Status | Field | Bytes / value | Evidence (file @ offset) |
| --- | --: | --- | --- | --- | --- |
| `0x180` | 12 | `VERIFIED` bytes, `UNKNOWN` meaning | common prefix | `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` | `MMAIN001.DAT` @ `0x180`; `REFER002/COORD001.DAT` @ `0x180`; `MAPAL001/B28R070R.DAT` @ `0x180`; `RDSTM001/RDSTM001.DAT` @ `0x180`; C-011 |
| `0x180` | 2 | `UNKNOWN` | prefix word 0 | u16 LE `0xffff` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x182` | 2 | `UNKNOWN` | prefix word 1 | u16 LE `0xff24` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x184` | 2 | `UNKNOWN` | prefix word 2 | u16 LE `0xc012` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x186` | 2 | `UNKNOWN` | prefix word 3 | u16 LE `0x0005` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x188` | 2 | `UNKNOWN` | prefix word 4 | u16 LE `0x50fb` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x18a` | 2 | `UNKNOWN` | prefix word 5 | u16 LE `0xf00f` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180`; TODO: no semantics |
| `0x18c` | 8 | `OBSERVED` bytes, `HYPOTHESIS` meaning | class code list or fill | `05 04 02 07 0a 06 08 14` in MMAIN/REFER; `3f` × 8 in MAPAL/RDSTM | `MMAIN001.DAT` @ `0x18c`; `REFER002/COORD001.DAT` @ `0x18c`; `MAPAL001/B28R070R.DAT` @ `0x18c`; `RDSTM001/RDSTM001.DAT` @ `0x18c`; C-037 calls it a per-language code list (fitted); TODO: codes not decoded |
| `0x194` | 12 | `OBSERVED` bytes, `UNKNOWN` meaning | class fill run | `3f` × 12 | `MMAIN001.DAT` @ `0x194`; `REFER002/COORD001.DAT` @ `0x194`; `MAPAL001/B28R070R.DAT` @ `0x194`; `RDSTM001/RDSTM001.DAT` @ `0x194`; TODO: no semantics |
| `0x1a0` | 12 | `OBSERVED` | reserved/absent run | `ff` × 12 | `MMAIN001.DAT` @ `0x1a0`; `REFER002/COORD001.DAT` @ `0x1a0`; `MAPAL001/B28R070R.DAT` @ `0x1a0`; `RDSTM001/RDSTM001.DAT` @ `0x1a0`; TODO: "reserved" is only a hypothesis |
| `0x1ac` | 1 | `VERIFIED` | descriptor lead byte | `00` | C-052; `MAPAL001/B28R070R.DAT` @ `0x1ac`; `MMAIN001.DAT` @ `0x1ac`; `REFER002/COORD001.DAT` @ `0x1ac`; `RDSTM001/RDSTM001.DAT` @ `0x1ac` |
| `0x1ad` | 1 | `VERIFIED` | `n_tables` | `03` MMAIN/REFER, `02` MAPAL, `01` RDSTM | `MMAIN001.DAT` @ `0x1ad`; `REFER002/COORD001.DAT` @ `0x1ad`; `MAPAL001/B28R070R.DAT` @ `0x1ad`; `RDSTM001/RDSTM001.DAT` @ `0x1ad`; C-052 |
| `0x1ae` | 1 | `VERIFIED` | first `table_id` | `01` MMAIN/REFER/MAPAL, `03` RDSTM | `MMAIN001.DAT` @ `0x1ae`; `REFER002/COORD001.DAT` @ `0x1ae`; `MAPAL001/B28R070R.DAT` @ `0x1ae`; `RDSTM001/RDSTM001.DAT` @ `0x1ae`; C-052 |
| `0x1af` | 1 | `VERIFIED` | first `n_entries` | `06` MMAIN/REFER/MAPAL, `02` RDSTM | `MMAIN001.DAT` @ `0x1af`; `REFER002/COORD001.DAT` @ `0x1af`; `MAPAL001/B28R070R.DAT` @ `0x1af`; `RDSTM001/RDSTM001.DAT` @ `0x1af`; C-052 |
| `0x1b0` | 4 each | `VERIFIED` structure, `HYPOTHESIS` meaning | descriptor entry | `(level: u8, kind: u8, count: u16 LE)` | `MAPAL001/B28R070R.DAT` @ `0x1b0` (`06 80 00 00`); `MMAIN001.DAT` @ `0x1b0` (`06 80 00 01`); `RDSTM001/RDSTM001.DAT` @ `0x1b0` (`04 ff ff ff`); TODO: level/kind/count semantics unknown |
| variable | 1 | `VERIFIED` for tiles, `OBSERVED` elsewhere | container terminator | `00` after the last table | C-052; `MAPAL001/B28R070R.DAT` @ descriptor end |
| variable | — | `UNKNOWN` | descriptor tail | bytes after the parsed container up to `0x1ff` | TODO: not mapped in any sample; do not interpret |

The prefix is twelve bytes; as little-endian `u16` words it reads
`ffff ff24 c012 0005 50fb f00f`. As little-endian `u32` words it reads
`ff24ffff 0005c012 f00f50fb`. Neither grouping has a decoded meaning.

### Class signatures

The documented bytes give these signatures. `REFER` and `MMAIN` are **not
distinguishable** from the documented header fields: `MMAIN001.DAT` and
`REFER002/COORD001.DAT` share the same values in every row above. Do not claim
header-only REFER/MMAIN detection; use the filename or payload.

| Class | `0x18c`–`0x19f` | `0x1a0`–`0x1ab` | `0x1ad` | `0x1ae`–`0x1af` |
| --- | --- | --- | --: | --- |
| `MMAIN001.DAT` | `05 04 02 07 0a 06 08 14` + `3f` × 12 | `ff` × 12 | `03` | `01 06` |
| `REFER002/COORD001.DAT` | same as MMAIN | `ff` × 12 | `03` | `01 06` |
| `MAPAL001/B28R070R.DAT` | `3f` × 20 | `ff` × 12 | `02` | `01 06` |
| `RDSTM001/RDSTM001.DAT` | `3f` × 20 | `ff` × 12 | `01` | `03 02` |

Raw samples (the `...` means the sample hexdump was not extended in the
experiment record):

```
MMAIN001.DAT, REFER002/COORD001.DAT:
0x180: ff ff 24 ff 12 c0 05 00 fb 50 0f f0
0x18c: 05 04 02 07 0a 06 08 14
0x194: 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f
0x1a0: ff ff ff ff ff ff ff ff ff ff ff ff
0x1ac: 00 03 01 06 06 80 00 01 05 90 00 01 ...

MAPAL001/B28R070R.DAT:
0x18c: 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f
0x1a0: ff ff ff ff ff ff ff ff ff ff ff ff
0x1ac: 00 02 01 06 06 80 00 00 05 90 00 00 ...

RDSTM001/RDSTM001.DAT:
0x18c: 3f * 20
0x1a0: ff * 12
0x1ac: 00 01 03 02 04 ff ff ff 02 ff ff ff 00 ...
```

`LEV3456R.DAT` has a larger descriptor block that includes literal values
such as `12 c0 05 00 fb 50 0f f0`, `11 80 05 a0 fb 50 08 70`, etc. Its
`0x1ac` container has not been parsed separately.

### Structural invariants checked by `tools/header_block.py`

These are the only checks the tool treats as hard failures. `OBSERVED` checks
are reported as warnings so a new sample cannot be rejected on a fitted rule.

| Check ID | Status | Rule | Evidence |
| --- | --- | --- | --- |
| `header-size` | `VERIFIED` | file has at least 512 bytes | C-010; `docs/format/file-header.md` |
| `magic-clarion` | `VERIFIED` | UTF-16BE `CLARION` at `0x000` | C-010; four documented samples |
| `magic-hitachi` | `VERIFIED` | UTF-16BE `HITACHI` at `0x040` | C-010; four documented samples |
| `magic-model` | `VERIFIED` | `CLA-NAVI…` at `0x080` | C-010; four documented samples |
| `magic-format` | `VERIFIED` | `FORMAT VERSION …` at `0x0a0` | C-010; four documented samples |
| `magic-data` | `VERIFIED` | `DATA VERSION …` at `0x0e0` | C-010; four documented samples |
| `magic-version` | `VERIFIED` | `V…` at `0x160` | C-010; four documented samples |
| `text-terminators` | `VERIFIED` | each text slot is `0xffff`-terminated or ends at its slot | C-010 |
| `block-prefix` | `VERIFIED` | `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` at `0x180` | C-011; four documented samples @ `0x180` |
| `descriptor-container` | `VERIFIED` tile-like, `OBSERVED` MMAIN/REFER | `00`, `n_tables`, … parses and fits before `0x200` | C-052; `MAPAL001/B28R070R.DAT` @ `0x1ac`; MMAIN/REFER container is observed only |
| `block-trailer` | `VERIFIED` | the 128-byte block `0x180`–`0x1ff` is present | `docs/format/file-header.md` |
| `reserved-run` | `OBSERVED` | `ff` × 12 at `0x1a0` | four documented samples @ `0x1a0` |
| `class-area-pattern` | `OBSERVED` | `0x18c`–`0x19f` matches one of the two known patterns | four documented samples @ `0x18c` |

```bash
python3 tools/header_block.py dump FILE          # u32/u16 grids + ASCII runs
python3 tools/header_block.py class FILE         # text family + block/name variant
python3 tools/header_block.py compare A B        # text and byte-run differences
python3 tools/header_block.py check FILE...      # structural invariants
python3 tools/header_block.py --selftest         # synthetic data only
```

`dump`, `class` and `compare` require a full 512-byte header and exit `2` if
it is shorter. `check` accepts a short file, reports the failing invariants
and exits `1`; it exits `0` only when every `VERIFIED` invariant passes. Add
`--json` before or after the subcommand for machine-readable output.

The checker stops at `0x200`. Bytes after the header (the tile descriptors at
`0x2ac`, the `RDSTM001` tables, the fixed `REFER001` area at `0x200`–`0x0fff`)
are per-class and are not validated by this tool.

### Unknown fields and TODO

The following are explicitly **UNKNOWN**; the tool prints the same list. Do not
fill them from the old "format revision / record sizes / LOD counts" story
without a new experiment.

- TODO `0x180`–`0x18b`: six little-endian `u16` words. Only the byte pattern is
  verified (`MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`,
  `RDSTM001/RDSTM001.DAT` @ `0x180`).
- TODO `0x18c`–`0x193`: the eight-code list in MMAIN/REFER. `C-037` calls it a
  per-language code list, but no code has been mapped to a language.
- TODO `0x194`–`0x19f`: twelve `0x3f` bytes. Fill/default is a hypothesis.
- TODO `0x1a0`–`0x1ab`: twelve `0xff` bytes. Reserved/absent is a hypothesis.
- TODO `0x1b0` onward: `level`, `kind` and `count` are names for the observed
  tuple shape only; no semantics are established.
- TODO descriptor tail: bytes after the parsed container are unmapped.

## Hypothesis (not promoted)

The block at `0x180` is a small per-database descriptor: format revision,
record sizes, level-of-detail counts and default values. This remains a
`HYPOTHESIS`; no experiment has decoded a field. The `0x3f` bytes look like
fill/default values and the `ff` run looks like a reserved/absent marker, but
both are fitted, not verified. The tool deliberately does not use these
interpretations for validation.

## Notes

- Decompressed `REFER001` files still carry this 512-byte header, so the
  logical `.DAT` size in `.ind` includes the header.
- `DRSTR001.DAT` is the exception: it does **not** use this header; it is a
  compact binary directory index (see [drstr.md](drstr.md)).
