# `.cmp` / `.ind` compressed containers

> **Evidence status:** the layout and decompression below are `VERIFIED`
> against all 194 pairs in the EU 2011 image. See
> [`../research/claims.md`](../research/claims.md).

`REFER001/` contains 194 logical databases. Each logical file `NAME.DAT` is
stored as:

- `NAME.DAT.cmp` — compressed payload
- `NAME.DAT.ind` — chunk index

This format is **fully decoded and verified** against all 194 pairs in the EU
2011 image.

## `.ind` layout

Little-endian:

```c
struct leaf_ind {
    uint32_t uncompressed_size;   // total logical size, including 512-byte header
    uint32_t compressed_size;     // must equal the .cmp file size
    uint32_t chunk_count;         // number of zlib streams
    uint32_t chunk_size;          // usually 0x10000 (65536)
    uint32_t chunk_offset[chunk_count]; // byte offset of each stream in .cmp
};
```

The header is 16 bytes, followed by `chunk_count` 4-byte offsets:

```
ind_size = 16 + 4 * chunk_count
```

The final stream extends from `chunk_offset[n-1]` to the end of `.cmp`.

### Example: `COORD001.DAT.ind`

20 bytes:

```
00 12 00 00   uncompressed = 0x1200 = 4608
46 02 00 00   compressed   = 0x0246 = 582
01 00 00 00   chunk_count  = 1
00 00 01 00   chunk_size   = 0x00010000 = 65536
00 00 00 00   chunk_offset[0] = 0
```

### Example: `ADDRE001.DAT.ind`

24 bytes:

```
00 36 01 00   uncompressed = 0x13600 = 79360
d4 be 00 00   compressed   = 0xbed4 = 48852
02 00 00 00   chunk_count  = 2
00 00 01 00   chunk_size   = 65536
00 00 00 00   chunk_offset[0] = 0
17 8a 00 00   chunk_offset[1] = 0x8a17 = 35351
```

Chunk 0 is `cmp[0:35351]`, chunk 1 is `cmp[35351:48852]`.

## Decompression

Each chunk is an **independent zlib stream** (header `78 9c`). Concatenate
the decompressed chunks in order:

```python
out = b"".join(zlib.decompress(cmp[offs[i]:offs[i+1] or len(cmp)])
               for i in range(n))
assert len(out) == uncompressed_size
```

Notes:

- `zlib.decompress(cmp)` alone only returns the first stream. A naive decoder
  appears to work for many small files and silently truncates large ones.
- Non-final chunks decompress to exactly `chunk_size` bytes.
- The decompressed payload still begins with the common 512-byte header
  described in [file-header.md](file-header.md).

## Verification

`python3 tools/cmpind.py verify REFER001` checks every pair and reports:

- `.ind` size matches `16 + 4 * chunk_count`
- `compressed_size` matches the `.cmp` size
- every chunk decompresses
- concatenated length equals `uncompressed_size`

Result on the EU 2011 image: **194/194 OK, 0 mismatches.**

Largest sample: `POINT005.DAT` — 2,498 chunks, 56,870,463 bytes compressed,
163,647,744 bytes uncompressed.

## Why it matters

This is the easiest writable part of the format: the compressor is plain
zlib, the index is simple, and regenerated files can be validated offline
before touching a card. Address/POI data is therefore a good first target for
a round-trip writer.
