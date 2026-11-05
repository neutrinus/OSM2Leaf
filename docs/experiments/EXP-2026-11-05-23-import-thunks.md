# EXP-2026-11-05-23: 0x2e0xxxx is an import-thunk area, not an export module

- **Status:** done (premise refuted; new anchors)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-370…C-378
- **Supersedes:** “0x2e0xxxx is an export module”
- **Superseded by:** none

## Question

Is the `0x2e0xxxx` module an export module, and can its export table name the
reader call targets?

## Hypothesis

`0x2e0xxxx` is a module with an export table covering `0x2e00f98–0x2e533e4`.

## Observations

- A corrected export scan (the ROM's export directory is **9 dwords**,
  timestamp first, not the usual 11) finds **135 export modules**, including
  OBJDLL (1294 exports) and STDDLL (310).
- **No module's RVA range covers `0x2e00f98–0x2e533e4`**: `match_callees.py`
  gets 1/9 (a WINSOCK coincidence); no `(module, VA base)` pair exceeds 4/9
  prologue hits.
- The band is the **import-thunk area** of the navi modules:
  - contiguous **86-entry table at `0x1724eb8–0x17252c0`**,
  - 12-byte thunks `mov.l @(disp,PC),r0; mov.l @r0,r0; jmp @r0; nop;
    .long iat_slot`, best-fit delta `0x16e248c`,
  - IAT slots are RAM addresses `0x01ab9000–0x01ab9440`; the loader writes the
    real pointers.
- The paired **import name table** is at `0x1708000–0x170a200`:
  `COREDLL.dll` (ordinal-only), `BT_DB`, `WS2`, `OBJDLL` (53 names),
  `STDDLL` (21), `ICLDLL` (12), `DCM_API`, `Cws_Apl`, `TelemaDLCCLib` (110).
- The underlying module is a **non-exporting shared library** at file
  ≈`0x171c000–0x1724eb8`, VA ≈`0x2e00000`. Its own name was not found;
  `HCXMemory`/`Errlogdll`/`AvCCWrapper` appear only in its import list.

## MAL volume chain

```
OBJ_DiscInfo_readDiscVol   file 0x7f65d8  VA 0x034993d8
  -> MAL_DataVol_getOffset  file 0x7f5f48  VA 0x03498d48
  -> MAL_DataVol_getSize    file 0x7f5f28  VA 0x03498d28
  -> read at base + offset*2, length size*2
```

OBJDLL VA base `0x03480000` is proven by three independent literal sites. Only
three sites in the whole payload call `MAL_DataVol_getOffset/getSize`, all in
OBJDLL (`0x7f6694`, `0x7f6aa4`, `0x7f6b84`); the map module uses a
higher-level wrapper that is still missing.

## fd/IOB layer confirmed

`NaviStateCC.DLL`, file base `0xc32200`:

- `0xc42520` — IOB dump, type tag `+0xC0`;
- `0xc426a4` — directory dump, tag `+0xB4`;
- `0xc438a4` — stats formatter.

It is table-dispatched; no `bsr` reaches it.

## Contract cross-check

- `.cmp` = chunked plain zlib — SILENT/consistent (six zlib copies).
- `.ind` 4-dword header + `0x10000` — SILENT in firmware; data side 194/194,
  max 3,093 chunks.
- `DRSTR` 40×40 + 324×32 — confirmed from the file; parser not found.
- Hardcoded filenames — **CONTRADICTED** (0 refs to `CMP.LST`,
  `DRSTR001.DAT`, `.ind`, `REFER001.DAT`, `MAPAL001`, `LEV3456R.DAT`).
- `0x2e0xxxx` is an export module — **CONTRADICTED**.

## `.ind` mutation matrix

`tools/ind_mutate.py` generates 8 variants from a real `.ind` without touching
vendor files:

```
size_20000, size_8000   chunk_size compare vs buffer sizing
count_p1, count_m1      count trust vs final size check
off_last_m1/p1          exact seek vs 78 9c scan
off0_1, off_last_0      index-0 special case / offset validation
```

Each variant is paired with the original `.cmp`; the manifest states the exact
byte edit and the accept/reject hypothesis.

## Follow-ups

- [ ] Find the 20-byte import descriptor with `FirstThunk = 0x1ab9000` and
      `Name = COREDLL.dll`; name the 86 thunks.
- [ ] Scan `NaviStateCC` (`0xc32200–0xc4c200`) for a function calling ≥3 fd
      thunks **and** a local zlib (`lbase`/`dbase`/`z_errmsg`).
- [ ] Run the `.ind` mutation matrix on a spare card.
