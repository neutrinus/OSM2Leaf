# EXP-2026-11-06-H4: Audit the delta-era firmware claims

- **Status:** done
- **Date:** 2026-11-06
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img` (build A firmware)
- **Image SHA-256:** `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-630–C-639 (audit), plus C-068, C-180, C-182, C-234, C-262, C-370, C-371, C-372, C-373, C-374, C-375, C-235, C-243, C-273, C-381, C-423
- **Supersedes:** none
- **Superseded by:** none

## Question

Is every firmware claim carried over from EXP-05…29 either re-verified through
`cerom.py` (CE ROM TOC) with a module/section/offset, or explicitly retracted
with a `Superseded by` pointer?

## Hypothesis

`none / exploratory` — an audit; no single expected outcome. Claims whose
addresses were derived under the retired delta model are expected to be
retracted, while claims independently confirmed by the CE ROM TOC (C-516…C-528)
are expected to survive re-verification.

## Inputs

| Item | Value |
| --- | --- |
| Image | `archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` |
| SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| Image start | `0x200200` (build A) |
| Tool | `tools/cerom.py` (ROMHDR, modules, sections, exports, thunks, file2va, va2file) |

## Method

Exact commands (build A, image start `0x200200`):

```bash
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img romhdr
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img modules
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img sections Navi.exe
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img sections OBJDLL.dll
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img sections NaviStateCC.dll
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img sections NaviSearchCC.dll
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img file2va 0xa438a4
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img file2va 0x7f5f48
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img va2file 0x8d73dd48
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img exports OBJDLL.dll
python3 tools/cerom.py --image-start 0x200200 archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img thunks NaviStateCC.dll
```

## Observations

Raw results (counts and resolved locations):

- `romhdr`: build A, `nummods=149`, `numfiles=1`, `usCPUType=0x01a6` (SH-4),
  physical range `0x8cae1000`–`0x8e233c88`, ROMHDR at file `0x01951b78`.
- `modules`: `OBJDLL.dll` is module 59, vbase `0x03480000`, load `0x8d725000`;
  `NaviStateCC.dll` is module 98, vbase `0x02df0000`, load `0x8dda9000`;
  `NaviSearchCC.dll` is module 95, vbase `0x02e80000`.
- `file2va 0xa438a4` → `0x8d3246a4`, which lies in inter-module padding
  between `ddddifull.dll` (ends `0x8d2d9c00`) and `Bolero.dll`
  (starts `0x8d36a000`); no stable module/section attribution.
- `file2va 0x7f5f48` → `0x8d0d6d48`; `va2file 0x8d73dd48` → `0x00e5cf48`
  (OBJDLL.dll `.text`, section rva `0x00001000`).
- `sections Navi.exe`: `.text` at rva `0x00001000` (psize `0x0054be00`,
  file `0x00c8f200`), RW data at rva `0x0054d000` (compressed).
- `sections OBJDLL.dll`: `.text` at rva `0x00001000` (psize `0x00055800`,
  file `0x007de200`), compressed RW data at `0x00057000`.
- `0x1952b00` resolves to `TOCentry[121]` (field `ulE32Offset` at phase
  `0x14`); field `+0x10` is `ftTime` (Unix timestamp), as established by
  EXP-2026-11-05-35.

## Interpretation

- **FACT:** C-374's MAL chain survives re-verification: `MAL_DataVol_getOffset`
  and `getSize` are in `OBJDLL.dll` `.text` (file `0x007de200`), reachable via
  `cerom.py file2va`/`sections`.
- **FACT:** C-370's export-directory observation and C-372's thunk-table
  observation are reproducible through `cerom.py exports`/`thunks`.
- **FACT:** C-273's `+0x10` Unix-timestamp observation is re-verified as the
  `TOCentry.ftTime` field.
- **OBSERVED:** C-634 — `NaviStateCC.dll` is confirmed by `cerom.py modules`,
  but its COM vtable is runtime-built, so the fd/IOB slot layout (C-375) is
  not statically recoverable.
- **RETRACTED:** C-068, C-180, C-182, C-234, C-262, C-371, C-373, C-375,
  C-235, C-243, C-381, C-423 — their addresses were derived under the retired
  delta model and are superseded by C-516…C-528 / C-630…C-639.

## Conclusion

All candidate rows named in TODO.md H4 now carry either a `VERIFIED` status with
a `cerom.py` module/section/offset (C-370, C-372, C-374, C-273) or a
`RETRACTED` status with `Superseded by` (C-068, C-180, C-182, C-234, C-262,
C-371, C-373, C-375, C-235, C-243, C-381, C-423). The audit claims
C-630–C-639 record the per-row outcome. `docs/research/claims.md` was updated
in the same commit.

## Follow-ups

- [ ] M2.1/M3.1 can now cite C-631 (OBJDLL MAL chain) as a verified anchor.
- [ ] M9.2 should load `OBJDLL.dll` `.text` at the `cerom.py`-resolved VA.
