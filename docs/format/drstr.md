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
