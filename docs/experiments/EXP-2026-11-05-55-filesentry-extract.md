# EXP-2026-11-05-55: FILESentry extraction and decode classification (M1.4)

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** synthetic CE ROM built by `tools/cerom.py --selftest`, SHA-256 `f99e20a012059432eda5c4c135839f63ee47ba52a1b25888ba42f6fcf72271a0` (29696 bytes, no vendor data). The real image question refers to `LEAF_2011-2012_QSD-309-101_navi158_eu.img`, first 256 MiB, SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9` (EXP-2026-11-05-51).
- **Claims:** C-573
- **Supersedes:** none
- **Superseded by:** none

## Question

Can `tools/cerom.py files` extract the stored `csize` bytes of a `FILESentry`
and classify a decode attempt without ever writing bytes whose length is not
`rsize`, on a ROM whose answer is known?

## Hypothesis

Exploratory tooling probe. The extraction and classification logic is
format-agnostic and should be provable on a synthetic ROM: an `encode_lzss`
stream must decode to exactly `rsize`, an LZX verbatim header must be
`UNSUPPORTED`, and a `csize == rsize` entry must not be treated as compressed.
The real image is a separate question: EXP-2026-11-05-51 already showed the
real FILESentry payloads are not zlib/LZMA/bz2, so this experiment can only
pin the tool, never the real payload format.

## Inputs

| Item | Value |
| --- | --- |
| Synthetic ROM | `tools/cerom.py --selftest` fixture, written to `/tmp/opencode/m14/synthetic-rom.img` for the CLI run |
| SHA-256 | `f99e20a012059432eda5c4c135839f63ee47ba52a1b25888ba42f6fcf72271a0` |
| Contents | 2 modules, 3 FILESentries: `default.hv` (LZSS, `rsize` 512 / `csize` 103), `boot.hv` (LZX verbatim header, `rsize` 256 / `csize` 4), `wince.nls` (`csize == rsize` 64) |
| Real-image reference | EXP-2026-11-05-51 (`--image-start 0x3e00200`, image B) |
| Tools | `python3 tools/cerom.py`, `python3 tools/cecompress.py` |

## Method

```bash
python3 -m py_compile tools/cerom.py
python3 tools/cerom.py --selftest

python3 - <<'PY'
import sys; sys.path.insert(0, "tools")
import cerom
rom, _ = cerom.build_synthetic_rom()
open("/tmp/opencode/m14/synthetic-rom.img", "wb").write(rom)
PY

python3 tools/cerom.py /tmp/opencode/m14/synthetic-rom.img files
python3 tools/cerom.py /tmp/opencode/m14/synthetic-rom.img \
    files --extract /tmp/opencode/m14/out --decompress --json

python3 tools/selftest.py --only cerom
```

## Observations

`files` with no options is byte-for-byte the previous text view (three lines,
no summary added):

```
  0 default.hv                   attr=0800 real=     512 comp=     103 load=8cae7a00 (file 0x00006c00)
  1 boot.hv                      attr=0800 real=     256 comp=       4 load=8cae7f00 (file 0x00007100)
  2 wince.nls                    attr=0007 real=      64 comp=      64 load=8cae8000 (file 0x00007200)
```

`files --extract DIR --decompress --json` (exit 1):

- `counts`: `files 3, compressed 2, uncompressed 1, stored 0, ok 1,
  unsupported 1, fail 0`.
- `files[0]` = `default.hv`: `status "OK"`, `method_used "lzss"`,
  `output_size 512` (= `rsize`), `sha256
  d56c68b9b5ca6baf9d54ba8824b57d8815e346e2a5fe8cd188142a9b3400c051` over the
  103 stored bytes.
- `files[1]` = `boot.hv`: `status "UNSUPPORTED"`, `error
  "UNSUPPORTED(lzx block type verbatim at output 0); only uncompressed
  (stored) LZX blocks are implemented"`, `output_size`/`method_used` null.
- `files[2]` = `wince.nls`: `status "UNCOMPRESSED"` (no decode attempted).
- `extracted`: `default.hv.0.stored.bin` (103 B) plus `default.hv.0.bin`
  (512 B, equal to the encoder's plaintext); `boot.hv.1.stored.bin` (4 B) and
  no `boot.hv.1.bin`; `wince.nls` not extracted.
- `--decompress --method lzss` on the same ROM: `boot.hv` becomes `FAIL`
  (`lzss: decoded 3 bytes, expected 256`), `output_size` null and no decoded
  bytes accepted.
- Truncated image (`rom[:0x6C01]`): all three records `FAIL`, error
  `stored bytes 0x... lie outside the image (...)`; `counts.fail` 3.
- Record keys, in order: `index, name, attrib, rsize, csize, load, status,
  method_used, output_size, sha256, error`.
- `python3 tools/cerom.py --selftest`: `cerom selftest: 223 checks OK
  (synthetic ROM, no vendor data)` (was 167 before this task; 56 new).
- `python3 tools/selftest.py --only cerom`: `tool:cerom PASS`, `selftest: OK`.

## Interpretation

- **FACT:** the extraction writes exactly `csize` stored bytes; the decoded
  file is written only when the decode length equals `rsize` (checked twice:
  `cecompress` `expected_size` plus an explicit length comparison).
- **FACT:** `csize == rsize` is classified `UNCOMPRESSED` and never extracted;
  `csize != rsize` is the only compression signal used. The `0x0800` attrib
  bit recorded by EXP-2026-11-05-51 is carried in the listing but never read
  for classification, because its meaning is unverified.
- **FACT:** an `UNSUPPORTED` codec/block type leaves only the stored payload on
  disk, and an `OK` decode is the only thing ever written as file contents.
- **OBSERVED:** EXP-2026-11-05-51 found no stdlib stream in the real `0x0800`
  payloads (zlib raw/zlib/gzip, LZMA, bz2 after skipping 0..16 header bytes),
  and only the real size appears to be at offset 0 of the small ones.
- **HYPOTHESIS:** the real payload is a CE-specific container (size field plus
  an internal table/block scheme), so `--decompress --method auto` will most
  likely report `UNSUPPORTED` or `FAIL` on it, not `OK`.
- **UNKNOWN:** whether any real FILESentry payload decodes with
  `tools/cecompress.py`, and what its real container is. This experiment does
  not test vendor bytes at all.

## Conclusion

`tools/cerom.py files` gained `--extract DIR`, `--decompress`, `--method
auto|lzss|lzx` and `--json`, with the default text output unchanged and the
extraction/classification proven by 56 new synthetic checks (one LZSS entry,
one LZX-verbatim entry, one `csize == rsize` entry, wrong-codec and
out-of-image negatives). `docs/format/cerom.md` needs no change: no fact about
the real FILESentry payload changed, and EXP-2026-11-05-51 still stands as the
negative result for stdlib decoders. **Real-image extraction remains
unverified** — the tool reports what happened per entry instead of assuming a
codec.

Claim added by the coordinator (C-573):

> `tools/cerom.py files` lists `FILESentry` records unchanged by default and,
> with `--extract DIR`, writes the stored `csize` bytes of every entry whose
> `csize != rsize`; `--decompress` classifies each through
> `tools/cecompress.py` with `expected_size=rsize` as `OK` (length == `rsize`,
> the only bytes ever written as file contents), `UNSUPPORTED` or `FAIL`, and
> `--json` emits stable records (`index, name, attrib, rsize, csize, load,
> status, method_used, output_size, sha256, error`) with `sha256` over the
> stored bytes. 56 new synthetic checks cover one LZSS entry, one LZX-verbatim
> entry and one `csize == rsize` entry (223 total). EXP-2026-11-05-51 showed
> the real payloads are not a stdlib format, so the real image decode stays
> UNKNOWN.

Status `VERIFIED (tool, synthetic)`; confidence `H`; command
`python3 tools/cerom.py --selftest`.

## Follow-ups

- [ ] Run `files --extract DIR --decompress --json` on image B and record the
      real status mix (expected `UNSUPPORTED`/`FAIL`).
- [ ] Test the `boot.hv` table hypothesis from EXP-2026-11-05-51 against the
      stored `csize` bytes this command now extracts.
- [ ] The kernel decompressor route (M8.E1 / M9.6) is still the only path to a
      real codec identification.
