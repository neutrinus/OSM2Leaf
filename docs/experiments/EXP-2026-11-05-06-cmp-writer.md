# EXP-2026-11-05-06: `.cmp` / `.ind` writer and byte-identity

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-190…C-195
- **Supersedes:** none
- **Superseded by:** none

## Question

Can we write `.cmp`/`.ind` back so that an unchanged file is byte-identical,
and what exactly is required for a changed file?

## Hypothesis

Preserving the original compressed streams guarantees byte-identity; a full
recompress is byte-identical only if the zlib build/settings match the factory.

## Inputs

Representative files from `REFER001`:

| File | Chunks | Logical size |
| --- | --: | --: |
| `COORD001.DAT` | 1 | 4,608 B |
| `ADDRE001.DAT` | 2 | 79,360 B |
| `POINT032.DAT` | 1 | 20,224 B |
| `ADDRE002.DAT` | 322 | 21,067,520 B |
| `POINT005.DAT` | 2,498 | 163,647,744 B |
| `ADDRE008.DAT` | 3,093 | 202,700,032 B |

Tool: `tools/cmpind_writer.py`.

## Method

```bash
# Preserve original streams, rebuild only the index
python3.13 tools/cmpind_writer.py preserve \
    REFER001/COORD001.DAT.cmp REFER001/COORD001.DAT.ind out COORD001.DAT

# Full recompress
python3.13 tools/cmpind_writer.py recompress \
    REFER001/COORD001.DAT.cmp REFER001/COORD001.DAT.ind out COORD001.DAT

# Verify every pair
python3.13 tools/cmpind_writer.py verify REFER001
```

## Observations

| Mode | Result |
| --- | --- |
| Preserved streams | **194/194 `.cmp` and `.ind` byte-identical** |
| Recompress, stock zlib 1.3.1 | 194/194 files, **36,581/36,581 chunks byte-identical** |
| Recompress, zlib-ng 1.3.1 (Python 3.14) | 194/194 payloads correct, **0/194 `.cmp` byte-identical** |
| `DRSTR001.DAT` writer | 11,968 B, byte-identical |

Factory-identical stock zlib settings:

```
level = 6
wbits = 15
memLevel = 8
strategy = Z_DEFAULT_STRATEGY
method = DEFLATED
```

zlib-ng deltas range from `+1` to `+576,155` bytes; an exhaustive search over
1,215 settings found no zlib-ng combination that reproduces the factory
streams.

Fixtures for a pre-write sanity check:

```
COORD001.DAT.cmp  6074a93c27081bf3e770411a549f4427721cd5bd44ef3198473ef03742956ed1
POINT032.DAT.cmp  1dac3ae6d330414686a69df6749b3bb8b563029ce00ecefad1bba02170f1bba7
ADDRE001.DAT.cmp  bbeb60f242a57f297d2d2c6d7180b8b68e57a2bec90fcbfd699eead7271a7025
```

## Interpretation

- **FACT:** preserved-stream writing is byte-identical on every machine.
- **FACT:** stock zlib 1.3.1 with the settings above reproduces the factory
  streams for this corpus.
- **FACT:** zlib-ng does not; byte-identity is a property of the compressor
  build, not of the format.
- **OBSERVED:** same build/settings are deterministic; different builds are
  not.
- **UNKNOWN:** whether an older stock zlib (2011 era) behaves identically;
  1.3.1 matching all chunks is strong but not a proof for all builds.

## Conclusion

A build tool should:

1. **Unchanged file:** preserve streams (or copy the original `.cmp`/`.ind`).
2. **Changed file:** preserve streams for untouched chunks; recompress only
   the 64 KiB chunks containing changed bytes; rebuild `.ind` offsets.
3. **New/whole-file rewrite:** pin stock zlib 1.3.1 and check the three
   fixtures before writing.

## Follow-ups

- [ ] Add `cmpind_writer.py` to the build tool as the only writer.
- [ ] Check the US dump separately (chunk counts/settings may differ).
- [ ] Add a pre-write fixture check to the future `tools/build.py`.
