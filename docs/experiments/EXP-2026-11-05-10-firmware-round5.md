# EXP-2026-11-05-10: Firmware round 5 — section placement is the blocker

- **Status:** done (readers still not located; root cause identified)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-230…C-235
- **Supersedes:** the expectation that `Lib.out32`, allocation shape or
  `0x132e06c` would locate the readers
- **Superseded by:** none

## Question

Can the `Lib.out32` code delta, the `.ind` allocation shape or the
`HDD_INFO` caller at `0x132e06c` locate the readers?

## Hypothesis

One of the three anchors would give a stable per-module delta and expose the
`.cmp`/`.ind` code.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Scripts | `xref_index.py`, `vtable_scan.py`, `solve_delta.py`, `func.py` |

## Observations

### `Lib.out32` code delta

- With the fixed data delta `0x01e00000`, literals into the `0x1619xxx` pool
  hit only two data blocks (`0x870000` 37 refs, `0x880000` 7 refs), never code.
- Prologue scoring over `0x870000–0x890000` (473 targets, K ∈
  `0x2b00000–0x2c00000`) is flat: max 31/473 coarse, 34/473 refined — no peak.
  A Lib module imports from many modules, so most `jsr` targets are external.
- The round-4 hypothesis that this module holds `.cmp` is **weakened, not
  refuted**.

### `.ind` parser

Whole-payload search (`0x200000–0x1952c88`):

- `mov #1,rN; shll16` (builds `0x10000`): **0 sites**
- code-context literal load of `0x00010000`: **0 sites**
- ≥4 consecutive `mov.l @Rm+,Rn`: **0 runs**

So the parser compares against a value read from the structure and reads the
header without consecutive post-increment loads. **Not found, not refuted.**

### `HDD_INFO` caller

- `0x132e06c` (value `0x02c1cf8c`, delta `0x2180000`) is **data**, not code;
  the neighbourhood decodes as garbage.
- The table base `0x02c9cf8c` occurs **0 times** in the payload; `0xa9cf8c` as
  a raw file offset also 0.
- The comparison function remains **UNKNOWN**. The text/field mechanism is
  unchanged.

### Root cause (proven)

The ROM places **sections at independent `(file offset, VA)` pairs**, and the
shared `.rdata` is mapped under **at least three deltas** (`0x01e00000`,
`0x02000000`, `0x02200000`). Therefore:

- isolated literal→string hits are meaningless (≈10⁵ deltas vs ≈10⁵ strings);
  only ≥4-slot clusters are trustworthy, and they land in data tables, not
  code;
- heavily-importing modules make call-target statistics useless for delta
  recovery.

One `o32_rom` record (`0x3221b0`) decodes perfectly **only if `dataptr` is
payload-relative** (`0x11000 → file 0x211000`, a dense code area;
`psize = round_up(vsize,0x200)`), implying delta `0x8c97b000`. But 0/21
literals in that VA window land on prologues — an **open lead**, not a result.

## Interpretation

- **FACT:** all three round-5 anchors are clean negatives.
- **FACT:** section placement is the root blocker.
- **FACT:** shared `.rdata` has ≥3 deltas; single literal hits are unreliable.
- **UNKNOWN:** the `.cmp` entry, `.ind` parser, tile reader, DRSTR parser and
  `HDD_INFO` comparator.

## Conclusion

Stop hunting readers by symbol shape. Decode the section/copy descriptor list
and the export tables first. `docs/format/firmware.md` and claims C-230…C-235
were updated.

## Follow-ups

- [ ] Decode the copy/section descriptor list at `0x1952b00` (32-byte records:
      two VAs ~0x70 apart, page-aligned value, size `0xc4`, flags
      `0x00001007`/`...1006`). Success = `(VA,size)` pairs that tile a VA range.
- [ ] Anchor on export tables: `TFAT.dll`/`FSDMGR` names at
      `0x29eec0–0x29f700` map name → RVA; file offset + RVA ⇒ module base.
- [ ] Use builds B/C as a Rosetta stone: identical functions at different file
      offsets pin relative placement.
- [ ] Re-run the existing scripts once a module base is known.
