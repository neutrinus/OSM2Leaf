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

## Writing

`tools/cmpind_writer.py` implements two modes:

| Mode | Behaviour | Byte-identity |
| --- | --- | --- |
| `preserve` | keep the original compressed chunk bytes, rebuild only `.ind` | **194/194 `.cmp` and `.ind` identical** |
| `recompress` | inflate, split into 64 KiB chunks, deflate from scratch | factory-identical only with matching zlib |

Factory-identical stock zlib settings (verified on all 36,581 chunks):

```
level 6, wbits 15, memLevel 8, Z_DEFAULT_STRATEGY, DEFLATED
```

**Important:** Python 3.14 may link **zlib-ng**, which reproduces **0/194**
factory `.cmp` files even though the payload is correct. On such a machine,
byte-identity requires `preserve`. This is a property of the compressor build,
not of the format.

Build rule:

1. unchanged file → preserve streams (or copy the original pair);
2. changed file → recompress only the 64 KiB chunks containing changed bytes,
   keep all other streams verbatim, rebuild `.ind` offsets;
3. new/whole-file rewrite → pin stock zlib 1.3.1 and check these fixtures:

```
COORD001.DAT.cmp  6074a93c27081bf3e770411a549f4427721cd5bd44ef3198473ef03742956ed1
POINT032.DAT.cmp  1dac3ae6d330414686a69df6749b3bb8b563029ce00ecefad1bba02170f1bba7
ADDRE001.DAT.cmp  bbeb60f242a57f297d2d2c6d7180b8b68e57a2bec90fcbfd699eead7271a7025
```

## zlib runtime guard

Byte-identity is a property of the compressor, not of the format, so a tool
must not report `FAIL` when the interpreter links zlib-ng. `tools/zlibinfo.py`
classifies the running library from `zlib.ZLIB_VERSION` (header) and
`zlib.ZLIB_RUNTIME_VERSION` (loaded library) and every tool that recompresses
prints that line:

```
zlib: zlib 1.3.1, runtime 1.3.1 (stock, reference build)
```

The verdicts are kept apart:

| Output | Exit | Meaning |
| --- | --- | --- |
| `OK` | 0 | byte-identical |
| `FAIL` | 1 | decoded payload or model is wrong |
| `UNVERIFIABLE` | 3 | payload reproduces, the compressor build differs |

On zlib-ng (`flavour zlib-ng`) or any unrecognised build the identity check is
reported as `UNVERIFIABLE` and the tool names the runtime; the data-level
checks still run. `--require-stock-zlib` (on `lev3456.py verify`/`rebuild` and
`cmpind_writer.py recompress`/`verify`) refuses before doing any work with the
same exit 3. `cmpind.py verify` only decompresses, so it prints a non-stock
note instead of failing, and `--json` carries the runtime in a `zlib` field.
`ind_mutate.py` never recompresses (it rewrites only `.ind` bytes), so a
non-stock build gets an informational note only.

```bash
python3 tools/zlibinfo.py                     # one line
python3 tools/zlibinfo.py --json              # ok / zlib_version / runtime_version / flavour / reference
python3 tools/zlibinfo.py --require-stock-zlib  # exit 3 when untrusted
```

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
