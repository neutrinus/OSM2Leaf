# EXP-2026-11-05-05: Firmware reader cross-check

- **Status:** done (partial: readers not yet located)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-180…C-183
- **Supersedes:** the assumption that the ROM section table is the next step
- **Superseded by:** none

## Question

Can the firmware reader code confirm the data-format hypotheses, and can the
ROM section table give a stable `VA − rva` map?

## Hypothesis

The section table at `0x374000`/`0x3e0060` is a normal WinCE `o32_rom` array
and will resolve literals for the map reader.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Ghidra project | `/tmp/opencode/research-firmware/ghidra-project` (base `0x02200000`) |
| Scripts | `solve_delta.py`, `ListFuncs.java`, `Decompile.java` |

## Method

- Decode the 24-byte records at `0x374000`/`0x3e0060` as `o32_rom`.
- Check `dataptr` against the file; check `psize == round_up(vsize, 0x200)`.
- Run Ghidra function recovery at candidate bases; measure code density per
  64 KiB; resolve known string literals.

## Observations

- A clean record at `0x3221b0` decodes as
  `{vsize=0xed26, rva=0x1000, psize=0xee00, realaddr=0x8cb8c000,
  dataptr=0x11000, flags=0x60000020}`, with
  `psize == round_up(vsize, 0x200)`.
- **The table is not usable as a file map:** every `dataptr` sampled
  (`0x039c1000`, `0x03bd1000`, `0x01f5d000`) points into pure `0xff` fill
  (entropy 0.00), and consecutive records do not share `realaddr − rva`.
  These are stale build-time offsets/mixed sections.
- **Two deltas suffice for the map module:**
  - code: file `0xc00000–0xc4b000` ↔ VA `0x02e00000–0x02e4b000`,
    i.e. `VA = file + 0x02200000`;
  - `.rdata`: file `0xdf6000–0xe10000`, `VA = file + 0x02000000`.
  - Ghidra recovered 136 functions in `0x02e00000` and 84 in `0x02e10000`;
    code density drops to 1/0 at `0xc4b000`.
- **Functions found:**
  - `0xc438a4` — opens `\CMP.LST` (only such site in the image), returns the
    handle.
  - `0xc42520` — file-descriptor dump; prints `.cmp` and eight dwords at
    struct `+0xAC…+0xC8`, including the `hcxcmp` field.
  - `0xc426a4` — directory-info dump (`dir cnt`, `file cnt`).
  - `0xc48380` — installs `MAP_DATA READ START/END` and
    `RGD_DATA READ START/END` into the DB-access descriptor.
  - `0xc0ebf8` — only place `0x1ac` is built (`alloc(…, 0x1ac)`).
- **Not found:** `.ind`/`.cmp` reader, `DRSTR001.DAT` parser, tile reader and
  zlib call sites. Filenames have no direct pointer (only a fixed 16-byte
  table at `0xdf8120`), and constants like `0x10000`/`40`/`0x1ac` are built
  from immediates+shifts, so literal-pool search is blind to them.
- `0x06000000` contains a byte-identical copy of `VER_INFO/HDD_INFO.TXT`
  (72/72 B) in a 4 KiB zero-padded slot.

## Cross-check summary

| Claim | Firmware status |
| --- | --- |
| `.cmp` chunked zlib + `.ind` | SILENT (six static zlib 1.1.4 copies; no other codec) |
| `DRSTR` 40/324 layout | SILENT (name present; no 40-byte stride multiply found) |
| Tile grid/stream keys | SILENT (only weak hint: `0x1ac` allocation) |
| `COORD001` path + bbox maths | PARTIAL (path confirmed; maths silent) |
| `HDD_INFO` line 1 / `0x06000000` copy | CONFIRMED (copy), comparison code not located |
| `MESH_ID`/`DIVID` tile addressing | CONFIRMED |
| Non-PE/uncompressed firmware | CONFIRMED |
| SD lock CMD42 | SILENT |
| No per-file checksum | PARTIAL/SILENT |

Nothing was **contradicted**.

## Interpretation

- **FACT:** the section table cannot resolve file offsets; do not build on it.
- **FACT:** two deltas are enough for the map module's code and `.rdata`.
- **FACT:** `CMP.LST` is opened by `0xc438a4`.
- **OBSERVED:** the reader functions are reached through indirect tables and
  immediate-built constants, not string references.
- **UNKNOWN:** the exact `.cmp`/`DRSTR`/tile reader functions.

## Conclusion

`docs/format/firmware.md` and claims C-180…C-183 were updated. The next step is
not another section-table pass; it is a dual-base Ghidra run plus indirect-table
analysis.

## Follow-ups

- [ ] Dual-base Ghidra: re-import at `0x02000000` for `.rdata`, keep
  `0x02200000` for code, export string xrefs.
- [ ] Walk the file-descriptor API from `0xc42520`; find the setter of
  `hcxcmp` (the `.cmp` decompression entry).
- [ ] Find the user of the 16-byte filename table at `0xdf8120` (scaled by 16)
  to locate the `MAPAL001`/`LEV3456R` selector.
