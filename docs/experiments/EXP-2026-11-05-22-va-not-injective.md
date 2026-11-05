# EXP-2026-11-05-22: The VA map is not injective; XIP table is the key

- **Status:** done (negative; structural blocker identified)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-360…C-367
- **Supersedes:** the attempt to pin the `0x0367–0x0369` module by deltas
- **Superseded by:** none

## Question

Can the `0x0367–0x0369xxxx` library module be pinned and the `HDD_INFO` parser
reached?

## Hypothesis

A constant delta for the helper VAs followed by a self-printed string cluster
will identify the module.

## Observations

### The band is a library layer, not a pinnable module

- F2 (register used as `jsr`/`jmp` target within 8 bytes) yields **1,899
  distinct code-target VAs** in `0x0360–0x036a` (1,227 in `0x0366+`).
- There is **no** export directory, `MSFT` or `.rgs` in the band.
- Of the 13 helper VAs, the best delta achieves **7/13** SH-4 prologues
  (`D≈0x02236a34`); the mapped words are mid-function bytes (`d306`, `7fec`,
  `9024`, `5cd0`…). A true constant delta needs ≥11/13.

### The VA map is not injective

- `VA 0x0367b180` is simultaneously a `jsr` target in the builder (`0x6faf7e`)
  **and** the UTF-16 string `" Debug Common Version 0.1 …"` at file
  `0xe7b180` under data delta `0x02800000` (exactly one occurrence).
- `0x0369d400` and `0x036922cc` map onto `0x7c`-pipe **string data**.

Therefore cross-module calls **cannot** be resolved by literal arithmetic;
they need the ROM's `romimage` **XIP section table**.

### Intra-module results stand

- Builder `0x6faeb0`: `mode = *(obj+16)`, path fragments appended, status
  `2…6` → `obj+68/76/80`.
- Reporter `0x6fb05c`: format `0x6fb0ce`, `0 ≤ v < 6` at `0x6fb122`.

Both are in one file region and need no delta.

## Still unknown

- Parser location: behind the builder's first call, in the unmappable library.
- Card vs built-in `0x06000000`: no code link.
- Six-line mapping: only constraints (`Sys[0x%x] SD[0x%x]`, `0 ≤ v < 6`,
  field enum `0x00A2` at `*(r12+4)`).

## Spare-card matrix — final

**89 length-preserving variants, all exactly 72 bytes** (73 content edits + 15
pairwise swaps + 1 reverse). Six-step boot plan and message oracle in
`ROUND14.md` §5:

```
SD Import: manufacturer_id is different Sys[0x%x] SD[0x%x]   0xe535c0
SD Import: userdata_type is different  Sys[0x%x] SD[0x%x]    0xe53548
SD Import: destination_id is different Sys[0x%x] SD[0x%x]    0xe53638
SD Import : application type not correct.                     0xe534a8
SD Import : finished not found.                               0xe53500
```

Step 1 `swap_1_2`, step 2 one `lastchar` per line, step 3 the `0…5` sweep on
the reacting line, steps 4–5 `line4_letters` / `line4_digits` to split
`destination_id` from `manufacturer_id`.

## Next step

**Parse the `romimage` XIP section table**: file offset ↔ VA ↔ size per
section. Leads: `ECEC` at container `+0x240` and `NKOK` at `+0x1fc` (round 1).
That one artefact converts every VA into a file offset and unblocks all
cross-module calls, including the parser, and the `0x02b0`/`0x02df` discrepancy.

Run the spare-card matrix in parallel; it answers the six-line question with no
further RE.

## Follow-ups

- [ ] Parse the XIP section table and build the VA ↔ file map.
- [ ] Re-resolve the `0x0367–0x0369` helpers and the map-module delta.
- [ ] Run the 89-variant spare-card matrix.
