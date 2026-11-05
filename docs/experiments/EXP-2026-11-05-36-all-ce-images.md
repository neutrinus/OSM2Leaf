# EXP-2026-11-05-36: The five payloads are three CE images; B and C are the kernel regions

- **Status:** done (positive)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image, full file (8,057,257,984 B), SHA-256
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
  (matches the reference sample)
- **Claims:** C-524…C-529
- **Supersedes:** none (extends EXP-2026-11-05-35)
- **Superseded by:** none

## Question

Do the other payloads (A copy, B, C) have CE ROM headers, which modules do
they contain, and does the kernel region explain the missing `nk.exe` /
`coredll.dll` and the COREDLL ordinals?

## Method

```bash
head -c 110000000 IMAGE > pre.bin          # pre-partition area
python3 tools/cerom.py pre.bin --image-start 0x3e00200 romhdr   # also 0x2000200, 0x4800200, 0x5200200
python3 tools/cerom.py pre.bin --image-start 0x3e00200 modules
python3 tools/cerom.py pre.bin --image-start 0x3e00200 exports coredll.dll
```

## Observations

`ECEC` + plausible `pTOC` exists at `0x200240`, `0x2000240`, `0x3e00240`,
`0x4800240`, `0x5200240` (other `ECEC` hits are noise).

| Image start | VA base | pTOC | nummods | numfiles | Notes |
| --- | --- | --- | --- | --- | --- |
| `0x200200`, `0x2000200` | `0x8cae1000` | `0x8e232978` | 149 | 1 | build A, byte-identical copies (24,456,328 B compared) |
| `0x3e00200`, `0x4800200` | `0x88000000` | `0x884e22f0` | 91 | 11 | build B, `physlast 0x886e18a4`, `ulCopyEntries 2` |
| `0x5200200` | `0x88000000` | `0x881f636c` | 88 | 10 | build C, `physlast 0x886683d8`, `ulCopyEntries 2` |

All three: `usCPUType 0x01a6`, `ulRAMStart 0x89e40000`, `pExtensions
0x880030a4`. B and C start at VA `0x88000000` (kernel region); A starts where
RAM ends (`ulRAMEnd 0x8cae1000`).

- **B (91 modules):** `nk.exe`, `coredll.dll`, `filesys.exe`, `gwes.exe`,
  `device.exe`, `fatfsd.dll`, drivers (`CAN`, `GPIO`, `I2C`, `SDHC`, `flash`,
  `lcddrv`, `navdrv`, …), and the updater set: `UpdateMng.exe`,
  `PRGUpdate.exe`, `MapUpdate.exe`, `AudioMiconUpdate.exe`, `BtUpdate.exe`,
  `DisplayUpdate.exe`, `VCANSubMiconUpdate.exe`, `OneSegUpdate.exe`,
  `FullSegUpdate.exe`, `*UpdateCC.dll`. Files include `UpdateNK.skn`
  (1,966,080 B), `default.hv`, `boot.hv`, `user.hv`, `wince.nls`,
  `DFHei-Nissan-P.ttf`.
- **C (88 modules):** kernel + drivers + USB (`usbd`, `usbhid`, `UsbOhci`),
  `SdCardLch.exe`, `TestMode.exe`, `BT_MGR/BT_ENG/BT_DB`, `FOMAB`, `COMD/COMH`.
- **A (149 modules):** application layer only (no `nk.exe`/`coredll.dll`); it
  imports `COREDLL`, `Errlogdll`, `SYS_INF`, `commondll`, which are in B/C.
- `coredll.dll` (B): `vbase 0x03fa0000`, 1651 named exports, ordinal base 2.
  Ordinal **719 = `sprintf`**, 1071 = `strncpy`, 35 = `LocalSize`.
  `OBJDLL` (A) export `MAL_DataVol_getOffset` has ordinal 3, RVA `0x18d48`
  (= VA `0x03498d48`, as in EXP-35).

## Interpretation

- **FACT:** the pre-partition area holds three CE images: A (application ROM,
  VA `0x8cae1000`), B (kernel + updater, VA `0x88000000`) and C (kernel +
  test/BT/USB drivers, VA `0x88000000`). A and B are stored twice, C once.
- **FACT:** `0x0369d400`, the "cross-module call" that blocked the HDD_INFO
  work since EXP-21, is the `BT_MGR.dll` thunk for `COREDLL!sprintf`
  (consistent with the `sprintf` at `0x6fb0d8`). The `0x6faeb0` path-builder
  is therefore ordinary `BT_MGR` code, unrelated to the map-code check.
- **OBSERVED:** the A image runs on top of a B- or C-like kernel; which one is
  active at boot is **UNKNOWN**. The B image contains `MapUpdate.exe`, so the
  map update flow is a likely second source of map-format knowledge.
- **UNKNOWN:** the compression of `IMAGE_SCN_COMPRESSED` sections and of
  `FILESentry` payloads (`comp != real`, e.g. `UpdateNK.skn`, `default.hv`).

## Conclusion

`tools/cerom.py` gained `exports`. C-524…C-529 added. The `nk.exe`/`coredll`
gap is closed.

## Follow-ups

- [ ] Disassemble `MapUpdate.exe` (B, file `0x04344200`): it knows how the
  unit validates and installs map data.
- [ ] Decide which kernel image the unit boots with A.
- [ ] Decompression (TODO Step 1b item 3); `FILESentry` payloads too.
