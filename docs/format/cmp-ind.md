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

## Firmware reader (EU2011 `Navi.exe` build A — located, M3.2b)

> Evidence: `EXP-2026-11-19-M3.2b-cmp-chunk-reader-walk-up.md` (C-5100–C-5109;
> supersedes the pass-2 "no static caller" blocker, which searched the
> mid-prologue VA `0x0041c7e8`), pass 1 `EXP-2026-11-06-M3.2b-…` (zlib,
> C-2060–C-2063). All VAs are EU2011 (`--image-start 0x200200`, sec0). The
> rules a writer must meet are checked by `tools/cmp_reader_contract.py`
> (factory EU set: 194/194 pass).

zlib 1.1.3 is linked into `Navi.exe` sec0: `inflateInit2_` `0x542256`,
`inflate` `0x54233c` (tramp `0x54232c`), `inflateEnd` `0x54220c`, one-shot
wrapper `0x542148` (C-2061, C-2062). The `.cmp` layer is the only caller of the
wrapper besides `0x542100` (an argument-checking front used by three other
functions, C-5108).

**Open** (`NAME.DAT` requested with the "compressed" flag set):

`0x0041855c` → `0x00417fe0` (path from `0x00418dfc`) → `0x0041b780(path, 1)`
→ `0x0041bed4` (critical section) → `0x0041be30`: take a free handle slot
(50 × `0x118` B), then `0x0041c2e0` matches the path against `CMP.LST` —
listed: `0x0041c524` reads the 16-byte header of `path + ".IND"`
(`0x0041c474`), stores the logical size and the `.ind` size
`16 + 4*count`, opens `path + ".CMP"` with `"rb"`, marks the slot
compressed (`u16 +0x116 = 1`); not listed: plain `fopen(path)`. `CMP.LST` is
read whole at mount (`0x0041ba90` → … → `0x0041c124`); entries are
NUL-separated, an entry ending in `\` matches the path's directory part, any
other entry the whole path, only `A`–`Z` are case-folded (C-5103). The
factory list `\SystemSD\REFER001\` therefore covers exactly the files
directly in `REFER001`. The flag alone does not compress: `MMAIN001.DAT` is
opened with flag 1 (`0x0041a438`) and served plain.

**Read:** `0x0041b954` → `0x0041c044` → `0x0041c990(ctx, handle, buf, len)`:

1. `0x0041c8c4` gets the `.ind` (through a name-keyed cache, `0x0041c404`),
   checks **word 3 (`chunk_size`) `== 0x10000`** (`0x0041c92a`) and turns
   position/length into a first and last chunk index (`_divlu` by
   `chunk_size`, last clamped to `count`).
2. `0x0041c5f0` — **the loop over `chunk_offset[]`** — re-checks
   `chunk_size` (`0x0041c696`) and fills 20-byte entries for
   `i = first..last`: `+0 = chunk_offset[i]` (read at `ind + 16 + 4*i`),
   `+4 = chunk_offset[i+1] - chunk_offset[i]` (last: `.ind` word 1 minus
   `chunk_offset[i]`), `+8 = i * chunk_size`, `+12 = chunk_size` (last:
   `logical % chunk_size`, or `chunk_size` if 0; `logical` when `count == 1`).
   A batch stops at 20 entries or before the compressed sum exceeds
   `0x14000` bytes.
3. `0x0041c990` sets `+16` to the stream's address in the compressed buffer,
   **seeks the `.cmp` to `chunk_offset[first]`** (`0x0041ca28`) and **reads the
   batch's summed length in one call**, which must return exactly that many
   bytes (`0x0041ca3c`).
4. `0x0041c7dc` inflates each entry with `0x542148`: whole chunks straight
   into the caller's buffer, a partial first/last chunk into a `0x10000`
   scratch buffer and `memcpy`.

**M3.2 answered (C-5102, C-5104):** (a) `chunk_size` is **compared** with the
configured `0x10000` (`0x0041c92a`, `0x0041c696`; the constant is built by
`mov #1; shll16` at `0x0041bafe` in the mount `0x0041ba90`) and is then the
divisor/multiplier; it sizes nothing — the scratch (`0x10000`) and batch
(`0x14000`) buffers come from the mount configuration. (b) The reader
**seeks by `chunk_offset[]`**; there is no `78 9c` scan.

**L3 run (M3.2, C-5330–C-5334, EXP-2026-11-20-M3.2-ind-handling-l3):**
`tools/cmp_read_l3.py` executes the EU2011 layer — manager ctor `0x0041bc98`
with the mount's constants, open `0x0041b780`, seek `0x0041b8a4`, read
`0x0041b954` — with the ops table bound to host files. Factory ADDRE001
(whole) and POINT010 (page `0x840ba0`) come back byte-identical to
`cmpind_codec`; the `.cmp` is accessed only as `seek(chunk_offset[first])` +
one `read(sum)` (POINT010: seek `0x234d7f` = `chunk_offset[132]`); with a
valid `78 9c` decoy prepended and the index shifted by `0x1000` the reader
seeks to `0x1000` and is still correct; a last offset one byte early fails
(-1), no resync. `chunk_size` `0x8000`/`0x20000` is rejected at `0x0041c92a`
before any `.cmp` byte is read; changing only the mount word to `0x20000`
rejects the factory file (the compare is against the configuration), and with
both at `0x20000` the read returns 79,360 **wrong** bytes — the equality
compare is the only `chunk_size` check.

**The 8 `ind_mutate` variants through the layer (M3.3, C-5340–C-5344, EXP-2026-11-20-M3.3-ind-variants-l3):**
ADDRE001 with the original `.cmp`, whole-file read. Rejected (-1), as
`cmpind.py`: `size_20000`, `size_8000` (at the `chunk_size` compare, no `.cmp`
access), `off0_1`, `off_last_m1`, `off_last_p1`, `off_last_0` (inflate fails).
**More lenient than `cmpind.py`:** `count_p1` is read byte-identical (the extra
entry is never visited); `count_m1` returns the full 79,360 B with bytes from
65,536 on **wrong** — no error. D1 below is therefore a writer obligation the
firmware does not enforce.

**Writer contract** (each rule tied to a compare above; `cmp_reader_contract.py
check DIR`):

| Rule | Requirement | Firmware site |
| --- | --- | --- |
| R1 | `.ind` word 3 == `0x10000` | `0x0041c92a`, `0x0041c696` |
| R2 | every compressed chunk ≤ `0x14000` B (factory max 65,562) | `0x0041c72a`, `0x0041c9da` |
| R3 | `.ind` word 1 == `.cmp` size | last-chunk length `0x0041c6fc`; read check `0x0041ca3c` |
| R4 | `.ind` is `16 + 4*count` bytes | `0x0041c6c6`, `0x0041c576` |
| D1 | `count == ceil(logical/0x10000)`, offsets increase from 0 | not tested; a too-small count reads **wrong bytes without error**, a too-large one is ignored (M3.3, C-5341/C-5342) |
| — | the directory (or file) is listed in `CMP.LST` | `0x0041c2e0` |
