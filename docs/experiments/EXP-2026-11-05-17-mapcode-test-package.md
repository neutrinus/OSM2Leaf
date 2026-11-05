# EXP-2026-11-05-17: Map-code comparator corrected and test package

- **Status:** done (comparator corrected; parser blocked on COM class)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-300…C-307
- **Supersedes:** the `0x6fafe4` comparator address from EXP-2026-11-05-16
- **Superseded by:** none

## Question

Can the `HDD_INFO` parser be located, and can the six-line ↔ field mapping be
settled?

## Hypothesis

The function at `0x6fafe4` is the comparator and its callers lead to the
parser.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Comparator module data delta | `0x02800000` |
| Tool | `tools/hddinfo_variants.py` |

## Observations

### Corrected comparator

`0x6fafe4` is only a 0x18-byte teardown stub. The real chain is:

| Address | Role |
| --- | --- |
| `0x6fab2c` | entry wrapper → calls `0x6faeb0` |
| `0x6faeb0` | mode/path selector: `r2 = *(obj+0x10)`; mode 0 or 10 → path A, other → path B; status selects object-relative pointers `+68/+76/+80` |
| `0x6fb05c` | field comparison: `manufacturer_id`, `userdata_type`, `destination_id`, `Sys[0x%x]` vs `SD[0x%x]` |

- **`userdata_type` is the range-checked field** (`0 < v < 6`, at
  `0x6fb122`–`0x6fb12a` on the `userdata_type` message path).
- The other two fields are arbitrary `u16`.
- The unit selects among multiple `HDD_INFO` locations by mode and status
  (`0x6faf02`–`0x6faf22`, `0x6faf3c`–`0x6faf76`): `\SystemSD\…` vs
  `\UserSD\…` plus three object-relative locations.

### Second module (SD format/validate)

- data delta **`0x1130000`**, code file **`0x30d000–0x315000`**;
- 10 clustered code references to `FormatVolume`, `Part00`, `SDC1:`, both
  `HDD_INFO` paths and `SD Import : finished not found.`;
- wrapper `0x30efcc` passes the path to a **COM property (id 17)**;
- **FATUTIL.dll is not the parser** (its 9 exports are Defrag/Format/Scan only).

### What is still unknown

The file parser is behind `obj->Set(17, path…)` inside an **unnamed COM class**.
The comparator module's **code delta is unrecoverable** (data delta
`0x02800000` proven; code and data differ; no anchor fixes the code side).
Static tracing stops there.

Six-line mapping is a ranked **HYPOTHESIS**:

1. line 4 `SDC08-EVEUR` → `manufacturer_id = "SDC08"` +
   `destination_id = "EVEUR"` (medium);
2. `QSD-302-100` / `QSD-309-101` → `userdata_type` family (weak);
3. line 6 `470323501005` → part number, not compared (medium);
4. lines 3/5 → version/date, likely not compared (weak).

The `Sys` side is a **parsed u16** (`*(r12+4)`), not a string; the built-in
`0x06000000` copy is the only system-side `HDD_INFO.TXT` in the image, so
**both are likely used**, with the built-in copy as the `Sys` source
(hypothesis, strong).

## Test package

`tools/hddinfo_variants.py` generates length-preserving variants:

```bash
python3 tools/hddinfo_variants.py VER_INFO/HDD_INFO.TXT /tmp/variants --sweep 0-5
# 73 variants + MANIFEST.txt, all exactly 72 bytes
```

Per line it emits: last-character change, a `0…5` sweep over each digit run,
and an `XXXX` replacement for each uppercase word (`EVEUR`→`XXXXX`). The
matrix isolates the range-checked `userdata_type` slot; a debug console prints
the exact field name and both values.

Safety: original card never written (`ddrescue` + SHA-256), work on a spare,
keep an untouched rollback card.

## Tile contract nuance

The `0..2047` bound is a **runtime/derived** constraint, not a storage rule.
Decoded `REFER001` bodies contain 4–7 % non-fill `u16` values in
`2048–4095` (and 23–26 % ≥ 4096), so coordinates are **bit-packed/bit-masked**,
not plain `u16`. Compliance cannot be claimed or refuted from raw bytes without
the tile record decoder.

`.ind` headers still confirm `chunk_size = 0x10000` and multi-chunk zlib
(`ADDRE008`: 3,093 chunks).

## Follow-ups

- [ ] Run the spare-card matrix (highest value, no RE needed).
- [ ] Identify the COM class behind property 17 via `.rgs`/CLSID registration
      data; decompile its `Set(17, path)` implementation.
- [ ] If a debug console is reachable, capture `SD Import: …` while running the
      matrix.
