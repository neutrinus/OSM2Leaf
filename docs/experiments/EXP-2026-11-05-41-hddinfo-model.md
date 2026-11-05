# EXP-2026-11-05-41: HDD_INFO parser and offline map-code model M0

- **Status:** done (tool + model implemented; every verdict still unvalidated)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`;
  `VER_INFO/HDD_INFO.TXT` SHA-256
  `9f014643ed9f4e1359d418f415f264f943e027669b872fc7675f3d99d9bc650a`
  (reconstructed from the documented lines; no vendor file read)
- **Claims:** C-528…C-531 (proposed; not yet registered in `claims.md`)
- **Supersedes:** none
- **Superseded by:** none

## Question

Can the documented map-code comparator be turned into a deterministic offline
model that parses the 72-byte `HDD_INFO.TXT`, predicts a verdict per variant,
and states exactly which predictions are unproven?

## Hypothesis

The comparator (`0x6fab2c` → `0x6faeb0` → `0x6fb05c`, C-300) compares three
numeric fields (`manufacturer_id`, `userdata_type` with a `0..5` bound, and
`destination_id`, C-301) and is silent about the six-line text. A model that
derives those numbers from the lines can predict, for every
length-preserving variant, whether the unit should answer `ACCEPT` or
`DIFFERENT MAP CODE`. The line→field mapping remains a guess (C-304/C-316).

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` (not present on this machine) |
| Image SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| `HDD_INFO.TXT` SHA-256 | `9f014643ed9f4e1359d418f415f264f943e027669b872fc7675f3d99d9bc650a` |
| Block size | 72 bytes, six CRLF-terminated lines, **no** trailing CRLF |
| Tool | `tools/hddinfo.py` (new), `tools/hddinfo_variants.py` (unchanged) |
| Python | 3.14.0, standard library only |

## Method

```bash
python3 -m py_compile tools/hddinfo.py
python3 tools/hddinfo.py --selftest

# layout check: the six documented lines, CRLF-joined, no trailer
python3 - <<'PY'
import hashlib
raw = (b"QSD-302-100\r\nQSD-309-101\r\n02-110100-00\r\n"
       b"SDC08-EVEUR\r\n11-05\r\n470323501005")
print(len(raw), hashlib.sha256(raw).hexdigest())
PY

# synthetic 72-byte fixture (not the factory block)
python3 - <<'PY'
from pathlib import Path
lines = [b"TST-302-100", b"TST-309-101", b"02-990100-00",
         b"TST08-EVEUR", b"99-05", b"990323501005"]
raw = b"\r\n".join(lines)
assert len(raw) == 72
Path("/tmp/opencode/hddinfo/BASE.HDD_INFO.TXT").write_bytes(raw)
PY

python3 tools/hddinfo.py parse /tmp/opencode/hddinfo/BASE.HDD_INFO.TXT
python3 tools/hddinfo.py matrix /tmp/opencode/hddinfo/BASE.HDD_INFO.TXT \
    /tmp/opencode/hddinfo/out
python3 tools/hddinfo.py classify /tmp/opencode/hddinfo/BASE.HDD_INFO.TXT \
    /tmp/opencode/hddinfo/out/line4_lastchar.HDD_INFO.TXT
python3 tools/hddinfo.py matrix /tmp/opencode/hddinfo/BASE.HDD_INFO.TXT \
    /tmp/opencode/hddinfo/out2 --no-permute --json
```

## Observations

### Layout

```
$ python3 - <<'PY' ... PY
72 9f014643ed9f4e1359d418f415f264f943e027669b872fc7675f3d99d9bc650a
```

The six documented lines joined with CRLF and no trailing terminator are
exactly 72 bytes and hash to the archived `VER_INFO/HDD_INFO.TXT` digest. Any
layout with a trailing CRLF is 74 bytes and hashes differently.

### `py_compile` and self-test

```
$ python3 -m py_compile tools/hddinfo.py
py_compile: OK
$ python3 tools/hddinfo.py --selftest
  ok    synthetic block is exactly 72 bytes
  ok    parsed record size is 72
  ok    parse/serialise round-trip is byte-identical
  ok    all six named lines retain their bytes
  ok    no tail bytes in the canonical block
  ok    trailing CRLF is retained
  ok    trailing CRLF is kept in tail, not in line 6
  ok    arbitrary tail bytes round-trip
  ok    arbitrary tail bytes stay in tail
  ok    manufacturer_id derives 0x08 from TST08
  ok    userdata_type derives family digit 3
  ok    destination_id maps EVEUR in the model table
  ok    family digit 3 is inside 0..5
  ok    identical Sys/SD classifies as ACCEPT
  ok    identical Sys/SD has no reasons
  ok    line-6 edit stays ACCEPT (part number not compared)
  ok    line-6 edit leaves manufacturer_id matching
  ok    destination token edit is DIFFERENT
  ok    destination token edit flags destination_id
  ok    destination token edit does not flag manufacturer_id
  ok    manufacturer digit edit is DIFFERENT
  ok    manufacturer digit edit flags manufacturer_id
  ok    manufacturer digit edit does not flag destination_id
  ok    userdata_type 9 is rejected
  ok    userdata_type 9 is flagged out-of-range
  ok    out-of-range reason names the 0..5 bound
  ok    model_fields marks userdata_type 9 out of range
  ok    userdata_type 0 differs but is not out-of-range
  ok    userdata_type 0 is inside the model bound
  ok    lost map_code line is DIFFERENT
  ok    lost map_code line leaves destination_id unparsed
  ok    lost map_code line leaves manufacturer_id unparsed
  ok    fewer than six lines raises ValueError
  ok    classification result is JSON-serialisable
selftest: OK (34 checks)
```

The repository runner discovers the flag and passes it too:

```
$ python3 tools/selftest.py --only hddinfo
tool:hddinfo  PASS  0.07s
selftest: OK
```

### Parse of the synthetic block

```
/tmp/opencode/hddinfo/BASE.HDD_INFO.TXT  72 bytes
  sha256       4e39d042c5a35922d980f3847890014e8fcc76457a15bc53f16a9e2fa41d28d7
  base_code    'TST-302-100'
  map_set      'TST-309-101'
  build        '02-990100-00'
  map_code     'TST08-EVEUR'
  year_month   '99-05'
  part_number  '990323501005'
  tail         (none)
  manufacturer_id 08  0x0008
  userdata_type 302  0x0003
  destination_id EVEUR  0x0001
```

### Variant matrix with predictions

```
$ python3 tools/hddinfo.py matrix .../BASE.HDD_INFO.TXT .../out
wrote 89 variants to .../out (all 72 bytes, same as input)
89 variants, all 72 bytes
  ACCEPT                66
  DIFFERENT MAP CODE    23
    destination_id       8
    manufacturer_id     12
    userdata_type       11
manifest: .../out/MANIFEST.txt
$ echo $?
0
```

`MANIFEST.txt` rows (excerpt):

```
line1_digits_4_000.HDD_INFO.TXT   1  TST-302-100 -> TST-000-100   DIFFERENT MAP CODE
line1_digits_8_000.HDD_INFO.TXT   1  TST-302-100 -> TST-302-000   ACCEPT
line1_lastchar.HDD_INFO.TXT       1  TST-302-100 -> TST-302-101   ACCEPT
line4_digits_3_00.HDD_INFO.TXT    4  TST08-EVEUR -> TST00-EVEUR   DIFFERENT MAP CODE
line4_letters_0_XXX.HDD_INFO.TXT  4  TST08-EVEUR -> XXX08-EVEUR   ACCEPT
line4_letters_6_XXXXX.HDD_INFO.TXT 4 TST08-EVEUR -> TST08-XXXXX  DIFFERENT MAP CODE
swap_1_2.HDD_INFO.TXT             -  permutation of lines          ACCEPT
swap_2_5.HDD_INFO.TXT             -  permutation of lines          ACCEPT
reverse.HDD_INFO.TXT              -  permutation of lines          DIFFERENT MAP CODE
```

With `--no-permute` the tool reports 73 variants
(`ACCEPT 59`, `DIFFERENT MAP CODE 14`) and the JSON `counts`/`field_counts`
match the text output.

### Single classification and exit codes

```
$ python3 tools/hddinfo.py classify BASE.HDD_INFO.TXT out/line4_lastchar.HDD_INFO.TXT
model M0 (HYPOTHESIS; unvalidated): Sys=BASE.HDD_INFO.TXT  SD=line4_lastchar.HDD_INFO.TXT
  manufacturer_id  Sys[0x0008] SD[0x0008]  match
  userdata_type    Sys[0x0003] SD[0x0003]  match
  destination_id   Sys[0x0001] SD[n/a]  different  (Sys['EVEUR'] != SD['EVEU1'] (no numeric mapping))
verdict: DIFFERENT MAP CODE
$ echo $?
1
```

Observed exit codes: ACCEPT → 0, DIFFERENT MAP CODE → 1, missing file and a
three-line file → 2 (with an `error:` line on stderr).

## Interpretation

- **VERIFIED (layout):** six documented lines, CRLF-separated, no trailing
  CRLF, are 72 bytes and reproduce the archived file digest. This is a hash
  check, not a read of the vendor file.
- **VERIFIED (tool):** parse/serialise round-trips arbitrary tail bytes, and
  the 34 synthetic self-test assertions pass. `matrix` output is
  length-preserving (89 variants × 72 bytes) and byte-stable under
  `--no-permute` (73 variants).
- **HYPOTHESIS (model M0):** the three compared numbers are derived as
  `userdata_type` = leading digit of the first number on line 1,
  `manufacturer_id` = digits of the line-4 prefix, `destination_id` =
  line-4 suffix token. Only the *existence and names* of the three compared
  fields and the `0..5` bound come from firmware (C-300/C-301); the derivation
  is a guess ranked by C-304.
- **HYPOTHESIS (consequence):** under M0, edits to lines 2, 3, 5, 6 and to the
  alphabetic prefix of line 4 should be accepted, while edits to the line-1
  family digit, the line-4 manufacturer digits or the line-4 destination token
  should produce `DIFFERENT MAP CODE`. Line permutations are accepted unless
  they move line 4 (or line 1 with a non-`3` family digit) into a compared
  position.
- **UNKNOWN:** whether the unit reads the card file, the `0x06000000` copy, or
  both (C-305); whether `userdata_type` is the family digit at all; whether
  `0` is accepted (`0 < v < 6` per C-301 vs the `0..5` bound used here).
- **Boundary:** `userdata_type == 0` is *inside* M0's accepted range. If the
  firmware really tests `0 < v < 6`, that variant will be rejected while M0
  predicts ACCEPT. This is the single cheapest falsifier in the matrix.

**No verdict in this record or in `MANIFEST.txt` is a validated result.** All
of them are predictions until the spare-card matrix runs and the on-screen /
debug-console messages are captured. Hardware access is currently unavailable,
so nothing here may be presented as confirmed.

## Conclusion

- New tool `tools/hddinfo.py`: 72-byte parser/serialiser with named fields and
  a retained tail; `classify` prediction; `matrix` annotation delegating to
  `tools/hddinfo_variants.py`; `--json`; exits 0/1/2; `--selftest`.
- `docs/format/validation.md` gained a clearly marked **HYPOTHESIS** subsection
  for model M0, its field table and exact commands.
- `tools/README.md` documents the new entry point.
- No `claims.md` row was added; the four proposed claims are listed in the
  report for the coordinator to register (IDs C-528…C-531).
- No change to any existing tool, no vendor data, no git operations.

## Proposed claims

| ID | Claim | Status | Confidence | Evidence |
| --- | --- | --- | --- | --- |
| C-528 | The 72-byte `HDD_INFO.TXT` layout is six CRLF-separated lines with **no** trailing CRLF; the six documented lines reproduce SHA-256 `9f014643…` and a trailing CRLF gives 74 bytes. | VERIFIED | H | EXP-2026-11-05-41; SHA-256 of the reconstructed bytes |
| C-529 | `tools/hddinfo.py` parses/serialises the block byte-identically (including arbitrary tail bytes) and passes 34 synthetic self-test checks. | VERIFIED | H | `python3 tools/hddinfo.py --selftest` |
| C-530 | Model M0 derives the three compared numbers as family digit of line 1, digits of the line-4 prefix and line-4 suffix token, with `userdata_type` bounded to `0..5`; it predicts ACCEPT/DIFFERENT MAP CODE per variant, and every prediction is unvalidated until the spare-card matrix runs. | HYPOTHESIS | L | EXP-2026-11-05-41; comparator chain C-300/C-301, mapping guess C-304 |
| C-531 | `tools/hddinfo.py matrix` emits 89 length-preserving variants (73 with `--no-permute`), each annotated with an M0 prediction in `MANIFEST.txt`, delegating generation to `tools/hddinfo_variants.py`. | VERIFIED | H | EXP-2026-11-05-41; `python3 tools/hddinfo.py matrix …` |

## Follow-ups

- [ ] Run the spare-card matrix and record observed messages per variant; the
      first comparison is predicted-vs-observed, not a re-decode.
- [ ] Resolve the `userdata_type == 0` boundary (`0..5` vs `0 < v < 6`).
- [ ] If swaps of lines 2/3/5/6 are accepted but swapping line 4 is not, the
      "content, not position" question is answered and the line-4 hypothesis
      gains support.
- [ ] If line 4 edits are accepted, model M0's field derivation is wrong; use
      the CE ROM TOC (`tools/ce_rom_parse.py`, `docs/format/firmware.md`) to
      reach the parser statically before inventing a new mapping.
