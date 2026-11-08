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
| `0x0e0` | `DATA VERSION YY/MM/DD/NN` (the stamp differs per file; see Identity fields) |
| `0x160` | u16 `16 00` (MMAIN001) or `14 00` (BICON001), then `V05.00.00` from `0x162` |

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

Byte order is **big-endian** on the card for the fields with proven semantics:
the `0x184` bounds (C-1724) and the `0x1ac`/`0x1b0` counts (C-1788). The
`MMAIN001.DAT` reader byte-swaps the whole 4,096 bytes to little-endian in
memory (`sub_0041a304`, M3.8). The `0x180` prefix words have no proven reading
order, so do not build their meaning on either endianness. Only the byte
layout and the descriptor *structure* are established; no field has a proven
semantic meaning beyond the class patterns.

### Common prefix and class area

| Offset | Size | Status | Field | Bytes / value | Evidence (file @ offset) |
| --- | --: | --- | --- | --- | --- |
| `0x180` | 12 | `VERIFIED` bytes on EU, `OBSERVED` on US, `UNKNOWN` meaning | common prefix | EU: `ff ff 24 ff 12 c0 05 00 fb 50 0f f0`; US: `ff ff 26 ff 12 c0 00 00 d7 b0 f3 d0` | split per word below; C-011, C-2490 |
| `0x180` | 2 | `VERIFIED` value, `UNKNOWN` meaning | word 0 | u16 LE `0xffff` in all eight real headers checked (MMAIN001, BICON001 of EU 2011/2014/2016 and US 2011) | C-2490; no semantics |
| `0x182` | 2 | `VERIFIED` value, `UNKNOWN` meaning | word 1 | u16 LE `0xff24` on EU, `0xff26` on US | C-2490; the only fixed-position difference besides the bounds; settling mutation below |
| `0x184` | 2 | `OBSERVED` | bound, north | BE i16 `0x12c0` = 4800 = 80.0° N in all eight headers | C-1724, C-2491 |
| `0x186` | 2 | `OBSERVED` | bound, south | BE i16 EU `0x0500` = 1280 (21.33° N); US `0x0000` = 0 | C-2491; the box contains every tile (C-2492) |
| `0x188` | 2 | `OBSERVED` | bound, west | BE i16 EU `0xfb50` = −1200 (−20°); US `0xd7b0` = −10320 (−172°) | C-2491; west edge equals the westernmost tile edge on both (C-2492) |
| `0x18a` | 2 | `OBSERVED` | bound, east | BE i16 EU `0x0ff0` = 4080 (68°); US `0xf3d0` = −3120 (−52°) | C-2491; US east equals the easternmost tile edge; EU 68° is beyond the 36° E tile edge (C-2492) |
| `0x18c` | variable: 2, 8 or 17 bytes | `VERIFIED` bytes, `UNKNOWN` identity | code list, then `3f` fill | US `03 04`; EU 2011 `05 04 02 07 0a 06 08 14`; EU 2014 and 2016 `05 04 02 07 0a 06 08 0d 0c 16 15 09 19 17 18 1a 14`; same bytes in MMAIN001 and BICON001 of each image | codes not decoded to languages (C-2494–C-2496) |
| `0x194` | variable | `OBSERVED` | `3f` fill to the end of the list | 12 bytes after the 8-code list, 3 bytes after the 17-code list, 18 bytes after the 2-code list | C-2494 |
| `0x1a0` | 12 | `OBSERVED` | reserved run | `ff` × 12 in MMAIN001; `00` × 12 in BICON001 (which has no descriptor) | C-2494; "reserved" is only a hypothesis |
| `0x1ac` | 1 | `VERIFIED` | descriptor lead byte | `00` | C-052; `MAPAL001/B28R070R.DAT` @ `0x1ac`; `MMAIN001.DAT` @ `0x1ac`; `REFER002/COORD001.DAT` @ `0x1ac`; `RDSTM001/RDSTM001.DAT` @ `0x1ac` |
| `0x1ad` | 1 | `VERIFIED` | `n_tables` | `03` MMAIN/REFER, `02` MAPAL, `01` RDSTM | `MMAIN001.DAT` @ `0x1ad`; `REFER002/COORD001.DAT` @ `0x1ad`; `MAPAL001/B28R070R.DAT` @ `0x1ad`; `RDSTM001/RDSTM001.DAT` @ `0x1ad`; C-052 |
| `0x1ae` | 1 | `VERIFIED` | first `table_id` | `01` MMAIN/REFER/MAPAL, `03` RDSTM | `MMAIN001.DAT` @ `0x1ae`; `REFER002/COORD001.DAT` @ `0x1ae`; `MAPAL001/B28R070R.DAT` @ `0x1ae`; `RDSTM001/RDSTM001.DAT` @ `0x1ae`; C-052 |
| `0x1af` | 1 | `VERIFIED` | first `n_entries` | `06` MMAIN/REFER/MAPAL, `02` RDSTM | `MMAIN001.DAT` @ `0x1af`; `REFER002/COORD001.DAT` @ `0x1af`; `MAPAL001/B28R070R.DAT` @ `0x1af`; `RDSTM001/RDSTM001.DAT` @ `0x1af`; C-052 |
| `0x1b0` | 4 each | `VERIFIED` structure, `HYPOTHESIS` meaning | descriptor entry | `(level: u8, kind: u8, count: u16 BE on the card)` | `MAPAL001/B28R070R.DAT` @ `0x1b0` (`06 80 00 00`); `MMAIN001.DAT` @ `0x1b0` (`06 80 00 01`); `RDSTM001/RDSTM001.DAT` @ `0x1b0` (`04 ff ff ff`); TODO: level/kind/count semantics unknown; C-1788 |
| variable | 1 | `VERIFIED` for tiles, `OBSERVED` elsewhere | container terminator | `00` after the last table | C-052; `MAPAL001/B28R070R.DAT` @ descriptor end |
| variable | — | `UNKNOWN` | descriptor tail | bytes after the parsed container up to `0x1ff` | TODO: not mapped in any sample; do not interpret |

The EU prefix is twelve bytes; as little-endian `u16` words it reads
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

The class table above describes the EU 2011 sample. The `0x18c` list length
varies per image (2, 8 or 17 codes); see Identity fields (M4.22).

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
| `magic-version` | `VERIFIED` | `V…` at `0x162`, after a u16 at `0x160` (M4.22) | C-010; four documented samples |
| `text-terminators` | `VERIFIED` | each text slot is `0xffff`-terminated or ends at its slot | C-010 |
| `block-prefix` | `VERIFIED` | `ff ff ?? ff 12 c0` at `0x180`; byte `0x182` is not checked (`24` EU, `26` US) | C-011, C-2490; eight real headers (M4.22) |
| `descriptor-container` | `VERIFIED` tile-like, `OBSERVED` MMAIN/REFER | `00`, `n_tables`, … parses and fits before `0x200` | C-052; `MAPAL001/B28R070R.DAT` @ `0x1ac`; MMAIN/REFER container is observed only |
| `block-trailer` | `VERIFIED` | the 128-byte block `0x180`–`0x1ff` is present | `docs/format/file-header.md` |
| `reserved-run` | `OBSERVED` | `ff` × 12 at `0x1a0` | four documented samples @ `0x1a0` |
| `class-area-pattern` | `OBSERVED` | `0x18c`–`0x19f` matches the 8-code pattern; the 17-code EU 2014/2016 list warns (C-2494) | four documented samples @ `0x18c` |

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

## Identity fields (M4.22)

Evidence: EXP-2026-11-08-M4.22-identity-codes; claims C-2490–C-2499. Samples are
the MMAIN001 and BICON001 headers of EU 2011, US 2011, EU 2014 and EU 2016.

| Field | Status | Meaning | Settling mutation (not run; needs the L3 harness, M9.20) |
| --- | --- | --- | --- |
| `0x180`–`0x181` | `VERIFIED` value, `UNKNOWN` meaning | constant `ffff` | none needed |
| `0x182`–`0x183` | `VERIFIED` value, `UNKNOWN` meaning | `ff24` (EU) / `ff26` (US) | change only byte `0x183` in a copy of MMAIN001, then run the M3.8 read path of `Navi.exe` (`0x0041a438`) and compare the byte-swapped buffer handed to `OBJ_DriveInfo_writeDataVol`; no change in the consumed fields means `0x182` is not consumed there |
| `0x184`–`0x18b` | `OBSERVED` | N, S, W, E bounds in arc-minutes, BE i16 | the box contains every `MAPAL001` tile on all four images (C-2492); a mutated west edge that cuts a tile must fail the same check |
| `0x18c`… | `OBSERVED` bytes, `UNKNOWN` identity | code list, `3f`-terminated, 2/8/17 entries | edit one code in a copy, and see which `SPEECH/<lang>` set the reader selects; needs the speech selector in `Navi.exe`, which M4.22 did not locate |
| `DATA VERSION` | `OBSERVED` text, `HYPOTHESIS` meaning (build-date stamp) | `YY/MM/DD/NN` | no firmware literal compares it (drstr.md, M3.8), so the stamp is a label; the BICON001 stamp could only matter if the BICON001 open path compares it, which is not yet checked |

### `DATA VERSION` per file (C-2497)

| File | EU 2011 | US 2011 | EU 2014 | EU 2016 |
| --- | --- | --- | --- | --- |
| `MMAIN001.DAT` | 11/06/27/01 | 10/08/12/01 | 14/04/12/01 | 16/08/01/01 |
| `BICON001/BICON001.DAT` | **11/04/08/01** | **10/06/24/01** | 14/04/12/01 | 16/08/01/01 |
| `MAPAL001/B28R070R.DAT` (US: `B18R100R`) | 11/06/27/01 | 10/08/12/01 | 14/04/12/01 | 16/08/01/01 |
| `RDSTM001/RDSTM001.DAT` | 11/06/27/01 | 10/08/12/01 | 14/04/12/01 | 16/08/01/01 |
| `RDSTM001/LCTBL001.DAT` | 11/06/27/01 | 10/08/12/01 | 14/04/12/01 | 16/08/01/01 |

`BICON001` differs from the other map files only on EU 2011 and US 2011. On EU
2014 and EU 2016 every file carries the same stamp, so "every other map file
differs" is not true for all images. The stamp is not the FAT modification time:
EU 2014 `MMAIN001.DAT` is stamped `14/04/12` but modified `2014-03-13`.

### `0x18c` code list by image (C-2494, C-2495, C-2496)

| Image | Codes at `0x18c` (MMAIN001 = BICON001) | Count | `SPEECH/` language dirs | DRSTR `SPEECH` entry count |
| --- | --- | --: | --- | --: |
| US 2011 | `03 04` | 2 | `CF`, `US` | 2 |
| EU 2011 | `05 04 02 07 0a 06 08 14` | 8 | `SP PT IT GE FR DU BE` | 7 |
| EU 2014 | `05 04 02 07 0a 06 08 0d 0c 16 15 09 19 17 18 1a 14` | 17 | `BE CS DA DU EL FI FR GE HU IT NO PL PT SK SP SV` | 16 |
| EU 2016 | as EU 2014 | 17 | as EU 2014 | 16 |

Counts agree for each image up to one extra code on EU (8 vs 7, 17 vs 16). The
EU 2011 codes are a subset of the EU 2014 codes, and the nine codes added in
2014 (`0d 0c 16 15 09 19 17 18 1a`) match the nine languages added in 2014
(`CS DA EL FI HU NO PL SK SV`) by count. Code `04` appears on both US and EU.
The `SPEECH/<lang>/GID` headers carry a date string, not a language code, so
the code-to-language identity is **not decoded**. Two readings fit the counts:
`0x14` is an extra non-speech code on EU, or `04` is English (speech on US,
text-only on EU). Nothing in the four images separates them.
