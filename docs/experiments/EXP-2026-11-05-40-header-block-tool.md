# EXP-2026-11-05-40: Header `0x180` block tool and field inventory

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** synthetic headers only; no vendor data was available or read.
  Context image (not accessed):
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** see [Claim candidates](#claim-candidates) (IDs to be assigned;
  the current ledger ends at C-515)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the 128-byte binary block at `0x180` be described field by field from the
published sample bytes, and can its known structural invariants be encoded in
a standard-library tool whose classification and failure modes are testable
without vendor data?

## Hypothesis

The repository already documents enough byte-level evidence for a structural
tool: the six UTF-16BE text slots, the `0x180` common prefix, the class-dependent
`0x18c` area and the `0x1ac` descriptor container. The semantic meanings will
remain `UNKNOWN`/`HYPOTHESIS`, but the layout can still be checked and
regressed with synthetic headers.

## Inputs

| Item | Value |
| --- | --- |
| Vendor image | none available on this machine; not read |
| Published header samples | `docs/format/file-header.md` (`MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT`) |
| Claim inputs | C-010, C-011, C-012, C-037, C-052 |
| New tool | `tools/header_block.py` |
| Fixtures | `synth_header()`: `MMAIN`, `REFER`, `MAPAL`, `RDSTM` |

## Method

```bash
python3 -m py_compile tools/header_block.py
python3 tools/header_block.py --selftest
python3 tools/header_block.py dump FILE
python3 tools/header_block.py class FILE
python3 tools/header_block.py compare FILE_A FILE_B
python3 tools/header_block.py check FILE [FILE ...]
python3 tools/header_block.py dump FILE --json
```

The self-test builds four synthetic 512-byte headers with the documented text
slots and the documented per-class `0x180` signatures. It creates no vendor
files and writes nothing persistent.

## Observations

### Tool self-test

`python3 -m py_compile tools/header_block.py` exits `0` with no output.

`python3 tools/header_block.py --selftest` (exact output):

```text
  ok   classify MMAIN from text+block+name
  ok   family MMAIN is clarion-ze0 from UTF-16BE text
  ok   text fields MMAIN match slots 0x000-0x180
  ok   classify REFER from text+block+name
  ok   family REFER is clarion-ze0 from UTF-16BE text
  ok   text fields REFER match slots 0x000-0x180
  ok   classify MAPAL from text+block+name
  ok   family MAPAL is clarion-ze0 from UTF-16BE text
  ok   text fields MAPAL match slots 0x000-0x180
  ok   classify RDSTM from text+block+name
  ok   family RDSTM is clarion-ze0 from UTF-16BE text
  ok   text fields RDSTM match slots 0x000-0x180
  ok   MAPAL class from block alone
  ok   RDSTM class from block alone
  ok   REFER/MMAIN header alone is honestly ambiguous
  ok   MMAIN filename resolves the ambiguity
  ok   dump u32 grid has 32 entries
  ok   dump u16 grid has 64 entries
  ok   dump starts at 0x180
  ok   dump covers 128 bytes
  ok   first u32 is ff24ffff (little-endian bytes ff ff 24 ff)
  ok   first u16 is ffff
  ok   block ASCII run is the 0x3f class fill
  ok   ASCII runs are offset and length correct
  ok   first ASCII run starts at 0x1002
  ok   invariants pass for synthetic MMAIN
  ok   invariants pass for synthetic REFER
  ok   invariants pass for synthetic MAPAL
  ok   invariants pass for synthetic RDSTM
  ok   wrong CLARION magic fails magic-clarion
  ok   truncated 400-byte header fails header-size
  ok   wrong 0x180 prefix fails block-prefix
  ok   wrong n_tables fails descriptor-container
  ok   header report is JSON-serialisable
  ok   compare finds differing bytes
  ok   compare classes are MAPAL and RDSTM
  ok   compare reports 0x1ad descriptor run
header_block selftest: 37/37 passed
header_block selftest: OK
```

### Published byte layout used by the tool

| Offset | Bytes | Source files in the published evidence |
| --- | --- | --- |
| `0x180`–`0x18b` | `ff ff 24 ff 12 c0 05 00 fb 50 0f f0` | `MMAIN001.DAT`, `REFER002/COORD001.DAT`, `MAPAL001/B28R070R.DAT`, `RDSTM001/RDSTM001.DAT` @ `0x180` |
| `0x18c`–`0x193` | `05 04 02 07 0a 06 08 14` (MMAIN/REFER) or `3f` × 8 (MAPAL/RDSTM) | same four files @ `0x18c` |
| `0x194`–`0x19f` | `3f` × 12 | same four files @ `0x194` |
| `0x1a0`–`0x1ab` | `ff` × 12 | same four files @ `0x1a0` |
| `0x1ac` | `00` | same four files @ `0x1ac` |
| `0x1ad` | `03` MMAIN/REFER; `02` MAPAL; `01` RDSTM | same four files @ `0x1ad` |
| `0x1ae`–`0x1af` | `01 06` MMAIN/REFER/MAPAL; `03 02` RDSTM | same four files @ `0x1ae` |

### Synthetic CLI observations

| Command | Observation |
| --- | --- |
| `class` on synthetic `B28R070R.DAT` | `MAPAL` from block signature; filename agrees |
| `class` on synthetic `COORD001.DAT` | `REFER` only because the filename resolves `MMAIN-OR-REFER` |
| `class` on a bare MMAIN/REFER header | `AMBIGUOUS`, candidates `MMAIN`, `REFER` |
| `compare` MAPAL vs RDSTM | first differing run `0x1ad..0x1ba` (13 bytes), 23/512 bytes differ |
| `check` on a valid synthetic header | `PASS (exit 0)` |
| `check` with `CLARION` cleared | `FAIL (exit 1)`, `magic-clarion` failed |
| `check` on a 400-byte header | `FAIL (exit 1)`, `header-size` failed |
| `dump` on a 400-byte header | exit `2` (needs 512 bytes) |
| `dump FILE --json` and `--json dump FILE` | both exit `0`; JSON parses; u32 grid has 32 entries |

## Interpretation

- **FACT:** the published sample bytes partition `0x180`–`0x1ff` into a
  12-byte prefix, a 20-byte class area, a 12-byte `ff` run and an `0x1ac`
  descriptor container.
- **OBSERVED:** `MMAIN001.DAT` and `REFER002/COORD001.DAT` share the same
  documented header bytes, so REFER vs MMAIN cannot be decided from those
  bytes alone.
- **OBSERVED:** the descriptor structure fits all four published classes when
  read as `00 | n_tables | table_id | n_entries | 4-byte entries`. Only the
  map-tile structure was previously `VERIFIED` (C-052); the other classes are
  `OBSERVED` here.
- **HYPOTHESIS:** `0x18c`–`0x193` is a per-language code list in MMAIN/REFER.
  The eight codes are not mapped to languages.
- **HYPOTHESIS:** the `3f` and `ff` runs are fill/default and reserved/absent
  markers. No experiment supports either interpretation.
- **UNKNOWN:** the meaning of every prefix word, the class codes, the `level`,
  `kind` and `count` entry fields, and the descriptor tail.
- **VERIFIED (tool behaviour):** the self-test reproduces classification,
  dump shape, JSON serialisation and the two required failure modes (wrong
  magic, truncated header) on synthetic data.
- **VERIFIED (negative):** no vendor data was read, so this experiment does
  not independently reproduce the published sample bytes. Claims about those
  bytes stay `OBSERVED`, not newly `VERIFIED`.

## Conclusion

`tools/header_block.py` now dumps the `0x180` block as little-endian `u32` and
`u16` grids with ASCII runs, detects the Clarion family from the UTF-16BE text,
refines the variant from the documented block signature and filename, compares
two headers, and validates the known structural invariants with exit codes
`0/1/2`. `docs/format/file-header.md` now carries the field-by-field inventory
with file/offset evidence and explicit `UNKNOWN`/TODO rows. The old
"format revision / record sizes / LOD counts" description remains a
`HYPOTHESIS` and is not used by the checker.

## Follow-ups

- [ ] Re-run `check` on the four real samples to promote the `OBSERVED` rows
      to `VERIFIED` (needs working data at
      `/home/marek/projekty/leafre-work/root/`).
- [ ] Decode the six `0x180` prefix words with a controlled mutation matrix.
- [ ] Map the `05 04 02 07 0a 06 08 14` codes to languages or locales.
- [ ] Establish what distinguishes REFER from MMAIN inside the header, if
      anything.
- [ ] Parse the `LEV3456R.DAT` descriptor separately; it was not covered here.

## Claim candidates

IDs are intentionally unassigned because `docs/research/claims.md` was not
edited by this task. The ledger's highest current ID is C-515.

| Proposed ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-522 | The `0x180`–`0x1ff` block is documented in four regions: prefix `0x180`–`0x18b`, class area `0x18c`–`0x19f`, `ff` run `0x1a0`–`0x1ab`, and descriptor container at `0x1ac`. | OBSERVED | M | `docs/format/file-header.md`; four samples @ the listed offsets |
| C-523 | `MMAIN001.DAT` and `REFER002/COORD001.DAT` are identical in the documented header fields; no header-only REFER/MMAIN discriminator is known. | OBSERVED | M | same published hexdumps; `tools/header_block.py class` reports `AMBIGUOUS` without a filename |
| C-524 | The `0x1ac` container is `00`, `n_tables`, then `table_id`, `n_entries` and 4-byte `(level:u8, kind:u8, count:u16 LE)` entries; `n_tables` is 3 for MMAIN/REFER, 2 for MAPAL and 1 for RDSTM in the documented samples. | OBSERVED (VERIFIED for MAPAL via C-052) | M | C-052; `MAPAL001/B28R070R.DAT` @ `0x1ac`; `MMAIN001.DAT` @ `0x1ac`; `RDSTM001/RDSTM001.DAT` @ `0x1ac` |
| C-525 | The eight-byte `05 04 02 07 0a 06 08 14` list at `0x18c` is a per-language/code list. | HYPOTHESIS | L | C-037; `MMAIN001.DAT` @ `0x18c`; no code→language mapping |
| C-526 | The `3f` bytes at `0x18c`–`0x19f` and the `ff` bytes at `0x1a0`–`0x1ab` are fill/reserved markers. | HYPOTHESIS | L | four published samples; no mutation experiment |
| C-527 | `tools/header_block.py` checks the 512-byte size, text magic, `0x180` prefix, descriptor container and block trailer, reports `OBSERVED` rules as warnings, and passes 37/37 synthetic self-tests. | VERIFIED (tool) | H | `python3 tools/header_block.py --selftest`; this record |
