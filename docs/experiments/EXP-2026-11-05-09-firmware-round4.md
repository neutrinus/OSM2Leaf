# EXP-2026-11-05-09: Firmware round 4 — retractions and new anchors

- **Status:** done (readers still not located)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-220…C-225
- **Supersedes:** the `+0x78…+0x9c` vtable and fd-setter claims from
  EXP-2026-11-05-07
- **Superseded by:** none

## Question

Can the descriptor vtable and fd setters anchor the `.cmp`/`.ind` reader?

## Hypothesis

`obj+0x78…+0x9c` is a vtable; the four functions at `0xc412ca`/`0xc42a7a`/
`0xc42ba6`/`0xc42e30` write fd fields, one of which is the `.cmp` entry.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Script | `scripts/vtable_scan.py` (fixed) |

## Observations

- **Retraction 1:** every value `0xc48380` stores into `+0x78…+0x9c` is a
  **string pointer** (`"DBgetLnk no data(mesh=%08x x:y=%d:%d)"`,
  `"DBgetRoad no data…"`, `"MAP_DATA READ START…"`). The object is a **message
  catalogue**, not a vtable. Image-wide, 28 dispatches through `+0x78…+0x9c`
  exist, but **zero** in `0xc00000–0xc4b000`; the map module dispatches
  through `+0x04/+0x08/+0x18` (1146 sites, ~0x114-byte period, generated
  handler code).
- **Retraction 2:** the four functions are **read-only classifiers**. They read
  `obj+0xAC/0xB0/0xB4/0xB8`, compare against small ints, and return an enum
  through the caller's out-pointer (one uses a 20-case `braf` jump table). The
  struct is a **state descriptor keyed by `(0xAC,0xB4,0xB8)`**; `+0xC4` is a
  separate type tag.
- The earlier scanner had two encoding bugs (`mov.l @(R0,Rm),Rn` nibbles
  swapped; `mov rBase,r0` before `extu.b`); fixed in `vtable_scan.py`.

### New anchor: `Lib.out32.dll`

- File `0x877740` holds UTF-16 `"Lib.out32.dll"` followed by a string-pointer
  table (`0x877764…`) whose values are all `0x0341xxxx` → **data delta
  `0x01e00000`**.
- Four entries land on a zlib copy's `z_errmsg` strings:
  `0x034196fc "need dictionary"`, `0x034196e0 "file error"`,
  `0x034196d0 "stream error"`, `0x034196a0 "buffer error"`.
- The **code delta of this module is unknown**, which is why the decompressor
  itself was not reached. Five of the six zlib copies inline their error
  strings, so only this one is anchorable this way.

### Map code

- Mechanism is proven at string/table level: wide paths
  `\SystemSD\VER_INFO\HDD_INFO.TXT` and `\UserSD\VER_INFO\HDD_INFO.TXT`, plus
  the verified 10-slot table at `0xa9cf8c` with `Sys[...] SD[...]` messages.
- The comparison function is **not located**. The `shll2`-scaled index into
  `0xa9cf8c` was not found; best candidate caller is `0x132e06c`
  (delta `0x2180000`), unproven.
- Six-line ↔ field mapping: **UNKNOWN**. `SDC08-EVEUR` looks like a
  destination code and `QSD-30x-100` like application/card codes, but that is
  resemblance only.

### DRSTR / tile readers

- No 40-byte stride or `mov #5`+`shll3` (×40) exists in the payload; the DRSTR
  parser is **not located**. The file layout remains confirmed from the file
  itself.
- The tile reader depended on the non-existent vtable; it is **not located**.
  Only the `MAP_DATA`/`RGD_DATA` + `MESH_ID`/`DIVID` strings and the `0x1ac`
  allocation at `0xc0ebf8` remain.

## Interpretation

- **FACT:** the `+0x78…+0x9c` object is a message catalogue, not a vtable.
- **FACT:** the four fd functions are classifiers, not writers.
- **FACT:** `Lib.out32.dll` has data delta `0x01e00000` and contains a zlib
  copy; its code delta is unknown.
- **HYPOTHESIS:** card `HDD_INFO` is compared against the built-in copy.
- **UNKNOWN:** `.cmp`/`.ind` chain, DRSTR parser, tile reader, HDD_INFO
  comparison function.

## Conclusion

`docs/format/firmware.md` and claims C-220…C-225 were updated. The next
experiments are: pin the `Lib.out32` code delta, find `.ind` by allocation
shape, and resolve the `HDD_INFO` caller around `0x132e06c`.

## Follow-ups

- [ ] Pin the `Lib.out32` code delta and hunt `uncompress(dst,&len,src,srclen)`.
- [ ] Find `.ind` by allocation shape: `mov #1,rN; shll16` + `shll2` + call,
  across the whole payload (not just the map module).
- [ ] Resolve the `HDD_INFO` caller via `shll2` + table base around `0x132e06c`.
