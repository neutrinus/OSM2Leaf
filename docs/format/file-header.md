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

Common prefix (identical in every examined file):

```
0x180: ff ff 24 ff 12 c0 05 00 fb 50 0f f0
```

Then a per-file block. Examples:

`MMAIN001.DAT` and `REFER002/COORD001.DAT`:

```
0x18c: 05 04 02 07 0a 06 08 14
0x194: 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f
0x1a0: ff ff ff ff ff ff ff ff ff ff ff ff
0x1ac: 00 03 01 06 06 80 00 01 05 90 00 01 ...
```

Map tiles (`MAPAL001/*.DAT`):

```
0x18c: 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f 3f
0x1a0: ff ff ff ff ff ff ff ff ff ff ff ff
0x1ac: 00 02 01 06 06 80 00 00 05 90 00 00 ...
```

`RDSTM001/RDSTM001.DAT`:

```
0x18c: 3f * 20
0x1a0: ff * 12
0x1ac: 00 01 03 02 04 ff ff ff 02 ff ff ff 00 ...
```

`LEV3456R.DAT` has a larger descriptor block that includes literal values
such as `12 c0 05 00 fb 50 0f f0`, `11 80 05 a0 fb 50 08 70`, etc.

## Hypothesis

The block at `0x180` is a small per-database descriptor: format revision,
record sizes, level-of-detail counts and default values. It is not yet
decoded field by field. The `0x3f` bytes look like fill/default values, and
the `ff` run looks like a reserved/absent field marker.

## Notes

- Decompressed `REFER001` files still carry this 512-byte header, so the
  logical `.DAT` size in `.ind` includes the header.
- `DRSTR001.DAT` is the exception: it does **not** use this header; it is a
  compact binary directory index (see [drstr.md](drstr.md)).
