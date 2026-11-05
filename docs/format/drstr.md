# `DRSTR001.DAT` directory index

`DRSTR001.DAT` is a compact binary index of the virtual map filesystem. It is
**not** a normal FAT directory and it does not use the common 512-byte header.

Sample: 11,968 bytes in the EU 2011 image
(SHA-256 `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6`).

## Status

- The node table and entry list layout below are **verified**: 39 nodes parse
  cleanly and their listings match the FAT contents.
- The meaning of the first 32-bit word (`0x2f` = 47 in this image) is
  **unknown**. It is *not* the node count; there are 39 nodes.
- The meaning of the `next_index` field is **observed** but not proven; it
  increases by one per record and wraps/stops at the last node.

## Header

```
+0x00  u32  0x2f            semantics unknown
+0x04  ...  zero padding to 0x28
```

## Node records

Starting at `0x28`, one 40-byte record per directory, **name first**:

```c
struct node {
    char     name[8];        // +0x00  ASCII, zero padded
    uint8_t  zero0[12];      // +0x08  zeros
    uint16_t next_index;     // +0x14  next node index (1-based)
    uint16_t type;           // +0x16  0x01 = directory
    uint32_t entry_count;    // +0x18  entries in this directory
    uint32_t reserved0;      // +0x1c  zero
    uint32_t reserved1;      // +0x20  zero
    uint32_t listing_offset; // +0x24  offset of this directory's entry list
};
```

There are **39** records in the EU 2011 image (the 39 directories in the FAT
filesystem). The table runs from `0x28` to `0x640`, where the first listing
begins.

> Earlier notes described a mysterious "one-node shift" between names and
> listing offsets. That was an artefact of parsing the record with the name at
> `+0x18` instead of `+0x00`. With the correct field order there is no shift:
> each node's `entry_count` and `listing_offset` describe its own listing.

## Entry lists

Each listing is an array of **32-byte entries** at `listing_offset`:

```c
struct entry {
    char     name[12];   // +0x00  "NAME.EXT", zero padded
    uint8_t  zero[10];   // +0x0c
    uint16_t type;       // +0x16  0 = file, 2 = directory
    uint32_t reserved;   // +0x18
    uint32_t value;      // +0x1c  logical size for files; opaque for dirs
};
```

Examples:

- Root listing at `0x640` has 11 entries: `MMAIN001.DAT`, `BICON001`,
  `MAPAL001`, `OPNG`, `RDSTM001`, `REFER001`, `REFER002`, `SPEECH`, `TMC`,
  `VER_INFO`, `CMP.LST`.
- `BICON001` listing at `0x7a0` has one entry, `BICON001.DAT`, size 114,598.
- `MAPAL001` listing at `0x7c0` has the 46 `BxxRyyR.DAT` tiles.
- `REFER001` listing at `0xde0` has 194 logical `*.DAT` entries whose sizes
  match the `.ind` uncompressed sizes (for example `ADDRE001.DAT` = 79,360).
- `REFER002` listing at `0x2620` also has 194 entries.

For compressed databases (`REFER001`), the size is the **uncompressed** size.
For map tiles, the size can be much larger than the on-disk `.DAT` file; it is
probably the total decompressed payload, but this is **observed, not proven**.

## Practical use

For the compiler, `DRSTR001.DAT` is a manifest: it tells the unit which
logical files exist and how large they are. A regenerated card must keep this
index consistent with the actual files and sizes, especially if files are
added, removed or resized.

`CMP.LST` is a separate, much simpler file containing the single path:

```
\SystemSD\REFER001\
```

It probably tells the update/loader code where compressed databases live.
