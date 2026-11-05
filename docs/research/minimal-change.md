# Minimal-change experiment

Goal: prove that the unit accepts a modified map database, with the smallest
possible change and an unambiguous visible result.

## Recommended first experiment

**Rename one POI display name in a single-chunk `REFER001/POINT0xx.DAT.cmp`,
keeping the exact byte length, after a no-op recompression control.**

- Use a single-chunk file so the outer `.cmp` is one zlib stream.
- Keep the name length identical, so no pointer/length field changes.
- Keep the logical `.DAT` size identical, so `DRSTR001.DAT` needs no edit.
- Do a no-op recompression of the same file first: it separates “the unit
  rejects non-factory zlib” from “the unit rejects changed content”.

Why this is the best first test:

- only two files change (`.cmp` and `.ind`), no tile/`DRSTR`/`MMAIN`/version
  file;
- the name is visible in the POI list/detail;
- `CMP.LST` points the unit at `REFER001`, so the real read path is exercised;
- the no-op control makes the result interpretable;
- rollback is restoring two files or swapping the original card.

## Offline result (EU 2011 sample)

Target: `POINT032.DAT.cmp`, page `0x4200`,
`VATICAN MUSEUM@VIALE VATICANO` → `OSM2LEAF PROBE@VIALE VATICANO`
(same 14-byte length).

| Check | No-op control | Rename |
| --- | --- | --- |
| logical `.DAT` | 20,224 → 20,224 | 20,224 → 20,224 |
| `.cmp` | 5,143 → 5,110 | 5,143 → **5,119** |
| inner payload diff | 0 bytes | **14 bytes** |
| changes outside page `0x4200` | 0 | 0 |
| `DRSTR` entry | 20,224 | 20,224 unchanged |
| `cmpind.py verify` | 1/1 OK | **1/1 OK** |

The rename was produced and validated with the repo tools:

```bash
python3 tools/scan_refer_names.py REFER001/POINT032.DAT.cmp --min 8
python3 tools/mutate_refer_poi.py REFER001/POINT032.DAT.cmp \
    REFER001/POINT032.DAT.ind /tmp/mut \
    --page 0x4200 --old "VATICAN MUSEUM" --new "OSM2LEAF PROBE"
python3 tools/validate_mutation.py REFER001 /tmp/mut POINT032.DAT \
    --page 0x4200 --drstr DRSTR001.DAT --inner-page 0x4200
python3 tools/cmpind.py verify /tmp/mut
```

Expected: `PASS: same logical size, changes confined to one page, DRSTR untouched`
and `1/1 OK`.

## Hardware protocol (spare card, spare unit)

1. **Gating condition:** the EU 2011 sample is not the owner's US card. Run
   the hardware test on the US dump (or in an EU car); a market mismatch
   produces a failure that says nothing about the format.
2. Prepare a **whole-card image** (not a file copy) on a spare 16 GB SDHC.
3. Test 1: no-op recompression of the chosen `POINT` file. If the unit
   rejects it, the format requires factory-exact compressed bytes; stop and
   pivot to a byte-preserving edit in an uncompressed outer file.
4. Test 2: same-length rename. Expect the new name in the POI list/detail.
5. Record every screen/error. Stop at the first map-data dialog, `SECURE`,
   black map or reboot, and restore the original card.
6. Lock the card with the target unit's CMD42 PIN before insertion.

## Falsification criteria

| Observation | Meaning |
| --- | --- |
| Control clone boots, no-op recompression fails | Unit requires factory-exact compressed bytes or has an unknown container check. “Edit and recompress” is dead; pivot to `REFER002`/byte-preserving edits. |
| No-op succeeds, rename gives map-data error/black map/crash | Content checksum, signature or activation binding exists. This is the main scientific result. |
| Both boot, new text never appears | The string page is not the display source, or the wrong shard/language. Format edit is accepted; visibility hypothesis is false. |
| Every clone is refused, including control | Inconclusive. Fix cloning/locking first. |
| Unit accepts but corrupts state | Treat the card as disposable; never use the original. |

## Side findings / corrections

- `REFER001` names are **plain Latin-1 text inside small inner zlib pages**,
  not a custom codec or encryption.
- `REFER002` has **16 files**, not 194; it is a separate EV/charging layer.
- `DRSTR001.DAT` stores **on-disk size** for `MAPAL001` tiles and **logical
  uncompressed size** for `.cmp` files.
- No per-file checksum was found in the 512-byte header, `.ind`, `DRSTR` or
  `MMAIN`; this is a negative result, not proof that no activation check
  exists in NAND/firmware.

## Tools

| Tool | Purpose |
| --- | --- |
| `tools/scan_refer_names.py` | list Latin-1 strings inside inner zlib pages |
| `tools/mutate_refer_poi.py` | same-length POI name rename |
| `tools/mutate_refer_page.py` | same-length in-page byte patch (e.g. coordinate nudge) |
| `tools/validate_mutation.py` | offline acceptance: size, page confinement, DRSTR |
| `tools/drstr_ze0.py` | DRSTR reader/writer helper used by the validator |

## Safety

Original card read-only and hashed. Full-device image (all partitions plus
pre/post areas). Spare card ≥ 16 GB SDHC. Re-lock with LeafSDTools before
insertion. Stop at the first map-data/`SECURE`/black-map/reboot symptom.
