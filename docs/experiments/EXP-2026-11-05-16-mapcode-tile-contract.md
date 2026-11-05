# EXP-2026-11-05-16: Map-code comparator and tile contract

- **Status:** done (comparator located; HDD_INFO parser still missing)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-290…C-297
- **Supersedes:** the `0x1ac` level-table assumption
- **Superseded by:** none

## Question

Can the map-code comparator and the tile data contract be recovered without a
module VA base?

## Hypothesis

Working in pure file offsets and using the diagnostic strings will expose both
the validation semantics and the tile constraints.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Comparator | file `0x6fafe4`–`0x6fb194` |
| Tools | Ghidra, capstone, ROUND9 scripts |

## Observations

### Map-code comparator

The comparator is located and readable at file `0x6fafe4`–`0x6fb194`
(prologue `e62f 224f`, ends `rts`). Its data delta is **`0x02800000`** (pool
`0x6fb200`–`0x6fb248` resolves exactly).

```
6fb0d8  call format(obj+32, 0, "SD Import: manufacturer_id i…")
6fb0dc  call parse_value(r11)            ; SD value
6fb0e6  mov.w @(4,r12),r0                ; Sys value (u16)
6fb0ea  cmp/eq r10,r2 ; bt 0x6fb10e      ; equal -> next field
6fb0ee  "…ifferent Sys[0x%x] SD[0x%x]"   ; mismatch report
6fb10e  "…port: userdata_type is dif…"
6fb122  cmp/pz r11 ; cmp/ge #6,r11       ; reject unless 0 <= v < 6
6fb12c  "…not found."
6fb13c  virtual call obj[3]->vtable+20   ; "finished" flag
6fb15a  "type not correct."              ; if non-zero
```

**Proven:** the check is a **numeric `Sys[0x%x]` vs `SD[0x%x]` comparison per
field** for `manufacturer_id`, `userdata_type` and `destination_id`; one field
is range-checked `0 ≤ v < 6`; failures report “finished not found” / “type not
correct”.

A second module is involved: pool code pointers `0x0369xxxx` land in file
`0x1683xxx` with code delta **`0x0200e438`** (4 of 7 land exactly on function
starts; density 37.5 prologues/4 KiB).

**Not proven:** the six `HDD_INFO.TXT` lines ↔ the three fields. The parser
(open/split/parse) was not reached. Shape-based guess only: `SDC08-EVEUR`
decomposes into `SDC08` (manufacturer) + `EVEUR` (destination).

**Hypothesis (strong):** the card file is compared against the built-in
`0x06000000` copy (`Sys[…]` vs `SD[…]`).

### Tile contract from diagnostics

All `FACT`, from the map layer's own strings:

- per-mesh structures `area_link`, `cvdata`, `rgd_t`, `RGD_commem`
  (`0xe58268`…`0xe5900c`), with alloc/free failure paths;
- **intra-mesh coordinates are `0..2047` (11-bit)**:
  `RGD_JLocGet : t_start_x = 0,2047`, `t_end_x = 0,2047`,
  `RGD_JNextSrch : start_x/end_x = 0,2047`;
- `MESHMAX_LEV1` exists and mesh numbers are validated
  (`RGD_JGetCrs : meshno >= MESHMAX_LEV1`);
- link layout: `subl->lseg.sttpos/.endpos`, `links_p->linkp`, node-buffer
  overflow check;
- complete ordered enums `RGD_DIRTYPE_*` (9), `RGD_CRSTYPE_*` (14),
  `RGD_DIRSUBTYPE_*`, `RGD_TMTYPE_*` at `0xcc90c4`+;
- dump headers: `VTb Tp;Lv;St;F#|L1;L2;L3;L4;L5;L6|Sz;Adr` (`0xdf65a1`) — a
  six-level table with size/address; `HFile;FileID;Tp;Lv;V#;la Lo`
  (`0xdf6621`) — the file descriptor.

### Retraction

The `0x1ac` allocation is **not** the tile level table. It sits in the OSM
allocator at `0xc0eba0`, which allocates a 428-byte per-object buffer for
`obj+0x40` and frees `obj+0x48` (offsets `0x04/0x2C/0x40/0x44/0x48`) — a
working buffer.

## Remaining blocker

Only the module containing the `HDD_INFO.TXT` parser lacks a recoverable code
delta (no exports, no usable imports, no module table, no literal anchor; the
`bsr` graph fragments into 191 components / 194 edges). Everything downstream
of the parse is located.

## Closure experiment (spare card, no JTAG)

1. `ddrescue` the card, verify SHA-256, keep the original read-only.
2. Edit **one** `VER_INFO/HDD_INFO.TXT` line per card, preserving length/CRLF.
3. Boot and record the reaction:
   - unchanged → line not checked;
   - map-code refusal → line carries a checked field;
   - numeric-looking lines: sweep values 0…5 (matching the proven range check).
4. If a debug console is reachable (`OSM_Printf`, `OSM_LogMsg`,
   `StatusData(): ERROR-HEADER`), the exact `SD Import: <field> is different`
   message names the field.

JTAG is secondary and more work.

## Follow-ups

- [ ] Find callers of `0x6fafe4` and the `HDD_INFO` open/split/parse path.
- [ ] Map the six lines to `manufacturer_id` / `userdata_type` /
      `destination_id`.
- [ ] Run the spare-card line sweep.
- [ ] Use the `0..2047` bound and `MESHMAX_LEV1` as hard constraints for the
      tile writer.
