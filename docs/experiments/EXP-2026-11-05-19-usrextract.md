# EXP-2026-11-05-19: The 0x30f008 trail is false; follow USR_Convert_*

- **Status:** done (false trail closed; new direction)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-320…C-327
- **Supersedes:** the round-10 SD-module/property-17 link and the round-11
  property-17 discussion
- **Superseded by:** none

## Question

Which class is behind the SD module's `0x30f008` call, and is it the
`HDD_INFO` parser?

## Hypothesis

The object passed to `0x30f008` opens and parses `HDD_INFO.TXT`.

## Inputs

| Item | Value |
| --- | --- |
| Image | `leaf2011.img` |
| SHA-256 | `105e2032…76307` |
| Tools | `solve_data_delta.py`, `hddinfo_variants.py` |

## Observations

### The premise was wrong

- `0x30efcc` is a **free function** `f(obj, mode, flag)`: masks arg2 with
  `2`, requires arg3 == 1, then calls `obj->vtable[0](3,&out)` and
  `obj->vtable[1](17, 0, *global)`. The object comes from the caller; there is
  **no `bsr` to it anywhere** and no absolute literal under any tried base.
- **`0x01f83368` is a writable global, not the `HDD_INFO` path.** Three
  instructions after loading `0x01f83314`, the code does `mov.l r2,@r3` — a
  **store**, not a string argument (`0x31098c`–`0x310996`; pool
  `0x310ac4` → `0x01f83324`, `0x310acc` → `0x01f83314`).
- The code range belongs to **`mspart.dll` / `WAVEAPI.dll`**: export dir
  `0x30d4bc` → base `0x309200` (`PD_*`, incl. `PD_FormatPartition`); export
  dir `0x321bfc` → base `0x30d200` (`ACM_*`/`WAM_*`).
- **Module attribution by `base ≤ file < base+size` is invalid here**: the
  bases overlap (`mspart` needs ≥ `0x309200`–`0x30d5a8`; `WAVEAPI` starts at
  `0x30d200`) because export dirs/names live in the shared `.rdata` blob
  addressed via each module's base+RVA. That is the inference error behind
  round 10.

### `0x6fb05c` is a message builder

It memsets two buffers, fills two 16-byte descriptors, formats
`SD Import: manufacturer_id is different Sys[0x%x] SD[0x%x]` via a
`sprintf`-like helper (`0x6fb0ce`–`0x6fb0d8`), branches on a u16 field id from
`*(r12+4)` compared with **`0x00A2`**, applies the `0 ≤ v < 6` test
(`0x6fb122`–`0x6fb12a`) in the `userdata_type` branch, then
`obj->vtable[5](&descriptor)`.

It takes two numbers + a report code and emits text; it is **not** the
parser.

## Retractions

- **Round 10 “SD format/validate module, delta `0x1130000`, passes the
  `HDD_INFO` path to a COM property” — retracted in full.** Those five
  “string references” were store targets to globals; `V − S = 0x1130000` was
  coincidence.
- **Round 11 “property 17” discussion is moot** (it depended on that false
  link).
- **`0x6fb05c` as comparator/parser — refuted.**

## Still unknown

- **Six-line ↔ field mapping**: unchanged. Constraints: numeric
  `Sys[0x%x] SD[0x%x]`, `userdata_type` in `0..5`, field id `0x00A2`.
- **Card file vs `0x06000000` copy**: the only `HDD_INFO` path-start literal
  has **zero** references; module U uses only suffixes
  (`0xe53374` → `mSD\VER_INFO\…`). Strong hypothesis that `Sys` is compiled
  in, but no code link.
- Message literals resolve to **suffixes** (`0xe53554` → `ort:
  userdata_type…`); no delta makes all of them string starts (best 5/11).
  Linker suffix merging is the working hypothesis; message identity is still
  certain because the full `manufacturer_id` text is the `sprintf` format.
- **Reader location: unknown.** Three routes are closed with reasons: the
  `0x30f008` object, VerInfoCC, comparator-as-parser.

## Card matrix

Final: **89 length-preserving variants, all 72 bytes** (73 content edits +
15 pairwise swaps + 1 reverse), with expected messages/addresses in
`ROUND12.md` §6.

## Next step

Follow the **`USR_Convert_*` family**. `Set finished mark (file=%s)`
(`0xe4dc18`) is the one function in the image that takes a *path* and opens
it — it already knows the card-side `VER_INFO` convention. Locate its module
with a **multi-string cluster test** (≥3 distinct strings in one window,
`solve_data_delta.py --around`), then walk backwards from the path argument.
Per-value `V − S` arithmetic must not be used again.

## Follow-ups

- [ ] Locate the `USR_Convert_*` module via a ≥3-string cluster.
- [ ] Walk backwards from the path argument to the open/parse path.
- [ ] Run the spare-card matrix to settle the six-line mapping.
- [ ] Never infer a module from a single `V − S` match again.
