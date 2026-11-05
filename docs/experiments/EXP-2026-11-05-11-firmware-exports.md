# EXP-2026-11-05-11: Export anchors and the RAM copy list

- **Status:** done (26 modules mapped; navi modules still unmapped)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-240…C-246
- **Supersedes:** the hope that `0x1952b00` is a section map
- **Superseded by:** none

## Question

Can the section/copy descriptor list or PE export directories give a stable
module base, and can that locate the map readers?

## Hypothesis

The 32-byte list at `0x1952b00` is a section map; export tables can anchor
module bases.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Tool | `scripts/module_scan.py` |

## Observations

### Export-directory anchor works

- A PE export directory at `0x29f26c` solves to **`TFAT.dll`, file base
  `0x28e200`**:
  - 35/35 name-RVAs land on real strings (`FSD_CloseFile`,
    `FSD_CreateFileW`, …);
  - 34/35 exported entries are genuine SH-4 prologues.
- Therefore **`file = file_base + RVA`** holds throughout a module.
- `module_scan.py` maps **26 modules**: TFAT, DISKCACHE, FATUTIL, toolhelp,
  commctrl, mspart, WAVEAPI, AUDEVMAN, PPP, NWMINI, CXPORT, iphlpapi, WS2,
  WS2INSTL, WSPM, NSPM, afd, NDIS, TCPSTK, Unimodem, USBD, MMTimer, ole32,
  OLEAUT32, atlce400, REDLL.
- **VA base** is recovered by requiring `V − RVA` to be constant across
  exported functions. Verified on OLEAUT32 (`Vb = 0x03930000`): 282 literal
  sites equal `Vb + RVA`, 166 of them immediate `jsr` targets.

### `0x1952b00` is not a section map

32-byte records decode as
`{srcVA, srcVA+0x70, dstVA (page-aligned, increasing), flags 0x0007/0x1007,
value, timestamp 0x01cc500e–10 (≈2011), size, VA}`.

- **No field is a file offset**; sizes do not tile (`0x11000–0x12000` gaps,
  sizes `0xba–0x3100`).
- The “checksum” is not a CRC32 of file bytes (0 matches over every
  4-byte-aligned window for six records); the values are monotonic.
- **Retraction:** this is a RAM copy list, not a section map.

### Remaining blocker

The navi/map modules are EXEs or non-exporting DLLs; there is no export
directory in `0x44xxxx–0x1952c88`. The import-descriptor anchor is the way in,
but the first pass is noisy: 380 candidates, including `Navi.exe`≈`0x8581f4`,
`NaviMapScrollCC.dll`≈`0x175e92c`, `MapCC.DLL`≈`0xab79d4`,
`SearchCC.DLL`≈`0xba4854` — unverified, because bases are not `0x200`-aligned
and many names are truncated tails.

**Hardening rule:** require `OriginalFirstThunk` to point at ≥4 VA-like thunk
entries and the module's IAT to contain a run of VAs belonging to one of the
26 mapped modules. That cross-check is decisive.

## Interpretation

- **FACT:** export directories give a stable file base; `file = Fb + RVA`.
- **FACT:** 26 modules are mapped; OLEAUT32 VA base is verified.
- **FACT:** `0x1952b00` is a RAM copy list, not a section map.
- **UNKNOWN:** the navi/map module bases and therefore the readers.

## Conclusion

`docs/format/firmware.md` and claims C-240…C-246 were updated. The remaining
problem is now narrow: harden the import anchor for the navi modules.

## Follow-ups

- [ ] Harden the import anchor with the 4-thunk + IAT-run rule.
- [ ] Then re-run the reader search from the recovered map-module base.
- [ ] Use B/C builds as a Rosetta stone if the anchor still fails.
