# EXP-2026-11-05-33: CE ROM segment recovery with `tools/ce_rom_parse.py`

- **Status:** done
- **Date:** 2026-11-05
- **Sample:** `LEAF_2011-2012_QSD-309-101_navi158_eu.img`
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-088, C-089
- **Supersedes:** the planned CE ROM segment lead in `docs/format/firmware.md`
- **Superseded by:** none

## Question

Can the Clarion wrapper's embedded Windows CE ROM segment be parsed as a
standard XIP TOC, giving module/file bases and names for the map readers?

## Hypothesis

The `ECEC` block at image offset `0x00200240` is a CE memory-segment header:
`ECEC`, `pTOC`, size. A parser can recover the TOC and module names without
global VA-delta guessing.

## Inputs

| Item | Value |
| --- | --- |
| Image | `archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img` |
| SHA-256 | `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307` |
| Segment base | `0x00200200` |
| `ECEC` | `0x00200240` |
| `pTOC` | `0x8e232978` |
| size | `0x01751978` |
| Tool | `tools/ce_rom_parse.py` |

## Method

```bash
python3 tools/ce_rom_parse.py \
  --image archive/images/LEAF_2011-2012_QSD-309-101_navi158_eu.img \
  --out /tmp/opencode/ce-rom-report.json
```

## Observations

The parser found five valid CE ROM segments:

| Segment base | Modules | Files | CPU | Physical range |
| --- | ---: | ---: | --- | --- |
| `0x00200200` (build A) | 149 | 1 | `0x01a6` (SH-4) | `0x8cae1000`–`0x8e233c88` |
| `0x02000200` (build A duplicate) | 149 | 1 | `0x01a6` (SH-4) | `0x8cae1000`–`0x8e233c88` |
| `0x03e00200` (build B) | 91 | 11 | `0x01a6` (SH-4) | `0x88000000`–`0x886e18a4` |
| `0x04800200` (build B duplicate) | 91 | 11 | `0x01a6` (SH-4) | `0x88000000`–`0x886e18a4` |
| `0x05200200` (build C) | 88 | 10 | `0x01a6` (SH-4) | `0x88000000`–`0x886683d8` |

Build A's ROMHDR is at file offset `0x01951b78`. Its TOC resolves module names
including `gwes.exe`, `fatfsd.dll`, `diskcache.dll`, `fatutil.dll`,
`shell.exe`, `toolhelp.dll`, `commctrl.dll`, `OBJDLL.dll`, `STDDLL.dll`,
`Navi.exe` and `NaviStateCC.dll`.

The parser is standard-library Python, reads the image read-only, and writes a
JSON report. It does not modify the image.

## Interpretation

- **FACT:** build A's CE ROM segment parses as a standard XIP TOC with 149
  modules, 1 file, CPU `0x01a6` (SH-4), and physical range
  `0x8cae1000`–`0x8e233c88`.
- **FACT:** the TOC resolves module names, including `Navi.exe`,
  `NaviStateCC.dll`, `OBJDLL.dll` and `STDDLL.dll`.
- **FACT:** builds A, B and C each have a duplicate copy in the image.
- **OBSERVED:** the physical-to-file mapping is recovered by requiring
  `physfirst` to equal the candidate physical base; this is validated by the
  SH-4 CPU type and coherent module names.
- **UNKNOWN:** reader functions, module bases as link-time VAs, and the
  `HDD_INFO` parser are still not located.

## Conclusion

`tools/ce_rom_parse.py` replaces global VA-delta guessing for the first
firmware step: the CE ROM TOC and module names are now recoverable directly
from the image. The next step is to use those module bases/names in Ghidra and
locate the `.cmp`/`.ind`, `DRSTR001.DAT` and tile readers.

## Follow-ups

- [ ] Use the extracted module bases to locate `Navi.exe`/`Navi*CC.dll`
  reader functions in Ghidra.
- [ ] Add an L3 corpus for at least one located reader.
- [ ] Keep `SUM4`/container parsing separate from ROM TOC parsing.
