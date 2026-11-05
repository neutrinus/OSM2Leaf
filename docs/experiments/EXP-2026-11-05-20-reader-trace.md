# EXP-2026-11-05-20: Container reader trace — corrections and new anchors

- **Status:** done (readers not found; model corrected)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-330…C-340
- **Supersedes:** `0xc438a4` as CMP.LST opener, the `+0x02200000` code delta,
  the fd `+0xC4` tag and the `0x1ac` allocation claim
- **Superseded by:** none

## Question

Can the `.cmp`/`.ind`, zlib and `DRSTR` readers be located by tracing from the
known fd/directory functions?

## Hypothesis

`0xc438a4` opens `CMP.LST`; the map module code is at `file + 0x02200000`.

## Observations

### Retraction 1 — `0xc438a4` is not the CMP.LST opener

It is a **memory/fd statistics formatter**: its pool `0xc439d0 = 0x02df9450`
→ file `0xdf9450` = `"ize  :%d\r\n"`, with neighbours `"Max  :%d"` and
`"memSize  :%d"`. The real `"\CMP.LST"` is at **`0xdf945d`** and has **zero**
pointer references anywhere in the payload.

### Retraction 2 — map filenames have no literals

`DRSTR001.DAT`, `.ind`, `.IND`, `REFER001.DAT`, `MAPAL001` and
`LEV3456R.DAT` have **zero** literal references. `.cmp` has exactly one, in
the debug dumper. “Names are name-driven” survives, but `CMP.LST` is not the
visible entry point in build A.

### Retraction 3 — the `0x02200000` code delta is wrong

An embedded per-instruction `{VA, flag}` table at `0x12fa000–0x132d200`
contains all nine known function entries as VAs in the
**`0x02b0xxxx–0x02b5xxxx`** band. Best fit is `VA = file + 0x01f07d5c` (the
exact value has a small even alias because the table lists every instruction;
the band is certain). Reproduce with `find_module_delta.py`.

`0xc438a4`'s “call targets” are code VAs in another module. Under the data
delta they collide with the shared `.rdata` and look like string fragments
(`0x02e07344` → `"fer Allocation Error"`). **Never apply the data delta to a
`jsr` target.**

### FD layer corrections

- `0xc42520` IOB/fd dump: fields `+0xAC/+0xB0/+0xB4/+0xB8/+0xBC/+0xC0/+0xC4`;
  the type tag is **`+0xC0`** (7–15), not `+0xC4`.
- `0xc426a4` dir/disc dump: type tag **`+0xB4`** (2, 18/19), second field
  `+0xBC` (8/9).
- `0xc0e998` is the true entry of the function containing `0xc0ebf8`;
  `0x1ac` is an argument to `0x2e533e4`, which is also called with negative
  values. The “0x1ac allocation” claim is **unproven**.

### New anchors

- **`OBJDLL.dll`**: file base `0x7dd200`, export dir `0x82816c`, **1294 named
  exports**. Map Access Layer API: `MAL_DataVol_getSize` (`0x7f5f28`),
  `MAL_DataVol_getOffset` (`0x7f5f48`), `MAL_DataVol_getAreaRect`
  (`0x7f5f68`), `OBJ_DiscInfo_readDiscVol` (`0x7f65d8`),
  `writeDiscVol` (`0x7f710c`), `readPublicLv` (`0x7f66f8`).
- **`STDDLL.dll`**: file base `0x834200`, **310 exports**.
- **Six zlib copies** fully mapped (lbase/dbase, `z_errmsg`, versions
  1.1.3/1.1.4): `0x5e5f98`, `0x8b5f10`, `0xa34f48`, `0xe88f78`,
  `0x15c7e88`, `0x1619848`.

## Contract cross-check

| Claim | Status |
| --- | --- |
| `.cmp` = chunked plain zlib | SILENT/consistent (six zlib copies, no other codec) |
| `.ind` 4-dword header + `0x10000` | SILENT in firmware; data side 194/194, max 3,093 chunks |
| decompressed payload keeps the 512-byte header | SILENT |
| `DRSTR` 40×40 + 324×32 | CONFIRMED from the file; parser not found |
| hardcoded filenames | **CONTRADICTED** |
| `0xc438a4` opens `CMP.LST` | **CONTRADICTED** |
| `VA = file + 0x02200000` | **CONTRADICTED** |

## Remaining blocker

Readers are **table-dispatched**, and their `jsr @Rn` targets are absolute VAs
in a module that is neither `OBJDLL.dll` nor `STDDLL.dll` and whose
placement/export table is not recovered. No `bsr` reaches `0xc42520`,
`0xc426a4`, `0xc438a4`, `0xc0e998` anywhere in the payload. Static delta
voting over all call literals is flat (~5 %).

## Exact next trace

1. **Cheapest, no hardware:** mutate one `.ind` on a spare card — change
   `chunk_size` (4th dword) to `0x20000`/`0x8000`, change `chunk_count` by ±1,
   shift one `chunk_offset`. The accept/reject behaviour tests the `0x10000`
   compare, count trust and seek-vs-scan.
2. **SD bus capture:** logic analyzer on CLK/CMD/DAT0-3 during boot and map
   screen; decode CMD17/CMD18 and record the LBA order of `DRSTR001.DAT` vs a
   `.cmp`/`.ind`.
3. **Serial/JTAG:** capture `MAP_DATA READ START MESH_ID=... DIVID=...`.
4. **Ghidra P-code emulation** of the fd layer with mock read/seek, stubbing
   `jsr @Rn` by target VA.
5. **Find the `0x2e0xxxx` module's export table** with `exports.py`; its RVA
   range must cover `0x2e00f98`–`0x2e533e4`. Once it does, every `jsr` target
   becomes a named API.

## Follow-ups

- [ ] Find the `0x2e0xxxx` module export table.
- [ ] Run the `.ind` mutation matrix on a spare card.
- [ ] SD bus capture to settle read order and seek-vs-scan.
