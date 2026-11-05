# EXP-2026-11-05-27: The 175-method vtable is iPodCC, not NaviStateCC

- **Status:** done (wrong module corrected; reader still unknown)
- **Date:** 2026-11-05
- **Sample:** EU 2011 image
  `105e2032e480e8ba162a2a9d4b6624cb1dafee380379a9908f3f101b15076307`
- **Claims:** C-410…C-417
- **Supersedes:** the round-4 assumption that the constructed vtable belongs
  to NaviStateCC
- **Superseded by:** none

## Question

Does the constructed vtable at `0x170f100–0x170f2b0` belong to NaviStateCC and
contain the map reader?

## Hypothesis

The 175 method VAs are NaviStateCC's COM methods, including the fd/reader.

## Observations

### The vtable is iPodCC's

The constructors at `0x170f100–0x170f2b0` are inside **`iPodCC.DLL`** (file base
`0x1709200`, link-time space `0x0260xxxx`). Surrounding symbols: `CiPodIPC`,
`iPodIPCInit`, `SetTrackTotalNum`, `SetPlayInfo`, `ReadMemTrackTitle`,
`ReadListCategory`, `IPCSender`.

Therefore `0x2e00eb8` — the target of NaviStateCC's `DllGetClassObject` — is a
**shared COM runtime helper**, not NaviStateCC's class factory. Round 4's COM
branch led to the wrong module.

### Slot tables

- Constructor A: 18 slots at `+0x00`, `+0x04`, `+0x70…+0x9c`, `+0xa4…+0xc0`.
- Constructor B: 14 slots at `+0x00`, `+0x04`, `+0x08`, `+0x50`, `+0x70…+0x94`.

Full method-VA lists are in `TRACE5.md` §1.

### Multi-anchor mapping

- 158/175 method VAs can be assigned to a prologue under some delta.
- The deltas cluster in `0x11a3xxxx` and `0x1182xxxx`, mapping to file
  `0x145xxxx–0x14axxxx`.
- **Confidence is low:** deltas within a band differ by only 0x1000–0x2000 and
  map the same VA to adjacent prologues; with 20k function starts the
  assignment is not unique.
- The vtable contains **no** MAL/fd/zlib/DRSTR/tile methods. All slots are
  iPod/media methods.
- There is **no NaviStateCC vtable** as a contiguous pointer table under its
  known code delta (`0x1f07d5c`): a ≥8-pointer prologue-target run scan found
  **0 runs**.

## Still guessed

- That `0x2e00eb8`/`0x171e9e8` is a generic shared COM helper rather than
  NaviStateCC's factory — strongly supported, not proven.
- iPodCC link-time base `0x02600000` (inferred from the pool and neighbouring
  TelemaFvtRegCC table).
- The per-section file map for the 158 assigned methods — low confidence.
- Reader address and NaviStateCC object vtable.

## Next step

The correct static anchor is **NaviStateCC's class data at `0x1d0f8a8`**, not
the shared helper:

1. Find the code that **writes** `0x1d0f8a8` — search the whole payload for a
   store through a register loaded with that literal (including
   `mov.l rN,@(r0,rM)`), or the ROM→RAM initializer table that copies class
   data.
2. The initializer should install the NaviStateCC class factory and object
   vtable; that vtable contains `0xc42520`, `0xc426a4`, `0xc438a4`.
3. If the initializer is not in the ROM, static is closed: use the MAL
   breakpoint or the spare-card matrix.

## Follow-ups

- [ ] Find the `0x1d0f8a8` writer/initializer.
- [ ] Recover the NaviStateCC class factory and vtable containing the fd layer.
- [ ] If absent, defer to the MAL breakpoint/card matrix.
