# EXP-2026-11-05-13: Import anchor fails; the ROM module table is next

- **Status:** done (navi base still not recovered)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-260…C-266
- **Supersedes:** the round-6 hope that the import descriptor is the way into
  the navi modules
- **Superseded by:** none

## Question

Can a hardened import anchor recover the navi/map module bases?

## Hypothesis

Requiring an aligned base, a clean DLL name, ≥4 thunks and an IAT run into one
of the 26 mapped modules will reject the noise and leave the real modules.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Tool | `scripts/import_scan.py` |

## Method

Rules: R1 `Fb` 0x200-aligned; R2 clean DLL name at a string onset; R3
`OriginalFirstThunk` → ≥4 ordinal/VA entries + terminator; R4 IAT → ≥4
user-space VAs; R5 an IAT value inside one of the 26 mapped modules.

## Observations

```
R1–R5, >=2 votes               : 0 candidates
R5 relaxed to intra-DLL cluster: 3 candidates, all rejected
```

| `Fb` | Imports | Prologues/4 KiB | Verdict |
| --- | --- | --: | --- |
| `0x77c200` | `HCXMemory.dll`, `OSM_MSGDLL.dll` | 0.0 | not code |
| `0x1889200` | `OSMDLL.dll`, `OSM_MSGDLL.dll` | 0.0 | not code |
| `0x670600` | `COREDLL.dll` | 10.8 | 1 vote |

**Cause (proven):** this is a **pre-bound WinCE ROM** — `romimage` turns
imports into direct calls, so import directories are stripped. Only 1,222
descriptor-shaped records exist in the whole payload and almost none are
coherent; the 380 round-6 candidates were coincidental byte patterns. R5 also
cannot fire because navi modules import `COREDLL.dll`, which is not among the
26 mapped modules.

- **Export anchor still stands** (26 modules, `file = Fb + RVA`), but no
  navi/map module has an export directory in `0x44xxxx–0x1952c88`.
- **Section table:** 0 `o32_rom`-shaped records have `dataptr` equal to any
  known module file base (TFAT `0x28e200`, NDIS `0x373200`, OLEAUT32
  `0x40f200`, …).
- **Rosetta:** a 96-byte TFAT function appears at A `0x291d08`, B `0x3f7bd14`,
  C `0x537bd18`; B and C differ by exactly 4 bytes, A is different. But A's
  map code (`0xc42410`, `0xc438a4`) is **absent from B and C**, so B/C cannot
  pin A's map module. The `0xc438a4` body occurs **4×** in A — a repeated
  template, not a unique anchor.

### What is pinned down

- map module `.rdata` = file `0xdf6000` = VA `0x02df6000` (21 literals under
  delta `0x02000000`);
- map module `.text` = file `0xc00000–0xc4b000` (1757 prologues, 1627 `jsr`
  per 64 KiB at `0xc00000`);
- therefore its VA base `Vt < 0x02df6000`; the `jsr` targets at `0x02e0xxxx`
  lie **outside** it and belong to a different module at VA `0x02e00000`
  (file `0xc00000`, delta `0x02200000`);
- a 1-D prologue search for `Vt` over `0x01a00000–0x02400000` is flat
  (max 23/218).

The file layout interleaves sections from different modules; no single or
pairwise delta guess works.

## Interpretation

- **FACT:** the hardened import anchor returns zero.
- **FACT:** the ROM is pre-bound; import directories are stripped.
- **FACT:** navi modules have no export directory.
- **FACT:** the section table does not cover these modules.
- **UNKNOWN:** the navi/map VA base, and therefore all four readers.

## Conclusion

Retract the import anchor. The next target is the ROM module table at
`0x15271c8` (`NaviSearchCC.dll`, `NaviDrawCC.dll`, `NaviStateCC.dll`
back-to-back as 16-byte-stride names), plus a self-name anchor and the
shared-`.rdata` clusters. `docs/format/firmware.md` and claims C-260…C-266
were updated.

**Timebox:** if the next round does not recover a base, pivot to the
data-side + hardware feedback loop and treat the reader-code cross-check as a
parallel long-running task, not a gate.

## Follow-ups

- [ ] Decode the ROM module table at `0x15271c8`; success = `{name, VA, size}`
      with a 64 KiB-aligned VA matching a prologue-dense file range.
- [ ] Self-name anchor: the literal pointing at `0x15271c8` is
      `0x15271c8 − filebase + Vt`; score `Vt` against string-pointer clusters.
- [ ] Enumerate shared-`.rdata` clusters under the known deltas; `Vt` follows
      if `.text` is adjacent to `.rdata` in VA.
