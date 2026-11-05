# EXP-2026-11-05-42: Section-4 parse/preserve tool

- **Status:** done (synthetic only; vendor tile not re-measured)
- **Date:** 2026-11-05
- **Sample:** synthetic 3-record / 5-name section-4 payload; no vendor data
- **Claims:** C-280, C-286; proposed C-520/C-521 (not added to the ledger)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can a standard-library tool parse a section-4 payload without inventing a
grammar, preserve it byte-for-byte, and refuse to build the fields that are
still unknown?

## Hypothesis

The zlib framing and the documented header fields are enough for a lossless
preserve mode. Build mode must fail closed for names and the binary fields
between the country code and the name list, because their placement grammar is
not mapped.

## Inputs

| Item | Value |
| --- | --- |
| Vendor image / file | none (no vendor data in this task) |
| Synthetic payload | 3 zlib members, 3 records, 5 names, 144 bytes |
| Synthetic payload SHA-256 | `f2ce2a1e370129cf1c8f917bdd497212267fc4bc841c86cfee65199f65790f51` |
| Tool | `tools/section4.py` (stdlib only, Python 3.10+) |

The compressed synthetic bytes depend on the local zlib build, so the SHA-256
above pins this run's fixture, not a repository binary. The decompressed
records are deterministic.

## Method

```bash
python3 -m py_compile tools/section4.py
python3 tools/section4.py --selftest
```

The selftest synthesises three records:

- record 0: `RODOS`, `LINDOS`;
- record 1: `ZIGHIDÌ` (Latin-1 `0xcc`);
- record 2: `PARALIA AFANTOU`, `ARCHIPOLI:ELEOUSA`.

All three carry parcel words `0x1234`/`0x5678`, type `0x0009`, country 300 and
an undocumented 10-byte binary span at `0x06..0x0f`. The records are compressed
separately and concatenated with one zero padding byte to exercise framing.

A second CLI pass used `parse --json-out`, `encode preserve`, `cmp` and
`encode build` on the same 144-byte payload.

## Observations

`py_compile` and the synthetic test:

```text
py_compile: OK
section4 selftest: 3 records, 5 names, payload sha256 f2ce2a1e370129cf1c8f917bdd497212267fc4bc841c86cfee65199f65790f51
  parse: OK (countries [300, 300, 300], type 0x0009)
  preserve: OK (byte-identical, 144 bytes)
  build refusal: OK (5 unknown name fields, exit 3)
  build nameless record: OK (country 300)
selftest: OK
```

CLI round-trip and refusal:

```text
section4: /tmp/opencode/s4/payload.bin (144 bytes, sha256 f2ce2a1e370129cf1c8f917bdd497212267fc4bc841c86cfee65199f65790f51)
framing: zlib, records: 3, names: 5 (unique 5)
record 0: 36 B, type 0x0009, country 300 (Greece), parcel w0=0x1234 w1=0x5678
  u32[0x0000] = 0x12345678  parcel_code (OBSERVED)
  names (2):
    +0x0013  0=RODOS [ascii]
    +0x001b  0=LINDOS [ascii]
  opaque:
    +0x0006..0x000f (10 B): de ad 11 11 22 22 aa bb cc dd
    +0x0012..0x0012 (1 B): 00
...
section4: preserve ... -> ... (144 bytes, sha256 f2ce2a1e...)
cmp: byte-identical
verify: ...
  records: 3, names: 5 (unique 5)
  preserve round-trip: OK byte-identical (144 bytes)
reference counts (C-126, EXP-2026-11-05-32; observed, not re-measured):
  year  records  names
  2011      20     68
  2014      24    126
  2016      24    129
  record delta vs 2011: 2014 +4, 2016 +4
  measured payload: 3 records / 5 names
  reference comparison: not requested (pass --reference-year)
section4: build refused: 5 unknown field(s); no output written
  - records[0].names[0] at 0x0013: name-list placement/terminator grammar is UNKNOWN; cannot rebuild 'RODOS' without guessing
  - records[0].names[1] at 0x001b: name-list placement/terminator grammar is UNKNOWN; cannot rebuild 'LINDOS' without guessing
  - records[1].names[0] at 0x0013: name-list placement/terminator grammar is UNKNOWN; cannot rebuild 'ZIGHIDÌ' without guessing
  - records[2].names[0] at 0x0013: name-list placement/terminator grammar is UNKNOWN; cannot rebuild 'PARALIA AFANTOU' without guessing
  - records[2].names[1] at 0x0025: name-list placement/terminator grammar is UNKNOWN; cannot rebuild 'ARCHIPOLI:ELEOUSA' without guessing
build exit=3
build: no output written
```

Reference row, printed as data only:

| Year | Records | Names | Record delta vs 2011 |
| --- | --: | --: | --: |
| 2011 | 20 | 68 | — |
| 2014 | 24 | 126 | +4 |
| 2016 | 24 | 129 | +4 |

The 20/24/24 counts are `OBSERVED` in `EXP-2026-11-05-32` (claim C-126), not
re-derived here. The tool prints them without treating them as a validation of
the current payload.

## Interpretation

- **FACT:** a 3-record / 5-name payload parses into 3 records and 5 names with
  country 300 and type `0x0009`.
- **FACT:** `encode preserve` reproduces the 144-byte payload byte-for-byte.
- **FACT:** `encode build` refuses all 5 names with exit 3 and writes no output.
- **OBSERVED:** the name splitter follows the viewer's `d=NAME` rule; adjacent
  names and a Latin-1 byte decode as expected.
- **OBSERVED:** a nameless synthetic record builds only because its whole
  undocumented span is supplied back as opaque hex.
- **UNKNOWN:** the binary fields at `0x06..0x0f`, the name-list start offset,
  its terminator/count grammar, and any semantic u32 at `0x08`/`0x0c`.
- **NOT TESTED:** a real vendor section-4 payload, because no vendor data is
  present in this task.

## Conclusion

`tools/section4.py` now provides the fail-closed parse/preserve/verify path and
the "Section 4 grammar" subsection in `docs/format/map-tiles.md`. It does not
add a section-4 encoder, and it does not promote any unknown offset to a known
one.

Proposed ledger rows (scoped out of this task; `claims.md` was not edited):

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-520 | Section-4 records expose only the parcel words at `0x00`/`0x02`, type `0x0009` at `0x04` and ISO 3166 country at `0x10`; bytes `0x06..0x0f` and the name-list placement remain `UNKNOWN`, and `tools/section4.py` reports them as hex. | VERIFIED (tool) | H | EXP-2026-11-05-42; `python3 tools/section4.py --selftest` |
| C-521 | Section-4 `preserve` is byte-identical; `build` refuses records with names or uncovered opaque bytes (exit 3), so unchanged and edited tiles must carry section 4 verbatim until the grammar is mapped. | VERIFIED (tool) | H | EXP-2026-11-05-42; `encode preserve`, `cmp` |

## Follow-ups

- [ ] Run `parse`/`verify` on the real `B30R048R.DAT` and compare the measured
  counts with 20/68 (2011); keep name counts marked as splitter-dependent.
- [ ] Map `0x06..0x0f` and the name-list start/terminator, then extend `build`.
- [ ] Do not build section 4 from OSM data; preserve it verbatim.
