# EXP-2026-11-06-H3: fold ce_rom_parse.py into cerom.py

## Summary

- **Task:** H3
- **Date:** 2026-11-06
- **Engineer:** agent
- **Sample:** `IMG256` = first 256 MiB of
  `LEAF_2011-2012_QSD-309-101_navi158_eu.img`,
  SHA-256 `92aa525d0db2c167cf4288b82f9cb951865a53c3a9ab4ead84d11a6f19a007f9`

## What was done

1. Added `cerom.py scan IMG` (whole-image `ECEC` segment discovery, copies
   included) with text and JSON output (`--out`, `--json`, `--offset`).
2. `tools/ce_rom_parse.py` is now a thin wrapper that forwards its arguments
   to `cerom.py scan` and prints a deprecation notice.
3. `tools/l3_harness/rommap.py` documentation names `cerom.py ... memmap`.
4. Claims C-620–C-629 added.

## Verification

```
python3 tools/cerom.py /tmp/opencode/IMG256 scan
# segments: 5
# A 149 modules, A copy 149, B 91, B copy 91, C 88
python3 tools/cerom.py --selftest          # 344 checks OK
python3 tools/l3_harness/rommap.py selftest # 19 checks, OK
python3 tools/selftest.py                  # pass
```

## Result

H3 complete. One CE ROM parser remains (`tools/cerom.py`); `ce_rom_parse.py`
is a deprecated wrapper.