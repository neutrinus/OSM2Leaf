# EXP-2026-11-05-07: Dual-base Ghidra and reader search

- **Status:** done (readers still not located; strategy changed)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-200…C-208
- **Supersedes:** the assumption that filename literals or the 16-byte table
  at `0xdf8120` can anchor the readers
- **Superseded by:** none

## Question

Can a dual-base Ghidra import and string-xref search locate the `.cmp`/`.ind`,
`DRSTR` and tile readers, and what exactly does the map-code check compare?

## Hypothesis

With `.rdata` imported at `0x02000000` and code at `0x02200000`, filename
xrefs will lead to the readers.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Ghidra | code base `0x02200000`, `.rdata` base `0x02000000` |
| Script | `xref_index.py` |

## Method

- Scan all 12.5 M dword positions for low-24-bit matches against map filenames
  under every plausible `0x1000000`-multiple delta.
- Build a dual-base Ghidra project, export string xrefs, and test pointer
  arrays for multi-slot string resolution.
- Decompile the fd dump and field writers; inspect the `HDD_INFO` strings and
  the pointer table near `0xa9cf8c`.

## Observations

- **Zero literal references** to `REFER001.DAT`, `REFER002`, `MAPAL001`,
  `LEV3456R.DAT`, `DRSTR001.DAT` or `.ind` anywhere in the payload, for every
  tested delta. Filename-xref search cannot reach the readers.
- Names are supplied at runtime by the `DRSTR001.DAT` directory tree;
  `CMP.LST` supplies the root directory.
- The 16-byte table at `0xdf8120` is reporting/update-tool data, not the
  runtime selector.
- The two-delta model is **local to the module at `0xc00000–0xc4b000`**. Other
  modules map the same shared `.rdata` at other VAs. A 10-slot pointer array
  at `0xa9cf8c..0xa9cfb8`, minus `0x02200000`, resolves to real UTF-16 strings
  (`\UserSD\VER_INFO\HDD_INFO.TXT`, `SD Import: userdata_type is different
  Sys[0x%x] SD[0x%x]`, …).
- **Map-code check is textual/field-based, not crypto.** Strings:
  - `\SystemSD\VER_INFO\HDD_INFO.TXT`
  - `\UserSD\VER_INFO\HDD_INFO.TXT`
  - `SD Import: userdata_type / manufacturer_id / destination_id is different
    Sys[0x%x] SD[0x%x]`
  - `SD Import : application type not correct.`
- The literal `"DIFFERENT MAP CODE"` is **absent from build A**; nearest hits
  are unrelated (`STD_JUDGE_DIFFERENT`, `RPF_Mgr_restoreData -> DIFFERENT`).
- fd field `+0xC4` is a **type tag** (switch over 7…15), not `hcxcmp`.
- **No runtime map-content checksum** beyond zlib Adler-32. A generic ASN.1/
  crypto provider exists (`0x1668070`, `md5WithRSASignature`, `desDes`, …) but
  nothing links it to the map path.
- `DRSTR` layout is confirmed file-side (`40*40 + 324*32 = 11968`, node 0 `/`,
  Σentry_count = 324), but the parser code is silent (no 40-byte stride
  multiply in the map module).

## Interpretation

- **FACT:** map filenames are not literal-referenced; the reader is
  name-driven through `DRSTR`/`CMP.LST`.
- **FACT:** the two-delta model is local, not global.
- **FACT:** the map-code check compares `HDD_INFO` fields; the exact
  line↔field mapping is unknown.
- **HYPOTHESIS:** the `0x06000000` copy is the system-side reference.
- **UNKNOWN:** `.cmp`/`.ind` parser, tile reader, `DRSTR` parser code,
  `hcxcmp` setter.

## Conclusion

`docs/format/firmware.md` and claims C-200…C-208 were updated. The next
strategy is to anchor on the descriptor struct (`obj+0x78…+0x9c`) and the fd
field setters, not on filename strings.

## Follow-ups

- [ ] Find `jsr @rN` where `rN` is loaded from `obj+0x78…+0x9c`; walk to the
  `.ind` parse.
- [ ] Decompile setters `0xc412ca`, `0xc42a7a`, `0xc42ba6`, `0xc42e30`; locate
  the `.cmp` entry.
- [ ] Find the `shll2`-scaled index into the table at `0xa9cf8c` and its caller
  (the `HDD_INFO` comparison).
- [ ] Add a multi-slot validation rule to `xref_index.py` before accepting a
  new module delta.
