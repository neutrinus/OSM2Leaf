# `DRSTR001.DAT` directory index

`DRSTR001.DAT` is the only manifest on the card: a complete index of the
logical file tree (root + directories + files) with logical sizes. It is not a
FAT directory and it does not use the common 512-byte header.

Sample: 11,968 bytes in the EU 2011 image
(SHA-256 `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6`).

> **Correction:** earlier notes in this repo claimed a 0x28-byte header, a
> `u32 0x2f` node count and a “one-node shift”. All three were wrong. `0x2f`
> is the ASCII `/` of the root node's name. The layout below is verified by
> the file-size identity `40*40 + 324*32 = 11968` and by cross-checking
> 2014/2016 map sets.

## Layout

```
0x0000  40-byte node records (node 0 = root "/")
0x0640  32-byte directory entries (324 in the 2011 sample)
EOF
```

There is **no header**. The node table starts at `0x0000`; the first listing
starts immediately after the last node record.

## Node record (40 bytes), name first

```c
struct node {
    char     name[8];        // +0x00  ASCII, zero padded; "/" for root
    uint8_t  unknown[12];    // +0x08
    uint16_t next_index;     // +0x14  always index + 1; last = node count
    uint16_t parent_plus_1;  // +0x16  1-based parent; root points to itself
    uint32_t entry_count;    // +0x18
    uint32_t reserved0;      // +0x1c  zero
    uint32_t reserved1;      // +0x20  zero
    uint32_t listing_offset; // +0x24
};
```

- `parent = parent_plus_1 - 1`. Root (`index 0`) stores `1`, i.e. points to
  itself.
- `next_index` is always `index + 1`; its purpose is unknown.
- The 2011 sample has 40 nodes: root + 39 directories.

## Directory entry (32 bytes)

```c
struct entry {
    char     name[13];   // +0x00  "NAME.EXT", zero padded; 13 bytes, not 12
    uint8_t  unknown[9]; // +0x0d
    uint16_t type;       // +0x16  0 = file, 2 = directory
    uint32_t reserved;   // +0x18  zero
    uint32_t value;      // +0x1c  file: logical size; dir: recursive total
};
```

- The writer stores **13** name bytes. `reception.dat` (13 characters) uses
  the 13th byte at `+0x0c`.
- For files, `value` is the logical uncompressed size (for `REFER001` it
  matches the `.ind` size exactly; 194/194).
- For directories, `value` is the recursive total size of the subtree
  (verified for all 39 directories).

## Examples

- Root listing at `0x640`: `MMAIN001.DAT`, `BICON001`, `MAPAL001`, `OPNG`,
  `RDSTM001`, `REFER001`, `REFER002`, `SPEECH`, `TMC`, `VER_INFO`, `CMP.LST`.
- `BICON001` at `0x7a0`: one file, `BICON001.DAT`, 114,598 bytes.
- `MAPAL001` at `0x7c0`: 46 `BxxRyyR.DAT` tiles.
- `REFER001` at `0xde0`: 194 logical `*.DAT` entries with uncompressed sizes.

## Firmware references (build A, real VAs)

Under the CE ROM TOC address model, `DRSTR001.DAT` and `\\CMP.LST` *do* have
code references in `Navi.exe` (this retracts part of C-331, "zero literal
references", which was produced under the wrong address model). `MAPAL001`
survives only as a static filename-table entry.

| String | String VA | Literal pool | Loaded at | Function VA | Caller VA |
| --- | --- | --- | --- | --- | --- |
| `DRSTR001.DAT` | `0x0017ab24` | `0x00419870` | `0x00419732` (r5) | `0x00419684` | `0x00419d24` |
| `\\CMP.LST` | `0x0017b25c` | `0x0041bbb0` | `0x0041bad0` (r5) | `0x0041ba90` | `0x00419ca0` |
| `LEV3456R.DAT` | `0x00179fa4` | `0x0040a0ec` | `0x0040a022` (r5) | `0x0040a014` | — |
| `MAPAL001` | `0x00179f98` | `0x00179cf8`/`0x00179d04`/`0x00179d10` (static table) | none | none | none |

- `RDSTM001` (`0x00179398`) is also referenced by code (fns `0x003fbed8`,
  `0x004125a8`); `REFER001.DAT`/`REFER002`/`INTER001.DAT`/etc. share the
  static filename table at `0x00179cf0`…`0x00179d34`.
- The two referencing functions (`0x00419684`, `0x0041ba90`) are
  CD-ROM/media-manager routines invoked during media initialisation; no
  count/order/sentinel check on the DRSTR layout (40 nodes, 324 entries,
  leading `u32 = 0x0000002f`) was identified in them.
- Search covered the uncompressed sections of `Navi.exe`, `NaviMapCC.dll`,
  `OBJDLL.dll`, `STDDLL.dll` (build A); the literals occur only in
  `Navi.exe`. Raw-image scan of the first 256 MiB found only the two
  build-A copies of `DRSTR001.DAT`.

## What it is used for

Static firmware evidence shows `DRSTR001.DAT` and `MMAIN001.DAT` are opened by
the CD-ROM/media-manager module, while database base names (`ZCODE0`,
`ADDRE0`, `POINT0`, `FRWAY0`, `INTER0`, `LCTBL0`) are hard-coded. The most
likely role is a **directory cache / logical size table**, not the only way to
locate data. This is a hypothesis; the cheapest test is to rename
`DRSTR001.DAT` on a spare card and see whether the unit still reads maps.

## Related files

- `CMP.LST` = exactly `\SystemSD\REFER001\` (19 bytes, no newline).
- `MMAIN001.DAT` is **not** a manifest. It is a format/version descriptor
  (common header, per-language code list at `0x18c`, a 3-section descriptor at
  `0x1ac`) with no file names, offsets or checksums.
- `VER_INFO/HDD_INFO.TXT` is a six-line text record; a byte-identical copy is
  embedded in the firmware area at `0x06000000`.
