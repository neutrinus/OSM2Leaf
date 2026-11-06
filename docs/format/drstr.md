# `DRSTR001.DAT` directory index

`DRSTR001.DAT` is the only manifest on the card: a complete index of the
logical file tree (root + directories + files) with logical sizes. It is not a
FAT directory and it does not use the common 512-byte header.

Sample: 11,968 bytes in the EU 2011 image
(SHA-256 `2b7f2fb8901bf18a2ad48334154a6d604c23a775083cb84754626d64417b25f6`).
Re-read on 2026-11-06 through its live FAT root entry (first cluster 29686):
same length, same SHA-256, root node `entry_count` 11 — see
[`EXP-2026-11-06-H6`](../experiments/EXP-2026-11-06-H6-drstr-docs.md).

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
  These are the 11 entries of the DRSTR root node. The **FAT** root directory
  of the same card holds 12 live entries: this list plus `DRSTR001.DAT`
  itself, which DRSTR never indexes (C-163).
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
  static filename table at `0x00179cf8`…`0x00179d18`.
- The two referencing functions (`0x00419684`, `0x0041ba90`) are
  CD-ROM/media-manager routines invoked during media initialisation; no
  count/order/sentinel check on the DRSTR layout (40 nodes, 324 entries,
  leading `u32 = 0x0000002f`) was identified in them.
- Search covered the uncompressed sections of `Navi.exe`, `NaviMapCC.dll`,
  `OBJDLL.dll`, `STDDLL.dll` (build A); the literals occur only in
  `Navi.exe`. A raw-image scan of the first 256 MiB found three `DRSTR`
  strings: the build-A copy at `0x00df8d24`, its duplicate at `0x02bf8d24`,
  and the `DRSTR001.DAT` **directory entry** in the FAT root directory at
  `0x064e5a60` (root cluster `0x064e5400` + entry offset `0x660`). No fourth
  string exists in that range.

## What it is used for

Static firmware evidence names `DRSTR001.DAT` and `\CMP.LST` in `Navi.exe`
functions `0x00419684`/`0x0041ba90` (EXP-2026-11-06-M3.4), and
`MMAIN001.DAT` in `Navi.exe` `0x0041a438` (M3.8, see below). The remaining
database base names (`ZCODE0`, `ADDRE0`,
`POINT0`, `FRWAY0`, `INTER0`, `LCTBL0`) belong to the same static filename
table family; no loader for them is identified (`UNKNOWN`).

The most likely role of DRSTR is a **directory cache / logical size table**,
not the only way to locate data. This is a hypothesis; the cheapest test is to
rename `DRSTR001.DAT` on a spare card and see whether the unit still reads
maps.

## Related files

- `CMP.LST` = exactly `\SystemSD\REFER001\` (19 bytes, no newline).
- `VER_INFO/HDD_INFO.TXT` is a six-line text record; a byte-identical copy is
  embedded in the firmware area at `0x06000000`.

### `MMAIN001.DAT` — the 4 KiB database header

`MMAIN001.DAT` is **not** a manifest and **not** a FAT directory log. It is a
4,096-byte header file holding no file names, offsets or checksums (C-037):

| Offset | Content | Status |
| --- | --- | --- |
| `0x000`–`0x17f` | common 512-byte header text, UTF-16BE: `CLARION`, `HITACHI`, `CLA-NAVI05-01`, `FORMAT VERSION X08-02-00`, `DATA VERSION 11/06/27/01`, `V05.00.00` | VERIFIED (C-010) |
| `0x180` | common prefix `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` | VERIFIED (C-011) |
| `0x184` | database bounds, big-endian `i16` arc-minutes: `0x12c0 0x0500 0xfb50 0x0ff0` = 4800, 1280, −1200, 4080 (80°N…68°E, the EU extent) | OBSERVED (C-1724) |
| `0x18c` | `05 04 02 07 0a 06 08 14`, 8 bytes; language/volume code list | HYPOTHESIS (C-551) |
| `0x194` | `3f` × 12 | OBSERVED (C-552) |
| `0x1a0` | `ff` × 12 | OBSERVED (C-552) |
| `0x1ac` | three-table descriptor: `00 03`, then table `01` (6 entries), table `02` (4), table `04` (1) = 11 `(level, kind, count)` tuples; `00` terminator at `0x1e0` | VERIFIED structure (C-550); counts (C-164) |
| `0x1e0`–`0xfff` | header constants and a `0x800` slot table; not mapped here | UNKNOWN |

- The `0x1ac` counts are the **sums** of the per-level counts of all 46
  `MAPAL001` files (`C-164`: 11/11), which is what an independent builder
  assumes (`tools_ze0/make_mmain.py`, see
  [`ze0-tools.md`](ze0-tools.md)).
- The counts are **big-endian** `u16` on the card (C-1788): the EU 2011 rows
  read `0001 0001 0001 002d 008a 06b5` = 1, 1, 1, 45, 138, 1717. The firmware
  byte-swaps the whole file on read (below); `tools_ze0/make_mmain.py` and
  `tools/cardcheck.py` already parse/write `>H`.
- The `0x184`/`0x5d0` word pair repeats the lat/lon bounds (`0x05d0`:
  `05 00 fb 50 0b 0b`) and is written big-endian by the same builder.
- The `0x18c` codes are **not** mapped to languages in this repo. That the
  list is language/volume codes is a fitted reading (C-551), not a verified
  code→language table.

> **Retraction (2026-11-06).** EXP-2026-11-05-M4.5 described `MMAIN001.DAT` as
> a FAT root-directory log and reported that `0x18c`/`0x1ac` fall inside FAT
> records `ER_INFO`. That object was the **FAT32 root directory**, not the
> file. The root entry `MMAIN001.DAT` (root offset `0x4e0`) stores first
> cluster `0x10002` — high word `0x0001` at `+0x14`, low word `0x0002` at
> `+0x1a` — and the log's "cluster 2" is the root directory itself
> (C-1721/C-1722). The SHA-256 quoted as the extracted file,
> `fe24bbc8…`, is exactly the first 4,096 bytes of the root directory
> (positive control), while the file at cluster `0x10002` is
> `240e7c97…` and starts with UTF-16BE `CLARION` (C-1720). All statements
> above are re-read from that file; the "FAT log" reading is RETRACTED and
> superseded.

### Firmware references (build A, M3.8)

`MMAIN001.DAT` has exactly one code reference in all three builds
(EXP-2026-11-06-M3.8, C-1780–C-1789):

- ASCII literal at `Navi.exe` VA `0x0017adac` (RVA `0x0016adac`, file
  `0x00df8fac`), loaded once at `0x0041a47a` from pool `0x0041a514` in
  function `0x0041a438`. Builds B and C contain no `MMAIN` string (ASCII or
  UTF-16); the positive control `HDD_INFO.TXT` was found by the same scan.
- `0x0041a438` builds `\SystemSD\MMAIN001.DAT` — `wcstombs` of the UTF-16
  `\SystemSD` at `0x00049fd4`, then `strncat` of `\` (`0x0017a9ec`) and
  `MMAIN001.DAT` — opens it with `0x0041b780`, and reads the fd with
  `0x0041b954(fd, dest, 0x1000, 1)`.
- **Checks:** the path-buffer bound (`converted_len + 13 < 260`), the open
  status, and that the read returns exactly `0x1000` bytes. No label,
  version, record-count, cluster or checksum check: `QSD-309-101` and
  `DATA VERSION` are not literals in build A, so no code compares the header
  text.
- The path is part of the **media-mount state machine**: handler table
  `0x0017ab38` row `status = 0`, entry `0x00419ca0`, is the caller; it reads
  `CMP.LST` first and sets global `0x009cfce0 = 1` on success. The debug-only
  `0x0041a52c` dump is a separate "Info Show" path.
- After the read, `0x0041a304` byte-swaps every `u16` (4096 bytes big-endian
  file → little-endian memory) and passes the buffer to OBJDLL
  `OBJ_DriveInfo_writeDataVol` (export #244, VA `0x034b984c`), which copies
  `0x1000` bytes into `obj+8`. The debug dump walks 128 32-byte records and
  prints `MGR ADR` at `+0` and `VOL ADR` at `+0x800` (two `0x800` areas).
- Consequence for M5.6: a verbatim copy satisfies the reader; the `0x1ac`
  totals are an offline `cardcheck` rule, not a firmware check. Regenerate
  the file when the tile set changes (see `TODO.md` M5.6).

